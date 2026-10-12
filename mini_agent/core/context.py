"""Agent 上下文与会话状态管理 (AgentContext)。

负责保存多轮对话历史、系统提示词以及将消息格式化为符合 OpenAI 规范的格式。
"""

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union
from mini_agent.ai.types import ToolCall, TokenUsage


@dataclass
class AgentContext:
    """保存会话上下文、历史消息与运行时状态"""
    messages: List[Dict[str, Any]] = field(default_factory=list)
    system_prompt: str = ""
    max_turns: int = field(default_factory=lambda: int(os.getenv("MAX_TURNS", "50")))  # 单次任务最大轮数限制 (<=0 表示无限制)
    context_window: int = field(default_factory=lambda: int(os.getenv("CONTEXT_WINDOW", "128000")))  # 模型上下文窗口上限 (Tokens)
    auto_compact_threshold: float = field(default_factory=lambda: float(os.getenv("AUTO_COMPACT_THRESHOLD", "0.8")))  # 自动压缩阈值 (占窗口比例，如 0.8 表示 80%)
    session_manager: Optional[Any] = None  # 可选的 SessionManager 持久化实例
    
    # 累计用量统计 (累加整个会话的所有调用)
    cumulative_usage: Dict[str, int] = field(default_factory=lambda: {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "cached_tokens": 0,
    })
    # 最近一次调用的用量 (用于精准计算当前完整上下文体积与即时缓存命中率)
    latest_usage: Dict[str, Any] = field(default_factory=lambda: {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "cached_tokens": 0,
        "cache_hit_rate": 0.0,
    })

    def get_messages_for_llm(self) -> List[Dict[str, Any]]:
        """组装符合标准 OpenAI 规范的消息列表发给大模型（包含 System Prompt，过滤内部元数据）"""
        formatted_messages = []
        if self.system_prompt:
            formatted_messages.append({"role": "system", "content": self.system_prompt})
        for m in self.messages:
            role = m.get("role")
            if role == "tool":
                formatted_messages.append({
                    "role": "tool",
                    "tool_call_id": m.get("tool_call_id", ""),
                    "content": m.get("content", ""),
                })
            elif role == "assistant":
                a_msg: Dict[str, Any] = {"role": "assistant", "content": m.get("content") or ""}
                if m.get("tool_calls"):
                    a_msg["tool_calls"] = m["tool_calls"]
                formatted_messages.append(a_msg)
            else:
                formatted_messages.append({
                    "role": role or "user",
                    "content": m.get("content", ""),
                })
        return formatted_messages

    def add_user_message(
        self,
        content: Union[str, List[Dict[str, Any]]],
        images: Optional[List[Dict[str, str]]] = None,
    ) -> None:
        """添加用户提问（支持纯文本或图文多模态数据）"""
        if images and len(images) > 0:
            text_str = content if isinstance(content, str) else ""
            content_parts: List[Dict[str, Any]] = []
            if text_str:
                content_parts.append({"type": "text", "text": text_str})
            for img in images:
                mime_type = img.get("mime_type", "image/png")
                b64 = img.get("data", "")
                content_parts.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{b64}"},
                })
            final_content = content_parts
        else:
            final_content = content

        self.messages.append({"role": "user", "content": final_content})
        if self.session_manager:
            self.session_manager.append_message(role="user", content=final_content)

    def add_assistant_message(
        self,
        content: str,
        tool_calls: Optional[List[ToolCall]] = None,
        reasoning: Optional[str] = None,
        usage: Optional[Dict[str, Any]] = None,
    ) -> None:
        """添加 Assistant 回复（可附带工具调用请求、深度思维链推理过程与 Token 用量）"""
        msg: Dict[str, Any] = {"role": "assistant", "content": content or ""}
        if reasoning:
            msg["reasoning"] = reasoning
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
        if self.session_manager:
            self.session_manager.append_message(
                role="assistant",
                content=content or "",
                tool_calls=msg.get("tool_calls"),
                reasoning=reasoning,
                usage=usage,
            )

    def add_tool_result(
        self,
        tool_call_id: str,
        output: str,
        images: Optional[List[Dict[str, str]]] = None,
        tool_name: Optional[str] = None,
        is_error: bool = False,
    ) -> None:
        """记录工具执行的返回结果 (对齐 Pi 的多模态协议与 toolResult 封装)"""
        self.messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
            "is_error": is_error,
            "content": output,
        })
        if self.session_manager:
            self.session_manager.append_message(
                role="tool",
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                content=output,
                is_error=is_error,
            )

        # 若工具读取到了图像数据，紧随其后追加一条附带图像的 user 消息
        if images and len(images) > 0:
            img_blocks: List[Dict[str, Any]] = [
                {"type": "text", "text": "已附加工具读取到的图像数据："}
            ]
            for img in images:
                mime = img.get("mime_type", "image/png")
                b64 = img.get("data", "")
                img_blocks.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{b64}"},
                })

            self.messages.append({"role": "user", "content": img_blocks})
            if self.session_manager:
                self.session_manager.append_message(role="user", content=img_blocks)

    def load_messages(self, messages: List[Dict[str, Any]]) -> None:
        """从外部（如持久化会话）加载恢复历史消息列表，并智能复原 Token 用量与缓存统计"""
        self.messages = list(messages)
        self._restore_usage_from_messages()

    def _restore_usage_from_messages(self) -> None:
        """从历史消息记录中重建累积与最新 Token 统计指标"""
        cum_prompt = 0
        cum_comp = 0
        cum_total = 0
        cum_cached = 0
        last_usage: Optional[Dict[str, Any]] = None

        for msg in self.messages:
            u = msg.get("usage")
            if isinstance(u, dict):
                p = u.get("prompt_tokens", 0) or 0
                c = u.get("completion_tokens", 0) or 0
                t = u.get("total_tokens", 0) or (p + c)
                cached = u.get("cached_tokens", 0) or 0
                cum_prompt += p
                cum_comp += c
                cum_total += t
                cum_cached += cached
                last_usage = u

        if last_usage:
            self.latest_usage = dict(last_usage)
            self.cumulative_usage = {
                "prompt_tokens": cum_prompt,
                "completion_tokens": cum_comp,
                "total_tokens": cum_total,
                "cached_tokens": cum_cached,
            }
        elif self.messages:
            # 兜底：若旧会话历史未记录 usage，通过消息字符数估算当前上下文大小
            est_tokens = sum(len(str(m.get("content", ""))) for m in self.messages) // 3
            self.latest_usage = {
                "prompt_tokens": est_tokens,
                "completion_tokens": 0,
                "total_tokens": est_tokens,
                "cached_tokens": 0,
                "cache_hit_rate": 0.0,
            }
            self.cumulative_usage = {
                "prompt_tokens": est_tokens,
                "completion_tokens": 0,
                "total_tokens": est_tokens,
                "cached_tokens": 0,
            }

    def record_usage(self, usage: Optional[TokenUsage]) -> None:
        """记录并累加本轮模型的 Token 消耗与缓存情况"""
        if not usage:
            return
        u_dict = usage.to_dict()
        self.latest_usage = u_dict
        self.cumulative_usage["prompt_tokens"] += usage.prompt_tokens
        self.cumulative_usage["completion_tokens"] += usage.completion_tokens
        self.cumulative_usage["total_tokens"] += usage.total_tokens
        self.cumulative_usage["cached_tokens"] += usage.cached_tokens

    def merge_subagent_usage(self, usage_dict: Dict[str, Any]) -> None:
        """合并累加子代理执行所消耗的 Token 用量至当前上下文的全局累计账本中"""
        if not usage_dict or not isinstance(usage_dict, dict):
            return
        p = usage_dict.get("prompt_tokens", 0) or 0
        c = usage_dict.get("completion_tokens", 0) or 0
        t = usage_dict.get("total_tokens", 0) or (p + c)
        cached = usage_dict.get("cached_tokens", 0) or 0
        self.cumulative_usage["prompt_tokens"] += p
        self.cumulative_usage["completion_tokens"] += c
        self.cumulative_usage["total_tokens"] += t
        self.cumulative_usage["cached_tokens"] += cached

    def should_auto_compact(self) -> bool:
        """检查当前上下文是否超过自动压缩阈值 (默认 80% 窗口上限且有足够的历史轮次)"""
        if self.context_window <= 0 or self.auto_compact_threshold <= 0:
            return False

        # 保留最近 2 轮对话，因此必须有至少 3 个 user 提问轮次以及至少 4 条历史消息才值得压缩
        user_indices = [i for i, m in enumerate(self.messages) if m.get("role") == "user"]
        if len(user_indices) <= 2 or len(self.messages) < 4:
            return False

        current_tokens = self.latest_usage.get("prompt_tokens", 0)
        if current_tokens <= 0:
            # 若尚未进行过调用（如刚恢复历史），通过字符数估算 Token
            current_tokens = sum(len(str(m.get("content", ""))) for m in self.messages) // 3

        ratio = current_tokens / self.context_window
        return ratio >= self.auto_compact_threshold

    def get_context_stats(self) -> Dict[str, Any]:
        """获取当前上下文用量与窗口占用百分比"""
        # 最新一轮请求的 prompt_tokens 真实反映当前上下文大小 (System Prompt + 消息历史 + 工具描述)
        current_tokens = self.latest_usage.get("prompt_tokens", 0)
        window = self.context_window
        percent = round((current_tokens / window * 100), 1) if window > 0 else 0.0
        cum_prompt = self.cumulative_usage.get("prompt_tokens", 0)
        cum_cached = self.cumulative_usage.get("cached_tokens", 0)
        cum_hit_rate = round((cum_cached / cum_prompt * 100), 1) if cum_prompt > 0 else 0.0

        return {
            "current_tokens": current_tokens,
            "context_window": window,
            "percent": percent,
            "auto_compact_threshold": self.auto_compact_threshold,
            "latest_cache_hit_rate": self.latest_usage.get("cache_hit_rate", 0.0),
            "latest_cached_tokens": self.latest_usage.get("cached_tokens", 0),
            "cumulative_prompt_tokens": cum_prompt,
            "cumulative_completion_tokens": self.cumulative_usage.get("completion_tokens", 0),
            "cumulative_total_tokens": self.cumulative_usage.get("total_tokens", 0),
            "cumulative_cached_tokens": cum_cached,
            "cumulative_cache_hit_rate": cum_hit_rate,
        }

    def clear(self) -> None:
        """清空当前在内存中的对话历史与临时用量统计"""
        self.messages.clear()
        self.latest_usage = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "cached_tokens": 0,
            "cache_hit_rate": 0.0,
        }
        self.cumulative_usage = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "cached_tokens": 0,
        }

    def get_last_user_prompt(self) -> str:
        """获取最后一条用户提问内容 (兼容纯文本与图文列表)"""
        for m in reversed(self.messages):
            if m.get("role") == "user":
                c = m.get("content", "")
                if isinstance(c, list):
                    text_parts = [p.get("text", "") for p in c if isinstance(p, dict) and p.get("type") == "text"]
                    return " ".join(text_parts)
                return str(c)
        return ""
