import chalk from "chalk";
import type { MarkdownTheme } from "@earendil-works/pi-tui";

/**
 * 助手正式回复的 Markdown 终端主题
 */
export function createMarkdownTheme(): MarkdownTheme {
  return {
    heading: (text: string) => chalk.cyan.bold(text),
    link: (text: string) => chalk.blue.underline(text),
    linkUrl: (text: string) => chalk.dim(text),
    code: (text: string) => chalk.yellow(text),
    codeBlock: (text: string) => chalk.white(text),
    codeBlockBorder: (text: string) => chalk.dim(text),
    quote: (text: string) => chalk.dim.italic(text),
    quoteBorder: (text: string) => chalk.dim("│ " + text),
    hr: (text: string) => chalk.dim(text),
    listBullet: (text: string) => chalk.cyan(text),
    bold: (text: string) => chalk.bold(text),
    italic: (text: string) => chalk.italic(text),
    underline: (text: string) => chalk.underline(text),
    strikethrough: (text: string) => chalk.strikethrough(text),
    highlightCode: (code: string) => {
      return code.split("\n").map((line) => chalk.white(line));
    },
    codeBlockIndent: "  ",
  };
}

/**
 * 深度思考 (Reasoning / Thinking) 专属的弱化暗色 Markdown 主题
 * 保持低对比度、斜体弱化感，与正式回复产生清晰视觉分层
 */
export function createThinkingMarkdownTheme(): MarkdownTheme {
  return {
    heading: (text: string) => chalk.dim.bold(text),
    link: (text: string) => chalk.dim.underline(text),
    linkUrl: (text: string) => chalk.dim(text),
    code: (text: string) => chalk.dim(text),
    codeBlock: (text: string) => chalk.dim(text),
    codeBlockBorder: (text: string) => chalk.dim("│ " + text),
    quote: (text: string) => chalk.dim.italic(text),
    quoteBorder: (text: string) => chalk.dim("│ " + text),
    hr: (text: string) => chalk.dim(text),
    listBullet: (text: string) => chalk.dim(text),
    bold: (text: string) => chalk.dim.bold(text),
    italic: (text: string) => chalk.dim.italic(text),
    underline: (text: string) => chalk.dim.underline(text),
    strikethrough: (text: string) => chalk.dim.strikethrough(text),
    highlightCode: (code: string) => {
      return code.split("\n").map((line) => chalk.dim(line));
    },
    codeBlockIndent: "  ",
  };
}
