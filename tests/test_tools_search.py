import asyncio
import os
import shutil
import tempfile
import unittest
from mini_agent.tools.search import GrepTool, GlobTool, is_binary_file


class TestSearchTools(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

        # 创建目录结构
        # temp_dir/
        #   root.py ("print('Hello root')\n")
        #   src/
        #     app.py ("def main():\n    print('Hello world')\n")
        #     utils.py ("def helper():\n    return 'Hello helper'\n")
        #   docs/
        #     README.md ("# Documentation\nHello reader\n")
        #   .github/
        #     ci.yml ("name: CI\nrun: pytest\n")
        #   node_modules/
        #     pkg.js ("console.log('Hello node');")
        #   .git/
        #     config ("Hello git")
        #   binary.bin (b"\x00\x01\x02Hello")
        os.makedirs(os.path.join(self.temp_dir, "src"), exist_ok=True)
        os.makedirs(os.path.join(self.temp_dir, "docs"), exist_ok=True)
        os.makedirs(os.path.join(self.temp_dir, ".github"), exist_ok=True)
        os.makedirs(os.path.join(self.temp_dir, "node_modules"), exist_ok=True)
        os.makedirs(os.path.join(self.temp_dir, ".git"), exist_ok=True)

        with open(os.path.join(self.temp_dir, "root.py"), "w", encoding="utf-8") as f:
            f.write("print('Hello root')\n")

        with open(os.path.join(self.temp_dir, "src", "app.py"), "w", encoding="utf-8") as f:
            f.write("def main():\n    print('Hello world')\n")

        with open(os.path.join(self.temp_dir, "src", "utils.py"), "w", encoding="utf-8") as f:
            f.write("def helper():\n    return 'Hello helper'\n")

        with open(os.path.join(self.temp_dir, "docs", "README.md"), "w", encoding="utf-8") as f:
            f.write("# Documentation\nHello reader\n")

        with open(os.path.join(self.temp_dir, ".github", "ci.yml"), "w", encoding="utf-8") as f:
            f.write("name: CI\nrun: pytest\n")

        with open(os.path.join(self.temp_dir, "node_modules", "pkg.js"), "w", encoding="utf-8") as f:
            f.write("console.log('Hello node');\n")

        with open(os.path.join(self.temp_dir, ".git", "config"), "w", encoding="utf-8") as f:
            f.write("Hello git\n")

        with open(os.path.join(self.temp_dir, "binary.bin"), "wb") as f:
            f.write(b"\x00\x01\x02Hello binary")

        self.grep_tool = GrepTool(workspace_dir=self.temp_dir)
        self.glob_tool = GlobTool(workspace_dir=self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_grep_basic(self):
        # 搜索 'Hello'
        res = asyncio.run(self.grep_tool.execute(pattern="Hello"))
        self.assertFalse(res.is_error)
        self.assertIn("找到 4 处匹配", res.content)  # root.py, app.py, utils.py, README.md
        self.assertIn("root.py:", res.content)
        self.assertIn("src/app.py:", res.content)
        self.assertIn("src/utils.py:", res.content)
        self.assertIn("docs/README.md:", res.content)
        # 确保自动排除了 node_modules, .git, .github (未开启 hidden) 以及二进制文件
        self.assertNotIn("node_modules", res.content)
        self.assertNotIn(".git", res.content)
        self.assertNotIn(".github", res.content)
        self.assertNotIn("binary.bin", res.content)

    def test_grep_regex_and_case_sensitivity(self):
        res = asyncio.run(self.grep_tool.execute(pattern=r"def \w+\(\):"))
        self.assertFalse(res.is_error)
        self.assertIn("def main():", res.content)
        self.assertIn("def helper():", res.content)

        # 大小写敏感搜索
        res_case = asyncio.run(self.grep_tool.execute(pattern="hello", case_sensitive=True))
        self.assertIn("未找到匹配", res_case.content)

        res_nocase = asyncio.run(self.grep_tool.execute(pattern="hello", case_sensitive=False))
        self.assertIn("找到 4 处匹配", res_nocase.content)

    def test_grep_file_pattern_filter(self):
        # 仅搜索 *.py
        res = asyncio.run(self.grep_tool.execute(pattern="Hello", file_pattern="*.py"))
        self.assertFalse(res.is_error)
        self.assertIn("root.py:", res.content)
        self.assertIn("src/app.py:", res.content)
        self.assertIn("src/utils.py:", res.content)
        self.assertNotIn("README.md", res.content)

    def test_grep_hidden_directories(self):
        # 默认不搜隐藏目录
        res_default = asyncio.run(self.grep_tool.execute(pattern="pytest"))
        self.assertIn("未找到匹配", res_default.content)

        # 开启 include_hidden=True，搜索到 .github/ci.yml
        res_hidden = asyncio.run(self.grep_tool.execute(pattern="pytest", include_hidden=True))
        self.assertFalse(res_hidden.is_error)
        self.assertIn(".github/ci.yml:", res_hidden.content)
        # 即使开启 include_hidden，核心黑名单 .git 依旧被排除
        self.assertNotIn(".git/", res_hidden.content)
        self.assertNotIn(".git/config", res_hidden.content)

        # 显式指定 path=".github" 时自动允许
        res_explicit = asyncio.run(self.grep_tool.execute(pattern="pytest", path=".github"))
        self.assertFalse(res_explicit.is_error)
        self.assertIn(".github/ci.yml:", res_explicit.content)

    def test_workspace_boundary_security(self):
        # 目录穿越 path=".."
        res_escape = asyncio.run(self.grep_tool.execute(pattern="Hello", path=".."))
        self.assertTrue(res_escape.is_error)
        self.assertIn("超出工作区边界", res_escape.content)

        # glob 目录穿越
        res_glob_escape = asyncio.run(self.glob_tool.execute(pattern="*", path=".."))
        self.assertTrue(res_glob_escape.is_error)
        self.assertIn("超出工作区边界", res_glob_escape.content)

        # 绝对路径逃逸
        res_abs_escape = asyncio.run(self.glob_tool.execute(pattern="*", path="/etc"))
        self.assertTrue(res_abs_escape.is_error)
        self.assertIn("超出工作区边界", res_abs_escape.content)

    def test_glob_path_aware_semantics(self):
        # 1. 严格单层匹配: *.py 只能匹配 root.py，绝不能递归进入 src/app.py
        res_root_py = asyncio.run(self.glob_tool.execute(pattern="*.py"))
        self.assertFalse(res_root_py.is_error)
        self.assertIn("root.py", res_root_py.content)
        self.assertNotIn("src/app.py", res_root_py.content)
        self.assertNotIn("src/utils.py", res_root_py.content)

        # 2. 单层子路径匹配: src/*.py 只能匹配 src 下的直接 py 文件
        res_src_py = asyncio.run(self.glob_tool.execute(pattern="src/*.py"))
        self.assertFalse(res_src_py.is_error)
        self.assertIn("src/app.py", res_src_py.content)
        self.assertIn("src/utils.py", res_src_py.content)
        self.assertNotIn("root.py", res_src_py.content)

        # 3. 递归通配符: **/*.py 匹配全库所有 py 文件
        res_all_py = asyncio.run(self.glob_tool.execute(pattern="**/*.py"))
        self.assertFalse(res_all_py.is_error)
        self.assertIn("root.py", res_all_py.content)
        self.assertIn("src/app.py", res_all_py.content)
        self.assertIn("src/utils.py", res_all_py.content)

    def test_glob_directory_matching(self):
        # 匹配具体目录: src
        res_dir = asyncio.run(self.glob_tool.execute(pattern="src"))
        self.assertFalse(res_dir.is_error)
        self.assertIn("src/", res_dir.content)

        # 匹配所有顶层目录: */
        res_top_dirs = asyncio.run(self.glob_tool.execute(pattern="*/"))
        self.assertFalse(res_top_dirs.is_error)
        self.assertIn("src/", res_top_dirs.content)
        self.assertIn("docs/", res_top_dirs.content)
        self.assertNotIn("root.py", res_top_dirs.content)

    def test_glob_hidden_directories(self):
        # 默认不搜隐藏目录
        res_default = asyncio.run(self.glob_tool.execute(pattern="**/*.yml"))
        self.assertIn("未找到匹配模式", res_default.content)

        # 开启 include_hidden=True
        res_hidden = asyncio.run(self.glob_tool.execute(pattern="**/*.yml", include_hidden=True))
        self.assertFalse(res_hidden.is_error)
        self.assertIn(".github/ci.yml", res_hidden.content)

    def test_glob_subpath_and_filtering(self):
        # 在指定子目录下匹配
        res = asyncio.run(self.glob_tool.execute(pattern="*.md", path="docs"))
        self.assertFalse(res.is_error)
        self.assertIn("docs/README.md", res.content)

    def test_glob_max_results(self):
        res = asyncio.run(self.glob_tool.execute(pattern="**/*", max_results=2))
        self.assertFalse(res.is_error)
        self.assertIn("已达到最大结果上限", res.content)

    def test_glob_character_sets(self):
        # 创建数字和字母命名的文件
        with open(os.path.join(self.temp_dir, "file1.txt"), "w") as f:
            f.write("1")
        with open(os.path.join(self.temp_dir, "file2.txt"), "w") as f:
            f.write("2")
        with open(os.path.join(self.temp_dir, "fileA.txt"), "w") as f:
            f.write("A")

        # 匹配数字字符集 [0-9]
        res_digits = asyncio.run(self.glob_tool.execute(pattern="file[0-9].txt"))
        self.assertFalse(res_digits.is_error)
        self.assertIn("file1.txt", res_digits.content)
        self.assertIn("file2.txt", res_digits.content)
        self.assertNotIn("fileA.txt", res_digits.content)

        # 否定字符集 [!0-9]
        res_non_digits = asyncio.run(self.glob_tool.execute(pattern="file[!0-9].txt"))
        self.assertFalse(res_non_digits.is_error)
        self.assertIn("fileA.txt", res_non_digits.content)
        self.assertNotIn("file1.txt", res_non_digits.content)

    def test_glob_case_sensitive(self):
        with open(os.path.join(self.temp_dir, "UPPER.TXT"), "w") as f:
            f.write("UPPER")

        # 默认 case_sensitive=False (忽略大小写)
        res_nocase = asyncio.run(self.glob_tool.execute(pattern="*.txt", case_sensitive=False))
        self.assertIn("UPPER.TXT", res_nocase.content)

        # 开启 case_sensitive=True (大小写敏感)
        res_case = asyncio.run(self.glob_tool.execute(pattern="*.txt", case_sensitive=True))
        self.assertNotIn("UPPER.TXT", res_case.content)

        res_upper = asyncio.run(self.glob_tool.execute(pattern="*.TXT", case_sensitive=True))
        self.assertIn("UPPER.TXT", res_upper.content)

    def test_is_binary_file(self):
        self.assertTrue(is_binary_file(os.path.join(self.temp_dir, "binary.bin")))
        self.assertFalse(is_binary_file(os.path.join(self.temp_dir, "src", "app.py")))


if __name__ == "__main__":
    unittest.main()
