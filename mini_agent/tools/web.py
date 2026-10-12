"""网络访问与网页提取工具 (WebFetchTool, WebSearchTool)。

赋能 Agent 获取外部网络知识：
1. WebFetchTool (web_fetch): 抓取指定 URL 页面并提取纯净 Markdown 正文，支持自动去噪与防 Token 爆炸截断。
2. WebSearchTool (web_search): 互联网关键词检索，返回结构化标题、摘要与原文链接。
"""

import asyncio
import ipaddress
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional, Tuple
from mini_agent.tools.base import BaseTool, ToolResult

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 MiniAgent/0.2.0"
)
DEFAULT_MAX_BYTES = 50 * 1024  # 50 KB 防爆上限


def is_safe_url(url: str, allow_local: bool = False) -> Tuple[bool, str]:
    """检查 URL 是否安全，阻断私有/保留/环回 IP (SSRF 防护)"""
    if allow_local:
        return True, ""
    try:
        parsed = urllib.parse.urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            return False, "无效的 URL 域名/主机名"
        hostname_lower = hostname.lower()
        if hostname_lower in ("localhost", "0.0.0.0", "127.0.0.1"):
            return False, f"安全拦截: 禁止访问本地环回地址 ({hostname})"
        try:
            ip = ipaddress.ip_address(hostname)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved:
                return False, f"安全拦截: 禁止访问私有/内部/元数据网络地址 ({hostname})"
        except ValueError:
            # 域名放行
            pass
        return True, ""
    except Exception as e:
        return False, f"URL 解析异常: {str(e)}"


def _fetch_url_sync(url: str, max_bytes: int) -> Tuple[str, str, bytes, bool]:
    """在后台工作线程执行同步网页抓取"""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/json,text/plain;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as response:
        content_type = response.headers.get_content_type()
        charset = response.headers.get_content_charset() or "utf-8"
        raw_bytes = response.read(max_bytes + 1024)

    is_truncated = len(raw_bytes) > max_bytes
    if is_truncated:
        raw_bytes = raw_bytes[:max_bytes]
    return content_type, charset, raw_bytes, is_truncated



class HTMLToMarkdownParser(HTMLParser):
    """将 HTML DOM 解析为轻量、可读的 Markdown 文本，并滤除脚本噪点。"""

    def __init__(self, ignore_nav: bool = False):
        super().__init__()
        self.text_parts: List[str] = []
        self.ignore_depth = 0
        self.ignore_tags = {"script", "style", "noscript", "svg", "head", "iframe", "footer"}
        if ignore_nav:
            self.ignore_tags.add("nav")
        self.current_link: Optional[str] = None

    def handle_starttag(self, tag: str, attrs: List[tuple]):
        tag = tag.lower()
        if tag in self.ignore_tags:
            self.ignore_depth += 1
            return
        if self.ignore_depth > 0:
            return

        attrs_dict = dict(attrs)
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            level = int(tag[1])
            self.text_parts.append("\n\n" + "#" * level + " ")
        elif tag == "p":
            self.text_parts.append("\n\n")
        elif tag == "br":
            self.text_parts.append("\n")
        elif tag == "li":
            self.text_parts.append("\n- ")
        elif tag == "a":
            href = attrs_dict.get("href", "")
            if href and not href.startswith("javascript:"):
                self.current_link = href
                self.text_parts.append("[")
        elif tag == "code":
            self.text_parts.append("`")
        elif tag == "pre":
            self.text_parts.append("\n```\n")
        elif tag in ("strong", "b"):
            self.text_parts.append("**")
        elif tag in ("em", "i"):
            self.text_parts.append("*")

    def handle_endtag(self, tag: str):
        tag = tag.lower()
        if tag in self.ignore_tags:
            self.ignore_depth = max(0, self.ignore_depth - 1)
            return
        if self.ignore_depth > 0:
            return

        if tag == "a" and self.current_link is not None:
            self.text_parts.append(f"]({self.current_link})")
            self.current_link = None
        elif tag == "code":
            self.text_parts.append("`")
        elif tag == "pre":
            self.text_parts.append("\n```\n")
        elif tag in ("strong", "b"):
            self.text_parts.append("**")
        elif tag in ("em", "i"):
            self.text_parts.append("*")

    def handle_data(self, data: str):
        if self.ignore_depth == 0:
            self.text_parts.append(data)

    def get_markdown(self) -> str:
        raw = "".join(self.text_parts)
        lines = [line.strip() for line in raw.splitlines()]
        cleaned = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
        return cleaned


