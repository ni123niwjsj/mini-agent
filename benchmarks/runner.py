"""SWE-bench 推理运行器 (Runner)。

负责为指定评测任务实例化 MiniAgent，在干净的工作目录中执行代码定位、修改和验证，
并最终提取 git diff 补丁文本存储至 results/patches/。
"""

import asyncio
import json
import os
import shutil
import subprocess
import time
import sys
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

BENCHMARKS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BENCHMARKS_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from mini_agent.agent import MiniAgent
from mini_agent.ai.client import LLMClient
from mini_agent.core.events import (
    AgentEnd,
    AgentStart,
    AssistantDelta,
    AssistantMessage,
    Error,
    ToolCallStart,
    ToolResult,
)

BENCHMARKS_DIR = os.path.dirname(os.path.abspath(__file__))
FIXTURES_DIR = os.path.join(BENCHMARKS_DIR, "fixtures")
WORKSPACES_DIR = os.path.join(BENCHMARKS_DIR, "workspaces")
RESULTS_DIR = os.path.join(BENCHMARKS_DIR, "results")
PATCHES_DIR = os.path.join(RESULTS_DIR, "patches")


@dataclass
class RunResult:
    """单个任务的执行结果统计"""
    instance_id: str
    status: str  # "SUCCESS", "MAX_TURNS", "ERROR"
    duration_seconds: float
    turns: int
    tool_calls: List[str] = field(default_factory=list)
    tokens: Dict[str, int] = field(default_factory=lambda: {"prompt": 0, "completion": 0, "total": 0})
    patch_path: Optional[str] = None
    patch_content: str = ""
    error_message: Optional[str] = None
    agent_summary: str = ""


