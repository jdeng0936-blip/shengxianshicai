"use client";

import { useParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import RiskReportPanel from "@/components/business/risk-report-panel";

export default function RiskReportPage() {
  const params = useParams();
  const projectId = params.id as string;

  return (
    <div className="space-y-4">
      {/* 页头 */}
      <div className="flex items-center gap-4">
        <Link href={`/dashboard/bid-projects/${projectId}`}>
          <Button variant="ghost" size="icon">
            <ArrowLeft className="h-5 w-5" />
          </Button>
        </Link>
        <h1 className="text-xl font-bold text-slate-900">投标文件风险检查</h1>
      </div>

      {/* 风险报告面板 — 自动触发检查 */}
      <RiskReportPanel projectId={projectId} autoCheck />
    </div>
  );
}
