# Pi vs Mini-Agent 会话存储架构对比与树状分支演进规范

本文档基于对 **Pi（@earendil-works/pi-coding-agent）** 生产级源码及其真实会话测试集（`fixtures/before-compaction.jsonl`、`fixtures/large-session.jsonl`）的实地调研，系统梳理 Pi 的会话持久化设计哲学，并为 Mini-Agent 未来的存储重构与树状分支（Tree & Branching）系统提供演进标准。

---

## 一、Pi 会话存储核心架构解析

### 1.1 存储位置与命名空间隔离
Pi 将会话集中存储在用户主目录下的隐藏文件夹中，并通过对工作区物理路径的编码实现工作区级别的隔离：
```text
~/.pi/agent/sessions/--<encoded-cwd-path>--/<timestamp>_<session-uuid>.jsonl
```
- **路径编码**：将绝对路径中的 `/`、`\\`、`:` 替换为破折号 `--`（例如 `/home/shuaige/code/fork项目专用/pi/workspace` 编码为 `--home-shuaige-code-fork项目专用-pi-workspace--`）。
- **文件命名**：`<ISO启动时间戳>_<UUID>.jsonl`，严格保证单机全局唯一性，避免并发冲突。

---

### 1.2 核心外壳：统一信封结构（SessionEntryBase）
在 Pi 中，除第 1 行是独立的 `session` 根元数据外，后续所有事件行（消息、模型切换、用量记录、上下文压缩等）均严格继承统一信封结构：

```typescript
interface SessionEntryBase {
  type: string;             // 条目类型: message, model_change, thinking_level_change, compaction, usage, custom...
  id: string;               // 本条目唯一标识 (8位 Hex 或 UUID)
  parentId: string | null;  // 父节点 ID (指向前序依赖节点，根节点为 null)
  timestamp: string;        // ISO 8601 标准时间戳 (UTC)
}
```

#### 典型条目示例：
1. **用户输入**：
   ```json
   {"type":"message","id":"e8a96b2a","parentId":"aeedc7f0","timestamp":"2026-10-04T11:50:23.947Z","message":{"role":"user","content":[{"type":"text","text":"你好"}]}}
   ```
2. **模型回复（含思维链与工具调用）**：
   ```json
   {
     "type":"message",
     "id":"9bf9f13f",
     "parentId":"e8a96b2a",
     "timestamp":"2026-10-04T11:50:25.557Z",
     "message":{
       "role":"assistant",
       "content":[
         {"type":"thinking","thinking":"用户问你好，我应简要礼貌回答。","thinkingSignature":"reasoning_content"},
         {"type":"text","text":"你好！有什么可以帮你的吗？"}
       ],
       "usage":{"input":3590,"output":28,"cacheRead":128,"totalTokens":3746},
       "stopReason":"stop"
     }
   }
   ```
3. **工具执行结果**：
   ```json
   {
     "type":"message",
     "id":"c3d4e5f6",
     "parentId":"9bf9f13f",
     "timestamp":"2026-10-04T11:50:28.000Z",
     "message":{
       "role":"toolResult",
       "toolCallId":"toolu_017q",
       "toolName":"read",
       "content":[{"type":"text","text":"文件内容..."}],
       "isError":false
     }
   }
   ```
4. **模型或思考强度热切换事件**：
   ```json
   {"type":"model_change","id":"db80e075","parentId":"04508dc2","timestamp":"2026-10-04T11:50:16.073Z","provider":"deepseek","modelId":"deepseek-flash"}
   {"type":"thinking_level_change","id":"04508dc2","parentId":"0f77f4bd","timestamp":"2026-10-04T11:49:57.591Z","thinkingLevel":"high"}
   ```

---

## 二、为什么需要 `id` 与 `parentId`？（Git Commit 树状拓扑原理）

### 2.1 扁平线性存储的局限性
在传统/早期的线性 `.jsonl` 存储中，所有事件按物理行严格顺序追加。如果用户在多轮交互后发现方案不理想、希望“撤销/回退”到第 3 步重新探索新分支时，线性存储面临两难：
1. **物理删除后面行**：导致前序尝试的所有过程、Token 消耗与错误教训彻底丢失，无法做审计与成本核算；
2. **不删直接加新提问**：上下文混合错乱，大模型无法区分哪个才是当前活跃的主线。

### 2.2 Pi 的树状分支架构（DAG Tree）
通过引入 `id` 与 `parentId`，Pi 把会话变成了一个标准的有向无环图（DAG），完美复刻了 Git 的 Commit Graph 原理：

```text
A (系统初始化) 
      │
      ▼
B (用户: "写一个网页游戏")
      │
      ▼
C (Agent 方案 1: 使用 Canvas 实现) ──► D (方案 1 遇到碰撞 Bug，调试中...)
      │
      └──► E (用户撤退回 B，切分支: parentId 指向 B，改用 SVG 实现)
                 │
                 ▼
           F (方案 2 运行良好，成为当前活跃的 Leaf 叶子节点)
```

