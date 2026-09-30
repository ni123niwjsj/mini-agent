"""工具契约与基础定义。"""

from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, Optional


class BaseTool(ABC):
    """所有工具的抽象基类"""
    name: str
    description: str

    @abstractmethod
    def get_schema(self) -> Dict[str, Any]:
        """获取工具对应的 OpenAI Function JSON Schema"""
        pass

    @abstractmethod
    async def execute(self, **kwargs: Any) -> Any:
        """执行工具逻辑"""
        pass


def tool(name: Optional[str] = None, description: Optional[str] = None) -> Callable:
    """快捷装饰器，将普通函数转换为 Tool"""
    def decorator(func: Callable) -> Callable:
        func.__tool_name__ = name or func.__name__
        func.__tool_description__ = description or (func.__doc__ or "")
        return func
    return decorator
