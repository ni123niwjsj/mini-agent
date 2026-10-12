"""子代理受限工具箱构建器 (Subagent ToolRegistry Factory)。

核心能力：
1. get_allowed_tool_names: 根据角色白名单计算可用工具集合。
2. create_subagent_registry: 派生隔离的受限 ToolRegistry 视图。
3. 铁律防套娃：无论任何角色，均强制剥离 "task" 工具，避免大模型无限递归调用。
"""

from typing import Set
from mini_agent.subagent.types import EXPLORE_TOOLS, PLAN_TOOLS
from mini_agent.tools.registry import ToolRegistry


def get_allowed_tool_names(agent_type: str, all_parent_tools: Set[str]) -> Set[str]:
    """根据子代理角色类型，计算允许加载的工具名集合。

    - explore: 严格只读 (read_file, grep, glob, web_search, web_fetch)
    - plan: 架构规划 (read_file, grep, glob, todo)
    - general: 全部父级工具 (排除 task)
    - 兜底: 默认回退至 explore
    """
    norm = (agent_type or "explore").strip().lower()
    if norm == "explore":
        allowed = set(EXPLORE_TOOLS)
    elif norm == "plan":
        allowed = set(PLAN_TOOLS)
    elif norm == "general":
        allowed = set(all_parent_tools)
    else:
        allowed = set(EXPLORE_TOOLS)

    # 核心安全护栏：无论任何角色，绝对剔除 "task" 工具，禁止递归套娃派发
    allowed.discard("task")
    return allowed


import logging

logger = logging.getLogger(__name__)


def create_subagent_registry(
    parent_registry: ToolRegistry,
    agent_type: str,
) -> ToolRegistry:
    """从父级工具箱派生出符合角色白名单的独立子工具箱。
    
    安全机制：
    1. 剥离 task 工具 (防套娃)；
    2. 对有状态工具 (如 todo) 自动克隆独立内存实例，严禁污染父级待办清单与文件；
    3. 工具箱为空时主动记录警告日志，便于追踪工具缺失。
    """
    sub_registry = ToolRegistry()
    all_parent_names = set(parent_registry.list_tools())
    allowed_names = get_allowed_tool_names(agent_type, all_parent_names)

    for name in allowed_names:
        tool_instance = parent_registry.get(name)
        if tool_instance is not None:
            # 解决有状态工具污染主清单问题 (TodoTool 独立克隆，不共享 storage_file)
            if getattr(tool_instance, "name", "") == "todo":
                from mini_agent.tools.todo import TodoTool
                sub_registry.register(TodoTool(storage_file=None))
            else:
                sub_registry.register(tool_instance)

    if not sub_registry.list_tools():
        logger.warning(
            "子代理角色 '%s' 未能挂载任何可用工具！白名单: %s, 父工具箱: %s",
            agent_type,
            allowed_names,
            list(all_parent_names),
        )

    return sub_registry

