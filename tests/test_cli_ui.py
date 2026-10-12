"""测试 Phase 9 CLI 交互与 TUI 增强组件 (menu.py, display.py, 状态条与进度条)"""

import unittest
from unittest.mock import patch
from mini_agent.cli.display import (
    TerminalDisplay,
    format_context_gauge,
    format_tokens,
    get_git_branch,
)
from mini_agent.cli.menu import MenuItem, select_menu


class TestCliUI(unittest.TestCase):
    """测试 CLI UI 渲染与交互组件"""

    def test_format_tokens(self):
        """测试 Token 紧凑格式化显示"""
        self.assertEqual(format_tokens(500), "500")
        self.assertEqual(format_tokens(1500), "1.5k")
        self.assertEqual(format_tokens(128000), "128k")
        self.assertEqual(format_tokens(1000000), "1.0M")

    def test_format_context_gauge(self):
        """测试上下文占用进度条槽位渲染"""
        # 0% 占用
        gauge_empty = format_context_gauge(0, 1000, width=10)
        self.assertIn("░", gauge_empty)

        # 50% 占用 (绿色)
        gauge_half = format_context_gauge(500, 1000, width=10)
        self.assertIn("■", gauge_half)
        self.assertIn("░", gauge_half)

        # 85% 占用 (红色警戒)
        gauge_high = format_context_gauge(850, 1000, width=10)
        self.assertIn("■", gauge_high)

    def test_get_git_branch(self):
        """测试 Git 分支检测 (当前仓库必在 git 分支下)"""
        branch = get_git_branch(".")
        self.assertIsNotNone(branch)
        self.assertEqual(branch, "main")

    def test_menu_item_dataclass(self):
        """测试 MenuItem 数据模型"""
        item = MenuItem(id="deepseek-v4", label="DeepSeek V4", description="1M Tokens", is_current=True)
        self.assertEqual(item.id, "deepseek-v4")
        self.assertEqual(item.label, "DeepSeek V4")
        self.assertTrue(item.is_current)

    def test_select_menu_non_tty_fallback(self):
        """测试非 TTY 管道环境下的菜单优雅降级"""
        items = [
            MenuItem(id="m1", label="Model 1", description="128k"),
            MenuItem(id="m2", label="Model 2", description="1M"),
        ]
        # 强制模拟非 TTY 环境 (如 CI、管道输入)，安全返回默认项
        with patch("sys.stdin.isatty", return_value=False):
            selected = select_menu(items, title="选择模型", current_id="m2")
            self.assertIsNotNone(selected)
            self.assertEqual(selected.id, "m2")

    def test_select_menu_empty_items(self):
        """测试空选项安全返回 None"""
        selected = select_menu([])
        self.assertIsNone(selected)

    def test_select_menu_interactive_navigation(self):
        """测试 select_menu 上下移动并回车确认"""
        items = [
            MenuItem(id="m1", label="Model 1"),
            MenuItem(id="m2", label="Model 2"),
        ]
        # 模拟 TTY 环境下：按方向键 down 移动到 m2，按 enter 确认
        with patch("sys.stdin.isatty", return_value=True), \
             patch("mini_agent.cli.menu._read_raw_key_linux", side_effect=["down", "enter"]), \
             patch("termios.tcgetattr", return_value=[]), \
             patch("termios.tcsetattr"), \
             patch("termios.tcflush"), \
             patch("tty.setcbreak"):
            selected = select_menu(items, title="选择模型")
            self.assertIsNotNone(selected)
            self.assertEqual(selected.id, "m2")

    def test_terminal_display_render_status_bar(self):
        """测试状态底栏渲染不抛出异常"""
        display = TerminalDisplay()
        # 测试在各种数值下格式化正常
        display.render_status_bar(
            model_name="deepseek/deepseek-v4.1-flash",
            context_window=1000000,
            current_tokens=4048,
            latest_cache_hit_rate=98.3,
            workspace_dir=".",
        )

    def test_terminal_display_spinner_toggle(self):
        """测试动态 Spinner 的安全启动与平滑停止"""
        display = TerminalDisplay()
        display.start_spinner("测试加载中...")
        display.stop_spinner()
        # 重复 stop 不报错
        display.stop_spinner()

    def test_parse_escape_sequence(self):
        """测试终端转义序列解析 (ANSI 与 SS3 模式方向键、回车、Esc、快捷键)"""
        from mini_agent.cli.menu import _parse_escape_sequence

        # ANSI 模式方向键
        self.assertEqual(_parse_escape_sequence(b"\x1b[A"), "up")
        self.assertEqual(_parse_escape_sequence(b"\x1b[B"), "down")
        self.assertEqual(_parse_escape_sequence(b"\x1b[C"), "right")
        self.assertEqual(_parse_escape_sequence(b"\x1b[D"), "left")

        # SS3 模式方向键 (部分 Linux 终端与 tmux 环境)
        self.assertEqual(_parse_escape_sequence(b"\x1bOA"), "up")
        self.assertEqual(_parse_escape_sequence(b"\x1bOB"), "down")
        self.assertEqual(_parse_escape_sequence(b"\x1bOC"), "right")
        self.assertEqual(_parse_escape_sequence(b"\x1bOD"), "left")

        # 功能键与快捷键
        self.assertEqual(_parse_escape_sequence(b"\r"), "enter")
        self.assertEqual(_parse_escape_sequence(b"\n"), "enter")
        self.assertEqual(_parse_escape_sequence(b"\x1b"), "esc")
        self.assertEqual(_parse_escape_sequence(b"j"), "down")
        self.assertEqual(_parse_escape_sequence(b"k"), "up")
        self.assertEqual(_parse_escape_sequence(b"q"), "esc")
        self.assertEqual(_parse_escape_sequence(b"2"), "2")

    def test_repl_slash_commands_intercepted(self):
        """测试 REPL 斜杠指令被本地完全拦截，且自动清洗残留 [B/ 等转义前缀"""
        import asyncio
        from unittest.mock import MagicMock
        from mini_agent.cli.repl import start_repl

        mock_agent = MagicMock()
        mock_agent.registry.list_tools.return_value = ["bash", "read_file"]
        mock_agent.client.model = "initial-model"
        mock_agent.client.get_context_window.return_value = 128000
        mock_agent.context.context_window = 128000
        mock_agent.context.get_context_stats.return_value = {"current_tokens": 100, "context_window": 128000}
        mock_agent.context.max_turns = 50
        mock_agent.current_session_id = "test_session"
        mock_agent.workspace_dir = "."
        mock_agent.list_sessions.return_value = []
        mock_agent.stream = MagicMock()

        # 模拟连续输入:
        # 1. /help
        # 2. [B/sessions (模拟带方向键残留的指令，需自动清洗为 /sessions)
        # 3. /turns 20
        # 4. /unknown_command
        # 5. EOFError (Ctrl+D 退出)
        inputs = ["/help", "[B/sessions", "/turns 20", "/unknown_command", EOFError]

        with patch("builtins.input", side_effect=inputs):
            asyncio.run(start_repl(mock_agent))

        # 校验: agent.stream 绝不应该被任何斜杠指令或清洗后的指令触发
        self.assertEqual(mock_agent.stream.call_count, 0)
        # 校验: /turns 指令生效
        self.assertEqual(mock_agent.context.max_turns, 20)
        # 校验: [B/sessions 被成功识别并调用了 list_sessions
        self.assertEqual(mock_agent.list_sessions.call_count, 1)

    def test_repl_resume_triggers_replay_history(self):
        """测试 /resume 成功恢复会话后立即调用 replay_history 重放历史消息"""
        import asyncio
        from unittest.mock import MagicMock
        from mini_agent.cli.repl import start_repl

        mock_agent = MagicMock()
        mock_agent.registry.list_tools.return_value = ["bash"]
        mock_agent.client.model = "test-model"
        mock_agent.client.get_context_window.return_value = 128000
        mock_agent.context.context_window = 128000
        mock_agent.context.get_context_stats.return_value = {}
        mock_agent.current_session_id = "curr_sess"
        mock_agent.workspace_dir = "."
        mock_agent.list_sessions.return_value = [
            {"session_id": "sess_1", "created_at": "2026-10-04T12:00:00", "first_prompt": "hello", "message_count": 2}
        ]
        mock_agent.context.messages = []
        def fake_load(session_id):
            mock_agent.context.messages = [
                {"role": "user", "content": "历史提问"},
                {"role": "assistant", "content": "历史回复"},
            ]
            return ({"id": session_id}, 2)
        mock_agent.load_session.side_effect = fake_load

        inputs = ["/resume 1", EOFError]
        with patch("builtins.input", side_effect=inputs), \
             patch("mini_agent.cli.display.TerminalDisplay.replay_history") as mock_replay:
            asyncio.run(start_repl(mock_agent))

        mock_agent.load_session.assert_called_once_with("sess_1")
        mock_replay.assert_called_once_with(mock_agent.context.messages)

    def test_assistant_delta_streaming_preserves_text(self):
        """测试流式吐字绝不会被逐字行擦除，且不输出未解析的富文本标签"""
        import io
        from contextlib import redirect_stdout

        display = TerminalDisplay()
        f = io.StringIO()
        with redirect_stdout(f):
            display.start_spinner("测试思考中...")
            # 模拟思考过程流式输出
            display.print_assistant_delta("思考第一步...", is_reasoning=True)
            display.print_assistant_delta("思考第二步...", is_reasoning=True)
            # 模拟转入实际回答
            display.print_assistant_delta("你好！", is_reasoning=False)
            display.print_assistant_delta("这是完整内容。", is_reasoning=False)
            display.print_assistant_message_end()

        output = f.getvalue()
        # 校验关键内容完整保留，未被逐行清除
        self.assertIn("思考第一步...", output)
        self.assertIn("思考第二步...", output)
        self.assertIn("你好！", output)
        self.assertIn("这是完整内容。", output)
        # 校验绝无裸露的 Rich 标签泄露
        self.assertNotIn("[/italic]", output)
        self.assertNotIn("[/dim]", output)
        self.assertNotIn("[dim]", output)

    def test_live_markdown_rendering_in_tty(self):
        """测试在 TTY 交互终端下启动 Live Markdown 实时渲染并平滑收起"""
        from unittest.mock import MagicMock

        display = TerminalDisplay()
        with patch("sys.stdout.isatty", return_value=True):
            # 开启并流式吐出 Markdown 内容
            display.print_agent_start("测试任务")
            display.print_assistant_delta("发现 **重点** 内容与 `代码`", is_reasoning=False)
            self.assertIsNotNone(display._live_display)
            display.print_assistant_message_end()
            # 结束时 Live 应已安全关闭
            self.assertIsNone(display._live_display)

    def test_tool_syntax_highlighting(self):
        """测试工具结果渲染支持代码语法高亮与 Diff 着色"""
        display = TerminalDisplay()
        display.print_tool_start("read_file", {"path": "main.py"})
        self.assertEqual(display._last_tool_file, "main.py")
        # 测试正常渲染 python 代码块不报错
        display.print_tool_result("read_file", "def hello():\n    return 42\n")
        # 测试渲染 bash 报错不报错
        display.print_tool_result("bash", "error: command not found", is_error=True)


    def test_token_streaming_preservation_and_spinner_coordination(self):
        """测试高频 Token 流式吐字时，文本完整保留绝不被覆写、抹除或截断，且 Spinner 协调优雅退出"""
        from unittest.mock import MagicMock
        import io

        mock_agent = MagicMock()
        mock_agent.workspace_dir = "/tmp/test"
        mock_agent.client.model = "test-model"

        display = TerminalDisplay(agent=mock_agent)
        
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            # 1. 模拟任务开始，进入规划等待阶段
            display.print_agent_start("你好啊又见面了")

            # 2. 首个思维链 token 到达 -> spinner 应平滑停靠，思维链自然展开
            display.print_assistant_delta("思考一下：", is_reasoning=True)
            self.assertFalse(display._spinner_active)
            display.print_assistant_delta("用户在向我们打招呼。", is_reasoning=True)

            # 3. 正式回答开始
            display.print_assistant_delta("你好！", is_reasoning=False)
            display.print_assistant_delta("很高兴再次见到你。\n", is_reasoning=False)
            display.print_assistant_delta("- 第 1 行: 内容 A\n", is_reasoning=False)
            display.print_assistant_delta("- 第 2 行: 内容 B", is_reasoning=False)
            display.print_assistant_message_end()

        output = buf.getvalue()
        # 验证所有文本均完好保留在输出流中
        self.assertIn("思考一下：", output)
        self.assertIn("用户在向我们打招呼。", output)
        self.assertIn("你好！", output)
        self.assertIn("很高兴再次见到你。", output)
        self.assertIn("- 第 1 行: 内容 A", output)
        self.assertIn("- 第 2 行: 内容 B", output)


if __name__ == "__main__":
    unittest.main()


