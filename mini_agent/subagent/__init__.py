"""Mini-Agent 自代理 (Subagent) 子系统。

提供三剑客角色 (Explore, Plan, General) 权限隔离与模型调度支持。
"""

from mini_agent.subagent.types import (
    DEFAULT_ROLE_MAX_TURNS,
    DEFAULT_SUBAGENT_MODEL,
    EXPLORE_TOOLS,
    PLAN_TOOLS,
    SubagentType,
    resolve_subagent_model,
)
from mini_agent.subagent.prompts import (
    build_explore_prompt,
    build_plan_prompt,
    build_general_prompt,
    get_subagent_prompt,
)
from mini_agent.subagent.registry import create_subagent_registry, get_allowed_tool_names
from mini_agent.subagent.task import TaskTool

__all__ = [
    "SubagentType",
    "DEFAULT_SUBAGENT_MODEL",
    "DEFAULT_ROLE_MAX_TURNS",
    "EXPLORE_TOOLS",
    "PLAN_TOOLS",
    "resolve_subagent_model",
    "build_explore_prompt",
    "build_plan_prompt",
    "build_general_prompt",
    "get_subagent_prompt",
    "create_subagent_registry",
    "get_allowed_tool_names",
    "TaskTool",
]

