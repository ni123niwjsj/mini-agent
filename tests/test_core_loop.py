"""测试 core/loop.py 完整的 ReAct 调度循环与 7 种生命周期事件"""

import asyncio
from mini_agent.ai.client import LLMClient
from mini_agent.core.context import AgentContext
from mini_agent.core.loop import agent_loop
from mini_agent.core.events import (
    AgentStart,
    AssistantDelta,
    AssistantMessage,
    ToolCallStart,
    ToolResult,
    AgentEnd,
    Error,
)
from mini_agent.tools.base import tool
from mini_agent.tools.registry import ToolRegistry


# 注册测试工具
@tool(description="计算两数相加")
def add(a: int, b: int) -> int:
    return a + b


async def main():
    registry = ToolRegistry()
    registry.register(add)

    client = LLMClient(model="mock")
    context = AgentContext(system_prompt="你是一个全能助手。")
    context.add_user_message("请帮我计算加法：10 + 20")

    print("🚀 开始启动 ReAct Agent Loop 调度：\n" + "=" * 50)

    async for event in agent_loop(context, client, registry):
        if isinstance(event, AgentStart):
            print(f"[事件 1: AgentStart] 用户提问: '{event.user_prompt}'")

        elif isinstance(event, AssistantDelta):
            # 打字机流式输出
            print(f"{event.content}", end="", flush=True)

        elif isinstance(event, AssistantMessage):
            print(f"\n[事件 3: AssistantMessage] 本轮生成完毕, 附带工具调用: {len(event.tool_calls)} 个")

        elif isinstance(event, ToolCallStart):
            print(f"\n[事件 4: ToolCallStart] 正在调用工具: {event.tool_name}, 参数: {event.arguments}")

        elif isinstance(event, ToolResult):
            print(f"[事件 5: ToolResult] 工具执行返回: content='{event.output}', is_error={event.is_error}\n")

        elif isinstance(event, AgentEnd):
            print(f"[事件 6: AgentEnd] 任务圆满结束！总轮数: {event.total_turns}, 最终回答: '{event.final_response}'")

        elif isinstance(event, Error):
            print(f"[事件 7: Error] 异常报警: {event.message}")

    print("=" * 50)
    print("多轮对话历史上下文记录验证:")
    for idx, msg in enumerate(context.messages):
        role = msg.get("role")
        content = msg.get("content", "")
        print(f"  {idx + 1}. [{role}]: {content[:40]}")


if __name__ == "__main__":
    asyncio.run(main())
