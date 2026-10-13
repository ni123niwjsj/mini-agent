# 🏆 Mini-Agent SWE-bench 基准评测报告

- **评测时间**: 2026-10-13 16:56:25
- **评估模型**: `deepseek/deepseek-v4.1-flash`
- **总测试题目**: 1
- **成功解决 (Resolved)**: 0 / 1 (0.0%)
- **平均轮数**: 14.0 轮
- **平均耗时**: 75.42s

## 📊 评测明细总表

| 题目编号 (Instance ID) | 修复状态 | 评测结论 | 轮数 | 耗时 | 工具调用 | 补丁大小 |
| :--- | :---: | :---: | :---: | :---: | :--- | :---: |
| `psf__requests-3362` | ✅ | 🔴 **FAIL** | 14 | 75.4s | `web_search, bash, edit_file, web_fetch, grep, read_file` | 30 行 |

## 🔍 用例测试细节

### `psf__requests-3362`
- **解决状态**: 未解决
- **FAIL_TO_PASS 校验**:
  - ❌ `tests/test_requests.py::TestRequests::test_response_decode_unicode`: FAILED
- **PASS_TO_PASS 校验**:
  - ❌ `tests/test_requests.py::TestRequests::test_entry_points`: FAILED
  - ❌ `tests/test_requests.py::TestRequests::test_invalid_url[MissingSchema-hiwpefhipowhefopw]`: FAILED
  - ❌ `tests/test_requests.py::TestRequests::test_invalid_url[InvalidSchema-localhost:3128]`: FAILED
  - ❌ `tests/test_requests.py::TestRequests::test_invalid_url[InvalidSchema-localhost.localdomain:3128/]`: FAILED
  - ❌ `tests/test_requests.py::TestRequests::test_invalid_url[InvalidSchema-10.122.1.1:3128/]`: FAILED
  - ❌ `tests/test_requests.py::TestRequests::test_invalid_url[InvalidURL-http://]`: FAILED
  - ❌ `tests/test_requests.py::TestRequests::test_basic_building`: FAILED
  - ❌ `tests/test_requests.py::TestRequests::test_path_is_not_double_encoded`: FAILED
  - ❌ `tests/test_requests.py::TestRequests::test_params_are_added_before_fragment[http://example.com/path#fragment-http://example.com/path?a=b#fragment]`: FAILED
  - ❌ `tests/test_requests.py::TestRequests::test_params_are_added_before_fragment[http://example.com/path?key=value#fragment-http://example.com/path?key=value&a=b#fragment]`: FAILED
  - ❌ `tests/test_requests.py::TestRequests::test_params_original_order_is_preserved_by_default`: FAILED
  - ❌ `tests/test_requests.py::TestRequests::test_params_bytes_are_encoded`: FAILED
  - ❌ `tests/test_requests.py::TestRequests::test_binary_put`: FAILED
  - ❌ `tests/test_requests.py::TestRequests::test_errors[http://doesnotexist.google.com-ConnectionError]`: FAILED
  - ❌ `tests/test_requests.py::TestRequests::test_errors[http://localhost:1-ConnectionError]`: FAILED
  - ❌ `tests/test_requests.py::TestRequests::test_errors[http://fe80::5054:ff:fe5a:fc0-InvalidURL]`: FAILED
  - ❌ `tests/test_requests.py::TestRequests::test_proxy_error`: FAILED
  - ❌ `tests/test_requests.py::TestRequests::test_non_prepared_request_error`: FAILED
  - ❌ `tests/test_requests.py::TestRequests::test_prepare_request_with_bytestring_url`: FAILED
  - ❌ `tests/test_requests.py::TestRequests::test_links`: FAILED
  - ❌ `tests/test_requests.py::TestRequests::test_cookie_parameters`: FAILED
  - ❌ `tests/test_requests.py::TestRequests::test_cookie_as_dict_keeps_len`: FAILED
  - ❌ `tests/test_requests.py::TestRequests::test_cookie_as_dict_keeps_items`: FAILED
  - ❌ `tests/test_requests.py::TestRequests::test_cookie_as_dict_keys`: FAILED
  - ❌ `tests/test_requests.py::TestRequests::test_cookie_as_dict_values`: FAILED
  - ❌ `tests/test_requests.py::TestRequests::test_cookie_as_dict_items`: FAILED
  - ❌ `tests/test_requests.py::TestRequests::test_cookie_duplicate_names_different_domains`: FAILED
  - ❌ `tests/test_requests.py::TestRequests::test_cookie_duplicate_names_raises_cookie_conflict_error`: FAILED
  - ❌ `tests/test_requests.py::TestRequests::test_response_is_iterable`: FAILED
  - ❌ `tests/test_requests.py::TestRequests::test_response_chunk_size_int`: FAILED
  - ❌ `tests/test_requests.py::TestRequests::test_http_error`: FAILED
  - ❌ `tests/test_requests.py::TestRequests::test_transport_adapter_ordering`: FAILED
  - ❌ `tests/test_requests.py::TestRequests::test_long_authinfo_in_url`: FAILED
  - ❌ `tests/test_requests.py::TestRequests::test_nonhttp_schemes_dont_check_URLs`: FAILED
  - ❌ `tests/test_requests.py::TestRequests::test_basic_auth_str_is_always_native`: FAILED
  - ❌ `tests/test_requests.py::TestCaseInsensitiveDict::test_init[cid0]`: FAILED
  - ❌ `tests/test_requests.py::TestCaseInsensitiveDict::test_init[cid1]`: FAILED
  - ❌ `tests/test_requests.py::TestCaseInsensitiveDict::test_init[cid2]`: FAILED
  - ❌ `tests/test_requests.py::TestCaseInsensitiveDict::test_docstring_example`: FAILED
  - ❌ `tests/test_requests.py::TestCaseInsensitiveDict::test_len`: FAILED
  - ❌ `tests/test_requests.py::TestCaseInsensitiveDict::test_getitem`: FAILED
  - ❌ `tests/test_requests.py::TestCaseInsensitiveDict::test_fixes_649`: FAILED
  - ❌ `tests/test_requests.py::TestCaseInsensitiveDict::test_delitem`: FAILED
  - ❌ `tests/test_requests.py::TestCaseInsensitiveDict::test_contains`: FAILED
  - ❌ `tests/test_requests.py::TestCaseInsensitiveDict::test_get`: FAILED
  - ❌ `tests/test_requests.py::TestCaseInsensitiveDict::test_update`: FAILED
  - ❌ `tests/test_requests.py::TestCaseInsensitiveDict::test_update_retains_unchanged`: FAILED
  - ❌ `tests/test_requests.py::TestCaseInsensitiveDict::test_iter`: FAILED
  - ❌ `tests/test_requests.py::TestCaseInsensitiveDict::test_equality`: FAILED
  - ❌ `tests/test_requests.py::TestCaseInsensitiveDict::test_setdefault`: FAILED
  - ❌ `tests/test_requests.py::TestCaseInsensitiveDict::test_lower_items`: FAILED
  - ❌ `tests/test_requests.py::TestCaseInsensitiveDict::test_preserve_key_case`: FAILED
  - ❌ `tests/test_requests.py::TestCaseInsensitiveDict::test_preserve_last_key_case`: FAILED
  - ❌ `tests/test_requests.py::TestCaseInsensitiveDict::test_copy`: FAILED
  - ❌ `tests/test_requests.py::TestMorselToCookieExpires::test_expires_valid_str`: FAILED
  - ❌ `tests/test_requests.py::TestMorselToCookieExpires::test_expires_invalid_int[100-TypeError]`: FAILED
  - ❌ `tests/test_requests.py::TestMorselToCookieExpires::test_expires_invalid_int[woops-ValueError]`: FAILED
  - ❌ `tests/test_requests.py::TestMorselToCookieExpires::test_expires_none`: FAILED
  - ❌ `tests/test_requests.py::TestMorselToCookieMaxAge::test_max_age_valid_int`: FAILED
  - ❌ `tests/test_requests.py::TestMorselToCookieMaxAge::test_max_age_invalid_str`: FAILED
  - ❌ `tests/test_requests.py::TestTimeout::test_connect_timeout`: FAILED
  - ❌ `tests/test_requests.py::TestTimeout::test_total_timeout_connect`: FAILED
  - ❌ `tests/test_requests.py::test_json_encodes_as_bytes`: FAILED
  - ❌ `tests/test_requests.py::test_proxy_env_vars_override_default[http_proxy-http://example.com-socks5://proxy.com:9876]`: FAILED
  - ❌ `tests/test_requests.py::test_proxy_env_vars_override_default[https_proxy-https://example.com-socks5://proxy.com:9876]`: FAILED
  - ❌ `tests/test_requests.py::test_proxy_env_vars_override_default[all_proxy-http://example.com-socks5://proxy.com:9876]`: FAILED
  - ❌ `tests/test_requests.py::test_proxy_env_vars_override_default[all_proxy-https://example.com-socks5://proxy.com:9876]`: FAILED
  - ❌ `tests/test_requests.py::test_data_argument_accepts_tuples[data0]`: FAILED
  - ❌ `tests/test_requests.py::test_data_argument_accepts_tuples[data1]`: FAILED
  - ❌ `tests/test_requests.py::test_data_argument_accepts_tuples[data2]`: FAILED
  - ❌ `tests/test_requests.py::test_prepared_copy[None]`: FAILED
  - ❌ `tests/test_requests.py::test_prepared_copy[kwargs1]`: FAILED
  - ❌ `tests/test_requests.py::test_prepared_copy[kwargs2]`: FAILED
  - ❌ `tests/test_requests.py::test_prepared_copy[kwargs3]`: FAILED
  - ❌ `tests/test_requests.py::test_vendor_aliases`: FAILED
