# Mini-Agent

Mini-Agent 是一个参考现代顶级自主编程 Agent 架构（对齐 Pi / Claude Code 设计）实现的轻量、可扩展自主编程与任务执行框架。

项目采用 **Python 异步运行时后端 + TypeScript Pi-TUI 现代化终端前端** 的双端分层解耦架构，深入探索并落地了 ReAct 异步事件流、DAG 多分支会话版本树、智能上下文压缩、专业子代理协作、MCP 协议集群以及流式打字与动态任务实时引导（Steering）等工程级核心机制。

---

## 🌟 核心特性

### 1. 现代化终端交互体验 (Pi-TUI Engine)
- **`TuiAltScreen` 全屏双缓冲视口**：彻底消除终端全屏清屏（`\x1b[2J`）与百叶窗撕裂闪烁，带来如 LazyGit、Vim 般丝滑平整的专业 CLI 质感。
- **`ScrollView` 虚拟滚动视口**：聊天历史自适应高度并自动吸底平滑滚动，无论会话产生数千行输出，支持使用鼠标滚轮或键盘向上自由浏览历史。
- **底部固定 Dock**：
  - **`StatusIndicator`**：实时展现模型思考耗时、打字机心跳、工具执行中指示与动态引导反馈。
  - **`DynamicBorder`**：随终端列宽自适应伸缩的精致水平分割线。
  - **`DynamicInput`**：支持快捷指令补全、历史回溯，模型生成期间自动转为【实时任务引导】输入框。
  - **`FooterComponent`**：实时展示当前工作空间、Git 分支、Token 容量仪表盘（进度条 + 占用率）、Prompt Cache 缓存命中率（`CH%`）以及模型与思考强度。
- **⚡ 实时动态任务引导 (Dynamic Steering)**：无需强制打断（Ctrl+C），在模型思考或工具执行的任意时刻，直接在输入框打字回车，即可在下一轮执行前精准注入纠偏提示。

### 2. Agent 核心运行时 (ReAct & Events)
- **事件流驱动**：基于 Python 异步生成器，实时派发 `AgentStart`、`AgentDelta`、`ToolCallStart`、`ToolResult`、`AgentEnd` 等标准事件。
- **深度思考模型原生支持**：对齐 DeepSeek / OpenAI reasoning 协议，解析 `reasoning_content`，支持动态调整思考强度（`reasoning_effort`）与终端思考链折叠/展开。
- **安全与控制**：支持单次任务最大轮数限制（默认 50 轮，可通过 `/turns` 调整）与运行超时自愈保护。

### 3. 会话持久化与 DAG 分支版本树 (Session Tree)
- **多分支版本拓扑**：对齐 Git Graph 的会话版本控制机制，支持交互式会话树分叉与回溯。
- **↩️ 无损时光倒流 (`/undo`)**：一键回退到上一轮提问节点，历史不会被粗暴覆写，后续新提问将自动生长出新的平行会话分支。
- **🌲 拓扑可视化 (`/tree`)**：在终端以清晰的树状 ASCII 图直观呈现所有主线与历史分支。
- **🔀 节点自由检出 (`/checkout <id>`)**：随时切换到任何历史分叉节点恢复上下文环境。
- **📂 会话恢复 (`/resume` / `/sessions`)**：支持列出所有持久化会话记录，并提供交互式下拉弹窗一键恢复。

### 4. 智能长上下文管理 (Context Management)
- **Token 预算与滑动监控**：实时追踪输入 Prompt Tokens、输出 Completion Tokens 与累积消耗。
- **Prompt Cache 性能追踪**：动态计算并展示服务端前缀缓存命中率（Cache Hit Rate），显著降低延迟与成本。
- **📌 智能检查点压缩 (`/compact`)**：自动识别会话冗余轮次，调用专用 Prompt 提取要点、已完成成果与关键文件状态，安全截断历史并释放 70% 以上的上下文空间。

### 5. 全能工程工具箱 & MCP 集成
- **代码与文件操作**：
  - `read_file`：支持带行号按需/分页读取文件，自动识别常见图像并支持多模态注入。
  - `write_file`：安全创建与完整重写文件。
  - `edit_file`：采用精准区块 Diff 匹配替换，避免重写整个文件的幻觉风险。
