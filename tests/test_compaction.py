"""测试 Phase 8: 智能上下文压缩 (Context Compaction) 核心机制与全流程集成"""

import json
import os
import shutil
import tempfile
import unittest
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

from mini_agent.agent import MiniAgent
from mini_agent.ai.client import LLMClient
from mini_agent.ai.types import ModelResponse, TokenUsage
from mini_agent.core.compaction import (
    FileOperations,
    extract_file_operations,
    generate_compaction_summary,
    perform_compaction,
    serialize_messages_for_summary,
)
from mini_agent.core.context import AgentContext
from mini_agent.core.events import (
    AgentEnd,
    AgentStart,
    CompactionEnd,
    CompactionStart,
)
from mini_agent.core.loop import agent_loop
from mini_agent.core.session import SessionManager
from mini_agent.tools.registry import ToolRegistry


class DummyMockLLMClient:
    """可指定输出内容的 Mock LLMClient"""

    def __init__(self, summary_text: str = ""):
        self.model = "mock-summary"
        self.summary_text = summary_text or (
            "## Goal\n重构并测试压缩模块\n\n"
            "## Constraints & Preferences\n- 无特殊约束\n\n"
            "## Progress\n### Done\n- [x] 实现了核心压缩逻辑\n\n"
            "### In Progress\n- [ ] 补充端到端测试\n\n"
            "### Blocked\n(none)\n\n"
            "## Key Decisions\n- 采用 Pi 式检查点置换策略\n\n"
            "## Next Steps\n1. 验证单元测试通过"
        )

    def get_context_window(self, model: str) -> int:
        return 128000

    async def stream_chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncGenerator[Tuple[str, Any], None]:
        yield ("text_delta", self.summary_text)
        yield (
            "response",
            ModelResponse(
                content=self.summary_text,
                tool_calls=[],
                finish_reason="stop",
                usage=TokenUsage(prompt_tokens=500, completion_tokens=100, total_tokens=600),
            ),
        )


