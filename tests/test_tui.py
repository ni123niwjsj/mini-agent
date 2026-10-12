"""测试现代 TUI 视觉组件与 Alt-Screen 状态 (theme.py, footer.py, screen.py)。"""

import os
import unittest
from unittest.mock import patch

from mini_agent.cli.footer import calculate_cost, format_cwd_for_footer, render_footer_lines
from mini_agent.cli.screen import (
    alt_screen_context,
    enter_alt_screen,
    is_alt_screen_active,
    leave_alt_screen,
)
from mini_agent.cli.theme import (
    ACCENT_BLUE,
    BG_TOOL_SUCCESS,
    BG_USER,
    FG_USER,
    get_terminal_width,
    render_full_width_box,
    render_full_width_line,
    strip_ansi,
    visible_width,
)


class TestTuiComponents(unittest.TestCase):
    """测试 Pi-aligned 现代 TUI 核心组件"""

    def test_visible_width_and_ansi_strip(self):
        """测试字符可见宽度精确计算与中文字符双列对齐"""
        self.assertEqual(visible_width("hello"), 5)
        # 中文字符每个占 2 列
        self.assertEqual(visible_width("你好"), 4)
        self.assertEqual(visible_width("99乘法表"), 8)
        # ANSI 控制符应被忽略其可见宽度
        ansi_text = "\033[1;34mhello\033[0m"
        self.assertEqual(strip_ansi(ansi_text), "hello")
        self.assertEqual(visible_width(ansi_text), 5)

    def test_render_full_width_line(self):
        """测试满宽背景行渲染与空格自动填充"""
        width = 60
        line = render_full_width_line("测试文本", bg_rgb=BG_USER, fg_rgb=FG_USER, width=width, left_padding=2)
        # 校验去除 ANSI 后的纯文本宽度刚好等于目标终端宽度
        clean = strip_ansi(line)
        self.assertEqual(visible_width(clean), width)
        self.assertTrue(clean.startswith("  测试文本"))

    def test_render_full_width_box(self):
        """测试类似 Pi 的全宽背景色块卡片渲染"""
        width = 80
        box = render_full_width_box(
            ["第一行", "第二行内容"],
            bg_rgb=BG_TOOL_SUCCESS,
            width=width,
            padding_y=1,
            padding_x=2,
            border_accent_rgb=ACCENT_BLUE,
        )
        lines = box.splitlines()
        # 顶部 1 行留白 + 2 行内容 + 底部 1 行留白 = 共 4 行
        self.assertEqual(len(lines), 4)
        for l in lines:
            clean = strip_ansi(l)
            # 加上 border accent 刚好填满 80 列
            self.assertEqual(visible_width(clean), width)

    def test_footer_cwd_formatting(self):
        """测试工作区路径 ~ 缩写"""
        home = os.path.expanduser("~")
        self.assertEqual(format_cwd_for_footer(home), "~")
        test_path = os.path.join(home, "projects", "mini-agent")
        self.assertEqual(format_cwd_for_footer(test_path), f"~{os.sep}projects{os.sep}mini-agent")
        # 非 Home 路径保持原样
        self.assertEqual(format_cwd_for_footer("/tmp/workspace"), "/tmp/workspace")

    def test_footer_cost_calculation(self):
        """测试 API 调用成本估算"""
        # 1M tokens 全命中
        cost_cached = calculate_cost(prompt_tokens=1000000, completion_tokens=0, cached_tokens=1000000)
        self.assertAlmostEqual(cost_cached, 0.014, places=4)
        # 1M tokens 全未命中
        cost_uncached = calculate_cost(prompt_tokens=1000000, completion_tokens=0, cached_tokens=0)
        self.assertAlmostEqual(cost_uncached, 0.14, places=4)

    def test_footer_rendering_lines(self):
        """测试双行高密度常驻底栏渲染"""
        stats = {
            "current_tokens": 4096,
            "context_window": 128000,
            "cumulative_prompt_tokens": 5000,
            "cumulative_completion_tokens": 1200,
            "cumulative_cached_tokens": 25000,
            "latest_cache_hit_rate": 96.5,
        }
        footer = render_footer_lines(
            cwd=".",
            model_name="deepseek/deepseek-v4.1-flash",
            context_stats=stats,
            reasoning_effort="high",
            width=80,
        )
        lines = footer.splitlines()
        self.assertEqual(len(lines), 3)  # 分割线 + 行 1 + 行 2
        # 分割线
        self.assertIn("─", lines[0])
        # 行 1 包含工作区
        self.assertIn("Tab 补全", lines[1])
        # 行 2 包含指标与模型
        self.assertIn("CH96.5%", lines[2])
        self.assertIn("deepseek/deepseek-v4.1-flash", lines[2])

    def test_alt_screen_lifecycle(self):
        """测试 Alt-Screen 状态切换与上下文管理器安全退出"""
        with patch("sys.stdout.isatty", return_value=True), patch("sys.stdout.write"):
            self.assertFalse(is_alt_screen_active())
            enter_alt_screen()
            self.assertTrue(is_alt_screen_active())
            leave_alt_screen()
            self.assertFalse(is_alt_screen_active())

            # 测试 contextmanager
            with alt_screen_context():
                self.assertTrue(is_alt_screen_active())
            self.assertFalse(is_alt_screen_active())

    def test_render_input_top_border(self):
        """测试输入槽顶部边框线渲染"""
        from mini_agent.cli.footer import render_input_top_border
        border = render_input_top_border(width=80)
        clean = strip_ansi(border)
        self.assertEqual(len(clean), 80)
        self.assertIn("─", clean)

    def test_format_tool_result_box_edit_diff(self):
        """测试 edit_file 工具结果渲染支持真实代码行号与上下文展示"""
        from mini_agent.cli.display import TerminalDisplay
        display = TerminalDisplay()
        args = {
            "path": "test.py",
            "old_str": "x = 1",
            "new_str": "x = 42\ny = 100",
        }
        diff_output = (
            "Successfully edited 'test.py'. Diff:\n\n"
            "--- a/test.py\n"
            "+++ b/test.py\n"
            "@@ -10,3 +10,4 @@\n"
            " def foo():\n"
            "-x = 1\n"
            "+x = 42\n"
            "+y = 100\n"
            " return x\n"
        )
        box = display.format_tool_result_box("edit_file", args, diff_output, is_error=False)
        clean = strip_ansi(box)
        # 验证包含动作与路径
        self.assertIn("edit", clean)
        self.assertIn("test.py", clean)
        # 验证包含上下文行号与 Diff +/- 符号行号
        self.assertIn("10  def foo():", clean)
        self.assertIn("-  11  x = 1", clean)
        self.assertIn("+  11  x = 42", clean)
        self.assertIn("+  12  y = 100", clean)
        self.assertIn("13  return x", clean)

    def test_replay_history_execution(self):
        """测试回放会话历史记录 (涵盖用户提问、思维链、工具调用与结果、正文回答)"""
        import io
        from contextlib import redirect_stdout
        from mini_agent.cli.display import TerminalDisplay

        display = TerminalDisplay()
        messages = [
            {"role": "user", "content": "把背景改成暗黑渐变色"},
            {
                "role": "assistant",
                "reasoning": "用户希望更改背景为渐变，我需要使用 edit_file 工具修改 99乘法表.html",
                "tool_calls": [
                    {
                        "id": "call_123",
                        "function": {
                            "name": "edit_file",
                            "arguments": '{"path": "99乘法表.html", "new_str": "background: #1a1a2e;"}',
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call_123",
                "tool_name": "edit_file",
                "content": "Successfully edited '99乘法表.html'.",
            },
            {
                "role": "assistant",
                "content": "已为您成功将背景样式调整为暗黑质感。",
            },
        ]

        f = io.StringIO()
        with redirect_stdout(f):
            display.replay_history(messages)

        output = f.getvalue()
        self.assertIn("把背景改成暗黑渐变色", output)
        self.assertIn("用户希望更改背景为渐变", output)
        self.assertIn("99乘法表.html", output)
        self.assertIn("已为您成功将背景样式调整为暗黑质感。", output)

    def test_footer_strict_width_no_wrap(self):
        """测试在不同终端宽度下 (80列、60列)，底栏所有行可见宽度绝不超标，杜绝物理折行"""
        stats = {
            "current_tokens": 39000,
            "context_window": 1000000,
            "cumulative_prompt_tokens": 39000,
            "cumulative_completion_tokens": 2100,
            "cumulative_cached_tokens": 33000,
            "latest_cache_hit_rate": 94.4,
        }
        for test_w in [80, 70, 60]:
            dock = render_footer_lines(
                cwd="/home/shuaige/code/我的项目/mini-agent/workspace",
                model_name="deepseek/deepseek-v4.1-flash",
                context_stats=stats,
                reasoning_effort="high",
                width=test_w,
            )
            lines = dock.splitlines()
            self.assertEqual(len(lines), 3)  # divider + line1 + line2
            for idx, l in enumerate(lines):
                vis_w = visible_width(l)
                self.assertLessEqual(
                    vis_w,
                    test_w,
                    f"Line {idx} exceeded width {test_w}: visible width is {vis_w} (text: {strip_ansi(l)})",
                )

    def test_footer_long_cwd_truncation(self):
        """测试在超长目录路径下，line_1 自动截断且保持可见宽度 <= terminal_width"""
        stats = {"current_tokens": 0, "context_window": 128000}
        long_path = "/home/shuaige/very/deep/nested/subproject/directory/structure/that/is/super/long"
        dock = render_footer_lines(
            cwd=long_path,
            model_name="deepseek/deepseek-v4.1-flash",
            context_stats=stats,
            width=60,
        )
        lines = dock.splitlines()
        self.assertLessEqual(visible_width(lines[1]), 60)
        self.assertIn("...", strip_ansi(lines[1]))

    def test_render_working_bottom_dock(self):
        """测试运行态常驻固定底栏 (嵌入 spinner 加载状态与双行遥测)"""
        from mini_agent.cli.footer import render_working_bottom_dock, render_working_top_border
        stats = {
            "current_tokens": 12000,
            "context_window": 128000,
            "cumulative_prompt_tokens": 12000,
            "cumulative_completion_tokens": 800,
            "cumulative_cached_tokens": 8000,
            "latest_cache_hit_rate": 85.0,
        }
        # 1. 顶边线嵌入测试
        top_border = render_working_top_border("正在分析执行结果...", spinner="⠋", width=80)
        clean_top = strip_ansi(top_border)
        self.assertIn("⠋", clean_top)
        self.assertIn("正在分析执行结果...", clean_top)
        self.assertEqual(visible_width(clean_top), 80)

        # 2. 完整运行态常驻底栏测试 (共 4 行)
        dock = render_working_bottom_dock(
            cwd="/home/shuaige/code/workspace",
            model_name="deepseek/deepseek-v4.1-flash",
            context_stats=stats,
            reasoning_effort="high",
            status_text="正在执行: edit test.py ...",
            width=80,
        )
        lines = dock.splitlines()
        self.assertEqual(len(lines), 4)  # working_top + divider + line_1 + line_2
        self.assertIn("正在执行: edit test.py ...", strip_ansi(lines[0]))
        self.assertIn("workspace", strip_ansi(lines[2]))
        self.assertIn("CH85.0%", strip_ansi(lines[3]))

    def test_terminal_display_attach_agent_and_working_dock(self):
        """测试 TerminalDisplay 动态关联 Agent 并生成工作态常驻底栏"""
        from mini_agent.cli.display import TerminalDisplay
        from unittest.mock import MagicMock

        mock_agent = MagicMock()
        mock_agent.workspace_dir = "/tmp/test_ws"
        mock_agent.client.model = "test-model"
        mock_agent.client.reasoning_effort = "medium"
        mock_agent.context.get_context_stats.return_value = {
            "current_tokens": 500,
            "context_window": 32000,
        }

        display = TerminalDisplay()
        # 未 attach 时返回空
        self.assertEqual(display.get_working_dock(), "")

        # attach 后返回完整运行态底栏
        display.attach_agent(mock_agent)
        dock = display.get_working_dock(status_text="规划任务中...")
        self.assertIn("规划任务中...", dock)
        self.assertIn("test_ws", dock)
        self.assertIn("test-model", dock)

    def test_truncate_to_width(self):
        """测试按物理列宽安全截断 (支持中英文全宽字符与 ANSI 颜色代码)"""
        from mini_agent.cli.theme import truncate_to_width

        # 1. 纯英文不超长
        self.assertEqual(truncate_to_width("hello", 10), "hello")
        # 2. 纯英文超长截断并补省略符
        res_en = truncate_to_width("hello world long text", 8, "…")
        self.assertLessEqual(visible_width(res_en), 8)
        self.assertTrue(strip_ansi(res_en).endswith("…"))

        # 3. 中文全宽双列截断
        res_cn = truncate_to_width("九九乘法表全彩高亮显示", 10, "…")
        self.assertLessEqual(visible_width(res_cn), 10)
        self.assertTrue(strip_ansi(res_cn).endswith("…"))

        # 4. ANSI 着色文本截断
        ansi_text = "\033[32m+181 // 第 5 行加粗高亮，第 4 行粉色，第 3/6 行蓝色\033[0m"
        res_ansi = truncate_to_width(ansi_text, 20, "…")
        self.assertLessEqual(visible_width(res_ansi), 20)
        self.assertTrue(strip_ansi(res_ansi).endswith("…"))

    def test_render_full_width_line_overflow_truncation_and_ansi_reset(self):
        """测试超长单行自动截断与内部 ANSI reset 底色保护，防止硬折行与色块黑缝"""
        # 超长行不应该超过给定 width (如 40 列)
        long_line = "// 第 5 行加粗高亮，第 4 行粉色，第 3/6 行蓝色，第 9 行红色，第 8 行彩虹"
        rendered = render_full_width_line(long_line, bg_rgb=BG_TOOL_SUCCESS, width=40)
        clean = strip_ansi(rendered)
        self.assertEqual(visible_width(clean), 40)
        self.assertTrue(clean.endswith("…"))

        # 内部包含 ansi_reset() 时，背景色序列被重新应用保护
        internal_reset_line = "前置文本\033[0m后置文本"
        rendered_safe = render_full_width_line(internal_reset_line, bg_rgb=BG_TOOL_SUCCESS, width=50)
        # 确保 \033[0m 之后立刻紧跟 24-bit TrueColor 背景色序列
        from mini_agent.cli.theme import ansi_bg, ansi_reset
        expected_patch = f"{ansi_reset()}{ansi_bg(BG_TOOL_SUCCESS)}"
        self.assertIn(expected_patch, rendered_safe)


if __name__ == "__main__":
    unittest.main()

