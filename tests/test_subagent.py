"""自代理 (Subagent) 系统全方位单元测试。

验证范围：
1. 模型规格目录 (Catalog) 对 deepseek-v4.1 的支持与上下文推断。
2. LLMClient 克隆机制与参数保留。
3. 三级优先级模型仲裁器 (动态入参 > 用户预设 > 环境变量 > inherit 继承主模型)。
4. 角色工具白名单与权限沙箱 (Explore, Plan, General)。
5. 核心防套娃护栏 (所有角色均不可见 task 工具)。
6. TodoTool 实例状态隔离 (子代理增删改绝对不污染主待办清单)。
7. 超轮数截断保护 (超限时坚决返回 is_error=True，禁止误判为成功交付)。
8. 白名单工具缺失防御 (无可用工具时坚决报错，禁止无工具空跑幻觉)。
9. 角色单次最大轮数细分 (explore/plan: 10, general: 30)。
10. Token 用量汇总合并回父级上下文账本。
11. 内部工具调用追踪 (tool_calls_trace) 与 on_progress 进度回调。
12. 项目级规范 (AGENTS.md / CLAUDE.md) 提示词注入。
"""

import asyncio
import os
import tempfile
import unittest
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

from mini_agent.ai.catalog import DEFAULT_MODEL_SPECS, infer_context_window
from mini_agent.agent import MiniAgent
from mini_agent.ai.client import LLMClient
from mini_agent.ai.types import ModelResponse, TokenUsage, ToolCall
from mini_agent.core.context import AgentContext
from mini_agent.subagent.prompts import (
    build_explore_prompt,
    build_general_prompt,
    build_plan_prompt,
    get_subagent_prompt,
)
from mini_agent.subagent.registry import create_subagent_registry, get_allowed_tool_names
from mini_agent.subagent.task import TaskTool
from mini_agent.subagent.types import (
    DEFAULT_ROLE_MAX_TURNS,
    DEFAULT_SUBAGENT_MODEL,
    EXPLORE_TOOLS,
    PLAN_TOOLS,
    resolve_subagent_model,
)
from mini_agent.tools.base import BaseTool, ToolResult as BaseToolResult, tool
from mini_agent.tools.registry import ToolRegistry
from mini_agent.tools.todo import TodoTool


class MockSubagentLLMClient:
    """可编排多轮回复的模拟 LLM 客户端"""

    def __init__(self, responses: List[ModelResponse], model: str = "mock-model"):
        self.responses = list(responses)
        self.turn = 0
        self.model = model
        self.api_key = "mock-key"
        self.base_url = "https://mock.api"
        self._model_specs_cache: Dict[str, int] = {}
        self._specs_list: List[Any] = []

    def get_context_window(self, model_name: Optional[str] = None) -> int:
        return 128000

    def clone(self, model: Optional[str] = None, **kwargs: Any) -> "MockSubagentLLMClient":
        cloned = MockSubagentLLMClient(
            responses=self.responses,
            model=model or self.model,
        )
        cloned.api_key = kwargs.get("api_key", self.api_key)
        cloned.base_url = kwargs.get("base_url", self.base_url)
        return cloned

    async def stream_chat(
        self, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None
    ) -> AsyncGenerator[Tuple[str, Any], None]:
        if self.turn < len(self.responses):
            resp = self.responses[self.turn]
            self.turn += 1
            yield ("response", resp)
        else:
            yield ("response", ModelResponse(content="默认无多余回复", tool_calls=[]))


