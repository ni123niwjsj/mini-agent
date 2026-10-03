"""测试 tools/base.py 核心能力"""

import asyncio
from mini_agent.tools.base import tool, ToolResult


# 1. 用 @tool 定义一个简单的测试函数
@tool(description="计算两个数的除法")
def divide(a: int, b: int) -> float:
    return a / b


async def main():
    print("=== 1. 查看自动生成的 OpenAI JSON Schema ===")
    import json
    schema = divide.get_schema()
    print(json.dumps(schema, indent=2, ensure_ascii=False))

    print("\n=== 2. 测试正常调用 (10 / 2) ===")
    result_ok = await divide.execute(a=10, b=2)
    print(f"结果: content='{result_ok.content}', is_error={result_ok.is_error}")

    print("\n=== 3. 测试异常调用 (除以 0 容错捕获) ===")
    result_err = await divide.execute(a=10, b=0)
    print(f"结果: content='{result_err.content}', is_error={result_err.is_error}")


if __name__ == "__main__":
    asyncio.run(main())
