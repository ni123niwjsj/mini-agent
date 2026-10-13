# 🏆 Mini-Agent SWE-bench 基准评测报告

- **评测时间**: 2026-10-13 16:36:01
- **评估模型**: `deepseek/deepseek-v4.1-flash`
- **总测试题目**: 1
- **成功解决 (Resolved)**: 0 / 1 (0.0%)
- **平均轮数**: 25.0 轮
- **平均耗时**: 398.06s

## 📊 评测明细总表

| 题目编号 (Instance ID) | 修复状态 | 评测结论 | 轮数 | 耗时 | 工具调用 | 补丁大小 |
| :--- | :---: | :---: | :---: | :---: | :--- | :---: |
| `mwaskom__seaborn-2848` | ❌ | 🔴 **FAIL** | 25 | 398.1s | `grep, edit_file, web_search, read_file, web_fetch, bash` | 18 行 |

## 🔍 用例测试细节

### `mwaskom__seaborn-2848`
- **解决状态**: 未解决
- **FAIL_TO_PASS 校验**:
  - ❌ `tests/test_relational.py::TestScatterPlotter::test_hue_order`: FAILED
- **PASS_TO_PASS 校验**:
  - ❌ `tests/test_relational.py::TestRelationalPlotter::test_wide_df_variables`: FAILED
  - ❌ `tests/test_relational.py::TestRelationalPlotter::test_wide_df_with_nonnumeric_variables`: FAILED
  - ❌ `tests/test_relational.py::TestRelationalPlotter::test_wide_array_variables`: FAILED
  - ❌ `tests/test_relational.py::TestRelationalPlotter::test_flat_array_variables`: FAILED
  - ❌ `tests/test_relational.py::TestRelationalPlotter::test_flat_list_variables`: FAILED
  - ❌ `tests/test_relational.py::TestRelationalPlotter::test_flat_series_variables`: FAILED
  - ❌ `tests/test_relational.py::TestRelationalPlotter::test_wide_list_of_series_variables`: FAILED
  - ❌ `tests/test_relational.py::TestRelationalPlotter::test_wide_list_of_arrays_variables`: FAILED
  - ❌ `tests/test_relational.py::TestRelationalPlotter::test_wide_list_of_list_variables`: FAILED
  - ❌ `tests/test_relational.py::TestRelationalPlotter::test_wide_dict_of_series_variables`: FAILED
  - ❌ `tests/test_relational.py::TestRelationalPlotter::test_wide_dict_of_arrays_variables`: FAILED
  - ❌ `tests/test_relational.py::TestRelationalPlotter::test_wide_dict_of_lists_variables`: FAILED
  - ❌ `tests/test_relational.py::TestRelationalPlotter::test_relplot_complex`: FAILED
  - ❌ `tests/test_relational.py::TestRelationalPlotter::test_relplot_vectors[series]`: FAILED
  - ❌ `tests/test_relational.py::TestRelationalPlotter::test_relplot_vectors[numpy]`: FAILED
  - ❌ `tests/test_relational.py::TestRelationalPlotter::test_relplot_vectors[list]`: FAILED
  - ❌ `tests/test_relational.py::TestRelationalPlotter::test_relplot_wide`: FAILED
  - ❌ `tests/test_relational.py::TestRelationalPlotter::test_relplot_hues`: FAILED
  - ❌ `tests/test_relational.py::TestRelationalPlotter::test_relplot_sizes`: FAILED
  - ❌ `tests/test_relational.py::TestRelationalPlotter::test_relplot_styles`: FAILED
  - ❌ `tests/test_relational.py::TestRelationalPlotter::test_relplot_stringy_numerics`: FAILED
  - ❌ `tests/test_relational.py::TestRelationalPlotter::test_relplot_data`: FAILED
  - ❌ `tests/test_relational.py::TestRelationalPlotter::test_facet_variable_collision`: FAILED
  - ❌ `tests/test_relational.py::TestRelationalPlotter::test_ax_kwarg_removal`: FAILED
  - ❌ `tests/test_relational.py::TestLinePlotter::test_legend_data`: FAILED
  - ❌ `tests/test_relational.py::TestLinePlotter::test_plot`: FAILED
  - ❌ `tests/test_relational.py::TestLinePlotter::test_axis_labels`: FAILED
  - ❌ `tests/test_relational.py::TestScatterPlotter::test_color`: FAILED
  - ❌ `tests/test_relational.py::TestScatterPlotter::test_legend_data`: FAILED
  - ❌ `tests/test_relational.py::TestScatterPlotter::test_plot`: FAILED
  - ❌ `tests/test_relational.py::TestScatterPlotter::test_axis_labels`: FAILED
  - ❌ `tests/test_relational.py::TestScatterPlotter::test_scatterplot_axes`: FAILED
  - ❌ `tests/test_relational.py::TestScatterPlotter::test_literal_attribute_vectors`: FAILED
  - ❌ `tests/test_relational.py::TestScatterPlotter::test_supplied_color_array`: FAILED
  - ❌ `tests/test_relational.py::TestScatterPlotter::test_linewidths`: FAILED
  - ❌ `tests/test_relational.py::TestScatterPlotter::test_size_norm_extrapolation`: FAILED
  - ❌ `tests/test_relational.py::TestScatterPlotter::test_datetime_scale`: FAILED
  - ❌ `tests/test_relational.py::TestScatterPlotter::test_scatterplot_vs_relplot[long_semantics0]`: FAILED
  - ❌ `tests/test_relational.py::TestScatterPlotter::test_scatterplot_vs_relplot[long_semantics1]`: FAILED
  - ❌ `tests/test_relational.py::TestScatterPlotter::test_scatterplot_vs_relplot[long_semantics2]`: FAILED
  - ❌ `tests/test_relational.py::TestScatterPlotter::test_scatterplot_vs_relplot[long_semantics3]`: FAILED
  - ❌ `tests/test_relational.py::TestScatterPlotter::test_scatterplot_vs_relplot[long_semantics4]`: FAILED
  - ❌ `tests/test_relational.py::TestScatterPlotter::test_scatterplot_vs_relplot[long_semantics5]`: FAILED
  - ❌ `tests/test_relational.py::TestScatterPlotter::test_scatterplot_vs_relplot[long_semantics6]`: FAILED
  - ❌ `tests/test_relational.py::TestScatterPlotter::test_scatterplot_vs_relplot[long_semantics7]`: FAILED
  - ❌ `tests/test_relational.py::TestScatterPlotter::test_scatterplot_vs_relplot[long_semantics8]`: FAILED
  - ❌ `tests/test_relational.py::TestScatterPlotter::test_scatterplot_vs_relplot[long_semantics9]`: FAILED
  - ❌ `tests/test_relational.py::TestScatterPlotter::test_scatterplot_vs_relplot[long_semantics10]`: FAILED
  - ❌ `tests/test_relational.py::TestScatterPlotter::test_scatterplot_vs_relplot[long_semantics11]`: FAILED
  - ❌ `tests/test_relational.py::TestScatterPlotter::test_scatterplot_smoke`: FAILED
