"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  FileText,
  Upload,
  Loader2,
  CheckCircle2,
  Sparkles,
} from "lucide-react";
import FileDropZone from "@/components/ui/file-drop-zone";
import api from "@/lib/api";

const CUSTOMER_TYPES = [
  { value: "", label: "不指定" },
  { value: "school", label: "学校食堂" },
  { value: "hospital", label: "医院" },
  { value: "government", label: "政府机关" },
  { value: "enterprise", label: "企业食堂" },
  { value: "canteen", label: "团餐公司" },
];

interface BidDocsListProps {
  search: string;
  showCreate: boolean;
  setShowCreate: (show: boolean) => void;
}

export default function BidDocsList({ search, showCreate, setShowCreate }: BidDocsListProps) {
  const [file, setFile] = useState<File | null>(null);
  const [projectName, setProjectName] = useState("");
  const [customerType, setCustomerType] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadError, setUploadError] = useState("");
  const [result, setResult] = useState<{ snippet_count: number; vectorized_count: number } | null>(null);

  const handleUpload = async () => {
    if (!file) return;
    setUploading(true);
    setUploadProgress(0);
    setUploadError("");
    setResult(null);

    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("project_name", projectName || file.name);
      formData.append("customer_type", customerType);

      const res = await api.post("/knowledge/bid-docs/upload", formData, {
        headers: { "Content-Type": "multipart/form-data" },
        timeout: 120000,
        onUploadProgress: (e) => {
          if (e.total) setUploadProgress(Math.round((e.loaded * 100) / e.total));
        },
      });

      setUploadProgress(100);
      const data = res.data?.data;
      setResult({
        snippet_count: data?.snippet_count || 0,
        vectorized_count: data?.vectorized_count || 0,
      });
    } catch (err: any) {
      setUploadError(err.response?.data?.detail || "上传失败");
    } finally {
      setUploading(false);
    }
  };

  const handleReset = () => {
    setFile(null);
    setProjectName("");
    setCustomerType("");
    setUploadProgress(0);
    setUploadError("");
    setResult(null);
  };

  return (
    <div className="space-y-4">
      {/* 说明卡片 */}
      <Card className="border-blue-200 bg-blue-50/30">
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-base">
            <Sparkles className="h-4 w-4 text-blue-500" />
            优选标书知识库
          </CardTitle>
          <CardDescription>
            上传过往中标标书（PDF / Word / TXT），系统自动按章节切片、向量化，作为 AI 生成新标书时的高质量参考源。上传越多，AI 生成质量越高。
          </CardDescription>
        </CardHeader>
      </Card>

      {/* 上传区域 */}
      {showCreate && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">上传优选标书</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <FileDropZone
              accept={[".pdf", ".docx", ".doc", ".txt"]}
              file={file}
              onFileSelect={(f) => { setFile(f); setResult(null); setUploadError(""); }}
              onFileRemove={() => { setFile(null); setResult(null); setUploadError(""); }}
              uploading={uploading}
              progress={uploadProgress}
              error={uploadError}
              hint="支持 PDF / Word / TXT 格式"
            />

            <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
              <div className="space-y-1.5">
                <Label>项目名称（可选）</Label>
                <Input
                  value={projectName}
                  onChange={(e) => setProjectName(e.target.value)}
                  placeholder="如：XX学校食材配送中标标书"
                />
              </div>
              <div className="space-y-1.5">
                <Label>客户类型（可选）</Label>
                <select
                  className="h-10 w-full rounded-md border border-slate-300 bg-white px-3 text-sm"
                  value={customerType}
                  onChange={(e) => setCustomerType(e.target.value)}
                >
                  {CUSTOMER_TYPES.map((t) => (
                    <option key={t.value} value={t.value}>{t.label}</option>
                  ))}
                </select>
              </div>
              <div className="flex items-end gap-2">
                <Button onClick={handleUpload} disabled={!file || uploading}>
                  {uploading ? (
                    <><Loader2 className="mr-2 h-4 w-4 animate-spin" />解析中...</>
                  ) : (
                    <><Upload className="mr-2 h-4 w-4" />上传并切片</>
                  )}
                </Button>
                <Button variant="outline" onClick={() => { handleReset(); setShowCreate(false); }}>取消</Button>
              </div>
            </div>

            {/* 成功结果 */}
            {result && (
              <div className="flex items-center gap-3 rounded-md bg-green-50 p-3">
                <CheckCircle2 className="h-5 w-5 text-green-500" />
                <div className="text-sm text-green-700">
                  <p className="font-medium">标书入库成功</p>
                  <p>切分为 {result.snippet_count} 个章节片段，{result.vectorized_count} 个已向量化</p>
                </div>
                <Button size="sm" variant="outline" className="ml-auto" onClick={() => { handleReset(); }}>
                  继续上传
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* 提示 */}
      {!showCreate && (
        <Card className="flex h-40 items-center justify-center">
          <div className="text-center text-slate-400">
            <FileText className="mx-auto mb-2 h-10 w-10 opacity-30" />
            <p className="text-sm">点击右上角「上传标书」导入历史中标标书</p>
            <p className="mt-1 text-xs">上传后的标书会自动切片为知识片段，可在「章节片段」Tab 中查看</p>
          </div>
        </Card>
      )}
    </div>
  );
}
