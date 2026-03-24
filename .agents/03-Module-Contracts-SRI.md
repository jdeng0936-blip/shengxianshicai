# 📋 项目开发契约索引 — 模块级规范（SRI)
# (Antigravity Project Rules — 放入项目 .agents/ 目录)
#
# 说明：本文件补充项目特定的模块级约束，与 01-AI-Platform-Rules.md 配合使用。
# 新增功能前，必须先读对应的契约文件，了解已定义的 Schema 和 API，不得重复定义。

---

## ⚙️ 交付环境强制要求（原 02-Project-SRI.md）

| 项目 | 规范 |
|------|------|
| **操作系统** | Ubuntu 22.04 LTS（生产）/ macOS 14+（开发）|
| **容器运行时** | Docker Engine 24+ / Docker Desktop 4+ |
| **Node.js** | ≥ 20.9.0 LTS（已通过 `.nvmrc` 和 `engines` 约束）|
| **Python** | 3.11.x（已通过 Dockerfile 和 CI 约束）|

**部署模式**：
- 开发环境：Docker 仅启动 PostgreSQL + Redis，前后端本地直接运行（`npm run dev` / `uvicorn --reload`）
- 生产环境：全容器化（`docker compose up -d`），Nginx 反代统一入口

---

## 📦 交付物清单（必须全部交付）

- [ ] 源代码（GitHub 仓库）
- [ ] 部署文档（README.md）
- [ ] Docker 一键部署配置（docker-compose.yml）
- [ ] 数据库迁移脚本（migrations/）
- [ ] 种子数据脚本（scripts/seed_data.py）
- [ ] 数据库备份恢复脚本（scripts/db_backup.sh / db_restore.sh）
- [ ] CI/CD 流水线（.github/workflows/）
- [ ] 单元测试报告（pytest / vitest）

---

## 📐 已实现模块的 Schema 和 API 契约（只读，禁止重复定义）

> ⚠️ 以下契约均已实现。**新增功能时必须先读对应契约**，不得与已有 Schema 冲突。
> 完整细节见 `docs/contracts/` 目录下的对应文件。

---

### CAL-01：支护计算引擎 → [完整契约](../contracts/CAL-01.contract.md)

**核心规范**：
- 输入 Schema：`SupportCalcInput`（围岩级别/断面形式/宽高/锚杆参数）
- 输出 Schema：`SupportCalcResult`（净断面积/锚固力/最大间距/最少锚索数/安全系数/预警列表）
- API：`POST /api/v1/calc/support`（必须 JWT）
- **必须实现的5条公式**（均有国标出处）：
  - F1：顶板锚杆锚固力 `Q = K × γ × S × L`（GB/T 35056）
  - F2：锚杆间排距验算 `a ≤ L_f / (K × n)`
  - F3：锚索破断力校核 `P_b ≥ K_s × Q_单根`
  - F4：断面净面积（矩形/拱形分支计算）
  - F5：支护密度 `N = S_top / (a × b)`
- **合规拦截**：锚杆间距超限 → 红色 error 预警；锚索不足 → 红色 error 预警；安全系数 < 1.5 → fail

---

### DAT-01：标准化基础库 → [完整契约](../contracts/DAT-01.contract.md)

**核心规范**：
- 数据模型：`StdDocument`（规范文档主表）+ `StdClause`（条款树，`parent_id` 自引用）
- **所有查询必须注入 `tenant_id` 过滤**（继承 AuditMixin）
- API 前缀：`/api/v1/standards`（7个接口，含文档 CRUD + 条款 CRUD）
- 条款树用递归 CTE（`WITH RECURSIVE`）实现，禁止应用层递归

---

### DAT-05：规则引擎 → [完整契约](../contracts/DAT-05.contract.md)

**核心规范**：
- **严禁硬编码 if-else**：结构化规则层通过条件表匹配，LLM 路由层预留接口
- 9个运算符（全部必须实现）：`eq` `ne` `gt` `lt` `gte` `lte` `in` `between` `contains`
- 17个 ProjectParams 字段均有对应的运算符适用矩阵（见契约文件 2.2节）
- Match Engine 是纯函数，条件 AND 逻辑，按 `priority` 降序排列
- API：`POST /projects/{id}/match`（触发匹配）+ `GET /projects/{id}/match-result`（获取结果）

---

### DOC-01：文档生成引擎 → [完整契约](../contracts/DOC-01.contract.md)

**核心规范**：
- 编排5步链路（严格顺序，不得跳过）：
  1. 加载 ProjectParams
  2. `RuleService.match_rules()` 获取命中规则
  3. `SupportCalcEngine` + `VentCalcEngine` 获取计算结果
  4. 按章节顺序（封面→参数→支护→通风→安全→附录）组装内容
  5. `python-docx` 生成 `.docx` 文件，存 `storage/outputs/`
- API：`POST /projects/{id}/generate` + `GET /projects/{id}/document`
- 生成文档必须含：封面（项目名/矿井名/编制日期）+ 合规预警醒目标注

---

## 🔴 新增模块开发前的必做检查

新增任何后端模块前，必须按以下顺序操作：

```
1. 确认是否已有契约文件（docs/contracts/）
   ├── 有 → 先读完整契约，不得与已定义 Schema/API 冲突
   └── 无 → 先写契约文件（docs/contracts/XXX.contract.md），再写代码

2. 确认 Schema 是否已在 Pydantic 中定义
   ├── 已定义 → 直接复用，禁止重复定义相似结构
   └── 未定义 → 按 Pydantic V2 规范定义，含完整字段注释

3. 确认 API 路径是否与已有路径冲突
   └── 查 app/api/v1/ 目录下已有路由定义

4. 确认测试覆盖
   ├── 计算引擎：纯函数单测，覆盖边界用例
   └── AI 服务：Mock LLM，不发起真实调用
```
