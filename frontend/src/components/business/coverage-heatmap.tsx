"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  CheckCircle2,
  AlertTriangle,
  XCircle,
  ChevronDown,
  ChevronUp,
  Lightbulb,
  Target,
} from "lucide-react";

// ============================
// 数据类型
// ============================

export interface CoverageRemediation {
  target_chapter: string;
  target_title: string;
  action: string;
  priority: "high" | "medium" | "low";
}

export interface CoverageItem {
  requirement_id: number;
  requirement_text: string;
  max_score: number | null;
  coverage_score: number;
  covered_in: string[];
  gap_note: string | null;
  remediation: CoverageRemediation | null;
}

export interface CoverageChapter {
  chapter_no: string;
  title: string;
}

export interface CoverageReport {
  overall_coverage: number;
  total_items: number;
  uncovered_count: number;
  chapters: CoverageChapter[];
  items: CoverageItem[];
}

// ============================
// 颜色工具
// ============================

function coverageColor(score: number): string {
  if (score >= 0.8) return "bg-emerald-500";
  if (score >= 0.6) return "bg-emerald-400";
  if (score >= 0.4) return "bg-amber-400";
  if (score >= 0.2) return "bg-orange-400";
  return "bg-red-400";
}

function coverageBg(score: number): string {
  if (score >= 0.8) return "bg-emerald-50 border-emerald-200";
  if (score >= 0.6) return "bg-emerald-50 border-emerald-200";
  if (score >= 0.4) return "bg-amber-50 border-amber-200";
  if (score >= 0.2) return "bg-orange-50 border-orange-200";
  return "bg-red-50 border-red-200";
}

function priorityBadge(priority: string) {
  const map: Record<string, { bg: string; text: string; label: string }> = {
    high: { bg: "bg-red-100", text: "text-red-700", label: "紧急" },
    medium: { bg: "bg-amber-100", text: "text-amber-700", label: "建议" },
    low: { bg: "bg-slate-100", text: "text-slate-600", label: "可选" },
  };
  return map[priority] || map.low;
}

function CoverageIcon({ score }: { score: number }) {
  if (score >= 0.6)
    return <CheckCircle2 className="h-4 w-4 text-emerald-500" />;
  if (score >= 0.3)
    return <AlertTriangle className="h-4 w-4 text-amber-500" />;
  return <XCircle className="h-4 w-4 text-red-500" />;
}

// ============================
// 单行展开的补充建议
// ============================

function RemediationCard({ rem }: { rem: CoverageRemediation }) {
  const badge = priorityBadge(rem.priority);
  return (
    <motion.div
      initial={{ opacity: 0, height: 0 }}
      animate={{ opacity: 1, height: "auto" }}
      exit={{ opacity: 0, height: 0 }}
      className="mt-2 rounded-lg border border-blue-200 bg-blue-50 p-3"
    >
      <div className="flex items-start gap-2">
        <Lightbulb className="mt-0.5 h-4 w-4 shrink-0 text-blue-500" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span
              className={`inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium ${badge.bg} ${badge.text}`}
            >
              {badge.label}
            </span>
            <span className="text-xs text-blue-600">
              <Target className="mr-0.5 inline h-3 w-3" />
              {rem.target_chapter} {rem.target_title}
            </span>
          </div>
          <p className="text-sm text-slate-700 whitespace-pre-wrap">
            {rem.action}
          </p>
        </div>
      </div>
    </motion.div>
  );
}

// ============================
// 主组件
// ============================

