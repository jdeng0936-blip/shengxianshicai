"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useParams } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  ArrowLeft,
  Upload,
  Loader2,
  FileText,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Clock,
  Sparkles,
  Trash2,
  ShieldCheck,
} from "lucide-react";
import Link from "next/link";
import api from "@/lib/api";
import RiskReportPanel from "@/components/business/risk-report-panel";

interface TenderRequirement {
  id: number;
  project_id: number;
  category: string;
  content: string;
  is_mandatory: boolean;
  score_weight?: number;
  max_score?: number;
  sort_order: number;
  compliance_status?: string;
  compliance_note?: string;
}

interface BidProject {
  id: number;
  project_name: string;
  enterprise_id?: number;
  tender_org?: string;
  customer_type?: string;
  tender_type?: string;
  deadline?: string;
  budget_amount?: number;
  bid_amount?: number;
  status: string;
  tender_doc_path?: string;
  bid_doc_path?: string;
  description?: string;
  delivery_scope?: string;
  delivery_period?: string;
  requirements: TenderRequirement[];
  chapters: any[];
}

const STATUS_MAP: Record<string, { label: string; color: string }> = {
  draft: { label: "草稿", color: "bg-slate-100 text-slate-600" },
  parsing: { label: "解析中...", color: "bg-blue-100 text-blue-700" },
  parsed: { label: "已解析", color: "bg-green-100 text-green-700" },
  generating: { label: "生成中...", color: "bg-blue-100 text-blue-700" },
  generated: { label: "已生成", color: "bg-green-100 text-green-700" },
  reviewing: { label: "审查中", color: "bg-yellow-100 text-yellow-700" },
  completed: { label: "已完成", color: "bg-green-100 text-green-700" },
  submitted: { label: "已投标", color: "bg-purple-100 text-purple-700" },
  won: { label: "已中标", color: "bg-emerald-100 text-emerald-700" },
  lost: { label: "未中标", color: "bg-red-100 text-red-600" },
  failed: { label: "失败", color: "bg-red-100 text-red-600" },
};

const CATEGORY_MAP: Record<string, { label: string; icon: any; color: string }> = {
  disqualification: { label: "废标项", icon: XCircle, color: "text-red-600" },
  qualification: { label: "资格要求", icon: CheckCircle2, color: "text-blue-600" },
  technical: { label: "技术要求", icon: FileText, color: "text-slate-600" },
  scoring: { label: "评分标准", icon: Sparkles, color: "text-amber-600" },
  commercial: { label: "商务要求", icon: Clock, color: "text-purple-600" },
};

