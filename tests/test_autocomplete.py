"""单元测试：斜杠指令内联自动补全与命令提示组件 (Command Autocomplete)"""

import unittest
from unittest.mock import MagicMock, patch
from mini_agent.cli.autocomplete import (
    SLASH_COMMANDS_REGISTRY,
    filter_slash_commands,
    is_interactive_tty,
    read_line_with_autocomplete,
    render_autocomplete_dropdown,
)
from mini_agent.cli.display import TerminalDisplay, WorkingDockRenderable


class TestAutocomplete(unittest.TestCase):
    """测试命令补全、筛选、浮层渲染与 TTY 判断"""

    def test_registry_contains_core_commands(self):
        """测试内置命令注册表中包含核心斜杠指令"""
        names = [c.name for c in SLASH_COMMANDS_REGISTRY]
        self.assertIn("/model", names)
        self.assertIn("/resume", names)
        self.assertIn("/compact", names)
        self.assertIn("/undo", names)
        self.assertIn("/tree", names)
        self.assertIn("/checkout", names)
        self.assertIn("/usage", names)
        self.assertIn("/effort", names)
        self.assertIn("/turns", names)
        self.assertIn("/tools", names)
        self.assertIn("/help", names)
        self.assertIn("/exit", names)

    def test_filter_exact_prefix(self):
        """测试输入前缀模糊筛选"""
        matches_m = filter_slash_commands("/m")
        names_m = [c.name for c in matches_m]
        self.assertIn("/model", names_m)
        self.assertIn("/models", names_m)
        self.assertNotIn("/help", names_m)

        matches_c = filter_slash_commands("/c")
        names_c = [c.name for c in matches_c]
        self.assertIn("/compact", names_c)
        self.assertIn("/checkout", names_c)
        self.assertIn("/clear", names_c)

    def test_filter_slash_only_returns_all(self):
        """测试单斜杠 '/' 返回全部命令候选"""
        matches = filter_slash_commands("/")
        self.assertEqual(len(matches), len(SLASH_COMMANDS_REGISTRY))

    def test_render_autocomplete_dropdown(self):
        """测试悬浮菜单卡片渲染与高亮光标"""
        matches = filter_slash_commands("/m")
        lines = render_autocomplete_dropdown(matches, selected_idx=0, width=80)
        self.assertGreaterEqual(len(lines), 3)
        # 第一项应该包含光标 ❯ 与反白
        self.assertIn("❯", lines[1])
        self.assertIn("/model", lines[1])
        # 第二项为普通未高亮项
        self.assertIn("/models", lines[2])

    def test_read_line_with_autocomplete_fallback_in_non_tty(self):
        """测试在非交互或 Mock input 环境下安全降级为 input()"""
        with patch("builtins.input", return_value="/help"):
            res = read_line_with_autocomplete(agent=None)
            self.assertEqual(res, "/help")

    def test_working_dock_renderable(self):
        """测试常驻运行态底栏 Renderable 渲染"""
        mock_agent = MagicMock()
        mock_agent.workspace_dir = "/tmp/test"
        mock_agent.client.model = "deepseek-v4.1"
        mock_agent.client.reasoning_effort = "high"
        mock_agent.context.get_context_stats.return_value = {"current_tokens": 500, "context_window": 128000}

        display = TerminalDisplay(agent=mock_agent)
        dock = WorkingDockRenderable(display)
        rich_obj = dock.__rich__()
        self.assertIsNotNone(rich_obj)
        # 底栏输出包含当前状态与模型信息
        plain = str(rich_obj)
        self.assertIn("deepseek-v4.1", plain)


if __name__ == "__main__":
    unittest.main()
