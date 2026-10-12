import {
  Container,
  Text,
  Spacer,
  SelectList,
  type SelectItem,
  type SelectListTheme,
  type Component,
} from "@earendil-works/pi-tui";
import chalk from "chalk";

const defaultTheme: SelectListTheme = {
  selectedPrefix: () => chalk.cyan("❯ "),
  selectedText: (text) => chalk.cyan.bold(text),
  description: (text) => chalk.dim(text),
  scrollInfo: (text) => chalk.dim(text),
  noMatch: (text) => chalk.yellow(text),
};

export class SelectDialog extends Container {
  private selectList: SelectList;
  private titleText: string;

  constructor(
    title: string,
    items: SelectItem[],
    onSelect: (item: SelectItem) => void,
    onCancel: () => void,
    maxVisible = 6
  ) {
    super();
    this.titleText = title;
    this.selectList = new SelectList(items, maxVisible, defaultTheme);
    this.selectList.onSelect = onSelect;
    this.selectList.onCancel = onCancel;

    this.addChild(new Text(chalk.cyan.bold(`🔍 ${this.titleText}`), 1, 0));
    this.addChild(new Text(chalk.dim("  (↑/↓ 或 j/k 移动, Enter 确认, Esc/q 取消)"), 1, 0));
    this.addChild(new Spacer(1));
    this.addChild(this.selectList);
  }

  handleInput(data: string): void {
    this.selectList.handleInput(data);
  }
}
