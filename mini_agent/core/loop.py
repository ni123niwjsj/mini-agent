"""Agent ReAct 核心调度循环 (业务无关内核)。

负责协调：
1. AgentContext (上下文与记忆)
2. LLMClient (大模型思考与流式吐字)
3. ToolRegistry (工具查找与执行)

通过单向事件流 (AsyncGenerator) 依次发射 7 种生命周期事件：
- AgentStart: 任务启动
- AssistantDelta: 模型流式吐字
- AssistantMessage: 本轮模型输出完毕
- ToolCallStart: 触发工具调用
- ToolResult: 工具执行完毕
- AgentEnd: 循环结束
- Error: 异常报错
"""

from typing import Any, AsyncGenerator, Optional
from mini_agent.ai.client import LLMClient
from mini_agent.ai.types import ModelResponse
from mini_agent.core.context import AgentContext
from mini_agent.core.events import (
    AgentEnd,
    AgentStart,
    AssistantDelta,
    AssistantMessage,
    CompactionEnd,
    CompactionStart,
    Error,
    ToolCallStart,
    ToolResult,
)
from mini_agent.core.compaction import perform_compaction
from mini_agent.tools.registry import ToolRegistry


async def agent_loop(
    context: AgentContext,
    llm_client: LLMClient,
    tool_registry: ToolRegistry,
) -> AsyncGenerator[Any, None]:
    """ReAct 核心调度生成器。
    
    外层通过 async for event in agent_loop(...) 即可消费完整的生命周期。
    """
    last_prompt = context.get_last_user_prompt()
    yield AgentStart(user_prompt=last_prompt)

    turn_count = 0

    try:
        while context.max_turns <= 0 or turn_count < context.max_turns:
            turn_count += 1

            # 0. 检查是否触发智能上下文自动压缩 (Auto-Compaction)
            if context.should_auto_compact():
                tokens_before = context.latest_usage.get("prompt_tokens", 0)
                yield CompactionStart(tokens_before=tokens_before)
                c_res = await perform_compaction(context, llm_client)
                if c_res:
                    yield CompactionEnd(
                        tokens_before=c_res["tokens_before"],
                        tokens_after=c_res["tokens_after"],
                        saved_tokens=c_res["saved_tokens"],
                        saved_percent=c_res["saved_percent"],
                        summary=c_res["summary"],
                        details={
                            "read_files": c_res["read_files"],
                            "modified_files": c_res["modified_files"],
                            "compacted_count": c_res["compacted_count"],
                        },
                    )

            # 1. 组装当前上下文与工具清单
            messages = context.get_messages_for_llm()
            tools = tool_registry.get_schemas()

            # 2. 调用大模型，实时流式消费
            response: Optional[ModelResponse] = None
            async for event_type, data in llm_client.stream_chat(messages, tools=tools):
                if event_type == "text_delta":
                    yield AssistantDelta(content=data, is_reasoning=False)
                elif event_type == "reasoning_delta":
                    yield AssistantDelta(content=data, is_reasoning=True)
                elif event_type == "response":
                    response = data

            if response is None:
                yield Error(message="大模型未返回有效推理结果。")
                break

            # 3. 记录模型消耗并广播本轮结束事件
            if response and getattr(response, "usage", None):
                context.record_usage(response.usage)

            yield AssistantMessage(
                content=response.content,
                tool_calls=[
                    {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                    for tc in response.tool_calls
                ],
                usage=response.usage.to_dict() if getattr(response, "usage", None) else None,
            )

            # 4. 把模型回复写入上下文
            context.add_assistant_message(
                content=response.content,
                tool_calls=response.tool_calls,
            )

            # 5. 判断终止条件：如果大模型没有要求调用任何工具，说明任务已搞定，退出！
            if not response.tool_calls:
                yield AgentEnd(
                    final_response=response.content,
                    total_turns=turn_count,
                    usage=context.get_context_stats(),
                )
                return

            # 6. 如果大模型要求调用工具：依次派发执行
            for tc in response.tool_calls:
                # 6.1 广播工具开始执行事件
                yield ToolCallStart(
                    tool_name=tc.name,
                    tool_call_id=tc.id,
                    arguments=tc.arguments,
                )

                # 6.2 在 ToolRegistry 中安全派发执行
                res = await tool_registry.execute(tc.name, tc.arguments)

                # 6.3 广播工具执行结果事件
                yield ToolResult(
                    tool_name=tc.name,
                    tool_call_id=tc.id,
                    output=res.content,
                    is_error=res.is_error,
                )

                # 6.4 将执行结果写回上下文，让模型在下一轮循环看到 (包含多模态附图)
                context.add_tool_result(tc.id, res.content, images=getattr(res, "images", None))

        # 超过最大轮数防御机制 (避免模型死循环烧 Token)
        yield Error(message=f"已达到单次任务最大轮数限制 ({context.max_turns} 轮)。如需继续推进，可使用 /turns 提高限制或直接输入指令继续。")
        yield AgentEnd(
            final_response="任务达到最大轮数限制，已暂停。",
            total_turns=turn_count,
            usage=context.get_context_stats(),
        )

    except Exception as e:
        yield Error(message=f"Agent 运行时发生未捕获异常: {str(e)}", exception=e)
