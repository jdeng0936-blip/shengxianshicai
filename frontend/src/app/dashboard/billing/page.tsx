"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Zap,
  FileText,
  Download,
  Bot,
  Crown,
  Loader2,
} from "lucide-react";
import api from "@/lib/api";

const PLAN_CONFIG = {
  free: { label: "免费版", color: "bg-slate-100 text-slate-600", icon: Zap },
  basic: { label: "基础版", color: "bg-blue-100 text-blue-700", icon: Zap },
  pro: { label: "专业版", color: "bg-purple-100 text-purple-700", icon: Crown },
  enterprise: { label: "企业版", color: "bg-amber-100 text-amber-700", icon: Crown },
};

interface QuotaItem {
  used: number;
  max: number;
}

interface UsageStats {
  plan_type: string;
  projects: QuotaItem;
  exports: QuotaItem;
  ai_calls: QuotaItem;
}

function ProgressBar({ used, max, label, icon: Icon }: { used: number; max: number; label: string; icon: any }) {
  const pct = max > 0 ? Math.min((used / max) * 100, 100) : 0;
  const isLow = pct > 80;

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm font-medium text-slate-700">
          <Icon className="h-4 w-4" />
          {label}
        </div>
        <span className={`text-sm font-bold ${isLow ? "text-red-600" : "text-slate-600"}`}>
          {used} / {max}
        </span>
      </div>
      <div className="h-2.5 overflow-hidden rounded-full bg-slate-100">
        <div
          className={`h-full rounded-full transition-all ${
            isLow ? "bg-red-500" : pct > 50 ? "bg-amber-500" : "bg-blue-500"
          }`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

export default function BillingPage() {
  const [stats, setStats] = useState<UsageStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchQuota = async () => {
      try {
        const res = await api.get("/billing/quota");
        setStats(res.data?.data || null);
      } catch {
        // API 不可用时使用默认值
        setStats({
          plan_type: "free",
          projects: { used: 0, max: 5 },
          exports: { used: 0, max: 10 },
          ai_calls: { used: 0, max: 100 },
        });
      } finally {
        setLoading(false);
      }
    };
    fetchQuota();
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-8 w-8 animate-spin text-slate-400" />
      </div>
    );
  }

  const plan = PLAN_CONFIG[stats?.plan_type as keyof typeof PLAN_CONFIG] || PLAN_CONFIG.free;
  const PlanIcon = plan.icon;

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold text-slate-800">计费中心</h2>

      {/* 当前套餐 */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <PlanIcon className="h-5 w-5" />
              当前套餐
            </CardTitle>
            <Badge className={plan.color}>{plan.label}</Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {stats && (
            <>
              <ProgressBar
                used={stats.projects.used}
                max={stats.projects.max}
                label="投标项目"
                icon={FileText}
              />
              <ProgressBar
                used={stats.exports.used}
                max={stats.exports.max}
                label="文档导出"
                icon={Download}
              />
              <ProgressBar
                used={stats.ai_calls.used}
                max={stats.ai_calls.max}
                label="AI 调用"
                icon={Bot}
              />
            </>
          )}
        </CardContent>
      </Card>

      {/* 套餐对比 */}
      <Card>
        <CardHeader>
          <CardTitle>套餐升级</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 md:grid-cols-3">
            {/* 基础版 */}
            <div className="rounded-lg border-2 border-blue-200 p-4">
              <div className="mb-2 text-lg font-bold text-blue-700">基础版</div>
              <div className="mb-4 text-2xl font-bold">
                ¥99<span className="text-sm text-slate-400">/月</span>
              </div>
              <ul className="space-y-2 text-sm text-slate-600">
                <li>20 个投标项目</li>
                <li>50 次文档导出</li>
                <li>500 次 AI 调用</li>
                <li>无水印导出</li>
              </ul>
              <Button className="mt-4 w-full" variant="outline">
                升级基础版
              </Button>
            </div>

            {/* 专业版 */}
            <div className="rounded-lg border-2 border-purple-300 bg-purple-50/30 p-4">
              <div className="mb-2 flex items-center gap-2">
                <span className="text-lg font-bold text-purple-700">专业版</span>
                <Badge className="bg-purple-100 text-purple-700">推荐</Badge>
              </div>
              <div className="mb-4 text-2xl font-bold">
                ¥299<span className="text-sm text-slate-400">/月</span>
              </div>
              <ul className="space-y-2 text-sm text-slate-600">
                <li>不限投标项目</li>
                <li>不限文档导出</li>
                <li>2000 次 AI 调用</li>
                <li>优先使用 DeepSeek Pro</li>
                <li>风险报告 + 合规检查</li>
              </ul>
              <Button className="mt-4 w-full">
                升级专业版
              </Button>
            </div>

            {/* 企业版 */}
            <div className="rounded-lg border-2 border-amber-200 p-4">
              <div className="mb-2 text-lg font-bold text-amber-700">企业版</div>
              <div className="mb-4 text-2xl font-bold">
                联系销售
              </div>
              <ul className="space-y-2 text-sm text-slate-600">
                <li>一切专业版功能</li>
                <li>私有化部署</li>
                <li>API 对接</li>
                <li>专属客户经理</li>
                <li>SLA 保障</li>
              </ul>
              <Button className="mt-4 w-full" variant="outline">
                联系我们
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
