# 🏆 Mini-Agent SWE-bench 基准评测报告

- **评测时间**: 2026-10-13 16:29:00
- **评估模型**: `deepseek/deepseek-v4.1-flash`
- **总测试题目**: 1
- **成功解决 (Resolved)**: 0 / 1 (0.0%)
- **平均轮数**: 11.0 轮
- **平均耗时**: 62.84s

## 📊 评测明细总表

| 题目编号 (Instance ID) | 修复状态 | 评测结论 | 轮数 | 耗时 | 工具调用 | 补丁大小 |
| :--- | :---: | :---: | :---: | :---: | :--- | :---: |
| `mwaskom__seaborn-3190` | ✅ | 🔴 **FAIL** | 11 | 62.8s | `bash, web_search, grep, read_file, edit_file, web_fetch` | 12 行 |

## 🔍 用例测试细节

### `mwaskom__seaborn-3190`
- **解决状态**: 未解决
- **FAIL_TO_PASS 校验**:
  - ❌ `tests/_core/test_scales.py::TestContinuous::test_interval_with_bools`: FAILED
- **PASS_TO_PASS 校验**:
  - ❌ `tests/_core/test_scales.py::TestContinuous::test_coordinate_defaults`: FAILED
  - ❌ `tests/_core/test_scales.py::TestContinuous::test_coordinate_transform`: FAILED
  - ❌ `tests/_core/test_scales.py::TestContinuous::test_coordinate_transform_with_parameter`: FAILED
  - ❌ `tests/_core/test_scales.py::TestContinuous::test_coordinate_transform_error`: FAILED
  - ❌ `tests/_core/test_scales.py::TestContinuous::test_interval_defaults`: FAILED
  - ❌ `tests/_core/test_scales.py::TestContinuous::test_interval_with_range`: FAILED
  - ❌ `tests/_core/test_scales.py::TestContinuous::test_interval_with_norm`: FAILED
  - ❌ `tests/_core/test_scales.py::TestContinuous::test_interval_with_range_norm_and_transform`: FAILED
  - ❌ `tests/_core/test_scales.py::TestContinuous::test_color_defaults`: FAILED
  - ❌ `tests/_core/test_scales.py::TestContinuous::test_color_named_values`: FAILED
  - ❌ `tests/_core/test_scales.py::TestContinuous::test_color_tuple_values`: FAILED
  - ❌ `tests/_core/test_scales.py::TestContinuous::test_color_callable_values`: FAILED
  - ❌ `tests/_core/test_scales.py::TestContinuous::test_color_with_norm`: FAILED
  - ❌ `tests/_core/test_scales.py::TestContinuous::test_color_with_transform`: FAILED
  - ❌ `tests/_core/test_scales.py::TestContinuous::test_tick_locator`: FAILED
  - ❌ `tests/_core/test_scales.py::TestContinuous::test_tick_locator_input_check`: FAILED
  - ❌ `tests/_core/test_scales.py::TestContinuous::test_tick_upto`: FAILED
  - ❌ `tests/_core/test_scales.py::TestContinuous::test_tick_every`: FAILED
  - ❌ `tests/_core/test_scales.py::TestContinuous::test_tick_every_between`: FAILED
  - ❌ `tests/_core/test_scales.py::TestContinuous::test_tick_at`: FAILED
  - ❌ `tests/_core/test_scales.py::TestContinuous::test_tick_count`: FAILED
  - ❌ `tests/_core/test_scales.py::TestContinuous::test_tick_count_between`: FAILED
  - ❌ `tests/_core/test_scales.py::TestContinuous::test_tick_minor`: FAILED
  - ❌ `tests/_core/test_scales.py::TestContinuous::test_log_tick_default`: FAILED
  - ❌ `tests/_core/test_scales.py::TestContinuous::test_log_tick_upto`: FAILED
  - ❌ `tests/_core/test_scales.py::TestContinuous::test_log_tick_count`: FAILED
  - ❌ `tests/_core/test_scales.py::TestContinuous::test_log_tick_format_disabled`: FAILED
  - ❌ `tests/_core/test_scales.py::TestContinuous::test_log_tick_every`: FAILED
  - ❌ `tests/_core/test_scales.py::TestContinuous::test_symlog_tick_default`: FAILED
  - ❌ `tests/_core/test_scales.py::TestContinuous::test_label_formatter`: FAILED
  - ❌ `tests/_core/test_scales.py::TestContinuous::test_label_like_pattern`: FAILED
  - ❌ `tests/_core/test_scales.py::TestContinuous::test_label_like_string`: FAILED
  - ❌ `tests/_core/test_scales.py::TestContinuous::test_label_like_function`: FAILED
  - ❌ `tests/_core/test_scales.py::TestContinuous::test_label_base`: FAILED
  - ❌ `tests/_core/test_scales.py::TestContinuous::test_label_unit`: FAILED
  - ❌ `tests/_core/test_scales.py::TestContinuous::test_label_unit_with_sep`: FAILED
  - ❌ `tests/_core/test_scales.py::TestContinuous::test_label_empty_unit`: FAILED
  - ❌ `tests/_core/test_scales.py::TestContinuous::test_label_base_from_transform`: FAILED
  - ❌ `tests/_core/test_scales.py::TestContinuous::test_label_type_checks`: FAILED
  - ❌ `tests/_core/test_scales.py::TestNominal::test_coordinate_defaults`: FAILED
  - ❌ `tests/_core/test_scales.py::TestNominal::test_coordinate_with_order`: FAILED
  - ❌ `tests/_core/test_scales.py::TestNominal::test_coordinate_with_subset_order`: FAILED
  - ❌ `tests/_core/test_scales.py::TestNominal::test_coordinate_axis`: FAILED
  - ❌ `tests/_core/test_scales.py::TestNominal::test_coordinate_axis_with_order`: FAILED
  - ❌ `tests/_core/test_scales.py::TestNominal::test_coordinate_axis_with_subset_order`: FAILED
  - ❌ `tests/_core/test_scales.py::TestNominal::test_coordinate_axis_with_category_dtype`: FAILED
  - ❌ `tests/_core/test_scales.py::TestNominal::test_coordinate_numeric_data`: FAILED
  - ❌ `tests/_core/test_scales.py::TestNominal::test_coordinate_numeric_data_with_order`: FAILED
  - ❌ `tests/_core/test_scales.py::TestNominal::test_color_defaults`: FAILED
  - ❌ `tests/_core/test_scales.py::TestNominal::test_color_named_palette`: FAILED
  - ❌ `tests/_core/test_scales.py::TestNominal::test_color_list_palette`: FAILED
  - ❌ `tests/_core/test_scales.py::TestNominal::test_color_dict_palette`: FAILED
  - ❌ `tests/_core/test_scales.py::TestNominal::test_color_numeric_data`: FAILED
  - ❌ `tests/_core/test_scales.py::TestNominal::test_color_numeric_with_order_subset`: FAILED
  - ❌ `tests/_core/test_scales.py::TestNominal::test_color_alpha_in_palette`: FAILED
  - ❌ `tests/_core/test_scales.py::TestNominal::test_color_unknown_palette`: FAILED
  - ❌ `tests/_core/test_scales.py::TestNominal::test_object_defaults`: FAILED
  - ❌ `tests/_core/test_scales.py::TestNominal::test_object_list`: FAILED
  - ❌ `tests/_core/test_scales.py::TestNominal::test_object_dict`: FAILED
  - ❌ `tests/_core/test_scales.py::TestNominal::test_object_order`: FAILED
  - ❌ `tests/_core/test_scales.py::TestNominal::test_object_order_subset`: FAILED
  - ❌ `tests/_core/test_scales.py::TestNominal::test_objects_that_are_weird`: FAILED
  - ❌ `tests/_core/test_scales.py::TestNominal::test_alpha_default`: FAILED
  - ❌ `tests/_core/test_scales.py::TestNominal::test_fill`: FAILED
  - ❌ `tests/_core/test_scales.py::TestNominal::test_fill_dict`: FAILED
  - ❌ `tests/_core/test_scales.py::TestNominal::test_fill_nunique_warning`: FAILED
  - ❌ `tests/_core/test_scales.py::TestNominal::test_interval_defaults`: FAILED
  - ❌ `tests/_core/test_scales.py::TestNominal::test_interval_tuple`: FAILED
  - ❌ `tests/_core/test_scales.py::TestNominal::test_interval_tuple_numeric`: FAILED
  - ❌ `tests/_core/test_scales.py::TestNominal::test_interval_list`: FAILED
  - ❌ `tests/_core/test_scales.py::TestNominal::test_interval_dict`: FAILED
  - ❌ `tests/_core/test_scales.py::TestNominal::test_interval_with_transform`: FAILED
  - ❌ `tests/_core/test_scales.py::TestNominal::test_empty_data`: FAILED
  - ❌ `tests/_core/test_scales.py::TestTemporal::test_coordinate_defaults`: FAILED
  - ❌ `tests/_core/test_scales.py::TestTemporal::test_interval_defaults`: FAILED
  - ❌ `tests/_core/test_scales.py::TestTemporal::test_interval_with_range`: FAILED
  - ❌ `tests/_core/test_scales.py::TestTemporal::test_interval_with_norm`: FAILED
  - ❌ `tests/_core/test_scales.py::TestTemporal::test_color_defaults`: FAILED
  - ❌ `tests/_core/test_scales.py::TestTemporal::test_color_named_values`: FAILED
  - ❌ `tests/_core/test_scales.py::TestTemporal::test_coordinate_axis`: FAILED
  - ❌ `tests/_core/test_scales.py::TestTemporal::test_tick_locator`: FAILED
  - ❌ `tests/_core/test_scales.py::TestTemporal::test_tick_upto`: FAILED
  - ❌ `tests/_core/test_scales.py::TestTemporal::test_label_formatter`: FAILED
  - ❌ `tests/_core/test_scales.py::TestTemporal::test_label_concise`: FAILED
