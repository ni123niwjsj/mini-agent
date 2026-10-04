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


def format_tokens(count: int) -> str:
    """对齐 Pi 的 Token 格式化显示 (如 120, 1.5k, 128k, 1.2M)"""
    if count < 1000:
        return str(count)
    if count < 10000:
        return f"{count / 1000:.1f}k"
    if count < 1000000:
        return f"{round(count / 1000)}k"
    return f"{count / 1000000:.1f}M"


class TerminalDisplay:
    """统一的终端事件渲染器"""

    def __init__(self):
        self._in_reasoning = False
        self._streamed_text = False

    def print_banner(
        self,
        workspace_dir: str,
        model_name: str,
        tools_count: int,
        session_id: Optional[str] = None,
        context_window: Optional[int] = None,
    ) -> None:
        """打印漂亮的欢迎启动面板"""
        session_line = f"💾 当前会话: {session_id}\n" if session_id else ""
        win_str = f" [窗口: {format_tokens(context_window)}]" if context_window else ""
        banner_text = (
            f"🤖 Mini-Agent CLI (v0.1.0)\n"
            f"📁 工作空间: {workspace_dir}\n"
            f"🧠 激活模型: {model_name}{win_str}\n"
            f"{session_line}"
            f"🔧 已加载工具: {tools_count} 个\n"
            f"💡 快捷指令: /help | /compact | /models | /usage | /sessions | /resume <id> | /tools | /exit"
        )
        if _HAS_RICH:
            console.print(Panel(banner_text, title="[bold cyan]Mini-Agent[/bold cyan]", border_style="cyan"))
        else:
            print("\n" + "=" * 60)
            print(banner_text)
            print("=" * 60 + "\n")

    def print_agent_start(self, prompt: Any) -> None:
        """任务启动提示"""
        self._streamed_text = False
        self._in_reasoning = False
        if isinstance(prompt, list):
            text_parts = [p.get("text", "") for p in prompt if isinstance(p, dict) and p.get("type") == "text"]
            has_img = any(isinstance(p, dict) and p.get("type") == "image_url" for p in prompt)
            img_suffix = " 🖼️ [包含图像附件]" if has_img else ""
            display_prompt = " ".join(text_parts) + img_suffix
        else:
            display_prompt = str(prompt)

        if _HAS_RICH:
            console.print(f"\n[info]▶ 正在思考任务:[/info] [bold]{display_prompt}[/bold]")
        else:
            print(f"\n▶ 正在思考任务: {display_prompt}")

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

    def print_agent_end(self, total_turns: int, usage: Optional[Dict[str, Any]] = None) -> None:
        """任务全部达成并渲染用量与缓存统计"""
        self.print_assistant_message_end()
        status_line = f"✨ 任务已完成 (共经历 {total_turns} 轮交互)"
        if _HAS_RICH:
            console.print(f"[success]{status_line}[/success]")
        else:
            print(f"\033[32m{status_line}\033[0m")

        if usage and (usage.get("current_tokens", 0) > 0 or usage.get("cumulative_total_tokens", 0) > 0):
            cur = format_tokens(usage.get("current_tokens", 0))
            win = format_tokens(usage.get("context_window", 128000))
            pct = usage.get("percent", 0.0)
            cum_in = format_tokens(usage.get("cumulative_prompt_tokens", 0))
            cum_out = format_tokens(usage.get("cumulative_completion_tokens", 0))
            latest_r = format_tokens(usage.get("latest_cached_tokens", 0))
            ch = usage.get("latest_cache_hit_rate", 0.0)

            stats_str = (
                f"📊 用量统计: ↑{cum_in} ↓{cum_out} | "
                f"缓存命中: R{latest_r} (CH {ch}%) | "
                f"上下文: {cur}/{win} ({pct}%)"
            )
            if _HAS_RICH:
                console.print(f"[dim]{stats_str}[/dim]\n")
            else:
                print(f"\033[2m{stats_str}\033[0m\n")
        else:
            print()

    def print_compaction_start(self, tokens_before: int) -> None:
        """上下文压缩启动提示"""
        self.print_assistant_message_end()
        msg = f"⚡ 上下文达到阈值 (约 {format_tokens(tokens_before)} Tokens)，正在执行智能压缩..."
        if _HAS_RICH:
            console.print(f"[warning]{msg}[/warning]")
        else:
            print(f"\033[33m{msg}\033[0m")

    def print_compaction_end(self, tokens_before: int, tokens_after: int, saved_percent: float) -> None:
        """上下文压缩完成提示"""
        self.print_assistant_message_end()
        msg = f"✨ 智能压缩完成: {format_tokens(tokens_before)} -> {format_tokens(tokens_after)} Tokens (节省 {saved_percent}%)"
        if _HAS_RICH:
            console.print(f"[success]{msg}[/success]\n")
        else:
            print(f"\033[32m{msg}\033[0m\n")

    def print_error(self, message: str) -> None:
        """全局异常或错误提示"""
        self.print_assistant_message_end()
        if _HAS_RICH:
            console.print(f"[error]🚨 发生错误: {message}[/error]\n")
        else:
            print(f"\033[31m🚨 发生错误: {message}\033[0m\n")
