"""Mini-Agent CLI 主入口。"""

import asyncio
import os
from dotenv import load_dotenv

from mini_agent.agent import MiniAgent
from mini_agent.cli.repl import start_repl


def main():
    load_dotenv()
    agent = MiniAgent(workspace_dir=os.getcwd())
    asyncio.run(start_repl(agent))


if __name__ == "__main__":
    main()
