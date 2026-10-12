"""智能终端输入槽与斜杠指令内联自动补全组件 (Command Autocomplete Overlay)。

对齐 Pi TUI Editor SelectList 规范：
1. 监听键盘输入，检测到以 '/' 开头时自动弹出命令建议悬浮列表；
2. 包含完整的命令元数据：命令名、参数占位提示 (argHint)、功能描述说明 (description)；
3. 支持键盘方向键 (↑ / ↓) 在候选建议中无缝移动高亮；
4. 支持 Tab 或 Enter 快速采纳补全，Esc 随时关闭浮层；
5. 在非补全状态下支持 ↑ / ↓ 检索历史输入历史 (History Navigation)；
6. 支持 UTF-8 多字节中文输入与退格处理；
7. 同步原子渲染 (\x1b[?2026h ... \x1b[?2026l)，零闪烁无界面撕裂；
8. 非 TTY 环境 (测试、重定向管道) 优雅降级为原生 input()。
"""

import os
import sys
import unicodedata
from dataclasses import dataclass
from typing import Any, List, Optional
from mini_agent.cli.footer import (
    render_input_bottom_dock,
    render_input_top_border,
)
from mini_agent.cli.theme import (
    ACCENT_BLUE,
    DIVIDER_PURPLE,
    FG_DOCK_BRIGHT,
    FG_DOCK_MUTED,
    ansi_bold,
    ansi_dim,
    ansi_fg,
    ansi_reset,
    get_terminal_width,
    visible_width,
)

HISTORY_FILE = os.path.expanduser("~/.mini_agent_history")


@dataclass
class SlashCommand:
    """斜杠指令元数据 (对齐 Pi SlashCommand 规范)"""
    name: str          # 指令名称，如 "/model"
    arg_hint: str      # 参数提示，如 "[名称]" 或 "<节点ID>"
    description: str   # 功能说明，如 "切换激活模型或呼出模型选择菜单"


# 完整注册的内置斜杠指令目录
SLASH_COMMANDS_REGISTRY: List[SlashCommand] = [
    SlashCommand("/model", "[名称]", "切换激活模型或呼出模型选择菜单"),
    SlashCommand("/models", "", "浏览服务端可用模型规格目录"),
    SlashCommand("/resume", "[序号/ID]", "呼出会话恢复菜单或恢复指定历史会话"),
    SlashCommand("/sessions", "", "列出所有已保存的历史会话列表"),
    SlashCommand("/new", "", "保存当前会话并创建全新空白会话"),
    SlashCommand("/undo", "", "撤销上一轮提问与回复，退回上一个分支点"),
    SlashCommand("/tree", "", "以 Git Commit Graph 风格渲染会话分支拓扑树"),
    SlashCommand("/checkout", "<节点ID>", "时光穿梭切换到指定分支节点"),
    SlashCommand("/compact", "", "对当前上下文执行智能摘要压缩并释放空间"),
    SlashCommand("/usage", "", "查看当前上下文与 Token 遥测消耗统计"),
    SlashCommand("/stats", "", "查看会话统计指标与缓存命中率"),
    SlashCommand("/effort", "<low|medium|high|none>", "设置模型思考强度 (Reasoning Effort)"),
    SlashCommand("/turns", "[轮数|0]", "设置单次任务最大轮数限制 (0 为无限制)"),
    SlashCommand("/tools", "", "查看当前已挂载的所有可用工具及描述"),
    SlashCommand("/image", "<路径> [提示词]", "上传并分析本地图像文件"),
    SlashCommand("/alt", "", "切换全屏 Alt-Screen 模式与标准终端模式"),
    SlashCommand("/clear", "", "清空当前屏幕与上下文工作区"),
    SlashCommand("/help", "", "查看命令帮助与键盘操作指南"),
    SlashCommand("/exit", "", "保存会话并安全退出 Mini-Agent"),
    SlashCommand("/quit", "", "退出命令行"),
]


def filter_slash_commands(prefix: str) -> List[SlashCommand]:
    """根据用户输入的字符前缀模糊筛选命令 (不区分大小写)"""
    p = prefix.lower().strip()
    if not p or p == "/":
        return list(SLASH_COMMANDS_REGISTRY)

    # 1. 严格前缀匹配优先
    exact_prefix = [c for c in SLASH_COMMANDS_REGISTRY if c.name.lower().startswith(p)]
    if exact_prefix:
        return exact_prefix

    # 2. 包含匹配或描述匹配回退
    query = p[1:] if p.startswith("/") else p
    sub_matches = [
        c for c in SLASH_COMMANDS_REGISTRY
        if query in c.name.lower() or query in c.description.lower()
    ]
    return sub_matches


