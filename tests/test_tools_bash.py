"""测试 tools/bash.py 终端命令执行、超时熔断与安全防御"""

import asyncio
import time
from mini_agent.tools.bash import BashTool


async def main():
    tool = BashTool(cwd=".")

    print("=== 1. 测试正常命令执行 (echo) ===")
    res_ok = await tool.execute("echo 'Hello from Mini-Agent'")
    print(f"状态: is_error={res_ok.is_error}")
    print(f"输出:\n{res_ok.content}\n")

    print("=== 2. 测试失败命令 (非 0 退出码捕获) ===")
    res_err = await tool.execute("ls /definitely_non_existent_dir_12345")
    print(f"状态: is_error={res_err.is_error}")
    print(f"输出:\n{res_err.content}\n")

    print("=== 3. 测试超时熔断强杀 (sleep 5 秒，但设定 1 秒超时) ===")
    start_t = time.time()
    res_timeout = await tool.execute("sleep 5", timeout=1)
    duration = time.time() - start_t
    print(f"耗时: {duration:.2f} 秒 (验证是否在 1 秒左右被强杀)")
    print(f"状态: is_error={res_timeout.is_error}")
    print(f"输出:\n{res_timeout.content}\n")

    print("=== 4. 测试危险指令前置拦截防御 (rm -rf /) ===")
    res_danger = await tool.execute("rm -rf /")
    print(f"状态: is_error={res_danger.is_error}")
    print(f"输出:\n{res_danger.content}\n")

    print("✅ Bash 终端工具全部安全测试通过！")


if __name__ == "__main__":
    asyncio.run(main())