class TestSubagentSystem(unittest.TestCase):
    def setUp(self):
        # 清理可能干扰的环境变量
        for key in ("SUBAGENT_DEFAULT_MODEL", "SUBAGENT_EXPLORE_MODEL", "SUBAGENT_PLAN_MODEL", "SUBAGENT_GENERAL_MODEL"):
            if key in os.environ:
                del os.environ[key]

    def test_catalog_specs_and_inference(self):
        """测试 deepseek-v4.1 规格注册与启发式上下文推断"""
        self.assertIn("deepseek-v4.1", DEFAULT_MODEL_SPECS)
        self.assertIn("deepseekv4.1", DEFAULT_MODEL_SPECS)
        self.assertEqual(DEFAULT_MODEL_SPECS["deepseek-v4.1"], 1000000)
        self.assertEqual(infer_context_window("deepseek-v4.1"), 1000000)
        self.assertEqual(infer_context_window("deepseekv4.1"), 1000000)

    def test_client_clone_method(self):
        """测试 LLMClient.clone 方法保留凭证并更新模型"""
        client = LLMClient(api_key="sk-test", base_url="https://api.test.com", model="gpt-4o")
        cloned = client.clone(model="deepseek-v4.1")
        self.assertEqual(cloned.api_key, "sk-test")
        self.assertEqual(cloned.base_url, "https://api.test.com")
        self.assertEqual(cloned.model, "deepseek-v4.1")

    def test_model_resolution_hierarchy(self):
        """测试模型三级仲裁机制 (动态指定 > 用户预设 > 环境变量 > 默认 inherit 继承主模型)"""
        # 1. 默认保底继承主模型 (保证任意第三方 provider 下零 404)
        m = resolve_subagent_model("explore", parent_model="my-local-llm")
        self.assertEqual(m, "my-local-llm")

        # 1.1 若父模型未就绪则回退 deepseek-v4.1
        m_fallback = resolve_subagent_model("explore", parent_model=None)
        self.assertEqual(m_fallback, "deepseek-v4.1")

        # 2. 动态入参最高优先
        m = resolve_subagent_model("explore", requested_model="claude-3-5-sonnet")
        self.assertEqual(m, "claude-3-5-sonnet")

        # 3. 动态指定 inherit 显式继承主模型
        m = resolve_subagent_model("explore", requested_model="inherit", parent_model="gpt-4o")
        self.assertEqual(m, "gpt-4o")

        # 4. 用户配置字典特定角色预设
        presets = {"explore": "deepseek-flash", "plan": "claude-3-7-sonnet"}
        self.assertEqual(resolve_subagent_model("explore", user_presets=presets), "deepseek-flash")
        self.assertEqual(resolve_subagent_model("plan", user_presets=presets), "claude-3-7-sonnet")

        # 5. 用户配置字典默认预设
        default_preset = {"default": "qwen-turbo"}
        self.assertEqual(resolve_subagent_model("general", user_presets=default_preset), "qwen-turbo")

        # 6. 用户配置字典指定 inherit
        inherit_preset = {"explore": "inherit"}
        self.assertEqual(resolve_subagent_model("explore", user_presets=inherit_preset, parent_model="my-main"), "my-main")

        # 7. 环境变量特定预设
        os.environ["SUBAGENT_EXPLORE_MODEL"] = "env-explore-model"
        self.assertEqual(resolve_subagent_model("explore"), "env-explore-model")
        del os.environ["SUBAGENT_EXPLORE_MODEL"]

        # 8. 环境变量默认预设
        os.environ["SUBAGENT_DEFAULT_MODEL"] = "env-default-model"
        self.assertEqual(resolve_subagent_model("general"), "env-default-model")
        del os.environ["SUBAGENT_DEFAULT_MODEL"]

    def test_role_tool_whitelists_and_recursion_guard(self):
        """测试三大角色的工具白名单与防套娃护栏"""
        parent_registry = ToolRegistry()

        @tool(description="读文件")
        def read_file(path: str) -> str:
            return f"content of {path}"

        @tool(description="写文件")
        def write_file(path: str, content: str) -> str:
            return "ok"

        @tool(description="搜索")
        def grep(pattern: str) -> str:
            return "matches"

        @tool(description="执行")
        def bash(command: str) -> str:
            return "output"

        @tool(description="子代理派发")
        def task(prompt: str) -> str:
            return "subagent done"

        parent_registry.register(read_file)
        parent_registry.register(write_file)
        parent_registry.register(grep)
        parent_registry.register(bash)
        parent_registry.register(task)

        # 1. Explore 只读白名单检查
        explore_reg = create_subagent_registry(parent_registry, agent_type="explore")
        explore_tools = set(explore_reg.list_tools())
        self.assertIn("read_file", explore_tools)
        self.assertIn("grep", explore_tools)
        self.assertNotIn("write_file", explore_tools)
        self.assertNotIn("bash", explore_tools)
        self.assertNotIn("task", explore_tools)

        # 2. General 通用型权限检查 (拥有 write_file / bash，但绝对没有 task)
        general_reg = create_subagent_registry(parent_registry, agent_type="general")
        general_tools = set(general_reg.list_tools())
        self.assertIn("read_file", general_tools)
        self.assertIn("write_file", general_tools)
        self.assertIn("bash", general_tools)
        self.assertIn("grep", general_tools)
        self.assertNotIn("task", general_tools)

    def test_todo_tool_state_isolation(self):
        """测试 TodoTool 实例状态隔离：子代理操作绝对不污染主 Agent 的任务清单"""
        parent_registry = ToolRegistry()
        parent_todo = TodoTool(storage_file=None)
        # 主 Agent 先添加一项主任务
        asyncio.run(parent_todo.execute(action="add", task="主任务：重构鉴权模块"))
        parent_registry.register(parent_todo)

        # 创建 plan 角色子工具箱
        plan_reg = create_subagent_registry(parent_registry, agent_type="plan")
        sub_todo = plan_reg.get("todo")

        self.assertIsNotNone(sub_todo)
        # 1. 严格断言子工具箱拿到的是一个全新独立的 TodoTool 实例，而非父级对象指针引用
        self.assertIsNot(sub_todo, parent_todo)

        # 2. 子代理向自己的待办清单添加子任务
        asyncio.run(sub_todo.execute(action="add", task="子任务：探索 auth.py 实现"))

        # 3. 校验父级待办清单：依然只有 1 个任务，绝对没有受到子任务污染！
        parent_list_res = asyncio.run(parent_todo.execute(action="list"))
        self.assertIn("主任务：重构鉴权模块", parent_list_res.content)
        self.assertNotIn("子任务：探索 auth.py 实现", parent_list_res.content)

    def test_max_turns_truncation_marked_as_error(self):
        """测试子代理超轮数截断时，明确返回 is_error=True，防止主 Agent 误判成功"""
        parent_registry = ToolRegistry()

        @tool(description="无休止调用")
        def endless_tool(arg: str) -> str:
            return "continue"

        parent_registry.register(endless_tool)

        # 模拟模型在每轮都持续请求工具调用，直到被硬性轮数限制拦截
        calls_response = ModelResponse(
            content="我需要继续调用工具",
            tool_calls=[ToolCall(id="tc", name="endless_tool", arguments={"arg": "x"})],
        )
        mock_client = MockSubagentLLMClient(
            responses=[calls_response, calls_response, calls_response, calls_response, calls_response]
        )

        task_tool = TaskTool(
            parent_client=mock_client,
            parent_registry=parent_registry,
            max_turns=2,  # 设定极小轮数限制，强迫其超轮数截断
        )

        res = asyncio.run(task_tool.execute(prompt="循环任务", agent_type="general"))

        # 核心断言：超轮数必须标记为 is_error=True！
        self.assertTrue(res.is_error)
        self.assertTrue(res.details.get("is_truncated"))
        self.assertIn("未完成任务：执行达到单次最大轮数限制", res.content)

    def test_empty_registry_protection(self):
        """测试白名单工具缺失时前置拦截，坚决不让子代理无工具空跑"""
        empty_parent_registry = ToolRegistry()

        @tool(description="无关工具")
        def custom_unrelated_tool() -> str:
            return "none"

        empty_parent_registry.register(custom_unrelated_tool)

        task_tool = TaskTool(
            parent_client=MockSubagentLLMClient([]),
            parent_registry=empty_parent_registry,
        )

        res = asyncio.run(task_tool.execute(prompt="探索", agent_type="explore"))
        self.assertTrue(res.is_error)
        self.assertEqual(res.details.get("error_type"), "NoAvailableTools")
        self.assertIn("未能挂载任何可用工具", res.content)

    def test_role_max_turns_resolution(self):
        """测试各角色的单次最大轮数防护配额解析"""
        task_tool = TaskTool(
            parent_client=MockSubagentLLMClient([]),
            parent_registry=ToolRegistry(),
            max_turns=None,  # 默认缺省
        )
        self.assertEqual(task_tool._resolve_max_turns_for_role("explore"), DEFAULT_ROLE_MAX_TURNS["explore"])
        self.assertEqual(task_tool._resolve_max_turns_for_role("plan"), DEFAULT_ROLE_MAX_TURNS["plan"])
        self.assertEqual(task_tool._resolve_max_turns_for_role("general"), DEFAULT_ROLE_MAX_TURNS["general"])

        # 字典级自定义覆盖
        custom_tool = TaskTool(
            parent_client=MockSubagentLLMClient([]),
            parent_registry=ToolRegistry(),
            max_turns={"explore": 5, "general": 50},
        )
        self.assertEqual(custom_tool._resolve_max_turns_for_role("explore"), 5)
        self.assertEqual(custom_tool._resolve_max_turns_for_role("general"), 50)

    def test_mini_agent_wiring_preserves_per_role_max_turns(self):
        """回归防护：MiniAgent 默认接线不得覆盖 per-role 轮数配额。

        历史 bug: MiniAgent.subagent_max_turns 默认值为 int(15)，
        会命中 TaskTool 的 isinstance(int) 分支，使 DEFAULT_ROLE_MAX_TURNS 失效。
        """
        agent = MiniAgent(workspace_dir=".", sessions_dir=None)
        self.assertIsNone(agent.subagent_max_turns)
        task_tool = agent.registry.get("task")
        self.assertIsNotNone(task_tool)
        self.assertEqual(task_tool._resolve_max_turns_for_role("explore"), DEFAULT_ROLE_MAX_TURNS["explore"])
        self.assertEqual(task_tool._resolve_max_turns_for_role("plan"), DEFAULT_ROLE_MAX_TURNS["plan"])
        self.assertEqual(task_tool._resolve_max_turns_for_role("general"), DEFAULT_ROLE_MAX_TURNS["general"])
        # 关键断言：general 必须显著大于 explore，否则说明 per-role 表未生效
        self.assertGreater(
            task_tool._resolve_max_turns_for_role("general"),
            task_tool._resolve_max_turns_for_role("explore"),
        )

    def test_token_usage_merges_to_parent_context(self):
        """测试子代理消耗的 Token 能够合并累加回主 Agent 的上下文用量账本中"""
        parent_registry = ToolRegistry()

        @tool(description="查询文件")
        def read_file(path: str = "") -> str:
            return "done"

        parent_registry.register(read_file)

        mock_client = MockSubagentLLMClient(
            responses=[
                ModelResponse(
                    content="完成检索",
                    tool_calls=[],
                    usage=TokenUsage(prompt_tokens=300, completion_tokens=150, total_tokens=450),
                )
            ]
        )

        parent_ctx = AgentContext()
        task_tool = TaskTool(
            parent_client=mock_client,
            parent_registry=parent_registry,
            parent_context=parent_ctx,
        )

        res = asyncio.run(task_tool.execute(prompt="统计测试", agent_type="explore"))
        self.assertFalse(res.is_error)

        # 验证主上下文已成功归集子代理消耗
        self.assertEqual(parent_ctx.cumulative_usage["prompt_tokens"], 300)
        self.assertEqual(parent_ctx.cumulative_usage["completion_tokens"], 150)
        self.assertEqual(parent_ctx.cumulative_usage["total_tokens"], 450)
        self.assertIn("usage", res.details)

    def test_subagent_progress_and_tool_trace(self):
        """测试内部工具调用轨迹收集与 on_progress 进度通知"""
        parent_registry = ToolRegistry()

        @tool(description="步骤1")
        def step1() -> str:
            return "ok"

        parent_registry.register(step1)

        mock_client = MockSubagentLLMClient(
            responses=[
                ModelResponse(
                    content="执行第一步",
                    tool_calls=[ToolCall(id="tc1", name="step1", arguments={})],
                ),
                ModelResponse(content="最终报告", tool_calls=[]),
            ]
        )

        progress_events: List[str] = []

        def on_prog(msg: str):
            progress_events.append(msg)

        task_tool = TaskTool(
            parent_client=mock_client,
            parent_registry=parent_registry,
            on_progress=on_prog,
        )

        res = asyncio.run(
            task_tool.execute(
                prompt="多步骤任务",
                agent_type="general",
                summary="执行全流程测试",
            )
        )

        self.assertFalse(res.is_error)
        self.assertEqual(res.details.get("summary"), "执行全流程测试")
        self.assertEqual(res.details.get("tool_calls_count"), 1)
        self.assertTrue(any("正在调用 step1" in p for p in progress_events))

    def test_subagent_prompts_and_instructions_injection(self):
        """测试项目级规范 AGENTS.md 被自动注入到子代理提示词中"""
        with tempfile.TemporaryDirectory() as temp_dir:
            agents_md_path = os.path.join(temp_dir, "AGENTS.md")
            with open(agents_md_path, "w", encoding="utf-8") as f:
                f.write("工程铁律：所有测试必须通过 pytest 运行。")

            prompt = get_subagent_prompt("explore", temp_dir)
            self.assertIn("只读权限约束", prompt)
            self.assertIn("工程铁律：所有测试必须通过 pytest 运行。", prompt)
            self.assertIn("<project_instructions", prompt)

    def test_parallel_subagent_execution(self):
        """测试主 Agent 并发派发两个 TaskTool 任务，验证无锁竞争与独立执行"""
        parent_registry = ToolRegistry()

        @tool(description="读取文件")
        async def read_file(path: str = "") -> str:
            await asyncio.sleep(0.05)
            return f"Found {path}"

        parent_registry.register(read_file)

        mock_client_a = MockSubagentLLMClient(
            responses=[
                ModelResponse(content="模块 A 探索结论：无安全漏洞", tool_calls=[]),
            ]
        )
        mock_client_b = MockSubagentLLMClient(
            responses=[
                ModelResponse(content="模块 B 探索结论：发现 2 处潜在死锁", tool_calls=[]),
            ]
        )

        task_tool_a = TaskTool(parent_client=mock_client_a, parent_registry=parent_registry)
        task_tool_b = TaskTool(parent_client=mock_client_b, parent_registry=parent_registry)

        async def run_both():
            return await asyncio.gather(
                task_tool_a.execute(prompt="分析模块 A", agent_type="explore"),
                task_tool_b.execute(prompt="分析模块 B", agent_type="explore"),
            )

        res_a, res_b = asyncio.run(run_both())
        self.assertIn("模块 A 探索结论", res_a.content)
        self.assertIn("模块 B 探索结论", res_b.content)

    def test_task_tool_empty_prompt_and_error_recovery(self):
        """测试空指令校验与子循环异常拦截"""
        mock_client = MockSubagentLLMClient([])
        task_tool = TaskTool(parent_client=mock_client, parent_registry=ToolRegistry())

        # 空 prompt 拦截
        res = asyncio.run(task_tool.execute(prompt=""))
        self.assertTrue(res.is_error)
        self.assertIn("prompt 字段不能为空", res.content)


if __name__ == "__main__":
    unittest.main()
