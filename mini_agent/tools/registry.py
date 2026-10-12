"""工具注册中心 (ToolRegistry)。

负责管理所有可用工具的注册、模式聚合 (JSON Schema) 与安全派发执行。
借鉴 Pi 的容错自愈机制：找不到工具或参数不匹配时永不抛出未经捕获的崩溃异常，
而是返回友好的 ToolResult 引导大模型自我修正。
"""

from typing import Any, Callable, Dict, List, Optional, Union
from mini_agent.tools.base import BaseTool, ToolResult, tool


class ToolRegistry:
    """Agent 工具注册中心 (工具箱)"""

    def __init__(self):
        # 存放工具实例的字典，key 是工具名，value 是 BaseTool 实例
        self._tools: Dict[str, BaseTool] = {}

    def register(self, tool_or_func: Union[BaseTool, Callable]) -> None:
        """注册一个工具。
        
        支持两种形式：
        1. 传入 BaseTool 子类实例 (例如 ReadFileTool())
        2. 传入带有 @tool 或普通函数 (自动包装为 BaseTool)
        """
        if isinstance(tool_or_func, BaseTool):
            target_tool = tool_or_func
        elif callable(tool_or_func):
            target_tool = tool()(tool_or_func)
        else:
            raise TypeError(f"无法注册类型为 {type(tool_or_func)} 的对象为工具")

        self._tools[target_tool.name] = target_tool

    def get(self, name: str) -> Optional[BaseTool]:
        """按名称查找工具"""
        return self._tools.get(name)

    def unregister(self, name: str) -> Optional[BaseTool]:
        """按名称注销工具"""
        return self._tools.pop(name, None)

    def list_tools(self) -> List[str]:
        """获取所有已注册的工具名称列表"""
        return list(self._tools.keys())

    def get_schemas(self) -> List[Dict[str, Any]]:
        """获取所有已注册工具的 OpenAI Function Calling JSON Schema 列表"""
        return [t.get_schema() for t in self._tools.values()]

    async def execute(self, name: str, arguments: Dict[str, Any]) -> ToolResult:
        """安全调度执行指定工具。
        
        具备防御性编程能力：
        - 工具不存在时：返回带有可用工具列表的错误提示，引导模型自发修正。
        - 参数不匹配 (TypeError) 时：返回参数错误提示。
        - 运行时异常时：兜底捕获并返回 is_error=True。
        """
        target_tool = self.get(name)

        # 1. 容错拦截：工具不存在 (对标 Pi 的 createErrorToolResult)
        if not target_tool:
            available = self.list_tools()
            return ToolResult(
                content=(
                    f"Error: Tool '{name}' not found. "
                    f"Available tools are: {available}."
                ),
                is_error=True,
                details={"error_type": "ToolNotFound", "attempted_name": name},
            )

        # 2. 安全派发执行
        try:
            return await target_tool.execute(**arguments)
        except TypeError as e:
            # 大模型传错参数名（如多传或少传了必填参数）
            return ToolResult(
                content=f"Error: Invalid arguments for tool '{name}': {str(e)}",
                is_error=True,
                details={"error_type": "InvalidArguments", "exception": str(e)},
            )
        except Exception as e:
            # 任何未预料的系统异常
            return ToolResult(
                content=f"Error: Unexpected failure in tool '{name}': {str(e)}",
                is_error=True,
                details={"error_type": "ExecutionFailure", "exception": str(e)},
            )
