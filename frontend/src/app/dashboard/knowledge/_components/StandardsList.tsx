"use client";

import { useState, useEffect, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Scale,
  ChevronDown,
  ChevronRight,
  Trash2,
  Loader2,
  Upload,
  CheckCircle2,
} from "lucide-react";
import FileDropZone from "@/components/ui/file-drop-zone";
import api from "@/lib/api";

const DOC_TYPE_LABELS: Record<string, string> = {
  food_safety_law: "食品安全法规",
  cold_chain_standard: "冷链标准",
  procurement_regulation: "采购规定",
  haccp: "HACCP",
  bid_template: "投标模板",
  "法律法规": "法律法规",
  "技术规范": "技术规范",
  "集团标准": "集团标准",
  "安全规程": "安全规程",
};

const DOC_TYPES = ["法律法规", "技术规范", "集团标准", "安全规程"];
const ACCEPTED_EXTENSIONS = [".doc", ".docx", ".txt", ".pdf"];

interface StdDocument {
  id: number;
  title: string;
  doc_type: string;
  version?: string;
  is_current: boolean;
  clause_count: number;
}

interface StandardsListProps {
  search: string;
  showCreate: boolean;
  setShowCreate: (show: boolean) => void;
}

export default function StandardsList({ search, showCreate, setShowCreate }: StandardsListProps) {
  const [stdDocs, setStdDocs] = useState<StdDocument[]>([]);
  const [expandedDoc, setExpandedDoc] = useState<number | null>(null);
  const [docClauses, setDocClauses] = useState<Record<number, any[]>>({});
  const [loading, setLoading] = useState(true);

  // 上传状态
  const [file, setFile] = useState<File | null>(null);
  const [docType, setDocType] = useState("安全规程");
  const [version, setVersion] = useState("v1.0");
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadError, setUploadError] = useState("");
  const [detecting, setDetecting] = useState(false);
  const [result, setResult] = useState<{ clause_count: number; vectorized_count: number } | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get("/standards", { params: { page: 1, page_size: 100 } });
      setStdDocs(res.data?.data?.items || []);
    } catch {
      setStdDocs([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const toggleDocClauses = async (docId: number) => {
    if (expandedDoc === docId) { setExpandedDoc(null); return; }
    setExpandedDoc(docId);
    if (!docClauses[docId]) {
      try {
        const res = await api.get(`/standards/${docId}/clauses`);
        setDocClauses((prev) => ({ ...prev, [docId]: res.data?.data || [] }));
      } catch {
        setDocClauses((prev) => ({ ...prev, [docId]: [] }));
      }
    }
  };

  const handleDeleteDoc = async (docId: number) => {
    if (!confirm("删除后将同时删除该文档下所有条款，确认删除？")) return;
    try {
      await api.delete(`/standards/${docId}`);
      fetchData();
    } catch (e: any) {
      alert("删除失败: " + (e.response?.data?.detail || e.message));
    }
  };

  const handleFileSelect = async (f: File) => {
    setFile(f);
    setResult(null);
    setUploadError("");
    // 自动识别文档类型和版本
    setDetecting(true);
    try {
      const fd = new FormData();
      fd.append("file", f);
      const res = await api.post("/standards/detect-type", fd, {
        headers: { "Content-Type": "multipart/form-data" },
        timeout: 15000,
      });
      const d = res.data?.data;
      if (d?.doc_type) setDocType(d.doc_type);
      if (d?.version) setVersion(d.version);
    } catch { /* 识别失败不阻塞 */ }
    setDetecting(false);
  };

  const handleUpload = async () => {
    if (!file) return;
    setUploading(true);
    setUploadProgress(0);
    setUploadError("");

    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("doc_type", docType);
      formData.append("version", version);

      const res = await api.post("/standards/upload", formData, {
        headers: { "Content-Type": "multipart/form-data" },
        timeout: 120000,
        onUploadProgress: (e) => {
          if (e.total) setUploadProgress(Math.round((e.loaded * 100) / e.total));
        },
      });

      setUploadProgress(100);
      const data = res.data?.data;
      setResult({
        clause_count: data?.clause_count || 0,
        vectorized_count: data?.vectorized_count || 0,
      });
      fetchData();
    } catch (err: any) {
      setUploadError(err.response?.data?.detail || "上传解析失败");
    } finally {
      setUploading(false);
    }
  };

  const handleReset = () => {
    setFile(null);
    setDocType("安全规程");
    setVersion("v1.0");
    setUploadProgress(0);
    setUploadError("");
    setResult(null);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-8 w-8 animate-spin text-slate-300" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* 上传区域 */}
      {showCreate && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">上传法规标准文档</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <FileDropZone
              accept={ACCEPTED_EXTENSIONS}
              file={file}
              onFileSelect={handleFileSelect}
              onFileRemove={() => { setFile(null); setUploadError(""); }}
              uploading={uploading}
              progress={uploadProgress}
              error={uploadError}
              hint="支持 PDF / Word / TXT 格式"
            />

            {detecting && (
              <div className="flex items-center gap-2 text-xs text-blue-600">
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                正在识别文档类型和版本...
              </div>
            )}

            <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
              <div className="space-y-1.5">
                <Label>文档类型</Label>
                <select
                  className="h-10 w-full rounded-md border border-slate-300 bg-white px-3 text-sm"
                  value={docType}
                  onChange={(e) => setDocType(e.target.value)}
                >
                  {DOC_TYPES.map((t) => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </select>
              </div>
              <div className="space-y-1.5">
                <Label>版本号</Label>
                <Input
                  value={version}
                  onChange={(e) => setVersion(e.target.value)}
                  placeholder="如：v1.0 或 2021"
                />
              </div>
              <div className="flex items-end gap-2">
                <Button onClick={handleUpload} disabled={!file || uploading}>
                  {uploading ? (
                    <><Loader2 className="mr-2 h-4 w-4 animate-spin" />解析中...</>
                  ) : (
                    <><Upload className="mr-2 h-4 w-4" />上传并解析</>
                  )}
                </Button>
                <Button variant="outline" onClick={() => { handleReset(); setShowCreate(false); }}>取消</Button>
              </div>
            </div>

            {result && (
              <div className="flex items-center gap-3 rounded-md bg-green-50 p-3">
                <CheckCircle2 className="h-5 w-5 text-green-500" />
                <div className="text-sm text-green-700">
                  <p className="font-medium">解析入库成功</p>
                  <p>共提取 {result.clause_count} 条条款，{result.vectorized_count} 条已向量化</p>
                </div>
                <Button size="sm" variant="outline" className="ml-auto" onClick={handleReset}>
                  继续上传
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* 文档列表 */}
      {stdDocs.length === 0 && !showCreate ? (
        <Card className="flex h-40 items-center justify-center">
          <div className="text-center text-slate-400">
            <Scale className="mx-auto mb-2 h-10 w-10 opacity-30" />
            <p className="text-sm">暂无法规标准，点击右上角「上传法规」导入</p>
          </div>
        </Card>
      ) : (
        <div className="space-y-2">
          {stdDocs
            .filter((d) => !search || d.title.includes(search))
            .map((doc) => (
              <div key={doc.id} className="overflow-hidden rounded-lg border">
                <div
                  className="flex cursor-pointer items-center justify-between px-4 py-3 transition-colors hover:bg-slate-50"
                  onClick={() => toggleDocClauses(doc.id)}
                >
                  <div className="flex items-center gap-3">
                    {expandedDoc === doc.id ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                    <Scale className="h-4 w-4 text-blue-500" />
                    <span className="font-medium">{doc.title}</span>
                    <span className="rounded-full bg-blue-100 px-2 py-0.5 text-xs text-blue-700">
                      {DOC_TYPE_LABELS[doc.doc_type] || doc.doc_type}
                    </span>
                    {doc.version && <span className="text-xs text-slate-400">{doc.version}</span>}
                    <span className="text-xs text-slate-400">{doc.clause_count} 条条款</span>
                  </div>
                  <Button variant="ghost" size="sm" onClick={(e) => { e.stopPropagation(); handleDeleteDoc(doc.id); }}>
                    <Trash2 className="h-3.5 w-3.5 text-red-400" />
                  </Button>
                </div>
                {expandedDoc === doc.id && (
                  <div className="border-t bg-slate-50 px-4 py-3 space-y-2">
                    {!docClauses[doc.id] ? (
                      <div className="flex items-center gap-2 py-4 justify-center text-slate-400">
                        <Loader2 className="h-4 w-4 animate-spin" /> 加载条款...
                      </div>
                    ) : docClauses[doc.id].length === 0 ? (
                      <p className="py-4 text-center text-sm text-slate-400">暂无条款</p>
                    ) : (
                      docClauses[doc.id].map((clause: any) => (
                        <div key={clause.id} className="rounded-md border bg-white p-3">
                          <div className="flex items-center gap-2 mb-1">
                            {clause.clause_no && <span className="font-mono text-xs text-slate-500">{clause.clause_no}</span>}
                            {clause.title && <span className="text-sm font-medium text-slate-700">{clause.title}</span>}
                          </div>
                          <p className="text-xs text-slate-600 leading-relaxed whitespace-pre-wrap">{clause.content}</p>
                        </div>
                      ))
                    )}
                  </div>
                )}
              </div>
            ))}
        </div>
      )}
    </div>
  );
}
