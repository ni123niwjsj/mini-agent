"""SWE-bench 测评器 (Evaluator)。

负责将 Agent 生成的代码补丁 (.patch) 以及任务的验证测试补丁 (test_patch) 应用到干净的代码仓库中，
执行测试并判定是否成功解决 (Resolved)。
"""

import os
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Dict, List, Optional


BENCHMARKS_DIR = os.path.dirname(os.path.abspath(__file__))
FIXTURES_DIR = os.path.join(BENCHMARKS_DIR, "fixtures")


class BenchmarkEvaluator:
    """自动化补丁应用与测试评测引擎"""

    def __init__(self, fixtures_dir: Optional[str] = None):
        self.fixtures_dir = fixtures_dir or FIXTURES_DIR

    def evaluate(
        self,
        task: Dict[str, Any],
        patch_content: str,
        work_dir: Optional[str] = None,
    ) -> Dict[str, Any]:
        """评测单个任务。
        
        Args:
            task: 任务元数据 (包含 repo_name, test_patch, FAIL_TO_PASS, PASS_TO_PASS 等)
            patch_content: Agent 修复生成的 git diff 补丁文本
            work_dir: 可选的评测工作目录；若未指定则自动创建并在结束后清理
        """
        instance_id = task.get("instance_id", "unknown")
        repo_name = task.get("repo_name", "")
        official_repo = task.get("official_repo")
        base_commit = task.get("base_commit")

        fixture_path = os.path.join(self.fixtures_dir, repo_name)
        if official_repo:
            repo_short = official_repo.split("/")[-1]
            official_dir = os.path.join(self.fixtures_dir, "official", repo_short)
            if os.path.exists(official_dir):
                fixture_path = official_dir

        if not os.path.exists(fixture_path):
            return {
                "instance_id": instance_id,
                "resolved": False,
                "error": f"Fixture 仓库不存在: {fixture_path}",
            }

        temp_dir = None
        eval_workspace = work_dir
        if not eval_workspace:
            temp_dir = tempfile.mkdtemp(prefix=f"eval_{instance_id}_")
            eval_workspace = temp_dir

        try:
            # 1. 复制一份完全干净的 Git 仓库到评估沙箱
            target_repo = os.path.join(eval_workspace, repo_name)
            if os.path.exists(target_repo):
                shutil.rmtree(target_repo)
            shutil.copytree(fixture_path, target_repo)

            if base_commit:
                try:
                    subprocess.run(
                        ["git", "checkout", "-f", base_commit],
                        cwd=target_repo,
                        check=True,
                        capture_output=True,
                    )
                    subprocess.run(
                        ["git", "clean", "-fdx"],
                        cwd=target_repo,
                        check=True,
                        capture_output=True,
                    )
                except Exception:
                    pass

            # 2. 应用 Agent 生成的代码修复补丁 (过滤可能的二进制 pyc 编译块)
            patch_applied = True
            patch_err = None
            if patch_content and patch_content.strip():
                clean_blocks = []
                for block in patch_content.split("diff --git "):
                    if not block.strip() or "Binary files " in block or ".pyc" in block:
                        continue
                    clean_blocks.append("diff --git " + block)
                usable_patch = "".join(clean_blocks)

                p = subprocess.run(
                    ["git", "apply", "--whitespace=nowarn", "-"],
                    input=usable_patch,
                    cwd=target_repo,
                    text=True,
                    capture_output=True,
                )
                if p.returncode != 0:
                    patch_applied = False
                    patch_err = p.stderr or "git apply 失败"

            # 3. 应用任务自带的测试集补丁 (test_patch)
            test_patch = task.get("test_patch", "")
            if test_patch and test_patch.strip():
                p = subprocess.run(
                    ["git", "apply", "--whitespace=nowarn", "-"],
                    input=test_patch,
                    cwd=target_repo,
                    text=True,
                    capture_output=True,
                )
                if p.returncode != 0:
                    return {
                        "instance_id": instance_id,
                        "resolved": False,
                        "patch_applied": patch_applied,
                        "error": f"应用 test_patch 失败: {p.stderr}",
                    }

            # 4. 执行测试用例
            # 优先使用 .venv 中的 pytest，若无则使用 sys.executable -m pytest
            pytest_bin = os.path.join(BENCHMARKS_DIR, "..", ".venv", "bin", "pytest")
            if not os.path.exists(pytest_bin):
                pytest_bin = "pytest"

            fail_to_pass_tests: List[str] = task.get("FAIL_TO_PASS", [])
            pass_to_pass_tests: List[str] = task.get("PASS_TO_PASS", [])
            target_tests = list(fail_to_pass_tests) + list(pass_to_pass_tests)

            test_args = [pytest_bin, "-v", "--color=no", "--tb=short"]
            if target_tests:
                test_args.extend(target_tests)
            else:
                test_args.append("tests")

            env = os.environ.copy()
            src_dir = os.path.join(target_repo, "src")
            env["PYTHONPATH"] = f"{src_dir}:{target_repo}:" + env.get("PYTHONPATH", "")

            test_run = subprocess.run(
                test_args,
                cwd=target_repo,
                env=env,
                text=True,
                capture_output=True,
            )

            test_output = test_run.stdout + "\n" + test_run.stderr

            # 5. 分析 FAIL_TO_PASS 与 PASS_TO_PASS 状态
            fail_to_pass_tests: List[str] = task.get("FAIL_TO_PASS", [])
            pass_to_pass_tests: List[str] = task.get("PASS_TO_PASS", [])

            f2p_results: Dict[str, str] = {}
            for t in fail_to_pass_tests:
                # 检查测试用例是否输出 PASSED
                if f"{t} PASSED" in test_output:
                    f2p_results[t] = "PASSED"
                else:
                    f2p_results[t] = "FAILED"

            p2p_results: Dict[str, str] = {}
            for t in pass_to_pass_tests:
                if f"{t} PASSED" in test_output:
                    p2p_results[t] = "PASSED"
                else:
                    p2p_results[t] = "FAILED"

            # 判定标准：所有 FAIL_TO_PASS 必须全部 PASSED，且所有 PASS_TO_PASS 保持 PASSED
            all_f2p_passed = bool(fail_to_pass_tests and all(res == "PASSED" for res in f2p_results.values()))
            all_p2p_passed = bool(all(res == "PASSED" for res in p2p_results.values())) if pass_to_pass_tests else True
            resolved = all_f2p_passed and all_p2p_passed and patch_applied

            return {
                "instance_id": instance_id,
                "resolved": resolved,
                "patch_applied": patch_applied,
                "patch_error": patch_err,
                "fail_to_pass": f2p_results,
                "pass_to_pass": p2p_results,
                "all_f2p_passed": all_f2p_passed,
                "all_p2p_passed": all_p2p_passed,
                "exit_code": test_run.returncode,
                "test_output": test_output.strip(),
            }

        finally:
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)

