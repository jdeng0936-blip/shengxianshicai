"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  FileText,
  Building2,
  Loader2,
  ArrowUpRight,
  Clock,
  CheckCircle2,
  AlertTriangle,
  Sparkles,
  Zap,
  CalendarClock,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import api from "@/lib/api";
import Link from "next/link";

interface BidProject {
  id: number;
  project_name: string;
  tender_org?: string;
  customer_type?: string;
  status: string;
  budget_amount?: number;
  deadline?: string;
  created_at?: string;
}

const STATUS_MAP: Record<string, { label: string; color: string }> = {
  draft: { label: "草稿", color: "bg-slate-100 text-slate-600" },
  parsing: { label: "解析中", color: "bg-blue-100 text-blue-700" },
  parsed: { label: "已解析", color: "bg-cyan-100 text-cyan-700" },
  generating: { label: "生成中", color: "bg-blue-100 text-blue-700" },
  generated: { label: "已生成", color: "bg-green-100 text-green-700" },
  reviewing: { label: "审查中", color: "bg-yellow-100 text-yellow-700" },
  completed: { label: "已完成", color: "bg-green-100 text-green-700" },
  submitted: { label: "已投标", color: "bg-purple-100 text-purple-700" },
  won: { label: "已中标", color: "bg-emerald-100 text-emerald-700" },
  lost: { label: "未中标", color: "bg-red-100 text-red-600" },
  failed: { label: "失败", color: "bg-red-100 text-red-600" },
};

const CUSTOMER_LABELS: Record<string, string> = {
  school: "学校", hospital: "医院", government: "政府",
  enterprise: "企业", canteen: "团餐",
};

