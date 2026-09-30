"""精准差异编辑工具 (精确字符串替换/Diff Patch)。"""

from typing import Any, Dict
from mini_agent.tools.base import BaseTool


class EditFileTool(BaseTool):
    """精准查找并替换文件内容的工具 (对标 Pi 的 edit-diff)"""
    name = "edit_file"
    description = "通过指定旧文本和新文本，对文件进行精确局部替换"

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
                        "old_str": {"type": "string", "description": "待替换的原始内容 (必须唯一精确匹配)"},
                        "new_str": {"type": "string", "description": "替换后的新内容"},
                    },
                    "required": ["path", "old_str", "new_str"],
                },
            },
        }

    async def execute(self, path: str, old_str: str, new_str: str) -> str:
        # 待具体实现
        return f"[edit_file]: Edited {path}"
