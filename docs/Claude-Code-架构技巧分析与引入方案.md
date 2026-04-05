# Claude Code 架构技巧分析与鲜标智投引入方案

> 分析来源: `civil-engineering-cloud/03-claude-code-runnable/` — Claude Code 源码还原
> 日期: 2026-04-05
> 用途: 提炼可复用的架构模式，指导鲜标智投平台的技术优化

---

## 一、Claude Code 核心架构概览

### 1.1 项目规模

- 1,987+ TypeScript/TSX 源文件
- 运行时: Bun 1.3.5+ / React + Ink (终端 UI)
- API: @anthropic-ai/sdk + MCP 协议
- 核心: Agent 编程框架，支持多 Agent 编排、工具系统、会话管理

### 1.2 分层架构

```
入口层 (dev-entry.ts, main.tsx)
    ↓
启动/初始化层 (entrypoints/, bootstrap/)
    ↓
命令层 (commands/, 87+ 内置命令)
    ↓
查询引擎层 (QueryEngine.ts — 核心循环)
    ↓
工具系统层 (Tool.ts, 53 个内置工具)
    ↓
服务层 (services/api, services/mcp, services/compact)
    ↓
状态管理层 (state/ — 不可变全局状态)
```

---

## 二、关键技术模式详解

### 2.1 LLM 调用 — Async 生成器 + 重试 + 心跳

**Claude Code 实现** (`services/api/withRetry.ts`):

```typescript
async function* withRetry<T>(
  getClient, operation, options
): AsyncGenerator<SystemAPIErrorMessage, T> {
  // 重试循环中通过 yield 发送心跳/状态更新
  // 调用方可实时显示重试状态
  // 最终通过 return 返回成功结果
}
```

**重试策略**:
- MAX_RETRIES: 10，指数退避
- 429 (限流): 所有情况重试
- 529 (过载): 前台查询 3 次上限，后台查询立即失败
- 连接错误: 禁用 keep-alive 后重试
- 认证错误: 刷新令牌后重试
- 持久模式: 429/529 无限重试（最大间隔 5 分钟）+ 30 秒心跳

### 2.2 错误分类与分级恢复

**Claude Code 实现** (`services/api/errors.ts`):

```typescript
// 不同错误走不同恢复路径
if (is529Error)           → 重试 → 降级非流式
if (isPromptTooLongError) → 响应式压缩 → 重试
if (isMediaSizeError)     → 移除图片/PDF → 重试
if (isAuthError)          → 刷新令牌 → 重试
if (modelFails)           → Opus → Sonnet 模型降级
```

**错误解析精度**:
- 从错误消息中解析 token 计数: `parsePromptTooLongTokenCounts()`
- 计算 token 缺口: `getPromptTooLongTokenGap()`
- 按缺口大小决定压缩力度

### 2.3 工具系统架构

**Tool 接口**:

```typescript
type Tool = {
  name: string
  isEnabled?: () => boolean         // 动态启用/禁用
  description: string
  inputSchema: ToolInputJSONSchema  // Zod 校验
  call: (input, context) => Promise<ToolResult>
  canUseTool?: CanUseToolFn         // 权限检查
  progress?: ToolCallProgress       // 进度反馈
}
```

**特点**:
- `getAllBaseTools()` 统一注册，支持动态发现
- `filterToolsByDenyRules()` 根据权限上下文过滤
- `lazySchema()` 惰性求值，避免循环依赖
- 53 个内置工具，按职责分为 9 大类

### 2.4 三层 Agent 系统

1. **主线 Claude**: 与用户直接交互，运行 QueryEngine
2. **异步 Worker Agent**: 通过 `AgentTool` 在子进程中运行，超 15 秒自动后台化
3. **Coordinator Mode**: 主 Claude 变指挥官（仅 Agent/SendMessage/TaskStop），Worker 执行实际工作

**任务追踪**: 任务 ID 生成 → 状态文件 `~/.claude/tasks/` → 完成通知

### 2.5 响应式压缩（Reactive Compaction）

当 Prompt 超限时动态处理:

```typescript
reactiveCompact() {
  gap = getPromptTooLongTokenGap(msg)
  // 按 token 缺口跳过多个消息组
  // 智能总结而非简单删除
}
```

**多层压缩策略**:
1. Snip Compact: 截断早期历史
2. Reactive Compact: 错误时自动压缩
3. Session Memory Compact: 长期会话自动总结
4. Auto Compact: 周期性压缩

### 2.6 特征编译开关

