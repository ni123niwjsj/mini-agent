#!/usr/bin/env python3
"""Mini-Agent SWE-bench 评测主入口脚本。

功能：
1. 自动发现 benchmarks/tasks/*.json 中的测试用例。
2. 调度 BenchmarkRunner 运行 Mini-Agent 解决问题并提取 git diff 补丁。
3. 调度 BenchmarkEvaluator 应用补丁并执行真实 pytest 单元测试验证。
4. 汇总胜率 (Resolved Rate %)、Token 消耗、交互轮数与工具调用指标，输出 Markdown / JSON 报表。

用法：
  python3 benchmarks/run_benchmark.py --all
  python3 benchmarks/run_benchmark.py --task flask_4992
  python3 benchmarks/run_benchmark.py --eval-only  # 仅重新评测已保存的 patches
"""

import argparse
import asyncio
import glob
import json
import os
import sys
import time
from dataclasses import asdict
from typing import Any, Dict, List

BENCHMARKS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BENCHMARKS_DIR)

# 自动无缝切换至 .venv 虚拟环境 Python (若存在且当前未处于该环境中)
venv_dir = os.path.join(PROJECT_ROOT, ".venv")
venv_python = os.path.join(venv_dir, "bin", "python")
if os.path.exists(venv_python) and sys.prefix != os.path.abspath(venv_dir):
    os.environ["VIRTUAL_ENV"] = venv_dir
    os.execv(venv_python, [venv_python] + sys.argv)

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def load_env():
    """强制优先从项目根目录加载 .env 配置"""
    env_file = os.path.join(PROJECT_ROOT, ".env")
    if os.path.exists(env_file):
        try:
            from dotenv import load_dotenv
            load_dotenv(env_file)
        except Exception:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'\"")
                        if k not in os.environ:
                            os.environ[k] = v


load_env()

from benchmarks.evaluator import BenchmarkEvaluator
from benchmarks.runner import BenchmarkRunner, RunResult

TASKS_DIR = os.path.join(BENCHMARKS_DIR, "tasks")
RESULTS_DIR = os.path.join(BENCHMARKS_DIR, "results")
PATCHES_DIR = os.path.join(RESULTS_DIR, "patches")


def parse_args():
    parser = argparse.ArgumentParser(description="Mini-Agent SWE-bench 评测基准套件")
    parser.add_argument(
        "--all", "-a",
        action="store_true",
        help="评测全部任务 (等价于 --task all)",
    )
    parser.add_argument(
        "--task",
        type=str,
        default="all",
        help="指定评测的任务名称或文件名 (例如 flask_4992，默认为 all 全部执行)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=os.getenv("MINI_AGENT_MODEL", "mock"),
        help="指定评测的大模型 (默认读取环境变量 MINI_AGENT_MODEL)",
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=25,
        help="单个任务最大允许轮数 (默认 25)",
    )
    parser.add_argument(
        "--eval-only",
        action="store_true",
        help="仅评测现有 patches，不重复发起 Agent 推理",
    )
    args = parser.parse_args()
    if args.all:
        args.task = "all"
    return args



def load_tasks(task_arg: str) -> List[Dict[str, Any]]:
    tasks = []
    if task_arg == "all":
        pattern = os.path.join(TASKS_DIR, "*.json")
        for f in sorted(glob.glob(pattern)):
            with open(f, "r", encoding="utf-8") as fp:
                tasks.append(json.load(fp))
    else:
        name = task_arg if task_arg.endswith(".json") else f"{task_arg}.json"
        target_path = os.path.join(TASKS_DIR, name)
        if not os.path.exists(target_path):
            # 尝试直接按绝对/相对路径加载
            target_path = task_arg
        if not os.path.exists(target_path):
            raise FileNotFoundError(f"找不到指定的任务文件: {task_arg}")
        with open(target_path, "r", encoding="utf-8") as fp:
            tasks.append(json.load(fp))
    return tasks


