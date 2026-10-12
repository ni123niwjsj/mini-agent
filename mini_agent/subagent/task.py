"""自代理任务派发工具 (TaskTool)。

核心职责：
1. 充当主 Agent 调用自代理的统一入口 (name: "task")。
2. 依据角色 (explore, plan, general) 自动装配受限工具箱与定制系统提示词。
3. 遵循三级优先级仲裁模型 (动态入参 > 人工预设 > 默认 inherit 继承主模型)。
4. 运行独立沙盒 ReAct 循环，向主 Agent 汇聚高纯度结果，严禁中间过程污染主上下文。
5. 健全防护：超轮数明确标记 is_error=True、有状态工具内存隔离、Token 消耗归集与内部执行追踪。
"""

import os
import uuid
from typing import Any, Callable, Dict, List, Optional, Union
from mini_agent.ai.client import LLMClient
from mini_agent.core.context import AgentContext
from mini_agent.core.events import AgentEnd, Error, ToolCallStart
from mini_agent.core.loop import agent_loop
from mini_agent.core.session import SessionManager
from mini_agent.subagent.prompts import get_subagent_prompt
from mini_agent.subagent.registry import create_subagent_registry
from mini_agent.subagent.types import (
    DEFAULT_ROLE_MAX_TURNS,
    resolve_subagent_model,
)
from mini_agent.tools.base import BaseTool, ToolResult
from mini_agent.tools.registry import ToolRegistry


