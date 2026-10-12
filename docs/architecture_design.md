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

### 第一阶段：打通底层数据流 (MVP 闭环) - [已完成 ✅]
- [x] **1.1 工具注册中心与基类 (`tools/base.py`, `tools/registry.py`)**
  - 实现 Python 函数/类自动生成 OpenAI Function Calling JSON Schema。
  - 实现工具的安全执行派发与异常捕获。
- [x] **1.2 统一模型客户端 (`ai/client.py`)**
  - 基于 `AsyncOpenAI` 封装，支持 BaseURL（兼容 Qwen、DeepSeek、本地模型）。
  - 支持流式输出（Streaming）与 Tool Calls 增量拼接、思考链 (Reasoning Effort) 强度调节。
- [x] **1.3 ReAct 调度循环 (`core/loop.py`)**
  - 实现 `Model -> Tool Call -> Tool Result -> Model` 的多轮自动循环。
  - 产出标准的 7 种生命周期事件。

### 第二阶段：终端交互与体验 (Rich CLI) - [已完成 ✅]
- [x] **2.1 终端流式渲染 (`cli/display.py`)**
  - 打字机流式输出、Reasoning 思维链高亮、工具执行双通道渲染、ANSI 零依赖优雅降级。
- [x] **2.2 REPL 循环 (`cli/repl.py`)**
  - 支持多轮连续对话、输入历史。
  - 常用斜杠命令：`/help`, `/clear`, `/tools`, `/models`, `/model <name>`, `/effort <level>`, `/exit`。

### 第三阶段：Coding 核心能力与自愈机制 - [已完成 ✅]
- [x] **3.1 编码工具集 (`tools/file.py`, `tools/edit.py`, `tools/bash.py`)**
  - `read_file`: 行号索引、范围切片、长文本截断防御。
  - `write_file`: 自动递归建目录。
  - `edit_file`: 唯一块 Diff 精准替换、CRLF/LF 归一化。
  - `bash`: 异步子进程、进程组隔离强杀、非零退出码报告、危险指令前置拦截。
- [x] **3.2 自我修复与错误重试 (Self-Correction)**
  - 工具报错时自动将 stderr 反馈给模型引导修正。

### 第四阶段：会话持久化与上下文工程 (Session & Context) - [已完成 ✅]
- [x] **4.1 追加写日志持久化 (`core/session.py`)**
  - 参考 Pi 架构，采用单行追加写 (Append-Only `.jsonl`) 机制，抗断电/崩溃零损坏。
  - 惰性建档避免生成空垃圾文件。
  - 支持会话列表扫描、按时间倒序排列、首句提示词自动提取。
- [x] **4.2 会话恢复与生命周期管理**
  - 命令行参数：`-s/--session <id>` 直接断点续传恢复，`--list-sessions` 快速查看。
  - REPL 斜杠指令：`/sessions` (历史清单)、`/resume <id|序号>` (热恢复)、`/new` (开启新会话)。

### 第五阶段：多模态视觉工程 (Multimodal Vision) - [已完成 ✅]
- [x] **5.1 图像读取与自动 Base64 编码 (`tools/file.py`)**
  - `read_file` 智能识别常见图像后缀 (`.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`, `.bmp`)。
  - 读取二进制字节流并转换为 Base64 编码，打包进 `ToolResult.images`。
- [x] **5.2 对齐 Pi 的 OpenAI Vision 协议桥接 (`core/context.py`, `core/loop.py`)**
  - 工具返回 `role: "tool"` 文本告知读取成功。
  - 协议层紧随其后追加 `role: "user"` 附带标准 `image_url` block，绕过各服务商对 tool 结果不能为图片数组的限制。
  - 会话持久化自动兼容存储与回放图文混合列表。
- [x] **5.3 终端交互式看图指令 (`cli/repl.py`)**
  - 增加 `/image <path> [prompt]` 指令，支持用户直接向 Agent 投喂本地图片提问。