#### 核心优势：
- **纯追加不可变性 (Append-Only Immutability)**：
  分支切换与撤销**永远不需要修改或截断文件**，只需往末尾写入指向历史父节点（如 `B`）的新记录。在异常断电或进程中断时零文件损坏风险。
- **活跃分支溯源 (Leaf-to-Root Tracing)**：
  加载会话时，只需指定当前的活动叶子节点 ID，沿着 `parentId` 递归向上回溯（`F -> E -> B -> A`），即可瞬时过滤掉被遗弃的死分支 `C` 和 `D`，精确组装干净的上下文。
- **支持多方案对比 (`/tree` & `/fork`)**：
  用户可以使用 `/tree` 命令随时在方案 1（`D`）和方案 2（`F`）之间无损穿梭。

---

## 三、Pi 与 Mini-Agent 当前存储对比矩阵 (已完成全面对齐 ✅)

| 对比维度 | Pi 的工业级设计 | Mini-Agent (升级前) | Mini-Agent (当前现状 ✅) |
| :--- | :--- | :--- | :--- |
| **存储组织** | 集中在 `~/.pi/agent/sessions/--cwd--/` | 项目根目录下 `.sessions/*.jsonl` | 项目根目录 `.sessions/*.jsonl`，结构清晰独立 |
| **拓扑数据结构** | **树状图 (Tree/DAG)**：`id` + `parentId` | 单向扁平列表 (Flat List) | **树状图 (DAG)**：8位短 Hex `id` + `parentId`，支持 `/tree`、`/undo`、`/checkout` |
| **信封规范 (Envelope)** | 严格统一：外层包含 `type/id/parentId/timestamp` 前置固定键序 | 字段未排序，`id/parent_id` 位于末尾 | **严格对齐**：每行前置键名与宽度完全对齐，`message` 独立嵌套 |
| **多模态与内容形态** | 强类型 Block 数组：`[{"type": "text"}, {"type": "thinking"}, {"type": "toolCall"}]` | 纯文本与多模态混杂 | **标准 Content Block 数组**：思考、文本、工具调用独立分块 |
| **思考链持久化** | 独立记录 `{"type": "thinking", "thinking": "..."}` | 仅流式输出，持久化时位于末尾不易查看 | **独立思考块**：置于 `content[0]`，思维链与文本输出彻底解耦 |
| **用量统计归属** | 内嵌在 `message.usage`，不生成冗余行 | 单独追加写 `type: "usage"`，污染会话树 | **内嵌归属**：嵌入 `assistant` 消息的 `usage`，树链条干净清晰 |

---

## 四、Mini-Agent 树状分支系统（阶段十）演进技术方案

### 4.1 数据模型重构（Schema 升级）
为保证向后兼容与升级平滑，Mini-Agent 的 `SessionManager`（`core/session.py`）将支持树状信封：

```python
class SessionEntry:
    type: str                  # "session", "message", "model_change", "compaction", "usage"
    id: str                    # 8 位短 hex 随机 ID (如 secrets.token_hex(4))
    parent_id: Optional[str]   # 父节点 ID
    timestamp: str             # ISO 格式字符串
    # 消息体或附加字段
    message: Optional[dict] = None
    data: Optional[dict] = None
```

### 4.2 活跃分支导航算法
```python
def get_active_branch_messages(entries: list[dict], leaf_id: Optional[str] = None) -> list[dict]:
    """从指定的叶子节点沿 parent_id 回溯至根节点，还原当前分支上下文"""
    id_map = {e["id"]: e for e in entries if "id" in e}
    if not leaf_id:
        leaf_id = entries[-1]["id"]
    
    branch = []
    curr_id = leaf_id
    while curr_id and curr_id in id_map:
        entry = id_map[curr_id]
        if entry["type"] == "message" and "message" in entry:
            branch.append(entry["message"])
        elif entry["type"] == "compaction":
            # 如果回溯到压缩节点，则注入压缩摘要并终止向前回溯
            branch.append(entry)
            break
        curr_id = entry.get("parent_id")
        
    return list(reversed(branch))
```

### 4.3 终端交互命令扩展
1. `/tree`：以 ASCII 字符树（类似 `git log --graph --oneline`）直观呈现当前会话的分支与分叉节点，支持光标上下移动自由切换活动分支。
2. `/undo`：时光倒流，将当前指针（Leaf）回退到上一轮用户提问节点，再次输入指令时自动从该节点生长出新分支，绝不破坏历史数据。
3. `/fork`：以当前节点为基础分叉生成新的独立 `.jsonl` 会话文件。
