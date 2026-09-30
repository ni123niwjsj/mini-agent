"""终端显示与渲染层 (基于 Rich 库)。"""

from typing import Optional


class TerminalDisplay:
    """负责将 Agent 事件以优美格式输出到终端"""

    def print_agent_start(self, prompt: str) -> None:
        print(f"\n🚀 Agent Started: {prompt}\n")

    def print_assistant_delta(self, delta: str, is_reasoning: bool = False) -> None:
        # 流式打印 token
        print(delta, end="", flush=True)

    def print_tool_start(self, tool_name: str, args: dict) -> None:
        print(f"\n🔧 [Executing: {tool_name}] with {args}...")

    def print_tool_result(self, tool_name: str, result: str, is_error: bool = False) -> None:
        status = "❌ Failed" if is_error else "✅ Success"
        print(f"📦 [{tool_name} {status}]:\n{result}\n")

    def print_agent_end(self) -> None:
        print("\n✨ Done.\n")

    def print_error(self, message: str) -> None:
        print(f"\n❌ Error: {message}\n")
