"""Agent ReAct 核心调度循环 (业务无关)。"""

from typing import AsyncGenerator, Any
from mini_agent.core.context import AgentContext
from mini_agent.core.events import AgentStart, AgentEnd, Error


async def agent_loop(
    context: AgentContext,
    llm_client: Any,
    tool_registry: Any,
) -> AsyncGenerator[Any, None]:
    """核心 ReAct 调度生成器，逐个产出生命周期事件。"""
    # 待具体实现
    yield AgentStart(user_prompt="TODO")
    yield AgentEnd(final_response="TODO")
