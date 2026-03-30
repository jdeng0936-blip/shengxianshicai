"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useParams } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import {
  ArrowLeft,
  Loader2,
  Sparkles,
  Save,
  RefreshCw,
  CheckCircle2,
  AlertTriangle,
  FileText,
  Zap,
} from "lucide-react";
import Link from "next/link";
import api from "@/lib/api";

interface BidChapter {
  id: number;
  project_id: number;
  chapter_no: string;
  title: string;
  content?: string;
  source: string;
  status: string;
  sort_order: number;
  ai_model_used?: string;
  has_warning: boolean;
}

const STATUS_BADGE: Record<string, { label: string; variant: "default" | "secondary" | "destructive" | "outline" }> = {
  draft: { label: "草稿", variant: "secondary" },
  generated: { label: "已生成", variant: "default" },
  reviewed: { label: "已审核", variant: "default" },
  finalized: { label: "已定稿", variant: "default" },
};

export default function ChaptersEditorPage() {
  const params = useParams();
  const projectId = params.id as string;

  const [chapters, setChapters] = useState<BidChapter[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [editContent, setEditContent] = useState("");
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [generatingAll, setGeneratingAll] = useState(false);
  const [saving, setSaving] = useState(false);
  const [progress, setProgress] = useState<{ completed: number; total: number; failed: number } | null>(null);

  const fetchChapters = useCallback(async () => {
    try {
      setLoading(true);
      const res = await api.get(`/bid-projects/${projectId}/chapters`);
      const data = res.data?.data || [];
      setChapters(data);
      if (data.length > 0 && !selectedId) {
        setSelectedId(data[0].id);
        setEditContent(data[0].content || "");
      }
    } catch {
      setChapters([]);
    } finally {
      setLoading(false);
    }
  }, [projectId, selectedId]);

  useEffect(() => {
    fetchChapters();
  }, [fetchChapters]);

  const handleInitChapters = async () => {
    try {
      setLoading(true);
      const res = await api.post(`/bid-projects/${projectId}/init-chapters`);
      const data = res.data?.data || [];
      setChapters(data);
      if (data.length > 0) {
        setSelectedId(data[0].id);
        setEditContent(data[0].content || "");
      }
    } catch (err: any) {
      alert(err.response?.data?.detail || "初始化失败");
    } finally {
      setLoading(false);
    }
  };

  const handleSelectChapter = (ch: BidChapter) => {
    setSelectedId(ch.id);
    setEditContent(ch.content || "");
  };

  const handleSave = async () => {
    if (!selectedId) return;
    setSaving(true);
    try {
      await api.put(`/bid-projects/chapters/${selectedId}`, { content: editContent });
      setChapters((prev) =>
        prev.map((ch) => (ch.id === selectedId ? { ...ch, content: editContent } : ch))
      );
    } catch {
      alert("保存失败");
    } finally {
      setSaving(false);
    }
  };

  const handleGenerateOne = async () => {
    if (!selectedId) return;
    setGenerating(true);
    try {
      const res = await api.post(
        `/bid-projects/${projectId}/generate-chapter/${selectedId}`
      );
      const chapter = res.data?.data;
      if (chapter) {
        setEditContent(chapter.content || "");
        setChapters((prev) =>
          prev.map((ch) => (ch.id === selectedId ? { ...ch, ...chapter } : ch))
        );
      }
    } catch (err: any) {
      alert(err.response?.data?.detail || "生成失败");
    } finally {
      setGenerating(false);
    }
  };

  const handleGenerateAll = async () => {
    setGeneratingAll(true);
    setProgress({ completed: 0, total: 0, failed: 0 });

    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1"}/bid-projects/${projectId}/generate-all`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${localStorage.getItem("access_token")}`,
          },
        }
      );

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();

      if (!reader) return;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const text = decoder.decode(value);
        const lines = text.split("\n").filter((l) => l.startsWith("data: "));

        for (const line of lines) {
          const data = line.slice(6);
          if (data === "[DONE]") continue;
          try {
            const msg = JSON.parse(data);
            if (msg.type === "progress" || msg.type === "done") {
              setProgress({
                completed: msg.completed || 0,
                total: msg.total || 0,
                failed: msg.failed || 0,
              });
            }
          } catch {
            // skip parse errors
          }
        }
      }

      // 刷新章节列表
      await fetchChapters();
    } catch (err: any) {
      alert("批量生成失败");
    } finally {
      setGeneratingAll(false);
      setProgress(null);
    }
  };

  const selectedChapter = chapters.find((ch) => ch.id === selectedId);

  if (loading && chapters.length === 0) {
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
          <h1 className="text-xl font-bold text-slate-900">投标文件章节编辑</h1>
        </div>
        <div className="flex items-center gap-2">
          {chapters.length === 0 ? (
            <Button onClick={handleInitChapters}>
              <FileText className="mr-2 h-4 w-4" />
              初始化章节
            </Button>
          ) : (
            <Button
              onClick={handleGenerateAll}
              disabled={generatingAll}
              variant="default"
            >
              {generatingAll ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Zap className="mr-2 h-4 w-4" />
              )}
              {generatingAll
                ? `生成中 ${progress?.completed || 0}/${progress?.total || 0}`
                : "一键生成全部"}
            </Button>
          )}
        </div>
      </div>

      {/* 进度条 */}
      {generatingAll && progress && progress.total > 0 && (
        <div className="rounded-lg border bg-blue-50 p-3">
          <div className="mb-2 flex items-center justify-between text-sm">
            <span className="text-blue-700">
              正在生成... {progress.completed}/{progress.total}
              {progress.failed > 0 && (
                <span className="ml-2 text-red-600">（{progress.failed} 失败）</span>
              )}
            </span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-blue-200">
            <div
              className="h-full rounded-full bg-blue-600 transition-all"
              style={{ width: `${(progress.completed / progress.total) * 100}%` }}
            />
          </div>
        </div>
      )}

      {chapters.length > 0 && (
        <div className="flex gap-4" style={{ height: "calc(100vh - 220px)" }}>
          {/* 左侧章节列表 */}
          <div className="w-72 shrink-0 overflow-y-auto rounded-lg border bg-white">
            <div className="border-b p-3">
              <h3 className="text-sm font-medium text-slate-700">章节目录</h3>
            </div>
            <div className="space-y-1 p-2">
              {chapters.map((ch) => {
                const isSelected = ch.id === selectedId;
                const statusInfo = STATUS_BADGE[ch.status] || STATUS_BADGE.draft;
                return (
                  <button
                    key={ch.id}
                    onClick={() => handleSelectChapter(ch)}
                    className={`flex w-full items-start gap-2 rounded-md px-3 py-2 text-left text-sm transition-colors ${
                      isSelected
                        ? "bg-slate-100 text-slate-900"
                        : "text-slate-600 hover:bg-slate-50"
                    }`}
                  >
                    <div className="flex-1 min-w-0">
                      <div className="font-medium truncate">{ch.chapter_no}</div>
                      <div className="truncate text-xs text-slate-400">{ch.title}</div>
                    </div>
                    <div className="shrink-0 flex flex-col items-end gap-1">
                      <Badge variant={statusInfo.variant} className="text-xs">
                        {statusInfo.label}
                      </Badge>
                      {ch.has_warning && (
                        <AlertTriangle className="h-3.5 w-3.5 text-amber-500" />
                      )}
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          {/* 右侧编辑区 */}
          <Card className="flex flex-1 flex-col overflow-hidden">
            {selectedChapter ? (
              <>
                <CardHeader className="shrink-0 border-b pb-3">
                  <div className="flex items-center justify-between">
                    <div>
                      <CardTitle className="text-base">
                        {selectedChapter.chapter_no} {selectedChapter.title}
                      </CardTitle>
                      <div className="mt-1 flex items-center gap-2 text-xs text-slate-400">
                        <span>来源: {selectedChapter.source}</span>
                        {selectedChapter.ai_model_used && (
                          <span>模型: {selectedChapter.ai_model_used}</span>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={handleGenerateOne}
                        disabled={generating}
                      >
                        {generating ? (
                          <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <Sparkles className="mr-1 h-3.5 w-3.5" />
                        )}
                        {selectedChapter.content ? "重新生成" : "AI 生成"}
                      </Button>
                      <Button size="sm" onClick={handleSave} disabled={saving}>
                        {saving ? (
                          <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <Save className="mr-1 h-3.5 w-3.5" />
                        )}
                        保存
                      </Button>
                    </div>
                  </div>
                </CardHeader>
                <CardContent className="flex-1 overflow-hidden p-0">
                  <Textarea
                    className="h-full w-full resize-none rounded-none border-0 p-4 font-mono text-sm focus-visible:ring-0"
                    placeholder="章节内容为空，点击「AI 生成」开始..."
                    value={editContent}
                    onChange={(e) => setEditContent(e.target.value)}
                  />
                </CardContent>
              </>
            ) : (
              <CardContent className="flex flex-1 items-center justify-center">
                <p className="text-slate-400">请选择左侧章节</p>
              </CardContent>
            )}
          </Card>
        </div>
      )}
    </div>
  );
}
