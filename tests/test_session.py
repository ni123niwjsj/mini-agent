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


if __name__ == "__main__":
    unittest.main()