class TaskTool(BaseTool):
    """自代理 (Subagent) 派发工具"""

    name = "task"
    description = (
        "派发子任务给专门的自代理 (Subagent) 并在隔离上下文中执行。\n"
        "支持角色：\n"
        "- 'explore' (默认): 代码库与网络只读探索，绝无写改副作用 (默认限 10 轮)；\n"
        "- 'plan': 架构与实施方案规划，只读分析并输出分步落地计划 (默认限 10 轮)；\n"
        "- 'general': 独立通用开发与验证，自主闭环复杂子功能 (默认限 30 轮)。\n"
        "子代理在独立沙盒中完成全部试错，只将提炼后的最终成果返回给当前会话。"
    )

    def __init__(
        self,
        parent_client: LLMClient,
        parent_registry: ToolRegistry,
        parent_context: Optional[AgentContext] = None,
        workspace_dir: str = ".",
        user_presets: Optional[Dict[str, str]] = None,
        max_turns: Optional[Union[int, Dict[str, int]]] = None,
        session_manager: Optional[SessionManager] = None,
        on_progress: Optional[Callable[[str], None]] = None,
    ):
        self.parent_client = parent_client
        self.parent_registry = parent_registry
        self.parent_context = parent_context
        self.workspace_dir = os.path.abspath(workspace_dir)
        self.user_presets = user_presets or {}
        self.max_turns = max_turns
        self.session_manager = session_manager
        self.on_progress = on_progress

    def _resolve_max_turns_for_role(self, agent_type: str) -> int:
        """根据角色类型解析其适用的单次最大轮数防护配额"""
        if isinstance(self.max_turns, dict):
            return self.max_turns.get(agent_type, DEFAULT_ROLE_MAX_TURNS.get(agent_type, 15))
        elif isinstance(self.max_turns, int) and self.max_turns > 0:
            return self.max_turns
        return DEFAULT_ROLE_MAX_TURNS.get(agent_type, 15)

    def get_schema(self) -> Dict[str, Any]:
        """获取兼容各大主流大模型的 OpenAI Function Calling JSON Schema"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "prompt": {
                            "type": "string",
                            "description": "委派给子代理的具体任务需求、探查问题或详细指令。",
                        },
                        "agent_type": {
                            "type": "string",
                            "enum": ["explore", "plan", "general"],
                            "description": "子代理角色类型：'explore' (只读探索，默认)、'plan' (方案规划)、'general' (通用闭环开发)。",
                        },
                        "model": {
                            "type": "string",
                            "description": "可选。指定该子代理使用的模型名称 (如 'deepseek-v4.1', 'claude-3-5-sonnet') 或 'inherit' (跟随主模型)。未指定时默认继承主模型。",
                        },
                        "summary": {
                            "type": "string",
                            "description": "可选。该子任务的一句话简短标题或摘要 (如 '搜索鉴权函数定义')，供展示与追溯。",
                        },
                    },
                    "required": ["prompt"],
                },
            },
        }

    async def execute(
        self,
        prompt: str,
        agent_type: str = "explore",
        model: Optional[str] = None,
        summary: Optional[str] = None,
        **kwargs: Any,
    ) -> ToolResult:
        """在独立沙盒中启动并执行子代理"""
        if not prompt or not isinstance(prompt, str) or not prompt.strip():
            return ToolResult(
                content="Error: prompt 字段不能为空，请提供具体的子任务指令。",
                is_error=True,
            )

        # 兼容旧调用或模型传参 description
        task_summary = summary or kwargs.get("description") or ""

        norm_type = (agent_type or "explore").strip().lower()
        if norm_type not in ("explore", "plan", "general"):
            norm_type = "explore"

        # 1. 模型仲裁判定
        parent_model = getattr(self.parent_client, "model", None)
        target_model = resolve_subagent_model(
            agent_type=norm_type,
            requested_model=model,
            user_presets=self.user_presets,
            parent_model=parent_model,
        )

        # 2. 克隆子 Client
        child_client = self.parent_client.clone(model=target_model)

        # 3. 构造专属受限工具箱与系统提示词
        child_registry = create_subagent_registry(self.parent_registry, agent_type=norm_type)
        if not child_registry.list_tools():
            return ToolResult(
                content=(
                    f"Error: 子代理角色 '{norm_type}' 未能挂载任何可用工具 (父工具箱中缺失对应白名单工具)。"
                    f"父工具箱中可用工具列表为: {self.parent_registry.list_tools()}。"
                ),
                is_error=True,
                details={"agent_type": norm_type, "error_type": "NoAvailableTools"},
            )

        child_prompt = get_subagent_prompt(norm_type, self.workspace_dir)

        # 4. 可选的持久化会话记录 (隔离存储在 .sessions/subagents/ 下)
        child_sm: Optional[SessionManager] = None
        if self.session_manager:
            subagents_dir = os.path.join(self.session_manager.storage_dir, "subagents")
            sub_id = f"{norm_type}_{uuid.uuid4().hex[:6]}"
            child_sm = SessionManager(
                storage_dir=subagents_dir,
                session_id=sub_id,
                cwd=self.workspace_dir,
                model=target_model,
            )

        # 5. 实例化子上下文并写入初始任务指令
        role_turns_limit = self._resolve_max_turns_for_role(norm_type)
        child_context_window = child_client.get_context_window(target_model)
        child_context = AgentContext(
            system_prompt=child_prompt,
            session_manager=child_sm,
            context_window=child_context_window,
            max_turns=role_turns_limit,
        )
        child_context.add_user_message(prompt)

        # 6. 独立沙盒执行 ReAct 循环 (捕获内部工具调用轨迹与超轮数截断)
        final_response: str = ""
        total_turns: int = 0
        is_truncated: bool = False
        error_message: Optional[str] = None
        tool_calls_trace: List[Dict[str, Any]] = []

        try:
            async for event in agent_loop(child_context, child_client, child_registry):
                if isinstance(event, AgentEnd):
                    final_response = event.final_response
                    total_turns = event.total_turns
                    is_truncated = getattr(event, "is_truncated", False)
                elif isinstance(event, Error):
                    error_message = event.message
                elif isinstance(event, ToolCallStart):
                    tool_calls_trace.append({"tool": event.tool_name, "args": event.arguments})
                    if self.on_progress:
                        try:
                            self.on_progress(f"[{norm_type}] 正在调用 {event.tool_name}")
                        except Exception:
                            pass
        except Exception as e:
            return ToolResult(
                content=f"Subagent ({norm_type}) 执行异常崩溃: {str(e)}",
                is_error=True,
                details={"agent_type": norm_type, "model": target_model, "error": str(e)},
            )

        # 7. Token 消耗合并至主上下文账本
        child_usage = dict(child_context.cumulative_usage)
        if self.parent_context is not None:
            self.parent_context.merge_subagent_usage(child_usage)

        # 8. 超轮数截断硬防护：若子代理撞上轮数上限，坚决标记为 is_error=True 避免主 Agent 误判成功
        if is_truncated or "任务达到最大轮数限制" in final_response:
            return ToolResult(
                content=(
                    f"Subagent ({norm_type}) 未完成任务：执行达到单次最大轮数限制 ({total_turns} 轮) 中断。"
                    f"\n最后中断时的部分输出：\n{final_response}"
                ),
                is_error=True,
                details={
                    "agent_type": norm_type,
                    "model": target_model,
                    "total_turns": total_turns,
                    "is_truncated": True,
                    "summary": task_summary,
                    "usage": child_usage,
                    "tool_calls_count": len(tool_calls_trace),
                },
            )

        # 9. 运行时未恢复的错误拦截
        if not final_response and error_message:
            return ToolResult(
                content=f"Subagent ({norm_type}) 未完成任务: {error_message}",
                is_error=True,
                details={
                    "agent_type": norm_type,
                    "model": target_model,
                    "turns": total_turns,
                    "usage": child_usage,
                    "tool_calls_count": len(tool_calls_trace),
                },
            )

        if not final_response:
            # 容错尝试提取最后一条助手消息
            for msg in reversed(child_context.messages):
                if msg.get("role") == "assistant" and msg.get("content"):
                    final_response = msg["content"]
                    break

        if not final_response:
            final_response = f"Subagent ({norm_type}) 已执行完毕，但未产生正文回复。"

        return ToolResult(
            content=final_response,
            is_error=False,
            details={
                "agent_type": norm_type,
                "model": target_model,
                "total_turns": total_turns,
                "summary": task_summary,
                "usage": child_usage,
                "tool_calls_count": len(tool_calls_trace),
            },
        )
