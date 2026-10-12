import { type Component, truncateToWidth } from "@earendil-works/pi-tui";
import chalk from "chalk";

export type StatusKind = "idle" | "thinking" | "generating" | "tool" | "steered" | "error";

/**
 * 底部状态指示条组件 (对标 Pi 的 StatusIndicator / WorkingDock)
 * 固定在底部输入框上方，负责呈现实时耗时、心跳、工具执行中指示与动态引导反馈。
 * 局部行级平滑渲染，杜绝滚动历史区域的行变动。
 */
export class StatusIndicatorComponent implements Component {
  private kind: StatusKind = "idle";
  private message = "";
  private elapsedSec = 0;

  invalidate(): void {}

  setIdle(): void {
    this.kind = "idle";
    this.message = "";
    this.elapsedSec = 0;
  }

  setThinking(elapsedSec = 0): void {
    this.kind = "thinking";
    this.elapsedSec = elapsedSec;
  }

  setGenerating(elapsedSec = 0): void {
    this.kind = "generating";
    this.elapsedSec = elapsedSec;
  }

  setTool(toolName: string, target = ""): void {
    this.kind = "tool";
    this.message = target ? `${toolName} (${target})` : toolName;
  }

  setSteered(guidance: string): void {
    this.kind = "steered";
    this.message = guidance;
  }

  setError(errorMsg: string): void {
    this.kind = "error";
    this.message = errorMsg;
  }

  updateElapsed(elapsedSec: number): void {
    this.elapsedSec = elapsedSec;
  }

  render(width: number): string[] {
    let line = "";
    const timeStr = this.elapsedSec > 0 ? ` ${chalk.dim(`(${this.elapsedSec}s)`)}` : "";

    switch (this.kind) {
      case "idle":
        line = chalk.dim("  ● Ready │ 随时可输入指令或提问");
        break;
      case "thinking":
        line = `${chalk.cyan.bold("  ⚡ Thinking...")}${timeStr}  ${chalk.dim("Esc/Ctrl+C 随时可注入任务引导")}`;
        break;
      case "generating":
        line = `${chalk.green.bold("  ⚡ Streaming response...")}${timeStr}`;
        break;
      case "tool":
        line = `${chalk.magenta.bold("  ⚡ Running tool:")} ${chalk.yellow(this.message)}${timeStr}`;
        break;
      case "steered":
        line = `${chalk.green.bold("  ✔ 已注入引导:")} ${chalk.white(`"${this.message}"`)}`;
        break;
      case "error":
        line = `${chalk.red.bold("  ✖ 错误:")} ${chalk.red(this.message)}`;
        break;
    }

    return [truncateToWidth(line, width, "")];
  }
}

