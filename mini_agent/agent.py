"""Agent 组装门面类 (Facade)。

负责组装 LLMClient、ToolRegistry、AgentContext 并发起循环。
保持极简，不堆砌业务逻辑。
"""

import os
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional, Tuple, Union
from mini_agent.ai.client import LLMClient
from mini_agent.core.context import AgentContext
from mini_agent.core.loop import agent_loop
from mini_agent.core.session import SessionManager
from mini_agent.tools.base import BaseTool, tool
from mini_agent.tools.registry import ToolRegistry
from mini_agent.tools.file import ReadFileTool, WriteFileTool
from mini_agent.tools.edit import EditFileTool
from mini_agent.tools.bash import BashTool
from mini_agent.tools.todo import TodoTool
from mini_agent.tools.search import GrepTool, GlobTool
from mini_agent.core.instructions import build_system_prompt


@tool(description="计算两数相加")
def add(a: int, b: int) -> int:
    """加法辅助计算工具"""
    return a + b


class MiniAgent:
    """轻量 Coding Agent 门面类"""

    def __init__(
        self,
        client: Optional[LLMClient] = None,
        system_prompt: Optional[str] = None,
        workspace_dir: str = ".",
        sessions_dir: Optional[str] = ".sessions",
        session_id: Optional[str] = None,
        max_turns: Optional[int] = None,
        auto_compact_threshold: Optional[float] = None,
    ):
        self.workspace_dir = os.path.abspath(workspace_dir)
        self.client = client or LLMClient()
        
        # 初始化 SessionManager (若 sessions_dir 为 None 则禁用持久化)
        if sessions_dir is not None:
            self.session_manager: Optional[SessionManager] = SessionManager(
                storage_dir=sessions_dir,
                session_id=session_id,
                cwd=self.workspace_dir,
                model=getattr(self.client, "model", ""),
            )
        else:
            self.session_manager = None

        prompt = system_prompt or build_system_prompt(self.workspace_dir)
        initial_context_window = self.client.get_context_window(self.client.model)
        context_kwargs: Dict[str, Any] = {
            "system_prompt": prompt,
            "session_manager": self.session_manager,
            "context_window": initial_context_window,
        }
        if max_turns is not None:
            context_kwargs["max_turns"] = max_turns
        if auto_compact_threshold is not None:
            context_kwargs["auto_compact_threshold"] = auto_compact_threshold

        self.context = AgentContext(**context_kwargs)

        self.registry = ToolRegistry()
        self._register_default_tools(self.workspace_dir)

        # 如果指定了已存在会话，则加载历史消息
        if self.session_manager and session_id:
            session_file = self.session_manager.get_session_file(session_id)
            if os.path.exists(session_file):
                self.load_session(session_id)

    @property
    def current_session_id(self) -> Optional[str]:
        """获取当前活跃的会话 ID"""
        return self.session_manager.current_session_id if self.session_manager else None

    def new_session(self, session_id: Optional[str] = None) -> str:
        """开启全新会话并清空当前上下文"""
        self.context.clear()
        if self.session_manager:
            sid = self.session_manager.create_session(
                session_id=session_id,
                cwd=self.workspace_dir,
                model=getattr(self.client, "model", ""),
            )
            todo_tool = self.registry.get("todo")
            if isinstance(todo_tool, TodoTool):
                todo_tool.set_storage_file(
                    os.path.join(self.session_manager.storage_dir, f"{sid}.todo.json")
                )
            return sid
        return ""

    def load_session(self, session_id: str) -> Tuple[Dict[str, Any], int]:
        """恢复指定历史会话到当前上下文。
        
        Returns:
            Tuple[header, message_count]: 会话元数据与恢复的消息条数
        """
        if not self.session_manager:
            raise RuntimeError("未启用 SessionManager 持久化管理器")

        header, messages = self.session_manager.load_session(session_id)
        self.context.load_messages(messages)
        todo_tool = self.registry.get("todo")
        if isinstance(todo_tool, TodoTool):
            todo_tool.set_storage_file(
                os.path.join(self.session_manager.storage_dir, f"{session_id}.todo.json")
            )
        return header, len(messages)

    def list_sessions(self) -> List[Dict[str, Any]]:
        """获取所有历史会话概要列表"""
        if not self.session_manager:
            return []
        return self.session_manager.list_sessions()

    def undo(self) -> Tuple[Optional[str], int]:
        """撤销最近一轮交互 (时光倒流，将分支指针回溯到上一轮提问节点之前)。
        
        Returns:
            Tuple[new_leaf_id, message_count]: 新的叶子节点 ID 与重构后的消息条数
        """
        if not self.session_manager:
            raise RuntimeError("未启用 SessionManager 持久化管理器")

        new_leaf, messages = self.session_manager.undo()
        self.context.load_messages(messages)
        return new_leaf, len(messages)

    def get_session_tree(self) -> Dict[str, Any]:
        """获取当前会话的完整树状拓扑图"""
        if not self.session_manager:
            return {}
        try:
            return self.session_manager.get_tree()
        except FileNotFoundError:
            return {"entries": {}, "children_map": {}, "roots": [], "active_leaf_id": None}

    def checkout(self, node_id: str) -> Tuple[Dict[str, Any], int]:
        """将当前活跃分支指针切换到指定的节点 ID (时光穿梭)"""
        if not self.session_manager:
            raise RuntimeError("未启用 SessionManager 持久化管理器")

        header, messages = self.session_manager.checkout(node_id)
        self.context.load_messages(messages)
        return header, len(messages)

    def _register_default_tools(self, workspace_dir: str) -> None:
        """注册默认基础工具集"""
        self.registry.register(add)
        self.registry.register(ReadFileTool(workspace_dir=workspace_dir))
        self.registry.register(WriteFileTool(workspace_dir=workspace_dir))
        self.registry.register(EditFileTool(workspace_dir=workspace_dir))
        self.registry.register(BashTool(cwd=workspace_dir))
        self.registry.register(GrepTool(workspace_dir=workspace_dir))
        self.registry.register(GlobTool(workspace_dir=workspace_dir))

        todo_storage = None
        if self.session_manager and self.session_manager.current_session_id:
            todo_storage = os.path.join(
                self.session_manager.storage_dir,
                f"{self.session_manager.current_session_id}.todo.json",
            )
        self.registry.register(TodoTool(storage_file=todo_storage))

    def register_tool(self, tool_or_func: Union[BaseTool, Callable]) -> None:
        """供用户自定义挂载新工具"""
        self.registry.register(tool_or_func)

    async def stream(
        self,
        prompt: Union[str, List[Dict[str, Any]]],
        images: Optional[List[Dict[str, str]]] = None,
        steering_queue: Optional[Any] = None,
    ) -> AsyncGenerator[Any, None]:
        """流式运行任务并返回事件流 (支持纯文本与多模态图文输入，以及实时动态任务引导)"""
        self.context.add_user_message(prompt, images=images)
        async for event in agent_loop(
            self.context,
            self.client,
            self.registry,
            steering_queue=steering_queue,
        ):
            yield event

    async def compact(self, keep_recent_turns: int = 2) -> Optional[Dict[str, Any]]:
        """手动对当前 Agent 上下文执行原子压缩"""
        from mini_agent.core.compaction import perform_compaction
        return await perform_compaction(self.context, self.client, keep_recent_turns=keep_recent_turns)
