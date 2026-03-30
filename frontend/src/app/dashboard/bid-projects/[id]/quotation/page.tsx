"use client";

import { useState, useEffect, useCallback } from "react";
import { useParams } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  ArrowLeft,
  Loader2,
  Plus,
  Trash2,
  Save,
  Zap,
  Calculator,
} from "lucide-react";
import Link from "next/link";
import api from "@/lib/api";

interface QuotationItem {
  id: number;
  sheet_id: number;
  category: string;
  item_name: string;
  spec?: string;
  unit?: string;
  market_ref_price?: number;
  unit_price?: number;
  quantity?: number;
  amount?: number;
  sort_order: number;
}

interface QuotationSheet {
  id: number;
  project_id: number;
  version: number;
  discount_rate?: number;
  total_amount?: number;
  budget_amount?: number;
  pricing_method?: string;
  remarks?: string;
  items: QuotationItem[];
  created_at?: string;
}

const CATEGORY_LABELS: Record<string, string> = {
  vegetable: "蔬菜类",
  meat: "肉类",
  seafood: "水产类",
  egg_poultry: "蛋禽类",
  dry_goods: "干货类",
  condiment: "调料类",
};

const CATEGORY_COLORS: Record<string, string> = {
  vegetable: "bg-green-100 text-green-700",
  meat: "bg-red-100 text-red-700",
  seafood: "bg-blue-100 text-blue-700",
  egg_poultry: "bg-amber-100 text-amber-700",
  dry_goods: "bg-orange-100 text-orange-700",
  condiment: "bg-purple-100 text-purple-700",
};

