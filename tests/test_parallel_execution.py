import asyncio
import time
import unittest
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple
from mini_agent.ai.types import ModelResponse, ToolCall
from mini_agent.core.context import AgentContext
from mini_agent.core.events import ToolCallStart, ToolResult
from mini_agent.core.loop import agent_loop
from mini_agent.tools.base import ToolResult as BaseToolResult, tool
from mini_agent.tools.registry import ToolRegistry


class MockParallelClient:
    """模拟返回多个工具调用的 Client"""

    def __init__(self, tool_calls_list: List[List[ToolCall]]):
        self.tool_calls_list = list(tool_calls_list)
        self.turn = 0
        self.model = "mock-parallel"

    async def stream_chat(
        self, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None
    ) -> AsyncGenerator[Tuple[str, Any], None]:
        if self.turn < len(self.tool_calls_list):
            calls = self.tool_calls_list[self.turn]
            self.turn += 1
            yield (
                "response",
                ModelResponse(
                    content=f"第 {self.turn} 轮模型输出",
                    tool_calls=calls,
                ),
            )
        else:
            yield (
                "response",
                ModelResponse(
                    content="任务全部完成！",
                    tool_calls=[],
                ),
            )


class TestParallelToolExecution(unittest.TestCase):
    def test_parallel_execution_timing_and_ordering(self):
        registry = ToolRegistry()

        @tool(description="模拟耗时工具 A")
        async def slow_tool_a(duration: float = 0.1) -> str:
            await asyncio.sleep(duration)
            return "Result A"

        @tool(description="模拟耗时工具 B")
        async def slow_tool_b(duration: float = 0.1) -> str:
            await asyncio.sleep(duration)
            return "Result B"

        @tool(description="模拟耗时工具 C")
        async def slow_tool_c(duration: float = 0.1) -> str:
            await asyncio.sleep(duration)
            return "Result C"

        registry.register(slow_tool_a)
        registry.register(slow_tool_b)
        registry.register(slow_tool_c)

        calls = [
            ToolCall(id="call_a", name="slow_tool_a", arguments={"duration": 0.1}),
            ToolCall(id="call_b", name="slow_tool_b", arguments={"duration": 0.1}),
            ToolCall(id="call_c", name="slow_tool_c", arguments={"duration": 0.1}),
        ]

        client = MockParallelClient([calls])
        context = AgentContext(system_prompt="test", max_turns=5)
        context.add_user_message("并发运行三个工具")

        async def run_test():
            events = []
            t0 = time.time()
            async for ev in agent_loop(context, client, registry):
                events.append(ev)
            total_time = time.time() - t0
            return events, total_time

        events, elapsed = asyncio.run(run_test())

        # 3 个各 0.1s 的工具并发执行，总耗时应显著小于串行耗时 (0.3s)
        self.assertLess(elapsed, 0.25)

        # 验证所有事件发射完整
        start_events = [e for e in events if isinstance(e, ToolCallStart)]
        result_events = [e for e in events if isinstance(e, ToolResult)]
        self.assertEqual(len(start_events), 3)
        self.assertEqual(len(result_events), 3)

        # 验证上下文中的回填顺序严格保持 call_a, call_b, call_c
        tool_messages = [m for m in context.messages if m.get("role") == "tool"]
        self.assertEqual(len(tool_messages), 3)
        self.assertEqual(tool_messages[0]["tool_call_id"], "call_a")
        self.assertEqual(tool_messages[1]["tool_call_id"], "call_b")
        self.assertEqual(tool_messages[2]["tool_call_id"], "call_c")
        self.assertEqual(tool_messages[0]["content"], "Result A")
        self.assertEqual(tool_messages[1]["content"], "Result B")
        self.assertEqual(tool_messages[2]["content"], "Result C")

    def test_parallel_execution_partial_failure_isolation(self):
        """测试并发执行中某一个工具抛出异常时不崩溃，并隔离报错"""
        registry = ToolRegistry()

        @tool(description="正常工具")
        async def normal_tool() -> str:
            await asyncio.sleep(0.02)
            return "Normal OK"

        @tool(description="异常工具")
        async def failing_tool() -> str:
            await asyncio.sleep(0.01)
            raise RuntimeError("Something exploded!")

        registry.register(normal_tool)
        registry.register(failing_tool)

        calls = [
            ToolCall(id="call_normal", name="normal_tool", arguments={}),
            ToolCall(id="call_fail", name="failing_tool", arguments={}),
        ]

        client = MockParallelClient([calls])
        context = AgentContext(system_prompt="test", max_turns=5)
        context.add_user_message("并发运行正常与异常工具")

        async def run_test():
            events = []
            async for ev in agent_loop(context, client, registry):
                events.append(ev)
            return events

        events = asyncio.run(run_test())
        result_events = [e for e in events if isinstance(e, ToolResult)]
        self.assertEqual(len(result_events), 2)

        normal_res = next(r for r in result_events if r.tool_call_id == "call_normal")
        fail_res = next(r for r in result_events if r.tool_call_id == "call_fail")

        self.assertFalse(normal_res.is_error)
        self.assertEqual(normal_res.output, "Normal OK")

        self.assertTrue(fail_res.is_error)
        self.assertIn("exploded", fail_res.output)

    def test_sync_thread_tool_does_not_block_event_loop(self):
        """测试在工作线程中执行的阻塞 I/O (如 web/grep) 不会霸占事件循环，允许快速工具并发完成"""
        registry = ToolRegistry()

        @tool(description="模拟耗时阻塞 I/O 工具")
        async def blocking_io_tool(duration: float = 0.1) -> str:
            def sync_io():
                time.sleep(duration)
                return "IO Result"
            return await asyncio.to_thread(sync_io)

        @tool(description="极速工具")
        async def fast_tool() -> str:
            await asyncio.sleep(0.01)
            return "Fast Result"

        registry.register(blocking_io_tool)
        registry.register(fast_tool)

        calls = [
            ToolCall(id="call_slow_io", name="blocking_io_tool", arguments={"duration": 0.1}),
            ToolCall(id="call_fast", name="fast_tool", arguments={}),
        ]

        client = MockParallelClient([calls])
        context = AgentContext(system_prompt="test", max_turns=5)
        context.add_user_message("并发运行阻塞 I/O 工具与快速工具")

        async def run_test():
            events = []
            t0 = time.time()
            async for ev in agent_loop(context, client, registry):
                events.append(ev)
            total_time = time.time() - t0
            return events, total_time

        events, elapsed = asyncio.run(run_test())

        # 验证 fast_tool 先于 slow_io 完成并优先抛出结果
        results = [e for e in events if isinstance(e, ToolResult)]
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].tool_call_id, "call_fast")
        self.assertEqual(results[1].tool_call_id, "call_slow_io")
        self.assertLess(elapsed, 0.2)


if __name__ == "__main__":
    unittest.main()


