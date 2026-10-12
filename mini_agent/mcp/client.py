"""Model Context Protocol (MCP) Stdio 客户端实现。

遵循 Anthropic MCP 协议标准 (JSON-RPC 2.0 over Stdio)：
1. 子进程生命周期管理 (启动、通信、健康检查、安全平滑退出)
2. 握手握流 (initialize -> notifications/initialized)
3. 工具发现与执行 (tools/list -> tools/call)
"""

import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


class MCPError(Exception):
    """MCP 协议或服务端返回的错误"""

    def __init__(self, message: str, data: Any = None):
        super().__init__(message)
        self.message = message
        self.data = data


class StdioMCPClient:
    """基于标准输入输出 (Stdio) 的 MCP JSON-RPC 客户端"""

    def __init__(
        self,
        name: str,
        command: str,
        args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
        cwd: Optional[str] = None,
    ):
        self.name = name
        self.command = command
        self.args = args or []
        self.env = env
        self.cwd = cwd

        self.process: Optional[asyncio.subprocess.Process] = None
        self._request_id: int = 0
        self._pending_requests: Dict[Union[int, str], asyncio.Future] = {}
        self._reader_task: Optional[asyncio.Task] = None
        self._stderr_task: Optional[asyncio.Task] = None
        self._running: bool = False
        self._is_initialized: bool = False

        self.server_info: Dict[str, Any] = {}
        self.capabilities: Dict[str, Any] = {}

    @property
    def is_running(self) -> bool:
        """进程是否仍在正常运行"""
        return self._running and self.process is not None and self.process.returncode is None

    async def start(self) -> None:
        """启动 MCP Server 子进程并完成协议握手初始化"""
        if self.is_running:
            return

        merged_env = os.environ.copy()
        if self.env:
            merged_env.update(self.env)

        try:
            self.process = await asyncio.create_subprocess_exec(
                self.command,
                *self.args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.cwd,
                env=merged_env,
            )
        except Exception as e:
            raise RuntimeError(f"启动 MCP Server [{self.name}] 失败 ({self.command}): {e}") from e

        self._running = True
        self._reader_task = asyncio.create_task(self._read_stdout_loop())
        self._stderr_task = asyncio.create_task(self._drain_stderr_loop())

        # 完成 MCP 协议初始化
        await self.initialize()

    async def _drain_stderr_loop(self) -> None:
        """后台持续消费子进程 stderr，防止管道缓冲区撑满或无上限内存滞留"""
        if not self.process or not self.process.stderr:
            return
        try:
            while self._running:
                line = await self.process.stderr.readline()
                if not line:
                    break
                line_str = line.decode("utf-8", errors="replace").strip()
                if line_str:
                    logger.debug(f"[MCP stderr {self.name}] {line_str}")
        except asyncio.CancelledError:
            pass
        except Exception:
            pass

    async def _read_stdout_loop(self) -> None:
        """后台持续读取子进程 stdout 的 JSON-RPC 响应消息"""
        assert self.process is not None and self.process.stdout is not None

        try:
            while self._running:
                line = await self.process.stdout.readline()
                if not line:
                    # EOF (子进程关闭了 stdout 或退出)
                    break

                line_str = line.decode("utf-8", errors="replace").strip()
                if not line_str:
                    continue

                try:
                    msg = json.loads(line_str)
                except json.JSONDecodeError:
                    # 忽略非 JSON 日志行 (部分服务端可能将日志混入 stdout)
                    continue

                if not isinstance(msg, dict):
                    continue

                req_id = msg.get("id")
                if req_id is not None and req_id in self._pending_requests:
                    future = self._pending_requests.pop(req_id)
                    if not future.done():
                        if "error" in msg:
                            err_info = msg["error"]
                            err_msg = err_info.get("message", "Unknown MCP error") if isinstance(err_info, dict) else str(err_info)
                            future.set_exception(MCPError(err_msg, data=err_info))
                        else:
                            future.set_result(msg.get("result"))
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug(f"MCP client [{self.name}] read loop exception: {e}")
        finally:
            self._running = False
            # 唤醒所有挂起的请求，标记异常
            for fut in list(self._pending_requests.values()):
                if not fut.done():
                    fut.set_exception(RuntimeError(f"MCP Server [{self.name}] 连接意外中断"))
            self._pending_requests.clear()

    async def send_request(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        timeout: float = 30.0,
    ) -> Any:
        """向服务端发送 JSON-RPC 请求并等待返回结果"""
        if not self.is_running or not self.process or not self.process.stdin:
            raise RuntimeError(f"MCP Server [{self.name}] 未运行")

        self._request_id += 1
        req_id = self._request_id
        payload = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params if params is not None else {},
        }

        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self._pending_requests[req_id] = future

        msg_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8") + b"\n"
        self.process.stdin.write(msg_bytes)
        await self.process.stdin.drain()

        try:
            return await asyncio.wait_for(future, timeout=timeout)
        finally:
            self._pending_requests.pop(req_id, None)

    async def send_notification(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> None:
        """向服务端发送单向通知 (无需响应)"""
        if not self.is_running or not self.process or not self.process.stdin:
            return

        payload: Dict[str, Any] = {
            "jsonrpc": "2.0",
            "method": method,
        }
        if params is not None:
            payload["params"] = params

        msg_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8") + b"\n"
        self.process.stdin.write(msg_bytes)
        await self.process.stdin.drain()

    async def initialize(self) -> Dict[str, Any]:
        """执行 MCP 握手流程"""
        init_params = {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "roots": {"listChanged": True},
                "sampling": {},
            },
            "clientInfo": {
                "name": "mini-agent",
                "version": "0.2.0",
            },
        }
        res = await self.send_request("initialize", init_params, timeout=15.0)
        if isinstance(res, dict):
            self.server_info = res.get("serverInfo", {})
            self.capabilities = res.get("capabilities", {})

        await self.send_notification("notifications/initialized")
        self._is_initialized = True
        return res if isinstance(res, dict) else {}

    async def list_tools(self) -> List[Dict[str, Any]]:
        """获取服务端支持的所有工具清单"""
        res = await self.send_request("tools/list", {}, timeout=15.0)
        if isinstance(res, dict):
            return res.get("tools", [])
        return []

    async def call_tool(
        self,
        name: str,
        arguments: Optional[Dict[str, Any]] = None,
        timeout: float = 60.0,
    ) -> Dict[str, Any]:
        """调用服务端的指定工具"""
        params = {
            "name": name,
            "arguments": arguments or {},
        }
        res = await self.send_request("tools/call", params, timeout=timeout)
        if isinstance(res, dict):
            return res
        return {"content": [{"type": "text", "text": str(res)}], "isError": False}

    async def close(self) -> None:
        """安全关闭 MCP Server 客户端与子进程"""
        self._running = False

        for fut in list(self._pending_requests.values()):
            if not fut.done():
                fut.cancel()
        self._pending_requests.clear()

        if self._reader_task:
            self._reader_task.cancel()
            self._reader_task = None

        if self._stderr_task:
            self._stderr_task.cancel()
            self._stderr_task = None

        if self.process:
            try:
                if self.process.stdin:
                    self.process.stdin.close()
                self.process.terminate()
                try:
                    await asyncio.wait_for(self.process.wait(), timeout=1.5)
                except (asyncio.TimeoutError, TimeoutError):
                    self.process.kill()
            except Exception:
                pass
            self.process = None