### 第六阶段：执行流控制与长任务治理 (Turn Control & Long Tasks) - [已完成 ✅]
- [x] **6.1 最大轮数解耦与动态调控 (`core/loop.py`, `core/context.py`)**
  - 破除原本硬编码 15 轮的紧箍咒，将默认上限提升至 **50 轮**（对齐现代编码任务标准）。
  - 支持 `max_turns <= 0` 开启**无上限自然退出模式**（对齐 Pi 交互式循环哲学）。
  - 支持环境变量 `MAX_TURNS`、启动参数 `--max-turns`。
- [x] **6.2 运行时交互控制 (`cli/repl.py`)**
  - 提供 `/turns` 查看当前轮数限制。
  - 支持 `/turns <num>` 或 `/turns 0` 随时在终端动态升降上限。
  - 达到上限时给出友好提示并允许用户直接输入指令继续执行，拒绝一刀切崩溃。

### 第七阶段：用量感知与缓存命中遥测 (Token & Cache Telemetry) - [已完成 ✅]
- [x] **7.1 流式用量捕获 (`ai/client.py`, `ai/types.py`)**
  - 在流式请求中注入 `stream_options: {"include_usage": True}`。
  - 提取末尾 chunk 的 `prompt_tokens`、`completion_tokens`、`total_tokens`。
  - 多厂商兼容 Prompt Cache 字段 (`prompt_tokens_details.cached_tokens` / `prompt_cache_hit_tokens` / `cache_read_input_tokens`)。
  - 封装为标准 `TokenUsage` 数据结构，自动计算命中率 `cache_hit_rate`。
- [x] **7.2 上下文与持久化统计 (`core/context.py`, `core/session.py`)**
  - `AgentContext` 实时跟踪单次上下文真实占用（`current_tokens`）、模型窗口大小（默认 128k）与百分比占用。
  - 会话日志单行追加写 `type: "usage"`（对齐 Pi 设计）。
- [x] **7.3 终端渲染与交互查询 (`cli/display.py`, `cli/repl.py`)**
  - 任务结束时自动打印精炼统计行：`📊 用量统计: ↑cum_in ↓cum_out | 缓存命中: R... (CH ...%) | 上下文: cur/win (pct%)`。
  - 提供 `/usage` 或 `/stats` 斜杠指令，支持在终端随时查看累计与即时用量。
- [x] **7.4 模型规格库与自适应上下文窗口解析 (`ai/catalog.py`)**
  - 三层分级裁决机制：用户环境变量覆盖 (`CONTEXT_WINDOW`) > 服务端动态规格缓存 (`context_length`) > 内置主流模型基准库 (`DEFAULT_MODEL_SPECS`) > 启发式命名规则推断 (`infer_context_window`)。
  - 实测适配并精准识别提供商（CommandCode 等）85 个模型的实际规格（如 `deepseek-v4.1-flash` 自动映射为 1,000,000 1M 窗口）。
  - `/models` 列表交互升级：输出模型名称的同时清晰附带上下文上限规格；切换模型自动联动更新 Agent 窗口基准。

### 第八阶段：智能上下文压缩 (Intelligent Context Compaction) - [已完成 ✅]
- [x] **8.1 文件操作状态追踪 (`core/compaction.py`)**
  - 深度扫描历史工具调用，精准提取 `read_file`、`write_file`、`edit_file` / `replace_file_content` 中的目标路径。
  - 自动解构为只读文件列表 (`<read-files>`) 与已写入/修改文件列表 (`<modified-files>`)。
- [x] **8.2 历史序列化与防爆截断 (`core/compaction.py`)**
  - 将多轮交互序列化为纯文本，对巨型工具输出（如超长终端执行日志或大文件读取）进行语义化智能截断（默认 1500 字符），防止摘要请求自身 Token 爆炸。
