"""CLI 交互层包入口。"""

from mini_agent.cli.display import TerminalDisplay
from mini_agent.cli.footer import render_footer_lines
from mini_agent.cli.menu import MenuItem, select_menu
from mini_agent.cli.repl import start_repl
from mini_agent.cli.screen import (
    alt_screen_context,
    clear_viewport,
    enter_alt_screen,
    is_alt_screen_active,
    leave_alt_screen,
)
from mini_agent.cli.theme import (
    BG_TOOL_ERROR,
    BG_TOOL_SUCCESS,
    BG_USER,
    FG_USER,
    render_full_width_box,
    render_full_width_line,
    visible_width,
)

__all__ = [
    "TerminalDisplay",
    "MenuItem",
    "select_menu",
    "start_repl",
    "render_footer_lines",
    "render_full_width_box",
    "render_full_width_line",
    "visible_width",
    "enter_alt_screen",
    "leave_alt_screen",
    "clear_viewport",
    "is_alt_screen_active",
    "alt_screen_context",
    "BG_USER",
    "FG_USER",
    "BG_TOOL_SUCCESS",
    "BG_TOOL_ERROR",
]