def render_autocomplete_dropdown(
    matches: List[SlashCommand],
    selected_idx: int,
    width: int,
    max_visible: int = 5,
) -> List[str]:
    """渲染内联 SelectList 悬浮菜单卡片 (对齐 Pi Editor Autocomplete 视觉)"""
    if not matches:
        return []

    reset = ansi_reset()
    lines: List[str] = []

    # 菜单顶部分割线
    lines.append(f"{ansi_fg(DIVIDER_PURPLE)}{'─' * width}{reset}")

    # 计算可视窗口范围 (支持上下滚动分页)
    total = len(matches)
    start_idx = 0
    if selected_idx >= max_visible:
        start_idx = selected_idx - max_visible + 1
    end_idx = min(start_idx + max_visible, total)

    visible_items = matches[start_idx:end_idx]

    for rel_idx, cmd in enumerate(visible_items):
        abs_idx = start_idx + rel_idx
        is_sel = (abs_idx == selected_idx)

        arg_str = f" {ansi_fg(ACCENT_BLUE)}{cmd.arg_hint}{reset}" if cmd.arg_hint else ""
        desc_str = f" {ansi_dim()}│ {cmd.description}{reset}"

        if is_sel:
            cursor = f"{ansi_fg(ACCENT_BLUE)}{ansi_bold()}❯{reset}"
            # 高亮选中项 (带反白背景底色卡片)
            tag = f"\033[1;37m\033[44m {cmd.name} \033[0m"
            line = f"  {cursor} {tag}{arg_str}{desc_str}"
        else:
            cursor = " "
            tag = f"{ansi_fg(FG_DOCK_BRIGHT)}{ansi_bold()}{cmd.name}{reset}"
            line = f"  {cursor} {tag}{arg_str}{desc_str}"

        lines.append(line)

    # 菜单底部分割线
    lines.append(f"{ansi_fg(DIVIDER_PURPLE)}{'─' * width}{reset}")
    return lines


def _load_history(history_file: str = HISTORY_FILE) -> List[str]:
    """加载历史输入列表"""
    if os.path.exists(history_file):
        try:
            with open(history_file, "r", encoding="utf-8", errors="ignore") as f:
                return [line.rstrip("\r\n") for line in f if line.strip()]
        except Exception:
            return []
    return []


def _append_history(line: str, history_file: str = HISTORY_FILE) -> None:
    """持久化新命令到历史文件与 readline 历史"""
    cleaned = line.strip()
    if not cleaned:
        return
    try:
        with open(history_file, "a", encoding="utf-8") as f:
            f.write(cleaned + "\n")
    except Exception:
        pass
    try:
        import readline
        readline.add_history(cleaned)
    except Exception:
        pass


def is_interactive_tty() -> bool:
    """检查是否处于真实的交互式 TTY 终端环境 (排除单元测试 Mock 或重定向管道)"""
    import builtins
    if hasattr(builtins.input, "mock") or hasattr(builtins.input, "assert_called"):
        return False
    return sys.stdin.isatty() and sys.stdout.isatty()


