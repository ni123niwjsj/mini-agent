"""Agent 上下文与会话状态管理。"""

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class AgentContext:
    """保存会话上下文、历史消息与运行时状态"""
    messages: List[Dict[str, Any]] = field(default_factory=list)
    system_prompt: str = ""
    max_turns: int = 20

    def add_user_message(self, content: str) -> None:
        self.messages.append({"role": "user", "content": content})

    def add_assistant_message(self, content: str, tool_calls: List[Dict[str, Any]] = None) -> None:
        msg: Dict[str, Any] = {"role": "assistant", "content": content}
        if tool_calls:
            msg["tool_calls"] = tool_calls
        self.messages.append(msg)

    def add_tool_result(self, tool_call_id: str, output: str) -> None:
        self.messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": output,
        })
