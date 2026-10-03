# Mini-Agent 架构设计与开发路线图

本文档记录 Mini-Agent 的整体架构设计、模块职责以及渐进式开发路线。

---

## 一、系统架构图

```text
+---------------------------------------------------------------+
|                      CLI Layer (终端交互层)                   |
|       - repl.py (命令输入循环 / 快捷命令)                      |
|       - display.py (Rich 终端流式渲染 / Diff 语法高亮)         |
+-------------------------------+-------------------------------+
                                | (消费事件 Event)
                                v
+---------------------------------------------------------------+
|                     Agent Facade (门面层)                     |
|       - agent.py (组装 LLMClient、Context、ToolRegistry)      |
+-------------------------------+-------------------------------+
                                |
                                v
+---------------------------------------------------------------+
|                     Core Engine (运行内核)                   |
|       - loop.py (核心 ReAct 调度状态机)                       |
|       - context.py (会话历史、Token 预算、滑动窗口)            |
|       - events.py (7 大核心生命周期事件)                      |
+--------------------+---------------------+--------------------+
                     |                     |
                     v                     v
+-----------------------------+   +-----------------------------+
|    AI Layer (模型抽象层)    |   |   Tools Layer (工具系统)    |
| - client.py (统一 LLM 调用) |   | - base.py (BaseTool / @tool)|
| - types.py (消息协议定义)   |   | - registry.py (注册与调度)  |
| - schema.py (函数转 Schema) |   | - file.py / edit.py / bash  |
+-----------------------------+   +-----------------------------+
```

---

## 二、核心事件流设计

Agent 采用单向事件流（Event-driven）设计，保证运行内核与展示层彻底解耦：

1. **`AgentStart`**：任务接收，会话启动。
2. **`AssistantDelta`**：大模型流式输出片段（文本增量 / 思考增量）。
3. **`AssistantMessage`**：本轮模型完整回复（含文本及发起的 Tool Calls）。
4. **`ToolCallStart`**：解析到工具调用指令，开始调度执行。
5. **`ToolResult`**：工具执行完成，携带输出结果及 `is_error` 标志。
6. **`AgentEnd`**：任务达成或达到最大轮次退出。
7. **`Error`**：系统未捕获异常。

---

## 三、渐进式开发路线图

### 第一阶段：打通底层数据流 (MVP 闭环)
- [ ] **1.1 工具注册中心与基类 (`tools/base.py`, `tools/registry.py`)**
  - 实现 Python 函数/类自动生成 OpenAI Function Calling JSON Schema。
  - 实现工具的安全执行派发与异常捕获。
- [ ] **1.2 统一模型客户端 (`ai/client.py`)**
  - 基于 `AsyncOpenAI` 封装，支持 BaseURL（兼容 Qwen、DeepSeek、本地模型）。
  - 支持流式输出（Streaming）与 Tool Calls 增量拼接。
- [ ] **1.3 ReAct 调度循环 (`core/loop.py`)**
  - 实现 `Model -> Tool Call -> Tool Result -> Model` 的多轮自动循环。
  - 产出标准的 7 种事件。

### 第二阶段：终端交互与体验 (Rich CLI)
- [ ] **2.1 终端流式渲染 (`cli/display.py`)**
  - 打字机流式输出、Spinner 工具调用加载动画。
- [ ] **2.2 REPL 循环 (`cli/repl.py`)**
  - 支持多轮连续对话、输入历史。

### 第三阶段：Coding 核心能力与自愈机制
- [ ] **3.1 编码工具集 (`tools/file.py`, `tools/edit.py`, `tools/bash.py`)**
  - 精准 Diff 替换算法（支持代码唯一块替换）。
  - Bash 命令安全执行与防死循环/输出截断。
- [ ] **3.2 自我修复与错误重试 (Self-Correction)**
  - 工具报错时自动将 stderr 反馈给模型引导修正。

### 第四阶段：知识增强 (Agentic RAG)
- [ ] 接入文档与代码库检索工具，形成完整的 RAG 问答与代码补全能力。
