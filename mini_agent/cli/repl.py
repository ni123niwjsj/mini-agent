"""交互式 REPL 命令行循环。

负责处理用户输入、调度 Agent 事件流并执行斜杠指令 (/help, /clear, /tools, /exit)。
"""

import asyncio
import base64
import os
import sys
from typing import Any
from mini_agent.cli.display import TerminalDisplay, format_tokens
from mini_agent.core.events import (
    AgentEnd,
    AgentStart,
    AssistantDelta,
    AssistantMessage,
    CompactionEnd,
    CompactionStart,
    Error,
    ToolCallStart,
    ToolResult,
)


def handle_event(display: TerminalDisplay, event: Any) -> None:
    """将 Agent 内核发射的生命周期事件派发给 TerminalDisplay 渲染"""
    if isinstance(event, AgentStart):
        display.print_agent_start(event.user_prompt)
    elif isinstance(event, AssistantDelta):
        display.print_assistant_delta(event.content, event.is_reasoning)
    elif isinstance(event, AssistantMessage):
        display.print_assistant_message_end()
    elif isinstance(event, ToolCallStart):
        display.print_tool_start(event.tool_name, event.arguments)
    elif isinstance(event, ToolResult):
        display.print_tool_result(event.tool_name, str(event.output), event.is_error)
    elif isinstance(event, CompactionStart):
        display.print_compaction_start(event.tokens_before)
    elif isinstance(event, CompactionEnd):
        display.print_compaction_end(event.tokens_before, event.tokens_after, event.saved_percent)
    elif isinstance(event, AgentEnd):
        display.print_agent_end(event.total_turns, usage=event.usage)
    elif isinstance(event, Error):
        display.print_error(event.message)


