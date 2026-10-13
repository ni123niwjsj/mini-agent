# 🏆 Mini-Agent SWE-bench 基准评测报告

- **评测时间**: 2026-10-13 16:02:32
- **评估模型**: `deepseek/deepseek-v4.1-flash`
- **总测试题目**: 1
- **成功解决 (Resolved)**: 0 / 1 (0.0%)
- **平均轮数**: 11.0 轮
- **平均耗时**: 71.52s

## 📊 评测明细总表

| 题目编号 (Instance ID) | 修复状态 | 评测结论 | 轮数 | 耗时 | 工具调用 | 补丁大小 |
| :--- | :---: | :---: | :---: | :---: | :--- | :---: |
| `mwaskom__seaborn-3010` | ✅ | 🔴 **FAIL** | 11 | 71.5s | `grep, read_file, edit_file, bash` | 13 行 |

## 🔍 用例测试细节

### `mwaskom__seaborn-3010`
- **解决状态**: 未解决
- **FAIL_TO_PASS 校验**:
  - ❌ `tests/_stats/test_regression.py::TestPolyFit::test_missing_data`: FAILED
- **PASS_TO_PASS 校验**:
  - ❌ `tests/_stats/test_regression.py::TestPolyFit::test_no_grouper`: FAILED
  - ❌ `tests/_stats/test_regression.py::TestPolyFit::test_one_grouper`: FAILED
