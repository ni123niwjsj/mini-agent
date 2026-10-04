"""文件读写工具 (ReadFile, WriteFile)。

借鉴 Pi 的工业级安全设计：
1. 行号标注：自动附带 1-indexed 行号 (如 `  1: def main():`)，方便大模型精准定位。
2. 防 Token 爆炸截断：超过最大行数 (如 400 行) 或体积 (50KB) 时自动截断，并提示断点续读。
3. 路径自动解析与目录自动递归创建。
4. 详尽的错误防御：文件不存在、是目录、编码异常时返回结构化错误引导自愈。
"""

import base64
import os
from typing import Any, Dict, Optional
from mini_agent.tools.base import BaseTool, ToolResult


DEFAULT_MAX_LINES = 400
DEFAULT_MAX_BYTES = 50 * 1024  # 50 KB

SUPPORTED_IMAGE_EXTENSIONS = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
}


def resolve_path(path: str, base_dir: str = ".") -> str:
    """将相对路径解析为规范的绝对路径"""
    if os.path.isabs(path):
        return os.path.normpath(path)
    return os.path.normpath(os.path.join(base_dir, path))


class ReadFileTool(BaseTool):
    """读取指定路径文件的工具，支持文本切片与图像多模态读取"""
    name = "read_file"
    description = (
        "读取本地文件内容。支持文本文件和图像文件 (png, jpg, jpeg, gif, webp, bmp)。"
        "对文本文件支持行号切片；读取图像文件时会自动编码并附带图像数据供视觉分析。"
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
                            "description": "文件路径 (相对路径或绝对路径)",
                        },
                        "start_line": {
                            "type": "integer",
                            "description": "起始行号 (仅文本文件有效，从 1 开始计数，默认第 1 行)",
                        },
                        "end_line": {
                            "type": "integer",
                            "description": "结束行号 (仅文本文件有效，包含此行；-1 表示读到文件末尾)",
                        },
                    },
                    "required": ["path"],
                },
            },
        }

    async def execute(
        self,
        path: str,
        start_line: int = 1,
        end_line: int = -1,
    ) -> ToolResult:
        abs_path = resolve_path(path, self.workspace_dir)

        # 1. 存在性与类型检查
        if not os.path.exists(abs_path):
            return ToolResult(
                content=f"Error: File '{path}' does not exist at '{abs_path}'.",
                is_error=True,
                details={"path": abs_path, "error": "NotFound"},
            )

        if os.path.isdir(abs_path):
            return ToolResult(
                content=f"Error: '{path}' is a directory, not a file.",
                is_error=True,
                details={"path": abs_path, "error": "IsADirectory"},
            )

        # 2. 检查是否为支持的图像格式 (对齐 Pi 的原生多模态设计)
        ext = os.path.splitext(abs_path)[1].lower()
        if ext in SUPPORTED_IMAGE_EXTENSIONS:
            mime_type = SUPPORTED_IMAGE_EXTENSIONS[ext]
            try:
                with open(abs_path, "rb") as f:
                    raw_bytes = f.read()

                size_kb = len(raw_bytes) / 1024
                if len(raw_bytes) > 20 * 1024 * 1024:
                    return ToolResult(
                        content=f"Error: Image '{path}' ({size_kb:.1f} KB) exceeds maximum allowed size of 20 MB.",
                        is_error=True,
                        details={"path": abs_path, "error": "ImageTooLarge"},
                    )

                b64_data = base64.b64encode(raw_bytes).decode("utf-8")
                return ToolResult(
                    content=f"Successfully read image '{path}' [{mime_type}, {size_kb:.1f} KB]. Image has been attached for visual analysis.",
                    is_error=False,
                    details={"path": abs_path, "mime_type": mime_type, "size_bytes": len(raw_bytes)},
                    images=[{"data": b64_data, "mime_type": mime_type}],
                )
            except Exception as e:
                return ToolResult(
                    content=f"Error reading image file '{path}': {str(e)}",
                    is_error=True,
                    details={"path": abs_path, "exception": str(e)},
                )

        # 3. 安全读取文本内容
        try:
            with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                all_lines = f.readlines()
        except Exception as e:
            return ToolResult(
                content=f"Error reading file '{path}': {str(e)}",
                is_error=True,
                details={"path": abs_path, "exception": str(e)},
            )

        total_lines = len(all_lines)
        if total_lines == 0:
            return ToolResult(
                content=f"File '{path}' is empty (0 lines).",
                is_error=False,
                details={"path": abs_path, "total_lines": 0},
            )

        # 3. 计算行号切片范围 (1-indexed)
        start_idx = max(0, start_line - 1)
        if end_line == -1 or end_line > total_lines:
            end_idx = total_lines
        else:
            end_idx = max(start_idx, end_line)

        selected_lines = all_lines[start_idx:end_idx]

        # 4. 格式化输出 (带行号)，并做大文件安全截断
        output_lines = []
        accumulated_bytes = 0
        truncated = False
        last_rendered_line = start_idx

        for i, line in enumerate(selected_lines):
            line_no = start_idx + i + 1
            formatted_line = f"{line_no:4d}: {line}"
            line_bytes = len(formatted_line.encode("utf-8"))

            # 超过最大行数或最大字节数限制 -> 截断
            if i >= DEFAULT_MAX_LINES or (accumulated_bytes + line_bytes) > DEFAULT_MAX_BYTES:
                truncated = True
                break

            output_lines.append(formatted_line)
            accumulated_bytes += line_bytes
            last_rendered_line = line_no

        result_text = "".join(output_lines)
        if truncated:
            result_text += (
                f"\n\n[⚠️ 输出已截断: 仅展示第 {start_line} 至 {last_rendered_line} 行 "
                f"(全文件共 {total_lines} 行)。若需阅读后续内容，请指定 start_line={last_rendered_line + 1}]"
            )

        return ToolResult(
            content=result_text,
            is_error=False,
            details={
                "path": abs_path,
                "total_lines": total_lines,
                "displayed_lines": len(output_lines),
                "truncated": truncated,
            },
        )


class WriteFileTool(BaseTool):
    """创建或覆盖写入文件的工具"""
    name = "write_file"
    description = (
        "创建新文件或覆盖写入文件内容。若上级目录不存在，将自动递归创建目录。"
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
                            "description": "写入的目标文件路径",
                        },
                        "content": {
                            "type": "string",
                            "description": "要写入的文件完整文本内容",
                        },
                    },
                    "required": ["path", "content"],
                },
            },
        }

    async def execute(self, path: str, content: str) -> ToolResult:
        abs_path = resolve_path(path, self.workspace_dir)

        try:
            # 自动创建父级目录
            parent_dir = os.path.dirname(abs_path)
            if parent_dir and not os.path.exists(parent_dir):
                os.makedirs(parent_dir, exist_ok=True)

            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(content)

            line_count = len(content.splitlines())
            byte_count = len(content.encode("utf-8"))

            return ToolResult(
                content=(
                    f"Successfully wrote to '{path}' "
                    f"({line_count} lines, {byte_count} bytes)."
                ),
                is_error=False,
                details={
                    "path": abs_path,
                    "line_count": line_count,
                    "byte_count": byte_count,
                },
            )

        except Exception as e:
            return ToolResult(
                content=f"Error writing to file '{path}': {str(e)}",
                is_error=True,
                details={"path": abs_path, "exception": str(e)},
            )
