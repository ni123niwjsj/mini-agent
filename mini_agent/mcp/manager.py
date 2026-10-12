"""MCP 多服务端生命周期与配置管理器 (MCPManager)。

支持加载 mcp_servers.json / .mcp.json 配置文件，
一键发现、批量启动并挂载外部 MCP 服务的全部工具到 ToolRegistry。
"""

import asyncio
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Union
from mini_agent.mcp.client import StdioMCPClient
from mini_agent.mcp.tool import MCPToolWrapper
from mini_agent.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


ENV_VAR_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


def expand_env_string(val: str) -> str:
    """展开形如 ${VAR} 或 ${VAR:-default} 的环境变量"""
    if not isinstance(val, str) or "$" not in val:
        return val

    def replace_var(match: re.Match) -> str:
        var_name = match.group(1)
        default_val = match.group(2) if match.group(2) is not None else ""
        return os.environ.get(var_name, default_val)

    expanded = ENV_VAR_PATTERN.sub(replace_var, val)
    return os.path.expandvars(expanded)


class MCPManager:
    """MCP 服务端集群与工具集成管理器"""

    def __init__(self, workspace_dir: str = "."):
        self.workspace_dir = os.path.abspath(workspace_dir)
        self.clients: Dict[str, StdioMCPClient] = {}
        self.tools: List[MCPToolWrapper] = []

    @classmethod
    def find_config_file(cls, base_dir: str = ".") -> Optional[str]:
        """按常规约定查找工作区中的 MCP 配置文件"""
        candidates = [
            os.path.join(base_dir, "mcp_servers.json"),
            os.path.join(base_dir, ".mcp.json"),
            os.path.join(base_dir, ".cursor", "mcp.json"),
        ]
        for path in candidates:
            if os.path.isfile(path):
                return path
        return None

    def parse_config(self, config: Union[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """解析并统一 MCP 配置字典"""
        raw_dict: Dict[str, Any] = {}
        if isinstance(config, str):
            if not os.path.isabs(config):
                config = os.path.join(self.workspace_dir, config)
            if not os.path.exists(config):
                logger.warning(f"MCP 配置文件未找到: {config}")
                return {}
            with open(config, "r", encoding="utf-8") as f:
                raw_dict = json.load(f)
        elif isinstance(config, dict):
            raw_dict = config

        # 兼容两种常见顶级格式: {"mcpServers": { ... }} 或 { "server1": { ... } }
        if "mcpServers" in raw_dict and isinstance(raw_dict["mcpServers"], dict):
            return raw_dict["mcpServers"]
        return raw_dict

    async def add_server(
        self,
        name: str,
        config: Dict[str, Any],
        registry: Optional[ToolRegistry] = None,
        prefix_tool_names: bool = False,
    ) -> List[MCPToolWrapper]:
        """启动单个 MCP 服务并挂载工具"""
        command = config.get("command")
        if not command:
            logger.warning(f"MCP 服务 [{name}] 配置缺失 'command'，已跳过")
            return []

        # 若已存在同名服务端，先平滑关闭旧进程并清除旧工具，防止僵尸进程泄漏
        if name in self.clients:
            old_client = self.clients[name]
            try:
                await old_client.close()
            except Exception as e:
                logger.debug(f"关闭旧 MCP 客户端 [{name}] 异常: {e}")
            old_tools = [t for t in self.tools if t.server_name == name]
            if registry:
                for ot in old_tools:
                    registry.unregister(ot.name)
            self.tools = [t for t in self.tools if t.server_name != name]

        args = config.get("args", [])
        raw_env = config.get("env")
        env: Optional[Dict[str, str]] = None
        if raw_env and isinstance(raw_env, dict):
            env = {str(k): expand_env_string(str(v)) for k, v in raw_env.items()}

        cwd = config.get("cwd", self.workspace_dir)

        client = StdioMCPClient(
            name=name,
            command=command,
            args=args,
            env=env,
            cwd=cwd,
        )

        try:
            await client.start()
        except Exception as e:
            logger.warning(f"MCP 服务 [{name}] 启动失败: {e}")
            await client.close()
            return []

        self.clients[name] = client

        # 发现工具并封装
        created_tools: List[MCPToolWrapper] = []
        try:
            remote_tools = await client.list_tools()
            for r_tool in remote_tools:
                orig_name = r_tool.get("name", "")
                if not orig_name:
                    continue

                tool_name = orig_name
                # 若需要前缀，或注册表中已有同名工具，自动加服务名前缀防止碰撞
                if prefix_tool_names or (registry and registry.get(tool_name) is not None):
                    tool_name = f"{name}__{orig_name}"

                wrapper = MCPToolWrapper(
                    client=client,
                    name=tool_name,
                    description=r_tool.get("description", ""),
                    input_schema=r_tool.get("inputSchema", {}),
                    server_name=name,
                    original_name=orig_name,
                )
                created_tools.append(wrapper)
                self.tools.append(wrapper)

                if registry:
                    registry.register(wrapper)

        except Exception as e:
            logger.warning(f"获取 MCP 服务 [{name}] 工具清单失败: {e}")

        return created_tools

    async def start_all(
        self,
        config: Union[str, Dict[str, Any]],
        registry: Optional[ToolRegistry] = None,
        prefix_tool_names: bool = False,
    ) -> List[MCPToolWrapper]:
        """批量启动配置中声明的所有 MCP 服务端"""
        servers = self.parse_config(config)
        all_tools: List[MCPToolWrapper] = []

        for s_name, s_cfg in servers.items():
            if not isinstance(s_cfg, dict):
                continue
            tools = await self.add_server(
                name=s_name,
                config=s_cfg,
                registry=registry,
                prefix_tool_names=prefix_tool_names,
            )
            all_tools.extend(tools)

        return all_tools

    async def close(self) -> None:
        """关闭所有运行中的 MCP 客户端进程"""
        close_tasks = [client.close() for client in self.clients.values()]
        if close_tasks:
            await asyncio.gather(*close_tasks, return_exceptions=True)
        self.clients.clear()
        self.tools.clear()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

