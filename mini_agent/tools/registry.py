"""工具注册中心 (ToolRegistry)。

负责工具的注册、查找、JSON Schema 聚合以及执行派发。
"""

from typing import Any, Dict, List, Optional
from mini_agent.tools.base import BaseTool


class ToolRegistry:
    """管理 Agent 可用工具的注册中心"""

    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """注册一个工具实例"""
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[BaseTool]:
        """按名称查找工具"""
        return self._tools.get(name)

    def get_schemas(self) -> List[Dict[str, Any]]:
        """获取所有已注册工具的 JSON Schema 列表供 LLM 使用"""
        return [tool.get_schema() for tool in self._tools.values()]

    async def execute(self, name: str, arguments: Dict[str, Any]) -> Any:
        """安全调度执行指定工具"""
        tool = self.get(name)
        if not tool:
            raise ValueError(f"未找到工具: '{name}'")
        return await tool.execute(**arguments)
