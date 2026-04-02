"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
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
  ExternalLink,
  Check,
} from "lucide-react";
import api from "@/lib/api";

interface RiskItem {
  id: string;
  level: "fatal" | "critical" | "warning";
  category: string;
  title: string;
  description: string;
  chapter_id: string | null;
  chapter_title: string | null;
  field_name: string | null;
  expected_value: string | null;
  actual_value: string | null;
  suggestion: string;
  is_resolved: boolean;
}

interface RiskReport {
  bid_project_id: string;
  generated_at: string;
  total_items: number;
  fatal_count: number;
  critical_count: number;
  warning_count: number;
  items: RiskItem[];
  can_export: boolean;
}

const LEVEL_CONFIG = {
  fatal: {
    label: "致命",
    icon: AlertOctagon,
    color: "text-red-600",
    bg: "bg-red-50",
    border: "border-red-200",
    badge: "bg-red-100 text-red-700",
    barColor: "bg-red-500",
  },
  critical: {
    label: "严重",
    icon: AlertTriangle,
    color: "text-orange-600",
    bg: "bg-orange-50",
    border: "border-orange-200",
    badge: "bg-orange-100 text-orange-700",
    barColor: "bg-orange-500",
  },
  warning: {
    label: "建议",
    icon: Lightbulb,
    color: "text-yellow-600",
    bg: "bg-yellow-50",
    border: "border-yellow-200",
    badge: "bg-yellow-100 text-yellow-700",
    barColor: "bg-yellow-500",
  },
};

interface Props {
  projectId: string;
  /** 挂载后自动触发检查 */
  autoCheck?: boolean;
}

