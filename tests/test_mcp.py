import asyncio
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

from mini_agent.agent import MiniAgent
from mini_agent.mcp.client import MCPError, StdioMCPClient
from mini_agent.mcp.manager import MCPManager
from mini_agent.mcp.tool import MCPToolWrapper
from mini_agent.tools.registry import ToolRegistry


MOCK_MCP_SERVER_SCRIPT = """
import sys, json

while True:
    line = sys.stdin.readline()
    if not line:
        break
    try:
        msg = json.loads(line)
    except Exception:
        continue

    method = msg.get("method")
    req_id = msg.get("id")

    if method == "initialize":
        res = {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "test-mock-server", "version": "1.0.0"}
            }
        }
        sys.stdout.write(json.dumps(res) + "\\n")
        sys.stdout.flush()
    elif method == "notifications/initialized":
        pass
    elif method == "tools/list":
        res = {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "tools": [
                    {
                        "name": "calc_double",
                        "description": "Double the given number",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "number": {"type": "integer", "description": "Target number"}
                            },
                            "required": ["number"]
                        }
                    },
                    {
                        "name": "fail_tool",
                        "description": "Tool that triggers an error",
                        "inputSchema": {
                            "type": "object",
                            "properties": {}
                        }
                    }
                ]
            }
        }
        sys.stdout.write(json.dumps(res) + "\\n")
        sys.stdout.flush()
    elif method == "tools/call":
        params = msg.get("params", {})
        tool_name = params.get("name")
        args = params.get("arguments", {})

        if tool_name == "calc_double":
            num = args.get("number", 0)
            res = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [
                        {"type": "text", "text": f"Result: {num * 2}"}
                    ],
                    "isError": False
                }
            }
        elif tool_name == "fail_tool":
            res = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [
                        {"type": "text", "text": "Operation failed unexpectedly"}
                    ],
                    "isError": True
                }
            }
        else:
            res = {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": -32601,
                    "message": f"Tool '{tool_name}' not found"
                }
            }
        sys.stdout.write(json.dumps(res) + "\\n")
        sys.stdout.flush()
"""


class TestStdioMCPClient(unittest.TestCase):
    def test_client_handshake_and_calls(self):
        async def run_test():
            client = StdioMCPClient(
                name="test_server",
                command=sys.executable,
                args=["-c", MOCK_MCP_SERVER_SCRIPT],
            )
            try:
                await client.start()
                self.assertTrue(client.is_running)
                self.assertEqual(client.server_info.get("name"), "test-mock-server")

                # 测试 tools/list
                tools = await client.list_tools()
                self.assertEqual(len(tools), 2)
                self.assertEqual(tools[0]["name"], "calc_double")
                self.assertEqual(tools[1]["name"], "fail_tool")

                # 测试 tools/call 正常成功
                call_res = await client.call_tool("calc_double", {"number": 21})
                self.assertFalse(call_res.get("isError", False))
                self.assertEqual(call_res["content"][0]["text"], "Result: 42")

                # 测试 tools/call 返回 isError=True
                fail_res = await client.call_tool("fail_tool", {})
                self.assertTrue(fail_res.get("isError", False))
                self.assertIn("failed unexpectedly", fail_res["content"][0]["text"])

                # 测试 tools/call 未知工具引发 MCPError
                with self.assertRaises(MCPError):
                    await client.call_tool("nonexistent", {})

            finally:
                await client.close()
                self.assertFalse(client.is_running)

        asyncio.run(run_test())

    def test_invalid_command_error(self):
        async def run_test():
            client = StdioMCPClient(
                name="invalid_server",
                command="non_existent_binary_12345678",
            )
            with self.assertRaises(RuntimeError):
                await client.start()

        asyncio.run(run_test())


