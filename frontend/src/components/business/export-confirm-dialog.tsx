"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  AlertOctagon,
  Download,
  Loader2,
  CheckCircle2,
  X,
} from "lucide-react";
import api from "@/lib/api";

interface FatalItem {
  level: string;
  category: string;
  title: string;
  detail: string;
}

interface Props {
  projectId: string;
  onConfirm: () => void;
  onCancel: () => void;
}

export default function ExportConfirmDialog({ projectId, onConfirm, onCancel }: Props) {
  const [checking, setChecking] = useState(true);
  const [canExport, setCanExport] = useState(false);
  const [fatalItems, setFatalItems] = useState<FatalItem[]>([]);
  const [disclaimer, setDisclaimer] = useState("");
  const [agreed, setAgreed] = useState(false);

  // 自动执行导出前检查
  useState(() => {
    (async () => {
      try {
        const res = await api.get(`/bid-projects/${projectId}/export-check`);
        const data = res.data?.data;
        setCanExport(data.can_export);
        setFatalItems(data.fatal_items || []);
        setDisclaimer(data.disclaimer || "");
      } catch {
        setCanExport(false);
      } finally {
        setChecking(false);
      }
    })();
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <Card className="mx-4 w-full max-w-lg">
        <CardContent className="pt-6">
          {/* 标题 */}
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-lg font-bold">导出确认</h3>
            <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onCancel}>
              <X className="h-4 w-4" />
            </Button>
          </div>

          {checking ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-6 w-6 animate-spin text-blue-500" />
              <span className="ml-2 text-sm text-slate-500">正在检查投标文件...</span>
            </div>
          ) : (
            <div className="space-y-4">
              {/* 致命项 */}
              {fatalItems.length > 0 && (
                <div className="rounded-lg border border-red-200 bg-red-50 p-3">
                  <div className="flex items-center gap-2 text-sm font-medium text-red-600">
                    <AlertOctagon className="h-4 w-4" />
                    发现 {fatalItems.length} 个致命风险
                  </div>
                  <ul className="mt-2 space-y-1">
                    {fatalItems.map((item, i) => (
                      <li key={i} className="text-xs text-red-600">
                        • {item.title}
                      </li>
                    ))}
                  </ul>
                  <p className="mt-2 text-xs text-red-500">
                    存在致命风险项，建议修复后再导出
                  </p>
                </div>
              )}

              {canExport && (
                <div className="rounded-lg border border-green-200 bg-green-50 p-3">
                  <div className="flex items-center gap-2 text-sm font-medium text-green-600">
                    <CheckCircle2 className="h-4 w-4" />
                    检查通过，无致命风险
                  </div>
                </div>
              )}

              {/* 免责声明 */}
              {disclaimer && (
                <div className="rounded-lg bg-slate-50 p-3">
                  <label className="flex items-start gap-2 text-xs text-slate-600">
                    <input
                      type="checkbox"
                      checked={agreed}
                      onChange={(e) => setAgreed(e.target.checked)}
                      className="mt-0.5 h-4 w-4 rounded border-slate-300"
                    />
                    <span>{disclaimer}</span>
                  </label>
                </div>
              )}

              {/* 操作按钮 */}
              <div className="flex justify-end gap-2 pt-2">
                <Button variant="outline" onClick={onCancel}>取消</Button>
                <Button
                  onClick={onConfirm}
                  disabled={!agreed && !!disclaimer}
                >
                  <Download className="mr-2 h-4 w-4" />
                  {canExport ? "确认导出" : "仍然导出"}
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
