import chalk from "chalk";
import type { MarkdownTheme } from "@earendil-works/pi-tui";

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
