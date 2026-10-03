"""测试 ai/client.py 核心能力与模型流式传输"""

import asyncio
from mini_agent.ai.client import LLMClient
from mini_agent.tools.base import tool
from mini_agent.tools.registry import ToolRegistry


# 准备测试工具
@tool(description="计算两数相加")
def add(a: int, b: int) -> int:
    return a + b


async def main():
    registry = ToolRegistry()
    registry.register(add)
    tools = registry.get_schemas()

    client = LLMClient(model="mock")

    print("=== 1. 测试普通对话流式打印 ===")
    messages = [{"role": "user", "content": "你好呀"}]
    async for event_type, data in client.stream_chat(messages, tools=tools):
        if event_type == "text_delta":
            print(data, end="", flush=True)
        elif event_type == "response":
            print(f"\n[最终回复结束] 触发工具数: {len(data.tool_calls)}")

    print("\n=== 2. 测试流式触发 Tool Call 并直接派发工具执行 ===")
    messages = [{"role": "user", "content": "请帮我计算加法"}]
    tool_calls_to_run = []

    async for event_type, data in client.stream_chat(messages, tools=tools):
        if event_type == "text_delta":
            print(data, end="", flush=True)
        elif event_type == "response":
            tool_calls_to_run = data.tool_calls
            print(f"\n[模型判定需要调用的工具]: {tool_calls_to_run}")

    # 将大模型决定的工具调用交给 ToolRegistry 执行
    for tc in tool_calls_to_run:
        print(f"\n🚀 正在执行大模型请求的工具: {tc.name}, 参数: {tc.arguments}")
        result = await registry.execute(tc.name, tc.arguments)
        print(f"📦 工具执行返回结果: content='{result.content}', is_error={result.is_error}")


if __name__ == "__main__":
    asyncio.run(main())