```typescript
import { feature } from 'bun:bundle'

// 编译时条件，零运行时开销
if (feature('KAIROS')) {
  // 仅在 KAIROS 版本中包含
}

// 用户类型门控
process.env.USER_TYPE === 'ant'      // Anthropic 内部
process.env.USER_TYPE === 'external' // 公开发布

// 远程门控 (GrowthBook A/B 测试)
getFeatureValue_CACHED('tengu_kairos', false)
```

**支持 50+ 编译开关，外部版本自动阉割内部功能**

### 2.7 不可变全局状态（AppState）

```typescript
type AppState = DeepImmutable<{
  settings: SettingsJson
  mainLoopModel: ModelSetting
  toolPermissionContext: ToolPermissionContext
  tasks: Map<TaskId, TaskState>
  // ...40+ 字段
}>

// 所有更新通过纯函数
setAppState((prev) => ({ ...prev, newField: value }))
```

### 2.8 权限上下文注入

```typescript
type ToolPermissionContext = {
  mode: 'default' | 'bypass' | 'plan' | 'auto'
  alwaysAllowRules: ToolPermissionRulesBySource
  alwaysDenyRules: ToolPermissionRulesBySource
  alwaysAskRules: ToolPermissionRulesBySource
}

// 作为参数传递给所有工具和 Agent，避免全局状态污染
```

### 2.9 会话持久化与恢复

```typescript
recordTranscript()           // 消息写入 ~/.claude/sessions/{sessionId}
loadConversationForResume()  // 恢复对话
flushSessionStorage()        // 强制刷新磁盘
```

**KAIROS 模式的自动做梦（Dream）**: 距上次整合 24+ 小时且 5+ 新会话时触发，四阶段: Orient → Gather → Consolidate → Prune

### 2.10 大结果落盘

```typescript
buildLargeToolResultMessage(content) {
  if (content.length > THRESHOLD) {
    // 写入 ~/.claude/tool-results/{hash}
    // 消息中仅包含路径引用
  }
}
```

### 2.11 性能优化

- **并行化 I/O**: 启动时多个子系统并行初始化
- **Memoization**: 昂贵操作缓存（命令列表、系统提示、用户上下文）
- **延迟导入**: `require()` 动态导入大模块减少启动时间
- **死代码消除**: 特征编译完全移除未启用功能的代码

---

## 三、鲜标智投可引入的技巧

### 3.1 已有但可增强

| 技巧 | Claude Code 实现 | 鲜标智投现状 | 改进方向 |
|------|-----------------|------------|---------|
| LLM 多模型 Fallback | `withRetry` async 生成器，10 次重试 + 指数退避 + 模型降级 | `circuit_breaker.py` + `call_with_fallback` | 加入心跳机制和指数退避 |
| 工具注册与路由 | `getAllBaseTools()` 统一注册 + `isEnabled()` 动态开关 | `ai_router.py` Tool Calling 8 大工具 | 抽象为工具注册表，支持动态启用/禁用 |
| 权限隔离 | `ToolPermissionContext` 不可变上下文注入 | `tenant_id` + `AuditMixin` | 思路一致，已做得不错 |

### 3.2 高价值新增

#### P0 — 错误分类 + 分级恢复（改动量: 小）

**目标文件**: `backend/app/core/llm_selector.py` 的 `call_with_fallback`

```python
class LLMErrorHandler:
    @staticmethod
    async def handle(error, task_type, retry_context):
        if is_rate_limit(error):       # 429 限流
            await exponential_backoff(retry_context)
            return "retry"
        if is_context_too_long(error):  # prompt 过长
            return "compact_and_retry"
        if is_timeout(error):           # 超时
            return "fallback_model"
        if is_auth_error(error):        # 认证失败
            return "fail_fast"
```

**收益**: LLM 调用稳定性大幅提升，不同错误场景有针对性的恢复策略

#### P0 — Async 生成器 + 心跳（改动量: 中）

**目标文件**: `backend/app/services/bid_generation_service.py`

```python
async def generate_with_progress(project_id, ...):
    yield {"node": 1, "status": "planner_start"}
    outline = await planner.run(...)
    yield {"node": 1, "status": "planner_done", "chapters": len(outline)}
    
    yield {"node": 2, "status": "retriever_start"}
    context = await retriever.search(...)
    yield {"node": 2, "status": "retriever_done", "docs": len(context)}
    
    # ... 每个节点实时推送进度
```

**收益**: 前端用户体验质变，7 节点生成流水线实时进度可见

#### P1 — 响应式压缩（改动量: 中）

**目标文件**: `backend/app/services/generation/writer.py`

