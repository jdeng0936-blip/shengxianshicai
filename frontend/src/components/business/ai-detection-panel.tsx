"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import {
  Shield,
  ShieldAlert,
  ShieldCheck,
  ChevronDown,
  ChevronUp,
  Lightbulb,
  Loader2,
} from "lucide-react";
import { Button } from "@/components/ui/button";

// ============================
// 数据类型
// ============================

export interface DetectionDimension {
  name: string;
  score: number;
  detail: string;
  suggestion: string;
}

export interface DetectionResult {
  chapter_no: string;
  title: string;
  overall_score: number;
  risk_level: "low" | "medium" | "high";
  summary: string;
  dimensions: DetectionDimension[];
}

// ============================
// 风险色彩
// ============================

function riskColor(level: string) {
  if (level === "high") return { bg: "bg-red-50", border: "border-red-200", text: "text-red-700", ring: "ring-red-500" };
  if (level === "medium") return { bg: "bg-amber-50", border: "border-amber-200", text: "text-amber-700", ring: "ring-amber-500" };
  return { bg: "bg-emerald-50", border: "border-emerald-200", text: "text-emerald-700", ring: "ring-emerald-500" };
}

function riskLabel(level: string) {
  if (level === "high") return "高风险";
  if (level === "medium") return "中风险";
  return "低风险";
}

function RiskIcon({ level }: { level: string }) {
  if (level === "high") return <ShieldAlert className="h-5 w-5 text-red-500" />;
  if (level === "medium") return <Shield className="h-5 w-5 text-amber-500" />;
  return <ShieldCheck className="h-5 w-5 text-emerald-500" />;
}

// ============================
// 维度条形图
// ============================

function DimensionBar({ dim }: { dim: DetectionDimension }) {
  const barColor =
    dim.score >= 60
      ? "bg-red-400"
      : dim.score >= 35
      ? "bg-amber-400"
      : "bg-emerald-400";

  const [expanded, setExpanded] = useState(false);

  return (
    <div className="space-y-1">
      <button
        onClick={() => dim.suggestion && setExpanded(!expanded)}
        className="w-full text-left"
      >
        <div className="flex items-center justify-between text-sm">
          <span className="text-slate-700 font-medium">{dim.name}</span>
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-500">{dim.detail}</span>
            <span
              className={`text-xs font-bold ${
                dim.score >= 60
                  ? "text-red-600"
                  : dim.score >= 35
                  ? "text-amber-600"
                  : "text-emerald-600"
              }`}
            >
              {Math.round(dim.score)}
            </span>
            {dim.suggestion && (
              expanded ? (
                <ChevronUp className="h-3.5 w-3.5 text-slate-400" />
              ) : (
                <ChevronDown className="h-3.5 w-3.5 text-slate-400" />
              )
            )}
          </div>
        </div>
        <div className="mt-1 h-1.5 rounded-full bg-slate-100 overflow-hidden">
          <motion.div
            className={`h-full rounded-full ${barColor}`}
            initial={{ width: 0 }}
            animate={{ width: `${Math.min(dim.score, 100)}%` }}
            transition={{ duration: 0.6, ease: "easeOut" }}
          />
        </div>
      </button>
      {expanded && dim.suggestion && (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: "auto" }}
          className="flex items-start gap-1.5 rounded-md bg-blue-50 px-2.5 py-2 text-xs text-blue-700"
        >
          <Lightbulb className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span>{dim.suggestion}</span>
        </motion.div>
      )}
    </div>
  );
}

// ============================
// 主组件
// ============================

interface AIDetectionPanelProps {
  result: DetectionResult | null;
  loading: boolean;
  onDetect: () => void;
  onHumanize?: () => void;
  humanizing?: boolean;
}

export default function AIDetectionPanel({
  result,
  loading,
  onDetect,
  onHumanize,
  humanizing,
}: AIDetectionPanelProps) {
  const color = result ? riskColor(result.risk_level) : riskColor("low");

  return (
    <div className={`rounded-xl border ${color.border} ${color.bg} p-4 space-y-4`}>
      {/* 头部 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {result ? (
            <RiskIcon level={result.risk_level} />
          ) : (
            <Shield className="h-5 w-5 text-slate-400" />
          )}
          <span className="text-sm font-semibold text-slate-800">
            反 AI 检测
          </span>
          {result && (
            <span
              className={`rounded-full px-2 py-0.5 text-xs font-medium ${color.text} ${
                result.risk_level === "high"
                  ? "bg-red-100"
                  : result.risk_level === "medium"
                  ? "bg-amber-100"
                  : "bg-emerald-100"
              }`}
            >
              {riskLabel(result.risk_level)} · {Math.round(result.overall_score)}分
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {result && result.risk_level !== "low" && onHumanize && (
            <Button
              size="sm"
              variant="default"
              onClick={onHumanize}
              disabled={humanizing}
              className="bg-blue-600 hover:bg-blue-700 text-white"
            >
              {humanizing ? (
                <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
              ) : (
                <ShieldCheck className="mr-1.5 h-3.5 w-3.5" />
              )}
              {humanizing ? "润色中..." : "一键降 AI"}
            </Button>
          )}
          <Button
            size="sm"
            variant="outline"
            onClick={onDetect}
            disabled={loading}
          >
            {loading ? (
              <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
            ) : (
              <Shield className="mr-1.5 h-3.5 w-3.5" />
            )}
            {loading ? "检测中..." : result ? "重新检测" : "开始检测"}
          </Button>
        </div>
      </div>

      {/* 摘要 */}
      {result && (
        <p className="text-sm text-slate-600">{result.summary}</p>
      )}

      {/* 五维度明细 */}
      {result && result.dimensions.length > 0 && (
        <div className="space-y-3">
          {result.dimensions.map((dim) => (
            <DimensionBar key={dim.name} dim={dim} />
          ))}
        </div>
      )}

      {/* 空状态 */}
      {!result && !loading && (
        <p className="text-center text-sm text-slate-400 py-2">
          点击「开始检测」分析当前章节的 AI 生成痕迹
        </p>
      )}
    </div>
  );
}