def generate_markdown_report(summary: Dict[str, Any], results: List[Dict[str, Any]]) -> str:
    md = [
        "# 🏆 Mini-Agent SWE-bench 基准评测报告\n",
        f"- **评测时间**: {summary['timestamp']}",
        f"- **评估模型**: `{summary['model']}`",
        f"- **总测试题目**: {summary['total_tasks']}",
        f"- **成功解决 (Resolved)**: {summary['resolved_tasks']} / {summary['total_tasks']} ({summary['resolved_rate']:.1f}%)",
        f"- **平均轮数**: {summary['avg_turns']:.1f} 轮",
        f"- **平均耗时**: {summary['avg_duration']:.2f}s\n",
        "## 📊 评测明细总表\n",
        "| 题目编号 (Instance ID) | 修复状态 | 评测结论 | 轮数 | 耗时 | 工具调用 | 补丁大小 |",
        "| :--- | :---: | :---: | :---: | :---: | :--- | :---: |",
    ]

    for r in results:
        iid = r["instance_id"]
        status_icon = "✅" if r.get("agent_status") == "SUCCESS" else "❌"
        resolved_icon = "🟢 **PASS**" if r.get("resolved") else "🔴 **FAIL**"
        turns = r.get("turns", 0)
        dur = f"{r.get('duration_seconds', 0):.1f}s"
        tools = ", ".join(set(r.get("tool_calls", []))) or "无"
        patch_lines = len(r.get("patch_content", "").strip().splitlines())
        md.append(f"| `{iid}` | {status_icon} | {resolved_icon} | {turns} | {dur} | `{tools}` | {patch_lines} 行 |")

    md.append("\n## 🔍 用例测试细节\n")
    for r in results:
        iid = r["instance_id"]
        md.append(f"### `{iid}`")
        md.append(f"- **解决状态**: {'已解决 (Resolved)' if r.get('resolved') else '未解决'}")
        if r.get("fail_to_pass"):
            md.append("- **FAIL_TO_PASS 校验**:")
            for t_name, t_stat in r["fail_to_pass"].items():
                mark = "✅" if t_stat == "PASSED" else "❌"
                md.append(f"  - {mark} `{t_name}`: {t_stat}")
        if r.get("pass_to_pass"):
            md.append("- **PASS_TO_PASS 校验**:")
            for t_name, t_stat in r["pass_to_pass"].items():
                mark = "✅" if t_stat == "PASSED" else "❌"
                md.append(f"  - {mark} `{t_name}`: {t_stat}")
        if r.get("patch_error"):
            md.append(f"- **补丁错误**: `{r['patch_error']}`")
        md.append("")

    return "\n".join(md)


