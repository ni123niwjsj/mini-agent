"""终端全屏备用屏幕 (Alternate Screen) 控制器。

利用 ANSI 标准转义序列：
- `\033[?1049h`: 激活终端备用屏幕缓冲区 (进入全屏锁屏模式，如 vim / htop / pi)
- `\033[?1049l`: 退出备用屏幕并无缝还原宿主终端历史内容，零残留无污染
- `\033[2J\033[H`: 清空当前视口光标复位
"""

import atexit
import sys
from contextlib import contextmanager
from typing import Iterator

_IN_ALT_SCREEN = False


def enter_alt_screen() -> None:
    """进入终端备用屏幕 (Alt-Screen)"""
    global _IN_ALT_SCREEN
    if not _IN_ALT_SCREEN and sys.stdout.isatty():
        sys.stdout.write("\033[?1049h\033[H")
        sys.stdout.flush()
        _IN_ALT_SCREEN = True


def leave_alt_screen() -> None:
    """退出终端备用屏幕并恢复原始终端"""
    global _IN_ALT_SCREEN
    if _IN_ALT_SCREEN and sys.stdout.isatty():
        sys.stdout.write("\033[?1049l")
        sys.stdout.flush()
        _IN_ALT_SCREEN = False


def clear_viewport() -> None:
    """清屏并复位光标至左上角 (0, 0)"""
    if sys.stdout.isatty():
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()


def is_alt_screen_active() -> bool:
    """检测当前是否处于全屏备用屏幕模式"""
    return _IN_ALT_SCREEN


# 注册退出钩子，防御进程异常退出导致终端残留
atexit.register(leave_alt_screen)


@contextmanager
def alt_screen_context() -> Iterator[None]:
    """Alt-Screen 自动上下文管理器"""
    enter_alt_screen()
    try:
        yield
    finally:
        leave_alt_screen()
