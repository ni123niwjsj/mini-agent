/**
 * Stdio JSON-RPC 桥接协议类型定义
 */

export interface ContextStats {
  current_tokens: number;
  max_tokens: number;
  percent: number;
  cumulative_prompt_tokens?: number;
  cumulative_completion_tokens?: number;
  cumulative_total_tokens?: number;
  cumulative_cached_tokens?: number;
  cumulative_cache_hit_rate?: number;
  latest_cached_tokens?: number;
  latest_cache_hit_rate?: number;
}

export interface SessionInfo {
  cwd: string;
  branch: string;
  model: string;
  context_window: number;
  stats: ContextStats;
  reasoning_effort: string;
  session_id: string;
  messages?: ChatMessage[];
}

export interface SessionSummary {
  session_id: string;
  created_at: string;
  last_timestamp?: string;
  cwd?: string;
  model?: string;
  first_prompt?: string;
  message_count: number;
}

export interface ModelSpec {
  id: string;
  context_length: number;
  description?: string;
}

export interface ToolCallItem {
  tool_name: string;
  tool_call_id: string;
  arguments: Record<string, any>;
  output?: string;
  is_error?: boolean;
}

export type MessageRole = "user" | "assistant" | "system" | "tool";

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  reasoning?: string;
  toolCalls?: ToolCallItem[];
  isStreaming?: boolean;
}

export interface JsonRpcRequest {
  jsonrpc: "2.0";
  id: number | string;
  method: string;
  params?: Record<string, any>;
}

export interface JsonRpcResponse {
  jsonrpc: "2.0";
  id: number | string;
  result?: any;
  error?: {
    code: number;
    message: string;
    data?: any;
  };
}

export interface JsonRpcNotification {
  jsonrpc: "2.0";
  method: string;
  params: Record<string, any>;
}
