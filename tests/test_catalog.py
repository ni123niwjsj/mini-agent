"""测试 ai/catalog.py 模型规格库与上下文窗口自适应推断"""

import os
import unittest
from mini_agent.ai.catalog import (
    DEFAULT_MODEL_SPECS,
    ModelSpec,
    infer_context_window,
    resolve_context_window,
)
from mini_agent.ai.client import LLMClient


class TestModelCatalog(unittest.TestCase):
    """测试模型规格与上下文窗口解析逻辑"""

    def setUp(self):
        self.old_env = os.environ.get("CONTEXT_WINDOW")
        if "CONTEXT_WINDOW" in os.environ:
            del os.environ["CONTEXT_WINDOW"]

    def tearDown(self):
        if self.old_env is not None:
            os.environ["CONTEXT_WINDOW"] = self.old_env
        elif "CONTEXT_WINDOW" in os.environ:
            del os.environ["CONTEXT_WINDOW"]

    def test_known_models_resolution(self):
        """测试知名主流模型的标准窗口映射"""
        # DeepSeek V4 系列 (1M)
        self.assertEqual(resolve_context_window("deepseek/deepseek-v4.1-flash"), 1000000)
        self.assertEqual(resolve_context_window("deepseek-v4-flash"), 1000000)

        # Gemini 系列 (1M ~ 2M)
        self.assertEqual(resolve_context_window("google/gemini-2.0-flash"), 1048576)

        # Claude 系列 (200k)
        self.assertEqual(resolve_context_window("anthropic/claude-3-5-sonnet"), 200000)

        # GPT-4o / DeepSeek-Chat (128k)
        self.assertEqual(resolve_context_window("gpt-4o"), 128000)
        self.assertEqual(resolve_context_window("deepseek-chat"), 128000)

    def test_heuristic_pattern_inference(self):
        """测试模型命名后缀的智能启发式推断"""
        self.assertEqual(infer_context_window("custom-model-1m"), 1000000)
        self.assertEqual(infer_context_window("my-org/model-500k-instruct"), 500000)
        self.assertEqual(infer_context_window("qwen-262k"), 262144)
        self.assertEqual(infer_context_window("llama-3-32k"), 32768)
        self.assertEqual(infer_context_window("mistral-8k"), 8192)
        # 未知且无后缀默认兜底 128k
        self.assertEqual(infer_context_window("unknown-arbitrary-model"), 128000)

    def test_env_override_priority(self):
        """测试用户环境变量优先覆盖"""
        os.environ["CONTEXT_WINDOW"] = "2048000"
        self.assertEqual(resolve_context_window("deepseek/deepseek-v4.1-flash"), 2048000)
        self.assertEqual(resolve_context_window("gpt-4o"), 2048000)

    def test_dynamic_specs_cache(self):
        """测试动态服务端规格缓存优先级高于静态推断"""
        cache = {
            "my-special-model": 888888,
        }
        self.assertEqual(resolve_context_window("my-special-model", cache), 888888)


class TestAsyncCatalog(unittest.IsolatedAsyncioTestCase):
    async def test_llm_client_mock_catalog(self):
        client = LLMClient(model="mock")
        catalog = await client.get_model_catalog()
        self.assertGreater(len(catalog), 0)
        flash_spec = next((s for s in catalog if "deepseek" in s.id), None)
        self.assertIsNotNone(flash_spec)
        self.assertEqual(flash_spec.context_length, 1000000)
