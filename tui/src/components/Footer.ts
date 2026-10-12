import { type Component, truncateToWidth, visibleWidth } from "@earendil-works/pi-tui";
import chalk from "chalk";
import type { SessionInfo, ContextStats } from "../bridge/types.js";

function formatTokens(tokens: number): string {
  if (tokens >= 1_000_000) {
    return `${(tokens / 1_000_000).toFixed(1)}M`;
  }
  if (tokens >= 1_000) {
    return `${(tokens / 1_000).toFixed(0)}k`;
  }
  return String(tokens);
}

function formatCwd(cwd: string): string {
  const home = process.env.HOME || "";
  if (home && cwd.startsWith(home)) {
    return "~" + cwd.slice(home.length);
  }
  return cwd;
}

function formatModel(model: string): string {
  if (model.includes("/")) {
    const parts = model.split("/");
    return parts[parts.length - 1] || model;
  }
  return model;
}

export class FooterComponent implements Component {
  private sessionInfo: SessionInfo | null = null;
  private stats: ContextStats | null = null;

  update(sessionInfo: SessionInfo | null, stats: ContextStats | null) {
    this.sessionInfo = sessionInfo;
    this.stats = stats;
  }

  invalidate(): void {}

  render(width: number): string[] {
    const rawCwd = this.sessionInfo?.cwd || ".";
    const branch = this.sessionInfo?.branch || "main";
    const rawModel = this.sessionInfo?.model || "default";
    const effort = this.sessionInfo?.reasoning_effort || "none";

    const shortCwd = formatCwd(rawCwd);
    const shortModel = formatModel(rawModel);

    const curTokens = this.stats?.current_tokens || this.sessionInfo?.stats?.current_tokens || 0;
    const maxTokens = this.stats?.max_tokens || this.sessionInfo?.context_window || 128000;
    const pct = this.stats?.percent || (maxTokens > 0 ? ((curTokens / maxTokens) * 100).toFixed(1) : "0.0");
    const cacheHit = this.stats?.latest_cache_hit_rate ?? this.sessionInfo?.stats?.latest_cache_hit_rate ?? 0;
    const cachedTokens = this.stats?.latest_cached_tokens ?? this.sessionInfo?.stats?.latest_cached_tokens ?? 0;
    const promptTokens = this.stats?.cumulative_prompt_tokens ?? this.sessionInfo?.stats?.cumulative_prompt_tokens ?? 0;
    const completionTokens = this.stats?.cumulative_completion_tokens ?? this.sessionInfo?.stats?.cumulative_completion_tokens ?? 0;

    // Line 1: 路径与分支 (左) │ 键盘操作提示 (右)
    const line1Left = `${chalk.dim(shortCwd)} ${chalk.green(`(${branch})`)}`;
    const line1Right = chalk.dim("Tab 补全 │ ↑/↓ 历史");
    const gap1 = Math.max(1, width - visibleWidth(line1Left) - visibleWidth(line1Right));
    const line1 = truncateToWidth(line1Left + " ".repeat(gap1) + line1Right, width, "");

    // Line 2: Token / 缓存统计 (左) │ 模型与思考级别 (右)
    const chColor = cacheHit > 50 ? chalk.green : cacheHit > 0 ? chalk.cyan : chalk.dim;
    const cacheHitStr = chColor(`CH${cacheHit}%`);
    const pctColor = Number(pct) > 80 ? chalk.red : Number(pct) > 60 ? chalk.yellow : chalk.dim;
    const pctStr = pctColor(`${pct}%/${formatTokens(maxTokens)}`);

    const line2Left = `↑${formatTokens(promptTokens)} ↓${formatTokens(completionTokens)} R${formatTokens(cachedTokens)} ${cacheHitStr} ${pctStr}`;
    const line2Right = `${chalk.dim(shortModel)} ${chalk.dim("•")} ${chalk.cyan(effort)}`;
    const gap2 = Math.max(1, width - visibleWidth(line2Left) - visibleWidth(line2Right));
    const line2 = truncateToWidth(line2Left + " ".repeat(gap2) + line2Right, width, "");

    return [line1, line2];
  }
}
