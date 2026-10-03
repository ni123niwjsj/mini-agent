"""Agent 组装门面类 (Facade)。

负责组装 LLMClient、ToolRegistry、AgentContext 并发起循环。
保持极简，不堆砌业务逻辑。
"""

import os
from typing import Any, AsyncGenerator, Callable, Optional, Union
from mini_agent.ai.client import LLMClient
from mini_agent.core.context import AgentContext
from mini_agent.core.loop import agent_loop
from mini_agent.tools.base import BaseTool, tool
from mini_agent.tools.registry import ToolRegistry
from mini_agent.tools.file import ReadFileTool, WriteFileTool
from mini_agent.tools.edit import EditFileTool
from mini_agent.tools.bash import BashTool


def build_system_prompt(workspace_dir: str) -> str:
    """构建注入环境信息的标准 System Prompt"""
    return (
        f"You are Mini-Agent, an autonomous coding and task execution assistant.\n"
        f"- Current Workspace Directory: {workspace_dir}\n"
        f"- Guidelines:\n"
        f"  1. Be concise, direct, and accurate.\n"
        f"  2. Use available tools whenever you need to examine files, run terminal commands, or perform computations.\n"
        f"  3. When an error occurs in tool execution, analyze the error output and attempt to self-correct."
    )


@tool(description="计算两数相加")
def add(a: int, b: int) -> int:
    """加法辅助计算工具"""
    return a + b


class MiniAgent:
    """轻量 Coding Agent 门面类"""

    def __init__(
        self,
        client: Optional[LLMClient] = None,
        system_prompt: Optional[str] = None,
        workspace_dir: str = ".",
    ):
        self.workspace_dir = os.path.abspath(workspace_dir)
        self.client = client or LLMClient()
        
        prompt = system_prompt or build_system_prompt(self.workspace_dir)
        self.context = AgentContext(system_prompt=prompt)
        
        self.registry = ToolRegistry()
        self._register_default_tools(self.workspace_dir)

    def _register_default_tools(self, workspace_dir: str) -> None:
        """注册默认基础工具集"""
        self.registry.register(add)
        self.registry.register(ReadFileTool())
        self.registry.register(WriteFileTool())
        self.registry.register(EditFileTool())
        self.registry.register(BashTool(cwd=workspace_dir))

    def register_tool(self, tool_or_func: Union[BaseTool, Callable]) -> None:
        """供用户自定义挂载新工具"""
        self.registry.register(tool_or_func)

    async def stream(self, prompt: str) -> AsyncGenerator[Any, None]:
        """流式运行任务并返回事件流"""
        self.context.add_user_message(prompt)
        async for event in agent_loop(self.context, self.client, self.registry):
            yield event