class DuckDuckGoHTMLParser(HTMLParser):
    """解析 DuckDuckGo HTML 搜索结果页面"""

    def __init__(self):
        super().__init__()
        self.results: List[Dict[str, str]] = []
        self.in_title = False
        self.in_snippet = False
        self.curr_title = ""
        self.curr_snippet = ""
        self.curr_url = ""

    def handle_starttag(self, tag: str, attrs: List[tuple]):
        tag = tag.lower()
        attrs_dict = dict(attrs)
        classes = attrs_dict.get("class", "").split()

        if tag == "a" and ("result__a" in classes or "result__title" in classes):
            self.in_title = True
            href = attrs_dict.get("href", "")
            if "uddg=" in href:
                parsed = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                self.curr_url = parsed.get("uddg", [href])[0]
            else:
                self.curr_url = href
        elif (tag == "a" and "result__snippet" in classes) or (tag in ("td", "div") and "result-snippet" in classes):
            self.in_snippet = True

    def handle_endtag(self, tag: str):
        tag = tag.lower()
        if tag == "a" and self.in_title:
            self.in_title = False
        elif self.in_snippet and tag in ("a", "td", "div"):
            self.in_snippet = False
            if self.curr_title and self.curr_url:
                self.results.append({
                    "title": self.curr_title.strip(),
                    "url": self.curr_url.strip(),
                    "snippet": self.curr_snippet.strip(),
                })
                self.curr_title = ""
                self.curr_snippet = ""
                self.curr_url = ""

    def handle_data(self, data: str):
        if self.in_title:
            self.curr_title += data
        elif self.in_snippet:
            self.curr_snippet += data


class WebFetchTool(BaseTool):
    """网页内容提取与格式化工具"""
    name = "web_fetch"
    description = (
        "抓取并阅读指定 URL (http/https) 的网页内容。自动剔除脚本和页面噪点，提取纯净的 Markdown 格式正文。"
        "包含内容防爆截断，用于查阅在线官方技术文档、GitHub 页面与 API 参考。"
    )

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "要抓取的网页绝对 URL (以 http:// 或 https:// 开头)",
                        },
                        "max_bytes": {
                            "type": "integer",
                            "description": f"可选。最大允许读取的字节数，默认为 {DEFAULT_MAX_BYTES} (50KB)",
                        },
                    },
                    "required": ["url"],
                },
            },
        }

    async def execute(
        self,
        url: str,
        max_bytes: int = DEFAULT_MAX_BYTES,
        allow_local: bool = False,
        **kwargs: Any,
    ) -> ToolResult:
        if not url or not (url.startswith("http://") or url.startswith("https://")):
            return ToolResult(
                content="错误: URL 必须以 'http://' 或 'https://' 开头。",
                is_error=True,
            )

        is_safe, reason = is_safe_url(url, allow_local=allow_local)
        if not is_safe:
            return ToolResult(
                content=f"抓取失败: {reason}",
                is_error=True,
                details={"url": url, "blocked": True},
            )

        try:
            content_type, charset, raw_bytes, is_truncated = await asyncio.to_thread(
                _fetch_url_sync, url, max_bytes
            )

            decoded_text = raw_bytes.decode(charset, errors="replace")

            if "html" in content_type:
                parser = HTMLToMarkdownParser()
                parser.feed(decoded_text)
                formatted_content = parser.get_markdown()
            elif "json" in content_type:
                try:
                    obj = json.loads(decoded_text)
                    formatted_content = json.dumps(obj, ensure_ascii=False, indent=2)
                except Exception:
                    formatted_content = decoded_text
            else:
                formatted_content = decoded_text

            if not formatted_content.strip():
                formatted_content = "(网页内容为空或未能提取到正文文本)"

            output_lines = [f"🌐 成功抓取网页: {url}"]
            if is_truncated:
                output_lines.append(f"⚠️ [内容已按 {max_bytes // 1024}KB 上限截断]")
            output_lines.append("\n" + formatted_content)

            return ToolResult(
                content="\n".join(output_lines),
                is_error=False,
                details={
                    "url": url,
                    "content_type": content_type,
                    "bytes": len(raw_bytes),
                    "truncated": is_truncated,
                },
            )

        except urllib.error.HTTPError as e:
            return ToolResult(
                content=f"抓取失败: HTTP {e.code} {e.reason} (URL: {url})",
                is_error=True,
                details={"status_code": e.code, "error": str(e)},
            )
        except urllib.error.URLError as e:
            return ToolResult(
                content=f"网络请求失败: 无法连接至目标站点 ({str(e.reason)})。请检查网络或 URL。",
                is_error=True,
                details={"error": str(e)},
            )
        except Exception as e:
            return ToolResult(
                content=f"抓取异常: {type(e).__name__} - {str(e)}",
                is_error=True,
                details={"error": str(e)},
            )