- [x] **8.3 工业级六段式检查点摘要生成 (`core/compaction.py`)**
  - 调用模型生成严格的上下文检查点摘要：包含 Goal, Constraints & Preferences, Progress (Done / In Progress / Blocked), Key Decisions, Next Steps 及文件追踪标签。
- [x] **8.4 保留保护区与原子上下文重构 (`core/compaction.py`, `core/context.py`)**
  - 保护区机制：默认保留最近 `keep_recent_turns=2` 轮活跃交互，仅将更早的历史送入摘要。
  - 原子重构：将消息列表置换为 `[检查点摘要, 确认消息, 保留的最近交互]`，即时释放 80%~95% Token 空间。
- [x] **8.5 会话持久化与断点无损恢复 (`core/session.py`)**
  - 追加写入 `type: "compaction"` 记录，包含完整摘要、压缩前后 Token 统计与文件状态。
  - `load_session` 遇到 compaction 检查点时，自动从最新检查点开始重构上下文，彻底消除旧历史冗余。
- [x] **8.6 自动阈值触发与终端交互 (`core/loop.py`, `core/events.py`, `cli/repl.py`)**
  - 在 ReAct 循环前置自动检测 `context.should_auto_compact()`（默认 80% 窗口阈值且具备足够轮次），触发时流式发射 `CompactionStart` 与 `CompactionEnd` 事件。
  - REPL 提供快捷指令 `/compact`，支持用户随时手动触发压缩，打印详细节省统计。

### 第九阶段：现代终端交互与全屏 TUI (Modern CLI & Interactive TUI) - [核心完成 🚀]
- [x] **9.1 交互式终端下拉选择器组件 (`cli/menu.py`)**
  - 零外部依赖，使用标准库 termios / tty 捕获底层未缓冲文件描述符，支持方向键 `↑` / `↓` / `k` / `j` 与 `Enter` / `Esc`。
  - 支持多页展示大量选项（针对 CommandCode 85 个模型自动分页 `[第 1/9 页]`），支持数字快捷键与非 TTY 优雅降级。
- [x] **9.2 终端视觉与动效升级 (`cli/display.py`)**
  - **实时状态条 (Status Bar & Context Gauge)**：常驻显示 `[🧠 模型]`、`[📊 槽位进度条 4k/1M]`、`[⚡ 缓存率]`、`[🌿 Git 分支]`。
  - **动态思考与执行 Spinner**：思维规划时展示 `⠋ 正在分析任务...`，执行命令时展示 `⠙ 正在执行工具...`，首字到达时无缝平滑收起。
  - **结构化工具面板**：为 `bash`、`read_file`、`edit_file` 定制专属图标与双层折叠面板，清晰高亮参数与结果。
- [x] **9.3 增强型 REPL 交互与下拉联动 (`cli/repl.py`)**
  - **Tab 自动补全与历史记录**：集成 `readline` 补全所有斜杠命令，持久化历史命令至 `~/.mini_agent_history`。
  - **菜单联动**：输入无参数 `/model` 或 `/resume` 时，直接唤起交互式下拉菜单，按方向键回车即可一键切换或恢复。
  - **转义清洗**：防御性过滤行首意外残留的方向键转义前缀（如 `[B/`）。
- [x] **9.4 Live Markdown 富文本排版与代码语法高亮 (`cli/display.py`)**
  - **实时消灭裸星号**：基于 `rich.live.Live` + `rich.markdown.Markdown`，将大模型输出实时转化为终端加粗、斜体、标题与表格，彻底消除 `**` 裸露字符。
  - **代码与 Diff 语法高亮**：对回答中的代码块（`python`, `bash`, `json`, `html` 等）及工具执行结果（`read_file`, `edit_file`）自动调用 Monokai 主题语法着色，代码变更以绿色 `+` / 红色 `-` 呈现 Diff 质感。
