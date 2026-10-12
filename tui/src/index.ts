#!/usr/bin/env node
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { BridgeClient } from "./bridge/client.js";
import { MiniAgentTUI } from "./app.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(__dirname, "../..");

async function main() {
  const client = new BridgeClient(projectRoot);
  try {
    client.start();
  } catch (err: any) {
    console.error("启动 Python 桥接服务失败:", err.message);
    process.exit(1);
  }

  const app = new MiniAgentTUI(client);

  process.on("SIGINT", () => {
    void app.shutdown();
  });

  process.on("SIGTERM", () => {
    void app.shutdown();
  });

  await app.start();
}

main().catch((err) => {
  console.error("TUI 运行时异常:", err);
  process.exit(1);
});
