"""终端交互式下拉选择菜单组件 (TerminalSelectMenu)。

零外部依赖，使用标准库 termios / tty (跨平台兼容 Windows msvcrt / 非 TTY 环境)。
支持：
1. 键盘方向键 (↑ / ↓ / j / k) 上下高亮选择。
2. 翻页支持 (PageUp / PageDown / n / p)，优雅展示大量选项 (如 85+ 个模型)。
3. 数字键 (1~8) 快速单键直达。
4. 回车 (Enter) 确认，q / Esc / Ctrl+C 取消。
5. 非 TTY 环境 (管道输入、自动化脚本) 优雅降级为静态编号选择或默认值。
"""

import os
import sys
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple, Union


@dataclass
class MenuItem:
    """菜单选项定义"""
    id: str  # 唯一键/选中时返回的值
    label: str  # 主要显示文本 (如模型名或会话ID)
    description: str = ""  # 辅助说明文本 (如上下文窗口、时间、首句等)
    is_current: bool = False  # 是否为当前激活项


def _parse_escape_sequence(data: bytes) -> str:
    """解析终端按键序列为统一的语义动作名称"""
    if not data:
        return ""

    # 方向键 (支持 ANSI 转义序列 \x1b[ 与 SS3 模式 \x1bO)
    if data in (b"\x1b[A", b"\x1bOA"):
        return "up"
    elif data in (b"\x1b[B", b"\x1bOB"):
        return "down"
    elif data in (b"\x1b[C", b"\x1bOC"):
        return "right"
    elif data in (b"\x1b[D", b"\x1bOD"):
        return "left"
    elif data in (b"\x1b[5~", b"\x1b[[5~"):
        return "page_up"
    elif data in (b"\x1b[6~", b"\x1b[[6~"):
        return "page_down"
    elif data in (b"\x1b[H", b"\x1b[1~"):
        return "home"
    elif data in (b"\x1b[F", b"\x1b[4~"):
        return "end"
    elif data in (b"\r", b"\n"):
        return "enter"
    elif data == b"\x03":
        return "ctrl_c"
    elif data in (b"\x1b", b"\x1b\x1b"):
        return "esc"

    try:
        s = data.decode("utf-8")
        if s.lower() == "k":
            return "up"
        elif s.lower() == "j":
            return "down"
        elif s.lower() == "p":
            return "page_up"
        elif s.lower() == "n":
            return "page_down"
        elif s.lower() == "q":
            return "esc"
        elif s.isdigit():
            return s
        return s
    except Exception:
        return ""


def _read_raw_key_linux(fd: int) -> str:
    """在 cbreak 模式下通过底层文件描述符读取未缓冲的按键序列"""
    import os
    import select

    # 尝试一次性读取最多 32 个字节 (方向键通常 3~4 字节由终端一次性写入)
    try:
        data = os.read(fd, 32)
    except Exception:
        return ""

    if not data:
        return ""

    # 如果仅读到了前导 \x1b，可能后续字节网络传输延迟，非阻塞等 50ms 拼接
    if data == b"\x1b":
        rlist, _, _ = select.select([fd], [], [], 0.05)
        if rlist:
            try:
                data += os.read(fd, 31)
            except Exception:
                pass

    return _parse_escape_sequence(data)


def _get_key_linux() -> str:
    """在 Linux / macOS 下单次读取单个按键或转义序列"""
    import termios
    import tty

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        return _read_raw_key_linux(fd)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def _get_key_windows() -> str:
    """在 Windows 下读取单个按键"""
    import msvcrt

    ch = msvcrt.getch()
    if ch in (b"\x00", b"\xe0"):  # 方向键前缀
        ch2 = msvcrt.getch()
        if ch2 == b"H":
            return "up"
        elif ch2 == b"P":
            return "down"
        elif ch2 == b"K":
            return "left"
        elif ch2 == b"M":
            return "right"
        elif ch2 == b"I":
            return "page_up"
        elif ch2 == b"Q":
            return "page_down"
        return "esc"
    elif ch in (b"\r", b"\n"):
        return "enter"
    elif ch == b"\x1b":
        return "esc"
    elif ch == b"\x03":
        return "ctrl_c"
    try:
        return ch.decode("utf-8")
    except Exception:
        return ""


def get_key() -> str:
    """跨平台统一读取按键"""
    if os.name == "nt":
        return _get_key_windows()
    return _get_linux_or_fallback()


def _get_linux_or_fallback() -> str:
    try:
        return _get_key_linux()
    except Exception:
        # 非终端环境降级
        line = sys.stdin.readline()
        return line.strip()


