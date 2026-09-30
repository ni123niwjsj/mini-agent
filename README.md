# Mini-Agent

Mini-Agent 是一个参考现代 Agent 架构（如 Pi）设计、基于 Python 实现的轻量级自主编程与任务执行 Agent 框架。

旨在通过清晰解耦的分层设计，深入探索 ReAct 循环、Function Calling、长上下文管理以及自动纠错等核心工程机制。

---

## 核心特性规划

- **模块化解耦架构**：
  - **LLM Adapter**：统一的多模型客户端抽象（支持流式响应与 Token 统计）。
  - **Agent Core**：轻量 ReAct 循环、事件分发与状态管理。
  - **Tool System**：结构化工具注册、基于 Type Hint / JSON Schema 的入参校验。
- **Coding 场景落地工具集**：
  - 文件系统操作（读取、写入、精准 Diff 替换）。
  - 安全沙箱与命令行执行（Command Runner）。
- **工程级优化**：
  - **上下文与记忆管理**：Token Budget 控制与长会话滑动窗口压缩。
  - **自愈纠错机制（Self-Correction）**：工具执行报错与格式异常的多轮重试修复。
- **扩展性（Future）**：
  - 融合 RAG 检索能力（Agentic RAG），支持外部知识库/项目文档增强。

---

## 项目结构规划

```text
mini-agent/
├── README.md               # 项目介绍与架构说明
├── requirements.txt        # 依赖列表
├── mini_agent/             # 核心源码包
│   ├── core/               # Agent 核心运行时与循环
│   ├── llm/                # LLM 抽象与适配器
│   ├── tools/              # 工具系统与内置工具
│   └── utils/              # 上下文、Token 统计与辅助工具
└── main.py                 # CLI 入口与调试
```