export default function QuotationPage() {
  const params = useParams();
  const projectId = params.id as string;

  const [sheet, setSheet] = useState<QuotationSheet | null>(null);
  const [loading, setLoading] = useState(true);
  const [initializing, setInitializing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [discountInput, setDiscountInput] = useState("");
  const [editedItems, setEditedItems] = useState<Record<number, Partial<QuotationItem>>>({});

  const fetchSheet = useCallback(async () => {
    try {
      setLoading(true);
      const res = await api.get(`/quotations/project/${projectId}`);
      const sheets = res.data?.data || [];
      if (sheets.length > 0) {
        setSheet(sheets[0]); // 最新版本
        setDiscountInput(
          sheets[0].discount_rate ? (sheets[0].discount_rate * 100).toFixed(1) : "10.0"
        );
      } else {
        setSheet(null);
      }
    } catch {
      setSheet(null);
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    fetchSheet();
  }, [fetchSheet]);

  const handleInit = async () => {
    setInitializing(true);
    try {
      const rate = parseFloat(discountInput) / 100;
      await api.post(
        `/bid-projects/${projectId}/init-quotation?discount_rate=${rate}`
      );
      await fetchSheet();
    } catch (err: any) {
      alert(err.response?.data?.detail || "初始化失败");
    } finally {
      setInitializing(false);
    }
  };

  const handleItemChange = (itemId: number, field: string, value: string) => {
    setEditedItems((prev) => ({
      ...prev,
      [itemId]: { ...prev[itemId], [field]: value },
    }));
  };

  const handleSaveItem = async (itemId: number) => {
    const edits = editedItems[itemId];
    if (!edits) return;

    setSaving(true);
    try {
      const payload: Record<string, any> = {};
      if (edits.unit_price !== undefined) payload.unit_price = parseFloat(String(edits.unit_price));
      if (edits.quantity !== undefined) payload.quantity = parseFloat(String(edits.quantity));
      if (edits.item_name !== undefined) payload.item_name = edits.item_name;
      if (edits.spec !== undefined) payload.spec = edits.spec;

      await api.put(`/quotations/items/${itemId}`, payload);
      setEditedItems((prev) => {
        const next = { ...prev };
        delete next[itemId];
        return next;
      });
      await fetchSheet();
    } catch {
      alert("保存失败");
    } finally {
      setSaving(false);
    }
  };

  const handleSaveAll = async () => {
    setSaving(true);
    try {
      for (const [itemId, edits] of Object.entries(editedItems)) {
        const payload: Record<string, any> = {};
        if (edits.unit_price !== undefined) payload.unit_price = parseFloat(String(edits.unit_price));
        if (edits.quantity !== undefined) payload.quantity = parseFloat(String(edits.quantity));
        if (edits.item_name !== undefined) payload.item_name = edits.item_name;
        if (edits.spec !== undefined) payload.spec = edits.spec;
        if (Object.keys(payload).length > 0) {
          await api.put(`/quotations/items/${itemId}`, payload);
        }
      }
      setEditedItems({});

      // 重算总额
      if (sheet) {
        await api.post(`/quotations/${sheet.id}/recalculate`);
      }
      await fetchSheet();
    } catch {
      alert("保存失败");
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteItem = async (itemId: number) => {
    try {
      await api.delete(`/quotations/items/${itemId}`);
      await fetchSheet();
    } catch {
      alert("删除失败");
    }
  };

  const handleRecalculate = async () => {
    if (!sheet) return;
    try {
      await api.post(`/quotations/${sheet.id}/recalculate`);
      await fetchSheet();
    } catch {
      alert("重算失败");
    }
  };

  const getItemValue = (item: QuotationItem, field: keyof QuotationItem) => {
    const edited = editedItems[item.id];
    if (edited && edited[field] !== undefined) return String(edited[field]);
    return item[field] !== undefined && item[field] !== null ? String(item[field]) : "";
  };

  // 按品类分组
  const groupedItems = sheet?.items.reduce((acc, item) => {
    if (!acc[item.category]) acc[item.category] = [];
    acc[item.category].push(item);
    return acc;
  }, {} as Record<string, QuotationItem[]>) || {};

  const totalAmount = sheet?.items.reduce((sum, item) => sum + (item.amount || 0), 0) || 0;
  const hasEdits = Object.keys(editedItems).length > 0;

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-8 w-8 animate-spin text-slate-400" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* 页头 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link href={`/dashboard/bid-projects/${projectId}`}>
            <Button variant="ghost" size="icon">
              <ArrowLeft className="h-5 w-5" />
            </Button>
          </Link>
          <h1 className="text-xl font-bold text-slate-900">报价管理</h1>
          {sheet && (
            <Badge variant="secondary">版本 V{sheet.version}</Badge>
          )}
        </div>
        <div className="flex items-center gap-2">
          {sheet && (
            <>
              <Button
                variant="outline"
                size="sm"
                onClick={handleRecalculate}
              >
                <Calculator className="mr-1 h-4 w-4" />
                重算总额
              </Button>
              <Button
                size="sm"
                onClick={handleSaveAll}
                disabled={saving || !hasEdits}
              >
                {saving ? (
                  <Loader2 className="mr-1 h-4 w-4 animate-spin" />
                ) : (
                  <Save className="mr-1 h-4 w-4" />
                )}
                保存修改
              </Button>
            </>
          )}
        </div>
      </div>

      {/* 无报价表 → 初始化入口 */}
      {!sheet && (
        <Card>
          <CardContent className="py-12 text-center">
            <p className="mb-4 text-slate-500">该项目尚未创建报价单</p>
            <div className="mx-auto flex max-w-sm items-center gap-2">
              <div className="flex-1">
                <label className="mb-1 block text-xs text-slate-500">下浮率 (%)</label>
                <Input
                  type="number"
                  min="5"
                  max="15"
                  step="0.5"
                  value={discountInput}
                  onChange={(e) => setDiscountInput(e.target.value)}
                  placeholder="10.0"
                />
              </div>
              <Button
                onClick={handleInit}
                disabled={initializing}
                className="mt-5"
              >
                {initializing ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Zap className="mr-2 h-4 w-4" />
                )}
                一键初始化报价
              </Button>
            </div>
            <p className="mt-2 text-xs text-slate-400">
              系统将根据招标要求自动生成六大品类报价框架
            </p>
          </CardContent>
        </Card>
      )}

      {/* 报价汇总 */}
      {sheet && (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
          <Card>
            <CardContent className="pt-4">
              <div className="text-sm text-slate-500">预算金额</div>
              <div className="mt-1 text-xl font-bold">
                {sheet.budget_amount
                  ? `¥${(sheet.budget_amount / 10000).toFixed(1)}万`
                  : "—"}
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-4">
              <div className="text-sm text-slate-500">报价总额</div>
              <div className="mt-1 text-xl font-bold text-blue-600">
                {totalAmount > 0 ? `¥${totalAmount.toFixed(2)}` : "待填写"}
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-4">
              <div className="text-sm text-slate-500">下浮率</div>
              <div className="mt-1 text-xl font-bold">
                {sheet.discount_rate
                  ? `${(sheet.discount_rate * 100).toFixed(1)}%`
                  : "—"}
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-4">
              <div className="text-sm text-slate-500">品目数量</div>
              <div className="mt-1 text-xl font-bold">{sheet.items.length} 项</div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* 报价明细 — 按品类分组 */}
      {sheet &&
        Object.entries(CATEGORY_LABELS).map(([cat, label]) => {
          const items = groupedItems[cat];
          if (!items || items.length === 0) return null;
          return (
            <Card key={cat}>
              <CardHeader className="pb-3">
                <CardTitle className="flex items-center gap-2 text-base">
                  <Badge className={CATEGORY_COLORS[cat]}>{label}</Badge>
                  <span className="text-xs text-slate-400">{items.length} 项</span>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b text-left text-xs text-slate-500">
                        <th className="pb-2 pr-2">品名</th>
                        <th className="pb-2 pr-2">规格</th>
                        <th className="pb-2 pr-2">单位</th>
                        <th className="pb-2 pr-2 text-right">参考价</th>
                        <th className="pb-2 pr-2 text-right">投标单价</th>
                        <th className="pb-2 pr-2 text-right">数量</th>
                        <th className="pb-2 pr-2 text-right">小计</th>
                        <th className="pb-2 w-16"></th>
                      </tr>
                    </thead>
                    <tbody>
                      {items.map((item) => (
                        <tr key={item.id} className="border-b last:border-0">
                          <td className="py-2 pr-2">
                            <Input
                              className="h-8 text-sm"
                              value={getItemValue(item, "item_name")}
                              onChange={(e) =>
                                handleItemChange(item.id, "item_name", e.target.value)
                              }
                            />
                          </td>
                          <td className="py-2 pr-2">
                            <Input
                              className="h-8 w-20 text-sm"
                              value={getItemValue(item, "spec")}
                              onChange={(e) =>
                                handleItemChange(item.id, "spec", e.target.value)
                              }
                            />
                          </td>
                          <td className="py-2 pr-2 text-slate-500">
                            {item.unit || "—"}
                          </td>
                          <td className="py-2 pr-2 text-right text-slate-400">
                            {item.market_ref_price?.toFixed(2) || "—"}
                          </td>
                          <td className="py-2 pr-2">
                            <Input
                              className="h-8 w-24 text-right text-sm"
                              type="number"
                              step="0.01"
                              value={getItemValue(item, "unit_price")}
                              onChange={(e) =>
                                handleItemChange(item.id, "unit_price", e.target.value)
                              }
                            />
                          </td>
                          <td className="py-2 pr-2">
                            <Input
                              className="h-8 w-20 text-right text-sm"
                              type="number"
                              step="1"
                              value={getItemValue(item, "quantity")}
                              onChange={(e) =>
                                handleItemChange(item.id, "quantity", e.target.value)
                              }
                            />
                          </td>
                          <td className="py-2 pr-2 text-right font-medium">
                            {item.amount ? `¥${item.amount.toFixed(2)}` : "—"}
                          </td>
                          <td className="py-2">
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-7 w-7 text-slate-400 hover:text-red-500"
                              onClick={() => handleDeleteItem(item.id)}
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </Button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          );
        })}
    </div>
  );
}
