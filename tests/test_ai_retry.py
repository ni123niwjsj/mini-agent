import asyncio
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from mini_agent.agent import MiniAgent
from mini_agent.ai.client import LLMClient
from mini_agent.tools.todo import TodoTool
from mini_agent.tools.search import GrepTool, GlobTool


class TestLLMClientRetry(unittest.TestCase):
    def test_retry_on_transient_failure_then_success(self):
        client = LLMClient(model="test-model", max_retries=2, retry_delay=0.01)

        # 模拟前一次失败，第二次成功的流
        mock_chunk = MagicMock()
        mock_chunk.usage = None
        mock_chunk.choices = [
            MagicMock(
                delta=MagicMock(content="Hello retry!", reasoning_content=None, reasoning=None, tool_calls=None),
                finish_reason="stop",
            )
        ]

        async def mock_async_stream():
            yield mock_chunk

        call_count = 0

        async def mock_create(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("Temporary network reset")
            return mock_async_stream()

        mock_instance = MagicMock()
        mock_instance.chat.completions.create = AsyncMock(side_effect=mock_create)
        mock_openai = MagicMock()
        mock_openai.AsyncOpenAI = MagicMock(return_value=mock_instance)

        with patch.dict(sys.modules, {"openai": mock_openai}):
            async def run_stream():
                events = []
                async for evt in client.stream_chat(messages=[{"role": "user", "content": "hi"}]):
                    events.append(evt)
                return events

            events = asyncio.run(run_stream())
            self.assertEqual(call_count, 2)
            self.assertTrue(any(e[0] == "text_delta" and e[1] == "Hello retry!" for e in events))

    def test_non_retryable_client_error_fails_immediately(self):
        client = LLMClient(model="test-model", max_retries=3, retry_delay=0.01)

        class MockAPIError(Exception):
            status_code = 401

        call_count = 0

        async def mock_create(**kwargs):
            nonlocal call_count
            call_count += 1
            raise MockAPIError("Unauthorized API Key")

        mock_instance = MagicMock()
        mock_instance.chat.completions.create = AsyncMock(side_effect=mock_create)
        mock_openai = MagicMock()
        mock_openai.AsyncOpenAI = MagicMock(return_value=mock_instance)

        with patch.dict(sys.modules, {"openai": mock_openai}):
            async def run_stream():
                async for _ in client.stream_chat(messages=[{"role": "user", "content": "hi"}]):
                    pass

            with self.assertRaises(MockAPIError):
                asyncio.run(run_stream())

            self.assertEqual(call_count, 1)

    def test_exceeds_max_retries_raises(self):
        client = LLMClient(model="test-model", max_retries=2, retry_delay=0.01)
        call_count = 0

        async def mock_create(**kwargs):
            nonlocal call_count
            call_count += 1
            raise ConnectionError("Persistent server failure")

        mock_instance = MagicMock()
        mock_instance.chat.completions.create = AsyncMock(side_effect=mock_create)
        mock_openai = MagicMock()
        mock_openai.AsyncOpenAI = MagicMock(return_value=mock_instance)

        with patch.dict(sys.modules, {"openai": mock_openai}):
            async def run_stream():
                async for _ in client.stream_chat(messages=[{"role": "user", "content": "hi"}]):
                    pass

            with self.assertRaises(ConnectionError):
                asyncio.run(run_stream())

            # 初始 1 次 + 重试 2 次 = 3 次调用
            self.assertEqual(call_count, 3)

    def test_agent_registers_phase2_tools(self):
        agent = MiniAgent(client=LLMClient(model="mock"), sessions_dir=None)
        self.assertIsNotNone(agent.registry.get("todo"))
        self.assertIsInstance(agent.registry.get("todo"), TodoTool)

        self.assertIsNotNone(agent.registry.get("grep"))
        self.assertIsInstance(agent.registry.get("grep"), GrepTool)

        self.assertIsNotNone(agent.registry.get("glob"))
        self.assertIsInstance(agent.registry.get("glob"), GlobTool)

        # 检查 system prompt 中是否含有 grep, glob, todo 说明
        sys_prompt = agent.context.system_prompt
        self.assertIn("grep", sys_prompt)
        self.assertIn("glob", sys_prompt)
        self.assertIn("todo", sys_prompt)


if __name__ == "__main__":
    unittest.main()

