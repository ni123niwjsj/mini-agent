"""模型抽象层与协议类型定义。"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ToolCall:
    """标准化的工具调用请求。
    
    属性：
        id: 工具调用的唯一标识 (如 "call_abc123")
        name: 目标工具名 (如 "read_file")
        arguments: 已解析为 Python 字典的参数
    """
    id: str
    name: str
    arguments: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ChatMessage:
    """统一聊天消息定义 (对齐 OpenAI 消息格式)"""
    role: str  # "system" | "user" | "assistant" | "tool"
    content: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = None
    tool_call_id: Optional[str] = None


@dataclass
class ModelResponse:
    """模型单轮推理的最终完整结果"""
    content: str
    tool_calls: List[ToolCall] = field(default_factory=list)
    finish_reason: Optional[str] = None
