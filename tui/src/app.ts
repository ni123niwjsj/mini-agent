import {
  TuiMainScreen,
  ProcessTerminal,
  Container,
  Input,
  Text,
  Spacer,
  Markdown,
  type OverlayHandle,
} from "@earendil-works/pi-tui";
import chalk from "chalk";
import * as path from "node:path";
import * as fs from "node:fs";
import { BridgeClient } from "./bridge/client.js";
import type { SessionInfo, ContextStats, ChatMessage, ToolCallItem } from "./bridge/types.js";
import { createMarkdownTheme } from "./theme.js";
import { UserMessageComponent } from "./components/UserMessage.js";
import { AssistantMessageComponent } from "./components/AssistantMessage.js";
import { FooterComponent } from "./components/Footer.js";
import { DynamicBorder } from "./components/DynamicBorder.js";
import { SelectDialog } from "./components/SelectDialog.js";

function formatSessionTree(treeData: any): string {
  const entries = treeData?.entries || {};
  const childrenMap = treeData?.children_map || {};
  const roots = treeData?.roots || [];
  const activeLeaf = treeData?.active_leaf_id;
  const activePath = new Set(treeData?.active_path_ids || []);

  if (roots.length === 0) {
    return "📭 当前会话暂无节点。";
  }

  const lines: string[] = [
    chalk.cyan.bold("🌲 会话版本分支拓扑图 (Session Tree):"),
    chalk.dim("  (标有 * 的节点为当前活跃主线分支)\n"),
  ];

  function formatSummary(entry: any): string {
    const etype = entry.type || "message";
    if (etype === "message") {
      const role = entry.role || "msg";
      let content = entry.content || "";
      if (Array.isArray(content)) {
        content = content.map((p: any) => p.text || "").join(" ");
      }
      let preview = String(content).replace(/\n/g, " ").trim().slice(0, 40);
      if (!preview && entry.tool_calls && entry.tool_calls.length > 0) {
        const fnName = entry.tool_calls[0].function?.name || entry.tool_calls[0].name || "tool";
        preview = `call ${fnName}...`;
      }
      return `[${role}] ${preview}`;
    } else if (etype === "compaction") {
      return "[compaction] 📌 智能上下文检查点";
    } else if (etype === "model_change") {
      return `[model_change] 🔄 切换模型: ${entry.model_id}`;
    } else if (etype === "usage") {
      return "[usage] 📊 Token 用量";
    }
    return `[${etype}]`;
  }

  function printNode(nodeId: string, prefix = "", isLast = true) {
    const entry = entries[nodeId] || {};
    const isActive = activePath.has(nodeId);
    const isLeaf = nodeId === activeLeaf;

    const marker = isActive ? chalk.green.bold("*") : chalk.dim("o");
    const summary = formatSummary(entry);
    const tag = isLeaf ? chalk.yellow(" ◀ [当前活动叶子]") : "";
    const branchSym = isLast ? "└── " : "├── ";

    lines.push(`${prefix}${branchSym}${nodeId} ${marker} ${summary}${tag}`);

    const children = childrenMap[nodeId] || [];
    const newPrefix = prefix + (isLast ? "    " : "│   ");
    for (let i = 0; i < children.length; i++) {
      printNode(children[i], newPrefix, i === children.length - 1);
    }
  }

  for (let r = 0; r < roots.length; r++) {
    printNode(roots[r], "", r === roots.length - 1);
  }

  return lines.join("\n");
}

class DynamicInput extends Input {
  setPromptAndPlaceholder(prompt: string, placeholder: string) {
    (this as any).prompt = prompt;
    (this as any).placeholder = placeholder;
  }
}

export class MiniAgentTUI {
  private client: BridgeClient;
  private terminal: ProcessTerminal;
  private ui: TuiMainScreen;
  private chatContainer: Container;
  private input: DynamicInput;
  private footer: FooterComponent;

  private sessionInfo: SessionInfo | null = null;
  private stats: ContextStats | null = null;

