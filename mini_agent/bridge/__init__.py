"""Mini-Agent Stdio JSON-RPC 桥接服务包。
提供 TypeScript/Ink 前端与 Python 后端 Agent 引擎通信的标准网关。
"""

from mini_agent.bridge.server import BridgeServer

__all__ = ["BridgeServer"]
