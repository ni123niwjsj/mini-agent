# 🏆 Mini-Agent SWE-bench Lite 官方基准评测报告 (Official Evaluation)

- **评测时间**: 2026-10-12 21:42:00
- **评估模型**: `deepseek/deepseek-v4.1-flash`
- **评测环境**: 官方 Docker 容器沙箱 (`swebench.harness.run_evaluation`)
- **总测试题目**: 9
- **成功解决 (Resolved)**: 7 / 9 (77.8%)
- **平均交互轮数**: 21.2 轮
- **平均耗时**: 164.5s

## 📊 评测明细总表 (Official Scorecard)

| 题目编号 (Instance ID) | 修复状态 | 官方评测结论 | 耗时 | 轮数 | 工具调用 | 补丁大小 |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| `pallets__flask-4992` | ✅ | 🎉 **PASSED** | 100.8s | 15 | 18 calls | 43 行 |
| `pallets__flask-5063` | ✅ | 🎉 **PASSED** | 319.9s | 25 | 28 calls | 113 行 |
| `pallets__flask-4045` | ❌ | 🔴 **FAIL** | 73.9s | 15 | 19 calls | 28 行 |
| `astropy__astropy-12907` | ✅ | 🎉 **PASSED** | 136.3s | 25 | 26 calls | 13 行 |
| `astropy__astropy-14182` | ✅ | 🎉 **PASSED** | 232.5s | 25 | 29 calls | 31 行 |
| `astropy__astropy-14365` | ❌ | 🔴 **FAIL** | 159.4s | 25 | 26 calls | 13 行 |
| `astropy__astropy-14995` | ✅ | 🎉 **PASSED** | 193.2s | 25 | 30 calls | 13 行 |
| `astropy__astropy-6938` | ✅ | 🎉 **PASSED** | 147.3s | 22 | 23 calls | 13 行 |
| `astropy__astropy-7746` | ✅ | 🎉 **PASSED** | 117.4s | 14 | 18 calls | 32 行 |

## 🔍 官方 Docker 容器评测细节 (Pytest Verification)

### `pallets__flask-4992`
- **官方判定**: 🎉 PASSED (Resolved)
- **运行时指标**: 耗时 100.8s | 交互 15 轮 | 工具调用 18 次 (`grep, read_file, bash, edit_file`)
- **补丁文件**: [`benchmarks/results/patches/pallets__flask-4992.patch`](patches/pallets__flask-4992.patch) (43 行)
- **FAIL_TO_PASS 靶向测试校验**:
  - ✅ `tests/test_config.py::test_config_from_file_toml`: PASSED
- **PASS_TO_PASS 无回归校验**:
  - ✅ 18 项既有单测全部保持通过 (0 broken)
- **Docker 容器完整日志**: [`logs/run_evaluation/mini_agent_official/mini-agent-deepseek/pallets__flask-4992/test_output.txt](../../logs/run_evaluation/mini_agent_official/mini-agent-deepseek/pallets__flask-4992/test_output.txt)

### `pallets__flask-5063`
- **官方判定**: 🎉 PASSED (Resolved)
- **运行时指标**: 耗时 319.9s | 交互 25 轮 | 工具调用 28 次 (`grep, read_file, bash, web_search, web_fetch, edit_file`)
- **补丁文件**: [`benchmarks/results/patches/pallets__flask-5063.patch`](patches/pallets__flask-5063.patch) (113 行)
- **FAIL_TO_PASS 靶向测试校验**:
  - ✅ `tests/test_cli.py::TestRoutes::test_subdomain`: PASSED
  - ✅ `tests/test_cli.py::TestRoutes::test_host`: PASSED
- **PASS_TO_PASS 无回归校验**:
  - ✅ 54 项既有单测全部保持通过 (0 broken)
- **Docker 容器完整日志**: [`logs/run_evaluation/mini_agent_official/mini-agent-deepseek/pallets__flask-5063/test_output.txt](../../logs/run_evaluation/mini_agent_official/mini-agent-deepseek/pallets__flask-5063/test_output.txt)

### `pallets__flask-4045`
- **官方判定**: ❌ FAILED (Unresolved)
- **运行时指标**: 耗时 73.9s | 交互 15 轮 | 工具调用 19 次 (`grep, read_file, edit_file, bash`)
- **补丁文件**: [`benchmarks/results/patches/pallets__flask-4045.patch`](patches/pallets__flask-4045.patch) (28 行)
- **FAIL_TO_PASS 靶向测试校验**:
  - ✅ `tests/test_blueprints.py::test_dotted_name_not_allowed`: PASSED
  - ❌ `tests/test_blueprints.py::test_route_decorator_custom_endpoint_with_dots`: FAILED
- **PASS_TO_PASS 无回归校验**:
  - ✅ 50 项既有单测全部保持通过 (0 broken)
- **Docker 容器完整日志**: [`logs/run_evaluation/mini_agent_official/mini-agent-deepseek/pallets__flask-4045/test_output.txt](../../logs/run_evaluation/mini_agent_official/mini-agent-deepseek/pallets__flask-4045/test_output.txt)

### `astropy__astropy-12907`
- **官方判定**: 🎉 PASSED (Resolved)
- **运行时指标**: 耗时 136.3s | 交互 25 轮 | 工具调用 26 次 (`read_file, bash, edit_file`)
- **补丁文件**: [`benchmarks/results/patches/astropy__astropy-12907.patch`](patches/astropy__astropy-12907.patch) (13 行)
- **FAIL_TO_PASS 靶向测试校验**:
  - ✅ `astropy/modeling/tests/test_separable.py::test_separable[compound_model6-result6]`: PASSED
  - ✅ `astropy/modeling/tests/test_separable.py::test_separable[compound_model9-result9]`: PASSED
- **PASS_TO_PASS 无回归校验**:
  - ✅ 13 项既有单测全部保持通过 (0 broken)
- **Docker 容器完整日志**: [`logs/run_evaluation/mini_agent_official/mini-agent-deepseek/astropy__astropy-12907/test_output.txt](../../logs/run_evaluation/mini_agent_official/mini-agent-deepseek/astropy__astropy-12907/test_output.txt)

