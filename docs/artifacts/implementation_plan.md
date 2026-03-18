# P3 + P4: 业务数据导入 & 自动化测试

## 目标

1. **P3**: 向标准库和规则库导入真实煤矿掘进业务数据，为 AI 助手和规则匹配引擎提供基础知识
2. **P4**: 搭建 pytest 测试基础设施，覆盖核心 API 路由的 CRUD 测试

---

## P3: 导入真实业务数据

### 方案

通过编写 Python 种子脚本（`seed_data.py`），调用后端 API 批量导入数据。好处：直接复用 JWT 鉴权流程，验证 API 端到端可用性。

### 标准库数据（8 份文档 + 条款）

| # | 分类 | 文档名称 | 关键条款数 |
|:-:|------|---------|:----------:|
| 1 | 法律法规 | 《中华人民共和国煤矿安全规程》(2022) | 5 |
| 2 | 法律法规 | 《煤矿防治水细则》(2018) | 3 |
| 3 | 技术规范 | 《煤矿巷道锚杆支护技术规范》GB/T 35056-2018 | 4 |
| 4 | 技术规范 | 《煤矿井巷工程质量验收规范》GB 50213-2018 | 3 |
| 5 | 安全规程 | 《煤矿掘进工作面作业规程编制指南》 | 4 |
| 6 | 安全规程 | 《煤矿通风安全质量标准化标准》 | 3 |
| 7 | 集团标准 | 《华阳集团掘进工作面管理规定》 | 3 |
| 8 | 集团标准 | 《华阳集团煤巷锚杆支护技术标准》 | 3 |

### 规则库数据（3 组 12 条规则）

**规则组 1: 支护规则组**（5 条规则）

| 规则名 | 条件 | 结论 |
|--------|------|------|
| IV/V 类围岩锚索加强 | `rock_class` in `["IV","V"]` | 章节 4.2 支护参数锚索加密 |
| III 类围岩标准支护 | `rock_class` eq `"III"` | 章节 4.2 标准锚杆间距 |
| 拱形断面特殊支护 | `section_form` eq `"拱形"` | 章节 4.3 拱形顶板支护 |
| 大断面加强支护 | `section_width` gte `5.0` | 章节 4.2 加密锚杆 |
| 煤巷锚网索联合支护 | `excavation_type` eq `"煤巷"` | 章节 4.4 锚网索方案 |

**规则组 2: 通风规则组**（4 条规则）

| 规则名 | 条件 | 结论 |
|--------|------|------|
| 高瓦斯矿井通风 | `gas_level` in `["高瓦斯","突出"]` | 章节 6.1 双风机双电源 |
| 低瓦斯标准通风 | `gas_level` eq `"低瓦斯"` | 章节 6.1 单风机 |
| 长距离掘进通风 | `excavation_length` gte `1000` | 章节 6.2 加大风筒直径 |
| 大断面需风量校核 | `section_width` gte `5.0` AND `section_height` gte `4.0` | 章节 6.3 风速校核 |

**规则组 3: 安全规则组**（3 条规则）

| 规则名 | 条件 | 结论 |
|--------|------|------|
| 突出矿井防突措施 | `gas_level` eq `"突出"` | 章节 8.1 区域防突 |
| 水文地质安全 | `hydro_type` contains `"复杂"` | 章节 8.3 探放水措施 |
| 自燃煤层防灭火 | `spontaneous_combustion` in `["容易","自燃"]` | 章节 8.4 防灭火措施 |

### 文件清单

#### [NEW] [seed_data.py](file:///Users/imac2026/Desktop/掘进工作面规程智能生成平台/backend/scripts/seed_data.py)
- Python 脚本，通过 HTTP API 调用导入数据
- 先登录获取 JWT → 批量 POST 标准文档+条款 → 批量 POST 规则组+规则
- 幂等设计：先查询是否已存在同名数据，避免重复导入

---

## P4: 自动化测试

### 方案

遵循用户规则：`pytest` + `pytest-asyncio` + `httpx.AsyncClient`，通过 `ASGITransport` 直连 FastAPI app 实例（不启动 Uvicorn）。

> [!IMPORTANT]
> 严格 Mock LLM API 调用和 OSS 上传，不发真实外部请求。数据库使用 Docker 容器内的 PostgreSQL 测试 schema。

### 测试文件清单

| # | 文件 | 覆盖范围 |
|:-:|------|---------|
| 1 | `conftest.py` | async client fixture, JWT token fixture, DB session fixture |
| 2 | `test_auth.py` | 登录、登录失败、Token 刷新 |
| 3 | `test_standards.py` | 标准库 CRUD（创建/列表/更新/删除） |
| 4 | `test_rules.py` | 规则组+规则 CRUD（含条件/结论验证） |
| 5 | `test_projects.py` | 项目 CRUD + mine_name 返回验证 |
| 6 | `test_calc.py` | 3 个计算引擎的 API 输入输出校验 |

### 文件详情

#### [NEW] [conftest.py](file:///Users/imac2026/Desktop/掘进工作面规程智能生成平台/backend/tests/conftest.py)
- `async_client` fixture: `httpx.AsyncClient` + `ASGITransport`
- `auth_headers` fixture: 自动登录 admin 获取 JWT, 返回 `{"Authorization": "Bearer xxx"}`
- 所有 fixture 使用 `session` scope 以避免重复登录

#### [NEW] [test_auth.py](file:///Users/imac2026/Desktop/掘进工作面规程智能生成平台/backend/tests/test_auth.py)
- 正确登录 → 200 + access_token
- 错误密码 → 401
- 无 Token 访问受保护路由 → 401

#### [NEW] [test_standards.py](file:///Users/imac2026/Desktop/掘进工作面规程智能生成平台/backend/tests/test_standards.py)
- POST 创建 → 201 + id
- GET 列表 → items 包含刚创建的
- PUT 更新 → 200 + 修改确认
- DELETE → 200 + 列表不再包含

#### [NEW] [test_rules.py](file:///Users/imac2026/Desktop/掘进工作面规程智能生成平台/backend/tests/test_rules.py)
- 创建规则组 → 201
- 创建规则（含 conditions + actions） → 201
- 列表查询 → 包含条件和结论
- 删除规则组 → 级联删除验证

#### [NEW] [test_projects.py](file:///Users/imac2026/Desktop/掘进工作面规程智能生成平台/backend/tests/test_projects.py)
- 创建项目 → 200 + mine_name 返回
- 列表 → 包含 mine_name
- 更新 → 200
- 删除 → 200

#### [NEW] [test_calc.py](file:///Users/imac2026/Desktop/掘进工作面规程智能生成平台/backend/tests/test_calc.py)
- POST 支护计算 → 200 + 合理结果
- POST 通风计算 → 200
- POST 循环作业 → 200

---

## 验证计划

### 自动化
```bash
# P3 种子数据导入
docker exec excavation-api python scripts/seed_data.py

# P4 测试运行
docker exec excavation-api pytest tests/ -v --tb=short
```

### 手动
- 浏览器确认标准库新增文档显示
- 浏览器确认规则管理新增规则组显示
- pytest 输出全绿