export default function CoverageHeatmap({
  report,
}: {
  report: CoverageReport;
}) {
  const [expandedId, setExpandedId] = useState<number | null>(null);

  const overallPct = Math.round(report.overall_coverage * 100);
  const overallSafe = overallPct >= 60;

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 space-y-5">
      {/* 顶部摘要 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div
            className={`flex h-12 w-12 items-center justify-center rounded-full text-lg font-bold ${
              overallSafe
                ? "bg-emerald-100 text-emerald-700"
                : "bg-red-100 text-red-700"
            }`}
          >
            {overallPct}
          </div>
          <div>
            <h3 className="text-sm font-semibold text-slate-900">
              评分覆盖率
            </h3>
            <p className="text-xs text-slate-500">
              {report.total_items} 项评分标准，
              <span
                className={
                  report.uncovered_count > 0
                    ? "text-red-600 font-medium"
                    : "text-emerald-600"
                }
              >
                {report.uncovered_count} 项未充分覆盖
              </span>
            </p>
          </div>
        </div>
        {/* 图例 */}
        <div className="hidden sm:flex items-center gap-3 text-xs text-slate-500">
          <span className="flex items-center gap-1">
            <span className="h-3 w-3 rounded-sm bg-emerald-500" />
            充分
          </span>
          <span className="flex items-center gap-1">
            <span className="h-3 w-3 rounded-sm bg-amber-400" />
            部分
          </span>
          <span className="flex items-center gap-1">
            <span className="h-3 w-3 rounded-sm bg-red-400" />
            缺失
          </span>
        </div>
      </div>

      {/* 总进度条 */}
      <div className="h-2.5 rounded-full bg-slate-100 overflow-hidden">
        <motion.div
          className={`h-full rounded-full ${
            overallSafe
              ? "bg-gradient-to-r from-emerald-400 to-emerald-500"
              : "bg-gradient-to-r from-red-400 to-amber-400"
          }`}
          initial={{ width: 0 }}
          animate={{ width: `${overallPct}%` }}
          transition={{ duration: 0.8, ease: "easeOut" }}
        />
      </div>

      {/* 评分项列表 */}
      <div className="space-y-1.5">
        {report.items.map((item) => {
          const isExpanded = expandedId === item.requirement_id;
          const scorePct = Math.round(item.coverage_score * 100);
          const hasRemediation =
            item.remediation && item.coverage_score < 0.6;

          return (
            <div key={item.requirement_id}>
              <button
                onClick={() =>
                  setExpandedId(isExpanded ? null : item.requirement_id)
                }
                className={`w-full rounded-lg border p-3 text-left transition-all ${
                  coverageBg(item.coverage_score)
                } hover:shadow-sm`}
              >
                <div className="flex items-center gap-3">
                  {/* 覆盖度图标 */}
                  <CoverageIcon score={item.coverage_score} />

                  {/* 评分项文本 */}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-slate-800 truncate">
                      {item.requirement_text}
                    </p>
                    <div className="mt-0.5 flex items-center gap-2 text-xs text-slate-500">
                      {item.max_score && (
                        <span className="font-medium">
                          {item.max_score}分
                        </span>
                      )}
                      {item.covered_in.length > 0 && (
                        <span>
                          覆盖: {item.covered_in.join("、")}
                        </span>
                      )}
                      {item.gap_note && (
                        <span className="text-red-500">{item.gap_note}</span>
                      )}
                    </div>
                  </div>

                  {/* 覆盖度条 */}
                  <div className="hidden sm:flex items-center gap-2 shrink-0 w-32">
                    <div className="flex-1 h-1.5 rounded-full bg-slate-200 overflow-hidden">
                      <div
                        className={`h-full rounded-full ${coverageColor(
                          item.coverage_score
                        )}`}
                        style={{ width: `${scorePct}%` }}
                      />
                    </div>
                    <span className="text-xs font-medium text-slate-600 w-8 text-right">
                      {scorePct}%
                    </span>
                  </div>

                  {/* 展开箭头 */}
                  {hasRemediation && (
                    <div className="shrink-0 text-slate-400">
                      {isExpanded ? (
                        <ChevronUp className="h-4 w-4" />
                      ) : (
                        <ChevronDown className="h-4 w-4" />
                      )}
                    </div>
                  )}
                </div>
              </button>

              {/* 补充建议展开区 */}
              <AnimatePresence>
                {isExpanded && hasRemediation && item.remediation && (
                  <RemediationCard rem={item.remediation} />
                )}
              </AnimatePresence>
            </div>
          );
        })}
      </div>
    </div>
  );
}