  private isWorking = false;
  private elapsedSec = 0;
  private timer: NodeJS.Timeout | null = null;
  private currentAssistantMsg: AssistantMessageComponent | null = null;
  private activeOverlay: OverlayHandle | null = null;
  private defaultThinkingExpanded = true;

  constructor(client: BridgeClient) {
    this.client = client;
    this.terminal = new ProcessTerminal();
    this.ui = new TuiMainScreen(this.terminal);

    this.chatContainer = new Container();
    this.input = new DynamicInput({
      prompt: chalk.blue.bold("❯ "),
      placeholder: "",
    });
    this.footer = new FooterComponent();

    // 组装整体组件树 (对标 Pi 的 Container 架构)
    this.ui.addChild(this.chatContainer);
    this.ui.addChild(new Spacer(1));
    this.ui.addChild(new DynamicBorder());
    this.ui.addChild(this.input);
    this.ui.addChild(new DynamicBorder());
    this.ui.addChild(this.footer);

    this.setupEventHandlers();
  }

  private setupEventHandlers() {
    this.input.onSubmit = (text: string) => {
      this.handleSubmit(text);
    };

    // 绑定 Bridge 事件
    this.client.on("agent.start", () => {
      this.isWorking = true;
      this.startTimer();
      this.input.setPromptAndPlaceholder(
        chalk.magenta.bold("⚡ [实时任务引导] "),
        ""
      );
      if (!this.currentAssistantMsg) {
        this.currentAssistantMsg = new AssistantMessageComponent(this.defaultThinkingExpanded);
        this.chatContainer.addChild(this.currentAssistantMsg);
      }
      this.currentAssistantMsg.setThinking(true, 0);
      this.ui.requestRender();
    });

    this.client.on("agent.delta", (params: { content: string; is_reasoning: boolean }) => {
      if (!this.currentAssistantMsg) {
        this.currentAssistantMsg = new AssistantMessageComponent(this.defaultThinkingExpanded);
        this.chatContainer.addChild(this.currentAssistantMsg);
      }
      if (params.is_reasoning) {
        this.currentAssistantMsg.appendReasoning(params.content, this.elapsedSec);
      } else {
        this.currentAssistantMsg.appendText(params.content, this.elapsedSec);
      }
      this.ui.requestRender();
    });

    this.client.on("tool.start", (params: any) => {
      if (this.currentAssistantMsg) {
        this.currentAssistantMsg.addToolCall({
          tool_name: params.tool_name,
          tool_call_id: params.tool_call_id,
          arguments: params.arguments,
        });
        this.ui.requestRender();
      }
    });

    this.client.on("tool.result", (params: any) => {
      if (this.currentAssistantMsg) {
        this.currentAssistantMsg.updateToolResult(params.tool_call_id, params.output, params.is_error);
        this.ui.requestRender();
      }
    });

    this.client.on("agent.end", (params: any) => {
      this.isWorking = false;
      this.stopTimer();
      this.input.setPromptAndPlaceholder(
        chalk.blue.bold("❯ "),
        ""
      );
      if (this.currentAssistantMsg) {
        this.currentAssistantMsg.finish(params.final_response);
        this.currentAssistantMsg = null;
      }
      this.ui.requestRender();
    });

    this.client.on("stats.update", (params: { stats: ContextStats }) => {
      this.stats = params.stats;
      this.footer.update(this.sessionInfo, this.stats);
      this.ui.requestRender();
    });

    this.client.on("agent.steered", (params: { guidance: string }) => {
      this.chatContainer.addChild(
        new Text(chalk.green(`✔ 已注入动态引导: "${params.guidance}"`), 1, 0)
      );
      this.ui.requestRender();
    });

    this.client.on("agent.error", (params: { message: string }) => {
      this.isWorking = false;
      this.stopTimer();
      this.input.setPromptAndPlaceholder(
        chalk.blue.bold("❯ "),
        ""
      );
      this.chatContainer.addChild(new Text(chalk.red.bold(`❌ Agent 异常: ${params.message}`), 1, 0));
      this.currentAssistantMsg = null;
      this.ui.requestRender();
    });
  }