class BenchmarkRunner:
    """Mini-Agent 基准评测执行器"""

    def __init__(
        self,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        max_turns: int = 15,
        fixtures_dir: Optional[str] = None,
    ):
        self.model = model
        self.base_url = base_url
        self.api_key = api_key
        self.max_turns = max_turns
        self.fixtures_dir = fixtures_dir or FIXTURES_DIR

        os.makedirs(WORKSPACES_DIR, exist_ok=True)
        os.makedirs(PATCHES_DIR, exist_ok=True)

    def prepare_workspace(self, task: Dict[str, Any]) -> str:
        """为任务创建干净的工作副本"""
        instance_id = task["instance_id"]
        official_repo = task.get("official_repo")
        base_commit = task.get("base_commit")

        ws_path = os.path.join(WORKSPACES_DIR, instance_id)
        if os.path.exists(ws_path):
            shutil.rmtree(ws_path)

        # 优先检测官方仓库镜像
        if official_repo:
            repo_short = official_repo.split("/")[-1]
            official_dir = os.path.join(self.fixtures_dir, "official", repo_short)
            if os.path.exists(official_dir):
                shutil.copytree(official_dir, ws_path)
                if base_commit:
                    subprocess.run(
                        ["git", "checkout", "-f", base_commit],
                        cwd=ws_path,
                        check=True,
                        capture_output=True,
                    )
                    subprocess.run(
                        ["git", "clean", "-fdx"],
                        cwd=ws_path,
                        check=True,
                        capture_output=True,
                    )
                return ws_path

        repo_name = task.get("repo_name", "")
        fixture_repo = os.path.join(self.fixtures_dir, repo_name)
        if not os.path.exists(fixture_repo):
            raise FileNotFoundError(f"Fixture 仓库不存在: {fixture_repo}")

        shutil.copytree(fixture_repo, ws_path)
        if base_commit:
            try:
                subprocess.run(
                    ["git", "checkout", "-f", base_commit],
                    cwd=ws_path,
                    check=True,
                    capture_output=True,
                )
                subprocess.run(
                    ["git", "clean", "-fdx"],
                    cwd=ws_path,
                    check=True,
                    capture_output=True,
                )
            except Exception:
                pass
        return ws_path

    async def run_task(
        self,
        task: Dict[str, Any],
        verbose: bool = True,
    ) -> RunResult:
        """运行单个 SWE-bench 任务并抽取生成的补丁"""
        instance_id = task["instance_id"]
        ws_path = self.prepare_workspace(task)

        client = LLMClient(
            api_key=self.api_key,
            base_url=self.base_url,
            model=self.model,
        )

        agent = MiniAgent(
            client=client,
            workspace_dir=ws_path,
            sessions_dir=None,  # 测试基准运行使用无状态会话
            max_turns=self.max_turns,
        )

        prompt = (
            f"You are an expert software engineer resolving an issue in this repository.\n\n"
            f"=== Problem Description ===\n"
            f"{task['problem_statement']}\n\n"
            f"=== Instructions ===\n"
            f"1. Explore the codebase using grep, glob, or read_file to inspect the relevant files.\n"
            f"2. Modify the code to fix the issue using edit_file or write_file.\n"
            f"3. Verify your changes via git diff. (Note: Third-party dependencies for running full test suites are evaluated in Docker containers; focus on analyzing the root cause, applying the clean minimal fix, and checking git diff).\n"
            f"4. Do NOT modify tests or commit git changes. Only edit the source code required to fix the issue.\n"
            f"5. When completed, briefly summarize the fix.\n"
        )

        start_time = time.time()
        turns = 0
        tool_calls = []
        token_stats = {"prompt": 0, "completion": 0, "total": 0}
        agent_summary = ""
        status = "SUCCESS"
        error_msg = None

        if verbose:
            print(f"\n🚀 开始执行任务: {instance_id}")
            print(f"📁 工作空间: {ws_path}")
            print("-" * 60)

        try:
            async for event in agent.stream(prompt):
                if isinstance(event, ToolCallStart):
                    tool_calls.append(event.tool_name)
                    if verbose:
                        args_preview = str(event.arguments)
                        if len(args_preview) > 80:
                            args_preview = args_preview[:77] + "..."
                        print(f"  🔧 [{event.tool_name}] {args_preview}")

                elif isinstance(event, ToolResult):
                    if event.is_error and verbose:
                        print(f"     ⚠️ 工具报错: {str(event.output)[:80]}")

                elif isinstance(event, AssistantMessage):
                    turns += 1
                    if event.usage:
                        u = event.usage
                        token_stats["prompt"] += getattr(u, "prompt_tokens", 0) or 0
                        token_stats["completion"] += getattr(u, "completion_tokens", 0) or 0
                        token_stats["total"] += getattr(u, "total_tokens", 0) or 0

                elif isinstance(event, AgentEnd):
                    agent_summary = event.final_response
                    if verbose:
                        print(f"  🏁 Agent 执行完成 (共 {event.total_turns} 轮)")

                elif isinstance(event, Error):
                    status = "ERROR"
                    error_msg = str(event.message)
                    if verbose:
                        print(f"  ❌ 发生错误: {error_msg}")

        except Exception as e:
            status = "ERROR"
            error_msg = str(e)
            if verbose:
                print(f"  💥 运行异常: {e}")

        duration = time.time() - start_time

        # 从工作空间提取 git diff，严格排除 pyc 与 __pycache__ 二进制编译缓存
        diff_res = subprocess.run(
            ["git", "diff", "--", ".", ":!*.pyc", ":!*__pycache__*"],
            cwd=ws_path,
            text=True,
            capture_output=True,
        )
        raw_patch = diff_res.stdout
        clean_blocks = []
        for block in raw_patch.split("diff --git "):
            if not block.strip() or "Binary files " in block or ".pyc" in block:
                continue
            clean_blocks.append("diff --git " + block)
        patch_content = "".join(clean_blocks)

        patch_file = os.path.join(PATCHES_DIR, f"{instance_id}.patch")
        with open(patch_file, "w", encoding="utf-8") as f:
            f.write(patch_content)

        if verbose:
            patch_lines = len(patch_content.strip().splitlines()) if patch_content.strip() else 0
            print(f"💾 补丁已保存至: {patch_file} ({patch_lines} 行)")
            print(f"⏱️ 耗时: {duration:.2f}s | 交互轮数: {turns} | 工具调用: {len(tool_calls)} 次")
            print("-" * 60)

        run_result = RunResult(
            instance_id=instance_id,
            status=status,
            duration_seconds=duration,
            turns=turns,
            tool_calls=tool_calls,
            tokens=token_stats,
            patch_path=patch_file,
            patch_content=patch_content,
            error_message=error_msg,
            agent_summary=agent_summary,
        )

        meta_file = os.path.join(RESULTS_DIR, f"{instance_id}.meta.json")
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(asdict(run_result), f, indent=2, ensure_ascii=False)

        return run_result

