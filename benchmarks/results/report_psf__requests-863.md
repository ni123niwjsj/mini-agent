# 🏆 Mini-Agent SWE-bench 基准评测报告

- **评测时间**: 2026-10-13 16:58:12
- **评估模型**: `deepseek/deepseek-v4.1-flash`
- **总测试题目**: 1
- **成功解决 (Resolved)**: 0 / 1 (0.0%)
- **平均轮数**: 13.0 轮
- **平均耗时**: 61.37s

## 📊 评测明细总表

| 题目编号 (Instance ID) | 修复状态 | 评测结论 | 轮数 | 耗时 | 工具调用 | 补丁大小 |
| :--- | :---: | :---: | :---: | :---: | :--- | :---: |
| `psf__requests-863` | ✅ | 🔴 **FAIL** | 13 | 61.4s | `grep, edit_file, read_file, bash` | 16 行 |

## 🔍 用例测试细节

### `psf__requests-863`
- **解决状态**: 未解决
- **FAIL_TO_PASS 校验**:
  - ❌ `tests/test_requests.py::RequestsTestSuite::test_POSTBIN_GET_POST_FILES_WITH_HEADERS`: FAILED
  - ❌ `tests/test_requests.py::RequestsTestSuite::test_nonurlencoded_postdata`: FAILED
  - ❌ `tests/test_requests.py::RequestsTestSuite::test_prefetch_redirect_bug`: FAILED
  - ❌ `tests/test_requests.py::RequestsTestSuite::test_urlencoded_post_data`: FAILED