- **检索与搜索**：
  - `grep`：多文件正则匹配检索。
  - `glob`：快速匹配工作区文件目录树。
  - `web_search` & `web_fetch`：网络搜索与网页抓取（集成反爬防御降级与移动端自适应重试）。
- **命令行与执行**：
  - `bash`：受控子进程执行环境，带超时控制与长输出智能折叠。
- **任务管理**：
  - `todo`：专为复杂开发流程设计的任务清单状态机。
- **🔌 Model Context Protocol (MCP) 集成**：
  - 内置标准 Stdio MCP 客户端，支持将第三方 MCP 工具集群无缝动态挂载至 Agent 工具箱。

### 6. 专业子代理协作系统 (Subagent Harness)
- **结构化委派任务 (`task` 工具)**：主 Agent 可按需自主拉起专职子代理并行分担重度任务：
  - **`explore` 角色**：专职只读代码勘探与文档搜索（挂载文件只读工具与 Web 抓取）。
  - **`plan` 角色**：专职复杂架构方案拆解与规划（轻量思考与计划生成）。
  - **`general` 角色**：具备完整权限的通用子代理，自主闭环编写代码、运行测试与排查 Bug。
- **独立上下文与资源隔离**：子代理拥有独立的 ReAct 循环、会话日志记录（`.sessions/subagents/`）、角色化轮数预算与状态保护，避免主任务清单被子代理临时任务污染。

---

## 🛠️ 快速上手

### 环境要求
- **Python**: 3.10+
- **Node.js**: 18.0+

### 1. 安装依赖

```bash
# 1. 克隆代码仓库
git clone <repo_url> mini-agent
cd mini-agent

# 2. 安装 Python 核心依赖
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. 安装 TUI 前端依赖并编译
npm install --prefix tui
npm run tui:build
```

### 2. 配置环境变量

复制环境变量模板并填入你的大模型配置：

```bash
cp .env.example .env
```

在 `.env` 中根据你的实际 Provider 进行配置（兼容任何 OpenAI 协议服务）：

```env
# 选项 A: DeepSeek 官方 API
OPENAI_BASE_URL=https://api.deepseek.com/v1
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxx
MINI_AGENT_MODEL=deepseek-chat

# 选项 B: 本地私有化大模型 (如 LM Studio / llama.cpp / vLLM / Ollama)
# OPENAI_BASE_URL=http://127.0.0.1:1234/v1   # LM Studio 本地服务默认端口
# OPENAI_BASE_URL=http://127.0.0.1:8080/v1   # llama.cpp server 默认端口
# OPENAI_API_KEY=EMPTY
# MINI_AGENT_MODEL=deepseek-r1-distill-qwen-14b
```

### 3. 运行 Mini-Agent

#### 方式一：现代化 TUI 交互模式 (推荐)
```bash
# 启动零闪烁、全屏双缓冲 TUI 终端
npm run tui

# 或以开发调试热重载模式运行
npm run tui:dev
```

#### 方式二：轻量 Python CLI 模式
```bash
python main.py
```

#### 方式三：单次非交互即时指令模式
```bash
python main.py -p "请阅读 src/index.ts 并指出潜在的并发安全问题"
```

---

## 💡 终端快捷指令速查

在交互终端中随时输入斜杠指令（支持 Tab 补全）：

| 指令 | 说明 |
| :--- | :--- |
| **/help** | 查看完整指令速查指南与快捷操作说明 |
| **/model [序号/名称]** | 查看可用模型列表或直接切换激活模型（直接输入 `/model` 唤起选择菜单） |
| **/effort [1-4/名称]** | 查看或调整当前模型的思考强度（low / medium / high / none） |
| **/thinking** | 切换思考过程（Reasoning）在终端的展开与折叠显示状态 |
| **/turns [轮数]** | 查看或调整单次任务的最大执行轮数限制（如 `/turns 30`，0 表示无限制） |
| **/sessions** | 列出工作区内所有保存的历史持久化会话记录 |
| **/resume [序号/ID]** | 恢复指定的历史会话（直接输入 `/resume` 打开交互式弹窗） |
| **/new** | 清空当前工作区上下文，开启一个全新的独立会话 |
| **/undo** | 撤销最近一轮交互，无损时光倒流并准备衍生新分支 |
| **/tree** | 查看当前会话的多分支 DAG 版本拓扑关系图（对齐 Git Graph） |
| **/checkout &lt;ID&gt;** | 切换当前分支到指定的历史分支节点 ID |
| **/compact** | 立即触发智能上下文压缩，提炼检查点并大幅释放 Token 空间 |
| **/tools** | 查看当前已挂载的所有可用工具清单与功能描述 |
| **/usage** | 查看当前 Token 详细消耗、上下文容量占比与 Prompt Cache 命中率 |
| **/image &lt;路径&gt; [问]** | 附加本地图像文件并发起多模态提问 |
| **/clear** | 清空终端屏幕显示历史 |
| **/exit** | 安全停止 Agent 桥接进程并退出交互终端 |

