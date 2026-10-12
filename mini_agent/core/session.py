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
        self.current_leaf_id: Optional[str] = None  # 当前活动分支的叶子节点 ID (支持 DAG 树状分支)

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
                "type": "session",
                "version": 2,
                "id": self.current_session_id,
                "timestamp": datetime.now().isoformat(),
                "cwd": self.cwd,
            }
            if self.model:
                header["model"] = self.model
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

    def append_entry(self, entry: Dict[str, Any]) -> str:
        """向当前会话文件单行追加写入一条记录 (Append-Only，自动维护树状 parentId 链条)。
        
        对齐 Pi 的顶层 Envelope 规范与固定键序:
        {"type": "...", "id": "...", "parentId": "...", "timestamp": "...", ...}
        
        Returns:
            str: 当前写入条目的唯一 ID
        """
        self._ensure_header_written()

        entry_type = entry.get("type", "message")
        is_header = entry_type in ("session", "session_header")

        # 构造强有序字典，确保每行前置键名与结构高度对齐统一
        ordered: Dict[str, Any] = {
            "type": entry_type,
        }

        if is_header:
            ordered["version"] = entry.get("version", 2)
            ordered["id"] = entry.get("id") or entry.get("session_id", self.current_session_id)
            ordered["timestamp"] = entry.get("timestamp") or entry.get("created_at") or datetime.now().isoformat()
            ordered["cwd"] = entry.get("cwd", self.cwd)
            if "model" in entry or self.model:
                ordered["model"] = entry.get("model", self.model)
            for k, v in entry.items():
                if k not in ordered and k not in ("session_id", "created_at"):
                    ordered[k] = v
        else:
            entry_id = entry.get("id") or uuid.uuid4().hex[:8]
            parent_id = entry.get("parentId")
            if parent_id is None and "parent_id" in entry:
                parent_id = entry["parent_id"]
            if parent_id is None:
                parent_id = self.current_leaf_id
            ts = entry.get("timestamp") or datetime.now().isoformat()

            ordered["id"] = entry_id
            ordered["parentId"] = parent_id
            ordered["timestamp"] = ts

            for k, v in entry.items():
                if k not in ("type", "id", "parentId", "parent_id", "timestamp"):
                    ordered[k] = v

        file_path = self.current_session_file
        if not file_path:
            return ordered.get("id", "")

        line = json.dumps(ordered, ensure_ascii=False) + "\n"
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(line)
            f.flush()

        # 更新当前活跃分支的叶子指针 (叶子节点前移)
        if not is_header and "id" in ordered:
            self.current_leaf_id = ordered["id"]

        return ordered.get("id", "")

    def append_message(
        self,
        role: str,
        content: Optional[Any] = None,
        tool_calls: Optional[List[Any]] = None,
        tool_call_id: Optional[str] = None,
        reasoning: Optional[str] = None,
        usage: Optional[Dict[str, Any]] = None,
        tool_name: Optional[str] = None,
        is_error: bool = False,
    ) -> str:
        """追加一条消息条目 (对齐 Pi 的标准 Message 协议与 Content Block 体系)。
        
        思考链推理过程 (thinking)、文本内容 (text) 与工具调用 (toolCall) 独立分块存储，
        并内嵌 Token 用量 (usage)，无需产生割裂的多余行。
        """
        if role in ("tool", "toolResult"):
            # 工具执行结果
            content_blocks = []
            if isinstance(content, str):
                content_blocks.append({"type": "text", "text": content})
            elif isinstance(content, list):
                content_blocks = content
            else:
                content_blocks.append({"type": "text", "text": str(content or "")})

            msg_payload = {
                "role": "toolResult",
                "toolCallId": tool_call_id or "",
                "toolName": tool_name or "",
                "content": content_blocks,
                "isError": is_error,
                "timestamp": int(datetime.now().timestamp() * 1000),
            }
        elif role == "assistant":
            content_blocks = []
            # 1. 深度思维链思考块 (对齐 Pi 的 type: 'thinking')
            if reasoning:
                content_blocks.append({
                    "type": "thinking",
                    "thinking": reasoning,
                    "thinkingSignature": "reasoning_content",
                })
            # 2. 文本回答块 (对齐 Pi 的 type: 'text')
            if content:
                content_blocks.append({
                    "type": "text",
                    "text": content,
                })
            # 3. 工具调用块 (对齐 Pi 的 type: 'toolCall')
            if tool_calls:
                for tc in tool_calls:
                    if hasattr(tc, "id"):
                        tc_id = tc.id
                        tc_name = tc.name
                        tc_args = tc.arguments
                    elif isinstance(tc, dict):
                        tc_id = tc.get("id", "")
                        if "function" in tc and isinstance(tc["function"], dict):
                            tc_name = tc["function"].get("name", "")
                            raw_args = tc["function"].get("arguments", {})
                            if isinstance(raw_args, str):
                                try:
                                    tc_args = json.loads(raw_args)
                                except Exception:
                                    tc_args = raw_args
                            else:
                                tc_args = raw_args
                        else:
                            tc_name = tc.get("name", "")
                            tc_args = tc.get("arguments", {})
                    else:
                        tc_id = ""
                        tc_name = ""
                        tc_args = {}

                    content_blocks.append({
                        "type": "toolCall",
                        "id": tc_id,
                        "name": tc_name,
                        "arguments": tc_args,
                    })

            msg_payload = {
                "role": "assistant",
                "content": content_blocks,
            }
            if self.model:
                msg_payload["model"] = self.model
            if usage:
                msg_payload["usage"] = usage
            msg_payload["stopReason"] = "toolUse" if tool_calls else "stop"
            msg_payload["timestamp"] = int(datetime.now().timestamp() * 1000)
        else:
            # 用户或其他消息 (role: "user" / "system")
            content_blocks = []
            if isinstance(content, str):
                content_blocks.append({"type": "text", "text": content})
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict):
                        content_blocks.append(item)
                    else:
                        content_blocks.append({"type": "text", "text": str(item)})
            else:
                content_blocks.append({"type": "text", "text": str(content or "")})

            msg_payload = {
                "role": role,
                "content": content_blocks,
                "timestamp": int(datetime.now().timestamp() * 1000),
            }

        return self.append_entry({
            "type": "message",
            "message": msg_payload,
        })

    def append_usage(self, usage: Dict[str, Any]) -> str:
        """追加一条大模型 Token 用量与缓存统计条目 (兼容性保留)"""
        return self.append_entry({
            "type": "usage",
            "usage": usage,
        })

    def append_model_change(self, provider: str, model_id: str) -> str:
        """追加一条大模型热切换事件 (对齐 Pi 的 type: 'model_change')"""
        return self.append_entry({
            "type": "model_change",
            "provider": provider,
            "modelId": model_id,
            "model_id": model_id,
        })

    def append_compaction(
        self,
        summary: str,
        tokens_before: int = 0,
        tokens_after: int = 0,
        details: Optional[Dict[str, Any]] = None,
    ) -> str:
        """追加一条智能上下文压缩检查点条目 (对齐 Pi 的 type: 'compaction')"""
        return self.append_entry({
            "type": "compaction",
            "summary": summary,
            "tokensBefore": tokens_before,
            "tokensAfter": tokens_after,
            "tokens_before": tokens_before,
            "tokens_after": tokens_after,
            "details": details or {},
        })

    def _load_raw_entries(self, session_id: str) -> Tuple[Dict[str, Any], List[Dict[str, Any]], Dict[str, Dict[str, Any]]]:
        """读取指定会话文件的所有原始条目，并向上向下双向兼容合成 id 与 parent_id/parentId"""
        file_path = self.get_session_file(session_id)
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"会话文件不存在: {file_path}")

        header: Dict[str, Any] = {}
        entries: List[Dict[str, Any]] = []

        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if entry.get("type") in ("session", "session_header"):
                    header = entry
                    hid = entry.get("id") or entry.get("session_id", "")
                    header["id"] = hid
                    header["session_id"] = hid
                    hts = entry.get("timestamp") or entry.get("created_at", "")
                    header["timestamp"] = hts
                    header["created_at"] = hts
                else:
                    entries.append(entry)

        # 兼容旧版未分配 id / parentId 的线性文件，按物理行序串联形成链表
        last_id: Optional[str] = None
        for idx, entry in enumerate(entries):
            if "id" not in entry:
                entry["id"] = f"legacy_{idx:04d}"

            p_id = entry.get("parentId")
            if p_id is None and "parent_id" in entry:
                p_id = entry["parent_id"]
            if p_id is None and idx > 0 and "parentId" not in entry and "parent_id" not in entry:
                p_id = last_id

            entry["parentId"] = p_id
            entry["parent_id"] = p_id
            last_id = entry["id"]

            # 如果是新版 Pi 包装的 message 结构，自动提取扁平属性供外部与测试透明访问
            if "message" in entry and isinstance(entry["message"], dict):
                m = entry["message"]
                raw_role = m.get("role", "user")
                entry["role"] = "tool" if raw_role in ("toolResult", "tool") else raw_role

                if raw_role in ("toolResult", "tool"):
                    entry["tool_call_id"] = m.get("toolCallId") or m.get("tool_call_id", "")
                    entry["tool_name"] = m.get("toolName") or m.get("tool_name", "")
                    entry["is_error"] = bool(m.get("isError") if "isError" in m else m.get("is_error", False))
                    m_content = m.get("content", [])
                    if isinstance(m_content, list):
                        text_parts = [b.get("text", "") for b in m_content if isinstance(b, dict) and b.get("type") == "text"]
                        entry["content"] = "".join(text_parts)
                    else:
                        entry["content"] = str(m_content)
                elif raw_role == "assistant":
                    m_content = m.get("content", [])
                    if isinstance(m_content, list):
                        text_parts = []
                        thinking_parts = []
                        tool_calls = []
                        for b in m_content:
                            if isinstance(b, dict):
                                btype = b.get("type")
                                if btype == "text":
                                    text_parts.append(b.get("text", ""))
                                elif btype == "thinking":
                                    thinking_parts.append(b.get("thinking", ""))
                                elif btype == "toolCall":
                                    args_val = b.get("arguments", {})
                                    args_str = json.dumps(args_val, ensure_ascii=False) if isinstance(args_val, dict) else str(args_val)
                                    tool_calls.append({
                                        "id": b.get("id", ""),
                                        "type": "function",
                                        "function": {
                                            "name": b.get("name", ""),
                                            "arguments": args_str,
                                        },
                                    })
                        entry["content"] = "".join(text_parts)
                        if thinking_parts:
                            entry["reasoning"] = "".join(thinking_parts)
                        if tool_calls:
                            entry["tool_calls"] = tool_calls
                    elif isinstance(m_content, str):
                        entry["content"] = m_content
                else:
                    # 用户/系统消息
                    m_content = m.get("content", [])
                    if isinstance(m_content, list):
                        has_multimodal = any(
                            isinstance(b, dict) and b.get("type") in ("image_url", "image")
                            for b in m_content
                        )
                        if has_multimodal:
                            entry["content"] = m_content
                        else:
                            text_parts = [b.get("text", "") for b in m_content if isinstance(b, dict) and b.get("type") == "text"]
                            entry["content"] = "".join(text_parts) if text_parts else m_content
                    else:
                        entry["content"] = m_content

                if "usage" in m:
                    entry["usage"] = m["usage"]

        entries_by_id = {e["id"]: e for e in entries if "id" in e}
        return header, entries, entries_by_id

    def load_session(
        self,
        session_id: str,
        leaf_id: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """从 .jsonl 文件沿树状拓扑链路恢复会话历史。
        
        Args:
            session_id: 会话标识
            leaf_id: 可选的目标叶子节点 ID。若不指定，默认取会话物理末尾节点。
            
        Returns:
            Tuple[header, messages]: 会话头部元数据和重构后的消息列表
        """
        header, entries, entries_by_id = self._load_raw_entries(session_id)

        clean_id = session_id[:-6] if session_id.endswith(".jsonl") else session_id
        self.current_session_id = clean_id
        if header.get("cwd"):
            self.cwd = header["cwd"]
        if header.get("model"):
            self.model = header["model"]

        if not entries:
            self.current_leaf_id = None
            return header, []

        # 确定起始叶子节点
        target_leaf = leaf_id
        if not target_leaf or target_leaf not in entries_by_id:
            target_leaf = entries[-1]["id"]

        # 沿 parent_id 指针由叶子向上回溯至根节点 (排除被遗弃的废弃分支)
        branch_entries: List[Dict[str, Any]] = []
        curr = target_leaf
        visited = set()
        while curr and curr in entries_by_id and curr not in visited:
            visited.add(curr)
            entry = entries_by_id[curr]
            branch_entries.append(entry)
            if entry.get("type") == "compaction":
                # 遇到检查点摘要，其前方历史已被压缩，终止继续向前回溯
                break
            curr = entry.get("parent_id")

        # 翻转为根到叶的正向时间序列
        branch_entries.reverse()

        messages: List[Dict[str, Any]] = []
        for entry in branch_entries:
            entry_type = entry.get("type")
            if entry_type == "compaction":
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
                msg: Dict[str, Any] = {"role": entry.get("role", "user")}
                if "content" in entry:
                    msg["content"] = entry["content"]
                if entry.get("tool_calls"):
                    msg["tool_calls"] = entry["tool_calls"]
                if entry.get("tool_call_id"):
                    msg["tool_call_id"] = entry["tool_call_id"]
                if entry.get("tool_name"):
                    msg["tool_name"] = entry["tool_name"]
                if entry.get("is_error") is not None:
                    msg["is_error"] = entry["is_error"]
                if entry.get("reasoning"):
                    msg["reasoning"] = entry["reasoning"]
                messages.append(msg)

        # 更新当前活动叶子
        self.current_leaf_id = target_leaf
        return header, messages

    def undo(self) -> Tuple[Optional[str], List[Dict[str, Any]]]:
        """撤销最近一轮交互 (时光倒流，将分支指针回溯到上一轮提问节点之前)。
        
        零文件物理删除！后续新提问将自动由此处生长出新分支，保留前序探索全部历史。
        
        Returns:
            Tuple[new_leaf_id, new_messages]: 新叶子节点 ID 与重构后的消息列表
        """
        if not self.current_session_id:
            return None, []

        header, entries, entries_by_id = self._load_raw_entries(self.current_session_id)
        if not self.current_leaf_id or self.current_leaf_id not in entries_by_id:
            if entries:
                self.current_leaf_id = entries[-1]["id"]
            else:
                return None, []

        # 从当前叶子向上遍历，找到最近的一条 user 消息
        curr = self.current_leaf_id
        target_user_entry: Optional[Dict[str, Any]] = None
        while curr and curr in entries_by_id:
            entry = entries_by_id[curr]
            if entry.get("type") == "message" and entry.get("role") == "user":
                target_user_entry = entry
                break
            curr = entry.get("parent_id")

        if not target_user_entry:
            return None, []  # 未找到可回退的用户提问

        # 新的叶子节点即为该 user 消息的父节点
        new_leaf = target_user_entry.get("parent_id")
        self.current_leaf_id = new_leaf

        # 重新根据 new_leaf 加载消息列表
        _, new_messages = self.load_session(self.current_session_id, leaf_id=new_leaf)
        return new_leaf, new_messages

    def get_tree(self) -> Dict[str, Any]:
        """获取当前会话的完整树状拓扑信息，用于可视化渲染与分支切换"""
        if not self.current_session_id:
            return {"entries": {}, "children_map": {}, "roots": [], "active_leaf_id": None, "active_path_ids": []}

        header, entries, entries_by_id = self._load_raw_entries(self.current_session_id)

        # 收集当前活跃路径上的所有节点 ID
        active_path_ids = set()
        curr = self.current_leaf_id
        while curr and curr in entries_by_id:
            active_path_ids.add(curr)
            curr = entries_by_id[curr].get("parentId") or entries_by_id[curr].get("parent_id")

        children_map: Dict[str, List[str]] = {}
        roots: List[str] = []

        for e in entries:
            e_id = e.get("id")
            if not e_id:
                continue
            p_id = e.get("parentId") or e.get("parent_id")
            if not p_id or p_id not in entries_by_id:
                roots.append(e_id)
            else:
                children_map.setdefault(p_id, []).append(e_id)

        return {
            "entries": entries_by_id,
            "children_map": children_map,
            "roots": roots,
            "active_leaf_id": self.current_leaf_id,
            "active_path_ids": list(active_path_ids),
        }

    def checkout(self, node_id: str) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """将当前活跃分支指针切换到指定的节点 ID (时光穿梭)"""
        return self.load_session(self.current_session_id, leaf_id=node_id)

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
                        if item_type in ("session_header", "session"):
                            header = item
                        elif item_type == "message":
                            message_count += 1
                            if not first_prompt:
                                role = item.get("role")
                                msg_obj = item.get("message")
                                if not role and isinstance(msg_obj, dict):
                                    role = msg_obj.get("role")
                                if role == "user":
                                    c = item.get("content")
                                    if not c and isinstance(msg_obj, dict):
                                        c = msg_obj.get("content")
                                    if isinstance(c, list):
                                        text_parts = [p.get("text", "") for p in c if isinstance(p, dict) and p.get("type") == "text"]
                                        first_prompt = " ".join(text_parts)
                                    else:
                                        first_prompt = str(c or "")
                            if "timestamp" in item:
                                last_timestamp = item["timestamp"]

                created_at = header.get("created_at") or header.get("timestamp") or datetime.fromtimestamp(
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
