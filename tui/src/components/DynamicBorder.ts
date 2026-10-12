import type { Component } from "@earendil-works/pi-tui";
import chalk from "chalk";

/**
 * 动态全宽分割线组件 (对标 Pi 的 DynamicBorder)
 * 自动根据终端当前实际视口列宽绘制水平细线
 */
export class DynamicBorder implements Component {
  private color: (str: string) => string;

  constructor(color: (str: string) => string = (str) => chalk.dim(str)) {
    this.color = color;
  }

  invalidate(): void {}

  render(width: number): string[] {
    return [this.color("─".repeat(Math.max(1, width)))];
  }
}

