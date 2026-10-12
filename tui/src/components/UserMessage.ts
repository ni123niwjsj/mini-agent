import { Container, Markdown, Text, Spacer } from "@earendil-works/pi-tui";
import chalk from "chalk";
import { createMarkdownTheme } from "../theme.js";

/**
 * 用户消息组件 (对标现代化 AI CLI 规范)
 * 采用整洁的左侧高亮强调线与富文本 Markdown 缩进排版
 */
export class UserMessageComponent extends Container {
  private text: string;

  constructor(text: string) {
    super();
    this.text = text;
    this.rebuild();
  }

  private rebuild() {
    this.clear();
    this.addChild(new Spacer(1));
    this.addChild(new Text(chalk.blue.bold("▌ You:"), 1, 0));
    this.addChild(new Markdown(this.text, 3, 0, createMarkdownTheme()));
    this.addChild(new Spacer(1));
  }
}
