# Mini-Agent Development Rules

## Conversational Style
- Keep responses concise, technical, and direct.
- No conversational filler, cheerful fluff, or repetitive pleasantries.
- Explain non-trivial designs as: problem, concrete trace/example, then solution.
- When asked a question or given feedback, explain the technical rationale first before making changes.
- Avoid unnecessary emojis in commits, code, and comments.

## Environment & Commands
- Virtual Environment: Always use `.venv/bin/python` for commands, scripts, and tests.
- Unit Testing: Run all unit tests with `.venv/bin/python -m unittest discover tests`.
- After code modifications: Always run unit tests to verify zero regressions before reporting completion.
- Interactive Agent CLI: Run with `python main.py` or `.venv/bin/python main.py`.
- Ad-hoc scripts: Write them to a temp file, execute, and clean up immediately. Do not leave stray script files in the workspace.

## Code Quality & Architecture
- Mini-Agent follows an autonomous ReAct agent harness architecture:
  - `mini_agent/ai/`: Unified LLM client adapter (OpenAI/DeepSeek compatible) and dynamic model catalog.
  - `mini_agent/core/`: ReAct event loop (`loop.py`), context management (`context.py`), tree session persistence (`session.py`), compaction (`compaction.py`), and project instructions (`instructions.py`).
  - `mini_agent/tools/`: Tool registry and tool implementations (`bash`, `file`, `edit`).
  - `mini_agent/cli/`: Interactive REPL, Rich display/formatting (`display.py`), and keyboard menu selector (`menu.py`).
- Coding standards:
  - Python 3.10+ typing syntax. Keep type hints clean and accurate.
  - Always read target files completely before making wide-ranging changes.
  - Use `edit_file` for targeted replacements; use `write_file` only for creating new files or complete rewrites.
  - Preserve backward compatibility for historical session files (`.jsonl`) and DAG branch structures.
  - Main ReAct loop must remain fully asynchronous (`async`/`await`), avoiding blocking synchronous I/O.

## Safety & Git Guidelines
- Never run destructive commands that bypass safety or destroy work:
  - `git reset --hard`, `git checkout .`, `git clean -fd`, `rm -rf`.
- Only stage and commit files modified in the current session (`git add <file1> <file2>`), never `git add -A` or `git add .`.
- Before committing, run `git status` and verify only intended files are staged.
- Never commit unless explicitly instructed by the user.

## User Override
- User explicit instructions in conversation always take precedence over rules in this file.
