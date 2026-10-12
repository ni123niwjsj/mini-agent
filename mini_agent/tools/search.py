"""代码与文件检索工具 (GrepTool, GlobTool)。

赋能 Agent 拥有原生、跨平台、高效率的语义与结构化搜索能力：
1. GrepTool: 跨文件正则与关键词搜索，自动定位文件名与行号，过滤二进制与干扰目录。
2. GlobTool: 基于路径感知通配符快速发现工作区文件与目录结构。
"""

import asyncio
import fnmatch
import os
import re
from typing import Any, Dict, List, Optional, Tuple
from mini_agent.tools.base import BaseTool, ToolResult

# 核心永远忽略的黑名单目录 (即使开启 include_hidden 也绝对不遍历)
CORE_IGNORE_DIRS = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    ".pytest_cache",
    ".mypy_cache",
    ".sessions",
}

# 默认跳过的非代码/干扰目录 (普通搜索时自动过滤)
DEFAULT_IGNORE_DIRS = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    ".idea",
    ".vscode",
    "dist",
    "build",
    ".next",
    ".cache",
    ".pytest_cache",
    ".mypy_cache",
    ".sessions",
    ".gemini",
    "egg-info",
}

# 常见二进制后缀，避免读取乱码
BINARY_EXTENSIONS = {
    ".pyc", ".pyo", ".pyd", ".so", ".dll", ".dylib", ".exe", ".bin",
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp", ".bmp", ".svg",
    ".pdf", ".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".7z",
    ".woff", ".woff2", ".ttf", ".eot", ".mp3", ".mp4", ".wav", ".avi",
    ".db", ".sqlite", ".sqlite3",
}


def is_binary_file(filepath: str) -> bool:
    """快速判断是否为二进制文件"""
    ext = os.path.splitext(filepath)[1].lower()
    if ext in BINARY_EXTENSIONS:
        return True
    try:
        with open(filepath, "rb") as f:
            chunk = f.read(1024)
            if b"\x00" in chunk:
                return True
    except Exception:
        return True
    return False


