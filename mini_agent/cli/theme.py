"""终端主题与色彩规范定义 (对齐 Pi / Earendil 工业级标准)。

包含：
1. 核心色彩令牌 (RGB & Hex)：userMessageBg, toolSuccessBg, thinkingText, divider 等。
2. 24-bit TrueColor ANSI 转义生成器。
3. CJK 双字节对齐与可见宽度计算 (解决中文字符排版错位问题)。
4. 满宽色块容器渲染引擎 (对齐 Pi 的 Box 满宽背景铺设算法)。
"""

import os
import re
import shutil
import unicodedata
from typing import List, Optional, Tuple, Union

# ============================================================================
# 色彩令牌常量 (严格采样自 Pi Dark Theme)
# ============================================================================

# 终端与背景
BG_TERM: Tuple[int, int, int] = (12, 12, 12)             # #0c0c0c
BG_USER: Tuple[int, int, int] = (33, 59, 73)             # #213b49 (userMessageBg: 深邃石油蓝)
FG_USER: Tuple[int, int, int] = (219, 228, 235)          # #dbe4eb (userMessageText: 柔和浅灰白)

# 工具面板
BG_TOOL_SUCCESS: Tuple[int, int, int] = (37, 65, 49)     # #254131 (toolSuccessBg: 沉浸墨绿)
FG_TOOL_SUCCESS: Tuple[int, int, int] = (133, 232, 157)   # #85e89d
BG_TOOL_PENDING: Tuple[int, int, int] = (33, 40, 54)     # #212836 (toolPendingBg: 暗黛青)
BG_TOOL_ERROR: Tuple[int, int, int] = (61, 33, 33)       # #3d2121 (toolErrorBg: 暗绯红)
FG_TOOL_ERROR: Tuple[int, int, int] = (248, 81, 73)      # #f85149

# 思考链与回答
FG_THINKING: Tuple[int, int, int] = (123, 136, 145)      # #7b8891 (thinkingText: 柔和灰)
FG_ASSISTANT: Tuple[int, int, int] = (216, 222, 228)     # #d8dee4 (assistantText: 自然正文白)

# 底栏与分割线
DIVIDER_PURPLE: Tuple[int, int, int] = (90, 82, 113)     # #5a5271 (dockDivider: 优雅暗紫)
FG_DOCK_MUTED: Tuple[int, int, int] = (139, 148, 158)    # #8b949e
FG_DOCK_BRIGHT: Tuple[int, int, int] = (201, 209, 217)   # #c9d1d9
ACCENT_BLUE: Tuple[int, int, int] = (88, 166, 255)       # #58a6ff
ACCENT_GREEN: Tuple[int, int, int] = (126, 231, 135)     # #7ee787
ACCENT_YELLOW: Tuple[int, int, int] = (229, 192, 123)    # #e5c07b
FG_DIFF_ADD: Tuple[int, int, int] = (126, 231, 135)      # #7ee787
BG_DIFF_ADD: Tuple[int, int, int] = (46, 85, 60)         # #2e553c


# ============================================================================
# ANSI 转义序列辅助函数
# ============================================================================

def ansi_bg(rgb: Tuple[int, int, int]) -> str:
    """生成 24-bit TrueColor 背景色转义序列"""
    return f"\033[48;2;{rgb[0]};{rgb[1]};{rgb[2]}m"


def ansi_fg(rgb: Tuple[int, int, int]) -> str:
    """生成 24-bit TrueColor 前景色转义序列"""
    return f"\033[38;2;{rgb[0]};{rgb[1]};{rgb[2]}m"


def ansi_reset() -> str:
    """清除全部样式格式"""
    return "\033[0m"


def ansi_italic() -> str:
    """开启斜体"""
    return "\033[3m"


def ansi_dim() -> str:
    """开启淡色/暗色"""
    return "\033[2m"


def ansi_bold() -> str:
    """开启加粗"""
    return "\033[1m"


# ============================================================================
# 字符宽度与对齐引擎
# ============================================================================

_ANSI_STRIP_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


def strip_ansi(text: str) -> str:
    """过滤字符串中的全部 ANSI 颜色与控制序列"""
    return _ANSI_STRIP_RE.sub("", text)


def visible_width(text: str) -> int:
    """精确计算文本在终端中占用的物理列数 (自动识别中日韩全宽字符)"""
    clean_text = strip_ansi(text)
    width = 0
    for char in clean_text:
        # F (Fullwidth) 与 W (Wide) 字符在终端占两列
        if unicodedata.east_asian_width(char) in ("F", "W"):
            width += 2
        else:
            width += 1
    return width


def truncate_to_width(text: str, max_width: int, ellipsis: str = "…") -> str:
    """按终端可见物理列宽安全截断字符串 (精确处理中英文全宽/半宽字符与 ANSI 转义序列)。
    
    Args:
        text: 待截断的原始文本 (可包含 ANSI 颜色代码)
        max_width: 目标最大可视物理列宽
        ellipsis: 截断省略符 (默认为单字符省略号 "…", 占用 1 或 2 列)
    """
    if max_width <= 0:
        return ""
    if visible_width(text) <= max_width:
        return text

    ellipsis_w = visible_width(ellipsis)
    target_w = max(0, max_width - ellipsis_w)

    result: List[str] = []
    curr_w = 0
    idx = 0
    str_len = len(text)

    while idx < str_len:
        # 1. 匹配 ANSI 控制序列：保留其原有样式，不计入可视物理列宽
        match = _ANSI_STRIP_RE.match(text, idx)
        if match:
            result.append(match.group(0))
            idx = match.end()
            continue

        # 2. 普通字符：计算东亚文字物理列宽 (全宽为 2，半宽为 1)
        char = text[idx]
        ch_w = 2 if unicodedata.east_asian_width(char) in ("F", "W") else 1
        if curr_w + ch_w > target_w:
            break
        result.append(char)
        curr_w += ch_w
        idx += 1

    result.append(ellipsis)
    result.append(ansi_reset())
    return "".join(result)


