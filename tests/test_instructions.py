"""测试项目级规范文件 (AGENTS.md / CLAUDE.md) 的探测与 System Prompt 注入。"""

import os
import shutil
import tempfile
import unittest

from mini_agent.core.instructions import (
    find_project_instructions,
    build_system_prompt,
    find_git_root,
)


class TestProjectInstructions(unittest.TestCase):
    """测试 AGENTS.md 自动发现与注入机制"""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="test_mini_agent_instructions_")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_find_instructions_in_workspace(self):
        """测试在工作区根目录直接命中 AGENTS.md"""
        agents_file = os.path.join(self.test_dir, "AGENTS.md")
        with open(agents_file, "w", encoding="utf-8") as f:
            f.write("# Project Test Rules\n- Rule 1: Always test\n")

        res = find_project_instructions(self.test_dir)
        self.assertIsNotNone(res)
        path, content = res
        self.assertEqual(path, agents_file)
        self.assertIn("Rule 1: Always test", content)

    def test_find_instructions_in_parent_git_root(self):
        """测试在子工作区中向上回溯至 Git 根目录发现 AGENTS.md"""
        # 模拟 git 仓库
        git_dir = os.path.join(self.test_dir, ".git")
        os.makedirs(git_dir, exist_ok=True)
        root_agents = os.path.join(self.test_dir, "AGENTS.md")
        with open(root_agents, "w", encoding="utf-8") as f:
            f.write("# Git Root Rules\n- Rule: Clean git commits\n")

        # 创建深层子目录作为当前工作区
        sub_workspace = os.path.join(self.test_dir, "packages", "subproject", "src")
        os.makedirs(sub_workspace, exist_ok=True)

        res = find_project_instructions(sub_workspace)
        self.assertIsNotNone(res)
        path, content = res
        self.assertEqual(path, root_agents)
        self.assertIn("Clean git commits", content)

    def test_candidate_precedence(self):
        """测试文件候选优先级: AGENTS.override.md > AGENTS.md > CLAUDE.md"""
        claude_file = os.path.join(self.test_dir, "CLAUDE.md")
        with open(claude_file, "w", encoding="utf-8") as f:
            f.write("# Claude Rules")

        res = find_project_instructions(self.test_dir)
        self.assertIsNotNone(res)
        self.assertEqual(res[0], claude_file)

        # 放入更高优先级的 AGENTS.md
        agents_file = os.path.join(self.test_dir, "AGENTS.md")
        with open(agents_file, "w", encoding="utf-8") as f:
            f.write("# Agents Rules")

        res2 = find_project_instructions(self.test_dir)
        self.assertEqual(res2[0], agents_file)

        # 放入最高优先级的 AGENTS.override.md
        override_file = os.path.join(self.test_dir, "AGENTS.override.md")
        with open(override_file, "w", encoding="utf-8") as f:
            f.write("# Override Rules")

        res3 = find_project_instructions(self.test_dir)
        self.assertEqual(res3[0], override_file)

    def test_build_system_prompt_structure(self):
        """测试 build_system_prompt 生成的固定 XML 结构与静态缓存友好性"""
        agents_file = os.path.join(self.test_dir, "AGENTS.md")
        with open(agents_file, "w", encoding="utf-8") as f:
            f.write("# Development Guidelines\n- Do not run rm -rf\n")

        prompt = build_system_prompt(self.test_dir, extra_rules="- Extra rule 1")
        self.assertIn("You are Mini-Agent", prompt)
        self.assertIn(f"<cwd>\n{os.path.abspath(self.test_dir)}\n</cwd>", prompt)
        self.assertIn("<rules>", prompt)
        self.assertIn("<project_context>", prompt)
        self.assertIn(f'<project_instructions path="{agents_file}">', prompt)
        self.assertIn("Do not run rm -rf", prompt)
        self.assertIn("<custom_rules>\n- Extra rule 1\n</custom_rules>", prompt)

    def test_build_system_prompt_without_instructions(self):
        """测试在无 AGENTS.md 时的基础 System Prompt 健全性"""
        prompt = build_system_prompt(self.test_dir)
        self.assertIn("You are Mini-Agent", prompt)
        self.assertIn(f"<cwd>\n{os.path.abspath(self.test_dir)}\n</cwd>", prompt)
        self.assertNotIn("<project_context>", prompt)


if __name__ == "__main__":
    unittest.main()
