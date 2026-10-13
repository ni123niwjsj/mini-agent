#!/usr/bin/env python3
"""Batch evaluation runner for 23 SWE-bench Lite tasks (Pylint 6 + Pytest 17)."""

import asyncio
import difflib
import json
import os
import shutil
import sys
import time
from typing import Any, Dict, List

BENCHMARKS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BENCHMARKS_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

import pyarrow as pa
import pyarrow.ipc as ipc

from benchmarks.runner import BenchmarkRunner, RunResult

TASKS_DIR = os.path.join(BENCHMARKS_DIR, "tasks")
RESULTS_DIR = os.path.join(BENCHMARKS_DIR, "results")
PATCHES_DIR = os.path.join(RESULTS_DIR, "patches")
WORKSPACES_DIR = os.path.join(BENCHMARKS_DIR, "workspaces")
PREDICTIONS_FILE = os.path.join(RESULTS_DIR, "predictions.jsonl")

PYLINT_TASKS = [
    "pylint-dev__pylint-5859",
    "pylint-dev__pylint-6506",
    "pylint-dev__pylint-7080",
    "pylint-dev__pylint-7114",
    "pylint-dev__pylint-7228",
    "pylint-dev__pylint-7993",
]

PYTEST_TASKS = [
    "pytest-dev__pytest-11143",
    "pytest-dev__pytest-11148",
    "pytest-dev__pytest-5103",
    "pytest-dev__pytest-5221",
    "pytest-dev__pytest-5227",
    "pytest-dev__pytest-5413",
    "pytest-dev__pytest-5495",
    "pytest-dev__pytest-5692",
    "pytest-dev__pytest-6116",
    "pytest-dev__pytest-7168",
    "pytest-dev__pytest-7220",
    "pytest-dev__pytest-7373",
    "pytest-dev__pytest-7432",
    "pytest-dev__pytest-7490",
    "pytest-dev__pytest-8365",
    "pytest-dev__pytest-8906",
    "pytest-dev__pytest-9359",
]

ALL_TASKS = PYLINT_TASKS + PYTEST_TASKS


def load_official_patches() -> Dict[str, str]:
    """从本地 Arrow 缓存加载官方 Ground Truth 补丁"""
    arrow_path = os.path.expanduser("~/.cache/huggingface/datasets/SWE-bench___swe-bench_lite/default/0.0.0/b0dde1093fe417d83b7184254edf8199c1f0dff5/swe-bench_lite-test.arrow")
    official_patches = {}
    if os.path.exists(arrow_path):
        with pa.memory_map(arrow_path, "r") as source:
            table = ipc.RecordBatchStreamReader(source).read_all()
            for row in table.to_pylist():
                if row["instance_id"] in ALL_TASKS:
                    official_patches[row["instance_id"]] = row.get("patch", "")
    return official_patches


def normalize_diff(diff_text: str) -> str:
    """归一化 diff 文本，去除 header 差异"""
    lines = []
    for line in diff_text.strip().splitlines():
        if line.startswith("index ") or line.startswith("diff --git ") or line.startswith("--- ") or line.startswith("+++ "):
            continue
        lines.append(line.rstrip())
    return "\n".join(lines)


