import { Container, Markdown, Text, Spacer } from "@earendil-works/pi-tui";
import chalk from "chalk";
import { createMarkdownTheme, createThinkingMarkdownTheme } from "../theme.js";
import type { ToolCallItem } from "../bridge/types.js";

/**
 * 助手消息组件 (对齐 Pi 现代化分层渲染与零闪烁规范)
 * 采用容器分层化设计 (Header / Thinking / Tools / Response)，
 * 历史文本区域单向追加，杜绝流式期间频繁擦除重置顶层行导致的全屏清屏。
 */
export class AssistantMessageComponent extends Container {
  private headerContainer: Container;
  private thinkingContainer: Container;
  private toolsContainer: Container;
  private responseContainer: Container;

  private reasoningText = "";
  private responseText = "";
  private isThinking = false;
  private thinkingDone = false;
  private elapsedSec = 0;
  private toolCalls: ToolCallItem[] = [];
  private isThinkingExpanded = true;

  constructor(isThinkingExpanded = true) {
    super();
    this.isThinkingExpanded = isThinkingExpanded;

    this.headerContainer = new Container();
    this.thinkingContainer = new Container();
    this.toolsContainer = new Container();
    this.responseContainer = new Container();

    this.addChild(this.headerContainer);
    this.addChild(this.thinkingContainer);
    this.addChild(this.toolsContainer);
    this.addChild(this.responseContainer);
  }

  setThinking(isThinking: boolean, elapsedSec = 0) {
    this.isThinking = isThinking;
    if (!isThinking && !this.thinkingDone) {
      this.thinkingDone = true;
      this.elapsedSec = elapsedSec;
    }
    this.updateHeader();
  }

  setThinkingExpanded(expanded: boolean) {
    this.isThinkingExpanded = expanded;
    this.updateHeader();
    this.updateThinkingContent();
  }

  toggleThinkingExpanded(): boolean {
    this.isThinkingExpanded = !this.isThinkingExpanded;
    this.updateHeader();
    this.updateThinkingContent();
    return this.isThinkingExpanded;
  }

  appendReasoning(delta: string, elapsedSec = 0) {
    this.reasoningText += delta;
    this.isThinking = true;
    this.elapsedSec = elapsedSec;
    this.updateHeader();
    this.updateThinkingContent();
  }

  appendText(delta: string, elapsedSec = 0) {
    if (this.isThinking) {
      // 思考阶段结束，转入正式生成
      this.isThinking = false;
      this.thinkingDone = true;
      if (elapsedSec > 0 && this.elapsedSec === 0) {
        this.elapsedSec = elapsedSec;
      }
      this.updateHeader();
      this.updateThinkingContent();
    }
    this.responseText += delta;
    this.updateResponseContent();
  }

  addToolCall(tool: ToolCallItem) {
    this.toolCalls.push(tool);
    this.updateTools();
  }

  updateToolResult(toolCallId: string, output: string, isError: boolean) {
    const target = this.toolCalls.find((t) => t.tool_call_id === toolCallId);
    if (target) {
      target.output = output;
      target.is_error = isError;
    }
    this.updateTools();
  }

  finish(finalResponse?: string) {
    this.isThinking = false;
    this.thinkingDone = true;
    if (finalResponse !== undefined) {
      this.responseText = finalResponse;
    }
    this.updateHeader();
    this.updateThinkingContent();
    this.updateTools();
    this.updateResponseContent();
  }

  private updateHeader() {
    this.headerContainer.clear();

    const hasReasoning = Boolean(this.reasoningText.trim());

    if (this.isThinking) {
      // 正在思考时保持静态文案，不把跳动的秒数塞进第一行，避免滚屏后 firstChanged < prevViewportTop 触发全屏清屏
      this.headerContainer.addChild(
        new Text(chalk.cyan.italic("💭 Thinking..."), 1, 0)
      );
    } else if (hasReasoning || this.thinkingDone) {
      const timeStr = this.elapsedSec > 0 ? `${this.elapsedSec}s` : "<1s";
      const tokenCount = Math.round(this.reasoningText.length / 4);
      const tokenStr = tokenCount > 0 ? ` [${tokenCount} tokens]` : "";
      const expandHint = hasReasoning && !this.isThinkingExpanded ? chalk.dim(" (输入 /thinking 展开)") : "";

      this.headerContainer.addChild(
        new Text(chalk.dim.italic(`💭 Thought for ${timeStr}${tokenStr}${expandHint}`), 1, 0)
      );
    }
  }

  private updateThinkingContent() {
    this.thinkingContainer.clear();
    const hasReasoning = Boolean(this.reasoningText.trim());

    if (hasReasoning && (this.isThinking || this.isThinkingExpanded)) {
      this.thinkingContainer.addChild(
        new Markdown(
          this.reasoningText,
          2,
          0,
          createThinkingMarkdownTheme(),
          { color: (text) => chalk.dim(text), italic: true }
        )
      );
    }
  }

  private updateTools() {
    this.toolsContainer.clear();
    if (this.toolCalls.length === 0) return;

    this.toolsContainer.addChild(new Spacer(1));
    for (const tc of this.toolCalls) {
      const isDone = tc.output !== undefined;
      const isError = tc.is_error || false;
      const statusStr = isDone
        ? isError
          ? chalk.red.bold("✖ 失败")
          : chalk.green.bold("✔ 完成")
        : chalk.yellow("⏳ 执行中...");

      const target =
        tc.arguments?.path ||
        tc.arguments?.file_path ||
        tc.arguments?.target_file ||
        tc.arguments?.command ||
        "";
      const targetStr = target ? ` ${chalk.cyan(String(target))}` : "";

      this.toolsContainer.addChild(
        new Text(`  ⚡ ${chalk.magenta.bold(tc.tool_name)}${targetStr} ── ${statusStr}`, 1, 0)
      );

      if (tc.output) {
        const lines = String(tc.output).trim().split("\n");
        const preview =
          lines.length > 6
            ? [...lines.slice(0, 3), chalk.dim(`... (折叠 ${lines.length - 5} 行) ...`), ...lines.slice(-2)]
            : lines;
        for (const l of preview) {
          this.toolsContainer.addChild(new Text(chalk.dim(`    │ ${l}`), 1, 0));
        }
      }
    }
  }

  private updateResponseContent() {
    this.responseContainer.clear();
    if (!this.responseText) return;

    this.responseContainer.addChild(new Spacer(1));
    this.responseContainer.addChild(
      new Markdown(this.responseText, 1, 0, createMarkdownTheme())
    );
  }
}
