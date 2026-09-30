"""Python 函数及类型注解转 JSON Schema 工具声明。"""

from typing import Any, Callable, Dict


def function_to_json_schema(func: Callable) -> Dict[str, Any]:
    """将 Python 函数解析为其对应的 OpenAI Function Calling JSON Schema。"""
    # 待具体实现
    return {
        "type": "function",
        "function": {
            "name": func.__name__,
            "description": func.__doc__ or "",
            "parameters": {"type": "object", "properties": {}},
        },
    }
