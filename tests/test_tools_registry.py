"""测试 tools/registry.py 工具箱核心功能"""

import asyncio
import json
from mini_agent.tools.base import tool
from mini_agent.tools.registry import ToolRegistry


# 定义两个测试工具
@tool(description="计算两个数相加")
def add(a: int, b: int) -> int:
    return a + b


@tool(description="计算两个数相乘")
def multiply(x: int, y: int) -> int:
    return x * y


async def main():
    registry = ToolRegistry()

    print("=== 1. 注册工具 ===")
    registry.register(add)
    registry.register(multiply)
    print(f"已注册的工具清单: {registry.list_tools()}")

    print("\n=== 2. 获取给大模型的 JSON Schema 列表 ===")
    schemas = registry.get_schemas()
    print(f"Schema 数量: {len(schemas)}")
    print(json.dumps(schemas, indent=2, ensure_ascii=False))

    print("\n=== 3. 正常执行工具 (add: a=3, b=5) ===")
    res_ok = await registry.execute("add", {"a": 3, "b": 5})
    print(f"结果: content='{res_ok.content}', is_error={res_ok.is_error}")

    print("\n=== 4. 测试调用不存在的工具 (模拟模型幻觉) ===")
    res_not_found = await registry.execute("search_web", {"query": "hello"})
    print(f"结果: content='{res_not_found.content}', is_error={res_not_found.is_error}")

    print("\n=== 5. 测试传错参数 (模拟模型参数错乱) ===")
    res_bad_args = await registry.execute("add", {"unknown_param": 100})
    print(f"结果: content='{res_bad_args.content}', is_error={res_bad_args.is_error}")


if __name__ == "__main__":
    asyncio.run(main())
