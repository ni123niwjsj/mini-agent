"""Mini-Agent CLI 主入口。

支持：
1. 交互式 REPL 终端: `python3 main.py`
2. 离线模拟测试模式: `python3 main.py --model mock`
3. 本地模型连接: `python3 main.py --base-url http://127.0.0.1:8080/v1 --model qwen`
4. 单次即时指令运行: `python3 main.py -p "帮我计算 1+2"`
"""

import argparse
import asyncio
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from mini_agent.agent import MiniAgent
from mini_agent.ai.client import LLMClient
from mini_agent.cli.display import TerminalDisplay
from mini_agent.cli.repl import handle_event, start_repl


def parse_args():
    parser = argparse.ArgumentParser(description="Mini-Agent: 轻量自主编程 Agent")
    parser.add_argument(
        "-p", "--prompt",
        type=str,
        default=None,
        help="非交互单次任务模式：直接指定提示词执行后退出",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=os.getenv("MINI_AGENT_MODEL", "mock"),
        help="指定调用的模型名称 (默认为 mock 模式或环境变量 MINI_AGENT_MODEL)",
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default=os.getenv("OPENAI_BASE_URL", None),
        help="指定大模型 API Base URL (如本地 http://127.0.0.1:8080/v1)",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=os.getenv("OPENAI_API_KEY", "EMPTY"),
        help="指定大模型 API Key",
    )
    parser.add_argument(
        "-d", "--dir",
        type=str,
        default=".",
        help="指定工作空间目录 (默认当前目录)",
    )
    parser.add_argument(
        "-e", "--effort",
        type=str,
        default=os.getenv("REASONING_EFFORT", None),
        help="指定模型思考强度 (low, medium, high)",
    )
    parser.add_argument(
        "-s", "--session",
        type=str,
        default=None,
        help="恢复指定的持久化会话 ID (如 20261004_130000_abc)",
    )
    parser.add_argument(
        "--list-sessions",
        action="store_true",
        help="查看所有历史持久化会话列表后退出",
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=int(os.getenv("MAX_TURNS", "50")),
        help="单次任务允许的最大轮数 (默认 50，设为 0 表示不限制)",
    )
    return parser.parse_args()


async def run_single_prompt(agent: MiniAgent, prompt: str):
    """运行单次任务"""
    display = TerminalDisplay()
    async for event in agent.stream(prompt):
        handle_event(display, event)


def main():
    args = parse_args()

    if args.list_sessions:
        from mini_agent.core.session import SessionManager
        sessions = SessionManager.list_sessions_in_dir(".sessions")
        if not sessions:
            print("📭 暂无历史会话记录。")
        else:
            print(f"📋 历史会话列表 (共 {len(sessions)} 个):")
            for idx, s in enumerate(sessions, 1):
                created = s["created_at"][:19].replace("T", " ")
                preview = s["first_prompt"] or "(新会话/无提问)"
                print(f"  [{idx}] {s['session_id']}")
                print(f"      时间: {created} | 消息数: {s['message_count']} | 首句: \"{preview}\"")
        return
    
    # 初始化 LLM 客户端
    client = LLMClient(
        api_key=args.api_key,
        base_url=args.base_url,
        model=args.model,
        reasoning_effort=args.effort,
    )

    # 初始化 Agent
    agent = MiniAgent(
        client=client,
        workspace_dir=args.dir,
        session_id=args.session,
        max_turns=args.max_turns,
    )

    try:
        if args.prompt:
            # 单次即时任务模式
            asyncio.run(run_single_prompt(agent, args.prompt))
        else:
            # 启动交互式 REPL
            asyncio.run(start_repl(agent))
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass


if __name__ == "__main__":
    main()
