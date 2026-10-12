"""项目级规范文件 (AGENTS.md / CLAUDE.md) 探测与加载模块。

参考 Pi 的设计哲学：
1. 优先探测当前工作区目录下的规范文件 (AGENTS.md, CLAUDE.md 等)。
2. 若当前工作区为子目录，向上溯源查找 Git 仓库根目录。
3. 支持用户主目录全局偏好文件 (~/.mini-agent/AGENTS.md) 兜底。
4. 将规范内容注入到 System Prompt 的固定位置，提高模型执行精确度并极大提升 Prompt Cache 命中率。
"""

import os
from typing import List, Optional, Tuple

INSTRUCTION_CANDIDATE_FILENAMES: List[str] = [
    "AGENTS.override.md",
    "AGENTS.md",
    "AGENTS.MD",
    "CLAUDE.md",
    "CLAUDE.MD",
]


def find_git_root(start_dir: str) -> Optional[str]:
    """向上查找包含 .git 目录的仓库根目录"""
    curr = os.path.abspath(start_dir)
    while True:
        if os.path.exists(os.path.join(curr, ".git")):
            return curr
        parent = os.path.dirname(curr)
        if parent == curr:  # 到达文件系统根目录
            return None
        curr = parent


def find_instruction_file_in_dir(directory: str) -> Optional[str]:
    """在指定目录中探测候选规范文件"""
    if not os.path.isdir(directory):
        return None
    for name in INSTRUCTION_CANDIDATE_FILENAMES:
        candidate_path = os.path.join(directory, name)
        if os.path.isfile(candidate_path):
            return candidate_path
    return None


def find_project_instructions(workspace_dir: str) -> Optional[Tuple[str, str]]:
    """递归探测并加载工作区规范文件内容。
    
    Returns:
        Optional[Tuple[file_path, content]]: 成功则返回文件绝对路径与完整文本，否则返回 None。
    """
    abs_workspace = os.path.abspath(workspace_dir)

    # 1. 优先探测当前工作区目录
    target = find_instruction_file_in_dir(abs_workspace)
    if target:
        try:
            with open(target, "r", encoding="utf-8") as f:
                return target, f.read().strip()
        except Exception:
            pass

    # 2. 向上递归直到 Git 仓库根目录 (解决在子目录下运行 Agent 的情况)
    git_root = find_git_root(abs_workspace)
    if git_root and git_root != abs_workspace:
        target = find_instruction_file_in_dir(git_root)
        if target:
            try:
                with open(target, "r", encoding="utf-8") as f:
                    return target, f.read().strip()
            except Exception:
                pass

    # 3. 全局用户偏好兜底 (~/.mini-agent/AGENTS.md)
    home_dir = os.path.expanduser("~")
    global_target = find_instruction_file_in_dir(os.path.join(home_dir, ".mini-agent"))
    if global_target:
        try:
            with open(global_target, "r", encoding="utf-8") as f:
                return global_target, f.read().strip()
        except Exception:
            pass

    return None


def build_system_prompt(workspace_dir: str, extra_rules: Optional[str] = None) -> str:
    """构建注入环境信息与项目级规范的标准 System Prompt。"""
    abs_workspace = os.path.abspath(workspace_dir)

    sections = [
        "You are Mini-Agent, an autonomous coding and task execution assistant operating in the user's workspace.",
        f"<cwd>\n{abs_workspace}\n</cwd>",
        (
            "<rules>\n"
            "- Be concise, direct, and accurate.\n"
            "- Use 'grep' and 'glob' for codebase search and file discovery instead of running find or grep in bash.\n"
            "- Use 'web_search' and 'web_fetch' to search the internet and read online documentation or web pages when needed.\n"
            "- Use 'read_file', 'write_file', 'edit_file', and 'bash' to examine files, modify code, or run commands.\n"
            "- For tasks involving multiple steps, use the 'todo' tool to plan and track your steps (add, update, list).\n"
            "- Always read files in full before making edits.\n"
            "- Use edit_file for precise text replacement; use write_file only for new files.\n"
            "- When an error occurs in tool execution, analyze the error output and attempt to self-correct.\n"
            "- Delegate codebase exploration, architecture planning, or isolated subtasks to specialized subagents using the 'task' tool (explore/plan/general) to keep context clean.\n"
            "- Never run destructive commands (git reset --hard, git checkout ., git clean -fd, rm -rf).\n"
            "</rules>"
        ),
    ]

    # 动态探测并注入项目级规范 (AGENTS.md / CLAUDE.md)
    instruction_result = find_project_instructions(abs_workspace)
    if instruction_result:
        instr_path, instr_content = instruction_result
        sections.append(
            f"<project_context>\n"
            f"Project-specific instructions and guidelines:\n\n"
            f"<project_instructions path=\"{instr_path}\">\n"
            f"{instr_content}\n"
            f"</project_instructions>\n"
            f"</project_context>"
        )

    if extra_rules:
        sections.append(f"<custom_rules>\n{extra_rules}\n</custom_rules>")

    return "\n\n".join(sections)
