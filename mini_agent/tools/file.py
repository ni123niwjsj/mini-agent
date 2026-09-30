"""文件读写工具 (ReadFile, WriteFile)。"""

from typing import Any, Dict
from mini_agent.tools.base import BaseTool


class ReadFileTool(BaseTool):
    """读取指定路径文件的工具，支持行号切片"""
    name = "read_file"
    description = "读取本地文件内容，可指定起止行号"

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "文件绝对路径或相对路径"},
                        "start_line": {"type": "integer", "description": "起始行号 (1-indexed)"},
                        "end_line": {"type": "integer", "description": "结束行号 (1-indexed)"},
                    },
                    "required": ["path"],
                },
            },
        }

    async def execute(self, path: str, start_line: int = 1, end_line: int = -1) -> str:
        # 待具体实现
        return f"[read_file]: Reading {path}"


class WriteFileTool(BaseTool):
    """写入文件内容的工具"""
    name = "write_file"
    description = "创建新文件或覆盖写入文件内容"

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "文件路径"},
                        "content": {"type": "string", "description": "写入的文件内容"},
                    },
                    "required": ["path", "content"],
                },
            },
        }

    async def execute(self, path: str, content: str) -> str:
        # 待具体实现
        return f"[write_file]: Written to {path}"