def read_line_with_autocomplete(
    agent: Optional[Any] = None,
    history_file: str = HISTORY_FILE,
) -> str:
    """带斜杠指令内联建议浮层的智能终端输入读取器。
    
    在用户键入 '/' 时即时展现菜单，支持方向键选择与 Tab/Enter 自动补全；
    在普通提问输入时保持纯净光标槽，支持方向键翻阅历史命令与退格操作。
    """
    if not is_interactive_tty():
        # 非 TTY 环境或单元测试 Mock 环境优雅降级为原生 input()
        return input("")

    history = _load_history(history_file)
    history_idx = len(history)  # 指向最新空白草稿

    buffer = ""
    cursor_pos = 0
    saved_draft = ""  # 保存开始翻阅历史前正在输入的草稿

    autocomplete_active = False
    autocomplete_selected = 0
    matches: List[SlashCommand] = []

    last_rendered_lines_count = 0

    import termios
    import tty

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    def get_dock_data():
        cwd = getattr(agent, "workspace_dir", ".") if agent else "."
        model = getattr(agent.client, "model", "default") if agent and hasattr(agent, "client") else "default"
        stats = agent.context.get_context_stats() if agent and hasattr(agent, "context") else {}
        effort = getattr(agent.client, "reasoning_effort", "high") if agent and hasattr(agent, "client") else "auto"
        return cwd, model, stats, effort or "auto"

    try:
        tty.setcbreak(fd)

        while True:
            total_w = get_terminal_width()
            cwd, model, stats, effort = get_dock_data()

            # 检查是否激活斜杠命令自动补全浮层
            is_slash_prefix = buffer.startswith("/") and (" " not in buffer)
            if is_slash_prefix:
                matches = filter_slash_commands(buffer)
                if matches:
                    autocomplete_active = True
                    autocomplete_selected = max(0, min(autocomplete_selected, len(matches) - 1))
                else:
                    autocomplete_active = False
            else:
                autocomplete_active = False
                matches = []

            # 构建本帧所有可见文本行
            top_border = render_input_top_border(total_w)

            # 单行输入槽防溢出视口保护：确保 input_line 严格保持为单行，绝不触发终端折行
            max_input_disp_w = max(10, total_w - 6)
            buf_vis_w = visible_width(buffer)
            if buf_vis_w <= max_input_disp_w:
                disp_buffer = buffer
                cursor_disp_col = visible_width(buffer[:cursor_pos])
            else:
                # 动态横向视口滑动：让光标保持在右侧可视区
                cur_full_w = visible_width(buffer[:cursor_pos])
                left_col = max(0, cur_full_w - max_input_disp_w + 3)
                chars_in_view = []
                acc_w = 0
                for ch in buffer:
                    ch_w = 2 if unicodedata.east_asian_width(ch) in ("F", "W") else 1
                    if acc_w + ch_w > left_col and acc_w < left_col + max_input_disp_w:
                        chars_in_view.append(ch)
                    acc_w += ch_w
                disp_buffer = "".join(chars_in_view)
                cursor_disp_col = max(0, min(cur_full_w - left_col, max_input_disp_w))

            input_line = f"  {disp_buffer}"

            # 底部栏信息 (3 行: divider, footer1, footer2)
            bottom_dock = render_input_bottom_dock(
                cwd=cwd,
                model_name=model,
                context_stats=stats,
                reasoning_effort=effort,
                width=total_w,
            )
            dock_lines = bottom_dock.splitlines()

            frame_lines: List[str] = [top_border, input_line]

            if autocomplete_active and matches:
                dropdown_lines = render_autocomplete_dropdown(
                    matches=matches,
                    selected_idx=autocomplete_selected,
                    width=total_w,
                    max_visible=5,
                )
                frame_lines.extend(dropdown_lines)
                # 附加上下文操作提示
                if len(dock_lines) >= 2:
                    # 动态替换右侧 hints 提示为补全操作提示
                    hint_str = "Tab/Enter 采纳 | ↑/↓ 选择 | Esc 取消"
                    line1 = dock_lines[0]
                    # 保留原 divider 与 footer
                    frame_lines.extend(dock_lines)
                else:
                    frame_lines.extend(dock_lines)
            else:
                frame_lines.extend(dock_lines)

            # 同步原子刷新当前输入框区域
            out_buf = []
            out_buf.append("\033[?2026h")  # 开启终端同步输出锁

            if last_rendered_lines_count > 0:
                # 关键修复：上一帧结束时光标停留在 input_line (即帧内索引 1 的行)
                # 从 input_line 回到帧顶部 (索引 0 的 top_border) 恰好只需上移 1 行
                # 使用 "\r\033[1A\033[J" 零漂移抹除整帧重新输出，彻底杜绝向上累计窜行
                out_buf.append("\r\033[1A\033[J")

            out_buf.append("\n".join(frame_lines))

            # 精准定位硬件光标到输入行的具体键入位置
            # frame_lines[1] 是 input_line
            # 计算从末行回到 input_line 需要上移的行数
            lines_to_input = len(frame_lines) - 2
            col_offset = 2 + cursor_disp_col

            if lines_to_input > 0:
                out_buf.append(f"\033[{lines_to_input}A\r")
            else:
                out_buf.append("\r")

            if col_offset > 0:
                out_buf.append(f"\033[{col_offset}C")

            out_buf.append("\033[?2026l")  # 结束终端同步输出锁
            sys.stdout.write("".join(out_buf))
            sys.stdout.flush()

            last_rendered_lines_count = len(frame_lines)

            # 读取单个按键或转义序列
            raw = os.read(fd, 32)
            if not raw:
                continue

            # 1. 回车键 (Enter)
            if raw in (b"\r", b"\n"):
                if autocomplete_active and matches:
                    # 采纳当前选中的指令并补上一个空格，退出补全浮层
                    chosen = matches[autocomplete_selected].name
                    buffer = chosen + " "
                    cursor_pos = len(buffer)
                    autocomplete_active = False
                    continue
                else:
                    # 提交当前输入
                    break

            # 2. Ctrl+C
            elif raw == b"\x03":
                raise KeyboardInterrupt()

            # 3. Ctrl+D
            elif raw == b"\x04":
                if not buffer:
                    raise EOFError()
                else:
                    # 删除光标所在字符
                    if cursor_pos < len(buffer):
                        buffer = buffer[:cursor_pos] + buffer[cursor_pos + 1:]
                    continue

            # 4. 退格键 (Backspace)
            elif raw in (b"\x7f", b"\x08"):
                if cursor_pos > 0:
                    buffer = buffer[:cursor_pos - 1] + buffer[cursor_pos:]
                    cursor_pos -= 1
                continue

            # 5. Tab 补全键
            elif raw == b"\t":
                if autocomplete_active and matches:
                    chosen = matches[autocomplete_selected].name
                    buffer = chosen + " "
                    cursor_pos = len(buffer)
                    autocomplete_active = False
                elif not buffer.startswith("/"):
                    # 尝试前缀补全首个斜杠
                    matches = filter_slash_commands("/")
                    if matches:
                        autocomplete_active = True
                        autocomplete_selected = 0
                continue

            # 6. Esc 键
            elif raw == b"\x1b":
                if autocomplete_active:
                    autocomplete_active = False
                continue

            # 7. ANSI 方向键与导航键处理
            elif raw in (b"\x1b[A", b"\x1bOA"):  # 上方向键 (Up)
                if autocomplete_active and matches:
                    autocomplete_selected = (autocomplete_selected - 1) % len(matches)
                else:
                    # 翻阅历史
                    if history:
                        if history_idx == len(history):
                            saved_draft = buffer
                        if history_idx > 0:
                            history_idx -= 1
                            buffer = history[history_idx]
                            cursor_pos = len(buffer)
                continue

            elif raw in (b"\x1b[B", b"\x1bOB"):  # 下方向键 (Down)
                if autocomplete_active and matches:
                    autocomplete_selected = (autocomplete_selected + 1) % len(matches)
                else:
                    # 翻阅历史
                    if history:
                        if history_idx < len(history) - 1:
                            history_idx += 1
                            buffer = history[history_idx]
                            cursor_pos = len(buffer)
                        elif history_idx == len(history) - 1:
                            history_idx = len(history)
                            buffer = saved_draft
                            cursor_pos = len(buffer)
                continue

            elif raw in (b"\x1b[C", b"\x1bOC"):  # 右方向键 (Right)
                if cursor_pos < len(buffer):
                    cursor_pos += 1
                continue

            elif raw in (b"\x1b[D", b"\x1bOD"):  # 左方向键 (Left)
                if cursor_pos > 0:
                    cursor_pos -= 1
                continue

            elif raw in (b"\x1b[H", b"\x1b[1~"):  # Home 键
                cursor_pos = 0
                continue

            elif raw in (b"\x1b[F", b"\x1b[4~"):  # End 键
                cursor_pos = len(buffer)
                continue

            elif raw == b"\x1b[3~":  # Delete 键
                if cursor_pos < len(buffer):
                    buffer = buffer[:cursor_pos] + buffer[cursor_pos + 1:]
                continue

            # 8. 普通可打印字符 (含中文与 UTF-8 多字节字符)
            else:
                try:
                    text = raw.decode("utf-8")
                    # 过滤掉无法识别的 ANSI 转义残留
                    if not text.startswith("\x1b"):
                        buffer = buffer[:cursor_pos] + text + buffer[cursor_pos:]
                        cursor_pos += len(text)
                except UnicodeDecodeError:
                    pass
                continue

    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        # 退出前抹掉当前整个输入帧，由上层统一接管后续输出
        if last_rendered_lines_count > 0:
            sys.stdout.write("\r\033[1A\033[J")
            sys.stdout.flush()

    cleaned = buffer.strip()
    if cleaned:
        _append_history(cleaned, history_file)
    return cleaned
