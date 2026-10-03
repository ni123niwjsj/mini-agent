"""精准差异编辑工具 (EditFileTool)。

对标 Cursor、Claude Code 与 Pi 的精准编辑算法 (Exact Match Diff Patch)：
1. 唯一性严格校验：old_str 在原文件中必须唯一匹配 (count == 1)。
   - 若为 0：报错提示未找到原代码，提醒模型重新 read_file；
   - 若大于 1：报错提示出现多处，强制模型附带更多上下文字符以确保唯一性，避免误改！
2. 跨平台换行符自动归一化：自动抹平 Windows (CRLF) 与 Linux (LF) 的差异。
3. 自动生成标准 Unified Diff：利用 Python 内置 difflib 产出类似 git diff 的补丁文本，
   方便模型自我核验，并提供给终端高亮渲染。
"""

import difflib
import os
from typing import Any, Dict
from mini_agent.tools.base import BaseTool, ToolResult


def normalize_newlines(text: str) -> str:
    """统一将 Windows 换行符 (\\r\\n) 规范化为 Linux (\\n)"""
    return text.replace("\r\n", "\n").replace("\r", "\n")


class EditFileTool(BaseTool):
    """精准局部差异替换工具"""
    name = "edit_file"
    description = (
        "精准局部修改文件。要求 old_str 在目标文件中必须唯一存在。"
        "若修改多处或出现重复片段，需在 old_str 中包含更多上下文字符以保证唯一性。"
    )

    def __init__(self, workspace_dir: str = "."):
        self.workspace_dir = os.path.abspath(workspace_dir)

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "要编辑的文件路径 (相对路径或绝对路径)",
                        },
                        "old_str": {
                            "type": "string",
                            "description": "待替换的原始内容 (必须在文件中唯一出现，区分大小写和缩进)",
                        },
                        "new_str": {
                            "type": "string",
                            "description": "替换后的新内容",
                        },
                    },
                    "required": ["path", "old_str", "new_str"],
                },
            },
        }

    async def execute(self, path: str, old_str: str, new_str: str) -> ToolResult:
        abs_path = os.path.normpath(
            path if os.path.isabs(path) else os.path.join(self.workspace_dir, path)
        )

        # 1. 基础校验
        if not os.path.exists(abs_path):
            return ToolResult(
                content=f"Error: File '{path}' does not exist at '{abs_path}'.",
                is_error=True,
                details={"error_type": "FileNotFound"},
            )

        if os.path.isdir(abs_path):
            return ToolResult(
                content=f"Error: '{path}' is a directory, not a file.",
                is_error=True,
                details={"error_type": "IsADirectory"},
            )

        # 2. 读取原始内容
        try:
            with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                original_content = f.read()
        except Exception as e:
            return ToolResult(
                content=f"Error reading '{path}': {str(e)}",
                is_error=True,
                details={"exception": str(e)},
            )

        # 3. 换行符归一化处理
        norm_original = normalize_newlines(original_content)
        norm_old = normalize_newlines(old_str)
        norm_new = normalize_newlines(new_str)

        # 4. 核心算法：唯一性检查 (Uniqueness Validation)
        occurrences = norm_original.count(norm_old)

        if occurrences == 0:
            return ToolResult(
                content=(
                    f"Error: `old_str` was not found in '{path}'.\n"
                    f"Please verify exact indentation, spaces, and line breaks, "
                    f"or call `read_file` to inspect the latest content first."
                ),
                is_error=True,
                details={"error_type": "NotFound", "occurrences": 0},
            )

        if occurrences > 1:
            return ToolResult(
                content=(
                    f"Error: `old_str` found {occurrences} times in '{path}'.\n"
                    f"To avoid corrupting the file, replacements require exact uniqueness.\n"
                    f"Please provide more surrounding context lines in `old_str` to uniquely identify the target block."
                ),
                is_error=True,
                details={"error_type": "AmbiguousMatch", "occurrences": occurrences},
            )

        # 5. 精准替换 (刚好且仅有 1 处匹配)
        modified_content = norm_original.replace(norm_old, norm_new, 1)

        # 6. 计算标准 Unified Diff 补丁
        diff_lines = list(
            difflib.unified_diff(
                norm_original.splitlines(keepends=True),
                modified_content.splitlines(keepends=True),
                fromfile=f"a/{path}",
                tofile=f"b/{path}",
                n=3,  # 上下文保留 3 行
            )
        )
        diff_text = "".join(diff_lines).strip()

        # 7. 写回文件
        try:
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(modified_content)
        except Exception as e:
            return ToolResult(
                content=f"Error saving modified content to '{path}': {str(e)}",
                is_error=True,
                details={"exception": str(e)},
            )

        return ToolResult(
            content=f"Successfully edited '{path}'. Diff:\n\n{diff_text}",
            is_error=False,
            details={"diff": diff_text, "path": abs_path},
        )
