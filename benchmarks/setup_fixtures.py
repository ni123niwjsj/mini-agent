#!/usr/bin/env python3
"""初始化 SWE-bench 测试基准所需的基础代码仓库夹具 (Fixtures)。

为每个真实评测任务创建独立的 Git 仓库，包含初始 Bug commit 与验证测试。
"""

import os
import subprocess

BENCHMARKS_DIR = os.path.dirname(os.path.abspath(__file__))
FIXTURES_DIR = os.path.join(BENCHMARKS_DIR, "fixtures")


def run_cmd(cmd: list[str], cwd: str):
    subprocess.run(cmd, cwd=cwd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def setup_flask_repo():
    repo_dir = os.path.join(FIXTURES_DIR, "flask_repo")
    os.makedirs(os.path.join(repo_dir, "src", "flask"), exist_ok=True)
    os.makedirs(os.path.join(repo_dir, "tests"), exist_ok=True)

    # 1. 源码: 存在 Bug 的 Config.from_file (缺少 mode 参数)
    config_py = '''import errno
import typing as t

class Config(dict):
    """Flask 配置类"""
    
    def from_mapping(self, mapping: t.Mapping[str, t.Any]) -> bool:
        for key, value in mapping.items():
            if key.isupper():
                self[key] = value
        return True

    def from_file(
        self,
        filename: str,
        load: t.Callable[[t.Any], t.Mapping[str, t.Any]],
        silent: bool = False,
    ) -> bool:
        """从文件加载配置。
        
        注意：当前实现缺少可配置的 mode 参数，导致需要二进制加载器 (如 tomllib.load) 
        时会因为默认的文本模式 open(filename) 抛出 TypeError。
        """
        try:
            with open(filename) as f:
                obj = load(f)
        except OSError as e:
            if silent and e.errno in (errno.ENOENT, errno.EISDIR):
                return False
            e.strerror = f"Unable to load configuration file ({e.strerror})"
            raise
        return self.from_mapping(obj)
'''
    with open(os.path.join(repo_dir, "src", "flask", "config.py"), "w", encoding="utf-8") as f:
        f.write(config_py)

    with open(os.path.join(repo_dir, "src", "flask", "__init__.py"), "w", encoding="utf-8") as f:
        f.write('from .config import Config\n__version__ = "2.3.0.dev0"\n')

    # 2. 基础测试用例
    test_py = '''import json
import pytest
from flask import Config

def test_config_from_file_json(tmp_path):
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({"SECRET_KEY": "flask-test-secret", "debug": False}))

    c = Config()
    assert c.from_file(str(cfg_file), json.load) is True
    assert c["SECRET_KEY"] == "flask-test-secret"
    assert "debug" not in c
'''
    with open(os.path.join(repo_dir, "tests", "test_config.py"), "w", encoding="utf-8") as f:
        f.write(test_py)

    # 3. 初始化 Git 仓库并创建 base commit
    run_cmd(["git", "init"], repo_dir)
    run_cmd(["git", "config", "user.name", "SWE-bench"], repo_dir)
    run_cmd(["git", "config", "user.email", "eval@swebench.org"], repo_dir)
    run_cmd(["git", "add", "."], repo_dir)
    run_cmd(["git", "commit", "-m", "Initial commit before fix"], repo_dir)
    print("✅ 已初始化 flask_repo 夹具")


def setup_requests_repo():
    repo_dir = os.path.join(FIXTURES_DIR, "requests_repo")
    os.makedirs(os.path.join(repo_dir, "requests"), exist_ok=True)
    os.makedirs(os.path.join(repo_dir, "tests"), exist_ok=True)

    exceptions_py = '''class RequestException(IOError):
    """请求基类异常"""
    pass

class ConnectionError(RequestException):
    """网络连接异常"""
    pass

class ProxyError(ConnectionError):
    """代理连接失败异常"""
    pass
'''
    with open(os.path.join(repo_dir, "requests", "exceptions.py"), "w", encoding="utf-8") as f:
        f.write(exceptions_py)

    adapters_py = '''from .exceptions import ConnectionError, ProxyError

class ProtocolError(Exception):
    """底层协议异常"""
    pass

class HTTPAdapter:
    """HTTP 适配器"""

    def send(self, url: str, proxies: dict = None) -> str:
        """发送请求。
        
        Bug: 当使用 proxies 且底层抛出 ProtocolError 时，
        未正确捕获并转换为标准的 ProxyError，导致上层无法捕获特定异常。
        """
        if proxies:
            # 模拟底层代理连接报错
            raise ProtocolError("Cannot connect to proxy socket")
        return "OK"
'''
    with open(os.path.join(repo_dir, "requests", "adapters.py"), "w", encoding="utf-8") as f:
        f.write(adapters_py)

    with open(os.path.join(repo_dir, "requests", "__init__.py"), "w", encoding="utf-8") as f:
        f.write('from .adapters import HTTPAdapter, ProtocolError\nfrom .exceptions import ProxyError, ConnectionError\n')

    test_py = '''import pytest
from requests import HTTPAdapter

def test_direct_send():
    adapter = HTTPAdapter()
    assert adapter.send("http://example.com") == "OK"
'''
    with open(os.path.join(repo_dir, "tests", "test_requests.py"), "w", encoding="utf-8") as f:
        f.write(test_py)

    run_cmd(["git", "init"], repo_dir)
    run_cmd(["git", "config", "user.name", "SWE-bench"], repo_dir)
    run_cmd(["git", "config", "user.email", "eval@swebench.org"], repo_dir)
    run_cmd(["git", "add", "."], repo_dir)
    run_cmd(["git", "commit", "-m", "Initial commit before fix"], repo_dir)
    print("✅ 已初始化 requests_repo 夹具")


def setup_cache_repo():
    repo_dir = os.path.join(FIXTURES_DIR, "cache_repo")
    os.makedirs(os.path.join(repo_dir, "cache"), exist_ok=True)
    os.makedirs(os.path.join(repo_dir, "tests"), exist_ok=True)

    lru_py = '''import time
from collections import OrderedDict
from typing import Any, Optional

class LRUCache:
    """带容量限制与可选 TTL 过期的 LRU 缓存。"""

    def __init__(self, capacity: int = 100):
        self.capacity = capacity
        self._cache: OrderedDict[str, Any] = OrderedDict()

    def get(self, key: str, default: Any = None) -> Any:
        if key not in self._cache:
            return default
        # 激活命中节点移动到末尾
        self._cache.move_to_end(key)
        return self._cache[key]

    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        """存储缓存。
        
        Bug: 缺少对 ttl 参数的支持与过期淘汰逻辑！
        即使传入了 ttl，缓存也永久有效。
        """
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = value
        if len(self._cache) > self.capacity:
            self._cache.popitem(last=False)
'''
    with open(os.path.join(repo_dir, "cache", "lru.py"), "w", encoding="utf-8") as f:
        f.write(lru_py)

    with open(os.path.join(repo_dir, "cache", "__init__.py"), "w", encoding="utf-8") as f:
        f.write('from .lru import LRUCache\n')

    test_py = '''from cache import LRUCache

def test_lru_eviction():
    c = LRUCache(capacity=2)
    c.set("a", 1)
    c.set("b", 2)
    assert c.get("a") == 1
    c.set("c", 3)
    assert c.get("b") is None
    assert c.get("c") == 3
'''
    with open(os.path.join(repo_dir, "tests", "test_cache.py"), "w", encoding="utf-8") as f:
        f.write(test_py)

    run_cmd(["git", "init"], repo_dir)
    run_cmd(["git", "config", "user.name", "SWE-bench"], repo_dir)
    run_cmd(["git", "config", "user.email", "eval@swebench.org"], repo_dir)
    run_cmd(["git", "add", "."], repo_dir)
    run_cmd(["git", "commit", "-m", "Initial commit before fix"], repo_dir)
    print("✅ 已初始化 cache_repo 夹具")


def setup_ratelimit_repo():
    repo_dir = os.path.join(FIXTURES_DIR, "ratelimit_repo")
    os.makedirs(os.path.join(repo_dir, "ratelimit"), exist_ok=True)
    os.makedirs(os.path.join(repo_dir, "tests"), exist_ok=True)

    bucket_py = '''import time

class TokenBucket:
    """令牌桶限流器。"""

    def __init__(self, capacity: float, refill_rate: float):
        self.capacity = float(capacity)
        self.refill_rate = float(refill_rate)  # 每秒补充的令牌数量
        self.tokens = float(capacity)
        self.last_refill = time.time()

    def consume(self, tokens: float = 1.0) -> bool:
        """消费指定数量的令牌。
        
        Bug: 缺少基于时间差的令牌补充 (refill) 逻辑！
        未根据 (now - last_refill) * refill_rate 增加 tokens，
        导致初始容量耗尽后无法自动恢复。
        """
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False
'''
    with open(os.path.join(repo_dir, "ratelimit", "bucket.py"), "w", encoding="utf-8") as f:
        f.write(bucket_py)

    with open(os.path.join(repo_dir, "ratelimit", "__init__.py"), "w", encoding="utf-8") as f:
        f.write("from .bucket import TokenBucket\n")

    test_py = '''from ratelimit import TokenBucket

def test_initial_consume():
    b = TokenBucket(capacity=2, refill_rate=10)
    assert b.consume(1) is True
    assert b.consume(1) is True
    assert b.consume(1) is False
'''
    with open(os.path.join(repo_dir, "tests", "test_bucket.py"), "w", encoding="utf-8") as f:
        f.write(test_py)

    run_cmd(["git", "init"], repo_dir)
    run_cmd(["git", "config", "user.name", "SWE-bench"], repo_dir)
    run_cmd(["git", "config", "user.email", "eval@swebench.org"], repo_dir)
    run_cmd(["git", "add", "."], repo_dir)
    run_cmd(["git", "commit", "-m", "Initial commit before fix"], repo_dir)
    print("✅ 已初始化 ratelimit_repo 夹具")


def setup_retry_repo():
    repo_dir = os.path.join(FIXTURES_DIR, "retry_repo")
    os.makedirs(os.path.join(repo_dir, "retry"), exist_ok=True)
    os.makedirs(os.path.join(repo_dir, "tests"), exist_ok=True)

    retry_py = '''import functools
import time
from typing import Callable, Tuple, Type

def retry(
    max_attempts: int = 3,
    delay: float = 0.01,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
) -> Callable:
    """重试装饰器。
    
    Bug:
    1. 发生异常时没有按 exceptions 元组过滤，而是盲目捕获了所有 Exception。
    2. 达到最大重试次数后没有将最后一次捕获的异常抛出 (re-raise)，而是隐式返回了 None。
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt < max_attempts - 1:
                        time.sleep(delay)
            return None
        return wrapper
    return decorator
'''
    with open(os.path.join(repo_dir, "retry", "decorator.py"), "w", encoding="utf-8") as f:
        f.write(retry_py)

    with open(os.path.join(repo_dir, "retry", "__init__.py"), "w", encoding="utf-8") as f:
        f.write("from .decorator import retry\n")

    test_py = '''from retry import retry

def test_successful_call():
    calls = 0
    @retry(max_attempts=3)
    def ok():
        nonlocal calls
        calls += 1
        return "success"
    assert ok() == "success"
    assert calls == 1
'''
    with open(os.path.join(repo_dir, "tests", "test_retry.py"), "w", encoding="utf-8") as f:
        f.write(test_py)

    run_cmd(["git", "init"], repo_dir)
    run_cmd(["git", "config", "user.name", "SWE-bench"], repo_dir)
    run_cmd(["git", "config", "user.email", "eval@swebench.org"], repo_dir)
    run_cmd(["git", "add", "."], repo_dir)
    run_cmd(["git", "commit", "-m", "Initial commit before fix"], repo_dir)
    print("✅ 已初始化 retry_repo 夹具")


def setup_sqlparse_repo():
    repo_dir = os.path.join(FIXTURES_DIR, "sqlparse_repo")
    os.makedirs(os.path.join(repo_dir, "sqlparse"), exist_ok=True)
    os.makedirs(os.path.join(repo_dir, "tests"), exist_ok=True)

    sql_py = '''import re

KEYWORDS = {
    "SELECT", "FROM", "WHERE", "JOIN", "ON", "AND", "OR",
    "ORDER", "BY", "GROUP", "LIMIT", "INSERT", "INTO", "VALUES",
    "UPDATE", "SET", "DELETE",
}

def format_sql(sql: str, keyword_case: str = "upper") -> str:
    """格式化 SQL 关键词大小写。
    
    Bug: 使用全局单词正则替换会导致单引号内的字符串字面量 (如 'select') 内部的文本也被误替换为大写。
    在字符串单引号或双引号内部的内容必须严格保持原样，不应被视为关键字。
    """
    for kw in KEYWORDS:
        replacement = kw.upper() if keyword_case == "upper" else kw.lower()
        sql = re.sub(rf"\\b{kw}\\b", replacement, sql, flags=re.IGNORECASE)
    return sql
'''
    with open(os.path.join(repo_dir, "sqlparse", "formatter.py"), "w", encoding="utf-8") as f:
        f.write(sql_py)

    with open(os.path.join(repo_dir, "sqlparse", "__init__.py"), "w", encoding="utf-8") as f:
        f.write("from .formatter import format_sql\n")

    test_py = '''from sqlparse import format_sql

def test_basic_format():
    assert format_sql("select id from tbl") == "SELECT id FROM tbl"
'''
    with open(os.path.join(repo_dir, "tests", "test_sql.py"), "w", encoding="utf-8") as f:
        f.write(test_py)

    run_cmd(["git", "init"], repo_dir)
    run_cmd(["git", "config", "user.name", "SWE-bench"], repo_dir)
    run_cmd(["git", "config", "user.email", "eval@swebench.org"], repo_dir)
    run_cmd(["git", "add", "."], repo_dir)
    run_cmd(["git", "commit", "-m", "Initial commit before fix"], repo_dir)
    print("✅ 已初始化 sqlparse_repo 夹具")


if __name__ == "__main__":
    os.makedirs(FIXTURES_DIR, exist_ok=True)
    setup_flask_repo()
    setup_requests_repo()
    setup_cache_repo()
    setup_ratelimit_repo()
    setup_retry_repo()
    setup_sqlparse_repo()
    print("\n🎉 所有 6 个测试夹具仓库初始化完毕！")


