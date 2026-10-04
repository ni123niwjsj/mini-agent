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
class TokenUsage:
    """单次大模型调用的 Token 消耗与 Prompt Cache 缓存统计。
    
    属性：
        prompt_tokens: 输入 Tokens
        completion_tokens: 输出 Tokens
        total_tokens: 本轮总 Tokens
        cached_tokens: 命中的上下文缓存 Tokens (DeepSeek / OpenAI Prompt Cache)
    """
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cached_tokens: int = 0

    @property
    def cache_hit_rate(self) -> float:
        """Prompt 缓存命中率 (百分比: 0.0 ~ 100.0)"""
        if self.prompt_tokens <= 0:
            return 0.0
        return round((self.cached_tokens / self.prompt_tokens) * 100, 1)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "cached_tokens": self.cached_tokens,
            "cache_hit_rate": self.cache_hit_rate,
        }


@dataclass
class ModelResponse:
    """模型单轮推理的最终完整结果"""
    content: str
    tool_calls: List[ToolCall] = field(default_factory=list)
    finish_reason: Optional[str] = None
    usage: Optional[TokenUsage] = None
