"""终端显示与渲染层 (对齐 Pi 工业级规范与沉浸式 TUI 质感)。

特性：
1. 用户消息满宽卡片 (Pi 同款 userMessageBg #213b49，消灭生硬的 "▶ 接收任务:")。
2. 纯净流式思维链 (柔和深灰斜体 dim italic，彻底消除 "[思考过程]" 与 "[回答]" 标签)。
3. 工具执行沉浸面板 (Pi 同款 toolSuccessBg #254131，支持行号、Diff +44 高亮与超长安全折叠)。
4. Markdown 实时流式排版 (Rich Live 消除裸星号，代码 Monokai 着色)。
5. 优雅降级：支持 Rich 终端富文本与 24-bit TrueColor 原生 ANSI 终端环境。
"""

import atexit
import json
import os
import re
import shutil
import signal
import sys
from typing import Any, Dict, List, Optional
from mini_agent.cli.theme import (
    ACCENT_BLUE,
    ACCENT_GREEN,
    ACCENT_YELLOW,
    BG_TOOL_ERROR,
    BG_TOOL_SUCCESS,
    BG_USER,
    FG_ASSISTANT,
    FG_DIFF_ADD,
    FG_THINKING,
    FG_TOOL_ERROR,
    FG_TOOL_SUCCESS,
    FG_USER,
    ansi_bold,
    ansi_dim,
    ansi_fg,
    ansi_italic,
    ansi_reset,
    get_terminal_width,
    render_full_width_box,
    visible_width,
)

# 检查是否安装了 rich 库
try:
    from rich.console import Console
    from rich.live import Live
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.spinner import Spinner
    from rich.syntax import Syntax
    from rich.text import Text
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

LEXER_MAP = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".json": "json",
    ".sh": "bash",
    ".bash": "bash",
    ".md": "markdown",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".sql": "sql",
}


def format_tokens(count: int) -> str:
    """对齐 Pi 的 Token 格式化显示 (如 120, 1.5k, 128k, 1.2M)"""
    if count < 1000:
        return str(count)
    if count < 10000:
        return f"{count / 1000:.1f}k"
    if count < 1000000:
        return f"{round(count / 1000)}k"
    return f"{count / 1000000:.1f}M"


def get_git_branch(cwd: str = ".") -> Optional[str]:
    """获取指定目录下的当前 Git 分支名称"""
    try:
        import subprocess
        res = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=1,
        )
        if res.returncode == 0:
            branch = res.stdout.strip()
            return branch if branch else None
    except Exception:
        pass
    return None


def format_context_gauge(current_tokens: int, max_tokens: int, width: int = 10) -> str:
    """生成形如 [■■■░░░░░░░] 的直观上下文容量占用槽"""
    if max_tokens <= 0:
        return "[░" * width + "]"
    ratio = min(1.0, max(0.0, current_tokens / max_tokens))
    filled = round(ratio * width)
    empty = width - filled
    if _HAS_RICH:
        color = "red" if ratio >= 0.8 else ("yellow" if ratio >= 0.6 else "green")
        return f"[{color}]{'■' * filled}[/{color}][dim]{'░' * empty}[/dim]"
    else:
        c_code = "\033[31m" if ratio >= 0.8 else ("\033[33m" if ratio >= 0.6 else "\033[32m")
        return f"[{c_code}{'■' * filled}\033[0m\033[2m{'░' * empty}\033[0m]"


TOOL_ICONS = {
    "bash": "💻",
    "read_file": "📄",
    "write_file": "📝",
    "edit_file": "✏️",
    "replace_file_content": "✏️",
    "add": "🧮",
}


class WorkingDockRenderable:
    """Rich 自定义 Renderable 组件，支持动态 Spinner 动画与实时运行态底栏 (对齐 Pi)"""

    def __init__(self, display: "TerminalDisplay"):
        self.display = display
        self.spinner = Spinner("dots", style="cyan") if _HAS_RICH else None

    def __rich__(self) -> Any:
        import time
        s_char = "⠋"
        if self.spinner is not None:
            try:
                s_char = self.spinner.render(time.time()).plain.strip() or "⠋"
            except Exception:
                s_char = "⠋"
        ansi_str = self.display.get_working_dock(
            status_text=self.display._current_status_text,
            spinner=s_char,
        )
        if _HAS_RICH:
            return Text.from_ansi(ansi_str)
        return ansi_str


