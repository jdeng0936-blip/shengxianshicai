"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  ShieldAlert,
  AlertOctagon,
  AlertTriangle,
  Lightbulb,
  Loader2,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import api from "@/lib/api";

interface RiskItem {
  level: "fatal" | "serious" | "advice";
  category: string;
  title: string;
  detail: string;
  suggestion: string;
}

interface RiskReport {
  project_id: number;
  project_name: string;
  generated_at: string;
  summary: {
    total: number;
    fatal: number;
    serious: number;
    advice: number;
    can_submit: boolean;
  };
  risks: RiskItem[];
}

const LEVEL_CONFIG = {
  fatal: {
    label: "致命",
    icon: AlertOctagon,
    color: "text-red-600",
    bg: "bg-red-50",
    border: "border-red-200",
    badge: "bg-red-100 text-red-700",
  },
  serious: {
    label: "严重",
    icon: AlertTriangle,
    color: "text-orange-600",
    bg: "bg-orange-50",
    border: "border-orange-200",
    badge: "bg-orange-100 text-orange-700",
  },
  advice: {
    label: "建议",
    icon: Lightbulb,
    color: "text-yellow-600",
    bg: "bg-yellow-50",
    border: "border-yellow-200",
    badge: "bg-yellow-100 text-yellow-700",
  },
};

interface Props {
  projectId: string;
}

export default function RiskReportPanel({ projectId }: Props) {
  const [report, setReport] = useState<RiskReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState(true);

  const handleGenerate = async () => {
    setLoading(true);
    try {
      const res = await api.post(`/bid-projects/${projectId}/risk-report`);
      setReport(res.data?.data);
    } catch (err: any) {
      alert(err.response?.data?.detail || "风险报告生成失败");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <ShieldAlert className="h-5 w-5" />
            投标风险报告
          </CardTitle>
          <div className="flex items-center gap-2">
            {report && (
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7"
                onClick={() => setExpanded(!expanded)}
              >
                {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
              </Button>
            )}
            <Button
              onClick={handleGenerate}
              disabled={loading}
              variant={report ? "outline" : "default"}
              size="sm"
            >
              {loading ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <ShieldAlert className="mr-2 h-4 w-4" />
              )}
              {loading ? "检查中..." : report ? "重新检查" : "生成风险报告"}
            </Button>
          </div>
        </div>
      </CardHeader>

      {report && expanded && (
        <CardContent className="space-y-4">
          {/* 汇总卡片 */}
          <div className="grid grid-cols-5 gap-3">
            <div className="rounded-lg bg-slate-50 p-3 text-center">
              <div className="text-2xl font-bold">{report.summary.total}</div>
              <div className="text-xs text-slate-500">风险项</div>
            </div>
            <div className="rounded-lg bg-red-50 p-3 text-center">
              <div className="text-2xl font-bold text-red-600">{report.summary.fatal}</div>
              <div className="text-xs text-red-600">致命</div>
            </div>
            <div className="rounded-lg bg-orange-50 p-3 text-center">
              <div className="text-2xl font-bold text-orange-600">{report.summary.serious}</div>
              <div className="text-xs text-orange-600">严重</div>
            </div>
            <div className="rounded-lg bg-yellow-50 p-3 text-center">
              <div className="text-2xl font-bold text-yellow-600">{report.summary.advice}</div>
              <div className="text-xs text-yellow-600">建议</div>
            </div>
            <div className={`rounded-lg p-3 text-center ${report.summary.can_submit ? "bg-green-50" : "bg-red-50"}`}>
              <div className={`text-lg font-bold ${report.summary.can_submit ? "text-green-600" : "text-red-600"}`}>
                {report.summary.can_submit ? "可投标" : "有风险"}
              </div>
              <div className={`text-xs ${report.summary.can_submit ? "text-green-600" : "text-red-600"}`}>
                {report.summary.can_submit ? "致命项为零" : "存在致命项"}
              </div>
            </div>
          </div>

          {/* 全部通过 */}
          {report.summary.total === 0 && (
            <div className="rounded-lg bg-green-50 p-6 text-center">
              <CheckCircle2 className="mx-auto h-10 w-10 text-green-500" />
              <p className="mt-2 font-medium text-green-700">零风险！投标文件已准备就绪</p>
            </div>
          )}

          {/* 风险列表 — 按级别排序 */}
          {["fatal", "serious", "advice"].map((level) => {
            const items = report.risks.filter((r) => r.level === level);
            if (items.length === 0) return null;
            const config = LEVEL_CONFIG[level as keyof typeof LEVEL_CONFIG];
            const Icon = config.icon;

            return (
              <div key={level} className="space-y-2">
                <h3 className={`flex items-center gap-2 text-sm font-medium ${config.color}`}>
                  <Icon className="h-4 w-4" />
                  {config.label}（{items.length}）
                </h3>
                {items.map((risk, i) => (
                  <div
                    key={i}
                    className={`rounded-lg border p-3 ${config.bg} ${config.border}`}
                  >
                    <div className="flex items-start gap-2">
                      <Badge className={`shrink-0 text-xs ${config.badge}`}>
                        {risk.category}
                      </Badge>
                      <div className="flex-1">
                        <p className="text-sm font-medium text-slate-800">{risk.title}</p>
                        <p className="mt-1 text-xs text-slate-600">{risk.detail}</p>
                        {risk.suggestion && (
                          <p className="mt-1 text-xs text-blue-600">
                            💡 {risk.suggestion}
                          </p>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            );
          })}
        </CardContent>
      )}
    </Card>
  );
}
