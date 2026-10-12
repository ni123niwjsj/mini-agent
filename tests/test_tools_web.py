import asyncio
import io
import json
import os
import unittest
import urllib.error
from unittest.mock import MagicMock, patch

from mini_agent.tools.web import (
    DEFAULT_MAX_BYTES,
    DuckDuckGoHTMLParser,
    HTMLToMarkdownParser,
    WebFetchTool,
    WebSearchTool,
)


class TestHTMLToMarkdownParser(unittest.TestCase):
    def test_basic_formatting(self):
        html = """
        <html>
        <head><title>Test Title</title><script>var x = 1;</script></head>
        <body>
            <h1>主标题</h1>
            <p>这是一段包含<strong>粗体</strong>和<em>斜体</em>以及<code>代码</code>的文字。</p>
            <p>访问 <a href="https://example.com">示例网站</a> 了解详情。</p>
            <ul>
                <li>列表项目 1</li>
                <li>列表项目 2</li>
            </ul>
            <pre>def foo():\n    return 42</pre>
            <style>body { color: red; }</style>
        </body>
        </html>
        """
        parser = HTMLToMarkdownParser()
        parser.feed(html)
        md = parser.get_markdown()

        self.assertIn("# 主标题", md)
        self.assertIn("**粗体**", md)
        self.assertIn("*斜体*", md)
        self.assertIn("`代码`", md)
        self.assertIn("[示例网站](https://example.com)", md)
        self.assertIn("- 列表项目 1", md)
        self.assertIn("- 列表项目 2", md)
        self.assertIn("def foo():", md)
        self.assertNotIn("var x = 1;", md)
        self.assertNotIn("color: red", md)

    def test_nav_content_preserved_by_default(self):
        html = "<nav><a href='/docs/intro'>入门指引</a><span> > </span><a href='/docs/api'>API 参考</a></nav>"
        parser = HTMLToMarkdownParser(ignore_nav=False)
        parser.feed(html)
        md = parser.get_markdown()
        self.assertIn("[入门指引](/docs/intro)", md)
        self.assertIn("[API 参考](/docs/api)", md)


class TestDuckDuckGoHTMLParser(unittest.TestCase):
    def test_parse_results(self):
        html = """
        <div class="result">
            <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fpython.org&rut=1">Python 官方网站</a>
            <a class="result__snippet" href="#">Python 是一种高级通用编程语言。</a>
        </div>
        <div class="result">
            <a class="result__a" href="https://docs.python.org">Python 文档中心</a>
            <div class="result-snippet">官方技术文档库与教程。</div>
        </div>
        """
        parser = DuckDuckGoHTMLParser()
        parser.feed(html)
        results = parser.results

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["title"], "Python 官方网站")
        self.assertEqual(results[0]["url"], "https://python.org")
        self.assertEqual(results[0]["snippet"], "Python 是一种高级通用编程语言。")
        self.assertEqual(results[1]["title"], "Python 文档中心")
        self.assertEqual(results[1]["url"], "https://docs.python.org")
        self.assertEqual(results[1]["snippet"], "官方技术文档库与教程。")