  private startTimer() {
    this.elapsedSec = 0;
    const start = Date.now();
    this.timer = setInterval(() => {
      this.elapsedSec = Math.floor((Date.now() - start) / 1000);
      if (this.currentAssistantMsg) {
        this.ui.requestRender();
      }
    }, 1000);
  }

  private stopTimer() {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
  }

  private replaySessionHistory(messages: ChatMessage[], sessionId: string) {
    const divider = chalk.yellow(
      `\n───── 📂 恢复历史会话 [${sessionId}] (共 ${messages.length} 轮消息) ─────\n`
    );
    this.chatContainer.addChild(new Text(divider, 1, 0));

    for (const msg of messages) {
      if (msg.role === "user") {
        this.chatContainer.addChild(new UserMessageComponent(msg.content));
      } else if (msg.role === "assistant") {
        const asstComp = new AssistantMessageComponent(this.defaultThinkingExpanded);
        if (msg.reasoning) {
          asstComp.appendReasoning(msg.reasoning, 0);
        }
        if (msg.toolCalls && msg.toolCalls.length > 0) {
          for (const tc of msg.toolCalls) {
            asstComp.addToolCall(tc);
          }
        }
        asstComp.finish(msg.content);
        this.chatContainer.addChild(asstComp);
      } else if (msg.role === "system") {
        this.chatContainer.addChild(new Text(chalk.dim(`ℹ️ ${msg.content}`), 1, 0));
      }
    }

    this.chatContainer.addChild(
      new Text(chalk.green(`✔ 历史上下文与用量已完全同步至当前控制台环境。随时可继续提问。`), 1, 0)
    );
    this.ui.requestRender();
  }

