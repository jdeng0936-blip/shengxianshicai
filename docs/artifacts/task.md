# 🎯 鲜标智投 — 当前任务清单

> 更新日期：2026-04-05 | 同步自远程最新（2026-04-04 17:06）

## 已完成（W1 ~ W5 + Phase 1.2）
- [x] W1: RBAC权限 + 统一日志 + 租户隔离 + 迁移目录
- [x] W2: 风险报告 + 导出增强 + 计费基础
- [x] W3: AI生成质量 + 企业画像(五维雷达) + 围串标检测 + 差异化引擎
- [x] W4: E2E 16步全链路测试 + 安全回归 + 资质预警 + 检查清单
- [x] W5: 商机漏斗 + 知识库重构 + 前端全面增强
- [x] Phase 1.2: 七节点生成流水线（Node1-7 全实现，59+条测试）
- [x] 支付中心模块（API + Model + Service + Migration + Test）
- [x] LLM 四级降级路由 + 熔断器
- [x] WebSocket 实时管线进度（Redis Pub/Sub）
- [x] 反AI检测引擎（五维度）
- [x] 195号文合规增强 + 移动端适配
- [x] edit_ratio 闭环（用户编辑占比仪表盘）

---

## 下一步待开发

### 优先级 P0 — 验证当前代码
- [ ] 跑 pytest 确认 23 个测试文件全绿（git pull 后未验证）
- [ ] 支付中心前端页面（后端已就绪，前端缺 `/dashboard/billing/payment` 页面）

### 优先级 P1 — Phase 2 行业插件化
- [ ] 设计 `IndustryPlugin` 抽象基类（`backend/app/plugins/base.py`）
- [ ] 实现 `FreshFoodPlugin`（生鲜配送行业插件）
- [ ] 改造核心服务使用插件（`bid_generation_service.py` 等）
- [ ] 数据库迁移：`bid_project` 增加 `industry_code` 字段

### 优先级 P2 — Phase 3 评分驱动 + 变体
- [ ] 评分点提取服务（`scoring_extract_service.py`）
- [ ] 评分点 → 驱动目录生成（对接 `TenderRequirement`）
- [ ] 变体生成引擎（`variant_service.py`，防撞标）
- [ ] 前端工作台 7步流程融合
