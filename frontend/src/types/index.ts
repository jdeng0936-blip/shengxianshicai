/**
 * 前端核心业务类型定义
 *
 * 减少 any 使用，提升 IDE 提示和类型安全。
 */

import type { LucideIcon } from "lucide-react";

/* ===== 投标项目相关 ===== */

/** 投标企业信息 */
export interface Enterprise {
  id: number;
  name: string;
  short_name?: string;
  credit_code?: string;
  food_license_no?: string;
  haccp_certified?: boolean;
  tenant_id?: number;
}

/** 投标项目信息 */
export interface BidProject {
  id: number;
  project_name: string;
  enterprise_id?: number;
  tender_org?: string;
  customer_type?: string;
  tender_type?: string;
  deadline?: string;
  budget_amount?: number;
  bid_amount?: number;
  delivery_scope?: string;
  delivery_period?: string;
  status: "draft" | "parsing" | "generating" | "reviewing" | "finalized" | "submitted";
  tender_doc_path?: string;
  bid_doc_path?: string;
  created_at?: string;
  updated_at?: string;
}

/* ===== 文档相关 ===== */

/** 生成的文档 */
export interface GeneratedDoc {
  filename: string;
  size: number;
  created_at: string;
  download_url: string;
}

/** 章节内容 */
export interface Chapter {
  title: string;
  content?: string;
  source?: string;
  warnings?: CalcWarning[];
}

/** 文档生成结果 */
export interface DocGenerateResult {
  project_id: number;
  project_name: string;
  file_path: string;
  total_chapters: number;
  total_warnings: number;
  chapters: Chapter[];
}

/* ===== 计算校验 ===== */

/** 预警项 */
export interface CalcWarning {
  level: "error" | "warning" | "info";
  field: string;
  message: string;
}

/** 合规校验项 */
export interface ComplianceItem {
  category: string;
  item: string;
  status: "pass" | "fail" | "warning";
  message: string;
  suggestion?: string;
}

/** 规则冲突 */
export interface RuleConflict {
  type: string;
  severity: "error" | "warning";
  rule_a_id: number;
  rule_a_name: string;
  rule_b_id: number;
  rule_b_name: string;
  detail: string;
  suggestion?: string;
}

/* ===== 通用 ===== */

/** 颜色映射（图标 + 背景 + 文字） */
export interface ColorStyle {
  bg: string;
  text: string;
  icon: LucideIcon;
}

/** API 错误（catch 中使用） */
export interface ApiError {
  response?: {
    data?: {
      detail?: string;
    };
  };
  message: string;
}