- **PASS_TO_PASS 校验**:
  - ❌ `tests/test_requests.py::RequestsTestSuite::test_BASICAUTH_HTTP_200_OK_GET`: FAILED
  - ❌ `tests/test_requests.py::RequestsTestSuite::test_BASICAUTH_TUPLE_HTTP_200_OK_GET`: FAILED
  - ❌ `tests/test_requests.py::RequestsTestSuite::test_GET_no_redirect`: FAILED
  - ❌ `tests/test_requests.py::RequestsTestSuite::test_HEAD_no_redirect`: FAILED
  - ❌ `tests/test_requests.py::RequestsTestSuite::test_HTTP_200_OK_GET`: FAILED
  - ❌ `tests/test_requests.py::RequestsTestSuite::test_HTTP_200_OK_GET_WITH_MIXED_PARAMS`: FAILED
  - ❌ `tests/test_requests.py::RequestsTestSuite::test_HTTP_200_OK_GET_WITH_PARAMS`: FAILED
  - ❌ `tests/test_requests.py::RequestsTestSuite::test_HTTP_200_OK_HEAD`: FAILED
  - ❌ `tests/test_requests.py::RequestsTestSuite::test_HTTP_200_OK_PUT`: FAILED
  - ❌ `tests/test_requests.py::RequestsTestSuite::test_HTTP_302_ALLOW_REDIRECT_GET`: FAILED
  - ❌ `tests/test_requests.py::RequestsTestSuite::test_HTTP_302_GET`: FAILED
  - ❌ `tests/test_requests.py::RequestsTestSuite::test_POSTBIN_GET_POST_FILES`: FAILED
  - ❌ `tests/test_requests.py::RequestsTestSuite::test_POSTBIN_GET_POST_FILES_WITH_PARAMS`: FAILED
  - ❌ `tests/test_requests.py::RequestsTestSuite::test_accept_objects_with_string_representations_as_urls`: FAILED
  - ❌ `tests/test_requests.py::RequestsTestSuite::test_bytes_files`: FAILED
  - ❌ `tests/test_requests.py::RequestsTestSuite::test_cached_response`: FAILED
  - ❌ `tests/test_requests.py::RequestsTestSuite::test_can_have_none_in_header_values`: FAILED
  - ❌ `tests/test_requests.py::RequestsTestSuite::test_connection_error`: FAILED
  - ❌ `tests/test_requests.py::RequestsTestSuite::test_connection_error_with_safe_mode`: FAILED
  - ❌ `tests/test_requests.py::RequestsTestSuite::test_connection_keepalive_and_close`: FAILED
  - ❌ `tests/test_requests.py::RequestsTestSuite::test_danger_mode_redirects`: FAILED
  - ❌ `tests/test_requests.py::RequestsTestSuite::test_decompress_gzip`: FAILED
  - ❌ `tests/test_requests.py::RequestsTestSuite::test_default_status_raising`: FAILED
  - ❌ `tests/test_requests.py::RequestsTestSuite::test_empty_response`: FAILED
  - ❌ `tests/test_requests.py::RequestsTestSuite::test_entry_points`: FAILED
  - ❌ `tests/test_requests.py::RequestsTestSuite::test_file_post_data`: FAILED
  - ❌ `tests/test_requests.py::RequestsTestSuite::test_head_content`: FAILED
  - ❌ `tests/test_requests.py::RequestsTestSuite::test_httpauth_recursion`: FAILED
  - ❌ `tests/test_requests.py::RequestsTestSuite::test_invalid_url`: FAILED
  - ❌ `tests/test_requests.py::RequestsTestSuite::test_invalid_urls_throw_requests_exception`: FAILED
  - ❌ `tests/test_requests.py::RequestsTestSuite::test_iter_lines`: FAILED
  - ❌ `tests/test_requests.py::RequestsTestSuite::test_max_redirects`: FAILED
  - ❌ `tests/test_requests.py::RequestsTestSuite::test_multiple_hooks`: FAILED
  - ❌ `tests/test_requests.py::RequestsTestSuite::test_nonurlencoded_post_data`: FAILED
  - ❌ `tests/test_requests.py::RequestsTestSuite::test_nonzero_evaluation`: FAILED
  - ❌ `tests/test_requests.py::RequestsTestSuite::test_params_accepts_kv_list`: FAILED
  - ❌ `tests/test_requests.py::RequestsTestSuite::test_params_are_added_before_fragment`: FAILED
  - ❌ `tests/test_requests.py::RequestsTestSuite::test_path_is_not_double_encoded`: FAILED
  - ❌ `tests/test_requests.py::RequestsTestSuite::test_post_fields_with_multiple_values_and_files`: FAILED
  - ❌ `tests/test_requests.py::RequestsTestSuite::test_post_fields_with_multiple_values_and_files_as_tuples`: FAILED
  - ❌ `tests/test_requests.py::RequestsTestSuite::test_prefetch_return_response_interaction`: FAILED
  - ❌ `tests/test_requests.py::RequestsTestSuite::test_redirect_history`: FAILED
  - ❌ `tests/test_requests.py::RequestsTestSuite::test_relative_redirect_history`: FAILED
  - ❌ `tests/test_requests.py::RequestsTestSuite::test_request_ok_set`: FAILED
  - ❌ `tests/test_requests.py::RequestsTestSuite::test_response_has_unicode_url`: FAILED
  - ❌ `tests/test_requests.py::RequestsTestSuite::test_response_sent`: FAILED
  - ❌ `tests/test_requests.py::RequestsTestSuite::test_session_HTTP_200_OK_GET`: FAILED
  - ❌ `tests/test_requests.py::RequestsTestSuite::test_session_persistent_headers`: FAILED
  - ❌ `tests/test_requests.py::RequestsTestSuite::test_session_pickling`: FAILED
  - ❌ `tests/test_requests.py::RequestsTestSuite::test_status_raising`: FAILED
  - ❌ `tests/test_requests.py::RequestsTestSuite::test_unicode_get`: FAILED
  - ❌ `tests/test_requests.py::RequestsTestSuite::test_upload_binary_data`: FAILED
  - ❌ `tests/test_requests.py::RequestsTestSuite::test_urlencoded_get_query_multivalued_param`: FAILED
  - ❌ `tests/test_requests.py::RequestsTestSuite::test_urlencoded_post_query_and_data`: FAILED
  - ❌ `tests/test_requests.py::RequestsTestSuite::test_urlencoded_post_query_multivalued_and_data`: FAILED
  - ❌ `tests/test_requests.py::RequestsTestSuite::test_urlencoded_post_querystring`: FAILED
  - ❌ `tests/test_requests.py::RequestsTestSuite::test_urlencoded_post_querystring_multivalued`: FAILED
  - ❌ `tests/test_requests.py::RequestsTestSuite::test_useful_exception_for_invalid_port`: FAILED
  - ❌ `tests/test_requests.py::RequestsTestSuite::test_useful_exception_for_invalid_scheme`: FAILED
  - ❌ `tests/test_requests.py::RequestsTestSuite::test_user_agent_transfers`: FAILED
