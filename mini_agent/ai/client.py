"""统一 LLM 客户端适配器 (兼容 OpenAI 规范)。

核心能力：
1. 统一兼容：支持 OpenAI、DeepSeek、通义千问 (DashScope) 以及本地部署模型 (如 llama.cpp / vLLM)。
2. 流式体验：逐字产出文本增量 (text_delta) 与思考增量 (reasoning_delta)。
3. 流式工具拼接 (Tool Call Accumulation)：将模型流式吐出的小碎片合并为完整 JSON 参数并安全反序列化。
4. 内置 Mock 模式：便于无网络环境与单测断言。
"""

import json
import os
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple
from mini_agent.ai.types import ModelResponse, ToolCall


class LLMClient:
    """封装大模型网络通信的统一客户端"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: str = "gpt-4o",
    ):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "EMPTY")
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL", None)
        self.model = model

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

        client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)

        # 准备请求参数
        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": True,
        }
        if tools and len(tools) > 0:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        response = await client.chat.completions.create(**kwargs)

        full_content = ""
        # 累积流式工具调用的缓存字典: index -> {"id": ..., "name": ..., "arguments_str": ...}
        tool_calls_acc: Dict[int, Dict[str, str]] = {}
        finish_reason = None

        async for chunk in response:
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

            # 2. 思考链增量 (如 DeepSeek-R1 / Qwen reasoning)
            reasoning = getattr(delta, "reasoning_content", None)
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
            ),
        )

    async def _mock_stream(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncGenerator[Tuple[str, Any], None]:
        """内置离线模拟测试流：模拟模型流式吐字并决定调用工具"""
        import asyncio

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
                ),
            )
