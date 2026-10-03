"""终端显示与渲染层。

支持：
1. 优雅回退：优先使用 Rich 渲染；若未安装 Rich 则无缝降级为 ANSI 原生终端色彩，零依赖也能完美运行。
2. 逐字流式打字机效果。
3. 区分普通思考、思维链（Reasoning）与工具调用状态。
"""

import sys
from typing import Any, Dict, Optional

# 检查是否安装了 rich 库
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.theme import Theme
    _HAS_RICH = True
    console = Console(theme=Theme({
        "info": "cyan",
        "warning": "yellow",
        "error": "bold red",
        "success": "bold green",
        "tool": "bold magenta",
        "reasoning": "dim italic cyan",
    }))
except ImportError:
    _HAS_RICH = False
    console = None


class TerminalDisplay:
    """统一的终端事件渲染器"""

    def __init__(self):
        self._in_reasoning = False
        self._streamed_text = False

    def print_banner(self, workspace_dir: str, model_name: str, tools_count: int) -> None:
        """打印漂亮的欢迎启动面板"""
        banner_text = (
            f"🤖 Mini-Agent CLI (v0.1.0)\n"
            f"📁 工作空间: {workspace_dir}\n"
            f"🧠 激活模型: {model_name}\n"
            f"🔧 已加载工具: {tools_count} 个\n"
            f"💡 快捷指令: /help (帮助) | /tools (工具列表) | /clear (清屏重置) | /exit (退出)"
        )
        if _HAS_RICH:
            console.print(Panel(banner_text, title="[bold cyan]Mini-Agent[/bold cyan]", border_style="cyan"))
        else:
            print("\n" + "=" * 60)
            print(banner_text)
            print("=" * 60 + "\n")

    def print_agent_start(self, prompt: str) -> None:
        """任务启动提示"""
        self._streamed_text = False
        self._in_reasoning = False
        if _HAS_RICH:
            console.print(f"\n[info]▶ 正在思考任务:[/info] [bold]{prompt}[/bold]")
        else:
            print(f"\n▶ 正在思考任务: {prompt}")

    def print_assistant_delta(self, delta: str, is_reasoning: bool = False) -> None:
        """流式吐字（打字机效果）"""
        self._streamed_text = True
        if is_reasoning:
            if not self._in_reasoning:
                sys.stdout.write("\033[2m\033[3m[思考过程] " if not _HAS_RICH else "")
                self._in_reasoning = True
            sys.stdout.write(delta)
        else:
            if self._in_reasoning:
                sys.stdout.write("\n[开始回答] \033[0m" if not _HAS_RICH else "\n")
                self._in_reasoning = False
            sys.stdout.write(delta)
        sys.stdout.flush()

    def print_assistant_message_end(self) -> None:
        """单轮模型输出结束，换行整理"""
        if self._streamed_text:
            sys.stdout.write("\n")
            sys.stdout.flush()
            self._streamed_text = False

    def print_tool_start(self, tool_name: str, args: Dict[str, Any]) -> None:
        """工具调用启动"""
        self.print_assistant_message_end()
        args_summary = ", ".join(f"{k}={repr(v)}" for k, v in args.items())
        if _HAS_RICH:
            console.print(f"🔧 [tool]调用工具:[/tool] [bold]{tool_name}[/bold]({args_summary})")
        else:
            print(f"🔧 \033[35m调用工具:\033[0m {tool_name}({args_summary})")

    def print_tool_result(self, tool_name: str, result: str, is_error: bool = False) -> None:
        """工具执行完毕并返回结果"""
        status_text = "❌ 报错失败" if is_error else "✅ 成功"
        color_prefix = "\033[31m" if is_error else "\033[32m"
        reset = "\033[0m"

        # 如果结果很长，简略截断展示防止刷屏
        preview = result.strip()
        if len(preview) > 300:
            preview = preview[:300] + "... (后文已截断展示，完整内容已送入模型上下文)"

        if _HAS_RICH:
            style = "error" if is_error else "success"
            console.print(f"📦 [{style}]{tool_name} {status_text}:[/{style}]\n   {preview}\n")
        else:
            print(f"📦 {color_prefix}{tool_name} {status_text}:{reset}\n   {preview}\n")

    def print_agent_end(self, total_turns: int) -> None:
        """任务全部达成"""
        self.print_assistant_message_end()
        if _HAS_RICH:
            console.print(f"[success]✨ 任务已完成 (共经历 {total_turns} 轮交互)[/success]\n")
        else:
            print(f"\033[32m✨ 任务已完成 (共经历 {total_turns} 轮交互)\033[0m\n")

    def print_error(self, message: str) -> None:
        """全局异常或错误提示"""
        self.print_assistant_message_end()
        if _HAS_RICH:
            console.print(f"[error]🚨 发生错误: {message}[/error]\n")
        else:
            print(f"\033[31m🚨 发生错误: {message}\033[0m\n")
