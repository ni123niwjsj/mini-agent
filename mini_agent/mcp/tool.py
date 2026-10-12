"""MCP 工具包装器 (MCPToolWrapper)。

将远程 MCP 服务端发现的工具桥接为 Mini-Agent 内置的 BaseTool 对象，
实现大模型与外部标准 MCP 生态的无缝调用。
"""

import json
from typing import Any, Dict, List, Optional
from mini_agent.mcp.client import MCPError, StdioMCPClient
from mini_agent.tools.base import BaseTool, ToolResult


class MCPToolWrapper(BaseTool):
    """远程 MCP 工具适配包装器"""

    def __init__(
        self,
        client: StdioMCPClient,
        name: str,
        description: str,
        input_schema: Dict[str, Any],
        server_name: str = "",
        original_name: Optional[str] = None,
    ):
        self.client = client
        self.name = name
        self.original_name = original_name or name
        self.description = (
            description
            or f"MCP 外部工具 '{self.original_name}' (来源服务: {server_name or 'custom'})"
        )
        self.input_schema = input_schema or {"type": "object", "properties": {}}
        self.server_name = server_name

    def get_schema(self) -> Dict[str, Any]:
        """生成兼容 OpenAI Function Calling 的工具参数 Schema"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        """执行远程 MCP 工具调用并解析规范返回"""
        try:
            res = await self.client.call_tool(self.original_name, kwargs)

            is_error = bool(res.get("isError", False))
            content_items = res.get("content", [])

            text_parts: List[str] = []
            images: List[Dict[str, str]] = []

            if isinstance(content_items, list):
                for item in content_items:
                    if not isinstance(item, dict):
                        text_parts.append(str(item))
                        continue

                    item_type = item.get("type", "text")
                    if item_type == "text":
                        text_parts.append(item.get("text", ""))
                    elif item_type == "image":
                        img_data = item.get("data", "")
                        mime = item.get("mimeType", "image/png")
                        if img_data:
                            images.append({"data": img_data, "mime_type": mime})
                    else:
                        text_parts.append(json.dumps(item, ensure_ascii=False))

            if not text_parts and not images:
                # 若服务端返回空 content，输出友好占位或全量 json
                content_str = (
                    json.dumps(res, ensure_ascii=False)
                    if res
                    else "(工具执行完成，无输出返回)"
                )
            else:
                content_str = "\n".join(text_parts).strip()

            return ToolResult(
                content=content_str,
                is_error=is_error,
                details={
                    "server": self.server_name,
                    "mcp_tool": self.original_name,
                    "raw_result": res,
                },
                images=images if images else None,
            )

        except MCPError as e:
            return ToolResult(
                content=f"MCP 服务端错误 ({self.name}): {e.message}",
                is_error=True,
                details={"server": self.server_name, "error": e.data},
            )
        except Exception as e:
            return ToolResult(
                content=f"MCP 调用失败 ({self.name}): {type(e).__name__} - {str(e)}",
                is_error=True,
                details={"server": self.server_name, "exception": str(e)},
            )

