"use client";

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import {
  CheckCircle2,
  Circle,
  Copy,
  ClipboardCheck,
  Stamp,
  Printer,
  Truck,
  Package,
  Lock,
  Hash,
  Tag,
  X,
  AlertTriangle,
} from "lucide-react";
import api from "@/lib/api";
import { toast } from "sonner";

// ============================
// 数据类型
// ============================

interface DepositMemo {
  amount: string | null;
  memo_text: string;
}

interface StampItem {
  document_name: string;
  stamp_type: string;
  source: string;
  checked: boolean;
}

interface PrintReminder {
  item: string;
  category: string;
  checked: boolean;
}

interface ChecklistData {
  deposit_memo: DepositMemo | null;
  stamp_items: StampItem[];
  print_reminders: PrintReminder[];
  total_items: number;
}

// ============================
// 分类图标
// ============================

const CATEGORY_ICON: Record<string, typeof Package> = {
  "装订": Package,
  "密封": Lock,
  "份数": Hash,
  "标记": Tag,
  "递交": Truck,
};

// ============================
// 主组件
// ============================

interface Props {
  projectId: string;
  onClose: () => void;
}

export default function PostExportChecklist({ projectId, onClose }: Props) {
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<ChecklistData | null>(null);
  const [stampChecks, setStampChecks] = useState<boolean[]>([]);
  const [reminderChecks, setReminderChecks] = useState<boolean[]>([]);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const res = await api.get(`/bid-projects/${projectId}/bid-checklist`);
        const d = res.data?.data;
        if (d) {
          setData(d);
          setStampChecks(new Array(d.stamp_items?.length || 0).fill(false));
          setReminderChecks(new Array(d.print_reminders?.length || 0).fill(false));
        }
      } catch {
        toast.error("获取检查清单失败");
      } finally {
        setLoading(false);
      }
    })();
  }, [projectId]);

  const toggleStamp = (i: number) =>
    setStampChecks((prev) => prev.map((v, idx) => (idx === i ? !v : v)));

  const toggleReminder = (i: number) =>
    setReminderChecks((prev) => prev.map((v, idx) => (idx === i ? !v : v)));

  const totalChecked =
    stampChecks.filter(Boolean).length + reminderChecks.filter(Boolean).length;
  const totalItems =
    (data?.stamp_items?.length || 0) + (data?.print_reminders?.length || 0);
  const allChecked = totalItems > 0 && totalChecked === totalItems;
  const progress = totalItems > 0 ? Math.round((totalChecked / totalItems) * 100) : 0;

  const handleCopyMemo = () => {
    if (data?.deposit_memo?.memo_text) {
      navigator.clipboard.writeText(data.deposit_memo.memo_text);
      setCopied(true);
      toast.success("备注已复制到剪贴板");
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleClose = () => {
    if (!allChecked && totalItems > 0) {
      const remaining = totalItems - totalChecked;
      if (!window.confirm(`还有 ${remaining} 项未勾选，确定跳过检查？`)) {
        return;
      }
    }
    onClose();
  };

  if (loading) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
        <div className="rounded-xl bg-white p-8 text-center">
          <div className="h-8 w-8 mx-auto animate-spin rounded-full border-2 border-blue-500 border-t-transparent" />
          <p className="mt-3 text-sm text-slate-500">加载检查清单...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="relative w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-xl bg-white shadow-2xl">
        {/* 头部 */}
        <div className="sticky top-0 z-10 flex items-center justify-between border-b bg-white px-6 py-4 rounded-t-xl">
          <div>
            <h2 className="text-lg font-bold text-slate-900">
              <ClipboardCheck className="mr-2 inline h-5 w-5 text-blue-500" />
              投标交付检查清单
            </h2>
            <p className="mt-0.5 text-xs text-slate-500">
              文件已导出，请在打印装订前逐项确认
            </p>
          </div>
          <button onClick={handleClose} className="text-slate-400 hover:text-slate-600">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="p-6 space-y-6">
          {/* 进度条 */}
          <div className="space-y-1.5">
            <div className="flex justify-between text-sm">
              <span className="text-slate-600">
                完成进度 <span className="font-bold text-blue-600">{totalChecked}/{totalItems}</span>
              </span>
              <span className={`font-bold ${allChecked ? "text-emerald-600" : "text-slate-400"}`}>
                {progress}%
              </span>
            </div>
            <div className="h-2 rounded-full bg-slate-100 overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-300 ${
                  allChecked ? "bg-emerald-500" : "bg-blue-500"
                }`}
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>

          {/* 保证金备注 */}
          {data?.deposit_memo && data.deposit_memo.memo_text && (
            <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
              <h3 className="flex items-center gap-2 text-sm font-semibold text-amber-800">
                <Stamp className="h-4 w-4" />
                保证金转账备注
              </h3>
              <div className="mt-2 flex items-center gap-2">
                <code className="flex-1 rounded bg-white px-3 py-2 text-sm text-slate-800 border border-amber-200">
                  {data.deposit_memo.memo_text}
                </code>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleCopyMemo}
                  className="shrink-0"
                >
                  {copied ? (
                    <CheckCircle2 className="mr-1 h-3.5 w-3.5 text-emerald-500" />
                  ) : (
                    <Copy className="mr-1 h-3.5 w-3.5" />
                  )}
                  {copied ? "已复制" : "复制"}
                </Button>
              </div>
              {data.deposit_memo.amount && (
                <p className="mt-1.5 text-xs text-amber-600">
                  保证金金额: {data.deposit_memo.amount} 元
                </p>
              )}
            </div>
          )}

          {/* 盖章清单 */}
          {data?.stamp_items && data.stamp_items.length > 0 && (
            <div>
              <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-800 mb-3">
                <Stamp className="h-4 w-4 text-red-500" />
                盖章/签字清单
                <span className="text-xs text-slate-400 font-normal">
                  ({stampChecks.filter(Boolean).length}/{data.stamp_items.length})
                </span>
              </h3>
              <div className="space-y-1.5">
                {data.stamp_items.map((item, i) => (
                  <button
                    key={i}
                    onClick={() => toggleStamp(i)}
                    className={`flex w-full items-center gap-3 rounded-lg border p-3 text-left transition-all ${
                      stampChecks[i]
                        ? "border-emerald-200 bg-emerald-50"
                        : "border-slate-200 hover:border-blue-200 hover:bg-blue-50/50"
                    }`}
                  >
                    {stampChecks[i] ? (
                      <CheckCircle2 className="h-4.5 w-4.5 shrink-0 text-emerald-500" />
                    ) : (
                      <Circle className="h-4.5 w-4.5 shrink-0 text-slate-300" />
                    )}
                    <div className="flex-1 min-w-0">
                      <span className={`text-sm ${stampChecks[i] ? "text-emerald-700 line-through" : "text-slate-700"}`}>
                        {item.document_name}
                      </span>
                      <span className="ml-2 text-xs text-slate-400">
                        {item.stamp_type}
                      </span>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* 打印装订提醒 */}
          {data?.print_reminders && data.print_reminders.length > 0 && (
            <div>
              <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-800 mb-3">
                <Printer className="h-4 w-4 text-blue-500" />
                打印装订 & 递交提醒
                <span className="text-xs text-slate-400 font-normal">
                  ({reminderChecks.filter(Boolean).length}/{data.print_reminders.length})
                </span>
              </h3>
              <div className="space-y-1.5">
                {data.print_reminders.map((item, i) => {
                  const Icon = CATEGORY_ICON[item.category] || Package;
                  return (
                    <button
                      key={i}
                      onClick={() => toggleReminder(i)}
                      className={`flex w-full items-center gap-3 rounded-lg border p-3 text-left transition-all ${
                        reminderChecks[i]
                          ? "border-emerald-200 bg-emerald-50"
                          : "border-slate-200 hover:border-blue-200 hover:bg-blue-50/50"
                      }`}
                    >
                      {reminderChecks[i] ? (
                        <CheckCircle2 className="h-4.5 w-4.5 shrink-0 text-emerald-500" />
                      ) : (
                        <Circle className="h-4.5 w-4.5 shrink-0 text-slate-300" />
                      )}
                      <Icon className="h-3.5 w-3.5 shrink-0 text-slate-400" />
                      <span className={`text-sm flex-1 ${reminderChecks[i] ? "text-emerald-700 line-through" : "text-slate-700"}`}>
                        {item.item}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* 底部操作栏 */}
        <div className="sticky bottom-0 border-t bg-white px-6 py-4 rounded-b-xl">
          {!allChecked && totalItems > 0 && (
            <div className="mb-3 flex items-center gap-2 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-700">
              <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
              <span>还有 {totalItems - totalChecked} 项未确认，建议全部勾选后再提交标书</span>
            </div>
          )}
          <div className="flex justify-end gap-3">
            <Button variant="outline" onClick={handleClose}>
              {allChecked ? "完成" : "稍后再看"}
            </Button>
            {allChecked && (
              <Button
                onClick={onClose}
                className="bg-emerald-600 hover:bg-emerald-700 text-white"
              >
                <CheckCircle2 className="mr-1.5 h-4 w-4" />
                全部确认，准备递交
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
