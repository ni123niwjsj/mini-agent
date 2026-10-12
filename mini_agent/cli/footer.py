"""双行高密度常驻状态底栏与输入槽框组件 (对齐 Pi Editor Box 规范)。

展示：
1. 顶部分割线：微光暗紫 (divider: #5a5271)
2. 输入槽区：纯净光标 (无任何 > 符号，上下双线包裹)
3. 底部分割线：微光暗紫 (divider: #5a5271)
4. 行 1：当前工作区路径 (带 ~ 波浪号智能缩写) + Git 分支 + 交互提示
5. 行 2：Token 流式遥测指标 (↑输入 ↓输出 R缓存 CH命中率 估算费用 上下文水位) + 激活模型与思考强度角标
"""

import os
from typing import Any, Dict, Optional
from mini_agent.cli.display import format_tokens, get_git_branch
from mini_agent.cli.theme import (
    ACCENT_BLUE,
    ACCENT_GREEN,
    ACCENT_YELLOW,
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


def format_cwd_for_footer(cwd: str) -> str:
    """智能缩写工作区路径，将用户 Home 目录优雅替换为 ~"""
    home = os.path.expanduser("~")
    abs_cwd = os.path.abspath(cwd)
    if abs_cwd == home:
        return "~"
    if abs_cwd.startswith(home + os.sep):
        return "~" + abs_cwd[len(home):]
    return abs_cwd


def calculate_cost(prompt_tokens: int, completion_tokens: int, cached_tokens: int) -> float:
    """按通用 DeepSeek/主流大模型定价估算调用成本 (美元 USD)
    DeepSeek V3/V4 参考价格:
    - 输入未命中缓存: $0.14 / 1M tokens ($0.00014 / 1k)
    - 缓存命中输入: $0.014 / 1M tokens ($0.000014 / 1k)
    - 输出补全: $0.28 / 1M tokens ($0.00028 / 1k)
    """
    uncached = max(0, prompt_tokens - cached_tokens)
    cost = (uncached * 0.14 + cached_tokens * 0.014 + completion_tokens * 0.28) / 1_000_000.0
    return max(0.0, cost)


def render_input_top_border(width: Optional[int] = None) -> str:
    """生成输入框顶部的优雅微光紫线 (对齐 Pi 输入槽顶线)"""
    total_w = width or get_terminal_width()
    return f"{ansi_fg(DIVIDER_PURPLE)}{'─' * total_w}{ansi_reset()}"


def render_working_top_border(
    status_text: str = "正在思考任务...",
    spinner: str = "⠋",
    width: Optional[int] = None,
) -> str:
    """生成运行态输入槽顶部的加载指示边框 (对齐 Pi WorkingStatusIndicator 规范)
    
    格式: ── ⠋ 正在分析任务并规划步骤... ────────────────────────────────
    """
    total_w = width or get_terminal_width()
    reset = ansi_reset()

    prefix = f"── {spinner} {status_text} "
    vis_w = visible_width(prefix)

    if vis_w + 2 <= total_w:
        remaining = total_w - vis_w
        return (
            f"{ansi_fg(DIVIDER_PURPLE)}── {reset}"
            f"{ansi_fg(ACCENT_BLUE)}{ansi_bold()}{spinner}{reset} "
            f"{ansi_fg(FG_DOCK_BRIGHT)}{status_text} "
            f"{ansi_fg(DIVIDER_PURPLE)}{'─' * remaining}{reset}"
        )
    else:
        avail = max(4, total_w - 8)
        trunc_status = status_text[:avail] + "..." if len(status_text) > avail else status_text
        return (
            f"{ansi_fg(DIVIDER_PURPLE)}── {reset}"
            f"{ansi_fg(ACCENT_BLUE)}{spinner}{reset} "
            f"{ansi_fg(FG_DOCK_BRIGHT)}{trunc_status}{reset} "
            f"{ansi_fg(DIVIDER_PURPLE)}──{reset}"
        )


def render_working_bottom_dock(
    cwd: str,
    model_name: str,
    context_stats: Dict[str, Any],
    reasoning_effort: Optional[str] = "high",
    status_text: str = "正在思考任务...",
    spinner: str = "⠋",
    width: Optional[int] = None,
) -> str:
    """生成完整的运行态底栏 (顶部嵌入 spinner + 开放式输入槽 + 底部边框 + 双行遥测信息)"""
    top_border = render_working_top_border(status_text=status_text, spinner=spinner, width=width)
    bottom_dock = render_input_bottom_dock(
        cwd=cwd,
        model_name=model_name,
        context_stats=context_stats,
        reasoning_effort=reasoning_effort,
        width=width,
    )
    return f"{top_border}\n{bottom_dock}"


def render_input_bottom_dock(
    cwd: str,
    model_name: str,
    context_stats: Dict[str, Any],
    reasoning_effort: Optional[str] = "high",
    width: Optional[int] = None,
) -> str:
    """生成输入框下方的底线与双行遥测信息面板 (对齐 Pi 输入槽底线与 Footer)"""
    total_w = width or get_terminal_width()
    reset = ansi_reset()

    # 1. 底部分割线
    divider_line = f"{ansi_fg(DIVIDER_PURPLE)}{'─' * total_w}{reset}"

    # 2. 第一行：CWD + Git 分支 (左) 与 键盘操作提示 (右)
    short_cwd = format_cwd_for_footer(cwd)
    branch = get_git_branch(cwd)
    branch_str = f" ({branch})" if branch else ""

    left_line1_vis = f"{short_cwd}{branch_str}"
    left_line1 = (
        f"{ansi_fg(FG_DOCK_BRIGHT)}{short_cwd}"
        f"{ansi_fg(ACCENT_GREEN)}{branch_str}{reset}"
    )

    right_line1_vis = "Tab 补全 | ↑/↓ 历史"
    right_line1 = f"{ansi_fg(FG_DOCK_MUTED)}{right_line1_vis}{reset}"

    min_gap_1 = 2
    if visible_width(left_line1_vis) + min_gap_1 + visible_width(right_line1_vis) <= total_w:
        gap_1 = total_w - visible_width(left_line1_vis) - visible_width(right_line1_vis)
        line_1 = f"{left_line1}{' ' * gap_1}{right_line1}"
    else:
        # 宽度受限时优先展示工作区路径，隐藏右侧快捷提示
        if visible_width(left_line1_vis) <= total_w:
            line_1 = left_line1
        else:
            # 路径超长时进行省略号截断 (对齐 Pi 的 truncateToWidth)
            avail = total_w - visible_width(branch_str) - 3
            if avail > 0:
                trunc_cwd = "..." + short_cwd[-avail:]
            else:
                trunc_cwd = "..."
            line_1 = f"{ansi_fg(FG_DOCK_BRIGHT)}{trunc_cwd}{ansi_fg(ACCENT_GREEN)}{branch_str}{reset}"

    # 3. 第二行：Token / 缓存遥测指标 (左) 与 模型角标 (右)
    prompt_tokens = context_stats.get("cumulative_prompt_tokens", 0) or context_stats.get("current_tokens", 0)
    completion_tokens = context_stats.get("cumulative_completion_tokens", 0)
    cached_tokens = context_stats.get("cumulative_cached_tokens", 0) or context_stats.get("latest_cached_tokens", 0)
    cache_rate = context_stats.get("latest_cache_hit_rate", 0.0) or context_stats.get("cumulative_cache_hit_rate", 0.0)
    current_tokens = context_stats.get("current_tokens", 0)
    context_win = context_stats.get("context_window", 128000)

    in_str = format_tokens(prompt_tokens)
    out_str = format_tokens(completion_tokens)
    cached_str = format_tokens(cached_tokens)
    win_str = format_tokens(context_win)
    pct_str = f"{(current_tokens / context_win * 100):.1f}%" if context_win > 0 else "0.0%"
    cost_val = calculate_cost(prompt_tokens, completion_tokens, cached_tokens)
    effort_str = reasoning_effort if isinstance(reasoning_effort, str) else "auto"

    # 构建左侧遥测指标：单空格紧凑分隔，移除左侧冗余的 (effort_str) (对齐 Pi 规范)
    left_line2_vis = (
        f"↑{in_str} ↓{out_str} R{cached_str} CH{cache_rate}% ${cost_val:.3f} {pct_str}/{win_str}"
    )
    left_line2 = (
        f"{ansi_fg(FG_DOCK_MUTED)}↑{in_str} ↓{out_str} R{cached_str} "
        f"{ansi_fg(ACCENT_GREEN)}CH{cache_rate}%{reset} "
        f"{ansi_fg(ACCENT_YELLOW)}${cost_val:.3f}{reset} "
        f"{ansi_fg(ACCENT_BLUE)}{pct_str}/{win_str}{reset}"
    )

    # 右侧展示模型名称与思考强度 (对齐 Pi: model • effort)
    right_line2_vis = f"{model_name} • {effort_str}"
    right_line2 = (
        f"{ansi_fg(FG_DOCK_BRIGHT)}{model_name}{reset} "
        f"{ansi_fg(FG_DOCK_MUTED)}• {effort_str}{reset}"
    )

    stats_left_w = visible_width(left_line2_vis)
    right_w = visible_width(right_line2_vis)
    min_padding = 2

    if stats_left_w + min_padding + right_w <= total_w:
        gap_2 = total_w - stats_left_w - right_w
        line_2 = f"{left_line2}{' ' * gap_2}{right_line2}"
    else:
        # 当总宽度不足以完整容纳左右两侧时，严格按 Pi 规则动态截断，绝不跨行折行！
        avail_right = total_w - stats_left_w - min_padding
        if avail_right >= 8:
            trunc_right_vis = right_line2_vis[:avail_right - 3] + "..." if len(right_line2_vis) > avail_right else right_line2_vis[:avail_right]
            gap_2 = max(1, total_w - stats_left_w - visible_width(trunc_right_vis))
            trunc_right = f"{ansi_fg(FG_DOCK_MUTED)}{trunc_right_vis}{reset}"
            line_2 = f"{left_line2}{' ' * gap_2}{trunc_right}"
        else:
            # 空间极端狭窄时仅保留左侧遥测指标，并确保不超出终端列数
            if stats_left_w <= total_w:
                line_2 = left_line2
            else:
                line_2 = left_line2[:total_w]

    return f"{divider_line}\n{line_1}\n{line_2}"


def render_footer_lines(
    cwd: str,
    model_name: str,
    context_stats: Dict[str, Any],
    reasoning_effort: Optional[str] = "high",
    width: Optional[int] = None,
) -> str:
    """完整渲染常驻底栏 (向前兼容保留方法)"""
    return render_input_bottom_dock(cwd, model_name, context_stats, reasoning_effort, width)
