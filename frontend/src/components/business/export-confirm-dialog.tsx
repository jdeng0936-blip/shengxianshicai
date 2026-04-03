"use client";

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  AlertOctagon,
  AlertTriangle,
  Download,
  Loader2,
  CheckCircle2,
  X,
  ShieldAlert,
  FileText,
  FileCheck,
} from "lucide-react";
import api from "@/lib/api";

interface RiskSummary {
  fatal_count: number;
  critical_count: number;
  warning_count: number;
  can_export: boolean;
}

interface Props {
  projectId: string;
  onConfirm: (format: string) => void;
  onCancel: () => void;
}

const HIGH_RISK_CHECKS = [
  { id: "certs", label: "资质证书编号与有效期已核实" },
  { id: "cases", label: "业绩案例信息真实准确" },
  { id: "metrics", label: "关键承诺指标（响应时间、温度等）可执行" },
  { id: "staff", label: "人员信息及资格证书已核实" },
  { id: "vehicles", label: "车辆/设备数据与实际一致" },
  { id: "quotation", label: "报价表由企业自行填写并复核" },
];

const DISCLAIMER =
  "本文档为 AI 辅助生成首稿，最终提交前请自行审核全部内容。" +
  "鲜标通不对标书内容的真实性和最终投标结果承担法律责任。";

