"""统一 LLM 客户端适配器 (兼容 OpenAI 规范)。

核心能力：
1. 统一兼容：支持 OpenAI、DeepSeek、通义千问 (DashScope) 以及本地部署模型 (如 llama.cpp / vLLM)。
2. 流式体验：逐字产出文本增量 (text_delta) 与思考增量 (reasoning_delta)。
3. 流式工具拼接 (Tool Call Accumulation)：将模型流式吐出的小碎片合并为完整 JSON 参数并安全反序列化。
4. 内置 Mock 模式：便于无网络环境与单测断言。
"""

import asyncio
import json
import os
import random
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple
from mini_agent.ai.types import ModelResponse, ToolCall, TokenUsage
from mini_agent.ai.catalog import ModelSpec, infer_context_window, resolve_context_window


def sanitize_proxy_env():
    """自动规范化系统代理环境变量。
    
    解决在 Linux (如 Clash / Mihomo 7897 端口) 下代理协议为 socks:// 时，
    httpx 原生报错 'Unknown scheme for proxy URL' 的问题。
    将其平滑映射为 http:// 混合协议。
    """
    for key in ("all_proxy", "ALL_PROXY", "http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY"):
        val = os.environ.get(key)
        if val and val.startswith("socks://"):
            os.environ[key] = val.replace("socks://", "http://", 1)