async def start_repl(agent: Any) -> None:
    """启动交互式终端 REPL 循环"""
    display = TerminalDisplay()
    
    # 获取基本信息展示欢迎横幅
    tools = agent.registry.list_tools()
    display.print_banner(
        workspace_dir=getattr(agent, "workspace_dir", "."),
        model_name=getattr(agent.client, "model", "default"),
        tools_count=len(tools),
        session_id=getattr(agent, "current_session_id", None),
        context_window=getattr(agent.context, "context_window", None),
    )

    while True:
        try:
            # 命令行提示符
            sys.stdout.write("\033[1;36mmini-agent>\033[0m ")
            sys.stdout.flush()
            user_input = sys.stdin.readline()

            # 处理 EOF (Ctrl+D)
            if not user_input:
                print("\n会话结束，再见！")
                break

            user_input = user_input.strip()
            if not user_input:
                continue

            # 处理内置斜杠指令
            if user_input.startswith("/"):
                cmd = user_input.lower()
                if cmd in ("/exit", "/quit"):
                    print("再见！感谢使用 Mini-Agent。")
                    break
                elif cmd == "/clear":
                    agent.context.clear()
                    print("\n🧹 内存会话历史已清空，上下文已重置。\n")
                    continue
                elif cmd == "/new":
                    new_id = agent.new_session()
                    print(f"\n✨ 已开启全新会话: {new_id}\n")
                    continue
                elif cmd in ("/sessions", "/session"):
                    sessions = agent.list_sessions()
                    if not sessions:
                        print("\n📭 暂无历史会话记录。\n")
                    else:
                        print(f"\n📋 历史会话列表 (共 {len(sessions)} 个):")
                        for idx, s in enumerate(sessions, 1):
                            curr = " (当前活跃)" if s["session_id"] == agent.current_session_id else ""
                            created = s["created_at"][:19].replace("T", " ")
                            preview = s["first_prompt"] or "(新会话/无提问)"
                            print(f"  [{idx}] {s['session_id']}{curr}")
                            print(f"      时间: {created} | 消息数: {s['message_count']} | 首句: \"{preview}\"")
                        print("\n提示: 输入 `/resume <会话ID 或 序号>` 即可恢复历史会话。\n")
                    continue
                elif cmd.startswith("/resume"):
                    parts = user_input.split(maxsplit=1)
                    if len(parts) > 1 and parts[1].strip():
                        target = parts[1].strip().strip("<>'\"")
                        sessions = agent.list_sessions()
                        # 支持按序号恢复
                        if target.isdigit():
                            idx = int(target) - 1
                            if 0 <= idx < len(sessions):
                                target = sessions[idx]["session_id"]
                        else:
                            # 支持前缀匹配
                            matched = [s["session_id"] for s in sessions if s["session_id"].startswith(target)]
                            if len(matched) == 1:
                                target = matched[0]

                        try:
                            header, count = agent.load_session(target)
                            print(f"\n✅ 已成功恢复会话 [{target}]，载入历史消息 {count} 条。\n")
                        except Exception as e:
                            print(f"\n❌ 恢复会话失败: {str(e)}\n")
                    else:
                        print("用法: /resume <会话ID 或 序号>")
                    continue
                elif cmd.startswith("/image"):
                    parts = user_input.split(maxsplit=2)
                    if len(parts) >= 2:
                        img_path = parts[1].strip().strip("<>'\"")
                        img_prompt = parts[2].strip() if len(parts) > 2 else "请详细描述并分析这张图片的内容。"
                        workspace = getattr(agent, "workspace_dir", ".")
                        resolved_path = img_path if os.path.isabs(img_path) else os.path.join(workspace, img_path)
                        if not os.path.exists(resolved_path):
                            if os.path.exists(os.path.abspath(img_path)):
                                resolved_path = os.path.abspath(img_path)
                            else:
                                print(f"\n❌ 图片文件不存在: {img_path}\n")
                                continue

                        from mini_agent.tools.file import SUPPORTED_IMAGE_EXTENSIONS
                        ext = os.path.splitext(resolved_path)[1].lower()
                        if ext not in SUPPORTED_IMAGE_EXTENSIONS:
                            print(f"\n❌ 不支持的图像格式: {ext} (支持: {', '.join(SUPPORTED_IMAGE_EXTENSIONS.keys())})\n")
                            continue

                        try:
                            with open(resolved_path, "rb") as f:
                                raw_bytes = f.read()
                            mime = SUPPORTED_IMAGE_EXTENSIONS[ext]
                            b64 = base64.b64encode(raw_bytes).decode("utf-8")
                            user_content = [
                                {"type": "text", "text": f"[{img_path}] {img_prompt}"},
                                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                            ]
                            async for event in agent.stream(user_content):
                                handle_event(display, event)
                        except Exception as e:
                            print(f"\n❌ 读取/发送图片失败: {str(e)}\n")
                    else:
                        print("用法: /image <图片路径> [针对图片的问题或要求]\n")
                    continue
                elif cmd == "/tools":
                    print("\n🔧 当前已注册的可用工具列表:")
                    for t_name in agent.registry.list_tools():
                        tool_obj = agent.registry.get(t_name)
                        desc = tool_obj.description if tool_obj else ""
                        print(f"  • {t_name:12s} - {desc}")
                    print()
                    continue
                elif cmd in ("/model", "/models"):
                    print("\n🔍 正在从服务端获取可用模型规格列表...")
                    try:
                        catalog = await agent.client.get_model_catalog()
                        print(f"📋 可用模型列表 (共 {len(catalog)} 个):")
                        for spec in catalog:
                            current_tag = " (当前激活)" if spec.id == agent.client.model else ""
                            win_display = format_tokens(spec.context_length)
                            print(f"  • {spec.id:35s} | 上下文: {win_display:>5s}{current_tag}")
                        print("\n提示: 输入 `/model <模型名>` 即可在线切换。\n")
                    except Exception as e:
                        print(f"❌ 获取失败: {str(e)}\n")
                    continue
                elif cmd.startswith("/model ") or cmd.startswith("/models "):
                    parts = user_input.split(maxsplit=1)
                    if len(parts) > 1 and parts[1].strip():
                        # 自动清理用户习惯性输入的尖括号 <...> 或引号 "..."
                        new_model = parts[1].strip().strip("<>'\"").strip()
                        agent.client.model = new_model
                        new_window = agent.client.get_context_window(new_model)
                        agent.context.context_window = new_window
                        print(f"\n✅ 已切换激活模型为: {new_model}")
                        print(f"⚙️ 上下文窗口已自适应调整为: {format_tokens(new_window)} Tokens\n")
                    else:
                        print("用法: /model <模型名称>")
                    continue
                elif cmd.startswith("/effort"):
                    parts = user_input.split()
                    if len(parts) == 2 and parts[1].lower() in ("low", "medium", "high", "none"):
                        val = None if parts[1].lower() == "none" else parts[1].lower()
                        agent.client.reasoning_effort = val
                        print(f"\n✅ 思考强度已调整为: {parts[1].lower()}\n")
                    else:
                        print(f"当前思考强度: {agent.client.reasoning_effort or '未设置'}")
                        print("用法: /effort <low | medium | high | none>\n")
                    continue
                elif cmd == "/turns" or cmd.startswith("/turns "):
                    parts = user_input.split(maxsplit=1)
                    if len(parts) == 1:
                        curr = "无限制" if agent.context.max_turns <= 0 else f"{agent.context.max_turns} 轮"
                        print(f"\n⚙️ 当前单次任务最大轮数限制: {curr}")
                        print("提示: 输入 `/turns <数字>` (如 `/turns 50` 或 `/turns 0` 解除限制) 即可动态调整。\n")
                    else:
                        arg_val = parts[1].strip().lower()
                        if arg_val in ("unlimited", "inf", "none", "0"):
                            agent.context.max_turns = 0
                            print("\n✅ 已解除单次任务最大轮数限制 (无上限模式)。\n")
                        elif arg_val.isdigit():
                            new_val = int(arg_val)
                            agent.context.max_turns = new_val
                            print(f"\n✅ 单次任务最大轮数限制已调整为: {new_val} 轮\n")
                        else:
                            print("用法: /turns [轮数 | 0 | unlimited]\n")
                    continue
                elif cmd in ("/usage", "/stats"):
                    stats = agent.context.get_context_stats()
                    cur = format_tokens(stats.get("current_tokens", 0))
                    win = format_tokens(stats.get("context_window", 128000))
                    pct = stats.get("percent", 0.0)
                    cum_in = format_tokens(stats.get("cumulative_prompt_tokens", 0))
                    cum_out = format_tokens(stats.get("cumulative_completion_tokens", 0))
                    cum_tot = format_tokens(stats.get("cumulative_total_tokens", 0))
                    cum_cached = format_tokens(stats.get("cumulative_cached_tokens", 0))
                    cum_ch = stats.get("cumulative_cache_hit_rate", 0.0)
                    latest_ch = stats.get("latest_cache_hit_rate", 0.0)
                    latest_r = format_tokens(stats.get("latest_cached_tokens", 0))

                    print("\n📈 会话 Token 与上下文用量统计:")
                    print(f"  • 当前上下文占用 : {cur} / {win} Tokens ({pct}%)")
                    print(f"  • 最新轮次缓存命中: R{latest_r} (CH {latest_ch}%)")
                    print(f"  • 累计输入 Tokens : ↑{cum_in}")
                    print(f"  • 累计输出 Tokens : ↓{cum_out}")
                    print(f"  • 累计总计 Tokens : {cum_tot}")
                    print(f"  • 累计缓存命中数 : R{cum_cached} (平均命中率 {cum_ch}%)\n")
                    continue
                elif cmd in ("/compact", "/compaction") or cmd.startswith("/compact "):
                    print("\n⚡ 正在对当前上下文执行智能压缩...")
                    from mini_agent.core.compaction import perform_compaction
                    res = await perform_compaction(agent.context, agent.client)
                    if res:
                        display.print_compaction_end(
                            res["tokens_before"],
                            res["tokens_after"],
                            res["saved_percent"],
                        )
                        print(f"  • 已压缩历史消息: {res['compacted_count']} 条")
                        print(f"  • 释放上下文空间: {format_tokens(res['saved_tokens'])} Tokens (-{res['saved_percent']}%)")
                        if res["read_files"]:
                            print(f"  • 追踪只读文件: {', '.join(res['read_files'])}")
                        if res["modified_files"]:
                            print(f"  • 追踪修改文件: {', '.join(res['modified_files'])}")
                        print()
                    else:
                        print("ℹ️ 当前上下文消息过少或用户轮次不足 (需至少保留最近 2 轮)，无需压缩。\n")
                    continue
                elif cmd == "/help":
                    print("\n💡 常用快捷命令:")
                    print("  • /image   : 上传并提问本地图像 (如 /image 粘贴的图像.png 这是什么)")
                    print("  • /compact : 手动触发智能上下文压缩，生成结构化检查点并释放空间")
                    print("  • /usage   : 查看当前上下文占用与 Token 缓存命中统计")
                    print("  • /sessions: 查看所有历史持久化会话")
                    print("  • /resume  : 恢复历史会话 (如 /resume 1 或 /resume 20261004_xxx)")
                    print("  • /new     : 开启全新会话")
                    print("  • /turns   : 查看或调整单次任务最大轮数限制 (如 /turns 50 或 /turns 0 无限制)")
                    print("  • /tools   : 查看当前已挂载的所有工具")
                    print("  • /models  : 自动获取服务端所有可用模型列表")
                    print("  • /model   : 切换当前大模型 (如 /model deepseek/deepseek-v4.1-flash)")
                    print("  • /effort  : 设置思考强度 (如 /effort high / medium / low)")
                    print("  • /clear   : 清空内存中的上下文历史")
                    print("  • /exit    : 退出命令行交互")
                    print("  • 直接输入任何文本即可开始与 Agent 交互。\n")
                    continue
                else:
                    print(f"未知指令 '{user_input}'。输入 /help 查看帮助。")
                    continue

            # 驱动 Agent 执行任务并流式渲染
            async for event in agent.stream(user_input):
                handle_event(display, event)

        except (KeyboardInterrupt, asyncio.CancelledError):
            cur_task = asyncio.current_task()
            if cur_task and hasattr(cur_task, "uncancel"):
                cur_task.uncancel()
            print("\n\n⚠️ 收到中断信号 (Ctrl+C)，当前任务已停止。\n")
            continue
        except Exception as e:
            display.print_error(f"终端运行异常: {str(e)}")
