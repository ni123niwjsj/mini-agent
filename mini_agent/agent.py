"""Agent 组装门面类 (Facade)。

负责组装 LLMClient、ToolRegistry、AgentContext 并发起循环。
保持极简，不堆砌业务逻辑。
"""

from typing import Any, AsyncGenerator, Optional
from mini_agent.ai.client import LLMClient
from mini_agent.core.context import AgentContext
from mini_agent.core.loop import agent_loop
from mini_agent.tools.registry import ToolRegistry
from mini_agent.tools.file import ReadFileTool, WriteFileTool
from mini_agent.tools.edit import EditFileTool
from mini_agent.tools.bash import BashTool


class MiniAgent:
    """轻量 Coding Agent 门面类"""

    def __init__(
        self,
        client: Optional[LLMClient] = None,
        system_prompt: Optional[str] = None,
        workspace_dir: str = ".",
    ):
        self.client = client or LLMClient()
        self.context = AgentContext(
            system_prompt=system_prompt or "You are Mini-Agent, an expert coding assistant."
        )
        self.registry = ToolRegistry()
        self._register_default_tools(workspace_dir)

    def _register_default_tools(self, workspace_dir: str) -> None:
        """注册默认 Coding 工具集"""
        self.registry.register(ReadFileTool())
        self.registry.register(WriteFileTool())
        self.registry.register(EditFileTool())
        self.registry.register(BashTool(cwd=workspace_dir))

    async def stream(self, prompt: str) -> AsyncGenerator[Any, None]:
        """流式运行任务并返回事件流"""
        self.context.add_user_message(prompt)
        async for event in agent_loop(self.context, self.client, self.registry):
            yield event
