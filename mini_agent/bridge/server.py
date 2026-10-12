"""Mini-Agent Stdio JSON-RPC 桥接服务端。

负责在标准输入输出 (stdio) 上收发 JSON-RPC 消息，连接 TypeScript/Ink 前端与 Python Agent 内核：
- 接收前端指令: session.init, prompt.send, agent.steer, agent.interrupt, config.set_model, etc.
- 向上发射事件: agent.start, agent.delta, tool.start, tool.result, stats.update, agent.end, error
- 天然支持无阻塞任务动态引导 (Steering Queue)
"""

import asyncio
import json
import os
import subprocess
import sys
from typing import Any, Dict, List, Optional, TextIO, Union

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from mini_agent.agent import MiniAgent
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


def get_git_branch(cwd: str) -> Optional[str]:
    """获取指定目录的 Git 分支名称"""
    try:
        res = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=1,
        )
        if res.returncode == 0:
            branch = res.stdout.strip()
            return branch if branch else None
    except Exception:
        pass
    return None


def serialize_context_messages(agent_context: Any) -> List[Dict[str, Any]]:
    """将 Agent 上下文历史消息序列化为符合前端 Transcript 组件规范的 ChatMessage 列表。
    
    能够完整保真用户提问、助手深度思维链、工具调用与结果、上下文压缩检查点。
    """
    result: List[Dict[str, Any]] = []
    tool_call_map: Dict[str, Dict[str, Any]] = {}

    for idx, msg in enumerate(getattr(agent_context, "messages", [])):
        role = msg.get("role")
        content = msg.get("content", "")
        reasoning = msg.get("reasoning")
        raw_tools = msg.get("tool_calls") or []

        # 1. 用户提问
        if role == "user":
            if isinstance(content, list):
                text_parts = [p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"]
                has_img = any(isinstance(p, dict) and p.get("type") in ("image_url", "image") for p in content)
                img_suffix = " 🖼️ [包含图像附件]" if has_img else ""
                text_content = " ".join(text_parts) + img_suffix
            else:
                text_content = str(content or "")

            result.append({
                "id": f"hist-u-{idx}",
                "role": "user",
                "content": text_content,
            })

        # 2. Assistant 回复
        elif role == "assistant":
            tool_items = []
            for tc in raw_tools:
                tc_id = tc.get("id") or f"tc-{len(tool_items)}"
                fn = tc.get("function") or {}
                fn_name = fn.get("name") or tc.get("name") or "tool"
                raw_args = fn.get("arguments") or tc.get("arguments") or {}
                if isinstance(raw_args, str):
                    try:
                        args_dict = json.loads(raw_args)
                    except Exception:
                        args_dict = {"raw": raw_args}
                elif isinstance(raw_args, dict):
                    args_dict = raw_args
                else:
                    args_dict = {}

                tool_item = {
                    "tool_name": fn_name,
                    "tool_call_id": tc_id,
                    "arguments": args_dict,
                }
                tool_items.append(tool_item)
                tool_call_map[tc_id] = tool_item

            text_content = ""
            if isinstance(content, str):
                text_content = content
            elif isinstance(content, list):
                text_parts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
                text_content = "".join(text_parts)

            result.append({
                "id": f"hist-a-{idx}",
                "role": "assistant",
                "content": text_content,
                "reasoning": reasoning if isinstance(reasoning, str) and reasoning.strip() else None,
                "toolCalls": tool_items if tool_items else None,
            })

        # 3. 工具执行结果
        elif role in ("tool", "toolResult"):
            tc_id = msg.get("tool_call_id") or ""
            if tc_id and tc_id in tool_call_map:
                tool_call_map[tc_id]["output"] = str(msg.get("content", ""))
                tool_call_map[tc_id]["is_error"] = bool(msg.get("is_error", False))

    return result


class BridgeServer:
    """Stdio JSON-RPC 桥接服务管理器"""

    def __init__(
        self,
        agent: Optional[MiniAgent] = None,
        workspace_dir: str = ".",
        session_id: Optional[str] = None,
        in_stream: Optional[TextIO] = None,
        out_stream: Optional[TextIO] = None,
    ):
        self.workspace_dir = os.path.abspath(workspace_dir)
        self.agent = agent or MiniAgent(
            workspace_dir=self.workspace_dir,
            session_id=session_id,
        )
        self.in_stream = in_stream or sys.stdin
        self.out_stream = out_stream or sys.stdout
        self._running = False
        self._current_task: Optional[asyncio.Task] = None
        self._steering_queue: asyncio.Queue = asyncio.Queue()

    def emit_event(self, method: str, params: Optional[Dict[str, Any]] = None) -> None:
        """向前端发射单向通知事件 (Notification)"""
        msg = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
        }
        raw = json.dumps(msg, ensure_ascii=False)
        self.out_stream.write(raw + "\n")
        self.out_stream.flush()

    def emit_response(
        self,
        req_id: Any,
        result: Optional[Any] = None,
        error: Optional[Dict[str, Any]] = None,
    ) -> None:
        """向前端响应 JSON-RPC 请求 (Response)"""
        msg: Dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": req_id,
        }
        if error is not None:
            msg["error"] = error
        else:
            msg["result"] = result if result is not None else {}
        raw = json.dumps(msg, ensure_ascii=False)
        self.out_stream.write(raw + "\n")
        self.out_stream.flush()

    def get_session_info(self) -> Dict[str, Any]:
        """获取当前会话基础元数据与实时遥测指标"""
        cwd = self.agent.workspace_dir
        branch = get_git_branch(cwd) or "main"
        model = getattr(self.agent.client, "model", "default")
        context_win = self.agent.context.context_window
        stats = self.agent.context.get_context_stats()
        effort = getattr(self.agent.client, "reasoning_effort", "high") or "auto"
        sid = self.agent.current_session_id or ""
        messages = serialize_context_messages(self.agent.context)

        return {
            "cwd": cwd,
            "branch": branch,
            "model": model,
            "context_window": context_win,
            "stats": stats,
            "reasoning_effort": effort,
            "session_id": sid,
            "messages": messages,
        }

    async def handle_request(self, req: Dict[str, Any]) -> None:
        """处理单条前端 JSON-RPC 请求"""
        req_id = req.get("id")
        method = req.get("method", "")
        params = req.get("params", {})

        try:
            if method == "session.init":
                info = self.get_session_info()
                self.emit_response(req_id, result=info)

            elif method == "prompt.send":
                prompt = params.get("prompt", "")
                images = params.get("images")
                if not prompt and not images:
                    self.emit_response(req_id, error={"code": -32602, "message": "Prompt 不能为空"})
                    return

                # 在后台 Task 运行该 turn，便于接收中途的 steering 和 interrupt
                self._current_task = asyncio.create_task(self._run_prompt_turn(prompt, images))
                try:
                    res = await self._current_task
                    self.emit_response(req_id, result=res)
                except asyncio.CancelledError:
                    self.emit_response(req_id, result={"status": "interrupted"})
                finally:
                    self._current_task = None

            elif method == "agent.steer":
                guidance = params.get("guidance", "").strip()
                if guidance:
                    await self._steering_queue.put(guidance)
                    self.emit_response(req_id, result={"status": "queued", "guidance": guidance})
                    self.emit_event("agent.steered", {"guidance": guidance})
                else:
                    self.emit_response(req_id, error={"code": -32602, "message": "Guidance 不能为空"})

            elif method == "agent.interrupt":
                if self._current_task and not self._current_task.done():
                    self._current_task.cancel()
                    self.emit_response(req_id, result={"status": "interrupting"})
                else:
                    self.emit_response(req_id, result={"status": "idle"})

            elif method == "config.set_model":
                new_model = str(params.get("model", "")).strip()
                if not new_model:
                    self.emit_response(req_id, error={"code": -32602, "message": "Model 不能为空"})
                    return

                # 支持通过数字序号选择模型 (例如 /model 1)
                catalog = []
                if hasattr(self.agent.client, "get_model_catalog"):
                    try:
                        res_cat = self.agent.client.get_model_catalog()
                        if asyncio.iscoroutine(res_cat):
                            catalog = await res_cat
                        elif isinstance(res_cat, list):
                            catalog = res_cat
                    except Exception:
                        catalog = []

                target_model = new_model
                if new_model.isdigit() and catalog:
                    idx = int(new_model) - 1
                    if 0 <= idx < len(catalog):
                        target_model = catalog[idx].id
                    else:
                        self.emit_response(
                            req_id,
                            error={"code": -32602, "message": f"无效的模型序号 [{new_model}]，当前范围: 1~{len(catalog)}"}
                        )
                        return
                elif catalog:
                    matched = [m.id for m in catalog if m.id.lower() == new_model.lower()]
                    if not matched:
                        matched = [m.id for m in catalog if new_model.lower() in m.id.lower()]
                    if len(matched) == 1:
                        target_model = matched[0]

                self.agent.client.model = target_model
                new_win = self.agent.client.get_context_window(target_model)
                self.agent.context.context_window = new_win
                if self.agent.session_manager:
                    self.agent.session_manager.append_model_change(provider="custom", model_id=target_model)
                self.emit_response(req_id, result={"model": target_model, "context_window": new_win})
                self.emit_event("stats.update", {"stats": self.agent.context.get_context_stats()})

            elif method == "config.set_effort":
                effort = str(params.get("effort", "")).strip()
                if effort == "1":
                    effort = "low"
                elif effort == "2":
                    effort = "medium"
                elif effort == "3":
                    effort = "high"
                elif effort in ("4", "0", "none"):
                    effort = None
                elif effort and effort.lower() == "none":
                    effort = None
                elif effort:
                    effort = effort.lower()
                else:
                    effort = None

                self.agent.client.reasoning_effort = effort
                self.emit_response(req_id, result={"reasoning_effort": effort or "none"})

            elif method == "config.set_turns":
                turns = int(params.get("turns", 50))
                self.agent.context.max_turns = turns
                self.emit_response(req_id, result={"max_turns": turns})

            elif method == "config.list_models":
                catalog = await self.agent.client.get_model_catalog()
                models = [
                    {
                        "id": spec.id,
                        "name": getattr(spec, "name", spec.id),
                        "context_length": spec.context_length,
                    }
                    for spec in catalog
                ]
                self.emit_response(req_id, result={"models": models, "current": self.agent.client.model})

            elif method == "context.compact":
                c_res = await self.agent.compact()
                self.emit_response(req_id, result={"compaction": c_res or {}})
                self.emit_event("stats.update", {"stats": self.agent.context.get_context_stats()})

            elif method == "session.tree":
                tree = self.agent.get_session_tree()
                if isinstance(tree, dict) and isinstance(tree.get("active_path_ids"), (set, tuple)):
                    tree["active_path_ids"] = list(tree["active_path_ids"])
                self.emit_response(req_id, result=tree)

            elif method == "session.list":
                sessions = self.agent.list_sessions()
                self.emit_response(req_id, result={"sessions": sessions})

            elif method == "session.resume":
                sid = str(params.get("session_id", "")).strip()
                sessions = self.agent.list_sessions()

                # 支持通过数字序号恢复 (例如 /resume 1)
                if sid.isdigit() and sessions:
                    idx = int(sid) - 1
                    if 0 <= idx < len(sessions):
                        sid = sessions[idx]["session_id"]
                    else:
                        self.emit_response(
                            req_id,
                            error={"code": -32602, "message": f"无效的会话序号 [{sid}]，当前共有 {len(sessions)} 个会话 (1~{len(sessions)})"}
                        )
                        return
                elif sid and sessions:
                    # 支持前缀匹配
                    matched = [s["session_id"] for s in sessions if s["session_id"].startswith(sid)]
                    if len(matched) == 1:
                        sid = matched[0]
                    elif len(matched) > 1:
                        self.emit_response(
                            req_id,
                            error={"code": -32602, "message": f"会话 ID 前缀 '{sid}' 匹配到多个候选: {matched}"}
                        )
                        return

                if not sid:
                    self.emit_response(req_id, error={"code": -32602, "message": "请指定要恢复的会话 ID 或序号"})
                    return

                header, count = self.agent.load_session(sid)
                history = serialize_context_messages(self.agent.context)
                self.emit_response(req_id, result={
                    "session_id": sid,
                    "header": header,
                    "message_count": count,
                    "messages": history,
                    "stats": self.agent.context.get_context_stats(),
                })
                self.emit_event("stats.update", {"stats": self.agent.context.get_context_stats()})

            elif method == "session.new":
                sid = params.get("session_id")
                new_id = self.agent.new_session(session_id=sid)
                self.emit_response(req_id, result={
                    "session_id": new_id,
                    "stats": self.agent.context.get_context_stats(),
                })
                self.emit_event("stats.update", {"stats": self.agent.context.get_context_stats()})

            elif method == "session.undo":
                new_leaf, count = self.agent.undo()
                history = serialize_context_messages(self.agent.context)
                self.emit_response(req_id, result={
                    "new_leaf_id": new_leaf,
                    "message_count": count,
                    "messages": history,
                    "stats": self.agent.context.get_context_stats(),
                })
                self.emit_event("stats.update", {"stats": self.agent.context.get_context_stats()})

            elif method == "session.checkout":
                node_id = str(params.get("node_id", "")).strip()
                if not node_id:
                    self.emit_response(req_id, error={"code": -32602, "message": "节点 ID 不能为空"})
                    return

                header, count = self.agent.checkout(node_id)
                history = serialize_context_messages(self.agent.context)
                self.emit_response(req_id, result={
                    "header": header,
                    "message_count": count,
                    "messages": history,
                    "stats": self.agent.context.get_context_stats(),
                })
                self.emit_event("stats.update", {"stats": self.agent.context.get_context_stats()})

            elif method == "tools.list":
                tools_data = []
                for t_name in self.agent.registry.list_tools():
                    tool_obj = self.agent.registry.get(t_name)
                    desc = tool_obj.description if tool_obj else ""
                    schema = tool_obj.to_schema() if tool_obj and hasattr(tool_obj, "to_schema") else {}
                    tools_data.append({"name": t_name, "description": desc, "schema": schema})
                self.emit_response(req_id, result={"tools": tools_data})

            elif method == "exit":
                self._running = False
                self.emit_response(req_id, result={"status": "exiting"})

            else:
                self.emit_response(
                    req_id,
                    error={"code": -32601, "message": f"未知的 RPC 方法: {method}"},
                )
        except Exception as e:
            self.emit_response(
                req_id,
                error={"code": -32603, "message": f"执行异常: {str(e)}"},
            )

    async def _run_prompt_turn(
        self,
        prompt: Union[str, List[Dict[str, Any]]],
        images: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """流式运行单轮 Agent 任务并将各事件实时通知前端"""
        async for event in self.agent.stream(
            prompt,
            images=images,
            steering_queue=self._steering_queue,
        ):
            if isinstance(event, AgentStart):
                self.emit_event("agent.start", {"user_prompt": event.user_prompt})
            elif isinstance(event, AssistantDelta):
                self.emit_event(
                    "agent.delta",
                    {"content": event.content, "is_reasoning": event.is_reasoning},
                )
            elif isinstance(event, AssistantMessage):
                self.emit_event(
                    "assistant.message",
                    {
                        "content": event.content,
                        "tool_calls": event.tool_calls,
                        "usage": event.usage,
                    },
                )
            elif isinstance(event, ToolCallStart):
                self.emit_event(
                    "tool.start",
                    {
                        "tool_name": event.tool_name,
                        "tool_call_id": event.tool_call_id,
                        "arguments": event.arguments,
                    },
                )
            elif isinstance(event, ToolResult):
                self.emit_event(
                    "tool.result",
                    {
                        "tool_name": event.tool_name,
                        "tool_call_id": event.tool_call_id,
                        "output": str(event.output),
                        "is_error": event.is_error,
                    },
                )
            elif isinstance(event, CompactionStart):
                self.emit_event("compaction.start", {"tokens_before": event.tokens_before})
            elif isinstance(event, CompactionEnd):
                self.emit_event(
                    "compaction.end",
                    {
                        "tokens_before": event.tokens_before,
                        "tokens_after": event.tokens_after,
                        "saved_tokens": event.saved_tokens,
                        "saved_percent": event.saved_percent,
                        "summary": event.summary,
                    },
                )
            elif isinstance(event, AgentEnd):
                self.emit_event(
                    "agent.end",
                    {
                        "final_response": event.final_response,
                        "total_turns": event.total_turns,
                        "usage": event.usage,
                    },
                )
            elif isinstance(event, Error):
                self.emit_event("agent.error", {"message": event.message})

        # 任务结束后同步最新的遥测数据
        self.emit_event("stats.update", {"stats": self.agent.context.get_context_stats()})
        return {"status": "completed"}

    async def serve(self) -> None:
        """启动主服务监听循环"""
        self._running = True
        try:
            while self._running:
                line = await asyncio.to_thread(self.in_stream.readline)
                if not line:
                    break
                line_str = line.strip()
                if not line_str:
                    continue
                try:
                    req_obj = json.loads(line_str)
                    asyncio.create_task(self.handle_request(req_obj))
                except json.JSONDecodeError as jde:
                    self.emit_response(
                        None,
                        error={"code": -32700, "message": f"无效的 JSON 字符串: {str(jde)}"},
                    )
        except (asyncio.CancelledError, KeyboardInterrupt):
            pass
        finally:
            self._running = False


def main() -> None:
    """CLI 入口函数: python -m mini_agent.bridge.server"""
    server = BridgeServer()
    asyncio.run(server.serve())


if __name__ == "__main__":
    main()
