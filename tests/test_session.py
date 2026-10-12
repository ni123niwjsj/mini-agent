"""测试 SessionManager 与会话持久化功能。"""

import os
import shutil
import tempfile
import unittest
from mini_agent.agent import MiniAgent
from mini_agent.ai.client import LLMClient
from mini_agent.ai.types import ToolCall
from mini_agent.core.context import AgentContext
from mini_agent.core.session import SessionManager


class TestSessionPersistence(unittest.TestCase):
    """测试会话持久化核心逻辑"""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="test_mini_agent_sessions_")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_create_and_load_session(self):
        """测试创建会话、追加写入并重新加载"""
        manager = SessionManager(storage_dir=self.test_dir, model="test-model")
        session_id = manager.current_session_id
        self.assertIsNotNone(session_id)

        # 写入几条消息
        manager.append_message(role="user", content="你好，请帮我写个脚本")
        manager.append_message(
            role="assistant",
            content="没问题，我来调用工具",
            tool_calls=[{"id": "call_1", "name": "bash", "arguments": {"command": "ls"}}],
        )
        manager.append_message(role="tool", tool_call_id="call_1", content="file1.txt\nfile2.txt")

        # 验证文件是否存在
        session_file = manager.get_session_file(session_id)
        self.assertTrue(os.path.exists(session_file))

        # 读取并恢复
        header, messages = manager.load_session(session_id)
        self.assertEqual(header["session_id"], session_id)
        self.assertEqual(header["model"], "test-model")
        self.assertEqual(len(messages), 3)

        self.assertEqual(messages[0]["role"], "user")
        self.assertEqual(messages[0]["content"], "你好，请帮我写个脚本")

        self.assertEqual(messages[1]["role"], "assistant")
        self.assertEqual(messages[1]["content"], "没问题，我来调用工具")
        self.assertEqual(len(messages[1]["tool_calls"]), 1)

        self.assertEqual(messages[2]["role"], "tool")
        self.assertEqual(messages[2]["tool_call_id"], "call_1")
        self.assertEqual(messages[2]["content"], "file1.txt\nfile2.txt")

    def test_list_sessions(self):
        """测试会话列表扫描与摘要信息提取"""
        manager1 = SessionManager(storage_dir=self.test_dir, model="model-a")
        sid1 = manager1.current_session_id
        manager1.append_message(role="user", content="第一个任务：测试 A")

        manager2 = SessionManager(storage_dir=self.test_dir, model="model-b")
        sid2 = manager2.current_session_id
        manager2.append_message(role="user", content="第二个任务：测试 B")
        manager2.append_message(role="assistant", content="完成测试 B")

        sessions = manager1.list_sessions()
        self.assertEqual(len(sessions), 2)

        s_ids = [s["session_id"] for s in sessions]
        self.assertIn(sid1, s_ids)
        self.assertIn(sid2, s_ids)

        # 验证第二个会话的摘要
        s2_info = next(s for s in sessions if s["session_id"] == sid2)
        self.assertEqual(s2_info["message_count"], 2)
        self.assertEqual(s2_info["first_prompt"], "第二个任务：测试 B")

    def test_context_binding(self):
        """测试 AgentContext 与 SessionManager 联动实时持久化"""
        manager = SessionManager(storage_dir=self.test_dir)
        context = AgentContext(session_manager=manager)

        context.add_user_message("提问 1")
        context.add_assistant_message("回答 1", tool_calls=[ToolCall(id="t1", name="add", arguments={"a": 1, "b": 2})])
        context.add_tool_result("t1", "3")

        # 重新开一个 manager 加载
        manager2 = SessionManager(storage_dir=self.test_dir, session_id=manager.current_session_id)
        header, messages = manager2.load_session(manager.current_session_id)

        self.assertEqual(len(messages), 3)
        self.assertEqual(messages[0]["content"], "提问 1")
        self.assertEqual(messages[1]["tool_calls"][0]["function"]["name"], "add")
        self.assertEqual(messages[2]["content"], "3")

    def test_mini_agent_persistence_integration(self):
        """测试 MiniAgent 集成 session_id 恢复与状态管理"""
        client = LLMClient(model="mock")
        agent = MiniAgent(
            client=client,
            workspace_dir=self.test_dir,
            sessions_dir=self.test_dir,
        )
        sid = agent.current_session_id
        self.assertIsNotNone(sid)

        # 模拟交互
        agent.context.add_user_message("帮我统计数字")
        agent.context.add_assistant_message("统计完成，结果是 42")

        # 开启全新会话
        new_sid = agent.new_session()
        self.assertNotEqual(sid, new_sid)
        self.assertEqual(len(agent.context.messages), 0)

        # 重新恢复旧会话
        header, count = agent.load_session(sid)
        self.assertEqual(count, 2)
        self.assertEqual(len(agent.context.messages), 2)
        self.assertEqual(agent.context.messages[0]["content"], "帮我统计数字")

    def test_tree_parent_id_linking_and_reasoning(self):
        """测试条目的 id 与 parent_id 树状串联以及思维链持久化"""
        manager = SessionManager(storage_dir=self.test_dir)
        
        # 1. 第一条消息：用户提问 (parent_id 为 None)
        id1 = manager.append_message(role="user", content="第 1 问")
        self.assertIsNotNone(id1)
        self.assertIsNone(manager.load_session(manager.current_session_id)[1][0].get("parent_id"))

        # 2. 第二条消息：Assistant 回复 (携带思维链，parent_id 指向 id1)
        id2 = manager.append_message(
            role="assistant",
            content="第 1 答",
            reasoning="这是思考过程...",
        )
        self.assertEqual(manager.current_leaf_id, id2)

        # 校验原始文件中的 parent_id 和 reasoning
        _, entries, by_id = manager._load_raw_entries(manager.current_session_id)
        self.assertEqual(by_id[id2]["parent_id"], id1)
        self.assertEqual(by_id[id2]["reasoning"], "这是思考过程...")

    def test_undo_and_branch_sprouting(self):
        """测试 undo 时光倒流与无损新分支衍生"""
        agent = MiniAgent(
            workspace_dir=self.test_dir,
            sessions_dir=self.test_dir,
        )
        sid = agent.current_session_id

        # 轮次 1
        agent.context.add_user_message("提问 1")
        agent.context.add_assistant_message("回答 1")
        # 轮次 2
        agent.context.add_user_message("提问 2 (走入死胡同)")
        agent.context.add_assistant_message("回答 2 (有 Bug 的方案)")
        self.assertEqual(len(agent.context.messages), 4)

        # 执行 undo：时光倒流
        new_leaf, remaining_count = agent.undo()
        self.assertEqual(remaining_count, 2)
        self.assertEqual(len(agent.context.messages), 2)
        self.assertEqual(agent.context.messages[-1]["content"], "回答 1")

        # 从该节点衍生出新分支 (轮次 2 的全新方案)
        agent.context.add_user_message("提问 2 (新方案)")
        agent.context.add_assistant_message("回答 2 (正确的全新方案)")
        self.assertEqual(len(agent.context.messages), 4)
        self.assertEqual(agent.context.messages[2]["content"], "提问 2 (新方案)")

        # 检查底层文件：零删除！旧的"有 Bug 的方案"依然完好存在于文件中
        _, entries, by_id = agent.session_manager._load_raw_entries(sid)
        all_contents = [e.get("content") for e in entries if e.get("type") == "message"]
        self.assertIn("提问 2 (走入死胡同)", all_contents)
        self.assertIn("回答 2 (有 Bug 的方案)", all_contents)
        self.assertIn("提问 2 (新方案)", all_contents)
        self.assertIn("回答 2 (正确的全新方案)", all_contents)

        # 校验树状结构
        tree = agent.get_session_tree()
        self.assertGreaterEqual(len(tree["entries"]), 4)
        self.assertEqual(tree["active_leaf_id"], agent.session_manager.current_leaf_id)

    def test_checkout_branch(self):
        """测试 checkout 自由穿梭切换到历史分支"""
        manager = SessionManager(storage_dir=self.test_dir)
        id_u1 = manager.append_message(role="user", content="问 1")
        id_a1 = manager.append_message(role="assistant", content="答 1")
        
        # 分支 A
        id_u2a = manager.append_message(role="user", content="分支 A 问")
        id_a2a = manager.append_message(role="assistant", content="分支 A 答")

        # 撤回
        manager.undo()
        # 分支 B
        id_u2b = manager.append_message(role="user", content="分支 B 问")
        id_a2b = manager.append_message(role="assistant", content="分支 B 答")

        # 当前在分支 B
        _, msgs_b = manager.load_session(manager.current_session_id)
        self.assertEqual(msgs_b[-1]["content"], "分支 B 答")

        # 切回分支 A
        _, msgs_a = manager.checkout(id_a2a)
        self.assertEqual(msgs_a[-1]["content"], "分支 A 答")
        self.assertEqual(msgs_a[-2]["content"], "分支 A 问")

    def test_pi_format_envelope_alignment_and_content_blocks(self):
        """测试对齐 Pi 的顶层 Envelope 键序以及思考块/文本块/工具调用块的独立分块"""
        import json
        manager = SessionManager(storage_dir=self.test_dir, model="deepseek-flash")
        sid = manager.current_session_id

        # 1. 用户提问
        uid = manager.append_message(role="user", content="99乘法表")

        # 2. 助手回复 (包含 thinking 思考链, text 文本, toolCall 工具调用, usage 用量)
        aid = manager.append_message(
            role="assistant",
            content="正在为您生成 99 乘法表...",
            reasoning="用户需要 99 乘法表，我将调用 write_file 工具创建文件。",
            tool_calls=[{"id": "call_123", "name": "write_file", "arguments": {"path": "table.html"}}],
            usage={"input": 100, "output": 50, "cacheRead": 80, "totalTokens": 150},
        )

        # 3. 工具执行结果
        tid = manager.append_message(
            role="tool",
            tool_call_id="call_123",
            tool_name="write_file",
            content="Successfully written",
            is_error=False,
        )

        # 读取物理文件每一行，检查原始 JSON 结构
        file_path = manager.get_session_file(sid)
        with open(file_path, "r", encoding="utf-8") as f:
            lines = [json.loads(line) for line in f if line.strip()]

        self.assertEqual(len(lines), 4)  # session header, user, assistant, toolResult

        # 验证头部
        self.assertEqual(lines[0]["type"], "session")
        self.assertEqual(list(lines[0].keys())[:4], ["type", "version", "id", "timestamp"])

        # 验证前置键名严格有序: ["type", "id", "parentId", "timestamp", "message"]
        for entry_line in lines[1:]:
            keys = list(entry_line.keys())
            self.assertEqual(keys[:4], ["type", "id", "parentId", "timestamp"])
            self.assertEqual(keys[4], "message")

        # 验证助手消息中的独立分块
        ast_msg = lines[2]["message"]
        self.assertEqual(ast_msg["role"], "assistant")
        blocks = ast_msg["content"]
        self.assertEqual(len(blocks), 3)

        # 块 1: thinking
        self.assertEqual(blocks[0]["type"], "thinking")
        self.assertEqual(blocks[0]["thinking"], "用户需要 99 乘法表，我将调用 write_file 工具创建文件。")
        self.assertEqual(blocks[0]["thinkingSignature"], "reasoning_content")

        # 块 2: text
        self.assertEqual(blocks[1]["type"], "text")
        self.assertEqual(blocks[1]["text"], "正在为您生成 99 乘法表...")

        # 块 3: toolCall
        self.assertEqual(blocks[2]["type"], "toolCall")
        self.assertEqual(blocks[2]["id"], "call_123")
        self.assertEqual(blocks[2]["name"], "write_file")
        self.assertEqual(blocks[2]["arguments"], {"path": "table.html"})

        # 验证内嵌用量
        self.assertEqual(ast_msg["usage"]["totalTokens"], 150)
        self.assertEqual(ast_msg["stopReason"], "toolUse")

        # 验证工具返回
        tool_msg = lines[3]["message"]
        self.assertEqual(tool_msg["role"], "toolResult")
        self.assertEqual(tool_msg["toolCallId"], "call_123")
        self.assertEqual(tool_msg["toolName"], "write_file")
        self.assertEqual(tool_msg["content"][0]["text"], "Successfully written")

        # 验证 load_session 恢复
        header, restored = manager.load_session(sid)
        self.assertEqual(len(restored), 3)
        self.assertEqual(restored[1]["role"], "assistant")
        self.assertEqual(restored[1]["content"], "正在为您生成 99 乘法表...")
        self.assertEqual(restored[1]["reasoning"], "用户需要 99 乘法表，我将调用 write_file 工具创建文件。")
        self.assertEqual(restored[1]["tool_calls"][0]["function"]["name"], "write_file")

    def test_legacy_flat_format_compatibility(self):
        """测试加载旧版扁平 JSONL 历史文件 (向下无缝兼容)"""
        import json
        sid = "legacy_test_001"
        file_path = os.path.join(self.test_dir, f"{sid}.jsonl")
        legacy_lines = [
            {"type": "session_header", "session_id": sid, "created_at": "2026-10-01T10:00:00", "cwd": "/tmp", "model": "old-model"},
            {"type": "message", "role": "user", "content": "老提问", "id": "u1", "parent_id": None},
            {"type": "message", "role": "assistant", "content": "老回答", "reasoning": "老思考", "id": "a1", "parent_id": "u1"},
            {"type": "message", "role": "tool", "tool_call_id": "c1", "content": "老输出", "id": "t1", "parent_id": "a1"},
        ]
        with open(file_path, "w", encoding="utf-8") as f:
            for l in legacy_lines:
                f.write(json.dumps(l) + "\n")

        manager = SessionManager(storage_dir=self.test_dir, session_id=sid)
        header, messages = manager.load_session(sid)
        self.assertEqual(header["session_id"], sid)
        self.assertEqual(len(messages), 3)
        self.assertEqual(messages[0]["content"], "老提问")
        self.assertEqual(messages[1]["content"], "老回答")
        self.assertEqual(messages[1]["reasoning"], "老思考")
        self.assertEqual(messages[2]["content"], "老输出")


if __name__ == "__main__":
    unittest.main()
