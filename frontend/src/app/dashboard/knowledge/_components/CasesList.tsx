"use client";

import { useState, useEffect, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  BookOpen,
  Plus,
  Trash2,
  Loader2,
} from "lucide-react";
import api from "@/lib/api";

interface Case {
  id: number;
  title: string;
  buyer_name?: string;
  discount_rate?: string;
  customer_type?: string;
  summary?: string;
}

interface CasesListProps {
  search: string;
  showCreate: boolean;
  setShowCreate: (show: boolean) => void;
}

export default function CasesList({ search, showCreate, setShowCreate }: CasesListProps) {
  const [cases, setCases] = useState<Case[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [caseForm, setCaseForm] = useState({
    title: "", buyer_name: "", bid_amount: "", discount_rate: "", customer_type: "", summary: "",
  });

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get("/knowledge/cases");
      setCases(res.data?.data || []);
    } catch { setCases([]); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const createCase = async () => {
    if (!caseForm.title.trim()) { alert("案例标题不能为空"); return; }
    setCreating(true);
    try {
      const payload: Record<string, any> = { title: caseForm.title.trim() };
      if (caseForm.buyer_name.trim()) payload.buyer_name = caseForm.buyer_name.trim();
      if (caseForm.discount_rate.trim()) payload.discount_rate = caseForm.discount_rate.trim();
      if (caseForm.customer_type.trim()) payload.customer_type = caseForm.customer_type.trim();
      if (caseForm.summary.trim()) payload.summary = caseForm.summary.trim();
      await api.post("/knowledge/cases", payload);
      setCaseForm({ title: "", buyer_name: "", bid_amount: "", discount_rate: "", customer_type: "", summary: "" });
      setShowCreate(false);
      fetchData();
    } catch (e: any) {
      const detail = e.response?.data?.detail;
      alert("创建失败: " + (typeof detail === "string" ? detail : JSON.stringify(detail)));
    } finally { setCreating(false); }
  };

  const handleDelete = async (id: number) => {
    if (!confirm("确认删除？")) return;
    try { await api.delete(`/knowledge/cases/${id}`); fetchData(); }
    catch (e: any) { alert("删除失败: " + (e.response?.data?.detail || e.message)); }
  };

  if (loading) {
    return <div className="flex items-center justify-center py-20"><Loader2 className="h-8 w-8 animate-spin text-slate-300" /></div>;
  }

  return (
    <>
      {showCreate && (
        <Card className="border-blue-200 bg-blue-50/50">
          <CardContent className="space-y-3 pt-4">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="mb-1 block text-xs font-medium">案例标题 <span className="text-red-500">*</span></label>
                <Input value={caseForm.title} onChange={(e) => setCaseForm({ ...caseForm, title: e.target.value })} placeholder="如：XX市第一中学食材配送项目" />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium">采购方</label>
                <Input value={caseForm.buyer_name} onChange={(e) => setCaseForm({ ...caseForm, buyer_name: e.target.value })} placeholder="采购方名称" />
              </div>
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className="mb-1 block text-xs font-medium">客户类型</label>
                <Input value={caseForm.customer_type} onChange={(e) => setCaseForm({ ...caseForm, customer_type: e.target.value })} placeholder="school/hospital/government" />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium">中标金额</label>
                <Input value={caseForm.bid_amount} onChange={(e) => setCaseForm({ ...caseForm, bid_amount: e.target.value })} placeholder="如：50万" />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium">摘要</label>
                <Input value={caseForm.summary} onChange={(e) => setCaseForm({ ...caseForm, summary: e.target.value })} placeholder="案例简述" />
              </div>
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="outline" size="sm" onClick={() => setShowCreate(false)}>取消</Button>
              <Button size="sm" onClick={createCase} disabled={creating}>
                {creating && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}创建案例
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {cases.length === 0 ? (
        <Card className="flex h-40 items-center justify-center">
          <div className="text-center text-slate-400">
            <BookOpen className="mx-auto mb-2 h-10 w-10 opacity-30" />
            <p className="text-sm">暂无案例，点击「新增」录入</p>
          </div>
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {cases.filter((c) => !search || c.title.includes(search)).map((c) => (
            <Card key={c.id}>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center justify-between text-base">
                  <span className="flex items-center gap-2"><BookOpen className="h-4 w-4 text-blue-500" /> {c.title}</span>
                  <Button variant="ghost" size="sm" onClick={() => handleDelete(c.id)}><Trash2 className="h-3.5 w-3.5 text-red-400" /></Button>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="mb-2 grid grid-cols-3 gap-2 text-xs text-slate-500">
                  <div>采购方：<span className="font-medium text-slate-700">{c.buyer_name || "—"}</span></div>
                  <div>客户：<span className="font-medium text-slate-700">{c.customer_type || "—"}</span></div>
                  <div>下浮率：<span className="font-medium text-slate-700">{c.discount_rate || "—"}</span></div>
                </div>
                <p className="text-sm text-slate-600">{c.summary || "暂无摘要"}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </>
  );
}
