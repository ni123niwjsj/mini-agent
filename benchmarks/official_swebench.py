#!/usr/bin/env python3
"""SWE-bench 官方标准评测适配桥接器 (Official SWE-bench Bridge)。

功能：
1. 本地任务与预测导出 (--export-preds)：
   将 Mini-Agent 评测生成的补丁自动导出为 SWE-bench 官方标准的 predictions.jsonl 格式。
2. 官方数据集探索 (--list-tasks)：
   浏览已本地缓存的 300 道 SWE-bench Lite 官方测试题目与所属仓库。
3. 官方题目导入 (--import-task <instance_id>)：
   将官方数据集中的真实 GitHub Issue 导入至 benchmarks/tasks/ 中，供 Mini-Agent 直接推理解决。
4. 官方 Docker 评测入口 (--eval-official)：
   调用 swebench.harness.run_evaluation 执行官方标准的 Docker 沙箱隔离评测并产出官方榜单战报。
"""

import argparse
import glob
import json
import os
import subprocess
import sys
from typing import Any, Dict, List, Optional

BENCHMARKS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BENCHMARKS_DIR)

# 自动无缝切换至 .venv 虚拟环境 Python
venv_dir = os.path.join(PROJECT_ROOT, ".venv")
venv_python = os.path.join(venv_dir, "bin", "python")
if os.path.exists(venv_python) and sys.prefix != os.path.abspath(venv_dir):
    os.environ["VIRTUAL_ENV"] = venv_dir
    os.execv(venv_python, [venv_python] + sys.argv)

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

TASKS_DIR = os.path.join(BENCHMARKS_DIR, "tasks")
RESULTS_DIR = os.path.join(BENCHMARKS_DIR, "results")
PATCHES_DIR = os.path.join(RESULTS_DIR, "patches")
PREDICTIONS_FILE = os.path.join(RESULTS_DIR, "predictions.jsonl")