async def main():
    args = parse_args()
    tasks = load_tasks(args.task)

    if not tasks:
        print("⚠️ 未找到任何评测任务！请检查 benchmarks/tasks/ 目录。")
        return

    print("=" * 70)
    print("🧪 Mini-Agent SWE-bench 评测套件")
    print(f"📌 模型: {args.model}")
    print(f"📋 任务数: {len(tasks)}")
    print(f"⚙️ 模式: {'仅补丁评测 (eval-only)' if args.eval_only else '完整推理 + 评测'}")
    print("=" * 70)

    runner = BenchmarkRunner(
        model=args.model,
        max_turns=args.max_turns,
    )
    evaluator = BenchmarkEvaluator()

    final_results = []
    total_resolved = 0
    total_duration = 0.0
    total_turns = 0

    for idx, task in enumerate(tasks, 1):
        instance_id = task["instance_id"]
        print(f"\n[{idx}/{len(tasks)}] 正在评测任务: {instance_id} ...")

        patch_content = ""
        run_res: Dict[str, Any] = {}

        if not args.eval_only:
            run_data = await runner.run_task(task, verbose=True)
            patch_content = run_data.patch_content
            run_res = asdict(run_data)
        else:
            patch_file = os.path.join(PATCHES_DIR, f"{instance_id}.patch")
            if os.path.exists(patch_file):
                with open(patch_file, "r", encoding="utf-8") as fp:
                    patch_content = fp.read()

            meta_file = os.path.join(RESULTS_DIR, f"{instance_id}.meta.json")
            if os.path.exists(meta_file):
                with open(meta_file, "r", encoding="utf-8") as fp:
                    run_res = json.load(fp)
            else:
                run_res = {
                    "instance_id": instance_id,
                    "status": "SUCCESS" if patch_content else "EMPTY",
                    "duration_seconds": 0.0,
                    "turns": 0,
                    "tool_calls": [],
                    "patch_path": patch_file,
                }
            run_res["patch_content"] = patch_content


        # 执行评测
        eval_res = evaluator.evaluate(task, patch_content)

        is_resolved = eval_res.get("resolved", False)
        if is_resolved:
            total_resolved += 1

        turns = run_res.get("turns", 0)
        dur = run_res.get("duration_seconds", 0.0)
        total_turns += turns
        total_duration += dur

        combined = {
            "instance_id": instance_id,
            "resolved": is_resolved,
            "agent_status": run_res.get("status"),
            "turns": turns,
            "duration_seconds": dur,
            "tool_calls": run_res.get("tool_calls", []),
            "tokens": run_res.get("tokens", {}),
            "patch_content": patch_content,
            "patch_applied": eval_res.get("patch_applied", False),
            "patch_error": eval_res.get("patch_error"),
            "fail_to_pass": eval_res.get("fail_to_pass", {}),
            "pass_to_pass": eval_res.get("pass_to_pass", {}),
        }
        final_results.append(combined)

        icon = "🎉 PASSED (Resolved)" if is_resolved else "❌ FAILED"
        print(f"👉 评测判定: {icon}")

    resolved_rate = (total_resolved / len(tasks)) * 100 if tasks else 0
    avg_turns = total_turns / len(tasks) if tasks else 0
    avg_duration = total_duration / len(tasks) if tasks else 0

    summary = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "model": args.model,
        "total_tasks": len(tasks),
        "resolved_tasks": total_resolved,
        "resolved_rate": resolved_rate,
        "avg_turns": avg_turns,
        "avg_duration": avg_duration,
    }

    # 打印总结终端看板
    print("\n" + "=" * 70)
    print("📊 评测汇总结果 (SWE-bench Scorecard)")
    print("=" * 70)
    print(f"🎯 胜率 (Resolved Rate): {total_resolved}/{len(tasks)} ({resolved_rate:.1f}%)")
    print(f"⏱️ 平均耗时: {avg_duration:.2f}s | 平均轮数: {avg_turns:.1f} 轮")
    print("-" * 70)
    print(f"{'Instance ID':<26} | {'Resolved?':<10} | {'Turns':<6} | {'Duration':<8} | {'Tools'}")
    print("-" * 70)
    for r in final_results:
        res_str = "YES ✅" if r["resolved"] else "NO ❌"
        dur_str = f"{r['duration_seconds']:.1f}s"
        tools_str = f"{len(r['tool_calls'])} calls"
        print(f"{r['instance_id']:<26} | {res_str:<10} | {r['turns']:<6} | {dur_str:<8} | {tools_str}")
    print("=" * 70)

    # 导出报告
    os.makedirs(RESULTS_DIR, exist_ok=True)
    report_json_path = os.path.join(RESULTS_DIR, "report.json")
    with open(report_json_path, "w", encoding="utf-8") as fp:
        json.dump({"summary": summary, "results": final_results}, fp, indent=2, ensure_ascii=False)

    report_md_path = os.path.join(RESULTS_DIR, "report.md")
    md_content = generate_markdown_report(summary, final_results)
    with open(report_md_path, "w", encoding="utf-8") as fp:
        fp.write(md_content)

    print(f"📄 评测报告已生成:")
    print(f"  - Markdown: {report_md_path}")
    print(f"  - JSON:     {report_json_path}\n")


if __name__ == "__main__":
    asyncio.run(main())