def resolve_safe_workspace_path(
    workspace_dir: str,
    path: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """安全解析工作区内路径并防止目录穿越。
    
    Returns:
        Tuple[abs_path, error_message]: 成功返回 (绝对路径, None)；失败返回 (None, 错误描述)。
    """
    workspace_abs = os.path.abspath(workspace_dir)
    if not path or path.strip() in (".", ""):
        return workspace_abs, None

    clean_path = path.strip()
    if os.path.isabs(clean_path):
        target_abs = os.path.normpath(clean_path)
    else:
        target_abs = os.path.normpath(os.path.join(workspace_abs, clean_path))

    try:
        common = os.path.commonpath([workspace_abs, target_abs])
    except ValueError:
        return None, f"错误: 搜索路径 '{path}' 超出工作区边界 ({workspace_abs})。"

    if common != workspace_abs:
        return None, f"错误: 搜索路径 '{path}' 超出工作区边界 ({workspace_abs})。"

    if not os.path.exists(target_abs):
        return None, f"错误: 搜索路径不存在: '{path}'"

    return target_abs, None


def glob_to_path_regex(pattern: str, case_sensitive: bool = False) -> Tuple[re.Pattern, bool]:
    """将 Unix 通配符模式编译为路径感知的正规表达式。
    
    特性：
    - '*' 仅匹配单个路径段内的非 '/' 字符，绝不跨越目录层级；
    - '**' 支持跨目录层级匹配；
    - 若模式以 '/' 结尾，标记为仅匹配目录；
    - 支持字符集与范围 (如 [0-9], [a-z], [!abc])；
    - 支持大小写敏感开关 (case_sensitive)。
    
    Returns:
        Tuple[compiled_regex, match_dir_only]
    """
    pattern = pattern.replace("\\", "/").strip()
    match_dir_only = pattern.endswith("/")
    if match_dir_only:
        pattern = pattern.rstrip("/")
    if pattern.startswith("./"):
        pattern = pattern[2:]

    i = 0
    n = len(pattern)
    res = []
    while i < n:
        c = pattern[i]
        if c == "*":
            if i + 1 < n and pattern[i + 1] == "*":
                # '**' 模式
                if i + 2 < n and pattern[i + 2] == "/":
                    res.append("(?:.+/)?")
                    i += 3
                    continue
                elif i > 0 and pattern[i - 1] == "/":
                    if res and res[-1] == "/":
                        res.pop()
                    res.append("(?:/.*)?")
                    i += 2
                    continue
                else:
                    res.append(".*")
                    i += 2
                    continue
            else:
                # 单个 '*'，仅匹配单层
                res.append("[^/]*")
                i += 1
                continue
        elif c == "?":
            res.append("[^/]")
            i += 1
            continue
        elif c == "[":
            # 解析字符集 [0-9] 或 [!abc]
            j = i + 1
            if j < n and pattern[j] in ("!", "^"):
                j += 1
            if j < n and pattern[j] == "]":
                j += 1
            while j < n and pattern[j] != "]":
                j += 1
            if j < n and "/" not in pattern[i:j + 1]:
                inner = pattern[i + 1:j]
                if inner.startswith("!"):
                    inner = "^" + inner[1:]
                res.append("[" + inner + "]")
                i = j + 1
                continue
            else:
                res.append(r"\[")
                i += 1
                continue
        elif c in r"().+^${}|":
            res.append("\\" + c)
            i += 1
            continue
        else:
            res.append(c)
            i += 1

    flags = 0 if case_sensitive else re.IGNORECASE
    regex = re.compile("^" + "".join(res) + "$", flags)
    return regex, match_dir_only


class GrepTool(BaseTool):
    """跨文件正则表达式检索工具"""
    name = "grep"
    description = (
        "在工作区中搜索匹配正则表达式或关键词的文件内容。自动排除 .git, node_modules, __pycache__, .venv, dist 等干扰目录。"
        "返回匹配的文件相对路径、行号与内容摘要。对于大项目搜索极其高效。"
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
                        "pattern": {
                            "type": "string",
                            "description": "要搜索的正则表达式或关键字 (例如 'def stream_chat', 'class .*Tool')",
                        },
                        "path": {
                            "type": "string",
                            "description": "可选。搜索的子目录或单个文件路径 (相对工作区)，默认为当前工作区根目录",
                        },
                        "case_sensitive": {
                            "type": "boolean",
                            "description": "可选。是否区分大小写，默认为 False",
                        },
                        "file_pattern": {
                            "type": "string",
                            "description": "可选。按文件名模式过滤 (例如 '*.py', '*.ts', '*.json')",
                        },
                        "include_hidden": {
                            "type": "boolean",
                            "description": "可选。是否搜索隐藏目录与隐藏文件 (以 '.' 开头，如 .github)，默认为 False",
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "可选。最大返回的匹配行数，默认为 100",
                        },
                    },
                    "required": ["pattern"],
                },
            },
        }

    async def execute(
        self,
        pattern: str,
        path: Optional[str] = None,
        case_sensitive: bool = False,
        file_pattern: Optional[str] = None,
        include_hidden: bool = False,
        max_results: int = 100,
        **kwargs: Any,
    ) -> ToolResult:
        if not pattern:
            return ToolResult(content="错误: 搜索 pattern 不能为空。", is_error=True)

        target_root, err_msg = resolve_safe_workspace_path(self.workspace_dir, path)
        if err_msg or not target_root:
            return ToolResult(content=err_msg or "错误: 无效路径", is_error=True)

        try:
            flags = 0 if case_sensitive else re.IGNORECASE
            regex = re.compile(pattern, flags)
        except re.error as e:
            return ToolResult(content=f"错误: 正则表达式编译失败 '{pattern}': {str(e)}", is_error=True)

        # 若 target_root 本身显式指向隐藏目录 (例如 path=".github")，自动允许隐藏模式
        is_hidden_target = os.path.basename(target_root).startswith(".") or any(
            part.startswith(".") for part in os.path.relpath(target_root, self.workspace_dir).split(os.sep) if part != "."
        )
        effective_hidden = include_hidden or is_hidden_target

        matches_by_file, total_matches = await asyncio.to_thread(
            self._sync_grep_files,
            target_root,
            effective_hidden,
            file_pattern,
            regex,
            max_results,
        )

        if not matches_by_file:
            return ToolResult(
                content=f"🔍 未找到匹配 '{pattern}' 的内容 (搜索范围: {path or '.'})",
                is_error=False,
                details={"pattern": pattern, "matched_count": 0},
            )

        output_lines = [f"🔍 找到 {total_matches} 处匹配 (模式: '{pattern}'):"]
        for rpath, lines in matches_by_file.items():
            output_lines.append(f"\n{rpath}:")
            output_lines.extend(lines)

        if total_matches >= max_results:
            output_lines.append(f"\n⚠️ 已达到最大结果上限 ({max_results} 行)，更多匹配已省略。")

        return ToolResult(
            content="\n".join(output_lines),
            is_error=False,
            details={"pattern": pattern, "matched_count": total_matches, "files_count": len(matches_by_file)},
        )

    def _sync_grep_files(
        self,
        target_root: str,
        effective_hidden: bool,
        file_pattern: Optional[str],
        regex: re.Pattern,
        max_results: int,
    ) -> Tuple[Dict[str, List[str]], int]:
        """在后台工作线程执行同步文件遍历与内容扫描"""
        matches_by_file: Dict[str, List[str]] = {}
        total_matches = 0

        # 如果 target_root 是单个文件
        if os.path.isfile(target_root):
            files_to_check = [target_root]
        else:
            files_to_check = []
            for root, dirs, files in os.walk(target_root):
                # 剪枝排除干扰目录
                if effective_hidden:
                    dirs[:] = [d for d in dirs if d not in CORE_IGNORE_DIRS]
                else:
                    dirs[:] = [d for d in dirs if d not in DEFAULT_IGNORE_DIRS and not d.startswith(".")]

                for fname in files:
                    if not effective_hidden and fname.startswith("."):
                        continue
                    if file_pattern and not fnmatch.fnmatch(fname, file_pattern):
                        continue
                    files_to_check.append(os.path.join(root, fname))

        for fpath in files_to_check:
            if is_binary_file(fpath):
                continue

            rel_path = os.path.relpath(fpath, self.workspace_dir).replace("\\", "/")
            try:
                with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                    file_matches = []
                    for line_no, line in enumerate(f, start=1):
                        if regex.search(line):
                            clean_line = line.rstrip("\r\n")
                            if len(clean_line) > 200:
                                clean_line = clean_line[:200] + "..."
                            file_matches.append(f"  {line_no}: {clean_line}")
                            total_matches += 1
                            if total_matches >= max_results:
                                break

                    if file_matches:
                        matches_by_file[rel_path] = file_matches

                if total_matches >= max_results:
                    break
            except Exception:
                continue

        return matches_by_file, total_matches


