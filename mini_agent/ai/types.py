"""模型抽象层与协议类型定义。"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class ToolCall:
    """标准化的工具调用请求"""
    id: str
    name: str
    arguments: Dict[str, Any]


@dataclass
class ChatMessage:
    """统一聊天消息定义"""
    role: str  # "system" | "user" | "assistant" | "tool"
    content: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = None
    tool_call_id: Optional[str] = None


@dataclass
class ModelResponse:
    """模型单轮推理结果"""
    content: str
    tool_calls: List[ToolCall]
    finish_reason: Optional[str] = None