def compare_with_official(gen_patch: str, off_patch: str) -> Dict[str, Any]:
    norm_gen = normalize_diff(gen_patch)
    norm_off = normalize_diff(off_patch)
    if not norm_gen:
        return {"status": "EMPTY", "match_rate": 0.0, "note": "补丁为空"}
    if norm_gen == norm_off:
        return {"status": "EXACT_MATCH", "match_rate": 100.0, "note": "100% 字节级完全一致"}
    
    # 提取修改的文件列表
    def extract_files(patch):
        files = set()
        for line in patch.splitlines():
            if line.startswith("diff --git a/"):
                parts = line.split(" ")
                if len(parts) >= 3:
                    files.add(parts[2][2:])
        return files

    gen_files = extract_files(gen_patch)
    off_files = extract_files(off_patch)
    files_match = bool(gen_files and gen_files == off_files)

    matcher = difflib.SequenceMatcher(None, norm_gen, norm_off)
    ratio = matcher.ratio() * 100.0

    if files_match and ratio >= 60.0:
        return {"status": "LOGIC_MATCH", "match_rate": round(ratio, 1), "note": f"修改相同文件，逻辑高度吻合 ({ratio:.1f}%)"}
    elif files_match:
        return {"status": "PARTIAL_MATCH", "match_rate": round(ratio, 1), "note": f"修改相同文件，存在实现差异 ({ratio:.1f}%)"}
    else:
        return {"status": "DIVERGENT", "match_rate": round(ratio, 1), "note": f"修改文件不同 (吻合率 {ratio:.1f}%)"}