export default function BidProjectDetailPage() {
  const params = useParams();
  const projectId = params.id as string;
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [project, setProject] = useState<BidProject | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [parsing, setParsing] = useState(false);
  const [activeTab, setActiveTab] = useState("disqualification");
  const [checking, setChecking] = useState(false);
  const [complianceResult, setComplianceResult] = useState<{
    total: number; passed: number; failed: number; warning: number;
    results: { id: number; category: string; content: string; status: string; note: string }[];
  } | null>(null);

  const fetchProject = useCallback(async () => {
    try {
      setLoading(true);
      const res = await api.get(`/bid-projects/${projectId}`);
      setProject(res.data?.data);
    } catch {
      setProject(null);
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    fetchProject();
  }, [fetchProject]);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      await api.post(`/bid-projects/${projectId}/upload-tender`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      await fetchProject();
    } catch (err: any) {
      alert(err.response?.data?.detail || "上传失败");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleParse = async () => {
    setParsing(true);
    try {
      await api.post(`/bid-projects/${projectId}/parse-tender`);
      await fetchProject();
    } catch (err: any) {
      alert(err.response?.data?.detail || "解析失败");
      await fetchProject();
    } finally {
      setParsing(false);
    }
  };

  const handleComplianceCheck = async () => {
    setChecking(true);
    try {
      const res = await api.post(`/bid-projects/${projectId}/compliance-check`);
      setComplianceResult(res.data?.data);
      await fetchProject();
    } catch (err: any) {
      alert(err.response?.data?.detail || "合规检查失败");
    } finally {
      setChecking(false);
    }
  };

  const handleDeleteRequirement = async (reqId: number) => {
    try {
      await api.delete(`/bid-projects/requirements/${reqId}`);
      await fetchProject();
    } catch {
      alert("删除失败");
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-8 w-8 animate-spin text-slate-400" />
      </div>
    );
  }

  if (!project) {
    return (
      <div className="text-center py-20 text-slate-500">投标项目不存在</div>
    );
  }

  const statusInfo = STATUS_MAP[project.status] || { label: project.status, color: "bg-slate-100" };
  const requirementsByCategory = project.requirements.reduce((acc, req) => {
    if (!acc[req.category]) acc[req.category] = [];
    acc[req.category].push(req);
    return acc;
  }, {} as Record<string, TenderRequirement[]>);

  return (
    <div className="space-y-6">
      {/* 页头 */}
      <div className="flex items-center gap-4">
        <Link href="/dashboard/bid-projects">
          <Button variant="ghost" size="icon">
            <ArrowLeft className="h-5 w-5" />
          </Button>
        </Link>
        <div className="flex-1">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-slate-900">{project.project_name}</h1>
            <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${statusInfo.color}`}>
              {statusInfo.label}
            </span>
          </div>
          <p className="mt-1 text-sm text-slate-500">
            {[project.tender_org, project.customer_type, project.deadline && `截止: ${project.deadline}`]
              .filter(Boolean)
              .join(" · ")}
          </p>
        </div>
      </div>

      {/* 项目概览 */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-5">
        <Card>
          <CardContent className="pt-4">
            <div className="text-sm text-slate-500">预算金额</div>
            <div className="mt-1 text-xl font-bold">
              {project.budget_amount ? `${(project.budget_amount / 10000).toFixed(1)} 万` : "—"}
            </div>
          </CardContent>
        </Card>
        <Link href={`/dashboard/bid-projects/${project.id}/enterprise`}>
          <Card className="cursor-pointer transition-shadow hover:shadow-md">
            <CardContent className="pt-4">
              <div className="text-sm text-slate-500">投标企业</div>
              <div className="mt-1 text-xl font-bold">
                {project.enterprise_id ? "已关联" : "未关联"}
              </div>
              <div className="mt-1 text-xs text-blue-500">
                {project.enterprise_id ? "查看/编辑企业信息 →" : "点击关联企业 →"}
              </div>
            </CardContent>
          </Card>
        </Link>
        <Card>
          <CardContent className="pt-4">
            <div className="text-sm text-slate-500">招标要求</div>
            <div className="mt-1 text-xl font-bold">{project.requirements.length} 条</div>
          </CardContent>
        </Card>
        <Link href={`/dashboard/bid-projects/${project.id}/chapters`}>
          <Card className="cursor-pointer transition-shadow hover:shadow-md">
            <CardContent className="pt-4">
              <div className="text-sm text-slate-500">投标章节</div>
              <div className="mt-1 text-xl font-bold">{project.chapters.length} 章</div>
              <div className="mt-1 text-xs text-blue-500">点击进入编辑 &rarr;</div>
            </CardContent>
          </Card>
        </Link>
        <Link href={`/dashboard/bid-projects/${project.id}/quotation`}>
          <Card className="cursor-pointer transition-shadow hover:shadow-md">
            <CardContent className="pt-4">
              <div className="text-sm text-slate-500">报价管理</div>
              <div className="mt-1 text-xl font-bold">
                {project.bid_amount ? `¥${(project.bid_amount / 10000).toFixed(1)}万` : "待报价"}
              </div>
              <div className="mt-1 text-xs text-blue-500">点击编辑报价 &rarr;</div>
            </CardContent>
          </Card>
        </Link>
      </div>

      {/* 合规检查 */}
      {project.requirements.length > 0 && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="flex items-center gap-2">
                <ShieldCheck className="h-5 w-5" />
                合规检查
              </CardTitle>
              <Button
                onClick={handleComplianceCheck}
                disabled={checking}
                variant={complianceResult ? "outline" : "default"}
              >
                {checking ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <ShieldCheck className="mr-2 h-4 w-4" />
                )}
                {checking ? "检查中..." : complianceResult ? "重新检查" : "开始合规检查"}
              </Button>
            </div>
          </CardHeader>
          {complianceResult && (
            <CardContent>
              {/* 汇总 */}
              <div className="mb-4 grid grid-cols-4 gap-3">
                <div className="rounded-lg bg-slate-50 p-3 text-center">
                  <div className="text-2xl font-bold">{complianceResult.total}</div>
                  <div className="text-xs text-slate-500">检查项</div>
                </div>
                <div className="rounded-lg bg-green-50 p-3 text-center">
                  <div className="text-2xl font-bold text-green-600">{complianceResult.passed}</div>
                  <div className="text-xs text-green-600">通过</div>
                </div>
                <div className="rounded-lg bg-red-50 p-3 text-center">
                  <div className="text-2xl font-bold text-red-600">{complianceResult.failed}</div>
                  <div className="text-xs text-red-600">不通过</div>
                </div>
                <div className="rounded-lg bg-amber-50 p-3 text-center">
                  <div className="text-2xl font-bold text-amber-600">{complianceResult.warning}</div>
                  <div className="text-xs text-amber-600">警告</div>
                </div>
              </div>

              {/* 问题清单（只显示 failed 和 warning） */}
              {complianceResult.results
                .filter((r) => r.status !== "passed")
                .map((r) => (
                  <div
                    key={r.id}
                    className={`mb-2 rounded-lg border p-3 ${
                      r.status === "failed"
                        ? "border-red-300 bg-red-50"
                        : "border-amber-300 bg-amber-50"
                    }`}
                  >
                    <div className="flex items-start gap-2">
                      {r.status === "failed" ? (
                        <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-red-500" />
                      ) : (
                        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />
                      )}
                      <div className="flex-1">
                        <div className="flex items-center gap-2">
                          <Badge
                            variant={r.status === "failed" ? "destructive" : "outline"}
                            className="text-xs"
                          >
                            {CATEGORY_MAP[r.category]?.label || r.category}
                          </Badge>
                          <span className="text-sm text-slate-700">{r.content}</span>
                        </div>
                        <p className={`mt-1 text-xs ${
                          r.status === "failed" ? "text-red-600 font-medium" : "text-amber-600"
                        }`}>
                          {r.note}
                        </p>
                      </div>
                    </div>
                  </div>
                ))}
              {complianceResult.failed === 0 && complianceResult.warning === 0 && (
                <div className="rounded-lg bg-green-50 p-4 text-center">
                  <CheckCircle2 className="mx-auto h-8 w-8 text-green-500" />
                  <p className="mt-2 text-sm font-medium text-green-700">全部检查通过！</p>
                </div>
              )}
            </CardContent>
          )}
        </Card>
      )}

      {/* 风险报告 */}
      <RiskReportPanel projectId={projectId} />

      {/* 招标文件上传 & 解析 */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FileText className="h-5 w-5" />
            招标文件
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-4">
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.docx,.doc"
              onChange={handleUpload}
              className="hidden"
            />
            <Button
              variant="outline"
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading}
            >
              {uploading ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Upload className="mr-2 h-4 w-4" />
              )}
              {project.tender_doc_path ? "重新上传" : "上传招标文件"}
            </Button>
            {project.tender_doc_path && (
              <>
                <span className="text-sm text-green-600">
                  <CheckCircle2 className="mr-1 inline h-4 w-4" />
                  已上传
                </span>
                <Button
                  onClick={handleParse}
                  disabled={parsing || project.status === "parsing"}
                >
                  {parsing || project.status === "parsing" ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <Sparkles className="mr-2 h-4 w-4" />
                  )}
                  AI 解析招标要求
                </Button>
              </>
            )}
          </div>
        </CardContent>
      </Card>

      {/* 解析结果 — 按类型分 Tab */}
      {project.requirements.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5" />
              招标要求（{project.requirements.length} 条）
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Tabs value={activeTab} onValueChange={setActiveTab}>
              <TabsList className="mb-4">
                {Object.entries(CATEGORY_MAP).map(([key, cat]) => {
                  const count = (requirementsByCategory[key] || []).length;
                  return (
                    <TabsTrigger key={key} value={key} className="gap-1.5">
                      <cat.icon className={`h-3.5 w-3.5 ${cat.color}`} />
                      {cat.label}
                      {count > 0 && (
                        <Badge variant="secondary" className="ml-1 h-5 px-1.5 text-xs">
                          {count}
                        </Badge>
                      )}
                    </TabsTrigger>
                  );
                })}
              </TabsList>
              {Object.entries(CATEGORY_MAP).map(([key, cat]) => (
                <TabsContent key={key} value={key} className="space-y-2">
                  {(requirementsByCategory[key] || []).length === 0 ? (
                    <p className="py-8 text-center text-sm text-slate-400">
                      暂无{cat.label}
                    </p>
                  ) : (
                    (requirementsByCategory[key] || []).map((req) => (
                      <div
                        key={req.id}
                        className={`flex items-start gap-3 rounded-lg border p-3 ${
                          key === "disqualification"
                            ? "border-red-200 bg-red-50"
                            : "border-slate-200"
                        }`}
                      >
                        <cat.icon className={`mt-0.5 h-4 w-4 shrink-0 ${cat.color}`} />
                        <div className="flex-1">
                          <p className="text-sm text-slate-800">{req.content}</p>
                          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-400">
                            {req.is_mandatory && <Badge variant="outline">必须</Badge>}
                            {req.max_score && <span>满分: {req.max_score}</span>}
                            {req.score_weight && <span>权重: {req.score_weight}%</span>}
                            {req.compliance_status === "passed" && (
                              <Badge className="bg-green-100 text-green-700 border-green-200">通过</Badge>
                            )}
                            {req.compliance_status === "failed" && (
                              <Badge variant="destructive">不通过</Badge>
                            )}
                            {req.compliance_status === "warning" && (
                              <Badge className="bg-amber-100 text-amber-700 border-amber-200">警告</Badge>
                            )}
                          </div>
                          {req.compliance_note && (
                            <p className={`mt-1 text-xs ${
                              req.compliance_status === "failed" ? "text-red-500" :
                              req.compliance_status === "warning" ? "text-amber-500" :
                              "text-green-500"
                            }`}>
                              {req.compliance_note}
                            </p>
                          )}
                        </div>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7 text-slate-400 hover:text-red-500"
                          onClick={() => handleDeleteRequirement(req.id)}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    ))
                  )}
                </TabsContent>
              ))}
            </Tabs>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