def get_terminal_width(fallback: int = 100) -> int:
    """获取当前终端物理真实列宽 (多源自适应探测：ioctl > 环境变量 > shutil > fallback)"""
    # 1. 尝试使用 ioctl 获取真实 TTY 设备大小
    try:
        import fcntl
        import struct
        import termios
        for fd in (1, 0, 2):
            try:
                res = fcntl.ioctl(fd, termios.TIOCGWINSZ, b"\x00" * 8)
                lines, cols = struct.unpack("HHHH", res)[:2]
                if cols > 0:
                    return max(40, cols)
            except Exception:
                pass
    except Exception:
        pass

    # 2. 尝试读取 COLUMNS 环境变量
    try:
        if "COLUMNS" in os.environ:
            c = int(os.environ["COLUMNS"])
            if c > 0:
                return max(40, c)
    except Exception:
        pass

    # 3. 尝试使用 shutil.get_terminal_size
    try:
        cols = shutil.get_terminal_size(fallback=(fallback, 24)).columns
        return max(40, cols)
    except Exception:
        return fallback


# ============================================================================
# 满宽色块容器渲染引擎 (Box Rendering)
# ============================================================================

def render_full_width_line(
    content: str,
    bg_rgb: Tuple[int, int, int],
    fg_rgb: Optional[Tuple[int, int, int]] = None,
    width: Optional[int] = None,
    left_padding: int = 2,
    border_accent_rgb: Optional[Tuple[int, int, int]] = None,
) -> str:
    """渲染一行固定宽度的满宽背景色条。
    
    Args:
        content: 文本内容
        bg_rgb: 背景 RGB 颜色
        fg_rgb: 前景文本 RGB 颜色
        width: 目标总宽度 (为 None 时自动获取终端列宽)
        left_padding: 左侧留白空格数
        border_accent_rgb: 可选的左侧 1 字符高亮细边线色
    """
    total_w = width or get_terminal_width()
    prefix = ""
    prefix_w = 0

    if border_accent_rgb:
        # 左侧 1 字符高亮重音边条
        prefix = f"{ansi_bg(border_accent_rgb)} {ansi_reset()}"
        prefix_w = 1

    bg_seq = ansi_bg(bg_rgb)
    fg_seq = ansi_fg(fg_rgb) if fg_rgb else ""
    reset_seq = ansi_reset()

    # 最大可用内容物理宽度：严格防止单行溢出导致终端硬件折行撕裂卡片
    max_content_w = max(0, total_w - prefix_w - left_padding)
    content_vis_w = visible_width(content)
    if content_vis_w > max_content_w:
        content = truncate_to_width(content, max_content_w, "…")
        content_vis_w = visible_width(content)

    # 核心保护：content 内部可能包含语法高亮结束的 ansi_reset()
    # 为防止重置后跌落为终端默认黑底，自动将内部 reset 替换为 reset + 当前背景色
    safe_content = content.replace(ansi_reset(), f"{ansi_reset()}{bg_seq}")

    # 计算需要右侧填充的空格数，使整行刚好撑满整个屏幕宽度
    needed_spaces = max(0, total_w - prefix_w - left_padding - content_vis_w)

    left_pad_str = " " * left_padding
    right_pad_str = " " * needed_spaces

    return f"{prefix}{bg_seq}{left_pad_str}{fg_seq}{safe_content}{bg_seq}{right_pad_str}{reset_seq}"



def render_full_width_box(
    lines: Union[str, List[str]],
    bg_rgb: Tuple[int, int, int],
    fg_rgb: Optional[Tuple[int, int, int]] = None,
    width: Optional[int] = None,
    padding_y: int = 1,
    padding_x: int = 2,
    border_accent_rgb: Optional[Tuple[int, int, int]] = None,
) -> str:
    """渲染类似 Pi 风格的满宽背景色块卡片 (支持多行文本与垂直内边距)。"""
    if isinstance(lines, str):
        content_lines = lines.splitlines() or [""]
    else:
        content_lines = lines or [""]

    total_w = width or get_terminal_width()
    rendered: List[str] = []

    # 顶部背景内边距
    for _ in range(padding_y):
        rendered.append(render_full_width_line("", bg_rgb, None, total_w, padding_x, border_accent_rgb))

    # 内容主体行
    for line in content_lines:
        rendered.append(render_full_width_line(line, bg_rgb, fg_rgb, total_w, padding_x, border_accent_rgb))

    # 底部背景内边距
    for _ in range(padding_y):
        rendered.append(render_full_width_line("", bg_rgb, None, total_w, padding_x, border_accent_rgb))

    return "\n".join(rendered)
