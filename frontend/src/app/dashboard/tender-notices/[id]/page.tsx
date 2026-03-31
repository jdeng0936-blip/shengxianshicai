"use client";

import { useState, useEffect, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  ArrowLeft,
  ArrowUpRight,
  Loader2,
  RefreshCw,
  XCircle,
  CheckCircle2,
  AlertTriangle,
  ShieldCheck,
  Sparkles,
  Building2,
  Calendar,
  MapPin,
  Banknote,
  ClipboardCheck,
} from "lucide-react";
import Link from "next/link";
import api from "@/lib/api";

interface MatchAnalysis {
  match_score?: number;
  match_level?: string;
  summary?: string;
  strengths?: { item: string; detail: string }[];
  gaps?: { item: string; severity: string; detail: string; suggestion: string }[];
  risk_factors?: { factor: string; level: string; detail: string }[];
  recommendation?: string;
  estimated_win_probability?: string;
  preparation_checklist?: string[];
}

interface TenderNoticeDetail {
  id: number;
  title: string;
  buyer_name?: string;
  buyer_region?: string;
  customer_type?: string;
  tender_type?: string;
  budget_amount?: number;
  deadline?: string;
  publish_date?: string;
  delivery_scope?: string;
  content_summary?: string;
  match_score?: number;
  match_level?: string;
  match_analysis?: MatchAnalysis;
  capability_gaps?: any[];
  recommendation?: string;
  status: string;
  converted_project_id?: number;
  enterprise_id?: number;
}

const SEVERITY_MAP: Record<string, { label: string; color: string }> = {
  fatal: { label: "致命", color: "bg-red-100 text-red-700" },
  warning: { label: "警告", color: "bg-amber-100 text-amber-700" },
  minor: { label: "轻微", color: "bg-slate-100 text-slate-600" },
};

const CUSTOMER_LABELS: Record<string, string> = {
  school: "学校食堂", hospital: "医院", government: "政府机关",
  enterprise: "企业食堂", canteen: "团餐公司",
};

const TENDER_TYPE_LABELS: Record<string, string> = {
  open: "公开招标", invite: "邀请招标", negotiate: "竞争性谈判",
  inquiry: "询价", single: "单一来源",
};

