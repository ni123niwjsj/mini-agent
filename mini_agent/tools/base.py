"""工具契约与基础定义 (BaseTool, ToolResult, @tool)。

借鉴现代开源 Agent (如 Pi) 的设计思想：
1. 双通道结果 (ToolResult)：content 喂给大模型，details 留给前端 UI，is_error 支持自发纠错。
2. 既支持面向对象继承 BaseTool，也支持使用 @tool 快速装饰普通 Python 函数。
"""

import inspect
import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, get_type_hints


@dataclass
class ToolResult:
    """工具执行结果的统一包装。
    
    属性：
        content: 真正返回给大模型的文本内容 (字符串)。
        is_error: 标记该次调用是否发生错误 (模型可根据错误信息自我修复)。
        details: 结构化元数据 (供 CLI / UI 展示，不占用大模型的上下文 Token)。
    """
    content: str
    is_error: bool = False
    details: Optional[Dict[str, Any]] = None

    def __str__(self) -> str:
        return self.content


# Python 类型到 JSON Schema 类型的简单映射
PYTHON_TYPE_TO_JSON_SCHEMA = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
}


class BaseTool(ABC):
    """所有工具的抽象基类。
    
    子类需要实现：
    - name: 工具英文名称 (如 read_file)
    - description: 工具功能描述 (告诉模型何时使用)
    - get_schema(): 返回 OpenAI 规范的 JSON Schema 参数定义
    - execute(**kwargs): 异步执行逻辑
    """
    name: str
    description: str

    @abstractmethod
    def get_schema(self) -> Dict[str, Any]:
        """获取工具对应的 OpenAI Function Calling JSON Schema"""
        pass

    @abstractmethod
    async def execute(self, **kwargs: Any) -> ToolResult:
        """执行工具的核心逻辑，返回 ToolResult 对象"""
        pass

    def _normalize_result(self, result: Any) -> ToolResult:
        """辅助方法：将任意返回值自动包装为 ToolResult"""
        if isinstance(result, ToolResult):
            return result
        elif isinstance(result, str):
            return ToolResult(content=result, is_error=False)
        else:
            return ToolResult(content=str(result), is_error=False)


class FunctionTool(BaseTool):
    """通过普通 Python 函数包装而成的工具对象。"""

    def __init__(self, func: Callable, name: Optional[str] = None, description: Optional[str] = None):
        self.func = func
        self.name = name or func.__name__
        self.description = description or (func.__doc__ or "").strip()
        self._schema = self._build_schema()

    def _build_schema(self) -> Dict[str, Any]:
        """通过 inspect 分析函数签名与类型注解，自动生成 OpenAI JSON Schema"""
        sig = inspect.signature(self.func)
        try:
            hints = get_type_hints(self.func)
        except Exception:
            hints = getattr(self.func, "__annotations__", {})

        properties: Dict[str, Any] = {}
        required: List[str] = []

        for param_name, param in sig.parameters.items():
            # 忽略 *args 与 **kwargs
            if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                continue

            param_type = hints.get(param_name, str)
            json_type = PYTHON_TYPE_TO_JSON_SCHEMA.get(param_type, "string")

            properties[param_name] = {
                "type": json_type,
                "description": f"参数 {param_name}",
            }

            # 如果没有默认值，则是必填项
            if param.default is inspect.Parameter.empty:
                required.append(param_name)

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }

    def get_schema(self) -> Dict[str, Any]:
        return self._schema

    async def execute(self, **kwargs: Any) -> ToolResult:
        """执行底层函数，兼容同步函数与异步协程"""
        try:
            if asyncio.iscoroutinefunction(self.func):
                raw_result = await self.func(**kwargs)
            else:
                raw_result = self.func(**kwargs)
            return self._normalize_result(raw_result)
        except Exception as e:
            # 捕获异常，包装成 is_error=True 的结果，不让程序崩溃
            return ToolResult(
                content=f"Error executing tool '{self.name}': {str(e)}",
                is_error=True,
                details={"exception": str(e)},
            )


def tool(name: Optional[str] = None, description: Optional[str] = None) -> Callable:
    """快捷装饰器：把普通 Python 函数一键变成可调用的 BaseTool。
    
    示例：
        @tool(description="计算两个数的和")
        def add(a: int, b: int) -> int:
            return a + b
    """
    def decorator(func: Callable) -> FunctionTool:
        return FunctionTool(func, name=name, description=description)
    return decorator
