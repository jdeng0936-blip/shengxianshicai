"use client";

import { useState, useEffect, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Plus,
  FileText,
  Loader2,
  ClipboardList,
  Clock,
  DollarSign,
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

export default function BidProjectsPage() {
  const [projects, setProjects] = useState<BidProject[]>([]);
  const [loading, setLoading] = useState(true);

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

      {/* 项目列表 */}
      {loading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="h-8 w-8 animate-spin text-slate-400" />
        </div>
      ) : projects.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-20">
            <ClipboardList className="h-12 w-12 text-slate-300" />
            <p className="mt-4 text-slate-500">暂无投标项目</p>
            <Link href="/dashboard/bid-projects/new" className="mt-4">
              <Button variant="outline">
                <Plus className="mr-2 h-4 w-4" />
                创建第一个项目
              </Button>
            </Link>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {projects.map((p) => {
            const statusInfo = STATUS_MAP[p.status] || { label: p.status, variant: "secondary" as const };
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
