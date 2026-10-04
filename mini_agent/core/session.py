"""会话持久化与管理模块 (SessionManager)。

参考 Pi 的追加写架构 (Append-Only JSONL):
1. 每次交互 (User Message, Assistant Message, Tool Result) 实时单行追加写到 .sessions/<session_id>.jsonl。
2. 异常崩溃、Ctrl+C 或断电时，历史记录零丢失、无文件损坏风险。
3. 支持会话恢复 (Resume)、列表查询 (List)、历史回放。
"""

import json
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


class SessionManager:
    """会话管理器，负责将对话历史持久化为 JSONL 文件"""

    def __init__(
        self,
        storage_dir: str = ".sessions",
        session_id: Optional[str] = None,
        cwd: Optional[str] = None,
        model: str = "",
    ):
        self.storage_dir = os.path.abspath(storage_dir)
        os.makedirs(self.storage_dir, exist_ok=True)
        self.cwd = os.path.abspath(cwd) if cwd else os.getcwd()
        self.model = model

        if session_id:
            # 兼容带 .jsonl 后缀
            clean_id = session_id[:-6] if session_id.endswith(".jsonl") else session_id
            self.current_session_id = clean_id
        else:
            self.current_session_id = self._generate_session_id()

    def _generate_session_id(self) -> str:
        """生成带时间戳和短随机字符串的会话 ID，如 20261004_130000_a1b2c3"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        short_id = uuid.uuid4().hex[:6]
        return f"{timestamp}_{short_id}"

    def get_session_file(self, session_id: str) -> str:
        """获取指定 session_id 对应的 .jsonl 文件绝对路径"""
        clean_id = session_id[:-6] if session_id.endswith(".jsonl") else session_id
        return os.path.join(self.storage_dir, f"{clean_id}.jsonl")

    @property
    def current_session_file(self) -> Optional[str]:
        """获取当前活跃会话的文件路径"""
        if not self.current_session_id:
            return None
        return self.get_session_file(self.current_session_id)

    def _ensure_header_written(self) -> None:
        """确保当前会话的头部元数据已写入文件 (惰性创建，避免生成空会话文件)"""
        if not self.current_session_id:
            self.current_session_id = self._generate_session_id()

        file_path = self.get_session_file(self.current_session_id)
        if not os.path.exists(file_path):
            header = {
                "type": "session_header",
                "session_id": self.current_session_id,
                "created_at": datetime.now().isoformat(),
                "cwd": self.cwd,
                "model": self.model,
                "version": 1,
            }
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(json.dumps(header, ensure_ascii=False) + "\n")
                f.flush()

    def create_session(
        self,
        session_id: Optional[str] = None,
        cwd: Optional[str] = None,
        model: str = "",
        immediate_write: bool = False,
    ) -> str:
        """创建全新会话 ID"""
        new_id = session_id or self._generate_session_id()
        self.current_session_id = new_id
        if cwd:
            self.cwd = os.path.abspath(cwd)
        if model:
            self.model = model

        if immediate_write:
            self._ensure_header_written()

        return new_id

    def append_entry(self, entry: Dict[str, Any]) -> None:
        """向当前会话文件单行追加写入一条记录 (Append-Only)"""
        self._ensure_header_written()

        if "timestamp" not in entry:
            entry["timestamp"] = datetime.now().isoformat()

        file_path = self.current_session_file
        if not file_path:
            return

        line = json.dumps(entry, ensure_ascii=False) + "\n"
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(line)
            f.flush()

    def append_message(
        self,
        role: str,
        content: Optional[str] = None,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        tool_call_id: Optional[str] = None,
    ) -> None:
        """追加一条消息条目"""
        entry: Dict[str, Any] = {
            "type": "message",
            "role": role,
            "content": content if content is not None else "",
        }
        if tool_calls:
            entry["tool_calls"] = tool_calls
        if tool_call_id:
            entry["tool_call_id"] = tool_call_id

        self.append_entry(entry)

    def append_usage(self, usage: Dict[str, Any]) -> None:
        """追加一条大模型 Token 用量与缓存统计条目 (对齐 Pi 的 type: 'usage')"""
        self.append_entry({
            "type": "usage",
            "usage": usage,
        })

    def append_compaction(
        self,
        summary: str,
        tokens_before: int = 0,
        tokens_after: int = 0,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """追加一条智能上下文压缩检查点条目 (对齐 Pi 的 type: 'compaction')"""
        self.append_entry({
            "type": "compaction",
            "summary": summary,
            "tokens_before": tokens_before,
            "tokens_after": tokens_after,
            "details": details or {},
        })

    def load_session(self, session_id: str) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """从 .jsonl 文件恢复会话历史。
        
        Returns:
            Tuple[header, messages]: 会话头部元数据和重构后的消息列表
        """
        file_path = self.get_session_file(session_id)
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"会话文件不存在: {file_path}")

        header: Dict[str, Any] = {}
        messages: List[Dict[str, Any]] = []

        with open(file_path, "r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    # 防御性忽略异常损坏行
                    continue

                entry_type = entry.get("type")
                if entry_type == "session_header":
                    header = entry
                elif entry_type == "compaction":
                    # 遇到压缩检查点，将前面的历史消息重构为 [检查点摘要, 确认消息]
                    summary = entry.get("summary", "")
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
                    messages = [checkpoint_msg, ack_msg]
                elif entry_type == "message":
                    # 重构成符合 AgentContext / OpenAI 的标准字典格式
                    msg: Dict[str, Any] = {"role": entry.get("role", "user")}
                    if "content" in entry:
                        msg["content"] = entry["content"]
                    if "tool_calls" in entry and entry["tool_calls"] is not None:
                        msg["tool_calls"] = entry["tool_calls"]
                    if "tool_call_id" in entry and entry["tool_call_id"] is not None:
                        msg["tool_call_id"] = entry["tool_call_id"]
                    messages.append(msg)

        clean_id = session_id[:-6] if session_id.endswith(".jsonl") else session_id
        self.current_session_id = clean_id
        if header.get("cwd"):
            self.cwd = header["cwd"]
        if header.get("model"):
            self.model = header["model"]

        return header, messages

    def list_sessions(self) -> List[Dict[str, Any]]:
        """获取当前 storage_dir 下的所有历史会话列表"""
        return self.list_sessions_in_dir(self.storage_dir)

    @staticmethod
    def list_sessions_in_dir(storage_dir: str = ".sessions") -> List[Dict[str, Any]]:
        """扫描 storage_dir 获取所有历史会话概要列表，按创建时间倒序排列"""
        sessions: List[Dict[str, Any]] = []
        target_dir = os.path.abspath(storage_dir)
        if not os.path.exists(target_dir):
            return sessions

        for filename in os.listdir(target_dir):
            if not filename.endswith(".jsonl"):
                continue

            file_path = os.path.join(target_dir, filename)
            session_id = filename[:-6]

            header: Dict[str, Any] = {}
            first_prompt = ""
            message_count = 0
            last_timestamp = ""

            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            item = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        item_type = item.get("type")
                        if item_type == "session_header":
                            header = item
                        elif item_type == "message":
                            message_count += 1
                            if not first_prompt and item.get("role") == "user":
                                c = item.get("content", "")
                                if isinstance(c, list):
                                    text_parts = [p.get("text", "") for p in c if isinstance(p, dict) and p.get("type") == "text"]
                                    first_prompt = " ".join(text_parts)
                                else:
                                    first_prompt = str(c)
                            if "timestamp" in item:
                                last_timestamp = item["timestamp"]

                created_at = header.get("created_at") or datetime.fromtimestamp(
                    os.path.getctime(file_path)
                ).isoformat()

                sessions.append({
                    "session_id": session_id,
                    "created_at": created_at,
                    "last_timestamp": last_timestamp or created_at,
                    "cwd": header.get("cwd", ""),
                    "model": header.get("model", ""),
                    "first_prompt": first_prompt.strip().replace("\n", " ")[:60],
                    "message_count": message_count,
                    "file_size": os.path.getsize(file_path),
                })
            except Exception:
                continue

        # 按创建时间倒序排序 (最新在前)
        sessions.sort(key=lambda s: s.get("created_at", ""), reverse=True)
        return sessions
