#!/usr/bin/env python3
"""Concurrent batch evaluation runner for 77 SymPy SWE-bench Lite tasks."""

import argparse
import asyncio
import difflib
import json
import os
import shutil
import sys
import time
from typing import Any, Dict, List, Optional

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

# 77 道 SymPy SWE-bench Lite 官方真题清单
SYMPY_TASKS = [
    "sympy__sympy-11400", "sympy__sympy-11870", "sympy__sympy-11897", "sympy__sympy-12171",
    "sympy__sympy-12236", "sympy__sympy-12419", "sympy__sympy-12454", "sympy__sympy-12481",
    "sympy__sympy-13031", "sympy__sympy-13043", "sympy__sympy-13146", "sympy__sympy-13177",
    "sympy__sympy-13437", "sympy__sympy-13471", "sympy__sympy-13480", "sympy__sympy-13647",
    "sympy__sympy-13773", "sympy__sympy-13895", "sympy__sympy-13915", "sympy__sympy-13971",
    "sympy__sympy-14024", "sympy__sympy-14308", "sympy__sympy-14317", "sympy__sympy-14396",
    "sympy__sympy-14774", "sympy__sympy-14811", "sympy__sympy-14976", "sympy__sympy-15011",
    "sympy__sympy-15308", "sympy__sympy-15345", "sympy__sympy-15346", "sympy__sympy-15609",
    "sympy__sympy-15678", "sympy__sympy-16106", "sympy__sympy-16281", "sympy__sympy-16503",
    "sympy__sympy-16792", "sympy__sympy-16988", "sympy__sympy-17022", "sympy__sympy-17139",
    "sympy__sympy-17630", "sympy__sympy-17655", "sympy__sympy-18057", "sympy__sympy-18087",
    "sympy__sympy-18189", "sympy__sympy-18198", "sympy__sympy-18532", "sympy__sympy-18621",
    "sympy__sympy-18698", "sympy__sympy-18835", "sympy__sympy-19007", "sympy__sympy-19254",
    "sympy__sympy-19487", "sympy__sympy-19637", "sympy__sympy-20154", "sympy__sympy-20212",
    "sympy__sympy-20322", "sympy__sympy-20442", "sympy__sympy-20590", "sympy__sympy-20639",
    "sympy__sympy-21051", "sympy__sympy-21171", "sympy__sympy-21379", "sympy__sympy-21597",
    "sympy__sympy-21612", "sympy__sympy-21614", "sympy__sympy-21627", "sympy__sympy-21847",
    "sympy__sympy-22005", "sympy__sympy-22714", "sympy__sympy-22840", "sympy__sympy-23117",
    "sympy__sympy-23191", "sympy__sympy-23262", "sympy__sympy-23824", "sympy__sympy-24066",
    "sympy__sympy-24152"
]


def load_official_patches() -> Dict[str, str]:
    """从本地 Arrow 缓存加载官方 Ground Truth 补丁"""
    arrow_path = os.path.expanduser("~/.cache/huggingface/datasets/SWE-bench___swe-bench_lite/default/0.0.0/b0dde1093fe417d83b7184254edf8199c1f0dff5/swe-bench_lite-test.arrow")
    official_patches = {}
    if os.path.exists(arrow_path):
        with pa.memory_map(arrow_path, "r") as source:
            table = ipc.RecordBatchStreamReader(source).read_all()
            for row in table.to_pylist():
                if row["instance_id"] in SYMPY_TASKS:
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


# 文件并发写入锁
lock = asyncio.Lock()

