"""子代理类型定义与模型仲裁器 (Subagent Types & Model Resolver)。

核心能力：
1. SubagentType: 三大核心角色定义 (explore / plan / general)。
2. 工具白名单常量定义 (EXPLORE_TOOLS, PLAN_TOOLS)。
3. resolve_subagent_model: 三级优先级模型仲裁器 (运行时动态 > 用户配置/环境变量 > 默认 deepseek-v4.1 > inherit)。
"""

import os
from enum import Enum
from typing import Dict, Optional, Set


class SubagentType(str, Enum):
    """子代理角色枚举"""
    EXPLORE = "explore"   # 只读探索型 (信息检索/符号索引/文档查询)
    PLAN = "plan"         # 架构规划型 (拓扑分析/方案推演/分步拆解)
    GENERAL = "general"   # 通用执行型 (封闭子任务/独立闭环开发)


# 默认子代理基准模型：默认继承主 Agent 的模型配置 (保证任意 provider 下零 404)
DEFAULT_SUBAGENT_MODEL: str = "inherit"

# 各角色默认单次最大轮数防护配额
DEFAULT_ROLE_MAX_TURNS: Dict[str, int] = {
    "explore": 10,
    "plan": 10,
    "general": 30,
}

# 角色工具白名单定义
EXPLORE_TOOLS: Set[str] = {
    "read_file",
    "grep",
    "glob",
    "web_search",
    "web_fetch",
}

PLAN_TOOLS: Set[str] = {
    "read_file",
    "grep",
    "glob",
    "todo",
}


def resolve_subagent_model(
    agent_type: str,
    requested_model: Optional[str] = None,
    user_presets: Optional[Dict[str, str]] = None,
    parent_model: Optional[str] = None,
) -> str:
    """仲裁子代理实际使用的模型名称。

    优先级：
    1. 主 Agent 运行时动态指定 (requested_model)
    2. 用户字典配置或环境变量 (user_presets / SUBAGENT_{TYPE}_MODEL / SUBAGENT_DEFAULT_MODEL)
    3. 全局默认值 (DEFAULT_SUBAGENT_MODEL: deepseek-v4.1)

    特殊值处理：
    若任何层级指定为 "inherit"，则回退继承主 Agent 的 parent_model。
    """
    normalized_type = (agent_type or "explore").strip().lower()

    # 1. 运行时动态入参 (最高优先)
    if requested_model:
        req = requested_model.strip()
        if req.lower() == "inherit":
            return parent_model or DEFAULT_SUBAGENT_MODEL
        return req

    # 2. 用户字典配置预设
    if user_presets:
        if normalized_type in user_presets and user_presets[normalized_type]:
            preset = user_presets[normalized_type].strip()
            if preset.lower() == "inherit":
                return parent_model or DEFAULT_SUBAGENT_MODEL
            return preset
        if "default" in user_presets and user_presets["default"]:
            preset = user_presets["default"].strip()
            if preset.lower() == "inherit":
                return parent_model or "deepseek-v4.1"
            return preset

    # 3. 环境变量预设
    type_env_key = f"SUBAGENT_{normalized_type.upper()}_MODEL"
    type_env_val = os.getenv(type_env_key)
    if type_env_val:
        val = type_env_val.strip()
        if val.lower() == "inherit":
            return parent_model or "deepseek-v4.1"
        return val

    default_env_val = os.getenv("SUBAGENT_DEFAULT_MODEL")
    if default_env_val:
        val = default_env_val.strip()
        if val.lower() == "inherit":
            return parent_model or "deepseek-v4.1"
        return val

    # 4. 全局默认回退：优先继承主模型，若主模型未就绪则回退到 deepseek-v4.1
    return parent_model or "deepseek-v4.1"

