"""任务规划与进度跟踪工具 (TodoTool)。

赋能 Agent 在执行多步骤、复杂编码重构任务时进行显式计划制定与进度跟踪。
支持操作:
- add: 添加待办任务 (task: str)
- update: 更新任务状态 (task_id: int, status: 'pending'|'in_progress'|'completed'|'cancelled', task: Optional[str])
- list: 查看当前所有任务及进度
- clear: 清空当前任务清单
"""

import json
import os
from typing import Any, Dict, List, Optional
from mini_agent.tools.base import BaseTool, ToolResult


class TodoTool(BaseTool):
    """任务规划与进度跟踪工具 (Todo List)"""
    name = "todo"
    description = (
        "管理任务规划清单与进度跟踪 (Todo List)。用于在执行多步骤或复杂任务时显式拆解计划并跟踪进展。"
        "支持动作: "
        "'add' (添加待办任务，需传入 task 描述), "
        "'update' (更新任务状态或描述，需传入 task_id 和 status: pending/in_progress/completed/cancelled), "
        "'list' (查看当前任务清单与完成度), "
        "'clear' (清空任务清单)。"
    )

    def __init__(self, storage_file: Optional[str] = None):
        self.storage_file = os.path.abspath(storage_file) if storage_file else None
        self._todos: List[Dict[str, Any]] = []
        self._next_id: int = 1
        if self.storage_file:
            self._load()

    def set_storage_file(self, storage_file: Optional[str]) -> None:
        """动态绑定或重定向持久化文件 (如会话恢复或切换时)"""
        self.storage_file = os.path.abspath(storage_file) if storage_file else None
        self._todos = []
        self._next_id = 1
        if self.storage_file:
            self._load()

    def _load(self) -> None:
        if not self.storage_file or not os.path.exists(self.storage_file):
            return
        try:
            with open(self.storage_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    self._todos = data
                    max_id = max((t.get("id", 0) for t in self._todos), default=0)
                    self._next_id = max_id + 1
        except Exception:
            pass

    def _save(self) -> None:
        if not self.storage_file:
            return
        try:
            os.makedirs(os.path.dirname(self.storage_file), exist_ok=True)
            with open(self.storage_file, "w", encoding="utf-8") as f:
                json.dump(self._todos, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["add", "update", "list", "clear"],
                            "description": "执行动作: 'add', 'update', 'list', 'clear'",
                        },
                        "task": {
                            "type": "string",
                            "description": "任务描述 (add 动作必填，或 update 动作修改文本时使用)",
                        },
                        "task_id": {
                            "type": "integer",
                            "description": "任务编号 ID (update 动作必填)",
                        },
                        "status": {
                            "type": "string",
                            "enum": ["pending", "in_progress", "completed", "cancelled"],
                            "description": "任务新状态 (update 动作时使用: pending/in_progress/completed/cancelled)",
                        },
                    },
                    "required": ["action"],
                },
            },
        }

    async def execute(
        self,
        action: str,
        task: Optional[str] = None,
        task_id: Optional[int] = None,
        status: Optional[str] = None,
        **kwargs: Any,
    ) -> ToolResult:
        action = (action or "").strip().lower()

        if action == "add":
            if not task or not task.strip():
                return ToolResult(
                    content="错误: 'add' 动作必须提供 'task' 任务描述参数。",
                    is_error=True,
                )
            new_item = {
                "id": self._next_id,
                "task": task.strip(),
                "status": status if status in ("pending", "in_progress", "completed", "cancelled") else "pending",
            }
            self._next_id += 1
            self._todos.append(new_item)
            self._save()
            return ToolResult(
                content=f"✔ 已添加任务 #{new_item['id']}: {new_item['task']}\n\n{self._format_todos()}",
                is_error=False,
                details={"action": "add", "item": new_item, "todos": list(self._todos)},
            )

        elif action == "update":
            if task_id is None:
                return ToolResult(
                    content="错误: 'update' 动作必须提供 'task_id' 任务编号。",
                    is_error=True,
                )
            target = next((t for t in self._todos if t["id"] == task_id), None)
            if not target:
                return ToolResult(
                    content=f"错误: 未找到编号为 #{task_id} 的任务。当前任务列表:\n{self._format_todos()}",
                    is_error=True,
                )
            if status:
                valid_statuses = ("pending", "in_progress", "completed", "cancelled")
                if status not in valid_statuses:
                    return ToolResult(
                        content=f"错误: 非法状态 '{status}'。可用状态: {valid_statuses}",
                        is_error=True,
                    )
                target["status"] = status
            if task and task.strip():
                target["task"] = task.strip()

            self._save()
            return ToolResult(
                content=f"✔ 已更新任务 #{task_id} 状态为 [{target['status']}]\n\n{self._format_todos()}",
                is_error=False,
                details={"action": "update", "item": target, "todos": list(self._todos)},
            )

        elif action == "list":
            return ToolResult(
                content=self._format_todos(),
                is_error=False,
                details={"action": "list", "todos": list(self._todos)},
            )

        elif action == "clear":
            count = len(self._todos)
            self._todos.clear()
            self._next_id = 1
            self._save()
            return ToolResult(
                content=f"✔ 已清空任务清单 (共清除 {count} 项)。",
                is_error=False,
                details={"action": "clear", "todos": []},
            )

        else:
            return ToolResult(
                content=f"错误: 未知动作 '{action}'。有效动作为: 'add', 'update', 'list', 'clear'。",
                is_error=True,
            )

    def _format_todos(self) -> str:
        if not self._todos:
            return "📋 当前暂无任务待办项 (使用 action='add' 添加新任务)。"

        total = len(self._todos)
        completed = sum(1 for t in self._todos if t["status"] == "completed")
        in_progress = sum(1 for t in self._todos if t["status"] == "in_progress")
        pending = sum(1 for t in self._todos if t["status"] == "pending")

        status_symbols = {
            "completed": "[✔]",
            "in_progress": "[▶]",
            "pending": "[ ]",
            "cancelled": "[✖]",
        }

        lines = [f"📋 任务清单 (共 {total} 项, {completed} 已完成, {in_progress} 进行中, {pending} 待处理):"]
        for t in self._todos:
            sym = status_symbols.get(t["status"], "[ ]")
            lines.append(f"  {sym} #{t['id']}: {t['task']} ({t['status']})")

        return "\n".join(lines)