def select_menu(
    items: List[Union[MenuItem, Tuple[str, str], str]],
    title: str = "请选择一个选项",
    current_id: Optional[str] = None,
    page_size: int = 8,
) -> Optional[MenuItem]:
    """弹出交互式光标选择菜单。

    Args:
        items: 选项列表，支持 MenuItem 对象、(id, label) 元组或纯字符串
        title: 菜单标题提示语
        current_id: 当前正在使用的 item id（用于在列表中标记为 [当前]）
        page_size: 每页展示数量 (默认 8 个，避免撑破终端)

    Returns:
        选中的 MenuItem 对象；如果按 Esc / q 取消则返回 None
    """
    if not items:
        return None

    # 标准化选项为 MenuItem 列表
    normalized_items: List[MenuItem] = []
    for it in items:
        if isinstance(it, MenuItem):
            normalized_items.append(it)
        elif isinstance(it, tuple) and len(it) >= 2:
            normalized_items.append(MenuItem(id=str(it[0]), label=str(it[1])))
        else:
            s = str(it)
            normalized_items.append(MenuItem(id=s, label=s))

    # 标记当前选中项
    if current_id:
        for it in normalized_items:
            if it.id == current_id:
                it.is_current = True

    # 找到默认高亮索引
    selected_index = 0
    if current_id:
        for idx, it in enumerate(normalized_items):
            if it.id == current_id:
                selected_index = idx
                break

    # 非 TTY 交互终端降级逻辑 (例如重定向管道或自动化测试)
    if not sys.stdin.isatty():
        print(f"\n{title}:")
        for i, it in enumerate(normalized_items, 1):
            curr_str = " (当前)" if it.is_current else ""
            desc_str = f" - {it.description}" if it.description else ""
            print(f"  [{i}] {it.label}{curr_str}{desc_str}")
        print(f"非交互环境，默认选用: {normalized_items[selected_index].label}\n")
        return normalized_items[selected_index]

    total_items = len(normalized_items)
    total_pages = (total_items + page_size - 1) // page_size

    # ANSI 转义码
    C_HIDE = "\033[?25l"
    C_SHOW = "\033[?25h"
    C_CYAN_BOLD = "\033[1;36m"
    C_GREEN = "\033[32m"
    C_YELLOW = "\033[33m"
    C_DIM = "\033[2m"
    C_RESET = "\033[0m"

    lines_rendered = 0
    fd = None
    old_settings = None

    try:
        sys.stdout.write(C_HIDE)
        sys.stdout.flush()

        if os.name != "nt":
            try:
                import termios
                import tty
                fd = sys.stdin.fileno()
                old_settings = termios.tcgetattr(fd)
                tty.setcbreak(fd)
            except Exception:
                fd = None
                old_settings = None

        while True:
            # 计算当前页范围
            current_page = selected_index // page_size
            start_idx = current_page * page_size
            end_idx = min(start_idx + page_size, total_items)
            page_items = normalized_items[start_idx:end_idx]

            # 清除上次渲染的内容 (回到顶部并清空)
            if lines_rendered > 0:
                sys.stdout.write(f"\033[{lines_rendered}A\r\033[J")
                sys.stdout.flush()

            # 构建当前帧内容
            out_lines: List[str] = []
            page_info = f" {C_DIM}[第 {current_page + 1}/{total_pages} 页, 共 {total_items} 项]{C_RESET}" if total_pages > 1 else ""
            out_lines.append(f"{C_CYAN_BOLD}🔍 {title}{C_RESET}{page_info}")

            for idx_in_page, it in enumerate(page_items):
                global_idx = start_idx + idx_in_page
                is_highlighted = (global_idx == selected_index)
                curr_mark = f" {C_GREEN}(当前激活){C_RESET}" if it.is_current else ""
                num_tag = f"[{idx_in_page + 1}]"

                desc_text = f" {C_DIM}│ {it.description}{C_RESET}" if it.description else ""

                if is_highlighted:
                    # 高亮选中项 (带光标 ❯ 和青色加粗反白)
                    cursor = f"{C_CYAN_BOLD}❯{C_RESET}"
                    label_str = f"\033[1;37m\033[44m {it.label} \033[0m"
                    out_lines.append(f"  {cursor} {num_tag} {label_str}{desc_text}{curr_mark}")
                else:
                    cursor = " "
                    out_lines.append(f"  {cursor} {num_tag} {it.label}{desc_text}{curr_mark}")

            hint_nav = "↑/↓ 移动"
            hint_page = " | n/p 翻页" if total_pages > 1 else ""
            hint_num = " | 1~8 数字键直达" if len(page_items) > 1 else ""
            hint_exit = " | Enter 确认 | q/Esc 取消"
            out_lines.append(f"{C_DIM}  ({hint_nav}{hint_page}{hint_num}{hint_exit}){C_RESET}")

            # 打印本帧
            sys.stdout.write("\n".join(out_lines) + "\n")
            sys.stdout.flush()
            lines_rendered = len(out_lines)

            # 读取按键事件 (Linux/macOS 直接读取底层 fd，避免 stdio 缓存丢失按键)
            if os.name == "nt":
                key = _get_key_windows()
            elif fd is not None:
                key = _read_raw_key_linux(fd)
            else:
                key = _get_linux_or_fallback()

            if key in ("up", "k"):
                selected_index = (selected_index - 1) % total_items
            elif key in ("down", "j"):
                selected_index = (selected_index + 1) % total_items
            elif key in ("page_up", "p", "left"):
                # 上一页
                new_page = max(0, current_page - 1)
                selected_index = new_page * page_size
            elif key in ("page_down", "n", "right"):
                # 下一页
                new_page = min(total_pages - 1, current_page + 1)
                selected_index = min(new_page * page_size, total_items - 1)
            elif key.isdigit() and 1 <= int(key) <= len(page_items):
                # 数字键快速选择当前页的对应项并直接确认
                chosen_idx = start_idx + int(key) - 1
                selected_index = chosen_idx
                break
            elif key == "enter":
                # 确认选中
                break
            elif key in ("esc", "q", "ctrl_c"):
                # 取消选择
                if lines_rendered > 0:
                    sys.stdout.write(f"\033[{lines_rendered}A\r\033[J")
                    sys.stdout.flush()
                return None

        # 选中完成：清理菜单并返回结果
        if lines_rendered > 0:
            sys.stdout.write(f"\033[{lines_rendered}A\r\033[J")
            sys.stdout.flush()

        return normalized_items[selected_index]

    finally:
        if fd is not None and old_settings is not None:
            try:
                import termios
                # 清理输入队列中残留未读字节 (如用户连按产生的冗余方向键或转义码)
                termios.tcflush(fd, termios.TCIFLUSH)
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            except Exception:
                pass
        sys.stdout.write(C_SHOW)
        sys.stdout.flush()