- [x] **9.5 现代沉浸式 TUI 与 Alt-Screen 全屏锁屏模式 (`cli/theme.py`, `cli/footer.py`, `cli/screen.py`, `cli/display.py`, `cli/repl.py`) - [已完成 ✅]**
  - **用户消息满宽深蓝卡片**：对齐 Pi 的 `userMessageBg` (`#213b49`) 与中文字符宽度精确对齐，告别生硬的 `▶ 接收任务:`。
  - **纯净流式思维链**：彻底移除 `[思考过程]` 与 `[回答]` 伪标签，采用柔和深灰斜体字符 (`#7b8891`) 流式展开，无感过渡。
  - **工具执行满宽墨绿面板**：采用 `toolSuccessBg` (`#254131`)，支持行号、Diff `+44` 绿色高亮与超长安全折叠。
  - **双行高密度常驻 Footer**：以紫色分割线 (`#5a5271`) 为界，展示 CWD/Git + Token 进出/缓存命中/费用 + 模型角标。
  - **Alt-Screen 全屏锁屏支持**：利用 ANSI `\033[?1049h` 激活备用屏幕，支持 `/alt` 自由切换，退出时干净复位。

### 第十阶段：工业级树状会话引擎与时光倒流 (Session Tree & Branching) - [已完成 ✅]
详细技术对比与设计规范请参阅：[`docs/session_architecture_pi_comparison.md`](session_architecture_pi_comparison.md)
- [x] **10.1 顶层强有序 Envelope 信封与固定键序 (`core/session.py`)**
  - 为所有持久化条目严格对齐 Pi 顶层规范：`type`, `id` (8位短 hex), `parentId`, `timestamp` 稳居每行最前，前置字符完全垂直对齐。
  - 双向兼容历史线性会话与扁平结构文件（兼容 `parent_id` / `session_header`）。
- [x] **10.2 深度思维链分块与 Content Block 体系 (`core/session.py`, `core/context.py`, `core/loop.py`)**
  - 对齐 Pi 标准 Content Block：思考链 (`type: "thinking"`) 与回答文本 (`type: "text"`)、工具调用 (`type: "toolCall"`) 严格独立分块存储，思考内容居于首块，清晰可查。
  - 将 Token 用量嵌入 `message.usage`，消除原本造成会话树割裂的独立 usage 冗余行。
- [x] **10.3 无损撤销与多分支时光穿梭 (`cli/repl.py`, `core/session.py`)**
  - `/undo`：时光倒流，将当前分支指针回退到上一轮提问节点，新提问自动生长出新分支，历史数据零丢失。
  - `/tree`：终端 ASCII 打印分支版本拓扑树（类似 `git log --graph`），标注活跃主线与当前叶子。
  - `/checkout <node_id>`：分支自由穿梭，秒级重构任意历史节点的消息上下文。

### 第十一阶段：项目级规范探测与 Prompt Cache 强化 (Project Instructions & AGENTS.md) - [已完成 ✅]
- [x] **11.1 多级向上递归探测引擎 (`core/instructions.py`)**
  - 多候选格式优先支持：`AGENTS.override.md` > `AGENTS.md` > `AGENTS.MD` > `CLAUDE.md` > `CLAUDE.MD`。
  - 自动向上溯源至当前 Git 仓库根目录（解决在深层子目录执行 Agent 的痛点），并支持 `~/.mini-agent/` 全局兜底。
- [x] **11.2 缓存亲和的 System Prompt 注入与结构化 XML 封装 (`core/instructions.py`, `agent.py`)**
  - 将规范内容包装为标准 XML 块 `<project_context><project_instructions path="...">...</project_instructions></project_context>`。
  - 静态拼接于 System Prompt 头部，为大模型建立 3000+ 字符的稳定前缀，大幅度提升后续轮次的 Prompt Cache 命中率。
- [x] **11.3 根目录标准化规范文件 (`AGENTS.md`)**
  - 为 Mini-Agent 仓库本身编写了首份工业级 `AGENTS.md`，涵盖交互风格、常用测试指令、编码纪律与 Git 安全防线。


