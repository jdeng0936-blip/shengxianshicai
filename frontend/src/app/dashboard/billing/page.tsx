"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Zap,
  FileText,
  Crown,
  Loader2,
  CheckCircle2,
  Clock,
  ShoppingCart,
  Receipt,
} from "lucide-react";
import { toast } from "sonner";
import Link from "next/link";
import api from "@/lib/api";

const PLAN_CONFIG: Record<string, { label: string; color: string; icon: any }> = {
  free_trial: { label: "免费试用", color: "bg-slate-100 text-slate-600", icon: Zap },
  per_document: { label: "按篇付费", color: "bg-blue-100 text-blue-700", icon: FileText },
  quarterly: { label: "季度包", color: "bg-purple-100 text-purple-700", icon: Crown },
  yearly: { label: "年度包", color: "bg-amber-100 text-amber-700", icon: Crown },
};

interface SubscriptionInfo {
  plan_type: string;
  remaining_quota: number;
  is_active: boolean;
  total_quota: number;
  used_count: number;
  end_date: string | null;
}

const PRICING = [
  {
    type: "per_document",
    label: "按篇付费",
    price: "¥199",
    unit: "/篇",
    features: ["单篇投标文件生成", "含风险报告", "无水印导出", "即买即用"],
    recommended: false,
    color: "border-blue-200",
  },
  {
    type: "quarterly",
    label: "季度包",
    price: "¥999",
    unit: "/季度",
    features: ["10篇投标文件", "含风险报告", "无水印导出", "有效期90天", "平均¥99.9/篇"],
    recommended: true,
    color: "border-purple-300 bg-purple-50/30",
  },
  {
    type: "yearly",
    label: "年度包",
    price: "¥2988",
    unit: "/年",
    features: ["不限篇数", "含风险报告", "无水印导出", "有效期365天", "优先技术支持"],
    recommended: false,
    color: "border-amber-200",
  },
];

export default function BillingPage() {
  const [subscription, setSubscription] = useState<SubscriptionInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [ordering, setOrdering] = useState<string | null>(null);

  useEffect(() => {
    const fetchSubscription = async () => {
      try {
        const res = await api.get("/subscriptions/current");
        setSubscription(res.data?.data || null);
      } catch {
        setSubscription({
          plan_type: "free_trial",
          remaining_quota: 1,
          is_active: true,
          total_quota: 1,
          used_count: 0,
          end_date: null,
        });
      } finally {
        setLoading(false);
      }
    };
    fetchSubscription();
  }, []);

  const handleOrder = async (orderType: string) => {
    setOrdering(orderType);
    try {
      const res = await api.post("/payments/create-order", {
        order_type: orderType,
        payment_method: "manual",
      });
      const data = res.data?.data;
      toast.success("订单创建成功", {
        description: `订单号: ${data.order_no}  金额: ¥${data.amount}\n请联系管理员完成付款确认。`,
        duration: 8000,
      });
      // 刷新订阅状态
      const subRes = await api.get("/subscriptions/current");
      setSubscription(subRes.data?.data || null);
    } catch (err: any) {
      toast.error(err.response?.data?.detail || "创建订单失败");
    } finally {
      setOrdering(null);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-8 w-8 animate-spin text-slate-400" />
      </div>
    );
  }

  const plan = PLAN_CONFIG[subscription?.plan_type || "free_trial"] || PLAN_CONFIG.free_trial;
  const PlanIcon = plan.icon;
  const quotaDisplay = subscription?.plan_type === "yearly"
    ? "不限"
    : `${subscription?.remaining_quota ?? 0} 篇`;

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold text-slate-800">计费中心</h2>

      {/* 当前订阅状态 */}
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
        <CardContent>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
            {/* 剩余配额 */}
            <div className="rounded-lg bg-blue-50 p-4 text-center">
              <div className="text-2xl font-bold text-blue-700">{quotaDisplay}</div>
              <div className="text-xs text-blue-600">剩余配额</div>
            </div>
            {/* 已使用 */}
            <div className="rounded-lg bg-slate-50 p-4 text-center">
              <div className="text-2xl font-bold">{subscription?.used_count ?? 0}</div>
              <div className="text-xs text-slate-500">已使用</div>
            </div>
            {/* 总配额 */}
            <div className="rounded-lg bg-slate-50 p-4 text-center">
              <div className="text-2xl font-bold">
                {subscription?.plan_type === "yearly" ? "不限" : subscription?.total_quota ?? 0}
              </div>
              <div className="text-xs text-slate-500">总配额</div>
            </div>
            {/* 到期时间 */}
            <div className="rounded-lg bg-slate-50 p-4 text-center">
              <div className="flex items-center justify-center gap-1">
                <Clock className="h-4 w-4 text-slate-400" />
                <span className="text-sm font-medium text-slate-600">
                  {subscription?.end_date
                    ? new Date(subscription.end_date).toLocaleDateString("zh-CN")
                    : "永久"}
                </span>
              </div>
              <div className="text-xs text-slate-500">到期时间</div>
            </div>
          </div>

          {/* 活跃状态提示 */}
          {subscription && !subscription.is_active && (
            <div className="mt-3 rounded-lg bg-red-50 p-3 text-center text-sm text-red-600">
              配额已用完或已过期，请续费以继续使用
            </div>
          )}
          {subscription?.plan_type === "free_trial" && subscription.is_active && (
            <div className="mt-3 rounded-lg bg-amber-50 p-3 text-center text-sm text-amber-700">
              免费试用仅含 1 篇带水印文档，升级后解锁无水印导出
            </div>
          )}
        </CardContent>
      </Card>

      {/* 套餐选择 */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ShoppingCart className="h-5 w-5" />
            选择套餐
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 md:grid-cols-3">
            {PRICING.map((pkg) => (
              <div
                key={pkg.type}
                className={`rounded-lg border-2 p-5 ${pkg.color}`}
              >
                <div className="mb-2 flex items-center gap-2">
                  <span className="text-lg font-bold">{pkg.label}</span>
                  {pkg.recommended && (
                    <Badge className="bg-purple-100 text-purple-700">推荐</Badge>
                  )}
                </div>
                <div className="mb-4">
                  <span className="text-3xl font-bold">{pkg.price}</span>
                  <span className="text-sm text-slate-400">{pkg.unit}</span>
                </div>
                <ul className="mb-4 space-y-2 text-sm text-slate-600">
                  {pkg.features.map((f, i) => (
                    <li key={i} className="flex items-center gap-2">
                      <CheckCircle2 className="h-3.5 w-3.5 text-green-500" />
                      {f}
                    </li>
                  ))}
                </ul>
                <Button
                  className="w-full"
                  variant={pkg.recommended ? "default" : "outline"}
                  disabled={ordering === pkg.type}
                  onClick={() => handleOrder(pkg.type)}
                >
                  {ordering === pkg.type ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : null}
                  {ordering === pkg.type ? "创建订单中..." : `购买${pkg.label}`}
                </Button>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* 订单记录入口 */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-slate-600">
              <Receipt className="h-5 w-5" />
              <span>查看历史订单和支付记录</span>
            </div>
            <Link href="/dashboard/billing/payment">
              <Button variant="outline">订单管理</Button>
            </Link>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