```python
async def reactive_compact(context_chunks, max_tokens):
    """RAG 检索上下文超限时，智能压缩而非粗暴截断"""
    if count_tokens(context_chunks) <= max_tokens:
        return context_chunks
    # 按相关性排序
    # 低分段落 → 总结为一句话
    # 高分段落 → 保留原文
    # 确保关键废标项/评分项优先保留
```

**收益**: 生成质量提升，关键信息不因截断丢失

#### P1 — 特征开关（改动量: 小）

**目标文件**: `backend/llm_registry.yaml`

```yaml
features:
  ai_detection: true        # 反 AI 检测引擎
  text_diversifier: true    # 文本差异化
  similarity_check: false   # 围串标检测（灰度中）
  bid_engine_v2: false      # BidEngine 合并（开发中）

# 使用方式
# if feature_enabled("bid_engine_v2"):
#     use_new_pipeline()
# else:
#     use_current_pipeline()
```

**收益**: BidEngine 合并阶段平滑过渡，灰度发布降低风险

#### P2 — 大结果落盘（改动量: 中）

**目标文件**: `backend/app/services/tender_parser.py`

```python
async def store_parse_result(project_id, result):
    """大型解析结果存 OSS，DB 只存引用 + 摘要"""
    payload = json.dumps(result, ensure_ascii=False)
    if len(payload) > 100_000:  # 100KB
        path = await oss_upload(f"parse/{project_id}.json", payload)
        return {"ref": path, "summary": result.get("summary", "")}
    return result
```

**收益**: 数据库性能优化，符合二进制零入库红线

#### P2 — 不可变状态 + 事件溯源（改动量: 大）

**目标文件**: `backend/app/services/bid_project_service.py`

```python
@dataclass
class ProjectStateEvent:
    project_id: int
    from_status: str
    to_status: str
    trigger: str       # "generation_complete" / "compliance_pass"
    timestamp: datetime
    metadata: dict     # 触发时的上下文快照

class ProjectStateMachine:
    TRANSITIONS = {
        "draft": ["parsing", "generating"],
        "parsing": ["parsed", "parse_failed"],
        "parsed": ["generating"],
        "generating": ["generated", "generate_failed"],
        "generated": ["reviewing", "exporting"],
        # ...
    }
    
    async def transition(self, project_id, to_status, trigger, metadata=None):
        current = await self.get_status(project_id)
        if to_status not in self.TRANSITIONS.get(current, []):
            raise InvalidTransition(f"{current} → {to_status}")
        event = ProjectStateEvent(...)
        await self.save_event(event)
        await self.update_status(project_id, to_status)
```

**收益**: 投标项目全生命周期可审计、可回溯、状态机严格校验

---

## 四、实施优先级总结

| 优先级 | 技巧 | 改动量 | 目标文件 | 收益 |
|--------|------|--------|---------|------|
| **P0** | 错误分类 + 分级恢复 | 小 | `llm_selector.py` | LLM 调用稳定性 |
| **P0** | Async 生成器 + 心跳 | 中 | `bid_generation_service.py` | 前端体验质变 |
| **P1** | 响应式压缩 | 中 | `generation/writer.py` | 生成质量提升 |
| **P1** | 特征开关 | 小 | `llm_registry.yaml` | 灰度发布 |
| **P2** | 大结果落盘 | 中 | `tender_parser.py` | DB 性能优化 |
| **P2** | 不可变状态 + 事件溯源 | 大 | `bid_project_service.py` | 可审计可回溯 |

---

## 五、Claude Code 源码参考路径

| 模块 | 文件路径 |
|------|---------|
| 入口 | `src/dev-entry.ts` → `src/entrypoints/cli.tsx` |
| 核心循环 | `src/QueryEngine.ts` |
| API 调用 | `src/services/api/claude.ts` (3400+ 行) |
| 重试机制 | `src/services/api/withRetry.ts` |
| 错误处理 | `src/services/api/errors.ts` |
| 工具接口 | `src/Tool.ts` + `src/tools.ts` |
| Agent 系统 | `src/tools/AgentTool/AgentTool.tsx` |
| 状态管理 | `src/state/AppStateStore.ts` |
| 命令系统 | `src/commands.ts` (87+ 命令) |
| 权限模型 | `src/types/permissions.ts` + `src/utils/permissions/` |
| MCP 集成 | `src/services/mcp/` (客户端 119KB) |
| 会话持久化 | `src/utils/sessionStorage.ts` |
| 上下文压缩 | `src/services/compact/` |
| Prompt 管理 | `src/constants/prompts.ts` |
