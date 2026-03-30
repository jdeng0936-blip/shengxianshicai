"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { ArrowLeft, Loader2 } from "lucide-react";
import Link from "next/link";
import api from "@/lib/api";

export default function NewBidProjectPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({
    project_name: "",
    tender_org: "",
    customer_type: "",
    tender_type: "",
    deadline: "",
    budget_amount: "",
    delivery_scope: "",
    delivery_period: "",
    description: "",
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.project_name.trim()) return;

    setLoading(true);
    try {
      const payload = {
        ...form,
        budget_amount: form.budget_amount ? parseFloat(form.budget_amount) : undefined,
      };
      const res = await api.post("/bid-projects", payload);
      const project = res.data?.data;
      if (project?.id) {
        router.push(`/dashboard/bid-projects/${project.id}`);
      }
    } catch (err: any) {
      alert(err.response?.data?.detail || "创建失败");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Link href="/dashboard/bid-projects">
          <Button variant="ghost" size="icon">
            <ArrowLeft className="h-5 w-5" />
          </Button>
        </Link>
        <h1 className="text-2xl font-bold text-slate-900">新建投标项目</h1>
      </div>

      <form onSubmit={handleSubmit}>
        <Card>
          <CardHeader>
            <CardTitle>项目基本信息</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="project_name">招标项目名称 *</Label>
                <Input
                  id="project_name"
                  placeholder="如：XX学校2026年食材配送服务采购项目"
                  value={form.project_name}
                  onChange={(e) => setForm({ ...form, project_name: e.target.value })}
                  required
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="tender_org">招标方/采购方名称</Label>
                <Input
                  id="tender_org"
                  placeholder="如：XX市第一中学"
                  value={form.tender_org}
                  onChange={(e) => setForm({ ...form, tender_org: e.target.value })}
                />
              </div>
              <div className="space-y-2">
                <Label>客户类型</Label>
                <Select
                  value={form.customer_type}
                  onValueChange={(v) => setForm({ ...form, customer_type: v })}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="选择客户类型" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="school">学校食堂</SelectItem>
                    <SelectItem value="hospital">医院</SelectItem>
                    <SelectItem value="government">政府机关</SelectItem>
                    <SelectItem value="enterprise">企业食堂</SelectItem>
                    <SelectItem value="canteen">团餐公司</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>招标方式</Label>
                <Select
                  value={form.tender_type}
                  onValueChange={(v) => setForm({ ...form, tender_type: v })}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="选择招标方式" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="open">公开招标</SelectItem>
                    <SelectItem value="invite">邀请招标</SelectItem>
                    <SelectItem value="negotiate">竞争性谈判</SelectItem>
                    <SelectItem value="inquiry">询价</SelectItem>
                    <SelectItem value="single">单一来源</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="deadline">投标截止时间</Label>
                <Input
                  id="deadline"
                  type="datetime-local"
                  value={form.deadline}
                  onChange={(e) => setForm({ ...form, deadline: e.target.value })}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="budget_amount">预算金额（元）</Label>
                <Input
                  id="budget_amount"
                  type="number"
                  placeholder="如：500000"
                  value={form.budget_amount}
                  onChange={(e) => setForm({ ...form, budget_amount: e.target.value })}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="delivery_period">配送周期/合同期限</Label>
                <Input
                  id="delivery_period"
                  placeholder="如：1年（可续签）"
                  value={form.delivery_period}
                  onChange={(e) => setForm({ ...form, delivery_period: e.target.value })}
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="delivery_scope">配送范围描述</Label>
              <Textarea
                id="delivery_scope"
                placeholder="如：XX市城区范围内5所学校食堂，日均供餐3000人"
                value={form.delivery_scope}
                onChange={(e) => setForm({ ...form, delivery_scope: e.target.value })}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="description">备注说明</Label>
              <Textarea
                id="description"
                placeholder="其他补充信息..."
                value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
              />
            </div>
            <div className="flex justify-end gap-3 pt-4">
              <Link href="/dashboard/bid-projects">
                <Button variant="outline" type="button">取消</Button>
              </Link>
              <Button type="submit" disabled={loading || !form.project_name.trim()}>
                {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                创建项目
              </Button>
            </div>
          </CardContent>
        </Card>
      </form>
    </div>
  );
}