class TestCompaction(unittest.IsolatedAsyncioTestCase):
    """测试智能上下文压缩"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_file_operations_extraction(self):
        """测试从工具调用中精准提取文件读写操作"""
        messages = [
            {"role": "user", "content": "帮我看看 a.py 和 b.py"},
            {
                "role": "assistant",
                "content": "正在读取",
                "tool_calls": [
                    {
                        "id": "c1",
                        "function": {
                            "name": "read_file",
                            "arguments": json.dumps({"path": "src/a.py"}),
                        },
                    },
                    {
                        "id": "c2",
                        "function": {
                            "name": "read_file",
                            "arguments": json.dumps({"file_path": "src/b.py"}),
                        },
                    },
                ],
            },
            {
                "role": "assistant",
                "content": "修改 b.py 并创建 c.py",
                "tool_calls": [
                    {
                        "id": "c3",
                        "function": {
                            "name": "edit_file",
                            "arguments": json.dumps({"path": "src/b.py"}),
                        },
                    },
                    {
                        "id": "c4",
                        "function": {
                            "name": "write_file",
                            "arguments": {"target_file": "src/c.py"},
                        },
                    },
                ],
            },
        ]

        ops = extract_file_operations(messages)
        read_only, modified = ops.compute_file_lists()

        # a.py 仅读过，未被写或改，属于 read_only
        self.assertEqual(read_only, ["src/a.py"])
        # b.py 虽被读过但随后被 edit_file 修改；c.py 被 write_file 写入，均属于 modified
        self.assertEqual(modified, ["src/b.py", "src/c.py"])

    def test_serialize_messages_for_summary(self):
        """测试消息序列化为摘要文本时的格式化与工具超长截断保护"""
        huge_tool_output = "X" * 3000
        messages = [
            {"role": "user", "content": [{"type": "text", "text": "分析数据"}, {"type": "image_url", "image_url": {"url": "data:image/png;base64,xxx"}}]},
            {
                "role": "assistant",
                "content": "正在处理",
                "tool_calls": [{"name": "bash", "arguments": {"cmd": "ls"}}],
            },
            {"role": "tool", "tool_call_id": "call_123", "content": huge_tool_output},
        ]

        text = serialize_messages_for_summary(messages, max_tool_chars=500)
        self.assertIn("[User]: 分析数据 [包含附加图像]", text)
        self.assertIn("[Assistant]: 正在处理", text)
        self.assertIn("[Assistant Tool Calls]: bash({'cmd': 'ls'})", text)
        self.assertIn("[Tool Result (call_123)]:", text)
        # 验证超长文本被截断并附加提示
        self.assertIn("[已截断，省略 2500 字符]", text)
        self.assertNotIn("X" * 3000, text)

    def test_should_auto_compact(self):
        """测试自动压缩阈值判断"""
        ctx = AgentContext(context_window=1000, auto_compact_threshold=0.8)

        # 消息过少或用户轮次不足时不触发
        self.assertFalse(ctx.should_auto_compact())

        # 添加足够的轮次 (3 轮提问及回复)
        ctx.messages = [
            {"role": "user", "content": "第一轮问"},
            {"role": "assistant", "content": "第一轮答"},
            {"role": "user", "content": "第二轮问"},
            {"role": "assistant", "content": "第二轮答"},
            {"role": "user", "content": "第三轮问"},
            {"role": "assistant", "content": "第三轮答"},
        ]

        # 当前 prompt_tokens 仅 500 (50% < 80%)，不触发
        ctx.latest_usage["prompt_tokens"] = 500
        self.assertFalse(ctx.should_auto_compact())

        # 当前 prompt_tokens 达到 850 (85% >= 80%)，触发
        ctx.latest_usage["prompt_tokens"] = 850
        self.assertTrue(ctx.should_auto_compact())

        # 若阈值设为 0，不触发
        ctx.auto_compact_threshold = 0.0
        self.assertFalse(ctx.should_auto_compact())

    async def test_perform_compaction_atomic_replacement(self):
        """测试 perform_compaction 原子置换上下文与保留最近轮次"""
        client = DummyMockLLMClient()
        session_mgr = SessionManager(storage_dir=self.temp_dir, session_id="test_compaction")
        ctx = AgentContext(context_window=1000, session_manager=session_mgr)

        # 构建 4 轮对话历史
        ctx.messages = [
            {"role": "user", "content": "任务目标：创建项目"},
            {"role": "assistant", "content": "好的", "tool_calls": [{"name": "write_file", "arguments": {"path": "main.py"}}]},
            {"role": "tool", "tool_call_id": "tc1", "content": "Created"},
            {"role": "user", "content": "第二步：读取文档"},
            {"role": "assistant", "content": "正在读", "tool_calls": [{"name": "read_file", "arguments": {"path": "README.md"}}]},
            {"role": "tool", "tool_call_id": "tc2", "content": "# Readme"},
            # 保留最近 2 轮:
            {"role": "user", "content": "第三步：编写测试"},
            {"role": "assistant", "content": "正在写测试"},
            {"role": "user", "content": "第四步：运行测试"},
            {"role": "assistant", "content": "测试已全部通过"},
        ]
        ctx.latest_usage["prompt_tokens"] = 800

        result = await perform_compaction(ctx, client, keep_recent_turns=2)
        self.assertIsNotNone(result)
        self.assertGreater(result["tokens_before"], 0)
        self.assertGreater(result["saved_tokens"], 0)
        self.assertIn("main.py", result["modified_files"])
        self.assertIn("README.md", result["read_files"])

        # 验证重构后的上下文：
        # [0]: Checkpoint Message (user)
        # [1]: Ack Message (assistant)
        # [2..]: 保留的最近 2 轮对话 (第三步问、第三步答、第四步问、第四步答)
        self.assertEqual(len(ctx.messages), 6)
        self.assertIn("📌 [上下文检查点摘要", ctx.messages[0]["content"])
        self.assertEqual(ctx.messages[1]["role"], "assistant")
        self.assertEqual(ctx.messages[2]["content"], "第三步：编写测试")
        self.assertEqual(ctx.messages[3]["content"], "正在写测试")
        self.assertEqual(ctx.messages[4]["content"], "第四步：运行测试")
        self.assertEqual(ctx.messages[5]["content"], "测试已全部通过")

        # 验证持久化文件中写入了 type: "compaction"
        session_file = session_mgr.current_session_file
        with open(session_file, "r", encoding="utf-8") as f:
            lines = [json.loads(line) for line in f if line.strip()]
        compaction_entries = [e for e in lines if e.get("type") == "compaction"]
        self.assertEqual(len(compaction_entries), 1)
        self.assertIn("README.md", compaction_entries[0]["details"]["read_files"])

    def test_session_reload_reconstructs_from_compaction(self):
        """测试从包含 compaction 记录的会话文件恢复时重构历史"""
        session_mgr = SessionManager(storage_dir=self.temp_dir, session_id="reload_compaction")
        # 1. 模拟写入被压缩前的消息
        session_mgr.append_message(role="user", content="旧历史1")
        session_mgr.append_message(role="assistant", content="旧历史答1")
        # 2. 写入压缩记录
        session_mgr.append_compaction(
            summary="## Goal\n重构会话\n## Progress\n全部完成",
            tokens_before=1000,
            tokens_after=200,
            details={"read_files": ["f1.txt"], "modified_files": []},
        )
        # 3. 写入压缩后追加的后续消息
        session_mgr.append_message(role="user", content="压缩后的新提问")
        session_mgr.append_message(role="assistant", content="压缩后的新回答")

        # 从 session 文件恢复
        header, messages = session_mgr.load_session("reload_compaction")
        self.assertEqual(header["session_id"], "reload_compaction")
        # 验证旧历史被冲掉，messages 严格从检查点开始：
        # [0] 检查点 user, [1] 检查点 assistant, [2] 压缩后的新提问, [3] 压缩后的新回答
        self.assertEqual(len(messages), 4)
        self.assertIn("📌 [上下文检查点摘要", messages[0]["content"])
        self.assertIn("重构会话", messages[0]["content"])
        self.assertEqual(messages[1]["role"], "assistant")
        self.assertEqual(messages[2]["content"], "压缩后的新提问")
        self.assertEqual(messages[3]["content"], "压缩后的新回答")

    async def test_auto_compaction_in_agent_loop(self):
        """测试 ReAct 循环在到达阈值时自动触发压缩并继续完成任务"""
        registry = ToolRegistry()
        # 创建一个阈值很低的 context
        client = LLMClient(model="mock")
        ctx = AgentContext(
            system_prompt="助手",
            context_window=1000,
            auto_compact_threshold=0.5,  # 50% 阈值
        )
        # 填充足够轮次以满足压缩前置条件
        ctx.messages = [
            {"role": "user", "content": "第一问"},
            {"role": "assistant", "content": "第一答"},
            {"role": "user", "content": "第二问"},
            {"role": "assistant", "content": "第二答"},
            {"role": "user", "content": "计算 10 + 20"},  # 第三问 (保留最近轮次)
        ]
        # 设置当前 prompt_tokens 超过阈值 (600 / 1000 = 60% >= 50%)
        ctx.latest_usage["prompt_tokens"] = 600

        events = []
        async for event in agent_loop(ctx, client, registry):
            events.append(event)

        # 验证在循环中发射了 CompactionStart 和 CompactionEnd 事件
        start_events = [e for e in events if isinstance(e, CompactionStart)]
        end_events = [e for e in events if isinstance(e, CompactionEnd)]
        self.assertEqual(len(start_events), 1)
        self.assertEqual(len(end_events), 1)
        self.assertGreater(end_events[0].saved_percent, 0.0)

        # 循环继续向下执行完成任务
        agent_end = next(e for e in events if isinstance(e, AgentEnd))
        self.assertIsNotNone(agent_end)

    async def test_mini_agent_compact_facade(self):
        """测试 MiniAgent 门面方法 compact()"""
        mock_client = DummyMockLLMClient()
        agent = MiniAgent(client=mock_client, sessions_dir=self.temp_dir, auto_compact_threshold=0.75)
        self.assertEqual(agent.context.auto_compact_threshold, 0.75)

        # 模拟积累了 3 轮交互
        for i in range(1, 4):
            agent.context.add_user_message(f"用户问题 {i}")
            agent.context.add_assistant_message(f"助手回答 {i}")

        result = await agent.compact(keep_recent_turns=2)
        self.assertIsNotNone(result)
        self.assertIn("tokens_before", result)
        self.assertIn("tokens_after", result)
        self.assertIn("📌 [上下文检查点摘要", agent.context.messages[0]["content"])


if __name__ == "__main__":
    unittest.main()