class TestMCPToolWrapper(unittest.TestCase):
    def test_wrapper_schema_and_execution(self):
        async def run_test():
            client = StdioMCPClient(
                name="test_server",
                command=sys.executable,
                args=["-c", MOCK_MCP_SERVER_SCRIPT],
            )
            try:
                await client.start()
                wrapper = MCPToolWrapper(
                    client=client,
                    name="double_number",
                    description="Double a number",
                    input_schema={
                        "type": "object",
                        "properties": {"number": {"type": "integer"}},
                        "required": ["number"],
                    },
                    server_name="test_server",
                    original_name="calc_double",
                )

                # 校验 Schema 转换
                schema = wrapper.get_schema()
                self.assertEqual(schema["type"], "function")
                self.assertEqual(schema["function"]["name"], "double_number")
                self.assertIn("number", schema["function"]["parameters"]["properties"])

                # 校验 execute 成功
                res = await wrapper.execute(number=50)
                self.assertFalse(res.is_error)
                self.assertEqual(res.content, "Result: 100")
                self.assertEqual(res.details["server"], "test_server")

                # 校验 failure tool 包装
                fail_wrapper = MCPToolWrapper(
                    client=client,
                    name="fail_tool",
                    description="Fails",
                    input_schema={},
                    server_name="test_server",
                    original_name="fail_tool",
                )
                res_fail = await fail_wrapper.execute()
                self.assertTrue(res_fail.is_error)
                self.assertIn("failed unexpectedly", res_fail.content)

            finally:
                await client.close()

        asyncio.run(run_test())