class LLMClient:
    """封装大模型网络通信的统一客户端"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        reasoning_effort: Optional[str] = None,
        max_retries: int = 5,
        retry_delay: float = 1.0,
    ):
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "EMPTY")
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL", None)
        self.model = model or os.getenv("MINI_AGENT_MODEL", "gpt-4o")
        self.reasoning_effort = reasoning_effort or os.getenv("REASONING_EFFORT", None)
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._model_specs_cache: Dict[str, int] = {}
        self._specs_list: List[ModelSpec] = []

    def get_context_window(self, model_name: Optional[str] = None) -> int:
        """获取指定模型（或当前激活模型）的上下文窗口上限 (Tokens)"""
        target = model_name or self.model
        return resolve_context_window(target, self._model_specs_cache)

    def clone(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        reasoning_effort: Optional[str] = None,
        max_retries: Optional[int] = None,
        retry_delay: Optional[float] = None,
    ) -> "LLMClient":
        """基于当前配置克隆出一个新的 LLMClient 实例（用于子代理切换特定模型）。"""
        new_client = LLMClient(
            api_key=api_key or self.api_key,
            base_url=base_url or self.base_url,
            model=model or self.model,
            reasoning_effort=self.reasoning_effort if reasoning_effort is None else reasoning_effort,
            max_retries=self.max_retries if max_retries is None else max_retries,
            retry_delay=self.retry_delay if retry_delay is None else retry_delay,
        )
        # 共享已知 specs 缓存以减少重复网络请求
        new_client._model_specs_cache = dict(self._model_specs_cache)
        new_client._specs_list = list(self._specs_list)
        return new_client

    async def get_model_catalog(self, force_refresh: bool = False) -> List[ModelSpec]:
        """动态从 Provider 服务端获取包含上下文规格的模型列表 (GET /v1/models)"""
        if self._specs_list and not force_refresh:
            return self._specs_list

        if self.model == "mock":
            mock_specs = [
                ModelSpec(id="mock", name="Mock Model", context_length=128000),
                ModelSpec(id="deepseek/deepseek-v4-flash", name="DeepSeek V4 Flash", context_length=1000000),
                ModelSpec(id="claude-sonnet-4-6", name="Claude Sonnet 4.6", context_length=1000000),
                ModelSpec(id="gpt-4o", name="GPT-4o", context_length=128000),
                ModelSpec(id="qwen3.6-35b-a3b", name="Qwen 3.6 35B", context_length=262144),
            ]
            self._specs_list = mock_specs
            self._model_specs_cache = {s.id: s.context_length for s in mock_specs}
            return self._specs_list

        try:
            from openai import AsyncOpenAI
            sanitize_proxy_env()
            client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)
            models_page = await client.models.list()
            
            specs: List[ModelSpec] = []
            specs_cache: Dict[str, int] = {}
            for m in models_page.data:
                # 优先提取服务端返回的真实 context_length (CommandCode, OpenRouter 等)
                ctx_len = (
                    getattr(m, "context_length", None)
                    or (getattr(m, "model_extra", None) or {}).get("context_length")
                    or (getattr(m, "model_extra", None) or {}).get("context_window")
                )
                if not ctx_len or not isinstance(ctx_len, int) or ctx_len <= 0:
                    ctx_len = resolve_context_window(m.id)

                m_name = (
                    getattr(m, "name", None)
                    or (getattr(m, "model_extra", None) or {}).get("name")
                    or m.id
                )
                spec = ModelSpec(id=m.id, name=m_name, context_length=ctx_len)
                specs.append(spec)
                specs_cache[m.id] = ctx_len

            # 补充常见推荐模型列表 (确保用户有丰富的可选列表)
            existing_ids = {s.id for s in specs}
            popular_defaults = [
                ("deepseek/deepseek-v4.1-flash", 1000000),
                ("deepseek/deepseek-v4.1-flash-fast", 1000000),
                ("deepseek/deepseek-v4-pro", 1000000),
                ("deepseek-chat", 128000),
                ("deepseek-reasoner", 128000),
                ("claude-3-7-sonnet", 200000),
                ("claude-3-5-sonnet", 200000),
                ("gpt-4o", 128000),
                ("o3-mini", 200000),
                ("gemini-2.0-flash", 1048576),
                ("qwen-plus", 128000),
            ]
            for p_id, p_ctx in popular_defaults:
                if p_id not in existing_ids:
                    spec = ModelSpec(id=p_id, name=p_id, context_length=p_ctx)
                    specs.append(spec)
                    specs_cache[p_id] = p_ctx

            self._specs_list = specs
            self._model_specs_cache = specs_cache
            return specs
        except Exception:
            # 网络异常或接口不通时，优雅降级为当前模型与静态推荐列表
            fallback_len = resolve_context_window(self.model)
            self._model_specs_cache[self.model] = fallback_len
            fallback_specs = [ModelSpec(id=self.model, name=self.model, context_length=fallback_len)]
            for p_id, p_ctx in [
                ("deepseek/deepseek-v4.1-flash", 1000000),
                ("deepseek/deepseek-v4.1-flash-fast", 1000000),
                ("deepseek-chat", 128000),
                ("claude-3-7-sonnet", 200000),
                ("gpt-4o", 128000),
            ]:
                if p_id != self.model:
                    fallback_specs.append(ModelSpec(id=p_id, name=p_id, context_length=p_ctx))
                    self._model_specs_cache[p_id] = p_ctx
            self._specs_list = fallback_specs
            return fallback_specs

    async def list_models(self) -> List[str]:
        """动态从 Provider 服务端获取可用模型 ID 列表"""
        specs = await self.get_model_catalog()
        return [s.id for s in specs]

    async def stream_chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncGenerator[Tuple[str, Any], None]:
        """流式请求大模型。
        
        产出数据格式为元组: (event_type, payload)
        - ("text_delta", "字"): 增量文本 Token
        - ("reasoning_delta", "思考"): 增量思考 Token (若模型支持)
        - ("response", ModelResponse): 本轮模型完整回复与解析后的 ToolCall 列表
        """
        # 如果是 mock 模式或未安装 openai 库时的调试分支
        if self.model == "mock":
            async for event in self._mock_stream(messages, tools):
                yield event
            return

        try:
            from openai import AsyncOpenAI
        except ImportError:
            raise ImportError(
                "未检测到 'openai' 依赖库。请运行 `pip install openai` 安装，"
                "或在测试时将 model 设为 'mock'。"
            )

        sanitize_proxy_env()
        client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)

        # 准备请求参数
        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        # 如果指定了思考强度 (如 low, medium, high)，注入参数
        if self.reasoning_effort:
            kwargs["reasoning_effort"] = self.reasoning_effort
        if tools and len(tools) > 0:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        # 循环重试机制：支持退避与随机抖动 (Exponential Backoff + Jitter)
        full_content = ""
        tool_calls_acc: Dict[int, Dict[str, str]] = {}
        finish_reason = None
        captured_usage: Optional[TokenUsage] = None
        attempt = 0

        while True:
            try:
                response = await client.chat.completions.create(**kwargs)
                full_content = ""
                tool_calls_acc = {}
                finish_reason = None
                captured_usage = None

                async for chunk in response:
                    # 捕获 Token 使用统计 (流式末尾 chunk 携带 usage 信息)
                    usage_obj = getattr(chunk, "usage", None)
                    if usage_obj:
                        p_tok = getattr(usage_obj, "prompt_tokens", 0) or 0
                        c_tok = getattr(usage_obj, "completion_tokens", 0) or 0
                        t_tok = getattr(usage_obj, "total_tokens", 0) or (p_tok + c_tok)
                        cached = 0
                        
                        # 兼容各主流服务商 (OpenAI, DeepSeek, Anthropic 兼容代理)
                        details = getattr(usage_obj, "prompt_tokens_details", None)
                        if details:
                            cached = getattr(details, "cached_tokens", 0) or 0
                        if not cached:
                            cached = getattr(usage_obj, "prompt_cache_hit_tokens", 0) or 0
                        if not cached:
                            cached = getattr(usage_obj, "cache_read_input_tokens", 0) or 0

                        captured_usage = TokenUsage(
                            prompt_tokens=p_tok,
                            completion_tokens=c_tok,
                            total_tokens=t_tok,
                            cached_tokens=cached,
                        )

                    if not chunk.choices:
                        continue

                    choice = chunk.choices[0]
                    delta = choice.delta
                    if choice.finish_reason:
                        finish_reason = choice.finish_reason

                    # 1. 普通文本增量
                    if delta.content:
                        full_content += delta.content
                        yield ("text_delta", delta.content)

                    # 2. 思考链增量 (如 DeepSeek-R1 / Qwen / Claude reasoning)
                    reasoning = getattr(delta, "reasoning_content", None) or getattr(delta, "reasoning", None)
                    if reasoning:
                        yield ("reasoning_delta", reasoning)

                    # 3. 流式工具调用拼装
                    if delta.tool_calls:
                        for tc_chunk in delta.tool_calls:
                            idx = tc_chunk.index
                            if idx not in tool_calls_acc:
                                tool_calls_acc[idx] = {
                                    "id": tc_chunk.id or f"call_{idx}",
                                    "name": tc_chunk.function.name if tc_chunk.function else "",
                                    "arguments_str": "",
                                }
                            else:
                                if tc_chunk.id:
                                    tool_calls_acc[idx]["id"] = tc_chunk.id
                                if tc_chunk.function and tc_chunk.function.name:
                                    tool_calls_acc[idx]["name"] += tc_chunk.function.name

                            if tc_chunk.function and tc_chunk.function.arguments:
                                tool_calls_acc[idx]["arguments_str"] += tc_chunk.function.arguments

                # 成功完成单次完整流式响应
                break
            except Exception as e:
                attempt += 1
                # 检查是否为不可重试的客户端错误 (如 400 Bad Request, 401 Unauthorized, 403 Forbidden, 404 Not Found)
                status_code = getattr(e, "status_code", None)
                if status_code and status_code in (400, 401, 403, 404):
                    raise
                if attempt > self.max_retries:
                    raise
                # 计算退避时间: base_delay * 2^(attempt - 1) + jitter
                delay = self.retry_delay * (2 ** (attempt - 1)) + random.uniform(0.1, 0.5)
                await asyncio.sleep(delay)

        # 4. 流式结束，反序列化拼接好的工具参数
        final_tool_calls: List[ToolCall] = []
        for idx in sorted(tool_calls_acc.keys()):
            tc_data = tool_calls_acc[idx]
            args_str = tc_data["arguments_str"]
            try:
                parsed_args = json.loads(args_str) if args_str.strip() else {}
            except json.JSONDecodeError:
                parsed_args = {"raw_arguments": args_str}

            final_tool_calls.append(
                ToolCall(
                    id=tc_data["id"],
                    name=tc_data["name"],
                    arguments=parsed_args,
                )
            )

        # 5. 发射最终汇总结果
        yield (
            "response",
            ModelResponse(
                content=full_content,
                tool_calls=final_tool_calls,
                finish_reason=finish_reason,
                usage=captured_usage,
            ),
        )

    async def _mock_stream(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncGenerator[Tuple[str, Any], None]:
        """内置离线模拟测试流：模拟模型流式吐字并决定调用工具"""
        import asyncio

        mock_usage = TokenUsage(
            prompt_tokens=42,
            completion_tokens=18,
            total_tokens=60,
            cached_tokens=25,
        )

        last_user_msg = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                last_user_msg = m.get("content", "")
                break

        last_msg = messages[-1] if messages else {}
        # 如果上一条消息是工具执行结果 (进入第二轮 ReAct: 观察结果并输出最终结论)
        if last_msg.get("role") == "tool":
            tool_output = last_msg.get("content", "")
            tokens = ["计", "算", "已", "完", "成", "！", "最", "终", "结", "果", "是", "：", str(tool_output)]
            for t in tokens:
                await asyncio.sleep(0.01)
                yield ("text_delta", t)
            yield (
                "response",
                ModelResponse(
                    content="".join(tokens),
                    tool_calls=[],
                    finish_reason="stop",
                    usage=mock_usage,
                ),
            )
            return

        # 如果用户提到了计算或加法，模拟发起工具调用
        if "加" in last_user_msg or "add" in last_user_msg or "计算" in last_user_msg:
            tokens = ["我", "来", "帮", "你", "计", "算", "这", "个", "数", "字", "："]
            for t in tokens:
                await asyncio.sleep(0.01)
                yield ("text_delta", t)

            yield (
                "response",
                ModelResponse(
                    content="".join(tokens),
                    tool_calls=[
                        ToolCall(id="call_mock_001", name="add", arguments={"a": 10, "b": 20})
                    ],
                    finish_reason="tool_calls",
                    usage=mock_usage,
                ),
            )
        else:
            tokens = ["你", "好", "！", "我", "是", " Mini-Agent", "，", "请", "问", "有", "什", "么", "我", "能", "帮", "你", "的", "？"]
            for t in tokens:
                await asyncio.sleep(0.01)
                yield ("text_delta", t)

            yield (
                "response",
                ModelResponse(
                    content="".join(tokens),
                    tool_calls=[],
                    finish_reason="stop",
                    usage=mock_usage,
                ),
            )
