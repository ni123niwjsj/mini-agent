"""终端命令执行工具 (BashTool)。

对标 Pi 的命令执行与安全防护机制：
1. 异步子进程非阻塞执行：基于 asyncio.create_subprocess_shell，保证执行命令时不卡死事件循环。
2. 超时熔断机制：针对死循环 (while true)、交互等待 (read) 或网络卡死，超时后自动 SIGKILL 强杀子进程。
3. 退出码智能捕获与自愈支持：非 0 退出码自动标记 is_error=True，并将 stderr 详细日志反馈给模型引导修正。
4. 输出截断防御：限制最大输出行数与字节数，防止 cat 大日志或 find / 导致上下文 Token 瞬间爆满。
"""

import asyncio
import os
from typing import Any, Dict, Optional
from mini_agent.tools.base import BaseTool, ToolResult

MAX_OUTPUT_LINES = 300
MAX_OUTPUT_BYTES = 40 * 1024  # 40 KB


class BashTool(BaseTool):
    """在指定工作目录下执行 shell 命令"""
    name = "bash"
    description = (
        "在系统终端执行 bash 命令行指令。支持执行测试、运行脚本、git 操作等。"
        "包含超时保护与输出截断，返回 stdout、stderr 及退出码。"
    )

    def __init__(self, cwd: str = "."):
        self.cwd = os.path.abspath(cwd)

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "要执行的 Shell 命令行指令 (如 pytest、git status、ls -la 等)",
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "超时熔断时间 (秒)，默认 60 秒",
                        },
                    },
                    "required": ["command"],
                },
            },
        }

    async def execute(self, command: str, timeout: int = 60) -> ToolResult:
        # 1. 危险指令前置拦截防御
        forbidden_patterns = ["rm -rf /", "rm -rf /*", ":(){ :|:& };:"]
        for pattern in forbidden_patterns:
            if pattern in command:
                return ToolResult(
                    content=f"Error: Command '{command}' was blocked for safety reasons.",
                    is_error=True,
                    details={"error_type": "DangerousCommandBlocked"},
                )

        try:
            # 2. 异步启动子进程 (开启新会话/进程组，便于超时整树强杀)
            env = os.environ.copy()
            for p in [os.path.join(self.cwd, ".venv", "bin"), os.path.expanduser("~/code/我的项目/mini-agent/.venv/bin")]:
                if os.path.exists(p) and p not in env.get("PATH", ""):
                    env["PATH"] = f"{p}:{env.get('PATH', '')}"

            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.cwd,
                env=env,
                start_new_session=True,
            )

            # 3. 超时防护 (wait_for)
            try:
                stdout_data, stderr_data = await asyncio.wait_for(
                    process.communicate(),
                    timeout=float(timeout),
                )
            except asyncio.TimeoutError:
                # 强杀整个进程组 (包含 shell 衍生的所有子命令)，防止孤儿进程后台空转
                try:
                    import signal
                    os.killpg(process.pid, signal.SIGKILL)
                    await process.wait()
                except Exception:
                    pass

                return ToolResult(
                    content=(
                        f"Error: Command timed out after {timeout} seconds.\n"
                        f"Command process tree was forcefully terminated to prevent hanging."
                    ),
                    is_error=True,
                    details={"error_type": "Timeout", "timeout_seconds": timeout},
                )

            # 4. 解码输出
            stdout_str = stdout_data.decode("utf-8", errors="replace")
            stderr_str = stderr_data.decode("utf-8", errors="replace")
            returncode = process.returncode

            # 5. 组装输出文本
            output_parts = []
            if stdout_str:
                output_parts.append(stdout_str)
            if stderr_str:
                output_parts.append(f"[stderr]\n{stderr_str}")

            combined_output = "\n".join(output_parts).strip()
            if not combined_output:
                combined_output = "(Command executed successfully with no output)"

            # 如果非 0 退出，附带退出码说明
            is_error = (returncode != 0)
            if is_error:
                combined_output += f"\n\n[Process exited with non-zero exit code: {returncode}]"

            # 6. 大输出安全截断检查
            lines = combined_output.splitlines(keepends=True)
            truncated = False
            if len(lines) > MAX_OUTPUT_LINES:
                lines = lines[:MAX_OUTPUT_LINES]
                truncated = True

            final_text = "".join(lines)
            if len(final_text.encode("utf-8")) > MAX_OUTPUT_BYTES:
                final_text = final_text[:MAX_OUTPUT_BYTES]
                truncated = True

            if truncated:
                final_text += (
                    f"\n\n[⚠️ 输出已截断: 超过行数或体积限制。"
                    f"如需完整输出，建议将结果输出到文件后查看。]"
                )

            return ToolResult(
                content=final_text,
                is_error=is_error,
                details={
                    "command": command,
                    "returncode": returncode,
                    "is_error": is_error,
                    "truncated": truncated,
                },
            )

        except Exception as e:
            return ToolResult(
                content=f"Error executing command '{command}': {str(e)}",
                is_error=True,
                details={"exception": str(e)},
            )
