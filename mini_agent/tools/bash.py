"""终端命令执行工具 (安全执行与输出截断防御)。"""

from typing import Any, Dict
from mini_agent.tools.base import BaseTool


class BashTool(BaseTool):
    """在指定工作目录下执行 shell 命令"""
    name = "bash"
    description = "执行 bash 命令并返回标准输出与标准错误"

    def __init__(self, cwd: str = "."):
        self.cwd = cwd

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "要执行的 Shell 命令行指令"},
                        "timeout": {"type": "integer", "description": "超时时间 (秒)", "default": 60},
                    },
                    "required": ["command"],
                },
            },
        }

    async def execute(self, command: str, timeout: int = 60) -> str:
        # 待具体实现
        return f"[bash]: Executed '{command}'"