  private async handleSubmit(text: string) {
    const trimmed = text.trim();
    if (!trimmed) return;
    this.input.setValue("");

    // 任务执行中的打字即为实时引导 (Steering)
    if (this.isWorking) {
      try {
        await this.client.steer(trimmed);
      } catch (err: any) {
        this.chatContainer.addChild(new Text(chalk.red(`引导失败: ${err.message}`), 1, 0));
        this.ui.requestRender();
      }
      return;
    }

    if (trimmed === "/exit") {
      await this.shutdown();
      return;
    }

    if (trimmed === "/clear") {
      this.chatContainer.clear();
      this.chatContainer.addChild(new Text(chalk.cyan.bold("🤖 Mini-Agent CLI (对标 Pi 现代化架构 v2.0)"), 1, 0));
      this.chatContainer.addChild(
        new Text(chalk.dim("💡 常用指令: /help | /model | /resume | /compact | /tree | /undo | /exit"), 1, 0)
      );
      this.chatContainer.addChild(new Spacer(1));
      this.chatContainer.addChild(new Text(chalk.dim("已清空终端屏幕历史。"), 1, 0));
      this.ui.requestRender();
      return;
    }

    if (trimmed === "/help") {
      const helpMsg =
        `### 💡 Mini-Agent 常用指令速查指南\n\n` +
        `- **/model [序号/名称]** : 查看可选模型列表或按序号切换 (如 \`/model 1\` 或 \`/model gpt-4o\`)\n` +
        `- **/effort [强度/序号]** : 查看或调整思考强度 (1:low, 2:medium, 3:high, 4:none)\n` +
        `- **/thinking** : 切换思考过程展开/折叠显示 (默认展开)\n` +
        `- **/turns [轮数]** : 查看或调整单次任务最大轮数限制 (默认 50，0 表示无限制)\n` +
        `- **/sessions** : 查看所有已保存的历史会话列表与时间、提问摘要\n` +
        `- **/resume [序号/ID]** : 恢复指定的历史会话 (直接输入 \`/resume\` 打开下拉菜单)\n` +
        `- **/new** : 开启全新的独立会话\n` +
        `- **/undo** : 撤销最近一轮交互 (无损回溯到上一轮提问节点)\n` +
        `- **/tree** : 查看当前会话的多分支版本拓扑树 (对齐 git graph)\n` +
        `- **/checkout <ID>** : 切换当前分支到指定的历史分支节点 ID\n` +
        `- **/compact** : 立即触发智能上下文压缩，生成结构化检查点并释放空间\n` +
        `- **/tools** : 查看当前已挂载的所有可用工具清单与功能描述\n` +
        `- **/usage** : 查看详细 Token 消耗、上下文占用与缓存命中率统计\n` +
        `- **/image <路径> [问]** : 发送本地图像附件与针对图像的多模态提问\n` +
        `- **/clear** : 清空当前控制台屏幕\n` +
        `- **/exit** : 退出交互终端\n\n` +
        `*✨ 动态引导: 模型执行任务期间，输入框自动变为【实时任务引导】，随时打字实时纠偏！*`;
      this.chatContainer.addChild(new Markdown(helpMsg, 1, 0, createMarkdownTheme()));
      this.ui.requestRender();
      return;
    }

    if (trimmed === "/thinking") {
      this.defaultThinkingExpanded = !this.defaultThinkingExpanded;
      const stateStr = this.defaultThinkingExpanded ? "展开 (实时呈现完整思考)" : "折叠 (仅显示耗时与用量)";
      this.chatContainer.addChild(
        new Text(chalk.cyan(`💡 思考链显示模式已切换为: [${stateStr}]`), 1, 0)
      );
      this.ui.requestRender();
      return;
    }

    if (trimmed === "/usage") {
      const cur = this.stats?.current_tokens ?? this.sessionInfo?.stats?.current_tokens ?? 0;
      const win = this.stats?.max_tokens ?? this.sessionInfo?.context_window ?? 128000;
      const pct = this.stats?.percent ?? (win > 0 ? ((cur / win) * 100).toFixed(1) : 0);
      const ch = this.stats?.latest_cache_hit_rate ?? this.sessionInfo?.stats?.latest_cache_hit_rate ?? 0;
      const cached = this.stats?.latest_cached_tokens ?? this.sessionInfo?.stats?.latest_cached_tokens ?? 0;
      const ratio = win > 0 ? Math.min(1.0, Math.max(0.0, cur / win)) : 0;
      const filled = Math.round(ratio * 10);
      const empty = 10 - filled;
      const gauge = `[${"■".repeat(filled)}${"░".repeat(empty)}]`;

      const usageMsg =
        `### 📈 会话 Token 与上下文用量统计\n\n` +
        `- **上下文容量占用** : \`${gauge}\` ${cur} / ${win} Tokens (${pct}%)\n` +
        `- **最新轮次缓存命中** : R${cached} Tokens (命中率 ${ch}%)\n` +
        `- **累计输入 Tokens** : ↑${this.stats?.cumulative_prompt_tokens ?? this.sessionInfo?.stats?.cumulative_prompt_tokens ?? 0}\n` +
        `- **累计输出 Tokens** : ↓${this.stats?.cumulative_completion_tokens ?? this.sessionInfo?.stats?.cumulative_completion_tokens ?? 0}\n` +
        `- **累计总计 Tokens** : ${this.stats?.cumulative_total_tokens ?? this.sessionInfo?.stats?.cumulative_total_tokens ?? 0}`;
      this.chatContainer.addChild(new Markdown(usageMsg, 1, 0, createMarkdownTheme()));
      this.ui.requestRender();
      return;
    }

    if (trimmed === "/model" || trimmed.startsWith("/model ") || trimmed === "/models") {
      const parts = trimmed.split(/\s+/, 2);
      if (parts.length > 1 && parts[1]) {
        const inputModel = parts[1].trim();
        try {
          const res = await this.client.setModel(inputModel);
          if (this.sessionInfo) {
            this.sessionInfo.model = res.model;
            this.sessionInfo.context_window = res.context_window;
          }
          this.footer.update(this.sessionInfo, this.stats);
          this.chatContainer.addChild(
            new Text(chalk.green(`✅ 已切换激活模型为: ${res.model}`), 1, 0)
          );
        } catch (err: any) {
          this.chatContainer.addChild(new Text(chalk.red(`切换模型失败: ${err.message}`), 1, 0));
        }
        this.ui.requestRender();
      } else {
        try {
          const cat = await this.client.listModels();
          const items = cat.models.map((m: any) => {
            const winStr =
              m.context_length >= 1000000
                ? `${(m.context_length / 1000000).toFixed(1)}M`
                : `${(m.context_length / 1000).toFixed(0)}k`;
            return {
              value: m.id,
              label: m.id,
              description: `上下文: ${winStr} Tokens ${m.id === (this.sessionInfo?.model || cat.current) ? "(当前)" : ""}`,
            };
          });

          const dialog = new SelectDialog(
            "请选择要切换的激活模型",
            items,
            async (item) => {
              this.closeOverlay();
              try {
                const res = await this.client.setModel(item.value);
                if (this.sessionInfo) {
                  this.sessionInfo.model = res.model;
                  this.sessionInfo.context_window = res.context_window;
                }
                this.footer.update(this.sessionInfo, this.stats);
                this.chatContainer.addChild(
                  new Text(chalk.green(`✅ 已切换激活模型为: ${res.model}`), 1, 0)
                );
              } catch (err: any) {
                this.chatContainer.addChild(new Text(chalk.red(`切换模型失败: ${err.message}`), 1, 0));
              }
              this.ui.requestRender();
            },
            () => {
              this.closeOverlay();
            }
          );
          this.openOverlay(dialog);
        } catch (err: any) {
          this.chatContainer.addChild(new Text(chalk.red(`获取模型列表失败: ${err.message}`), 1, 0));
          this.ui.requestRender();
        }
      }
      return;
    }

    if (trimmed === "/effort" || trimmed.startsWith("/effort ")) {
      const parts = trimmed.split(/\s+/, 2);
      if (parts.length > 1 && parts[1]) {
        const val = parts[1].trim().toLowerCase();
        try {
          const res = await this.client.setEffort(val === "none" ? "" : val);
          const finalEffort = res.reasoning_effort || "none";
          if (this.sessionInfo) this.sessionInfo.reasoning_effort = finalEffort;
          this.chatContainer.addChild(
            new Text(chalk.green(`✅ 思考强度已调整为: ${finalEffort}`), 1, 0)
          );
        } catch (err: any) {
          this.chatContainer.addChild(new Text(chalk.red(`调整思考强度失败: ${err.message}`), 1, 0));
        }
        this.ui.requestRender();
      } else {
        const currentEffort = this.sessionInfo?.reasoning_effort || "none";
        const items = [
          { value: "low", label: "low", description: `低强度思考 (快速响应) ${currentEffort === "low" ? "(当前)" : ""}` },
          { value: "medium", label: "medium", description: `中等强度思考 (平衡深度) ${currentEffort === "medium" ? "(当前)" : ""}` },
          { value: "high", label: "high", description: `深度思考 (严密反思) ${currentEffort === "high" ? "(当前)" : ""}` },
          { value: "none", label: "none", description: `关闭思考 (最快速度) ${currentEffort === "none" ? "(当前)" : ""}` },
        ];
        const dialog = new SelectDialog(
          "请选择思考强度 (Reasoning Effort)",
          items,
          async (item) => {
            this.closeOverlay();
            try {
              const res = await this.client.setEffort(item.value === "none" ? "" : item.value);
              const finalEffort = res.reasoning_effort || "none";
              if (this.sessionInfo) this.sessionInfo.reasoning_effort = finalEffort;
              this.chatContainer.addChild(
                new Text(chalk.green(`✅ 思考强度已调整为: ${finalEffort}`), 1, 0)
              );
            } catch (err: any) {
              this.chatContainer.addChild(new Text(chalk.red(`调整思考强度失败: ${err.message}`), 1, 0));
            }
            this.ui.requestRender();
          },
          () => {
            this.closeOverlay();
          }
        );
        this.openOverlay(dialog);
      }
      return;
    }

    if (trimmed === "/turns" || trimmed.startsWith("/turns ")) {
      const parts = trimmed.split(/\s+/, 2);
      if (parts.length > 1 && parts[1]) {
        const n = parseInt(parts[1], 10);
        if (!isNaN(n)) {
          try {
            await this.client.setTurns(n);
            this.chatContainer.addChild(
              new Text(chalk.green(`✅ 单次任务最大轮数已调整为: ${n === 0 ? "无限制 (0)" : `${n} 轮`}`), 1, 0)
            );
          } catch (err: any) {
            this.chatContainer.addChild(new Text(chalk.red(`调整轮数失败: ${err.message}`), 1, 0));
          }
        }
      }
      this.ui.requestRender();
      return;
    }

    if (trimmed === "/sessions" || trimmed === "/session") {
      try {
        const res = await this.client.listSessions();
        const sessList = res.sessions || [];
        if (sessList.length === 0) {
          this.chatContainer.addChild(new Text(chalk.dim("📭 暂无历史会话记录。"), 1, 0));
        } else {
          const lines = sessList.map((s: any, idx: number) => {
            const isCur = s.session_id === this.sessionInfo?.session_id ? chalk.green(" ◀ [当前活跃]") : "";
            const time = s.created_at ? s.created_at.slice(0, 19).replace("T", " ") : "";
            const first = s.first_prompt ? `"${s.first_prompt.slice(0, 35)}..."` : "(新会话)";
            return `  [${idx + 1}] ${chalk.cyan(s.session_id)}${isCur}\n      时间: ${time} │ 消息数: ${s.message_count} │ 首句: ${first}`;
          });
          this.chatContainer.addChild(
            new Text(`📋 历史会话列表 (共 ${sessList.length} 个):\n${lines.join("\n")}`, 1, 0)
          );
        }
      } catch (err: any) {
        this.chatContainer.addChild(new Text(chalk.red(`获取历史会话失败: ${err.message}`), 1, 0));
      }
      this.ui.requestRender();
      return;
    }

    if (trimmed === "/resume" || trimmed.startsWith("/resume ") || trimmed === "resume" || trimmed.startsWith("resume ")) {
      const parts = trimmed.split(/\s+/, 2);
      if (parts.length > 1 && parts[1]) {
        const sid = parts[1].trim();
        try {
          const res = await this.client.resumeSession(sid);
          if (this.sessionInfo) {
            this.sessionInfo.session_id = res.session_id;
            this.sessionInfo.cwd = res.header?.cwd || this.sessionInfo.cwd;
          }
          if (res.stats) {
            this.stats = res.stats;
          }
          this.footer.update(this.sessionInfo, this.stats);
          this.replaySessionHistory((res.messages || []) as ChatMessage[], res.session_id);
        } catch (err: any) {
          this.chatContainer.addChild(new Text(chalk.red(`恢复会话失败: ${err.message}`), 1, 0));
          this.ui.requestRender();
        }
      } else {
        try {
          const res = await this.client.listSessions();
          const sessList = res.sessions || [];
          if (sessList.length === 0) {
            this.chatContainer.addChild(new Text(chalk.dim("📭 暂无历史会话记录。"), 1, 0));
            this.ui.requestRender();
          } else {
            const items = sessList.map((s: any) => {
              const time = s.created_at ? s.created_at.slice(11, 16) : "";
              const first = s.first_prompt ? `"${s.first_prompt.slice(0, 25)}..."` : "(无提问)";
              return {
                value: s.session_id,
                label: s.session_id,
                description: `${time} │ ${s.message_count}条 │ ${first} ${s.session_id === this.sessionInfo?.session_id ? "(当前)" : ""}`,
              };
            });

            const dialog = new SelectDialog(
              "请选择要恢复的历史会话",
              items,
              async (item) => {
                this.closeOverlay();
                try {
                  const r = await this.client.resumeSession(item.value);
                  if (this.sessionInfo) {
                    this.sessionInfo.session_id = r.session_id;
                    this.sessionInfo.cwd = r.header?.cwd || this.sessionInfo.cwd;
                  }
                  if (r.stats) {
                    this.stats = r.stats;
                  }
                  this.footer.update(this.sessionInfo, this.stats);
                  this.replaySessionHistory((r.messages || []) as ChatMessage[], r.session_id);
                } catch (err: any) {
                  this.chatContainer.addChild(new Text(chalk.red(`恢复会话失败: ${err.message}`), 1, 0));
                  this.ui.requestRender();
                }
              },
              () => {
                this.closeOverlay();
              }
            );
            this.openOverlay(dialog);
          }
        } catch (err: any) {
          this.chatContainer.addChild(new Text(chalk.red(`获取历史会话失败: ${err.message}`), 1, 0));
          this.ui.requestRender();
        }
      }
      return;
    }

    if (trimmed === "/compact") {
      try {
        const res = await this.client.compact();
        if (res && res.compaction && Object.keys(res.compaction).length > 0) {
          const c = res.compaction;
          this.chatContainer.addChild(
            new Text(chalk.green(`⚡ 上下文压缩完成: 释放空间 ${c.saved_tokens} Tokens (-${c.saved_percent}%)`), 1, 0)
          );
        } else {
          this.chatContainer.addChild(new Text(chalk.dim("ℹ️ 当前历史较少或轮次不足，无需压缩。"), 1, 0));
        }
      } catch (err: any) {
        this.chatContainer.addChild(new Text(chalk.red(`压缩失败: ${err.message}`), 1, 0));
      }
      this.ui.requestRender();
      return;
    }

    if (trimmed === "/undo") {
      try {
        const res = await this.client.undo();
        if (res.stats) {
          this.stats = res.stats;
          this.footer.update(this.sessionInfo, this.stats);
        }
        if (res.new_leaf_id) {
          this.chatContainer.addChild(
            new Text(chalk.green(`↩️ 已成功撤销上一轮交互 [当前新节点: ${res.new_leaf_id}]，剩余 ${res.message_count} 条。`), 1, 0)
          );
        } else {
          this.chatContainer.addChild(new Text(chalk.dim("当前已处于会话起点，无更多可撤销交互。"), 1, 0));
        }
      } catch (err: any) {
        this.chatContainer.addChild(new Text(chalk.red(`撤销失败: ${err.message}`), 1, 0));
      }
      this.ui.requestRender();
      return;
    }

    if (trimmed === "/tree") {
      try {
        const tree = await this.client.getSessionTree();
        this.chatContainer.addChild(new Text("\n" + formatSessionTree(tree) + "\n", 1, 0));
      } catch (err: any) {
        this.chatContainer.addChild(new Text(chalk.red(`获取分支拓扑树失败: ${err.message}`), 1, 0));
      }
      this.ui.requestRender();
      return;
    }

    if (trimmed.startsWith("/checkout")) {
      const parts = trimmed.split(/\s+/, 2);
      if (parts.length > 1 && parts[1]) {
        try {
          const res = await this.client.checkout(parts[1].trim());
          if (res.stats) {
            this.stats = res.stats;
            this.footer.update(this.sessionInfo, this.stats);
          }
          this.chatContainer.addChild(
            new Text(chalk.green(`🔀 已成功切换至分支节点 [${parts[1].trim()}]，重构消息 ${res.message_count} 条。`), 1, 0)
          );
        } catch (err: any) {
          this.chatContainer.addChild(new Text(chalk.red(`分支切换失败: ${err.message}`), 1, 0));
        }
      }
      this.ui.requestRender();
      return;
    }

    if (trimmed === "/tools") {
      try {
        const res = await this.client.listTools();
        const tools = res.tools || [];
        const lines = tools.map((t: any) => `  • ${chalk.yellow.bold(t.name)}: ${t.description || "无描述"}`);
        this.chatContainer.addChild(
          new Text(`🛠️ 当前已挂载可用工具清单 (共 ${tools.length} 个):\n${lines.join("\n")}`, 1, 0)
        );
      } catch (err: any) {
        this.chatContainer.addChild(new Text(chalk.red(`获取工具清单失败: ${err.message}`), 1, 0));
      }
      this.ui.requestRender();
      return;
    }

    if (trimmed === "/new") {
      try {
        const res = await this.client.newSession();
        if (this.sessionInfo) this.sessionInfo.session_id = res.session_id;
        if (res.stats) this.stats = res.stats;
        this.footer.update(this.sessionInfo, this.stats);
        this.chatContainer.clear();
        this.chatContainer.addChild(new Text(chalk.green(`已开启全新独立会话: ${res.session_id}`), 1, 0));
      } catch (err: any) {
        this.chatContainer.addChild(new Text(chalk.red(`新建会话失败: ${err.message}`), 1, 0));
      }
      this.ui.requestRender();
      return;
    }

    // 拦截任何未知斜杠指令
    if (trimmed.startsWith("/")) {
      this.chatContainer.addChild(
        new Text(chalk.red(`❌ 未知指令 '${trimmed}'。输入 /help 查看完整可用指令列表。`), 1, 0)
      );
      this.ui.requestRender();
      return;
    }

    // 正常用户任务提问
    this.chatContainer.addChild(new UserMessageComponent(trimmed));
    this.currentAssistantMsg = new AssistantMessageComponent(this.defaultThinkingExpanded);
    this.chatContainer.addChild(this.currentAssistantMsg);

    this.isWorking = true;
    this.startTimer();
    this.input.setPromptAndPlaceholder(
      chalk.magenta.bold("⚡ [实时任务引导] "),
      ""
    );
    this.ui.requestRender();

    try {
      await this.client.sendPrompt(trimmed);
    } catch (err: any) {
      this.isWorking = false;
      this.stopTimer();
      this.input.setPromptAndPlaceholder(
        chalk.blue.bold("❯ "),
        ""
      );
      this.chatContainer.addChild(new Text(chalk.red.bold(`❌ 执行失败: ${err.message}`), 1, 0));
      this.currentAssistantMsg = null;
      this.ui.requestRender();
    }
  }

