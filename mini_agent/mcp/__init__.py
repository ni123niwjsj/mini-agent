"""Model Context Protocol (MCP) 模块。

导出标准 Stdio MCP 客户端、工具包装器与服务端集群管理器。
"""

from mini_agent.mcp.client import MCPError, StdioMCPClient
from mini_agent.mcp.manager import MCPManager
from mini_agent.mcp.tool import MCPToolWrapper

__all__ = [
    "StdioMCPClient",
    "MCPError",
    "MCPToolWrapper",
    "MCPManager",
]