export default function ExportConfirmDialog({ projectId, onConfirm, onCancel }: Props) {
  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(true);
  const [risk, setRisk] = useState<RiskSummary | null>(null);
  const [checks, setChecks] = useState<Record<string, boolean>>({});
  const [disclaimerAgreed, setDisclaimerAgreed] = useState(false);
  const [exportFormat, setExportFormat] = useState("docx");

  // 弹窗打开时加载风险状态
  useEffect(() => {
    (async () => {
      try {
        const res = await api.post(`/bid-projects/${projectId}/risk/check`);
        const data = res.data?.data;
        setRisk({
          fatal_count: data?.fatal_count ?? 0,
          critical_count: data?.critical_count ?? 0,
          warning_count: data?.warning_count ?? 0,
          can_export: data?.can_export ?? false,
        });
      } catch {
        setRisk({ fatal_count: 0, critical_count: 0, warning_count: 0, can_export: true });
      } finally {
        setLoading(false);
      }
    })();
  }, [projectId]);

  const allChecked = HIGH_RISK_CHECKS.every((c) => checks[c.id]);
  const canProceedStep1 = risk?.can_export ?? false;
  const canProceedStep2 = allChecked;
  const canProceedStep3 = disclaimerAgreed;
  const canExport = canProceedStep1 && canProceedStep2 && canProceedStep3;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <Card className="mx-4 w-full max-w-xl max-h-[90vh] overflow-y-auto">
        <CardContent className="pt-6">
          {/* 标题 */}
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-lg font-bold flex items-center gap-2">
              <FileCheck className="h-5 w-5" />
              导出确认（{step}/4）
            </h3>
            <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onCancel}>
              <X className="h-4 w-4" />
            </Button>
          </div>

          {/* 步骤指示器 */}
          <div className="mb-5 flex gap-1">
            {[1, 2, 3, 4].map((s) => (
              <div
                key={s}
                className={`h-1.5 flex-1 rounded-full transition-colors ${
                  s <= step ? "bg-blue-500" : "bg-slate-200"
                }`}
              />
            ))}
          </div>

          {loading && (
            <div className="flex items-center justify-center py-10">
              <Loader2 className="h-6 w-6 animate-spin text-slate-400" />
              <span className="ml-2 text-sm text-slate-500">正在检查风险状态...</span>
            </div>
          )}

          {/* Step 1: 风险检查状态 */}
          {!loading && step === 1 && (
            <div className="space-y-3">
              <h4 className="flex items-center gap-2 text-sm font-medium">
                <ShieldAlert className="h-4 w-4" />
                Step 1 — 风险检查状态
              </h4>
              {risk && (
                <div className="grid grid-cols-3 gap-3">
                  <div className={`rounded-lg p-3 text-center ${risk.fatal_count > 0 ? "bg-red-50" : "bg-green-50"}`}>
                    <div className={`text-xl font-bold ${risk.fatal_count > 0 ? "text-red-600" : "text-green-600"}`}>
                      {risk.fatal_count}
                    </div>
                    <div className="text-xs text-slate-500">致命项</div>
                  </div>
                  <div className="rounded-lg bg-orange-50 p-3 text-center">
                    <div className="text-xl font-bold text-orange-600">{risk.critical_count}</div>
                    <div className="text-xs text-slate-500">严重项</div>
                  </div>
                  <div className="rounded-lg bg-yellow-50 p-3 text-center">
                    <div className="text-xl font-bold text-yellow-600">{risk.warning_count}</div>
                    <div className="text-xs text-slate-500">建议项</div>
                  </div>
                </div>
              )}
              {canProceedStep1 ? (
                <div className="flex items-center gap-2 rounded-lg bg-green-50 p-3 text-sm text-green-700">
                  <CheckCircle2 className="h-4 w-4" />
                  致命问题已全部修复，可以导出
                </div>
              ) : (
                <div className="flex items-center gap-2 rounded-lg bg-red-50 p-3 text-sm text-red-600">
                  <AlertOctagon className="h-4 w-4" />
                  存在 {risk?.fatal_count} 个致命问题未修复，无法导出
                </div>
              )}
              <div className="flex justify-end gap-2">
                {!canProceedStep1 && (
                  <Button variant="outline" size="sm" onClick={onCancel}>
                    前往修复
                  </Button>
                )}
                <Button size="sm" disabled={!canProceedStep1} onClick={() => setStep(2)}>
                  下一步
                </Button>
              </div>
            </div>
          )}

          {/* Step 2: 高风险字段人工确认 */}
          {!loading && step === 2 && (
            <div className="space-y-3">
              <h4 className="flex items-center gap-2 text-sm font-medium">
                <AlertTriangle className="h-4 w-4 text-orange-500" />
                Step 2 — 高风险字段人工确认
              </h4>
              <p className="text-xs text-slate-500">
                以下内容为 AI 辅助生成，请逐项核实后勾选确认：
              </p>
              <div className="space-y-2">
                {HIGH_RISK_CHECKS.map((item) => (
                  <label
                    key={item.id}
                    className={`flex cursor-pointer items-center gap-3 rounded-lg border p-3 transition-colors ${
                      checks[item.id] ? "border-green-300 bg-green-50" : "border-slate-200 hover:bg-slate-50"
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={checks[item.id] || false}
                      onChange={(e) => setChecks({ ...checks, [item.id]: e.target.checked })}
                      className="h-4 w-4 rounded border-slate-300"
                    />
                    <span className="text-sm">{item.label}</span>
                  </label>
                ))}
              </div>
              <div className="flex justify-between">
                <Button variant="ghost" size="sm" onClick={() => setStep(1)}>
                  上一步
                </Button>
                <Button size="sm" disabled={!canProceedStep2} onClick={() => setStep(3)}>
                  下一步
                </Button>
              </div>
            </div>
          )}

          {/* Step 3: 免责声明 */}
          {!loading && step === 3 && (
            <div className="space-y-3">
              <h4 className="flex items-center gap-2 text-sm font-medium">
                <FileText className="h-4 w-4" />
                Step 3 — 免责声明
              </h4>
              <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600 leading-relaxed">
                {DISCLAIMER}
              </div>
              <label className="flex cursor-pointer items-center gap-3 rounded-lg border p-3 transition-colors hover:bg-slate-50">
                <input
                  type="checkbox"
                  checked={disclaimerAgreed}
                  onChange={(e) => setDisclaimerAgreed(e.target.checked)}
                  className="h-4 w-4 rounded border-slate-300"
                />
                <span className="text-sm font-medium">我已阅读并同意以上声明</span>
              </label>
              <div className="flex justify-between">
                <Button variant="ghost" size="sm" onClick={() => setStep(2)}>
                  上一步
                </Button>
                <Button size="sm" disabled={!canProceedStep3} onClick={() => setStep(4)}>
                  下一步
                </Button>
              </div>
            </div>
          )}

          {/* Step 4: 导出格式选择 */}
          {!loading && step === 4 && (
            <div className="space-y-3">
              <h4 className="flex items-center gap-2 text-sm font-medium">
                <Download className="h-4 w-4" />
                Step 4 — 选择导出格式
              </h4>
              <div className="space-y-2">
                {[
                  { value: "docx", label: "Word (.docx)", desc: "推荐，可继续编辑" },
                  { value: "pdf", label: "PDF (.pdf)", desc: "固定版式，适合提交" },
                ].map((fmt) => (
                  <label
                    key={fmt.value}
                    className={`flex cursor-pointer items-center gap-3 rounded-lg border p-3 transition-colors ${
                      exportFormat === fmt.value ? "border-blue-300 bg-blue-50" : "border-slate-200 hover:bg-slate-50"
                    }`}
                  >
                    <input
                      type="radio"
                      name="format"
                      value={fmt.value}
                      checked={exportFormat === fmt.value}
                      onChange={() => setExportFormat(fmt.value)}
                      className="h-4 w-4"
                    />
                    <div>
                      <div className="text-sm font-medium">{fmt.label}</div>
                      <div className="text-xs text-slate-400">{fmt.desc}</div>
                    </div>
                  </label>
                ))}
              </div>
              <div className="flex justify-between">
                <Button variant="ghost" size="sm" onClick={() => setStep(3)}>
                  上一步
                </Button>
                <Button
                  size="sm"
                  disabled={!canExport}
                  onClick={() => onConfirm(exportFormat)}
                >
                  <Download className="mr-2 h-4 w-4" />
                  确认导出
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
