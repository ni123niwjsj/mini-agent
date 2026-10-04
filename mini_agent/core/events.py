"""Agent 生命周期事件定义。

包含 7 种核心事件：
- AgentStart: 任务启动
- AssistantDelta: 模型流式增量 Token (可选附带 reasoning)
- AssistantMessage: 本轮模型输出完整消息
- ToolCallStart: 触发工具调用，准备执行
- ToolResult: 工具执行完毕返回结果
- AgentEnd: 循环结束，任务完成
- Error: 异常或错误事件
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class AgentStart:
    """Agent 任务开始事件"""
    user_prompt: str
    session_id: Optional[str] = None


@dataclass
class AssistantDelta:
    """模型流式增量输出事件 (打字机效果)"""
    content: str
    is_reasoning: bool = False  # 若模型输出思维链/思考过程，可置为 True


@dataclass
class AssistantMessage:
    """本轮 Assistant 完整生成完毕事件"""
    content: str
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    usage: Optional[Dict[str, Any]] = None  # 本轮模型推理 Token 与缓存详情


@dataclass
class ToolCallStart:
    """工具开始调用事件"""
    tool_name: str
    tool_call_id: str
    arguments: Dict[str, Any]


@dataclass
class ToolResult:
    """工具执行完成事件"""
    tool_name: str
    tool_call_id: str
    output: Any
    is_error: bool = False


@dataclass
class AgentEnd:
    """Agent 整体运行结束事件"""
    final_response: str
    total_turns: int = 1
    usage: Optional[Dict[str, Any]] = None  # 全局上下文占用与会话累计 Token 用量统计


@dataclass
class CompactionStart:
    """触发上下文压缩事件"""
    tokens_before: int = 0


@dataclass
class CompactionEnd:
    """上下文压缩完成事件"""
    tokens_before: int
    tokens_after: int
    saved_tokens: int
    saved_percent: float
    summary: str
    details: Optional[Dict[str, Any]] = None


@dataclass
class Error:
    """Agent 发生异常或未捕获错误事件"""
    message: str
    exception: Optional[Exception] = None
