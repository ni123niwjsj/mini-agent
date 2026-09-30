"""统一 LLM 客户端适配器 (兼容 OpenAI 规范)。"""

from typing import Any, AsyncGenerator, Dict, List, Optional
from mini_agent.ai.types import ModelResponse


class LLMClient:
    """封装与大模型的通信，支持流式传输与 Function Calling。"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: str = "gpt-4o",
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model

    async def stream_chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncGenerator[Any, None]:
        """流式请求大模型，产出 token 增量或工具调用信息。"""
        # 待具体实现
        if False:
            yield None