export default function TenderNoticeDetailPage() {
  const params = useParams();
  const router = useRouter();
  const noticeId = params.id as string;

  const [notice, setNotice] = useState<TenderNoticeDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [analyzing, setAnalyzing] = useState(false);
  const [converting, setConverting] = useState(false);

  const fetchNotice = useCallback(async () => {
    try {
      setLoading(true);
      const res = await api.get(`/tender-notices/${noticeId}`);
      setNotice(res.data?.data || null);
    } catch {
      setNotice(null);
    } finally {
      setLoading(false);
    }
  }, [noticeId]);

  useEffect(() => { fetchNotice(); }, [fetchNotice]);

  const handleReanalyze = async () => {
    if (!notice?.enterprise_id) return;
    setAnalyzing(true);
    try {
      await api.post(`/tender-notices/${noticeId}/analyze?enterprise_id=${notice.enterprise_id}`);
      await fetchNotice();
    } catch (err: any) {
      alert(err.response?.data?.detail || "分析失败");
    } finally {
      setAnalyzing(false);
    }
  };

  const handleConvert = async () => {
    if (!notice?.enterprise_id) return;
    setConverting(true);
    try {
      const res = await api.post(`/tender-notices/${noticeId}/convert?enterprise_id=${notice.enterprise_id}`);
      const projectId = res.data?.data?.project_id;
      if (projectId) {
        router.push(`/dashboard/bid-projects/${projectId}`);
      }
    } catch (err: any) {
      alert(err.response?.data?.detail || "转化失败");
    } finally {
      setConverting(false);
    }
  };

  const handleDismiss = async () => {
    try {
      await api.post(`/tender-notices/${noticeId}/dismiss`);
      router.push("/dashboard/tender-notices");
    } catch { /* ignore */ }
  };

  if (loading) {
    return <div className="flex items-center justify-center py-20"><Loader2 className="h-8 w-8 animate-spin text-slate-400" /></div>;
  }
  if (!notice) {
    return <div className="py-20 text-center text-slate-500">商机不存在</div>;
  }

  const analysis = notice.match_analysis;
  const scoreColor = (notice.match_score ?? 0) >= 70 ? "text-green-600" : (notice.match_score ?? 0) >= 40 ? "text-amber-600" : "text-red-600";

  return (
    <div className="space-y-6">
      {/* 页头 */}
      <div className="flex items-center gap-4">
        <Link href="/dashboard/tender-notices">
          <Button variant="ghost" size="icon"><ArrowLeft className="h-5 w-5" /></Button>
        </Link>
        <div className="flex-1 min-w-0">
          <h1 className="text-xl font-bold text-slate-900 truncate">{notice.title}</h1>
          <div className="mt-1 flex items-center gap-3 text-sm text-slate-500">
            {notice.buyer_name && <span className="flex items-center gap-1"><Building2 className="h-3.5 w-3.5" />{notice.buyer_name}</span>}
            {notice.buyer_region && <span className="flex items-center gap-1"><MapPin className="h-3.5 w-3.5" />{notice.buyer_region}</span>}
          </div>
        </div>
        {/* 匹配分数 */}
        {notice.match_score != null && (
          <div className="text-center">
            <div className={`text-4xl font-bold ${scoreColor}`}>{notice.match_score}</div>
            <div className="text-xs text-slate-500">匹配分</div>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* 左栏：详情 + 分析 */}
        <div className="space-y-6 lg:col-span-2">
          {/* 基本信息 */}
          <Card>
            <CardHeader><CardTitle>公告信息</CardTitle></CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 gap-4 text-sm md:grid-cols-4">
                <div>
                  <span className="text-slate-500">客户类型</span>
                  <p className="font-medium">{CUSTOMER_LABELS[notice.customer_type || ""] || "未知"}</p>
                </div>
                <div>
                  <span className="text-slate-500">招标方式</span>
                  <p className="font-medium">{TENDER_TYPE_LABELS[notice.tender_type || ""] || "未知"}</p>
                </div>
                <div>
                  <span className="text-slate-500">预算金额</span>
                  <p className="font-medium">{notice.budget_amount ? `${(notice.budget_amount / 10000).toFixed(1)} 万元` : "未知"}</p>
                </div>
                <div>
                  <span className="text-slate-500">投标截止</span>
                  <p className="font-medium">{notice.deadline || "未知"}</p>
                </div>
              </div>
              {notice.delivery_scope && (
                <div className="mt-4"><span className="text-sm text-slate-500">配送范围</span><p className="mt-1 text-sm">{notice.delivery_scope}</p></div>
              )}
              {notice.content_summary && (
                <div className="mt-4"><span className="text-sm text-slate-500">公告摘要</span><p className="mt-1 text-sm text-slate-700 whitespace-pre-wrap">{notice.content_summary}</p></div>
              )}
            </CardContent>
          </Card>

          {/* AI 分析 */}
          {analysis && (
            <>
              {/* 综合建议 */}
              <Card className="border-blue-200">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2"><Sparkles className="h-5 w-5 text-blue-500" />AI 投标建议</CardTitle>
                </CardHeader>
                <CardContent>
                  {analysis.summary && <p className="mb-3 font-medium text-slate-800">{analysis.summary}</p>}
                  {analysis.recommendation && <p className="text-sm text-slate-600">{analysis.recommendation}</p>}
                </CardContent>
              </Card>

              {/* 优势 */}
              {analysis.strengths && analysis.strengths.length > 0 && (
                <Card>
                  <CardHeader><CardTitle className="flex items-center gap-2 text-green-700"><CheckCircle2 className="h-5 w-5" />竞争优势（{analysis.strengths.length} 项）</CardTitle></CardHeader>
                  <CardContent className="space-y-2">
                    {analysis.strengths.map((s, i) => (
                      <div key={i} className="rounded-lg border border-green-200 bg-green-50 p-3">
                        <p className="text-sm font-medium text-green-800">{s.item}</p>
                        <p className="mt-1 text-xs text-green-600">{s.detail}</p>
                      </div>
                    ))}
                  </CardContent>
                </Card>
              )}

              {/* 缺口 */}
              {analysis.gaps && analysis.gaps.length > 0 && (
                <Card>
                  <CardHeader><CardTitle className="flex items-center gap-2 text-red-700"><AlertTriangle className="h-5 w-5" />能力缺口（{analysis.gaps.length} 项）</CardTitle></CardHeader>
                  <CardContent className="space-y-2">
                    {analysis.gaps.map((g, i) => {
                      const sev = SEVERITY_MAP[g.severity] || SEVERITY_MAP.minor;
                      return (
                        <div key={i} className={`rounded-lg border p-3 ${g.severity === "fatal" ? "border-red-300 bg-red-50" : "border-amber-200 bg-amber-50"}`}>
                          <div className="flex items-center gap-2">
                            <Badge className={sev.color}>{sev.label}</Badge>
                            <span className="text-sm font-medium">{g.item}</span>
                          </div>
                          <p className="mt-1 text-xs text-slate-600">{g.detail}</p>
                          {g.suggestion && <p className="mt-1 text-xs text-blue-600">建议：{g.suggestion}</p>}
                        </div>
                      );
                    })}
                  </CardContent>
                </Card>
              )}

              {/* 准备清单 */}
              {analysis.preparation_checklist && analysis.preparation_checklist.length > 0 && (
                <Card>
                  <CardHeader><CardTitle className="flex items-center gap-2"><ClipboardCheck className="h-5 w-5" />投标准备清单</CardTitle></CardHeader>
                  <CardContent>
                    <ul className="space-y-2">
                      {analysis.preparation_checklist.map((item, i) => (
                        <li key={i} className="flex items-start gap-2 text-sm">
                          <span className="mt-0.5 h-5 w-5 shrink-0 rounded-full bg-blue-100 text-center text-xs font-medium text-blue-700 leading-5">{i + 1}</span>
                          {item}
                        </li>
                      ))}
                    </ul>
                  </CardContent>
                </Card>
              )}
            </>
          )}
        </div>

        {/* 右栏：操作 */}
        <div className="space-y-4">
          <Card>
            <CardHeader><CardTitle>操作</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              {notice.status === "converted" && notice.converted_project_id ? (
                <Link href={`/dashboard/bid-projects/${notice.converted_project_id}`}>
                  <Button className="w-full gap-2">
                    <ArrowUpRight className="h-4 w-4" />
                    查看投标项目
                  </Button>
                </Link>
              ) : notice.status !== "dismissed" ? (
                <>
                  <Button className="w-full gap-2" onClick={handleConvert} disabled={converting || !notice.enterprise_id}>
                    {converting ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowUpRight className="h-4 w-4" />}
                    转为投标项目
                  </Button>
                  <Button variant="outline" className="w-full gap-2" onClick={handleReanalyze} disabled={analyzing || !notice.enterprise_id}>
                    {analyzing ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                    重新分析
                  </Button>
                  <Button variant="ghost" className="w-full gap-2 text-slate-400" onClick={handleDismiss}>
                    <XCircle className="h-4 w-4" />
                    忽略此商机
                  </Button>
                </>
              ) : (
                <p className="text-center text-sm text-slate-400">此商机已忽略</p>
              )}
            </CardContent>
          </Card>

          {/* 风险因素 */}
          {analysis?.risk_factors && analysis.risk_factors.length > 0 && (
            <Card className="border-amber-200">
              <CardHeader><CardTitle className="text-sm flex items-center gap-2"><ShieldCheck className="h-4 w-4 text-amber-500" />风险因素</CardTitle></CardHeader>
              <CardContent className="space-y-2">
                {analysis.risk_factors.map((r, i) => (
                  <div key={i} className="text-xs">
                    <span className={`font-medium ${r.level === "high" ? "text-red-600" : r.level === "medium" ? "text-amber-600" : "text-slate-600"}`}>
                      [{r.level === "high" ? "高" : r.level === "medium" ? "中" : "低"}] {r.factor}
                    </span>
                    <p className="text-slate-500">{r.detail}</p>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