export default function DashboardPage() {
  const [projects, setProjects] = useState<BidProject[]>([]);
  const [stats, setStats] = useState<{
    total: number; in_progress: number; completed: number; total_budget: number;
  } | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [projRes, statsRes] = await Promise.all([
          api.get("/bid-projects"),
          api.get("/bid-projects/dashboard/stats"),
        ]);
        setProjects(projRes.data?.data || []);
        setStats(statsRes.data?.data || null);
      } catch {
        // ignore
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, []);

  const total = stats?.total ?? projects.length;
  const inProgress = stats?.in_progress ?? 0;
  const completed = stats?.completed ?? 0;
  const totalBudget = stats?.total_budget ?? projects.reduce((sum, p) => sum + (p.budget_amount || 0), 0);

  const recentProjects = [...projects]
    .sort((a, b) => (b.created_at || "").localeCompare(a.created_at || ""))
    .slice(0, 6);

  const cards = [
    { title: "投标项目", value: total, icon: FileText, desc: "总项目数", color: "text-blue-600", bg: "bg-blue-50" },
    { title: "进行中", value: inProgress, icon: Clock, desc: "解析/生成/审查", color: "text-amber-600", bg: "bg-amber-50" },
    { title: "已完成", value: completed, icon: CheckCircle2, desc: "完成/投标/中标", color: "text-green-600", bg: "bg-green-50" },
    {
      title: "总预算",
      value: totalBudget > 0 ? `${(totalBudget / 10000).toFixed(0)}万` : "—",
      icon: Building2,
      desc: "累计预算金额",
      color: "text-purple-600",
      bg: "bg-purple-50",
    },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-slate-800 dark:text-white">工作台</h2>
        <Link href="/dashboard/bid-projects/new">
          <span className="flex items-center gap-1 text-sm text-blue-600 hover:underline cursor-pointer">
            <Sparkles className="h-3.5 w-3.5" />
            新建投标项目 <ArrowUpRight className="h-3.5 w-3.5" />
          </span>
        </Link>
      </div>

      {/* 统计卡片 */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {cards.map((s) => (
          <Card key={s.title}>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium text-slate-500">{s.title}</CardTitle>
              <div className={`rounded-lg p-2 ${s.bg}`}>
                <s.icon className={`h-4 w-4 ${s.color}`} />
              </div>
            </CardHeader>
            <CardContent>
              <div className="text-3xl font-bold">
                {loading ? <Loader2 className="h-6 w-6 animate-spin text-slate-300" /> : s.value}
              </div>
              <p className="text-xs text-slate-500">{s.desc}</p>
            </CardContent>
          </Card>
        ))}
      </div>
      {/* 智能待办提醒 */}
      {!loading && (
        <Card className="border-amber-100">
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <CalendarClock className="h-4 w-4 text-amber-600" />
              待办提醒
            </CardTitle>
          </CardHeader>
          <CardContent>
            {(() => {
              const reminders: { text: string; type: "urgent" | "warn" | "info"; href: string }[] = [];

              // 截止日倒计时
              projects.forEach((p) => {
                if (p.deadline && !["completed", "submitted", "won", "lost"].includes(p.status)) {
                  const deadlineDate = new Date(p.deadline);
                  const now = new Date();
                  const daysLeft = Math.ceil((deadlineDate.getTime() - now.getTime()) / (1000 * 60 * 60 * 24));
                  if (daysLeft <= 0) {
                    reminders.push({
                      text: `「${p.project_name}」已过截止日期`,
                      type: "urgent",
                      href: `/dashboard/bid-projects/${p.id}`,
                    });
                  } else if (daysLeft <= 3) {
                    reminders.push({
                      text: `「${p.project_name}」截止日期还剩 ${daysLeft} 天`,
                      type: "urgent",
                      href: `/dashboard/bid-projects/${p.id}`,
                    });
                  } else if (daysLeft <= 7) {
                    reminders.push({
                      text: `「${p.project_name}」截止日期还剩 ${daysLeft} 天`,
                      type: "warn",
                      href: `/dashboard/bid-projects/${p.id}`,
                    });
                  }
                }
              });

              // 草稿状态提醒
              const drafts = projects.filter((p) => p.status === "draft");
              if (drafts.length > 0) {
                reminders.push({
                  text: `${drafts.length} 个项目仍处于草稿状态，请上传招标文件并开始解析`,
                  type: "info",
                  href: "/dashboard/bid-projects",
                });
              }

              // AI 配额预警
              if ((stats?.in_progress ?? 0) > 0 && total > 0) {
                const progressRate = Math.round(((stats?.in_progress ?? 0) / total) * 100);
                if (progressRate > 60) {
                  reminders.push({
                    text: `${stats?.in_progress} 个项目正在进行中，注意 AI 配额消耗`,
                    type: "warn",
                    href: "/dashboard/billing",
                  });
                }
              }

              if (reminders.length === 0) {
                return (
                  <div className="flex items-center gap-2 py-2 text-sm text-slate-400">
                    <CheckCircle2 className="h-4 w-4 text-green-400" />
                    暂无紧急待办，一切顺利 🎉
                  </div>
                );
              }

              return (
                <div className="space-y-2">
                  {reminders.map((r, i) => (
                    <Link key={i} href={r.href}>
                      <div
                        className={`flex items-center gap-3 rounded-lg border px-3 py-2.5 text-sm transition-all hover:shadow-sm cursor-pointer ${
                          r.type === "urgent"
                            ? "border-red-200 bg-red-50 text-red-700"
                            : r.type === "warn"
                            ? "border-amber-200 bg-amber-50 text-amber-700"
                            : "border-blue-200 bg-blue-50 text-blue-700"
                        }`}
                      >
                        {r.type === "urgent" ? (
                          <AlertTriangle className="h-4 w-4 shrink-0" />
                        ) : r.type === "warn" ? (
                          <Clock className="h-4 w-4 shrink-0" />
                        ) : (
                          <Zap className="h-4 w-4 shrink-0" />
                        )}
                        <span className="flex-1">{r.text}</span>
                        <ArrowUpRight className="h-3.5 w-3.5 shrink-0 opacity-50" />
                      </div>
                    </Link>
                  ))}
                </div>
              );
            })()}
          </CardContent>
        </Card>
      )}

      {/* 最近项目 */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-base">最近投标项目</CardTitle>
          <Link href="/dashboard/bid-projects">
            <span className="text-xs text-slate-400 hover:text-slate-600 cursor-pointer">查看全部 →</span>
          </Link>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex justify-center py-8">
              <Loader2 className="h-6 w-6 animate-spin text-slate-300" />
            </div>
          ) : recentProjects.length > 0 ? (
            <div className="space-y-2.5">
              {recentProjects.map((p) => {
                const statusInfo = STATUS_MAP[p.status] || { label: p.status, color: "bg-slate-100 text-slate-500" };
                return (
                  <Link key={p.id} href={`/dashboard/bid-projects/${p.id}`}>
                    <div className="flex items-center justify-between rounded-lg border p-3.5 transition-all hover:bg-slate-50 hover:shadow-sm">
                      <div className="flex items-center gap-3">
                        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-50">
                          <FileText className="h-4 w-4 text-blue-600" />
                        </div>
                        <div>
                          <p className="text-sm font-medium">{p.project_name}</p>
                          <p className="text-xs text-slate-400">
                            {[
                              p.tender_org,
                              p.customer_type && CUSTOMER_LABELS[p.customer_type],
                              p.budget_amount && `${(p.budget_amount / 10000).toFixed(0)}万`,
                            ]
                              .filter(Boolean)
                              .join(" · ") || "—"}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-3">
                        {p.deadline && (
                          <span className="text-xs text-slate-400">截止: {p.deadline}</span>
                        )}
                        <Badge className={`text-xs ${statusInfo.color}`}>
                          {statusInfo.label}
                        </Badge>
                      </div>
                    </div>
                  </Link>
                );
              })}
            </div>
          ) : (
            <p className="py-8 text-center text-sm text-slate-400">
              暂无投标项目，点击右上角"新建投标项目"开始
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