def get_dataset():
    """加载本地缓存的 SWE-bench Lite 评测数据集 (300 题)"""
    os.environ["HF_DATASETS_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    from datasets import load_dataset
    try:
        return load_dataset("SWE-bench/SWE-bench_Lite", split="test")
    except Exception:
        os.environ.pop("HF_DATASETS_OFFLINE", None)
        return load_dataset("SWE-bench/SWE-bench_Lite", split="test")


def export_predictions(model_name: str = "mini-agent-deepseek", instance_ids: Optional[List[str]] = None) -> str:
    """将 results/patches/*.patch 转换为官方 predictions.jsonl，自动排除非官方测试任务"""
    os.makedirs(RESULTS_DIR, exist_ok=True)
    patches = glob.glob(os.path.join(PATCHES_DIR, "*.patch"))
    exported = 0

    try:
        ds = get_dataset()
        valid_official_ids = set(item["instance_id"] for item in ds)
    except Exception:
        valid_official_ids = None

    with open(PREDICTIONS_FILE, "w", encoding="utf-8") as out:
        for p_file in sorted(patches):
            filename = os.path.basename(p_file)
            iid = filename[:-6] if filename.endswith(".patch") else filename

            if instance_ids and iid not in instance_ids:
                continue

            if valid_official_ids is not None and iid not in valid_official_ids:
                continue

            with open(p_file, "r", encoding="utf-8") as pf:
                patch_content = pf.read()

            record = {
                "instance_id": iid,
                "model_patch": patch_content,
                "model_name_or_path": model_name,
            }
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
            exported += 1

    print(f"✅ 成功导出 {exported} 条官方补丁预测至: {PREDICTIONS_FILE}")
    return PREDICTIONS_FILE


def list_tasks(repo_filter: Optional[str] = None):
    """列出官方 SWE-bench Lite 题目"""
    ds = get_dataset()
    print("=" * 80)
    print(f"📋 官方 SWE-bench Lite 任务集 (共 {len(ds)} 题)")
    print("=" * 80)

    count = 0
    for item in ds:
        repo = item["repo"]
        iid = item["instance_id"]
        if repo_filter and repo_filter.lower() not in repo.lower():
            continue
        problem_snippet = item["problem_statement"].strip().splitlines()[0][:65]
        print(f"[{repo:<25}] {iid:<35} | {problem_snippet}...")
        count += 1

    print("-" * 80)
    print(f"共列出 {count} 个任务 (筛选: {repo_filter or '全部'})")


def import_task(instance_id: str):
    """从官方数据集导入单个任务为 tasks/<instance_id>.json"""
    ds = get_dataset()
    match = None
    for item in ds:
        if item["instance_id"] == instance_id:
            match = item
            break

    if not match:
        print(f"❌ 未找到官方任务: {instance_id}")
        return

    repo_short = match["repo"].split("/")[-1]
    task_data = {
        "instance_id": match["instance_id"],
        "repo_name": f"{repo_short}_repo",
        "official_repo": match["repo"],
        "base_commit": match["base_commit"],
        "version": match.get("version", ""),
        "problem_statement": match["problem_statement"],
        "hints_text": match.get("hints_text", ""),
        "test_patch": match["test_patch"],
        "FAIL_TO_PASS": json.loads(match["FAIL_TO_PASS"]) if isinstance(match["FAIL_TO_PASS"], str) else match["FAIL_TO_PASS"],
        "PASS_TO_PASS": json.loads(match["PASS_TO_PASS"]) if isinstance(match["PASS_TO_PASS"], str) else match["PASS_TO_PASS"],
    }

    out_file = os.path.join(TASKS_DIR, f"{instance_id}.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(task_data, f, indent=2, ensure_ascii=False)

    print(f"🎉 成功导入官方任务至: {out_file}")
    print(f"  - 仓库: {match['repo']}")
    print(f"  - Base Commit: {match['base_commit'][:10]}")
    print(f"  - FAIL_TO_PASS 校验测试数: {len(task_data['FAIL_TO_PASS'])}")


def run_official_evaluation(instance_ids: Optional[List[str]] = None, run_id: str = "mini_agent_run"):
    """调用 swebench.harness.run_evaluation 执行官方 Docker 容器评测"""
    print(f"📦 正在导出待评测的官方补丁...")
    export_predictions(instance_ids=instance_ids)

    cmd = [
        sys.executable,
        "-m",
        "swebench.harness.run_evaluation",
        "--dataset_name",
        "SWE-bench/SWE-bench_Lite",
        "--predictions_path",
        PREDICTIONS_FILE,
        "--run_id",
        run_id,
        "--report_dir",
        RESULTS_DIR,
    ]

    if instance_ids:
        cmd.extend(["--instance_ids"] + instance_ids)

    print("=" * 80)
    print("🐳 启动官方 SWE-bench Docker 评测 harness ...")
    print("指令:", " ".join(cmd))
    print("=" * 80)

    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"\n❌ 官方评测执行异常 (退出码 {e.returncode})")
        print("💡 常见提示: 如果报错 'permission denied ... /var/run/docker.sock'，")
        print("   请在终端运行: sudo chmod 666 /var/run/docker.sock 赋予 Docker 权限后重试。")
    except Exception as e:
        print(f"❌ 运行报错: {e}")


def main():
    parser = argparse.ArgumentParser(description="SWE-bench 官方评测桥接器")
    parser.add_argument("--export-preds", action="store_true", help="将当前生成的补丁导出为官方 predictions.jsonl")
    parser.add_argument("--list-tasks", nargs="?", const="all", help="列出官方题目 (可选仓库过滤，如 flask, requests, django)")
    parser.add_argument("--import-task", type=str, help="从官方数据集导入指定 instance_id 至 benchmarks/tasks/")
    parser.add_argument("--eval-official", action="store_true", help="调用官方 swebench.harness.run_evaluation 执行 Docker 评测")
    parser.add_argument("--instance-ids", nargs="+", help="官方评测时指定的目标 instance_id 列表")
    parser.add_argument("--run-id", type=str, default="mini_agent_official", help="评测标识 ID")

    args = parser.parse_args()

    if args.export_preds:
        export_predictions()
    elif args.list_tasks:
        rf = None if args.list_tasks == "all" else args.list_tasks
        list_tasks(rf)
    elif args.import_task:
        import_task(args.import_task)
    elif args.eval_official:
        run_official_evaluation(instance_ids=args.instance_ids, run_id=args.run_id)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
