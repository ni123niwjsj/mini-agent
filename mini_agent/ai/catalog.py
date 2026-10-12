"""模型规格与上下文窗口推断目录 (Model Catalog & Specs)。

负责维护已知模型的规格参数，并提供动态推断与缓存：
1. ModelSpec: 模型参数描述 (id, name, context_length)。
2. DEFAULT_MODEL_SPECS: 知名主流模型的静态规格库 (防断网保底)。
3. infer_context_window: 根据模型名称后缀规律智能推断 (如 -1m, -32k, gemini, claude)。
4. resolve_context_window: 统筹用户配置 (CONTEXT_WINDOW)、服务端动态规格与静态推断。
"""

import os
import re
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class ModelSpec:
    """模型规格信息"""
    id: str
    name: str = ""
    context_length: int = 128000


# 主流知名模型的基准上下文规格字典 (离线 / 标准 OpenAI 接口兜底)
DEFAULT_MODEL_SPECS: Dict[str, int] = {
    # OpenAI
    "gpt-4o": 128000,
    "gpt-4o-mini": 128000,
    "o1": 200000,
    "o1-mini": 128000,
    "o3-mini": 200000,
    # Anthropic Claude
    "claude-3-5-sonnet": 200000,
    "claude-3-7-sonnet": 200000,
    "claude-3-5-haiku": 200000,
    "claude-3-opus": 200000,
    # Google Gemini
    "gemini-1.5-pro": 2000000,
    "gemini-1.5-flash": 1000000,
    "gemini-2.0-flash": 1048576,
    "gemini-2.0-flash-exp": 1048576,
    "gemini-2.0-pro-exp": 2000000,
    # DeepSeek
    "deepseek-chat": 128000,
    "deepseek-reasoner": 128000,
    "deepseek-v4-flash": 1000000,
    "deepseek-v4-pro": 1000000,
    "deepseek-v4.1": 1000000,
    "deepseekv4.1": 1000000,
    "deepseek-v4.1-flash": 1000000,
    "deepseek-v4.1-flash-fast": 1000000,
    "deepseek/deepseek-v4.1": 1000000,
    "deepseek/deepseek-v4-flash": 1000000,
    "deepseek/deepseek-v4-pro": 1000000,
    "deepseek/deepseek-v4.1-flash": 1000000,
    "deepseek/deepseek-v4.1-flash-fast": 1000000,
    # Qwen (通义千问)
    "qwen-turbo": 128000,
    "qwen-plus": 128000,
    "qwen-max": 128000,
    # Kimi / Moonshot
    "moonshot-v1-8k": 8192,
    "moonshot-v1-32k": 32768,
    "moonshot-v1-128k": 128000,
}


def infer_context_window(model_name: str) -> int:
    """根据模型名称的命名规律启发式推断上下文窗口大小。"""
    name_lower = (model_name or "").lower()

    # 1. 匹配常见的数字后缀标签，如 1m, 500k, 256k, 128k, 64k, 32k, 16k, 8k, 4k
    m_1m = re.search(r"[-_/:](1m|1000k|1048k)\b", name_lower)
    if m_1m or "-1m" in name_lower or "1m" in name_lower or "long" in name_lower or "deepseek-v4" in name_lower or "deepseekv4" in name_lower:
        return 1000000

    m_500k = re.search(r"[-_/:](500k|512k)\b", name_lower)
    if m_500k:
        return 500000

    m_256k = re.search(r"[-_/:](256k|262k)\b", name_lower)
    if m_256k:
        return 262144

    m_200k = re.search(r"[-_/:](200k)\b", name_lower)
    if m_200k:
        return 200000

    m_64k = re.search(r"[-_/:](64k)\b", name_lower)
    if m_64k:
        return 65536

    m_32k = re.search(r"[-_/:](32k)\b", name_lower)
    if m_32k:
        return 32768

    m_16k = re.search(r"[-_/:](16k)\b", name_lower)
    if m_16k:
        return 16384

    m_8k = re.search(r"[-_/:](8k)\b", name_lower)
    if m_8k:
        return 8192

    # 2. 厂商通用规则
    if "gemini" in name_lower:
        return 1000000
    if "claude" in name_lower:
        return 200000

    # 3. 现代 LLM 默认兜底标尺
    return 128000


def resolve_context_window(
    model_name: str,
    specs_cache: Optional[Dict[str, int]] = None,
) -> int:
    """统一解析模型最终的上下文窗口上限。
    
    优先级：
    1. 环境变量 CONTEXT_WINDOW 显式配置 (最高优先级，人工覆盖)
    2. 提供商 API 动态返回的 specs_cache (如 CommandCode / OpenRouter)
    3. 内置的静态已知模型库 DEFAULT_MODEL_SPECS
    4. 命名规则智能启发式推断 infer_context_window
    """
    env_override = os.getenv("CONTEXT_WINDOW")
    if env_override and env_override.strip().isdigit():
        return int(env_override.strip())

    if not model_name:
        return 128000

    clean_name = model_name.strip()

    # 检查动态规格缓存
    if specs_cache and clean_name in specs_cache and specs_cache[clean_name] > 0:
        return specs_cache[clean_name]

    # 去掉提供商前缀 (如 deepseek/deepseek-v4.1-flash -> deepseek-v4.1-flash)
    short_name = clean_name.split("/")[-1]
    if specs_cache and short_name in specs_cache and specs_cache[short_name] > 0:
        return specs_cache[short_name]

    # 检查静态字典 (支持完整名称和去前缀名称)
    if clean_name in DEFAULT_MODEL_SPECS:
        return DEFAULT_MODEL_SPECS[clean_name]
    if short_name in DEFAULT_MODEL_SPECS:
        return DEFAULT_MODEL_SPECS[short_name]
    if short_name in DEFAULT_MODEL_SPECS:
        return DEFAULT_MODEL_SPECS[short_name]

    # 启发式推断
    return infer_context_window(clean_name)
