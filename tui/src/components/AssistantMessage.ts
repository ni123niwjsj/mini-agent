import { Container, Markdown, Text, Spacer } from "@earendil-works/pi-tui";
import chalk from "chalk";
import { createMarkdownTheme, createThinkingMarkdownTheme } from "../theme.js";
import type { ToolCallItem } from "../bridge/types.js";

export class AssistantMessageComponent extends Container {
  private contentContainer: Container;
  private reasoningText = "";
  private responseText = "";
  private isThinking = false;
  private elapsedSec = 0;
  private toolCalls: ToolCallItem[] = [];
  private isThinkingExpanded = true;

  constructor(isThinkingExpanded = true) {
    super();
    this.isThinkingExpanded = isThinkingExpanded;
    this.contentContainer = new Container();
    this.addChild(this.contentContainer);
  }

  setThinking(isThinking: boolean, elapsedSec = 0) {
    this.isThinking = isThinking;
    this.elapsedSec = elapsedSec;
    this.rebuild();
  }

  setThinkingExpanded(expanded: boolean) {
    this.isThinkingExpanded = expanded;
    this.rebuild();
  }

  toggleThinkingExpanded(): boolean {
    this.isThinkingExpanded = !this.isThinkingExpanded;
    this.rebuild();
    return this.isThinkingExpanded;
  }

  appendReasoning(delta: string, elapsedSec = 0) {
    this.reasoningText += delta;
    this.isThinking = true;
    this.elapsedSec = elapsedSec;
    this.rebuild();
  }

  appendText(delta: string, elapsedSec = 0) {
    this.isThinking = false;
    this.responseText += delta;
    this.elapsedSec = elapsedSec;
    this.rebuild();
  }

  addToolCall(tool: ToolCallItem) {
    this.toolCalls.push(tool);
    this.rebuild();
  }

  updateToolResult(toolCallId: string, output: string, isError: boolean) {
    const target = this.toolCalls.find((t) => t.tool_call_id === toolCallId);
    if (target) {
      target.output = output;
      target.is_error = isError;
    }
    this.rebuild();
  }

  finish(finalResponse?: string) {
    this.isThinking = false;
    if (finalResponse !== undefined) {
      this.responseText = finalResponse;
    }
    this.rebuild();
  }

  private rebuild() {
    this.contentContainer.clear();

    const hasReasoning = Boolean(this.reasoningText.trim());

    // 1. 思考状态指示与思考正文实时打字机流式输出
    if (this.isThinking) {
      const timeStr = this.elapsedSec > 0 ? ` (${this.elapsedSec}s)` : "";
      this.contentContainer.addChild(
        new Text(chalk.cyan.italic(`💭 Thinking${timeStr}...`), 1, 0)
      );
      if (hasReasoning) {
        this.contentContainer.addChild(
          new Markdown(
            this.reasoningText.trim(),
            2,
            0,
            createThinkingMarkdownTheme(),
            { color: (text) => chalk.dim(text), italic: true }
          )
        );
      }
    } else if (hasReasoning || this.elapsedSec > 0) {
      const timeStr = this.elapsedSec > 0 ? `${this.elapsedSec}s` : "<1s";
      const tokenCount = Math.round(this.reasoningText.length / 4);
      const tokenStr = tokenCount > 0 ? ` [${tokenCount} tokens]` : "";
      const expandHint = hasReasoning && !this.isThinkingExpanded ? chalk.dim(" (输入 /thinking 展开)") : "";

      this.contentContainer.addChild(
        new Text(chalk.dim.italic(`💭 Thought for ${timeStr}${tokenStr}${expandHint}`), 1, 0)
      );

      if (this.isThinkingExpanded && hasReasoning) {
        this.contentContainer.addChild(
          new Markdown(
            this.reasoningText.trim(),
            2,
            0,
            createThinkingMarkdownTheme(),
            { color: (text) => chalk.dim(text), italic: true }
          )
        );
      }
    }

    // 2. 工具调用清单
    if (this.toolCalls.length > 0) {
      this.contentContainer.addChild(new Spacer(1));
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

        this.contentContainer.addChild(
          new Text(`  ⚡ ${chalk.magenta.bold(tc.tool_name)}${targetStr} ── ${statusStr}`, 1, 0)
        );

        if (tc.output) {
          const lines = String(tc.output).trim().split("\n");
          const preview =
            lines.length > 6
              ? [...lines.slice(0, 3), chalk.dim(`... (折叠 ${lines.length - 5} 行) ...`), ...lines.slice(-2)]
              : lines;
          for (const l of preview) {
            this.contentContainer.addChild(new Text(chalk.dim(`    │ ${l}`), 1, 0));
          }
        }
      }
    }

    // 3. 正式回答正文 (基于 marked 的实时 ANSI Markdown 渲染组件)
    if (this.responseText.trim()) {
      this.contentContainer.addChild(new Spacer(1));
      this.contentContainer.addChild(
        new Markdown(this.responseText.trim(), 1, 0, createMarkdownTheme())
      );
    }
  }
}
