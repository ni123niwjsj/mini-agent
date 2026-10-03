"""交互式 REPL 命令行循环。

负责处理用户输入、调度 Agent 事件流并执行斜杠指令 (/help, /clear, /tools, /exit)。
"""

import sys
from typing import Any
from mini_agent.cli.display import TerminalDisplay
from mini_agent.core.events import (
    AgentEnd,
    AgentStart,
    AssistantDelta,
    AssistantMessage,
    Error,
    ToolCallStart,
    ToolResult,
)


def handle_event(display: TerminalDisplay, event: Any) -> None:
    """将 Agent 内核发射的 7 种生命周期事件派发给 TerminalDisplay 渲染"""
    if isinstance(event, AgentStart):
        display.print_agent_start(event.user_prompt)
    elif isinstance(event, AssistantDelta):
        display.print_assistant_delta(event.content, event.is_reasoning)
    elif isinstance(event, AssistantMessage):
        display.print_assistant_message_end()
    elif isinstance(event, ToolCallStart):
        display.print_tool_start(event.tool_name, event.arguments)
    elif isinstance(event, ToolResult):
        display.print_tool_result(event.tool_name, str(event.output), event.is_error)
    elif isinstance(event, AgentEnd):
        display.print_agent_end(event.total_turns)
    elif isinstance(event, Error):
        display.print_error(event.message)


async def start_repl(agent: Any) -> None:
    """启动交互式终端 REPL 循环"""
    display = TerminalDisplay()
    
    # 获取基本信息展示欢迎横幅
    tools = agent.registry.list_tools()
    display.print_banner(
        workspace_dir=getattr(agent, "workspace_dir", "."),
        model_name=getattr(agent.client, "model", "default"),
        tools_count=len(tools),
    )

    while True:
        try:
            # 命令行提示符
            sys.stdout.write("\033[1;36mmini-agent>\033[0m ")
            sys.stdout.flush()
            user_input = sys.stdin.readline()

            # 处理 EOF (Ctrl+D)
            if not user_input:
                print("\n会话结束，再见！")
                break

            user_input = user_input.strip()
            if not user_input:
                continue

            # 处理内置斜杠指令
            if user_input.startswith("/"):
                cmd = user_input.lower()
                if cmd in ("/exit", "/quit"):
                    print("再见！感谢使用 Mini-Agent。")
                    break
                elif cmd == "/clear":
                    agent.context.messages.clear()
                    print("\n🧹 会话历史已清空，上下文已重置。\n")
                    continue
                elif cmd == "/tools":
                    print("\n🔧 当前已注册的可用工具列表:")
                    for t_name in agent.registry.list_tools():
                        tool_obj = agent.registry.get(t_name)
                        desc = tool_obj.description if tool_obj else ""
                        print(f"  • {t_name:12s} - {desc}")
                    print()
                    continue
                elif cmd == "/help":
                    print("\n💡 常用快捷命令:")
                    print("  • /tools : 查看当前已挂载的所有工具")
                    print("  • /clear : 清空所有上下文对话历史")
                    print("  • /exit  : 退出命令行交互")
                    print("  • 直接输入任何文本即可开始与 Agent 交互。\n")
                    continue
                else:
                    print(f"未知指令 '{user_input}'。输入 /help 查看帮助。")
                    continue

            # 驱动 Agent 执行任务并流式渲染
            async for event in agent.stream(user_input):
                handle_event(display, event)

        except KeyboardInterrupt:
            print("\n\n⚠️ 收到中断信号 (Ctrl+C)，当前任务已停止。\n")
            continue
        except Exception as e:
            display.print_error(f"终端运行异常: {str(e)}")