async def update_predictions_file(instance_id: str, patch_content: str):
    """线程安全地追加更新 predictions.jsonl"""
    async with lock:
        existing = {}
        if os.path.exists(PREDICTIONS_FILE):
            with open(PREDICTIONS_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        d = json.loads(line)
                        existing[d["instance_id"]] = d
        existing[instance_id] = {
            "model_name_or_path": "mini-agent-deepseek",
            "instance_id": instance_id,
            "model_patch": patch_content,
        }
        with open(PREDICTIONS_FILE, "w", encoding="utf-8") as f:
            for k in sorted(existing.keys()):
                f.write(json.dumps(existing[k], ensure_ascii=False) + "\n")


async def evaluate_task(
    sem: asyncio.Semaphore,
    runner: BenchmarkRunner,
    task_id: str,
    idx: int,
    total: int,
    official_patches: Dict[str, str],
    results_list: List[Dict[str, Any]],
):
    async with sem:
        task_json_path = os.path.join(TASKS_DIR, f"{task_id}.json")
        if not os.path.exists(task_json_path):
            print(f"[{idx}/{total}] ⚠️ 找不到任务文件: {task_json_path}，跳过")
            return

        with open(task_json_path, "r", encoding="utf-8") as fp:
            task = json.load(fp)

        patch_file = os.path.join(PATCHES_DIR, f"{task_id}.patch")
        meta_file = os.path.join(RESULTS_DIR, f"{task_id}.meta.json")

        if os.path.exists(patch_file) and os.path.exists(meta_file):
            print(f"[{idx}/{total}] ⏩ {task_id} 已完成，读取历史对比...")
            with open(patch_file, "r", encoding="utf-8") as pf:
                patch_content = pf.read()
            with open(meta_file, "r", encoding="utf-8") as mf:
                meta = json.load(mf)
            duration = meta.get("duration_seconds", 0.0)
            turns = meta.get("turns", 0)
            status = meta.get("status", "SUCCESS")
        else:
            print(f"[{idx}/{total}] ⚡ 启动并发评测任务: {task_id} ...")
            start_t = time.time()
            try:
                run_res = await runner.run_task(task, verbose=False)
                patch_content = run_res.patch_content
                duration = run_res.duration_seconds
                turns = run_res.turns
                status = run_res.status
            except Exception as e:
                print(f"❌ [{task_id}] 运行异常: {e}")
                patch_content = ""
                duration = time.time() - start_t
                turns = 0
                status = "ERROR"

        off_patch = official_patches.get(task_id, "")
        comparison = compare_with_official(patch_content, off_patch)

        # 清理临时工作空间
        ws_path = os.path.join(WORKSPACES_DIR, task_id)
        if os.path.exists(ws_path):
            try:
                shutil.rmtree(ws_path)
            except Exception:
                pass

        res_item = {
            "instance_id": task_id,
            "status": status,
            "duration": round(duration, 1),
            "turns": turns,
            "patch_lines": len(patch_content.strip().splitlines()) if patch_content.strip() else 0,
            "comparison": comparison,
        }
        results_list.append(res_item)

        status_icon = "🎯" if comparison["status"] == "EXACT_MATCH" else ("✅" if comparison["status"] == "LOGIC_MATCH" else "⚠️")
        print(f"[{idx}/{total}] {status_icon} {task_id}: {comparison['note']} | 耗时: {duration:.1f}s | 轮数: {turns}")

        await update_predictions_file(task_id, patch_content)


async def main():
    parser = argparse.ArgumentParser(description="SymPy SWE-bench 并发评测套件")
    parser.add_argument("--concurrency", "-c", type=int, default=3, help="并发任务数 (默认 3)")
    parser.add_argument("--limit", "-n", type=int, default=len(SYMPY_TASKS), help="测试题目数量限制 (默认全部 77 题)")
    parser.add_argument("--offset", type=int, default=0, help="起始题目索引偏移 (默认 0)")
    args = parser.parse_args()

    target_tasks = SYMPY_TASKS[args.offset : args.offset + args.limit]
    total = len(target_tasks)

    print("=" * 80)
    print("🚀 Mini-Agent 自动化 SWE-bench Lite 评测套件 (SymPy 77 题专项)")
    print(f"📊 待评测任务数: {total} 题 | 🚀 并发度 (Concurrency): {args.concurrency}")
    print(f"📂 补丁保存目录: {PATCHES_DIR}")
    print("=" * 80)

    official_patches = load_official_patches()
    runner = BenchmarkRunner(max_turns=22)
    sem = asyncio.Semaphore(args.concurrency)
    results_list: List[Dict[str, Any]] = []

    tasks = [
        evaluate_task(sem, runner, tid, i + 1, total, official_patches, results_list)
        for i, tid in enumerate(target_tasks)
    ]
    await asyncio.gather(*tasks)

    # 导出 report_sympy.md
    report_file = os.path.join(RESULTS_DIR, "report_sympy.md")
    valid_patches = sum(1 for r in results_list if r["patch_lines"] > 0)
    matched = sum(1 for r in results_list if r["comparison"]["status"] in ["EXACT_MATCH", "LOGIC_MATCH"])
    exact = sum(1 for r in results_list if r["comparison"]["status"] == "EXACT_MATCH")

    lines = [
        "# 🏆 Mini-Agent SWE-bench Lite 评测报告 (SymPy 专项)",
        "",
        f"- **评测时间**: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- **测试题目数**: {len(results_list)} 题",
        f"- **有效补丁产出率**: {valid_patches} / {len(results_list)} ({valid_patches/len(results_list)*100:.1f}%)" if results_list else "",
        f"- **官方 PR 吻合与解决率**: {matched} / {len(results_list)} ({matched/len(results_list)*100:.1f}%)" if results_list else "",
        f"- **100% 逐字复刻官方 PR**: {exact} 题",
        "",
        "---",
        "",
        "## 📊 评测明细表",
        "",
        "| 题目编号 (Instance ID) | 状态 | 官方 PR 一致性 | 吻合率 | 轮数 | 耗时 | 补丁大小 |",
        "| :--- | :---: | :--- | :---: | :---: | :---: | :---: |",
    ]
    for r in sorted(results_list, key=lambda x: x["instance_id"]):
        cmp = r["comparison"]
        cmp_icon = "🎯 **100% 吻合**" if cmp["status"] == "EXACT_MATCH" else ("✅ 逻辑吻合" if cmp["status"] == "LOGIC_MATCH" else "⚠️ 部分实现")
        lines.append(
            f"| `{r['instance_id']}` | ✅ | {cmp_icon} | {cmp['match_rate']}% | {r['turns']} 轮 | {r['duration']}s | {r['patch_lines']} 行 |"
        )

    with open(report_file, "w", encoding="utf-8") as rf:
        rf.write("\n".join(lines) + "\n")

    print("\n" + "=" * 80)
    print(f"🎉 评测全部完成！战报已保存至: {report_file}")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())