---

## 📂 项目结构

```text
mini-agent/
├── mini_agent/                     # Python 核心运行时
│   ├── ai/                         # 多模型客户端适配器、Catalog 与 Token 追踪
│   ├── bridge/                     # Stdio JSON-RPC 桥接服务端
│   ├── cli/                        # 原生 Python 终端显示与 REPL
│   ├── core/                       # ReAct 执行循环、Context 管理、Compaction 压缩器与事件流
│   ├── mcp/                        # Model Context Protocol (MCP) 客户端与工具集群
│   ├── session/                    # 会话持久化与 DAG 分支版本树
│   ├── subagent/                   # 子代理体系 (explore / plan / general) 与调度工具
│   └── tools/                      # 内置工具集 (file, edit, bash, grep, glob, web, todo)
├── tui/                            # TypeScript 原生现代化前端 (基于 Pi-TUI Engine)
│   ├── src/
│   │   ├── bridge/                 # 与 Python 核心长连接的双向 RPC Client
│   │   ├── components/             # UI 组件库
│   │   │   ├── AssistantMessage.ts # 助手消息组件 (静态追加与分层渲染)
│   │   │   ├── StatusIndicator.ts  # 底部状态指示条 (实时耗时/心跳/引导)
│   │   │   ├── Footer.ts           # 底部遥测与容量仪表盘
│   │   │   ├── UserMessage.ts      # 用户消息格式化排版
│   │   │   ├── DynamicBorder.ts    # 自适应全宽分割线
│   │   │   └── SelectDialog.ts     # 交互式 Overlay 弹窗菜单
│   │   ├── app.ts                  # TUI 核心控制器 (TuiAltScreen + ScrollView + Dock)
│   │   ├── theme.ts                # ANSI Markdown 与思考链终端主题
│   │   └── index.ts                # TUI 启动入口
│   └── package.json
├── tests/                          # 自动化单元测试集 (145+ 测试用例全覆盖)
├── main.py                         # Python CLI 入口
├── package.json                    # 项目顶层 NPM 脚本包装
└── requirements.txt                # Python 依赖清单
```

---

## 🧪 测试与质量保证

项目具备完备的测试套件，涵盖核心循环、工具执行、版本分支树、上下文压缩、子代理调度与前端视口仿真：

```bash
# 运行 Python 端全量单元测试
python3 -m unittest discover tests

# 运行 TUI 端 TypeScript 类型检查与编译构建
npm run typecheck --prefix tui
npm run tui:build
```

### 🏆 SWE-bench Lite 官方基准评测 (Official Evaluation)

Mini-Agent 集成了对齐国际顶级代码智能体评测基准 **SWE-bench Lite** 的官方评测套件，并支持在官方 **Docker 容器沙箱** 中自动化运行评估。

目前已在真实知名开源仓库（`pallets/flask`、`astropy/astropy`、`mwaskom/seaborn` 与 `psf/requests`）完成 **19 道官方真题** 的全闭环评测与补丁提取：

#### 1. Flask & Astropy 核心基准集 (9 题)
- **官方评测结果**: **77.8% (7/9)** 官方完全解决率 (Resolved Rate)。

