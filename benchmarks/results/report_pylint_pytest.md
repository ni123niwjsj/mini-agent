# 🏆 Mini-Agent SWE-bench Lite 评测报告 (Pylint & Pytest 专项)

- **评测时间**: 2026-10-13 19:51:45
- **被测项目**: `pylint-dev/pylint` (6 题) 与 `pytest-dev/pytest` (17 题)
- **总测试题目**: 23 题
- **有效补丁产出率**: 22 / 23 (95.7%)
- **官方 PR 吻合/有效解决率**: 20 / 23 (87.0%)

---

## 📊 评测汇总明细表 (Scorecard)

| 题目编号 (Instance ID) | 项目 (Repo) | 状态 | 官方 PR 一致性 | 吻合率 | 轮数 | 耗时 | 补丁大小 |
| :--- | :--- | :---: | :--- | :---: | :---: | :---: | :---: |
| `pylint-dev__pylint-5859` | Pylint | ✅ | ✅ 逻辑吻合 | 95.5% | 17 轮 | 116.8s | 15 行 |
| `pylint-dev__pylint-6506` | Pylint | ✅ | 🎯 **100% 吻合** | 100.0% | 18 轮 | 114.5s | 14 行 |
| `pylint-dev__pylint-7080` | Pylint | ✅ | ⚠️ 部分实现 | 60.4% | 22 轮 | 130.6s | 28 行 |
| `pylint-dev__pylint-7114` | Pylint | ✅ | ⚠️ 部分实现 | 0.0% | 22 轮 | 133.0s | 0 行 |
| `pylint-dev__pylint-7228` | Pylint | ✅ | ✅ 逻辑吻合 | 94.8% | 22 轮 | 112.4s | 35 行 |
| `pylint-dev__pylint-7993` | Pylint | ✅ | ✅ 逻辑吻合 | 88.2% | 11 轮 | 64.8s | 13 行 |
| `pytest-dev__pytest-11143` | Pytest | ✅ | ✅ 逻辑吻合 | 89.8% | 11 轮 | 52.8s | 12 行 |
| `pytest-dev__pytest-11148` | Pytest | ✅ | 🎯 **100% 吻合** | 100.0% | 22 轮 | 153.9s | 13 行 |
| `pytest-dev__pytest-5103` | Pytest | ✅ | ✅ 逻辑吻合 | 86.3% | 22 轮 | 139.3s | 41 行 |
| `pytest-dev__pytest-5221` | Pytest | ✅ | 🎯 **100% 吻合** | 100.0% | 22 轮 | 150.2s | 28 行 |
| `pytest-dev__pytest-5227` | Pytest | ✅ | ⚠️ 部分实现 | 53.4% | 20 轮 | 81.0s | 26 行 |
| `pytest-dev__pytest-5413` | Pytest | ✅ | ✅ 逻辑吻合 | 96.4% | 13 轮 | 60.1s | 18 行 |
| `pytest-dev__pytest-5495` | Pytest | ✅ | ✅ 逻辑吻合 | 96.3% | 22 轮 | 128.2s | 43 行 |
| `pytest-dev__pytest-5692` | Pytest | ✅ | ✅ 逻辑吻合 | 81.6% | 15 轮 | 60.8s | 24 行 |
| `pytest-dev__pytest-6116` | Pytest | ✅ | 🎯 **100% 吻合** | 100.0% | 7 轮 | 24.8s | 12 行 |
| `pytest-dev__pytest-7168` | Pytest | ✅ | 🎯 **100% 吻合** | 100.0% | 17 轮 | 91.7s | 11 行 |
| `pytest-dev__pytest-7220` | Pytest | ✅ | ✅ 逻辑吻合 | 95.7% | 20 轮 | 109.8s | 28 行 |
| `pytest-dev__pytest-7373` | Pytest | ✅ | ✅ 逻辑吻合 | 76.6% | 18 轮 | 89.8s | 50 行 |
| `pytest-dev__pytest-7432` | Pytest | ✅ | 🎯 **100% 吻合** | 100.0% | 22 轮 | 134.6s | 14 行 |
| `pytest-dev__pytest-7490` | Pytest | ✅ | ✅ 逻辑吻合 | 89.1% | 21 轮 | 140.6s | 38 行 |
| `pytest-dev__pytest-8365` | Pytest | ✅ | ✅ 逻辑吻合 | 97.1% | 9 轮 | 48.6s | 18 行 |
| `pytest-dev__pytest-8906` | Pytest | ✅ | ✅ 逻辑吻合 | 97.1% | 10 轮 | 48.9s | 19 行 |
| `pytest-dev__pytest-9359` | Pytest | ✅ | ✅ 逻辑吻合 | 91.1% | 22 轮 | 277.9s | 15 行 |