class GlobTool(BaseTool):
    """文件名与目录模式快速匹配工具"""
    name = "glob"
    description = (
        "在工作区中使用路径感知通配符模式 (如 *.py 仅匹配当前层级，**/*.py 跨层级递归，src/**/*.ts) 快速搜索文件与目录路径。"
        "支持返回匹配的文件与目录 (目录以 / 结尾)。自动排除 .git, node_modules, .venv 等干扰目录。"
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
                        "pattern": {
                            "type": "string",
                            "description": "通配符模式 (例如 '*.py', '**/*.py', 'mini_agent/*.py', 'mini_agent/*')",
                        },
                        "path": {
                            "type": "string",
                            "description": "可选。起始搜索相对目录，默认为当前工作区根目录",
                        },
                        "include_hidden": {
                            "type": "boolean",
                            "description": "可选。是否搜索隐藏目录与隐藏文件 (以 '.' 开头，如 .github)，默认为 False",
                        },
                        "case_sensitive": {
                            "type": "boolean",
                            "description": "可选。是否区分大小写，默认为 False",
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "可选。最大返回路径数，默认为 100",
                        },
                    },
                    "required": ["pattern"],
                },
            },
        }

    async def execute(
        self,
        pattern: str,
        path: Optional[str] = None,
        include_hidden: bool = False,
        case_sensitive: bool = False,
        max_results: int = 100,
        **kwargs: Any,
    ) -> ToolResult:
        if not pattern:
            return ToolResult(content="错误: pattern 模式不能为空。", is_error=True)

        target_root, err_msg = resolve_safe_workspace_path(self.workspace_dir, path)
        if err_msg or not target_root:
            return ToolResult(content=err_msg or "错误: 无效路径", is_error=True)

        is_hidden_target = os.path.basename(target_root).startswith(".") or any(
            part.startswith(".") for part in os.path.relpath(target_root, self.workspace_dir).split(os.sep) if part != "."
        )
        effective_hidden = include_hidden or is_hidden_target

        regex, match_dir_only = glob_to_path_regex(pattern, case_sensitive=case_sensitive)

        matched_paths = await asyncio.to_thread(
            self._sync_glob_paths,
            target_root,
            effective_hidden,
            regex,
            match_dir_only,
            max_results,
        )

        if not matched_paths:
            return ToolResult(
                content=f"📁 未找到匹配模式 '{pattern}' 的路径 (范围: {path or '.'})",
                is_error=False,
                details={"pattern": pattern, "matched_count": 0},
            )

        matched_paths.sort()
        output_lines = [f"📁 找到 {len(matched_paths)} 个匹配项 (模式: '{pattern}'):"]
        for p in matched_paths:
            output_lines.append(f"  {p}")

        if len(matched_paths) >= max_results:
            output_lines.append(f"\n⚠️ 已达到最大结果上限 ({max_results} 个)，更多项已省略。")

        return ToolResult(
            content="\n".join(output_lines),
            is_error=False,
            details={"pattern": pattern, "matched_count": len(matched_paths)},
        )

    def _sync_glob_paths(
        self,
        target_root: str,
        effective_hidden: bool,
        regex: re.Pattern,
        match_dir_only: bool,
        max_results: int,
    ) -> List[str]:
        """在后台工作线程执行目录与文件 Glob 匹配"""
        matched_paths: List[str] = []

        # 如果 target_root 是单个文件
        if os.path.isfile(target_root):
            rel_to_target = os.path.basename(target_root)
            rel_to_ws = os.path.relpath(target_root, self.workspace_dir).replace("\\", "/")
            if regex.match(rel_to_target) and not match_dir_only:
                matched_paths.append(rel_to_ws)
        else:
            # 遍历工作区目录
            for root, dirs, files in os.walk(target_root):
                # 剪枝排除干扰目录
                if effective_hidden:
                    dirs[:] = [d for d in dirs if d not in CORE_IGNORE_DIRS]
                else:
                    dirs[:] = [d for d in dirs if d not in DEFAULT_IGNORE_DIRS and not d.startswith(".")]

                # 1. 匹配当前遍历层级中的目录
                for dname in dirs:
                    full_dpath = os.path.join(root, dname)
                    rel_to_target = os.path.relpath(full_dpath, target_root).replace("\\", "/")
                    rel_to_ws = os.path.relpath(full_dpath, self.workspace_dir).replace("\\", "/")
                    if regex.match(rel_to_target):
                        matched_paths.append(rel_to_ws + "/")
                        if len(matched_paths) >= max_results:
                            break
                if len(matched_paths) >= max_results:
                    break

                # 2. 匹配当前遍历层级中的文件 (若模式未强制要求为目录)
                if not match_dir_only:
                    for fname in files:
                        if not effective_hidden and fname.startswith("."):
                            continue
                        full_fpath = os.path.join(root, fname)
                        rel_to_target = os.path.relpath(full_fpath, target_root).replace("\\", "/")
                        rel_to_ws = os.path.relpath(full_fpath, self.workspace_dir).replace("\\", "/")
                        if regex.match(rel_to_target):
                            matched_paths.append(rel_to_ws)
                            if len(matched_paths) >= max_results:
                                break

                if len(matched_paths) >= max_results:
                    break

        return matched_paths