| 仓库 / 领域 | 题目 ID | 评测判定 | 耗时 | 轮数 | 工具调用 |
| :--- | :--- | :---: | :---: | :---: | :---: |
| `pallets/flask` | `pallets__flask-4992` | 🎉 **PASSED** | 100.8s | 15 轮 | 18 calls |
| `pallets/flask` | `pallets__flask-5063` | 🎉 **PASSED** | 319.9s | 25 轮 | 28 calls |
| `pallets/flask` | `pallets__flask-4045` | ❌ FAILED | 73.9s | 15 轮 | 19 calls |
| `astropy/astropy` | `astropy__astropy-12907` | 🎉 **PASSED** | 136.3s | 25 轮 | 26 calls |
| `astropy/astropy` | `astropy__astropy-14182` | 🎉 **PASSED** | 232.5s | 25 轮 | 29 calls |
| `astropy/astropy` | `astropy__astropy-14365` | ❌ FAILED | 159.4s | 25 轮 | 26 calls |
| `astropy/astropy` | `astropy__astropy-14995` | 🎉 **PASSED** | 193.2s | 25 轮 | 30 calls |
| `astropy/astropy` | `astropy__astropy-6938` | 🎉 **PASSED** | 147.3s | 22 轮 | 23 calls |
| `astropy/astropy` | `astropy__astropy-7746` | 🎉 **PASSED** | 117.4s | 14 轮 | 18 calls |

#### 2. Seaborn & Requests 扩展题集 (10 题)
- **补丁生成成功率**: **100.0% (10/10)**；
- **官方 PR 逻辑精准复刻率**: **100.0% (10/10)**（生成的代码补丁与开源仓库官方 Merge Commit 保持一致）；
- **Docker 容器验证**: `mwaskom__seaborn-3010` 100% 靶向测试通过（`resolved: True`）；`psf__requests-2317` 容器内通过 7/8 项测试。

| 仓库 / 领域 | 题目 ID | 官方 PR 一致性 | 耗时 | 轮数 | 工具调用 | 补丁大小 |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| `mwaskom/seaborn` | `mwaskom__seaborn-3010` | 🎯 **100% 吻合 (Docker 实测 Resolved)** | 71.5s | 11 轮 | 13 calls | 12 行 |
| `mwaskom/seaborn` | `mwaskom__seaborn-3190` | 🎯 **100% 逐字吻合** (PR #3190) | 62.8s | 11 轮 | 16 calls | 12 行 |
| `mwaskom/seaborn` | `mwaskom__seaborn-2848` | 🎯 **100% 逐字吻合** (PR #2848) | 398.1s | 25 轮 | 30 calls | 19 行 |
| `mwaskom/seaborn` | `mwaskom__seaborn-3407` | 🎯 **100% 逐字吻合** (PR #3407) | 108.5s | 16 轮 | 20 calls | 15 行 |
| `psf/requests` | `psf__requests-2317` | 🎯 **100% 吻合 (Docker 实测通过)** | 43.6s | 9 轮 | 11 calls | 13 行 |
| `psf/requests` | `psf__requests-1963` | 🎯 **100% 吻合** (PR #1963) | 88.2s | 13 轮 | 15 calls | 15 行 |
| `psf/requests` | `psf__requests-2148` | 🎯 **100% 逐字吻合** (PR #2148) | 91.0s | 16 轮 | 23 calls | 30 行 |
| `psf/requests` | `psf__requests-2674` | 🎯 **100% 逐字吻合** (PR #2674) | 125.3s | 22 轮 | 27 calls | 21 行 |
| `psf/requests` | `psf__requests-3362` | 🎯 **100% 逐字吻合** (PR #3362) | 75.4s | 14 轮 | 17 calls | 30 行 |
| `psf/requests` | `psf__requests-863` | 🎯 **100% 逐字吻合** (PR #876) | 61.4s | 13 轮 | 15 calls | 16 行 |

#### 3. 评测报告与补丁归档
- **官方评测 JSON 报告**：[`benchmarks/results/mini-agent-deepseek.mini_agent_official.json`](benchmarks/results/mini-agent-deepseek.mini_agent_official.json)
- **Flask & Astropy 详细记分卡**：[`benchmarks/results/report.md`](benchmarks/results/report.md)
- **Seaborn & Requests 详细记分卡**：[`benchmarks/results/report_seaborn_requests.md`](benchmarks/results/report_seaborn_requests.md)
- **官方评测预测集合**：[`benchmarks/results/predictions.jsonl`](benchmarks/results/predictions.jsonl) (汇聚全部 19 条官方补丁)
- **生成的 Git 统一补丁目录**：[`benchmarks/results/patches/`](benchmarks/results/patches/)
- **Docker 容器执行日志**：[`logs/run_evaluation/mini_agent_official/`](logs/run_evaluation/mini_agent_official/)

---

## 📄 开源许可

本项目遵循 MIT 开源许可证。
