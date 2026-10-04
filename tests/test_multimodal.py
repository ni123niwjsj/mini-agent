"""测试多模态图像支持与协议桥接 (Multimodal Vision Tests)。"""

import base64
import os
import shutil
import tempfile
import unittest
from mini_agent.agent import MiniAgent
from mini_agent.ai.client import LLMClient
from mini_agent.core.context import AgentContext
from mini_agent.core.session import SessionManager
from mini_agent.tools.file import ReadFileTool


# 创建一个微小的 1x1 像素 PNG 图片字节流 (标准有效的 PNG 头部)
TINY_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


class TestMultimodalSupport(unittest.TestCase):
    """测试多模态图像读取与上下文流转"""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="test_mini_agent_vision_")
        self.img_path = os.path.join(self.test_dir, "sample.png")
        with open(self.img_path, "wb") as f:
            f.write(TINY_PNG_BYTES)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    async def _async_test_read_image(self):
        tool = ReadFileTool(workspace_dir=self.test_dir)
        res = await tool.execute(path="sample.png")
        self.assertFalse(res.is_error)
        self.assertIn("Successfully read image 'sample.png'", res.content)
        self.assertIsNotNone(res.images)
        self.assertEqual(len(res.images), 1)
        self.assertEqual(res.images[0]["mime_type"], "image/png")
        self.assertTrue(len(res.images[0]["data"]) > 0)

    def test_read_file_tool_image(self):
        """测试 ReadFileTool 自动识别图像并编码 Base64"""
        import asyncio
        asyncio.run(self._async_test_read_image())

    def test_context_tool_result_multimodal_bridge(self):
        """测试 AgentContext 对齐 Pi 的协议桥接 (tool 结果 + 附图 user 消息)"""
        manager = SessionManager(storage_dir=self.test_dir)
        context = AgentContext(session_manager=manager)

        # 模拟模型发起了 read_file 调用，工具返回了图片
        sample_b64 = base64.b64encode(TINY_PNG_BYTES).decode("utf-8")
        context.add_tool_result(
            tool_call_id="call_img_1",
            output="Successfully read sample.png",
            images=[{"data": sample_b64, "mime_type": "image/png"}],
        )

        messages = context.get_messages_for_llm()
        # 验证有两条消息：一条 tool 文本回复，一条紧随其后的 user 图文消息
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["role"], "tool")
        self.assertEqual(messages[0]["content"], "Successfully read sample.png")

        self.assertEqual(messages[1]["role"], "user")
        self.assertIsInstance(messages[1]["content"], list)
        self.assertEqual(messages[1]["content"][0]["type"], "text")
        self.assertEqual(messages[1]["content"][1]["type"], "image_url")
        self.assertTrue(messages[1]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,"))

    def test_session_persistence_with_images(self):
        """测试多模态图像消息的落盘与恢复重构"""
        manager = SessionManager(storage_dir=self.test_dir)
        context = AgentContext(session_manager=manager)

        sample_b64 = base64.b64encode(TINY_PNG_BYTES).decode("utf-8")
        context.add_user_message(
            content="请看这张图片",
            images=[{"data": sample_b64, "mime_type": "image/png"}],
        )

        # 从磁盘重新载入
        header, restored_msgs = manager.load_session(manager.current_session_id)
        self.assertEqual(len(restored_msgs), 1)
        self.assertEqual(restored_msgs[0]["role"], "user")
        self.assertIsInstance(restored_msgs[0]["content"], list)
        self.assertEqual(restored_msgs[0]["content"][1]["type"], "image_url")


if __name__ == "__main__":
    unittest.main()