def _search_tavily_sync(query: str, max_results: int, api_key: str) -> Dict[str, Any]:
    """在工作线程执行 Tavily 同步请求"""
    req_data = json.dumps({
        "api_key": api_key,
        "query": query,
        "max_results": max_results,
        "search_depth": "basic",
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.tavily.com/search",
        data=req_data,
        headers={"Content-Type": "application/json", "User-Agent": DEFAULT_USER_AGENT},
    )
    with urllib.request.urlopen(req, timeout=12) as response:
        return json.loads(response.read().decode("utf-8"))


def _search_duckduckgo_sync(query: str) -> str:
    """在工作线程执行 DuckDuckGo HTML 同步抓取"""
    encoded_query = urllib.parse.urlencode({"q": query})
    url = f"https://html.duckduckgo.com/html/?{encoded_query}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=12) as response:
        return response.read().decode("utf-8", errors="replace")


class WebSearchTool(BaseTool):
    """互联网检索工具"""
    name = "web_search"
    description = (
        "在互联网上检索最新开发资料、技术方案、文档或报错解决方法。"
        "返回最相关的网页标题、网页摘要与原网站链接。"
    )

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "要搜索的关键词或问题描述",
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "可选。最大返回结果条数，默认为 5",
                        },
                    },
                    "required": ["query"],
                },
            },
        }

    async def execute(
        self,
        query: str,
        max_results: int = 5,
        **kwargs: Any,
    ) -> ToolResult:
        query = (query or "").strip()
        if not query:
            return ToolResult(content="错误: 搜索 query 不能为空。", is_error=True)

        # 1. 优先检查用户是否配置了专有搜索引擎 API (例如 Tavily)
        tavily_key = os.getenv("TAVILY_API_KEY")
        if tavily_key:
            return await self._search_tavily(query, max_results, tavily_key)

        # 2. 默认使用免 Key 搜索引擎 (DuckDuckGo HTML)
        return await self._search_duckduckgo(query, max_results)

    async def _search_tavily(self, query: str, max_results: int, api_key: str) -> ToolResult:
        try:
            res_json = await asyncio.to_thread(_search_tavily_sync, query, max_results, api_key)
            results = res_json.get("results", [])
            if not results:
                return ToolResult(content=f"🔍 未搜索到关于 '{query}' 的相关结果。", is_error=False)

            lines = [f"🔍 搜索结果 (关键词: '{query}'):\n"]
            for idx, r in enumerate(results[:max_results], 1):
                title = r.get("title", "无标题")
                url = r.get("url", "")
                snippet = r.get("content", "").strip()
                lines.append(f"{idx}. [{title}]({url})\n   {snippet}\n")

            return ToolResult(
                content="\n".join(lines).strip(),
                is_error=False,
                details={"query": query, "count": len(results[:max_results]), "provider": "tavily"},
            )
        except Exception:
            # Tavily 失败时平滑降级为内置引擎
            return await self._search_duckduckgo(query, max_results)

    async def _search_duckduckgo(self, query: str, max_results: int) -> ToolResult:
        try:
            html_text = await asyncio.to_thread(_search_duckduckgo_sync, query)

            parser = DuckDuckGoHTMLParser()
            parser.feed(html_text)
            results = parser.results

            if not results:
                lower_html = html_text.lower()
                is_blocked = any(kw in lower_html for kw in ("robot", "anomaly", "captcha", "challenge", "block"))
                if is_blocked:
                    return ToolResult(
                        content=f"⚠️ 检索受限: 搜索引擎触发人机拦截/反爬验证 (关键词: '{query}')。若需高可用生产搜索，建议在环境变量中配置 TAVILY_API_KEY。",
                        is_error=True,
                        details={"query": query, "blocked": True},
                    )
                return ToolResult(
                    content=(
                        f"🔍 未搜索到关于 '{query}' 的相关结果 (提示: 免 Key 搜索引擎可能受到速率限制，建议尝试换用核心技术英文关键词；"
                        f"或配置 TAVILY_API_KEY 以获得稳定检索结果)。"
                    ),
                    is_error=False,
                    details={"query": query, "count": 0},
                )

            lines = [f"🔍 搜索结果 (关键词: '{query}'):\n"]
            for idx, r in enumerate(results[:max_results], 1):
                lines.append(f"{idx}. [{r['title']}]({r['url']})\n   {r['snippet']}\n")

            return ToolResult(
                content="\n".join(lines).strip(),
                is_error=False,
                details={"query": query, "count": len(results[:max_results]), "provider": "duckduckgo"},
            )
        except urllib.error.URLError as e:
            return ToolResult(
                content=f"网络检索失败: 无法连接至搜索引擎 ({str(e.reason)})。请检查外网连接或代理设置。",
                is_error=True,
                details={"error": str(e)},
            )
        except Exception as e:
            return ToolResult(
                content=f"检索异常: {type(e).__name__} - {str(e)}",
                is_error=True,
                details={"error": str(e)},
            )