class TestMCPManager(unittest.TestCase):
    def test_manager_parse_config_and_start_all(self):
        async def run_test():
            with tempfile.TemporaryDirectory() as tmp_dir:
                # 写入 mock_script 到临时文件以供执行
                script_path = os.path.join(tmp_dir, "server.py")
                with open(script_path, "w", encoding="utf-8") as f:
                    f.write(MOCK_MCP_SERVER_SCRIPT)

                config_path = os.path.join(tmp_dir, "mcp_servers.json")
                config_data = {
                    "mcpServers": {
                        "calc_service": {
                            "command": sys.executable,
                            "args": [script_path],
                        }
                    }
                }
                with open(config_path, "w", encoding="utf-8") as f:
                    json.dump(config_data, f)

                manager = MCPManager(workspace_dir=tmp_dir)
                found = manager.find_config_file(tmp_dir)
                self.assertEqual(found, config_path)

                registry = ToolRegistry()
                tools = await manager.start_all(config_path, registry=registry)

                self.assertEqual(len(tools), 2)
                self.assertIn("calc_double", registry.list_tools())
                self.assertIn("fail_tool", registry.list_tools())

                # 通过 ToolRegistry 派发执行 MCP 工具
                exec_res = await registry.execute("calc_double", {"number": 15})
                self.assertFalse(exec_res.is_error)
                self.assertEqual(exec_res.content, "Result: 30")

                await manager.close()
                self.assertEqual(len(manager.clients), 0)

        asyncio.run(run_test())

    def test_mini_agent_mcp_integration(self):
        async def run_test():
            with tempfile.TemporaryDirectory() as tmp_dir:
                script_path = os.path.join(tmp_dir, "server.py")
                with open(script_path, "w", encoding="utf-8") as f:
                    f.write(MOCK_MCP_SERVER_SCRIPT)

                mcp_config = {
                    "mcpServers": {
                        "math_mcp": {
                            "command": sys.executable,
                            "args": [script_path],
                        }
                    }
                }

                agent = MiniAgent(
                    workspace_dir=tmp_dir,
                    mcp_config=mcp_config,
                    sessions_dir=None,
                )

                tool_names = await agent.load_mcp()
                self.assertIn("calc_double", tool_names)
                self.assertIn("calc_double", agent.registry.list_tools())

                # 验证工具可被正确执行
                res = await agent.registry.execute("calc_double", {"number": 7})
                self.assertEqual(res.content, "Result: 14")

                await agent.close_mcp()

        asyncio.run(run_test())

    def test_send_request_timeout_cleanup(self):
        """测试请求超时后 pending future 自动清理，杜绝内存泄漏"""
        async def run_test():
            client = StdioMCPClient(
                name="test_server",
                command=sys.executable,
                args=["-c", MOCK_MCP_SERVER_SCRIPT],
            )
            try:
                await client.start()
                # 发送一个 mock 脚本中故意不应答的假方法，触发超时
                with self.assertRaises(asyncio.TimeoutError):
                    await client.send_request("unknown_never_reply", {}, timeout=0.05)

                # 验证 _pending_requests 字典已完全清空，无残留 future
                self.assertEqual(len(client._pending_requests), 0)
            finally:
                await client.close()

        asyncio.run(run_test())

    def test_env_expansion(self):
        """测试 MCP 环境变量 ${VAR} 与 ${VAR:-default} 展开"""
        from mini_agent.mcp.manager import expand_env_string
        with patch.dict(os.environ, {"MY_SECRET": "sec-12345"}):
            self.assertEqual(expand_env_string("${MY_SECRET}"), "sec-12345")
            self.assertEqual(expand_env_string("${NONEXISTENT:-fallback}"), "fallback")
            self.assertEqual(expand_env_string("plain_value"), "plain_value")

    def test_load_mcp_idempotency(self):
        """测试 agent.load_mcp 幂等性，重复调用不泄漏孤儿子进程"""
        async def run_test():
            with tempfile.TemporaryDirectory() as tmp_dir:
                script_path = os.path.join(tmp_dir, "server.py")
                with open(script_path, "w", encoding="utf-8") as f:
                    f.write(MOCK_MCP_SERVER_SCRIPT)

                mcp_config = {
                    "mcpServers": {
                        "math_mcp": {
                            "command": sys.executable,
                            "args": [script_path],
                        }
                    }
                }

                agent = MiniAgent(
                    workspace_dir=tmp_dir,
                    mcp_config=mcp_config,
                    sessions_dir=None,
                )

                # 第一次加载
                tools1 = await agent.load_mcp()
                pid1 = agent.mcp_manager.clients["math_mcp"].process.pid

                # 第二次加载 (模拟 session.init 重入)
                tools2 = await agent.load_mcp()
                pid2 = agent.mcp_manager.clients["math_mcp"].process.pid

                # 验证工具列表一致，且没有重复启动新子进程
                self.assertEqual(tools1, tools2)
                self.assertEqual(pid1, pid2)

                await agent.close_mcp()

        asyncio.run(run_test())

    def test_load_mcp_config_reload_closes_old_clients(self):
        """测试显式传入新配置重载时，旧服务进程被彻底关闭且旧工具从注册表解绑"""
        async def run_test():
            with tempfile.TemporaryDirectory() as tmp_dir:
                script_path = os.path.join(tmp_dir, "server.py")
                with open(script_path, "w", encoding="utf-8") as f:
                    f.write(MOCK_MCP_SERVER_SCRIPT)

                config1 = {
                    "mcpServers": {
                        "server_one": {
                            "command": sys.executable,
                            "args": [script_path],
                        }
                    }
                }
                config2 = {
                    "mcpServers": {
                        "server_two": {
                            "command": sys.executable,
                            "args": [script_path],
                        }
                    }
                }

                agent = MiniAgent(workspace_dir=tmp_dir, sessions_dir=None)

                # 加载配置 1
                await agent.load_mcp(config1)
                proc1 = agent.mcp_manager.clients["server_one"].process
                self.assertIn("calc_double", agent.registry.list_tools())

                # 显式重载为配置 2
                await agent.load_mcp(config2)

                # 断言旧进程已退出
                self.assertTrue(proc1.returncode is not None or not agent.mcp_manager.clients.get("server_one"))
                self.assertNotIn("server_one", agent.mcp_manager.clients)
                self.assertIn("server_two", agent.mcp_manager.clients)

                await agent.close_mcp()

        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()


