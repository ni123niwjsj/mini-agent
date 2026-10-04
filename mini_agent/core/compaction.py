"""智能上下文压缩核心模块 (Context Compaction)。

参考 Pi 的工业级 Compaction 架构：
1. 文件操作追踪 (File Operations Tracking): 自动扫描历史工具调用，提取 readFiles 与 modifiedFiles。
2. 历史序列化与防爆截断: 将准备压缩的历史消息转为纯文本，并智能截断过长的工具返回值（如超长 read_file 或 bash 终端输出）。
3. 结构化检查点摘要生成 (Checkpoint Summary): 调用大模型，遵循严格的六段式格式输出：
   - ## Goal
   - ## Constraints & Preferences
   - ## Progress (Done / In Progress / Blocked)
   - ## Key Decisions
   - ## Next Steps
   - <read-files> & <modified-files>
4. 原子上下文置换与持久化:
   - 会话日志追加写 {"type": "compaction", "summary": "...", ...}
   - 内存上下文原子瘦身重构为 [System Prompt, 摘要消息, 最近保留的对话]，释放 80%~95% Token 空间。
"""

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from mini_agent.ai.client import LLMClient
from mini_agent.core.context import AgentContext


@dataclass
class FileOperations:
    """会话中的文件操作追踪"""
    read: Set[str] = field(default_factory=set)
    written: Set[str] = field(default_factory=set)
    edited: Set[str] = field(default_factory=set)

    def compute_file_lists(self) -> Tuple[List[str], List[str]]:
        """计算最终的只读文件列表和已修改文件列表"""
        modified = self.edited | self.written
        read_only = sorted([f for f in self.read if f not in modified])
        return read_only, sorted(list(modified))


def extract_file_operations(messages: List[Dict[str, Any]]) -> FileOperations:
    """从消息列表中扫描工具调用提取读写的文件路径"""
    ops = FileOperations()
    for msg in messages:
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                name = tc.get("function", {}).get("name") or tc.get("name", "")
                args_raw = tc.get("function", {}).get("arguments") or tc.get("arguments", {})
                if isinstance(args_raw, str):
                    try:
                        args = json.loads(args_raw)
                    except Exception:
                        args = {}
                else:
                    args = args_raw or {}

                # 提取文件路径参数
                path = args.get("path") or args.get("file_path") or args.get("target_file")
                if not path or not isinstance(path, str):
                    continue

                if name in ("read_file", "read"):
                    ops.read.add(path)
                elif name in ("write_file", "write"):
                    ops.written.add(path)
                elif name in ("edit_file", "replace_file_content", "edit"):
                    ops.edited.add(path)
    return ops


SUMMARIZATION_SYSTEM_PROMPT = (
    "You are an expert context summarization assistant. Your task is to read a conversation "
    "between a user and an AI coding agent, then produce a structured context checkpoint summary "
    "that another LLM will use to continue the work seamlessly.\n\n"
    "Do NOT continue the conversation. Do NOT answer user questions. ONLY output the structured summary."
)

SUMMARIZATION_USER_PROMPT = """The text above is the conversation history to summarize. Create a structured context checkpoint summary following this EXACT format:

## Goal
[What is the user trying to accomplish? Core objectives and tasks.]

## Constraints & Preferences
- [Any specific constraints, requirements, rules, or preferences mentioned by user]
- [Or "(none)" if none were mentioned]

## Progress
### Done
- [x] [Completed tasks and verified changes]

### In Progress
- [ ] [Current active work]

### Blocked
- [Issues, errors, or blockers encountered, if any; otherwise "(none)"]

## Key Decisions
- **[Decision]**: [Brief rationale]

## Next Steps
1. [Ordered list of what should happen next to continue the task]
"""