  private openOverlay(dialog: SelectDialog) {
    if (this.activeOverlay) {
      this.activeOverlay.hide();
    }
    this.activeOverlay = this.ui.showOverlay(dialog, {
      width: "80%",
      maxHeight: 12,
      anchor: "center",
    });
    this.ui.setFocus(dialog);
    this.ui.requestRender();
  }

  private closeOverlay() {
    if (this.activeOverlay) {
      this.activeOverlay.hide();
      this.activeOverlay = null;
    }
    this.ui.setFocus(this.input);
    this.ui.requestRender();
  }

  async start() {
    this.chatContainer.addChild(new Text(chalk.cyan.bold("🤖 Mini-Agent CLI (对标 Pi 现代化架构 v2.0)"), 1, 0));
    this.chatContainer.addChild(
      new Text(chalk.dim("💡 常用指令: /help | /model | /resume | /compact | /tree | /undo | /exit"), 1, 0)
    );
    this.chatContainer.addChild(new Spacer(1));

    try {
      const info = await this.client.initSession();
      this.sessionInfo = info;
      if (info.stats) this.stats = info.stats;
      this.footer.update(this.sessionInfo, this.stats);
    } catch {
      // 忽略启动初期初始化异常
    }

    this.ui.setFocus(this.input);
    this.ui.start();
    this.ui.requestRender();
  }

  async shutdown() {
    this.stopTimer();
    this.ui.stop();
    await this.terminal.drainInput(500);
    this.client.stop();
    process.exit(0);
  }
}
