"""交互式 REPL 命令行循环。"""

import asyncio
from mini_agent.cli.display import TerminalDisplay


async def start_repl(agent: any) -> None:
    """启动交互式终端 REPL 循环"""
    display = TerminalDisplay()
    print("Welcome to Mini-Agent CLI! (Type 'exit' or 'quit' to leave)")

    while True:
        try:
            user_input = input("\nmini-agent> ").strip()
            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit"):
                print("Goodbye!")
                break
            
            # 运行 Agent 任务
            display.print_agent_start(user_input)
            # 待具体接入 agent.stream
            display.print_agent_end()

        except (KeyboardInterrupt, EOFError):
            print("\nSession interrupted. Bye!")
            break