def serialize_messages_for_summary(messages: List[Dict[str, Any]], max_tool_chars: int = 1500) -> str:
    """将消息列表序列化为带有语义标签的纯文本，避免将巨型工具输出全量发给总结模型"""
    parts: List[str] = []
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")

        if role == "user":
            if isinstance(content, list):
                texts = [p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"]
                has_img = any(isinstance(p, dict) and p.get("type") == "image_url" for p in content)
                img_tag = " [包含附加图像]" if has_img else ""
                parts.append(f"[User]: {' '.join(texts)}{img_tag}")
            else:
                parts.append(f"[User]: {content}")

        elif role == "assistant":
            tc_list = msg.get("tool_calls")
            tc_strs = []
            if tc_list:
                for tc in tc_list:
                    name = tc.get("function", {}).get("name") or tc.get("name", "")
                    args = tc.get("function", {}).get("arguments") or tc.get("arguments", {})
                    tc_strs.append(f"{name}({args})")

            body = content if isinstance(content, str) and content.strip() else ""
            if body:
                parts.append(f"[Assistant]: {body}")
            if tc_strs:
                parts.append(f"[Assistant Tool Calls]: {'; '.join(tc_strs)}")

        elif role == "tool":
            tool_id = msg.get("tool_call_id", "")
            text_str = str(content)
            if len(text_str) > max_tool_chars:
                text_str = text_str[:max_tool_chars] + f"\n... [已截断，省略 {len(text_str) - max_tool_chars} 字符]"
            parts.append(f"[Tool Result ({tool_id})]: {text_str}")

    return "\n\n".join(parts)


async def generate_compaction_summary(
    messages_to_summarize: List[Dict[str, Any]],
    client: LLMClient,
    file_ops: FileOperations,
) -> str:
    """调用大模型生成结构化检查点摘要"""
    conversation_text = serialize_messages_for_summary(messages_to_summarize)
    read_files, modified_files = file_ops.compute_file_lists()

    file_ops_text = ""
    if read_files:
        file_ops_text += "\n\n<read-files>\n" + "\n".join(read_files) + "\n</read-files>"
    if modified_files:
        file_ops_text += "\n\n<modified-files>\n" + "\n".join(modified_files) + "\n</modified-files>"

    prompt = (
        f"<conversation>\n{conversation_text}\n</conversation>"
        f"{file_ops_text}\n\n"
        f"{SUMMARIZATION_USER_PROMPT}"
    )

    summary_messages = [
        {"role": "system", "content": SUMMARIZATION_SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]

    # 单轮获取汇总文本
    full_summary = ""
    async for event_type, data in client.stream_chat(summary_messages):
        if event_type == "text_delta":
            full_summary += data
        elif event_type == "response":
            if not full_summary and data.content:
                full_summary = data.content

    # 如果模型没有输出文件列表，自动追加
    if file_ops_text and "<read-files>" not in full_summary:
        full_summary += file_ops_text

    return full_summary.strip()


async def perform_compaction(
    context: AgentContext,
    client: LLMClient,
    keep_recent_turns: int = 2,
) -> Optional[Dict[str, Any]]:
    """对 AgentContext 进行原子智能压缩 (Compaction)"""
    all_messages = context.messages
    if len(all_messages) < 4:
        return None  # 消息过少，无需压缩

    # 寻找保留最近轮次的分界点 (保留最近 keep_recent_turns 个 user 提问及其后续交互)
    user_indices = [i for i, m in enumerate(all_messages) if m.get("role") == "user"]
    if len(user_indices) <= keep_recent_turns:
        return None

    split_index = user_indices[-keep_recent_turns]
    to_compact = all_messages[:split_index]
    kept_messages = all_messages[split_index:]

    if not to_compact:
        return None

    # 获取压缩前的 Token 计数
    tokens_before = context.latest_usage.get("prompt_tokens", 0)
    if tokens_before <= 0:
        # 估算字符数
        tokens_before = sum(len(str(m.get("content", ""))) for m in to_compact) // 3

    # 1. 提取文件操作状态
    file_ops = extract_file_operations(to_compact)

    # 2. 调用大模型生成摘要
    summary = await generate_compaction_summary(to_compact, client, file_ops)

    read_files, modified_files = file_ops.compute_file_lists()
    details = {
        "read_files": read_files,
        "modified_files": modified_files,
        "compacted_messages_count": len(to_compact),
    }

    # 3. 构造紧凑的新上下文消息
    checkpoint_msg = {
        "role": "user",
        "content": (
            f"📌 [上下文检查点摘要 / Context Checkpoint Summary]\n"
            f"此前对话历史已被结构化压缩，以下是当前任务目标、关键进展与文件状态：\n\n"
            f"{summary}"
        ),
    }
    ack_msg = {
        "role": "assistant",
        "content": "收到，我已完全掌握前文的检查点状态、已完成事项与修改过的文件列表。我将紧接着最新进度继续执行。",
    }

    new_messages = [checkpoint_msg, ack_msg] + kept_messages
    context.messages = new_messages

    # 4. 估算压缩后 Token (摘要 + 应答 + 保留消息)
    summary_tokens = len(summary) // 3 + 100
    kept_tokens = sum(len(str(m.get("content", ""))) for m in kept_messages) // 3
    tokens_after = summary_tokens + kept_tokens

    # 重置即时 prompt_tokens 为压缩后数值，避免误触发
    context.latest_usage["prompt_tokens"] = tokens_after

    # 5. 持久化到会话日志
    if context.session_manager:
        context.session_manager.append_compaction(
            summary=summary,
            tokens_before=tokens_before,
            tokens_after=tokens_after,
            details=details,
        )

    saved_tokens = max(0, tokens_before - tokens_after)
    saved_percent = round((saved_tokens / tokens_before * 100), 1) if tokens_before > 0 else 0.0

    return {
        "summary": summary,
        "tokens_before": tokens_before,
        "tokens_after": tokens_after,
        "saved_tokens": saved_tokens,
        "saved_percent": saved_percent,
        "read_files": read_files,
        "modified_files": modified_files,
        "compacted_count": len(to_compact),
    }