class TestWebFetchTool(unittest.TestCase):
    def setUp(self):
        self.tool = WebFetchTool()

    def test_schema(self):
        schema = self.tool.get_schema()
        self.assertEqual(schema["type"], "function")
        self.assertEqual(schema["function"]["name"], "web_fetch")
        self.assertIn("url", schema["function"]["parameters"]["properties"])

    def test_invalid_url(self):
        res = asyncio.run(self.tool.execute(url="ftp://ftp.example.com"))
        self.assertTrue(res.is_error)
        self.assertIn("错误: URL 必须以 'http://' 或 'https://' 开头", res.content)

        res2 = asyncio.run(self.tool.execute(url=""))
        self.assertTrue(res2.is_error)

    def test_fetch_ssrf_blocked(self):
        # 环回与私有地址被拦截
        res_loopback = asyncio.run(self.tool.execute(url="http://127.0.0.1:8080/admin"))
        self.assertTrue(res_loopback.is_error)
        self.assertIn("安全拦截", res_loopback.content)

        res_metadata = asyncio.run(self.tool.execute(url="http://169.254.169.254/latest/meta-data"))
        self.assertTrue(res_metadata.is_error)
        self.assertIn("安全拦截", res_metadata.content)

        res_localhost = asyncio.run(self.tool.execute(url="http://localhost/status"))
        self.assertTrue(res_localhost.is_error)
        self.assertIn("安全拦截", res_localhost.content)

    @patch("urllib.request.urlopen")
    def test_fetch_html_success(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.headers.get_content_type.return_value = "text/html"
        mock_response.headers.get_content_charset.return_value = "utf-8"
        html_content = "<html><body><h1>测试文档</h1><p>正文内容测试</p></body></html>".encode("utf-8")
        mock_response.read.return_value = html_content
        mock_response.__enter__.return_value = mock_response

        mock_urlopen.return_value = mock_response

        res = asyncio.run(self.tool.execute(url="https://example.com/docs"))
        self.assertFalse(res.is_error)
        self.assertIn("🌐 成功抓取网页: https://example.com/docs", res.content)
        self.assertIn("# 测试文档", res.content)
        self.assertIn("正文内容测试", res.content)
        self.assertEqual(res.details["content_type"], "text/html")

    @patch("urllib.request.urlopen")
    def test_fetch_json_success(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.headers.get_content_type.return_value = "application/json"
        mock_response.headers.get_content_charset.return_value = "utf-8"
        json_obj = {"status": "ok", "version": "1.0.0"}
        mock_response.read.return_value = json.dumps(json_obj).encode("utf-8")
        mock_response.__enter__.return_value = mock_response

        mock_urlopen.return_value = mock_response

        res = asyncio.run(self.tool.execute(url="https://api.example.com/status"))
        self.assertFalse(res.is_error)
        self.assertIn('"version": "1.0.0"', res.content)

    @patch("urllib.request.urlopen")
    def test_fetch_truncation(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.headers.get_content_type.return_value = "text/plain"
        mock_response.headers.get_content_charset.return_value = "utf-8"
        mock_response.read.return_value = b"A" * 2000
        mock_response.__enter__.return_value = mock_response

        mock_urlopen.return_value = mock_response

        res = asyncio.run(self.tool.execute(url="https://example.com/large.txt", max_bytes=1000))
        self.assertFalse(res.is_error)
        self.assertTrue(res.details["truncated"])
        self.assertEqual(res.details["bytes"], 1000)
        self.assertIn("内容已按 0KB 上限截断", res.content)

    @patch("urllib.request.urlopen")
    def test_fetch_http_error(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://example.com/404",
            code=404,
            msg="Not Found",
            hdrs={},
            fp=None,
        )

        res = asyncio.run(self.tool.execute(url="https://example.com/404"))
        self.assertTrue(res.is_error)
        self.assertIn("HTTP 404", res.content)
        self.assertEqual(res.details["status_code"], 404)

    @patch("urllib.request.urlopen")
    def test_fetch_url_error(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")

        res = asyncio.run(self.tool.execute(url="https://unreachable.site"))
        self.assertTrue(res.is_error)
        self.assertIn("网络请求失败", res.content)


class TestWebSearchTool(unittest.TestCase):
    def setUp(self):
        self.tool = WebSearchTool()

    def test_schema(self):
        schema = self.tool.get_schema()
        self.assertEqual(schema["type"], "function")
        self.assertEqual(schema["function"]["name"], "web_search")
        self.assertIn("query", schema["function"]["parameters"]["properties"])

    def test_empty_query(self):
        res = asyncio.run(self.tool.execute(query="   "))
        self.assertTrue(res.is_error)
        self.assertIn("错误: 搜索 query 不能为空", res.content)

    @patch("urllib.request.urlopen")
    def test_duckduckgo_search_success(self, mock_urlopen):
        mock_response = MagicMock()
        sample_html = """
        <div class="result">
            <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fastral.sh%2Fuv&rut=1">astral-sh/uv</a>
            <a class="result__snippet" href="#">An extremely fast Python package and project manager.</a>
        </div>
        """.encode("utf-8")
        mock_response.read.return_value = sample_html
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        with patch.dict(os.environ, {}, clear=True):
            res = asyncio.run(self.tool.execute(query="python uv"))

        self.assertFalse(res.is_error)
        self.assertEqual(res.details["provider"], "duckduckgo")
        self.assertIn("[astral-sh/uv](https://astral.sh/uv)", res.content)
        self.assertIn("An extremely fast Python package", res.content)

    @patch("urllib.request.urlopen")
    def test_tavily_search_success(self, mock_urlopen):
        mock_response = MagicMock()
        tavily_data = {
            "results": [
                {
                    "title": "FastAPI Framework",
                    "url": "https://fastapi.tiangolo.com",
                    "content": "FastAPI framework, high performance, easy to learn.",
                }
            ]
        }
        mock_response.read.return_value = json.dumps(tavily_data).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        with patch.dict(os.environ, {"TAVILY_API_KEY": "tvly-test-1234"}):
            res = asyncio.run(self.tool.execute(query="fastapi"))

        self.assertFalse(res.is_error)
        self.assertEqual(res.details["provider"], "tavily")
        self.assertIn("[FastAPI Framework](https://fastapi.tiangolo.com)", res.content)
        self.assertIn("FastAPI framework, high performance", res.content)

    @patch("urllib.request.urlopen")
    def test_duckduckgo_antibot_challenge_detected(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = b"<html><body>Our systems have detected anomalous traffic robot challenge</body></html>"
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        with patch.dict(os.environ, {}, clear=True):
            res = asyncio.run(self.tool.execute(query="test bot"))

        self.assertTrue(res.is_error)
        self.assertIn("触发人机拦截/反爬验证", res.content)


if __name__ == "__main__":
    unittest.main()

