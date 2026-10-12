"""BridgeServer 单元测试集。
验证 Stdio JSON-RPC 协议解析、生命周期事件通知、动态引导与模型参数配置。
"""

import asyncio
import io
import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from mini_agent.bridge.server import BridgeServer, get_git_branch
from mini_agent.core.events import (
    AgentEnd,
    AgentStart,
    AssistantDelta,
    AssistantMessage,
    ToolCallStart,
    ToolResult,
)


class TestBridgeServer(unittest.IsolatedAsyncioTestCase):
    """测试 BridgeServer JSON-RPC 通信与事件机制"""

    def setUp(self):
        self.mock_agent = MagicMock()
        self.mock_agent.workspace_dir = "/tmp/test_workspace"
        self.mock_agent.current_session_id = "test-sid-123"
        self.mock_agent.client.model = "test-model"
        self.mock_agent.client.reasoning_effort = "high"
        self.mock_agent.client.get_context_window.return_value = 128000
        self.mock_agent.context.context_window = 128000
        self.mock_agent.context.get_context_stats.return_value = {
            "current_tokens": 100,
            "max_tokens": 128000,
            "percent": 0.1,
        }
        self.mock_agent.registry.list_tools.return_value = ["bash"]
        mock_tool = MagicMock()
        mock_tool.description = "Execute shell commands"
        mock_tool.to_schema.return_value = {"name": "bash"}
        self.mock_agent.registry.get.return_value = mock_tool

        self.in_buf = io.StringIO()
        self.out_buf = io.StringIO()
        self.server = BridgeServer(
            agent=self.mock_agent,
            in_stream=self.in_buf,
            out_stream=self.out_buf,
        )

    def _get_output_messages(self):
        """解析输出流中的所有 JSON 消息"""
        lines = self.out_buf.getvalue().strip().split("\n")
        return [json.loads(line) for line in lines if line.strip()]

    async def test_session_init(self):
        """测试 session.init 正常获取工作区与模型遥测指标"""
        req = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "session.init",
            "params": {},
        }
        await self.server.handle_request(req)
        msgs = self._get_output_messages()
        self.assertEqual(len(msgs), 1)
        resp = msgs[0]
        self.assertEqual(resp["id"], 1)
        res = resp["result"]
        self.assertEqual(res["model"], "test-model")
        self.assertEqual(res["session_id"], "test-sid-123")
        self.assertEqual(res["context_window"], 128000)

    async def test_agent_steer(self):
        """测试 agent.steer 将任务引导词入队并派发事件"""
        req = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "agent.steer",
            "params": {"guidance": "不要修改 package.json"},
        }
        await self.server.handle_request(req)
        msgs = self._get_output_messages()
        self.assertEqual(len(msgs), 2)
        resp = msgs[0]
        self.assertEqual(resp["id"], 2)
        self.assertEqual(resp["result"]["status"], "queued")
        notify = msgs[1]
        self.assertEqual(notify["method"], "agent.steered")
        self.assertEqual(notify["params"]["guidance"], "不要修改 package.json")

        guidance = await self.server._steering_queue.get()
        self.assertEqual(guidance, "不要修改 package.json")

    async def test_config_set_model(self):
        """测试 config.set_model 更新模型规格与窗口"""
        req = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "config.set_model",
            "params": {"model": "claude-3-5-sonnet"},
        }
        await self.server.handle_request(req)
        msgs = self._get_output_messages()
        self.assertEqual(self.mock_agent.client.model, "claude-3-5-sonnet")
        self.assertEqual(msgs[0]["result"]["model"], "claude-3-5-sonnet")

    async def test_prompt_send_streaming_events(self):
        """测试 prompt.send 能够将 Agent 生成的生命周期事件完整转换为 JSON 通知"""
        async def fake_stream(*args, **kwargs):
            yield AgentStart(user_prompt="编写快速排序")
            yield AssistantDelta(content="思考实现方案", is_reasoning=True)
            yield AssistantDelta(content="def quicksort(): pass", is_reasoning=False)
            yield ToolCallStart(tool_name="bash", tool_call_id="call_1", arguments={"cmd": "ls"})
            yield ToolResult(tool_name="bash", tool_call_id="call_1", output="ok", is_error=False)
            yield AgentEnd(final_response="已完成", total_turns=1, usage={})

        self.mock_agent.stream = fake_stream

        req = {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "prompt.send",
            "params": {"prompt": "编写快速排序"},
        }
        await self.server.handle_request(req)
        msgs = self._get_output_messages()
        
        events = [m.get("method") for m in msgs if "method" in m]
        self.assertIn("agent.start", events)
        self.assertIn("agent.delta", events)
        self.assertIn("tool.start", events)
        self.assertIn("tool.result", events)
        self.assertIn("agent.end", events)
        self.assertIn("stats.update", events)

        last_resp = msgs[-1]
        self.assertEqual(last_resp["id"], 4)
        self.assertEqual(last_resp["result"]["status"], "completed")

    async def test_tools_list(self):
        """测试 tools.list 正常返回工具清单"""
        req = {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools.list",
            "params": {},
        }
        await self.server.handle_request(req)
        msgs = self._get_output_messages()
        self.assertEqual(len(msgs), 1)
        tools = msgs[0]["result"]["tools"]
        self.assertEqual(len(tools), 1)
        self.assertEqual(tools[0]["name"], "bash")

    async def test_session_resume_by_index(self):
        """测试 session.resume 支持纯数字序号解析并返回完整历史消息"""
        self.mock_agent.list_sessions.return_value = [
            {"session_id": "sess-20261005-001", "created_at": "2026-10-05T12:00:00", "message_count": 2},
            {"session_id": "sess-20261005-002", "created_at": "2026-10-05T13:00:00", "message_count": 5},
        ]
        self.mock_agent.load_session.return_value = ({"session_id": "sess-20261005-001"}, 2)
        self.mock_agent.context.messages = [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好！请问有什么我可以帮你的？"},
        ]

        req = {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "session.resume",
            "params": {"session_id": "1"},
        }
        await self.server.handle_request(req)
        msgs = self._get_output_messages()
        self.assertEqual(len(msgs), 2)
        resp = msgs[0]
        self.assertEqual(resp["id"], 6)
        self.assertEqual(resp["result"]["session_id"], "sess-20261005-001")
        self.assertEqual(len(resp["result"]["messages"]), 2)
        self.assertEqual(resp["result"]["messages"][0]["role"], "user")
        self.assertEqual(resp["result"]["messages"][0]["content"], "你好")

    async def test_config_set_effort_shortcuts(self):
        """测试 config.set_effort 支持数字快捷方式与命名设置"""
        req1 = {"jsonrpc": "2.0", "id": 7, "method": "config.set_effort", "params": {"effort": "3"}}
        await self.server.handle_request(req1)
        self.assertEqual(self.mock_agent.client.reasoning_effort, "high")

        req2 = {"jsonrpc": "2.0", "id": 8, "method": "config.set_effort", "params": {"effort": "none"}}
        await self.server.handle_request(req2)
        self.assertIsNone(self.mock_agent.client.reasoning_effort)


if __name__ == "__main__":
    unittest.main()