### `astropy__astropy-14182`
- **官方判定**: 🎉 PASSED (Resolved)
- **运行时指标**: 耗时 232.5s | 交互 25 轮 | 工具调用 29 次 (`bash, read_file, web_fetch, web_search, edit_file`)
- **补丁文件**: [`benchmarks/results/patches/astropy__astropy-14182.patch`](patches/astropy__astropy-14182.patch) (31 行)
- **FAIL_TO_PASS 靶向测试校验**:
  - ✅ `astropy/io/ascii/tests/test_rst.py::test_rst_with_header_rows`: PASSED
- **PASS_TO_PASS 无回归校验**:
  - ✅ 9 项既有单测全部保持通过 (0 broken)
- **Docker 容器完整日志**: [`logs/run_evaluation/mini_agent_official/mini-agent-deepseek/astropy__astropy-14182/test_output.txt](../../logs/run_evaluation/mini_agent_official/mini-agent-deepseek/astropy__astropy-14182/test_output.txt)

### `astropy__astropy-14365`
- **官方判定**: ❌ FAILED (Unresolved)
- **运行时指标**: 耗时 159.4s | 交互 25 轮 | 工具调用 26 次 (`grep, glob, read_file, edit_file, bash`)
- **补丁文件**: [`benchmarks/results/patches/astropy__astropy-14365.patch`](patches/astropy__astropy-14365.patch) (13 行)
- **FAIL_TO_PASS 靶向测试校验**:
  - ❌ `astropy/io/ascii/tests/test_qdp.py::test_roundtrip[True]`: FAILED
- **PASS_TO_PASS 无回归校验**:
  - ✅ 8 项既有单测全部保持通过 (0 broken)
- **Docker 容器完整日志**: [`logs/run_evaluation/mini_agent_official/mini-agent-deepseek/astropy__astropy-14365/test_output.txt](../../logs/run_evaluation/mini_agent_official/mini-agent-deepseek/astropy__astropy-14365/test_output.txt)

### `astropy__astropy-14995`
- **官方判定**: 🎉 PASSED (Resolved)
- **运行时指标**: 耗时 193.2s | 交互 25 轮 | 工具调用 30 次 (`glob, grep, bash, read_file, edit_file, web_search, web_fetch`)
- **补丁文件**: [`benchmarks/results/patches/astropy__astropy-14995.patch`](patches/astropy__astropy-14995.patch) (13 行)
- **FAIL_TO_PASS 靶向测试校验**:
  - ✅ `astropy/nddata/mixins/tests/test_ndarithmetic.py::test_nddata_bitmask_arithmetic`: PASSED
- **PASS_TO_PASS 无回归校验**:
  - ✅ 179 项既有单测全部保持通过 (0 broken)
- **Docker 容器完整日志**: [`logs/run_evaluation/mini_agent_official/mini-agent-deepseek/astropy__astropy-14995/test_output.txt](../../logs/run_evaluation/mini_agent_official/mini-agent-deepseek/astropy__astropy-14995/test_output.txt)

### `astropy__astropy-6938`
- **官方判定**: 🎉 PASSED (Resolved)
- **运行时指标**: 耗时 147.3s | 交互 22 轮 | 工具调用 23 次 (`grep, read_file, bash, web_search, web_fetch, edit_file`)
- **补丁文件**: [`benchmarks/results/patches/astropy__astropy-6938.patch`](patches/astropy__astropy-6938.patch) (13 行)
- **FAIL_TO_PASS 靶向测试校验**:
  - ✅ `astropy/io/fits/tests/test_checksum.py::TestChecksumFunctions::test_ascii_table_data`: PASSED
  - ✅ `astropy/io/fits/tests/test_table.py::TestTableFunctions::test_ascii_table`: PASSED
- **PASS_TO_PASS 无回归校验**:
  - ✅ 11 项既有单测全部保持通过 (0 broken)
- **Docker 容器完整日志**: [`logs/run_evaluation/mini_agent_official/mini-agent-deepseek/astropy__astropy-6938/test_output.txt](../../logs/run_evaluation/mini_agent_official/mini-agent-deepseek/astropy__astropy-6938/test_output.txt)

### `astropy__astropy-7746`
- **官方判定**: 🎉 PASSED (Resolved)
- **运行时指标**: 耗时 117.4s | 交互 14 轮 | 工具调用 18 次 (`grep, read_file, bash, web_fetch, edit_file`)
- **补丁文件**: [`benchmarks/results/patches/astropy__astropy-7746.patch`](patches/astropy__astropy-7746.patch) (32 行)
- **FAIL_TO_PASS 靶向测试校验**:
  - ✅ `astropy/wcs/tests/test_wcs.py::test_zero_size_input`: PASSED
- **PASS_TO_PASS 无回归校验**:
  - ✅ 56 项既有单测全部保持通过 (0 broken)
- **Docker 容器完整日志**: [`logs/run_evaluation/mini_agent_official/mini-agent-deepseek/astropy__astropy-7746/test_output.txt](../../logs/run_evaluation/mini_agent_official/mini-agent-deepseek/astropy__astropy-7746/test_output.txt)