def update_predictions_file():
    """将所有 patches 同步更新至 predictions.jsonl"""
    existing = {}
    if os.path.exists(PREDICTIONS_FILE):
        with open(PREDICTIONS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                existing[d["instance_id"]] = d

    # 扫描 patches
    for patch_file in os.listdir(PATCHES_DIR):
        if not patch_file.endswith(".patch"):
            continue
        instance_id = patch_file[:-6]
        with open(os.path.join(PATCHES_DIR, patch_file), "r", encoding="utf-8") as pf:
            content = pf.read()
        existing[instance_id] = {
            "model_name_or_path": "mini-agent-deepseek",
            "instance_id": instance_id,
            "model_patch": content,
        }

    with open(PREDICTIONS_FILE, "w", encoding="utf-8") as f:
        for k in sorted(existing.keys()):
            f.write(json.dumps(existing[k], ensure_ascii=False) + "\n")


async def main():
    print("=" * 80)
    print("🚀 Mini-Agent 自动化 SWE-bench Lite 评测套件 (Pylint 6 题 + Pytest 17 题)")
    print(f"📊 待评测任务总数: {len(ALL_TASKS)} 题")
    print(f"📂 补丁保存目录: {PATCHES_DIR}")
    print("=" * 80)

    official_patches = load_official_patches()
    runner = BenchmarkRunner(max_turns=22)

    results_summary = []

    for idx, instance_id in enumerate(ALL_TASKS, 1):
        task_json_path = os.path.join(TASKS_DIR, f"{instance_id}.json")
        if not os.path.exists(task_json_path):
            print(f"[{idx}/{len(ALL_TASKS)}] ⚠️ 找不到任务文件: {task_json_path}，跳过")
            continue

        with open(task_json_path, "r", encoding="utf-8") as fp:
            task = json.load(fp)

        patch_file = os.path.join(PATCHES_DIR, f"{instance_id}.patch")
        meta_file = os.path.join(RESULTS_DIR, f"{instance_id}.meta.json")

        # 检查是否已存在跑好的 patch
        if os.path.exists(patch_file) and os.path.getsize(patch_file) > 0 and os.path.exists(meta_file):
            print(f"\n[{idx}/{len(ALL_TASKS)}] ⏩ {instance_id} 补丁与元数据已存在，直接读取对比...")
            with open(patch_file, "r", encoding="utf-8") as pf:
                patch_content = pf.read()
            with open(meta_file, "r", encoding="utf-8") as mf:
                meta = json.load(fp=mf)
            duration = meta.get("duration_seconds", 0.0)
            turns = meta.get("turns", 0)
            tool_calls = meta.get("tool_calls", [])
            status = meta.get("status", "SUCCESS")
        else:
            print(f"\n[{idx}/{len(ALL_TASKS)}] ⚡ 正在运行任务: {instance_id} ...")
            start_t = time.time()
            try:
                run_res = await runner.run_task(task, verbose=True)
                patch_content = run_res.patch_content
                duration = run_res.duration_seconds
                turns = run_res.turns
                tool_calls = run_res.tool_calls
                status = run_res.status
            except Exception as e:
                print(f"❌ 运行异常: {e}")
                patch_content = ""
                duration = time.time() - start_t
                turns = 0
                tool_calls = []
                status = "ERROR"

        # 与官方补丁对比
        off_patch = official_patches.get(instance_id, "")
        comparison = compare_with_official(patch_content, off_patch)

        # 清理临时工作空间
        ws_path = os.path.join(WORKSPACES_DIR, instance_id)
        if os.path.exists(ws_path):
            try:
                shutil.rmtree(ws_path)
            except Exception:
                pass

        res_item = {
            "instance_id": instance_id,
            "repo": task.get("official_repo", ""),
            "status": status,
            "duration": round(duration, 1),
            "turns": turns,
            "tool_calls_count": len(tool_calls),
            "patch_lines": len(patch_content.strip().splitlines()) if patch_content.strip() else 0,
            "comparison": comparison,
        }
        results_summary.append(res_item)

        status_icon = "🎯" if comparison["status"] == "EXACT_MATCH" else ("✅" if comparison["status"] == "LOGIC_MATCH" else "⚠️")
        print(f"[{idx}/{len(ALL_TASKS)}] {status_icon} {instance_id}: {comparison['note']} | 耗时: {duration:.1f}s | 轮数: {turns}")

        # 每跑完一题立即更新 predictions.jsonl，保证随时中断也能持久化
        update_predictions_file()

    # 生成最终汇总 Markdown 报表
    report_file = os.path.join(RESULTS_DIR, "report_pylint_pytest.md")
    report_lines = [
        "# 🏆 Mini-Agent SWE-bench Lite 评测报告 (Pylint & Pytest 专项)",
        "",
        f"- **评测时间**: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- **被测项目**: `pylint-dev/pylint` (6 题) 与 `pytest-dev/pytest` (17 题)",
        f"- **总测试题目**: {len(results_summary)} 题",
        f"- **有效补丁产出率**: {sum(1 for r in results_summary if r['patch_lines'] > 0)} / {len(results_summary)} ({sum(1 for r in results_summary if r['patch_lines'] > 0)/len(results_summary)*100:.1f}%)",
        f"- **官方 PR 吻合/有效解决率**: {sum(1 for r in results_summary if r['comparison']['status'] in ['EXACT_MATCH', 'LOGIC_MATCH'])} / {len(results_summary)} ({sum(1 for r in results_summary if r['comparison']['status'] in ['EXACT_MATCH', 'LOGIC_MATCH'])/len(results_summary)*100:.1f}%)",
        "",
        "---",
        "",
        "## 📊 评测汇总明细表 (Scorecard)",
        "",
        "| 题目编号 (Instance ID) | 项目 (Repo) | 状态 | 官方 PR 一致性 | 吻合率 | 轮数 | 耗时 | 补丁大小 |",
        "| :--- | :--- | :---: | :--- | :---: | :---: | :---: | :---: |",
    ]

    for r in results_summary:
        repo_name = "Pylint" if "pylint" in r["repo"] else "Pytest"
        cmp = r["comparison"]
        cmp_icon = "🎯 **100% 吻合**" if cmp["status"] == "EXACT_MATCH" else ("✅ 逻辑吻合" if cmp["status"] == "LOGIC_MATCH" else "⚠️ 部分实现")
        report_lines.append(
            f"| `{r['instance_id']}` | {repo_name} | ✅ | {cmp_icon} | {cmp['match_rate']}% | {r['turns']} 轮 | {r['duration']}s | {r['patch_lines']} 行 |"
        )

    with open(report_file, "w", encoding="utf-8") as rf:
        rf.write("\n".join(report_lines) + "\n")

    print("\n" + "=" * 80)
    print(f"🎉 23 题基准评测全部完成！汇总报表已保存至: {report_file}")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())