export default function RiskReportPanel({ projectId, autoCheck = false }: Props) {
  const router = useRouter();
  const [report, setReport] = useState<RiskReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState(true);
  const [checkStage, setCheckStage] = useState("");
  const [triggered, setTriggered] = useState(false);

  const handleCheck = async () => {
    setLoading(true);
    setCheckStage("正在检查数据一致性...");
    try {
      // 模拟阶段推进（后端是同步返回的，前端分阶段展示提升体感）
      const stageTimer1 = setTimeout(() => setCheckStage("正在核验资质有效期..."), 1500);
      const stageTimer2 = setTimeout(() => setCheckStage("正在检查评分覆盖..."), 3000);

      const res = await api.post(`/bid-projects/${projectId}/risk/check`);
      clearTimeout(stageTimer1);
      clearTimeout(stageTimer2);
      setReport(res.data?.data);
      setCheckStage("");
    } catch (err: any) {
      alert(err.response?.data?.detail || "风险检查失败");
      setCheckStage("");
    } finally {
      setLoading(false);
    }
  };

  // autoCheck: 首次挂载自动触发
  if (autoCheck && !triggered && !loading && !report) {
    setTriggered(true);
    handleCheck();
  }

  const handleResolve = async (itemId: string) => {
    try {
      await api.put(`/bid-projects/${projectId}/risk/items/${itemId}/resolve`);
      setReport((prev) => {
        if (!prev) return prev;
        const updatedItems = prev.items.map((item) =>
          item.id === itemId ? { ...item, is_resolved: true } : item
        );
        const unresolvedFatal = updatedItems.filter(
          (item) => item.level === "fatal" && !item.is_resolved
        ).length;
        return {
          ...prev,
          items: updatedItems,
          can_export: unresolvedFatal === 0,
        };
      });
    } catch (err: any) {
      alert(err.response?.data?.detail || "标记修复失败");
    }
  };

  const handleJumpToChapter = (chapterId: string) => {
    router.push(
      `/dashboard/bid-projects/${projectId}/chapters?highlight=${chapterId}`
    );
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
              onClick={handleCheck}
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

      {/* 检查阶段动画 */}
      {loading && checkStage && (
        <CardContent>
          <div className="flex items-center gap-3 rounded-lg bg-blue-50 p-4">
            <Loader2 className="h-5 w-5 animate-spin text-blue-600" />
            <span className="text-sm font-medium text-blue-700">{checkStage}</span>
          </div>
        </CardContent>
      )}

      {report && expanded && (
        <CardContent className="space-y-4">
          {/* 汇总卡片 */}
          <div className="grid grid-cols-5 gap-3">
            <div className="rounded-lg bg-slate-50 p-3 text-center">
              <div className="text-2xl font-bold">{report.total_items}</div>
              <div className="text-xs text-slate-500">风险项</div>
            </div>
            <div className="rounded-lg bg-red-50 p-3 text-center">
              <div className="text-2xl font-bold text-red-600">{report.fatal_count}</div>
              <div className="text-xs text-red-600">致命</div>
            </div>
            <div className="rounded-lg bg-orange-50 p-3 text-center">
              <div className="text-2xl font-bold text-orange-600">{report.critical_count}</div>
              <div className="text-xs text-orange-600">严重</div>
            </div>
            <div className="rounded-lg bg-yellow-50 p-3 text-center">
              <div className="text-2xl font-bold text-yellow-600">{report.warning_count}</div>
              <div className="text-xs text-yellow-600">建议</div>
            </div>
            <div className={`rounded-lg p-3 text-center ${report.can_export ? "bg-green-50" : "bg-red-50"}`}>
              <div className={`text-lg font-bold ${report.can_export ? "text-green-600" : "text-red-600"}`}>
                {report.can_export ? "可导出" : "阻断导出"}
              </div>
              <div className={`text-xs ${report.can_export ? "text-green-600" : "text-red-600"}`}>
                {report.can_export ? "致命项为零" : "存在未修复致命项"}
              </div>
            </div>
          </div>

          {/* 全部通过 */}
          {report.total_items === 0 && (
            <div className="rounded-lg bg-green-50 p-6 text-center">
              <CheckCircle2 className="mx-auto h-10 w-10 text-green-500" />
              <p className="mt-2 font-medium text-green-700">零风险！投标文件已准备就绪</p>
            </div>
          )}

          {/* 风险列表 — 按级别排序 */}
          {(["fatal", "critical", "warning"] as const).map((level) => {
            const items = report.items.filter((r) => r.level === level);
            if (items.length === 0) return null;
            const config = LEVEL_CONFIG[level];
            const Icon = config.icon;

            return (
              <div key={level} className="space-y-2">
                <h3 className={`flex items-center gap-2 text-sm font-medium ${config.color}`}>
                  <Icon className="h-4 w-4" />
                  {config.label}（{items.length}）
                </h3>
                {items.map((risk) => (
                  <div
                    key={risk.id}
                    className={`rounded-lg border p-3 ${
                      risk.is_resolved
                        ? "border-slate-200 bg-slate-50"
                        : `${config.bg} ${config.border}`
                    }`}
                  >
                    <div className="flex items-start gap-2">
                      {/* 左侧色标 */}
                      <div className={`mt-0.5 w-1 shrink-0 self-stretch rounded-full ${
                        risk.is_resolved ? "bg-slate-300" : config.barColor
                      }`} />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <Badge className={`shrink-0 text-xs ${
                            risk.is_resolved ? "bg-slate-200 text-slate-500" : config.badge
                          }`}>
                            {risk.category}
                          </Badge>
                          <p className={`text-sm font-medium ${
                            risk.is_resolved ? "text-slate-400 line-through" : "text-slate-800"
                          }`}>
                            {risk.title}
                          </p>
                        </div>
                        <p className={`mt-1 text-xs ${
                          risk.is_resolved ? "text-slate-400" : "text-slate-600"
                        }`}>
                          {risk.description}
                        </p>
                        {/* 期望值 vs 实际值 */}
                        {risk.expected_value && risk.actual_value && (
                          <div className="mt-1.5 flex items-center gap-3 text-xs">
                            <span className="rounded bg-green-100 px-1.5 py-0.5 text-green-700">
                              期望: {risk.expected_value}
                            </span>
                            <span className="rounded bg-red-100 px-1.5 py-0.5 text-red-600">
                              实际: {risk.actual_value}
                            </span>
                          </div>
                        )}
                        {risk.suggestion && !risk.is_resolved && (
                          <p className="mt-1.5 text-xs text-blue-600">
                            💡 {risk.suggestion}
                          </p>
                        )}
                        {/* 操作按钮 */}
                        {!risk.is_resolved && (
                          <div className="mt-2 flex items-center gap-2">
                            {risk.chapter_id && (
                              <Button
                                variant="outline"
                                size="sm"
                                className="h-6 px-2 text-xs"
                                onClick={() => handleJumpToChapter(risk.chapter_id!)}
                              >
                                <ExternalLink className="mr-1 h-3 w-3" />
                                跳转到章节
                                {risk.chapter_title && (
                                  <span className="ml-1 text-slate-400">({risk.chapter_title})</span>
                                )}
                              </Button>
                            )}
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-6 px-2 text-xs text-green-600 hover:text-green-700"
                              onClick={() => handleResolve(risk.id)}
                            >
                              <Check className="mr-1 h-3 w-3" />
                              标记已修复
                            </Button>
                          </div>
                        )}
                        {risk.is_resolved && (
                          <div className="mt-1 flex items-center gap-1 text-xs text-green-600">
                            <CheckCircle2 className="h-3 w-3" />
                            已修复
                          </div>
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