class TerminalDisplay:
    """统一的终端事件渲染器 (对齐 Pi 视觉与交互规范)"""

    def __init__(self, agent: Optional[Any] = None):
        self._in_reasoning = False
        self._streamed_text = False
        self._spinner = None
        self._spinner_active = False
        self._live_display = None
        self._answer_buffer = ""
        self._last_tool_file = None
        self._last_tool_name = None
        self._last_tool_args = {}
        self._agent = agent
        self._current_status_text = "正在思考任务..."
        self._dock_renderable = WorkingDockRenderable(self)
        self._spinner_is_dock = False
        self._dock_active = False
        self._dock_height = 4
        self._scroll_bottom = 0
        self._rows = 0
        self._cols = 0
        self._current_spinner_char = "⠋"
        atexit.register(self._cleanup_on_exit)

    def _cleanup_on_exit(self) -> None:
        """进程退出保护：确保终端同步锁与文本格式复位"""
        if sys.stdout.isatty():
            try:
                sys.stdout.write("\033[0m\033[?2026l")
                sys.stdout.flush()
            except Exception:
                pass

    def enter_working_dock(self, status_text: str = "正在思考任务...") -> None:
        """启动工作态加载指示器 (纯净流式无硬件滚动边距劫持)"""
        self._dock_active = True
        self._current_status_text = status_text
        self.start_spinner(status_text)

    def update_working_dock(self, status_text: str, spinner: Optional[str] = None) -> None:
        """就地刷新工作态指示器文本"""
        self._current_status_text = status_text
        if spinner:
            self._current_spinner_char = spinner
        self.update_status(status_text)

    def leave_working_dock(self) -> None:
        """退出工作态并停止指示器"""
        self._dock_active = False
        self.stop_spinner()

    def attach_agent(self, agent: Any) -> None:
        """关联活跃 Agent 实例以获取实时工作区、遥测指标与运行状态"""
        self._agent = agent

    def get_working_dock(self, status_text: str = "正在思考任务...", spinner: str = "⠋") -> str:
        """生成当前运行态常驻固定底栏 (对齐 Pi: 顶部嵌入 spinner + 底部边框 + 双行遥测信息)"""
        if self._agent is None:
            return ""
        from mini_agent.cli.footer import render_working_bottom_dock
        cwd = getattr(self._agent, "workspace_dir", ".")
        model = getattr(self._agent.client, "model", "default")
        stats = self._agent.context.get_context_stats() if hasattr(self._agent, "context") else {}
        effort = getattr(self._agent.client, "reasoning_effort", "high") or "auto"
        return render_working_bottom_dock(
            cwd=cwd,
            model_name=model,
            context_stats=stats,
            reasoning_effort=effort,
            status_text=status_text,
            spinner=spinner,
        )

    def _stop_live_display(self) -> None:
        """安全停止当前的 Live Markdown 渲染器"""
        if self._live_display is not None:
            try:
                if self._answer_buffer:
                    self._live_display.update(Markdown(self._answer_buffer))
                self._live_display.stop()
            except Exception:
                pass
            self._live_display = None
        self._answer_buffer = ""

    def start_spinner(self, status_text: str = "正在思考任务...") -> None:
        """启动动态思考 / 执行加载指示器"""
        self._current_status_text = status_text
        self._spinner_active = True
        if _HAS_RICH and console and sys.stdout.isatty():
            try:
                self._spinner = console.status(f"[bold cyan]⠋[/bold cyan] [dim]{status_text}[/dim]", spinner="dots")
                self._spinner.start()
            except Exception:
                self._spinner = None
                sys.stdout.write(f"\033[2m⠋ {status_text}\033[0m\r")
                sys.stdout.flush()
        else:
            self._spinner = None
            sys.stdout.write(f"\033[2m⠋ {status_text}\033[0m\r")
            sys.stdout.flush()

    def update_status(self, status_text: str) -> None:
        """平滑更新加载指示器状态文本"""
        self._current_status_text = status_text
        if not self._spinner_active:
            self.start_spinner(status_text)
        elif self._spinner is not None and hasattr(self._spinner, "update"):
            try:
                self._spinner.update(status=f"[bold cyan]⠋[/bold cyan] [dim]{status_text}[/dim]")
            except Exception:
                pass
        else:
            sys.stdout.write(f"\033[2K\r\033[2m⠋ {status_text}\033[0m\r")
            sys.stdout.flush()

    def stop_spinner(self) -> None:
        """平滑停止加载指示器并清理行"""
        if not self._spinner_active:
            return
        self._spinner_active = False
        if self._spinner is not None:
            try:
                self._spinner.stop()
            except Exception:
                pass
            self._spinner = None
        sys.stdout.write("\033[2K\r")
        sys.stdout.flush()

    def render_status_bar(
        self,
        model_name: str,
        context_window: int,
        current_tokens: int,
        latest_cache_hit_rate: float = 0.0,
        workspace_dir: str = ".",
    ) -> None:
        """在提示符前渲染一行紧凑高密度的状态条 (向后兼容方法)"""
        win_str = format_tokens(context_window)
        cur_str = format_tokens(current_tokens)
        pct = round((current_tokens / context_window * 100), 1) if context_window > 0 else 0.0
        gauge = format_context_gauge(current_tokens, context_window, width=8)

        ws_name = os.path.basename(os.path.abspath(workspace_dir)) or workspace_dir
        git_b = get_git_branch(workspace_dir)
        git_str = f" [🌿 {git_b}]" if git_b else ""
        cache_str = f"⚡ 缓存:{latest_cache_hit_rate}%" if latest_cache_hit_rate > 0 else "⚡ 缓存:0%"

        if _HAS_RICH:
            bar_text = (
                f"[dim]╭─[/dim] [bold cyan]🧠 {model_name}[/bold cyan] [dim]({win_str})[/dim] "
                f"│ [cyan]📊 上下文: {cur_str}/{win_str} ({pct}%)[/cyan] {gauge} "
                f"│ [green]{cache_str}[/green] "
                f"│ [dim]📁 {ws_name}{git_str}[/dim]"
            )
            console.print(bar_text)
        else:
            bar_text = (
                f"\033[2m╭─\033[0m \033[1;36m🧠 {model_name}\033[0m \033[2m({win_str})\033[0m "
                f"│ \033[36m📊 上下文: {cur_str}/{win_str} ({pct}%)\033[0m {gauge} "
                f"│ \033[32m{cache_str}\033[0m "
                f"│ \033[2m📁 {ws_name}{git_str}\033[0m"
            )
            print(bar_text)

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
        git_b = get_git_branch(workspace_dir)
        git_str = f" (分支: {git_b})" if git_b else ""
        banner_text = (
            f"🤖 Mini-Agent CLI (v0.1.0)\n"
            f"📁 工作空间: {workspace_dir}{git_str}\n"
            f"🧠 激活模型: {model_name}{win_str}\n"
            f"{session_line}"
            f"🔧 已加载工具: {tools_count} 个\n"
            f"💡 快捷指令: /help | /model | /resume | /compact | /usage | /sessions | /exit"
        )
        if _HAS_RICH:
            console.print(Panel(banner_text, title="[bold cyan]Mini-Agent[/bold cyan]", border_style="cyan"))
        else:
            print("\n" + "=" * 60)
            print(banner_text)
            print("=" * 60 + "\n")

    def print_agent_start(self, prompt: Any) -> None:
        """用户提问渲染：采用 Pi 同款满宽深蓝底色卡片 (userMessageBg)，彻底消灭生硬的前缀"""
        self.stop_spinner()
        self._stop_live_display()
        self._streamed_text = False
        self._in_reasoning = False

        if isinstance(prompt, list):
            text_parts = [p.get("text", "") for p in prompt if isinstance(p, dict) and p.get("type") == "text"]
            has_img = any(isinstance(p, dict) and p.get("type") == "image_url" for p in prompt)
            img_suffix = " 🖼️ [包含图像附件]" if has_img else ""
            display_prompt = " ".join(text_parts) + img_suffix
        else:
            display_prompt = str(prompt)

        # 满宽深蓝底色色块卡片 (对齐 Pi 的 user-message.ts)
        user_card = render_full_width_box(
            display_prompt,
            bg_rgb=BG_USER,
            fg_rgb=FG_USER,
            padding_y=1,
            padding_x=2,
            border_accent_rgb=ACCENT_BLUE,
        )
        sys.stdout.write(f"\n{user_card}\n\n")
        sys.stdout.flush()

        self.enter_working_dock("正在分析任务并规划步骤...")

    def print_assistant_delta(self, delta: str, is_reasoning: bool = False) -> None:
        """流式吐字：
        - 运行态常驻底栏钉在底部，思考与回答平滑流式输出于底栏上方，绝不闪烁擦除；
        - 思考链采用柔和深灰斜体 (dim italic) 自然流式展开，彻底消除 [思考过程] 伪标签；
        - 正式回答无缝平滑衔接，纯净流式直吐 stdout，杜绝任何字符被覆盖或截断。
        """
        self._streamed_text = True

        if self._spinner_active:
            self.stop_spinner()

        if is_reasoning:
            if not self._in_reasoning:
                sys.stdout.write(f"{ansi_fg(FG_THINKING)}{ansi_italic()}")
                self._in_reasoning = True
            sys.stdout.write(delta)
            sys.stdout.flush()
        else:
            if self._in_reasoning:
                sys.stdout.write(f"{ansi_reset()}\n\n")
                sys.stdout.flush()
                self._in_reasoning = False
            self._answer_buffer += delta
            # 当未关联 Agent 且处于 TTY 环境时 (如单元测试)，支持 Live 渲染
            if _HAS_RICH and console and sys.stdout.isatty() and self._agent is None:
                if self._live_display is None:
                    try:
                        self._live_display = Live(
                            Markdown(self._answer_buffer),
                            console=console,
                            refresh_per_second=15,
                            vertical_overflow="visible",
                        )
                        self._live_display.start()
                    except Exception:
                        self._live_display = None
                if self._live_display is not None:
                    try:
                        self._live_display.update(Markdown(self._answer_buffer))
                    except Exception:
                        pass
                else:
                    sys.stdout.write(delta)
                    sys.stdout.flush()
            else:
                sys.stdout.write(delta)
                sys.stdout.flush()

    def print_assistant_message_end(self) -> None:
        """单轮模型输出结束收尾"""
        if self._live_display is not None:
            self._stop_live_display()
        if self._in_reasoning:
            sys.stdout.write(f"{ansi_reset()}\n\n")
            sys.stdout.flush()
            self._in_reasoning = False
        elif self._streamed_text:
            sys.stdout.write("\n\n")
            sys.stdout.flush()
            self._streamed_text = False
        self._answer_buffer = ""

    def print_tool_start(self, tool_name: str, args: Dict[str, Any]) -> None:
        """工具调用启动：记录上下文并即时展示执行指示器"""
        self.print_assistant_message_end()
        self._last_tool_name = tool_name
        self._last_tool_args = args or {}
        self._last_tool_file = (
            args.get("path")
            or args.get("file_path")
            or args.get("target_file")
            or args.get("command")
        )

        # 推断动作动词与简短目标
        action = tool_name
        if tool_name == "write_file":
            action = "write"
        elif tool_name in ("edit_file", "replace_file_content"):
            action = "edit"
        elif tool_name == "read_file":
            action = "read"
        elif tool_name == "bash":
            action = "bash"

        target_display = str(self._last_tool_file or "")[:40]
        self.start_spinner(f"正在执行: {action} {target_display} ...")

    def format_tool_result_box(
        self,
        tool_name: str,
        args: Dict[str, Any],
        result: str,
        is_error: bool = False,
    ) -> str:
        """格式化工具执行结果面板 (满宽沉浸墨绿/墨红面板，对齐 Pi toolSuccessBg 规范)。
        
        支持：
        - edit 工具：真实代码行号、真实上下文字符串、Diff 高亮着色 (+/-) 与超长折叠
        - 其他工具：4位行号对齐、超长折叠
        - 满宽 24-bit TrueColor 自适应终端宽度撑满
        """
        action = tool_name
        if tool_name == "write_file":
            action = "write"
        elif tool_name in ("edit_file", "replace_file_content"):
            action = "edit"
        elif tool_name == "read_file":
            action = "read"
        elif tool_name == "bash":
            action = "bash"

        target_path = (
            args.get("path")
            or args.get("file_path")
            or args.get("target_file")
            or args.get("command")
            or ""
        )
        if not target_path and self._last_tool_file:
            target_path = str(self._last_tool_file)

        header_color = FG_TOOL_ERROR if is_error else FG_TOOL_SUCCESS
        header_text = (
            f"{ansi_fg(header_color)}{ansi_bold()}{action}{ansi_reset()}  "
            f"{ansi_fg(FG_ASSISTANT)}{target_path}{ansi_reset()}"
        )

        panel_lines: List[str] = [header_text]
        raw_text = result.strip()
        lines = raw_text.splitlines()

        # 针对 edit_file / replace_file_content 渲染工业级 Diff 视图
        is_edit = action == "edit" and not is_error
        diff_handled = False

        if is_edit:
            # 模式 1: 如果 result 中包含了标准 Unified Diff 补丁 (如 @@ -40,5 +40,5 @@)
            hunk_re = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")
            has_hunk = any(hunk_re.match(l) for l in lines)
            if has_hunk:
                old_line = 1
                new_line = 1
                in_hunk = False
                for line in lines:
                    m = hunk_re.match(line)
                    if m:
                        old_line = int(m.group(1))
                        new_line = int(m.group(2))
                        if in_hunk:
                            panel_lines.append(f"  {ansi_dim()}...{ansi_reset()}")
                        in_hunk = True
                        continue
                    if not in_hunk:
                        continue
                    if line.startswith("+"):
                        panel_lines.append(f"  {ansi_fg(FG_DIFF_ADD)}+{new_line:4d}  {line[1:]}{ansi_reset()}")
                        new_line += 1
                    elif line.startswith("-"):
                        panel_lines.append(f"  {ansi_fg(FG_TOOL_ERROR)}-{old_line:4d}  {line[1:]}{ansi_reset()}")
                        old_line += 1
                    elif line.startswith(" "):
                        panel_lines.append(f"  {ansi_dim()} {new_line:4d}  {line[1:]}{ansi_reset()}")
                        old_line += 1
                        new_line += 1
                diff_handled = True

            # 模式 2: 从本地磁盘文件中精准定位 new_str，提取真实行号与上下文
            if not diff_handled and target_path:
                norm_path = target_path
                if not os.path.isabs(norm_path) and hasattr(self, "workspace_dir"):
                    norm_path = os.path.join(getattr(self, "workspace_dir", "."), norm_path)
                if os.path.exists(norm_path) and os.path.isfile(norm_path):
                    try:
                        with open(norm_path, "r", encoding="utf-8", errors="replace") as f:
                            disk_content = f.read()
                        new_val = args.get("new_str") or args.get("new_content") or ""
                        old_val = args.get("old_str") or args.get("old_content") or ""
                        if new_val and new_val in disk_content:
                            idx = disk_content.find(new_val)
                            before_text = disk_content[:idx]
                            before_lines = before_text.splitlines()
                            start_line = len(before_lines) + 1

                            after_text = disk_content[idx + len(new_val):]
                            if after_text.startswith("\r\n"):
                                after_text = after_text[2:]
                            elif after_text.startswith("\n"):
                                after_text = after_text[1:]
                            after_lines = after_text.splitlines()

                            # 上方上下文行 (最多 2 行)
                            ctx_before = before_lines[-2:] if before_lines else []
                            ctx_start = max(1, start_line - len(ctx_before))
                            for i, c_line in enumerate(ctx_before):
                                panel_lines.append(f"  {ansi_dim()} {ctx_start + i:4d}  {c_line[:120]}{ansi_reset()}")

                            # 移除的原内容行 (若提供 old_str)
                            if old_val:
                                for i, o_line in enumerate(old_val.splitlines()[:6]):
                                    panel_lines.append(f"  {ansi_fg(FG_TOOL_ERROR)}-{start_line + i:4d}  {o_line[:120]}{ansi_reset()}")
                                if len(old_val.splitlines()) > 6:
                                    panel_lines.append(f"  {ansi_dim()}... (剩余 {len(old_val.splitlines()) - 6} 行原内容已替换){ansi_reset()}")

                            # 新增内容行
                            new_split = new_val.splitlines()
                            for i, n_line in enumerate(new_split[:8]):
                                panel_lines.append(f"  {ansi_fg(FG_DIFF_ADD)}+{start_line + i:4d}  {n_line[:120]}{ansi_reset()}")
                            if len(new_split) > 8:
                                panel_lines.append(f"  {ansi_dim()}... (剩余 {len(new_split) - 8} 行变更已生效){ansi_reset()}")

                            # 下方上下文行 (最多 2 行)
                            ctx_after_start = start_line + len(new_split)
                            for i, a_line in enumerate(after_lines[:2]):
                                panel_lines.append(f"  {ansi_dim()} {ctx_after_start + i:4d}  {a_line[:120]}{ansi_reset()}")

                            diff_handled = True
                    except Exception:
                        pass

            # 模式 3: 优雅降级回退 (带 line 编号的 new_str 列表)
            if not diff_handled and ("new_str" in args or "new_content" in args):
                new_val = args.get("new_str") or args.get("new_content") or ""
                new_lines = new_val.splitlines()
                panel_lines.append(f"  {ansi_dim()}...{ansi_reset()}")
                for idx, nline in enumerate(new_lines[:8], 1):
                    panel_lines.append(f"  {ansi_fg(FG_DIFF_ADD)}+{idx:4d}  {nline[:120]}{ansi_reset()}")
                if len(new_lines) > 8:
                    panel_lines.append(f"  {ansi_dim()}... (剩余 {len(new_lines) - 8} 行变更已生效){ansi_reset()}")
                panel_lines.append(f"  {ansi_dim()}...{ansi_reset()}")
                diff_handled = True

        if not diff_handled:
            # 常规代码或执行日志输出展示
            max_preview_lines = 10
            preview_subset = lines[:max_preview_lines]
            for idx, line in enumerate(preview_subset, 1):
                line_str = line[:120]  # 防超长换行
                if line.startswith("+"):
                    panel_lines.append(f"  {ansi_fg(FG_DIFF_ADD)}{line_str}{ansi_reset()}")
                elif line.startswith("-"):
                    panel_lines.append(f"  {ansi_fg(FG_TOOL_ERROR)}{line_str}{ansi_reset()}")
                else:
                    panel_lines.append(f"  {ansi_dim()}{idx:4d}  {ansi_reset()}{line_str}")

            if len(lines) > max_preview_lines:
                remaining = len(lines) - max_preview_lines
                hint = f"... ({remaining} more lines, {len(lines)} total, ctrl+o to expand)"
                panel_lines.append(f"  {ansi_dim()}{ansi_italic()}{hint}{ansi_reset()}")

        bg_rgb = BG_TOOL_ERROR if is_error else BG_TOOL_SUCCESS
        return render_full_width_box(
            panel_lines,
            bg_rgb=bg_rgb,
            width=None,
            padding_y=1,
            padding_x=2,
            border_accent_rgb=header_color,
        )

    def print_tool_result(self, tool_name: str, result: str, is_error: bool = False) -> None:
        """工具执行结果：满宽沉浸墨绿面板 (toolSuccessBg #254131)，支持行号、Diff 着色与安全折叠"""
        args = self._last_tool_args or {}
        self.stop_spinner()
        panel_box = self.format_tool_result_box(tool_name, args, result, is_error)
        sys.stdout.write(f"\n{panel_box}\n\n")
        sys.stdout.flush()
        self.start_spinner("已获取工具结果，正在继续思考...")

    def replay_history(self, messages: List[Dict[str, Any]]) -> None:
        """回放恢复的会话历史记录 (对齐 Pi resume 行为)。
        
        将历史中的用户提问、思维链、工具调用与结果、助手回答按时间序列完整重放渲染到终端。
        """
        self.stop_spinner()
        self._stop_live_display()
        self._streamed_text = False
        self._in_reasoning = False

        if not messages:
            return

        tool_call_map: Dict[str, Dict[str, Any]] = {}

        for msg in messages:
            role = msg.get("role")
            content = msg.get("content")

            # 1. 用户提问
            if role == "user":
                if isinstance(content, str) and content.startswith("📌 [上下文检查点摘要"):
                    cp_card = render_full_width_box(
                        content,
                        bg_rgb=BG_USER,
                        fg_rgb=FG_USER,
                        padding_y=1,
                        padding_x=2,
                        border_accent_rgb=ACCENT_YELLOW,
                    )
                    sys.stdout.write(f"\n{cp_card}\n\n")
                    sys.stdout.flush()
                    continue

                if isinstance(content, list):
                    text_parts = [p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"]
                    has_img = any(isinstance(p, dict) and p.get("type") in ("image_url", "image") for p in content)
                    img_suffix = " 🖼️ [包含图像附件]" if has_img else ""
                    display_prompt = " ".join(text_parts) + img_suffix
                else:
                    display_prompt = str(content or "")

                if display_prompt.strip():
                    user_card = render_full_width_box(
                        display_prompt,
                        bg_rgb=BG_USER,
                        fg_rgb=FG_USER,
                        padding_y=1,
                        padding_x=2,
                        border_accent_rgb=ACCENT_BLUE,
                    )
                    sys.stdout.write(f"\n{user_card}\n\n")
                    sys.stdout.flush()

            # 2. Assistant 助手消息 (包含思维链、工具调用或正文回答)
            elif role == "assistant":
                # 思考链 (thinking / reasoning)
                reasoning = msg.get("reasoning")
                if reasoning and isinstance(reasoning, str) and reasoning.strip():
                    sys.stdout.write(f"{ansi_fg(FG_THINKING)}{ansi_italic()}{reasoning.strip()}{ansi_reset()}\n\n")
                    sys.stdout.flush()

                # 记录工具调用映射
                raw_tool_calls = msg.get("tool_calls") or []
                for tc in raw_tool_calls:
                    tc_id = tc.get("id") or ""
                    fn = tc.get("function") or {}
                    fn_name = fn.get("name") or tc.get("name") or ""
                    raw_args = fn.get("arguments") or tc.get("arguments") or {}
                    if isinstance(raw_args, str):
                        try:
                            args_dict = json.loads(raw_args)
                        except Exception:
                            args_dict = {"raw": raw_args}
                    elif isinstance(raw_args, dict):
                        args_dict = raw_args
                    else:
                        args_dict = {}
                    if tc_id:
                        tool_call_map[tc_id] = {"name": fn_name, "args": args_dict}

                # Markdown 正文回答
                text_content = ""
                if isinstance(content, str):
                    text_content = content
                elif isinstance(content, list):
                    text_parts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
                    text_content = "".join(text_parts)

                if text_content and text_content.strip():
                    if _HAS_RICH and console:
                        console.print(Markdown(text_content.strip()))
                        sys.stdout.write("\n")
                    else:
                        sys.stdout.write(f"{text_content.strip()}\n\n")
                    sys.stdout.flush()

            # 3. 工具执行结果
            elif role in ("tool", "toolResult"):
                tool_call_id = msg.get("tool_call_id") or ""
                cached_tc = tool_call_map.get(tool_call_id, {})
                tool_name = msg.get("tool_name") or cached_tc.get("name") or "tool"
                tool_args = cached_tc.get("args") or {}
                is_error = bool(msg.get("is_error", False))

                tool_result_str = ""
                if isinstance(content, str):
                    tool_result_str = content
                elif isinstance(content, list):
                    text_parts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
                    tool_result_str = "".join(text_parts)
                else:
                    tool_result_str = str(content or "")

                box_str = self.format_tool_result_box(tool_name, tool_args, tool_result_str, is_error)
                sys.stdout.write(f"\n{box_str}\n\n")
                sys.stdout.flush()

    def print_agent_end(self, total_turns: int, usage: Optional[Dict[str, Any]] = None) -> None:
        """任务全部达成：停止常驻运行态底栏并简练收束"""
        self.stop_spinner()
        self.print_assistant_message_end()
        self.leave_working_dock()
        status_line = f"✨ 任务已完成 (共经历 {total_turns} 轮交互)"
        if _HAS_RICH:
            console.print(f"[success]{status_line}[/success]\n")
        else:
            print(f"\033[32m{status_line}\033[0m\n")

    def print_compaction_start(self, tokens_before: int) -> None:
        """上下文压缩启动提示"""
        self.stop_spinner()
        msg = f"⚡ 上下文达到阈值 (约 {format_tokens(tokens_before)} Tokens)，正在执行智能压缩..."
        if _HAS_RICH:
            console.print(f"[warning]{msg}[/warning]")
        else:
            print(f"\033[33m{msg}\033[0m")
        self.start_spinner("正在执行上下文智能压缩...")

    def print_compaction_end(self, tokens_before: int, tokens_after: int, saved_percent: float) -> None:
        """上下文压缩完成提示"""
        self.stop_spinner()
        msg = f"✨ 智能压缩完成: {format_tokens(tokens_before)} -> {format_tokens(tokens_after)} Tokens (节省 {saved_percent}%)"
        if _HAS_RICH:
            console.print(f"[success]{msg}[/success]\n")
        else:
            print(f"\033[32m{msg}\033[0m\n")

    def print_error(self, message: str) -> None:
        """全局异常或错误提示"""
        self.stop_spinner()
        self.print_assistant_message_end()
        self.leave_working_dock()
        if _HAS_RICH:
            console.print(f"[error]🚨 发生错误: {message}[/error]\n")
        else:
            print(f"\033[31m🚨 发生错误: {message}\033[0m\n")
