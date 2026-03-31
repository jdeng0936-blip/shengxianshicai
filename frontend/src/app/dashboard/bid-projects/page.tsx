"use client";

import { useState, useEffect, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  Plus,
  FileText,
  Loader2,
  ClipboardList,
  Clock,
  DollarSign,
  Search,
  ArrowRight,
  Upload,
  Sparkles,
  BookCheck,
  Download,
} from "lucide-react";
import Link from "next/link";
import api from "@/lib/api";

interface BidProject {
  id: number;
  project_name: string;
  tender_org?: string;
  customer_type?: string;
  tender_type?: string;
  deadline?: string;
  budget_amount?: number;
  bid_amount?: number;
  status: string;
  tender_doc_path?: string;
  created_at?: string;
  updated_at?: string;
}

const STATUS_MAP: Record<string, { label: string; variant: "default" | "secondary" | "destructive" | "outline" }> = {
  draft: { label: "草稿", variant: "secondary" },
  parsing: { label: "解析中", variant: "outline" },
  parsed: { label: "已解析", variant: "default" },
  generating: { label: "生成中", variant: "outline" },
  generated: { label: "已生成", variant: "default" },
  reviewing: { label: "审查中", variant: "outline" },
  completed: { label: "已完成", variant: "default" },
  submitted: { label: "已投标", variant: "default" },
  won: { label: "已中标", variant: "default" },
  lost: { label: "未中标", variant: "destructive" },
  failed: { label: "失败", variant: "destructive" },
};

const CUSTOMER_TYPE_MAP: Record<string, string> = {
  school: "学校食堂",
  hospital: "医院",
  government: "政府机关",
  enterprise: "企业食堂",
  canteen: "团餐公司",
};

/** 根据项目状态计算下一步操作引导 */
function getNextStep(p: BidProject): { text: string; icon: any; color: string } | null {
  switch (p.status) {
    case "draft":
      return p.tender_doc_path
        ? { text: "下一步：AI 解析招标要求", icon: Sparkles, color: "text-purple-500" }
        : { text: "下一步：上传招标文件", icon: Upload, color: "text-blue-500" };
    case "parsed":
      return { text: "下一步：生成投标章节", icon: Sparkles, color: "text-purple-500" };
    case "generated":
      return { text: "下一步：审阅章节并合规检查", icon: BookCheck, color: "text-amber-500" };
    case "reviewing":
      return { text: "下一步：导出 Word 文件", icon: Download, color: "text-green-600" };
    default:
      return null;
  }
}

const STATUS_FILTER_OPTIONS = [
  { value: "all", label: "全部" },
  { value: "active", label: "进行中" },
  { value: "completed", label: "已完成" },
];

export default function BidProjectsPage() {
  const [projects, setProjects] = useState<BidProject[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");

  const fetchProjects = useCallback(async () => {
    try {
      setLoading(true);
      const res = await api.get("/bid-projects");
      const data = res.data?.data;
      setProjects(Array.isArray(data) ? data : []);
    } catch {
      setProjects([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchProjects();
  }, [fetchProjects]);

  // 筛选逻辑
  const filteredProjects = projects.filter((p) => {
    // 搜索过滤
    if (search) {
      const q = search.toLowerCase();
      const matchName = p.project_name.toLowerCase().includes(q);
      const matchOrg = p.tender_org?.toLowerCase().includes(q);
      if (!matchName && !matchOrg) return false;
    }
    // 状态过滤
    if (statusFilter === "active") {
      return ["draft", "parsing", "parsed", "generating", "generated", "reviewing"].includes(p.status);
    }
    if (statusFilter === "completed") {
      return ["completed", "submitted", "won", "lost", "failed"].includes(p.status);
    }
    return true;
  });

  return (
    <div className="space-y-6">
      {/* 页头 */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">投标项目</h1>
          <p className="mt-1 text-sm text-slate-500">
            管理所有投标项目，上传招标文件并生成投标方案
          </p>
        </div>
        <Link href="/dashboard/bid-projects/new">
          <Button>
            <Plus className="mr-2 h-4 w-4" />
            新建项目
          </Button>
        </Link>
      </div>

      {/* 搜索 + 筛选 */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <Input
            className="pl-10"
            placeholder="搜索项目名称或采购方..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <div className="flex gap-1 rounded-lg border bg-slate-100 p-1">
          {STATUS_FILTER_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              className={`rounded-md px-3 py-1.5 text-sm transition-colors ${
                statusFilter === opt.value
                  ? "bg-white font-medium shadow-sm"
                  : "text-slate-500 hover:text-slate-700"
              }`}
              onClick={() => setStatusFilter(opt.value)}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {/* 项目列表 */}
      {loading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="h-8 w-8 animate-spin text-slate-400" />
        </div>
      ) : filteredProjects.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-20">
            <ClipboardList className="h-12 w-12 text-slate-300" />
            <p className="mt-4 text-slate-500">
              {search || statusFilter !== "all" ? "没有匹配的项目" : "暂无投标项目"}
            </p>
            {!search && statusFilter === "all" && (
              <Link href="/dashboard/bid-projects/new" className="mt-4">
                <Button variant="outline">
                  <Plus className="mr-2 h-4 w-4" />
                  创建第一个项目
                </Button>
              </Link>
            )}
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {filteredProjects.map((p) => {
            const statusInfo = STATUS_MAP[p.status] || { label: p.status, variant: "secondary" as const };
            const nextStep = getNextStep(p);
            return (
              <Link key={p.id} href={`/dashboard/bid-projects/${p.id}`}>
                <Card className="cursor-pointer transition-shadow hover:shadow-md">
                  <CardHeader className="pb-3">
                    <div className="flex items-start justify-between">
                      <CardTitle className="line-clamp-2 text-base">
                        {p.project_name}
                      </CardTitle>
                      <Badge variant={statusInfo.variant}>{statusInfo.label}</Badge>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-2 text-sm text-slate-500">
                    {p.tender_org && (
                      <div className="flex items-center gap-2">
                        <FileText className="h-4 w-4" />
                        <span className="truncate">{p.tender_org}</span>
                      </div>
                    )}
                    {p.customer_type && (
                      <div className="flex items-center gap-2">
                        <ClipboardList className="h-4 w-4" />
                        <span>{CUSTOMER_TYPE_MAP[p.customer_type] || p.customer_type}</span>
                      </div>
                    )}
                    {p.budget_amount && (
                      <div className="flex items-center gap-2">
                        <DollarSign className="h-4 w-4" />
                        <span>{(p.budget_amount / 10000).toFixed(1)} 万元</span>
                      </div>
                    )}
                    {p.deadline && (
                      <div className="flex items-center gap-2">
                        <Clock className="h-4 w-4" />
                        <span>截止: {p.deadline}</span>
                      </div>
                    )}

                    {/* 下一步操作引导 */}
                    {nextStep && (
                      <div className={`mt-2 flex items-center gap-2 rounded-md border border-dashed px-2.5 py-1.5 text-xs font-medium ${nextStep.color}`}>
                        <nextStep.icon className="h-3.5 w-3.5" />
                        <span className="flex-1">{nextStep.text}</span>
                        <ArrowRight className="h-3 w-3 opacity-50" />
                      </div>
                    )}
                  </CardContent>
                </Card>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
