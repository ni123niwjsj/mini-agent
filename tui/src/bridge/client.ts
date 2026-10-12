/**
 * Stdio JSON-RPC 客户端。
 * 负责拉起 Python Agent 桥接子进程并维持长连接通信。
 */

import { spawn, type ChildProcess } from "node:child_process";
import { EventEmitter } from "node:events";
import * as path from "node:path";
import * as readline from "node:readline";
import * as fs from "node:fs";
import type {
  JsonRpcRequest,
  JsonRpcResponse,
  JsonRpcNotification,
  SessionInfo,
  ModelSpec,
} from "./types.js";

export class BridgeClient extends EventEmitter {
  private child: ChildProcess | null = null;
  private reqId = 0;
  private pendingRequests = new Map<
    number | string,
    { resolve: (val: any) => void; reject: (err: any) => void }
  >();
  private projectRoot: string;

  constructor(projectRoot?: string) {
    super();
    this.projectRoot = projectRoot || path.resolve(process.cwd(), "..");
  }

  private resolvePython(): string {
    const venvPython = path.join(this.projectRoot, ".venv", "bin", "python");
    if (fs.existsSync(venvPython)) {
      return venvPython;
    }
    const envVenv = process.env.VIRTUAL_ENV;
    if (envVenv && fs.existsSync(path.join(envVenv, "bin", "python"))) {
      return path.join(envVenv, "bin", "python");
    }
    return "python3";
  }

  public start(): void {
    const pythonExe = this.resolvePython();
    this.child = spawn(pythonExe, ["-m", "mini_agent.bridge.server"], {
      cwd: this.projectRoot,
      stdio: ["pipe", "pipe", "pipe"],
      env: {
        ...process.env,
        PYTHONUNBUFFERED: "1",
      },
    });

    if (!this.child.stdout || !this.child.stdin) {
      throw new Error("无法创建子进程 stdio 管道");
    }

    const rl = readline.createInterface({
      input: this.child.stdout,
      terminal: false,
    });

    rl.on("line", (line) => {
      const trimmed = line.trim();
      if (!trimmed) return;
      try {
        const msg = JSON.parse(trimmed);
        if ("id" in msg && msg.id !== undefined && msg.id !== null) {
          const pending = this.pendingRequests.get(msg.id);
          if (pending) {
            this.pendingRequests.delete(msg.id);
            if (msg.error) {
              pending.reject(new Error(msg.error.message || "RPC 错误"));
            } else {
              pending.resolve(msg.result);
            }
          }
        } else if ("method" in msg) {
          this.emit(msg.method, msg.params);
        }
      } catch (err) {}
    });

    if (this.child.stderr) {
      this.child.stderr.on("data", (chunk) => {
        this.emit("stderr", chunk.toString());
      });
    }

    this.child.on("exit", (code) => {
      this.emit("exit", code);
      for (const [_, pending] of this.pendingRequests) {
        pending.reject(new Error(`Python 桥接进程已退出 (代码: ${code})`));
      }
      this.pendingRequests.clear();
    });
  }

  public async request<T = any>(method: string, params: Record<string, any> = {}): Promise<T> {
    if (!this.child || !this.child.stdin || this.child.killed) {
      throw new Error("Python 桥接服务未连接");
    }

    const id = ++this.reqId;
    const req: JsonRpcRequest = {
      jsonrpc: "2.0",
      id,
      method,
      params,
    };

    return new Promise<T>((resolve, reject) => {
      this.pendingRequests.set(id, { resolve, reject });
      this.child!.stdin!.write(JSON.stringify(req) + "\n");
    });
  }

  public async initSession(): Promise<SessionInfo> {
    return this.request<SessionInfo>("session.init");
  }

  public async sendPrompt(prompt: string, images?: any[]): Promise<any> {
    return this.request("prompt.send", { prompt, images });
  }

  public async steer(guidance: string): Promise<any> {
    return this.request("agent.steer", { guidance });
  }

  public async interrupt(): Promise<any> {
    return this.request("agent.interrupt");
  }

  public async setModel(model: string): Promise<any> {
    return this.request("config.set_model", { model });
  }

  public async setEffort(effort: string): Promise<any> {
    return this.request("config.set_effort", { effort });
  }

  public async listModels(): Promise<{ models: ModelSpec[]; current: string }> {
    return this.request("config.list_models");
  }

  public async compact(): Promise<any> {
    return this.request("context.compact");
  }

  public async getSessionTree(): Promise<any> {
    return this.request("session.tree");
  }

  public async listSessions(): Promise<any> {
    return this.request("session.list");
  }

  public async resumeSession(sessionId: string): Promise<any> {
    return this.request("session.resume", { session_id: sessionId });
  }

  public async newSession(sessionId?: string): Promise<any> {
    return this.request("session.new", { session_id: sessionId });
  }

  public async undo(): Promise<any> {
    return this.request("session.undo");
  }

  public async checkout(nodeId: string): Promise<any> {
    return this.request("session.checkout", { node_id: nodeId });
  }

  public async listTools(): Promise<any> {
    return this.request("tools.list");
  }

  public async setTurns(turns: number): Promise<any> {
    return this.request("config.set_turns", { turns });
  }

  public stop(): void {
    if (this.child && !this.child.killed) {
      try {
        this.child.kill("SIGTERM");
      } catch {}
    }
  }
}
