"""测试 core/loop.py 完整的 ReAct 调度循环、生命周期事件与最大轮数限制"""

import unittest
from mini_agent.agent import MiniAgent
from mini_agent.ai.client import LLMClient
from mini_agent.core.context import AgentContext
from mini_agent.core.loop import agent_loop
from mini_agent.core.events import (
    AgentStart,
    AssistantDelta,
    AssistantMessage,
    ToolCallStart,
    ToolResult,
    AgentEnd,
    Error,
)
from mini_agent.tools.base import tool
from mini_agent.tools.registry import ToolRegistry


@tool(description="计算两数相加")
def add(a: int, b: int) -> int:
    return a + b


class TestCoreLoop(unittest.IsolatedAsyncioTestCase):
    """测试核心调度循环与生命周期"""

    async def test_agent_loop_success(self):
        registry = ToolRegistry()
        registry.register(add)

        client = LLMClient(model="mock")
        context = AgentContext(system_prompt="你是一个全能助手。")
        context.add_user_message("请帮我计算加法：10 + 20")

        events = []
        async for event in agent_loop(context, client, registry):
            events.append(event)

        # 验证发射的核心事件类型
        event_types = [type(e) for e in events]
        self.assertIn(AgentStart, event_types)
        self.assertIn(AssistantDelta, event_types)
        self.assertIn(AssistantMessage, event_types)
        self.assertIn(ToolCallStart, event_types)
        self.assertIn(ToolResult, event_types)
        self.assertIn(AgentEnd, event_types)

        end_event = next(e for e in events if isinstance(e, AgentEnd))
        self.assertEqual(end_event.total_turns, 2)

    async def test_max_turns_limit(self):
        """测试轮数限制触发保护"""
        registry = ToolRegistry()
        registry.register(add)

        client = LLMClient(model="mock")
        # 将最大轮数设置为 1，而 mock 需要调用工具后第 2 轮才完结
        context = AgentContext(system_prompt="助手", max_turns=1)
        context.add_user_message("加法运算")

        events = []
        async for event in agent_loop(context, client, registry):
            events.append(event)

        errors = [e for e in events if isinstance(e, Error)]
        self.assertTrue(len(errors) > 0)
        self.assertIn("已达到单次任务最大轮数限制", errors[0].message)

    def test_max_turns_configurable(self):
        """测试 max_turns 在 Context 与 MiniAgent 中的可配置性"""
        ctx_default = AgentContext()
        self.assertGreaterEqual(ctx_default.max_turns, 15)

        agent = MiniAgent(sessions_dir=None, max_turns=100)
        self.assertEqual(agent.context.max_turns, 100)

    def test_token_usage_and_cache_hit_rate(self):
        """测试 TokenUsage 数据结构与缓存命中率计算"""
        from mini_agent.ai.types import TokenUsage
        u = TokenUsage(prompt_tokens=100, completion_tokens=20, total_tokens=120, cached_tokens=80)
        self.assertEqual(u.cache_hit_rate, 80.0)

        # 0 prompt tokens 场景防除零
        u_zero = TokenUsage()
        self.assertEqual(u_zero.cache_hit_rate, 0.0)

    async def test_usage_telemetry_in_loop(self):
        """测试 ReAct 调度循环发射并统计 Token 用量与上下文占用"""
        registry = ToolRegistry()
        registry.register(add)

        client = LLMClient(model="mock")
        context = AgentContext(system_prompt="助手", context_window=100000)
        context.add_user_message("计算 10 + 20")

        events = []
        async for event in agent_loop(context, client, registry):
            events.append(event)

        end_events = [e for e in events if isinstance(e, AgentEnd)]
        self.assertEqual(len(end_events), 1)
        end_event = end_events[0]
        self.assertIsNotNone(end_event.usage)

        # 验证用量被正确记录在 Context 中
        stats = context.get_context_stats()
        self.assertGreater(stats["cumulative_prompt_tokens"], 0)
        self.assertGreater(stats["cumulative_completion_tokens"], 0)
        self.assertGreater(stats["latest_cache_hit_rate"], 0.0)
        self.assertEqual(stats["context_window"], 100000)

