"""Agent 上下文与会话状态管理 (AgentContext)。

负责保存多轮对话历史、系统提示词以及将消息格式化为符合 OpenAI 规范的格式。
"""

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from mini_agent.ai.types import ToolCall


@dataclass
class AgentContext:
    """保存会话上下文、历史消息与运行时状态"""
    messages: List[Dict[str, Any]] = field(default_factory=list)
    system_prompt: str = ""
    max_turns: int = 15  # 单次任务最大允许的思考与工具调用轮数

    def get_messages_for_llm(self) -> List[Dict[str, Any]]:
        """组装完整的消息列表发给大模型（包含 System Prompt）"""
        formatted_messages = []
        if self.system_prompt:
            formatted_messages.append({"role": "system", "content": self.system_prompt})
        formatted_messages.extend(self.messages)
        return formatted_messages

    def add_user_message(self, content: str) -> None:
        """添加用户提问"""
        self.messages.append({"role": "user", "content": content})

    def add_assistant_message(
        self,
        content: str,
        tool_calls: Optional[List[ToolCall]] = None,
    ) -> None:
        """添加 Assistant 回复（可附带工具调用请求）"""
        msg: Dict[str, Any] = {"role": "assistant", "content": content or ""}
        if tool_calls and len(tool_calls) > 0:
            msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments, ensure_ascii=False)
                        if isinstance(tc.arguments, dict)
                        else str(tc.arguments),
                    },
                }
                for tc in tool_calls
            ]
        self.messages.append(msg)

    def add_tool_result(self, tool_call_id: str, output: str) -> None:
        """记录工具执行的返回结果"""
        self.messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": output,
        })

    def get_last_user_prompt(self) -> str:
        """获取最后一条用户提问内容"""
        for m in reversed(self.messages):
            if m.get("role") == "user":
                return m.get("content", "")
        return ""
