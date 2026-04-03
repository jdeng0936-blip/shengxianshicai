"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import MarkdownEditor from "@/components/business/markdown-editor";
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
  Download,
} from "lucide-react";
import Link from "next/link";
import api from "@/lib/api";
import ChapterFeedback from "@/components/business/chapter-feedback";
import AIPipelineProgress from "@/components/business/ai-pipeline-progress";
import CoverageHeatmap, { type CoverageReport } from "@/components/business/coverage-heatmap";
import { useGenerationSocket } from "@/hooks/useGenerationSocket";
import AIDetectionPanel, { type DetectionResult } from "@/components/business/ai-detection-panel";
import { toast } from "sonner";

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
  ai_ratio: number;
  source_tags: string;
}

const SOURCE_TAG_CONFIG: Record<string, { label: string; color: string }> = {
  ai_generated: { label: "AI 生成", color: "bg-purple-100 text-purple-700" },
  company_db: { label: "企业库", color: "bg-green-100 text-green-700" },
  template: { label: "模板", color: "bg-blue-100 text-blue-700" },
  credential: { label: "资质", color: "bg-amber-100 text-amber-700" },
};

const STATUS_BADGE: Record<string, { label: string; variant: "default" | "secondary" | "destructive" | "outline" }> = {
  draft: { label: "草稿", variant: "secondary" },
  generated: { label: "已生成", variant: "default" },
  reviewed: { label: "已审核", variant: "default" },
  finalized: { label: "已定稿", variant: "default" },
};

export default function ChaptersEditorPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const projectId = params.id as string;
  const highlightChapterId = searchParams.get("highlight");

  const [chapters, setChapters] = useState<BidChapter[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [editContent, setEditContent] = useState("");
  const [highlightActive, setHighlightActive] = useState(false);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [generatingAll, setGeneratingAll] = useState(false);
  const [saving, setSaving] = useState(false);
  const [progress, setProgress] = useState<{ completed: number; total: number; failed: number } | null>(null);
  const [exporting, setExporting] = useState(false);
  const [selection, setSelection] = useState<{ text: string; start: number; end: number } | null>(null);
  const [rewriting, setRewriting] = useState(false);
  const [customInstruction, setCustomInstruction] = useState("");
  const [customRewriting, setCustomRewriting] = useState(false);

  // WebSocket 实时管线进度
  const { state: pipelineState, connect: wsConnect, disconnect: wsDisconnect } =
    useGenerationSocket(projectId);

  // 覆盖率报告
  const [coverageReport, setCoverageReport] = useState<CoverageReport | null>(null);
  const [coverageLoading, setCoverageLoading] = useState(false);
  const [showCoverage, setShowCoverage] = useState(false);

  // AI 检测
  const [detectionResult, setDetectionResult] = useState<DetectionResult | null>(null);
  const [detectLoading, setDetectLoading] = useState(false);
  const [humanizing, setHumanizing] = useState(false);

  const handleDetectAI = async () => {
    if (!selectedId) return;
    setDetectLoading(true);
    try {
      const res = await api.get(`/bid-projects/${projectId}/ai-detection/${selectedId}`);
      setDetectionResult(res.data?.data || null);
    } catch (err: any) {
      toast.error(err.response?.data?.detail || "AI 检测失败");
    } finally {
      setDetectLoading(false);
    }
  };

  const handleHumanize = async () => {
    if (!selectedId || !selectedChapter) return;
    setHumanizing(true);
    try {
      const res = await api.post(`/bid-projects/${projectId}/chapters/${selectedId}/rewrite`, {
        original_text: editContent,
        instruction: "请对以下投标文本进行人工化润色：减少程式化衔接词（如此外、同时、因此），增加句长变化，替换重复表述，加入具体数据和细节描写，使文本更像资深业务人员的手写风格。保持原有内容要点不变。",
      });
      const rewritten = res.data?.data?.rewritten;
      if (rewritten) {
        setEditContent(rewritten);
        toast.success("润色完成，请检查修改内容");
        // 重新检测
        setTimeout(() => handleDetectAI(), 500);
      }
    } catch (err: any) {
      toast.error(err.response?.data?.detail || "润色失败");
    } finally {
      setHumanizing(false);
    }
  };

  // 切换章节时清除检测结果
  const handleSelectChapterWithReset = (ch: BidChapter) => {
    handleSelectChapter(ch);
    setDetectionResult(null);
  };

  const handleCheckCoverage = async () => {
    setCoverageLoading(true);
    setShowCoverage(true);
    try {
      const res = await api.get(`/bid-projects/${projectId}/coverage-report`);
      setCoverageReport(res.data?.data || null);
    } catch (err: any) {
      toast.error(err.response?.data?.detail || "覆盖率检查失败");
      setCoverageReport(null);
    } finally {
      setCoverageLoading(false);
    }
  };

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

  // 风险报告跳转高亮：自动选中目标章节并高亮
  useEffect(() => {
    if (!highlightChapterId || chapters.length === 0) return;
    const target = chapters.find((ch) => String(ch.id) === highlightChapterId);
    if (!target) return;
    setSelectedId(target.id);
    setEditContent(target.content || "");
    setHighlightActive(true);
    // 滚动到目标章节
    requestAnimationFrame(() => {
      const el = document.getElementById(`chapter-${target.id}`);
      el?.scrollIntoView({ behavior: "smooth", block: "center" });
    });
    // 3 秒后淡出高亮
    const timer = setTimeout(() => setHighlightActive(false), 3000);
    return () => clearTimeout(timer);
  }, [highlightChapterId, chapters]);

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
      toast.error(err.response?.data?.detail || "初始化失败");
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
      toast.error("保存失败");
    } finally {
      setSaving(false);
    }
  };

  const [genStatus, setGenStatus] = useState("");

  const handleGenerateOne = async () => {
    if (!selectedId) return;
    setGenerating(true);
    setGenStatus("准备生成...");
    setEditContent("");

    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1"}/bid-projects/${projectId}/generate-chapter/${selectedId}/stream`,
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

      let fullContent = "";

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
            if (msg.type === "status") {
              setGenStatus(msg.text);
            } else if (msg.type === "content") {
              fullContent += msg.text;
              setEditContent(fullContent);
            } else if (msg.type === "done") {
              setGenStatus("");
            } else if (msg.type === "error") {
              toast.error(msg.message || "生成失败");
            }
          } catch {
            // skip parse errors
          }
        }
      }

      // 刷新章节列表获取最新状态
      await fetchChapters();
    } catch (err: any) {
      toast.error("生成失败");
    } finally {
      setGenerating(false);
      setGenStatus("");
    }
  };

  const handleGenerateAll = async () => {
    setGeneratingAll(true);
    setProgress({ completed: 0, total: 0, failed: 0 });
    wsConnect(); // 连接 WebSocket 接收管线级进度

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
      wsDisconnect();
    }
  };

  const handleExport = async () => {
    setExporting(true);
    try {
      // 1. 触发导出生成
      await api.post(`/bid-projects/${projectId}/export`);
      // 2. 下载文件
      const res = await api.get(`/bid-projects/${projectId}/download`, {
        responseType: "blob",
      });
      const blob = new Blob([res.data], {
        type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      const disposition = res.headers["content-disposition"];
      const filename = disposition
        ? decodeURIComponent(disposition.split("filename=")[1]?.replace(/"/g, "") || "投标文件.docx")
        : "投标文件.docx";
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (err: any) {
      toast.error(err.response?.data?.detail || "导出失败");
    } finally {
      setExporting(false);
    }
  };

  const handleRewrite = async (action: "polish" | "expand" | "condense" | "rewrite") => {
    if (!selection || !selectedChapter) return;
    setRewriting(true);
    try {
      const res = await api.post(`/bid-projects/${projectId}/rewrite-selection`, {
        text: selection.text,
        action,
        context: `${selectedChapter.chapter_no} ${selectedChapter.title}`,
      });
      const rewritten = res.data?.data?.rewritten;
      if (rewritten) {
        // 替换选中部分
        const newContent =
          editContent.slice(0, selection.start) +
          rewritten +
          editContent.slice(selection.end);
        setEditContent(newContent);
        setSelection(null);
      }
    } catch (err: any) {
      toast.error(err.response?.data?.detail || "AI 重写失败");
    } finally {
      setRewriting(false);
    }
  };

  const handleCustomRewrite = async () => {
    if (!selection || !selectedChapter || !customInstruction.trim()) return;
    setCustomRewriting(true);
    try {
      const res = await api.post(
        `/bid-projects/${projectId}/chapters/${selectedChapter.id}/rewrite`,
        { original_text: selection.text, instruction: customInstruction }
      );
      const rewritten = res.data?.data?.rewritten;
      if (rewritten) {
        const newContent =
          editContent.slice(0, selection.start) +
          rewritten +
          editContent.slice(selection.end);
        setEditContent(newContent);
        setSelection(null);
        setCustomInstruction("");
      }
    } catch (err: any) {
      toast.error(err.response?.data?.detail || "自定义重写失败");
    } finally {
      setCustomRewriting(false);
    }
  };

  // 计算项目整体 AI 占比（加权平均）
  const projectAiRatio = chapters.length > 0
    ? chapters.reduce((sum, ch) => sum + (ch.ai_ratio || 0), 0) / chapters.length
    : 0;
  const aiRatioPct = Math.round(projectAiRatio * 100);
  const aiRatioSafe = aiRatioPct <= 30;

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
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2">
        <div className="flex items-center gap-4">
          <Link href={`/dashboard/bid-projects/${projectId}`}>
            <Button variant="ghost" size="icon">
              <ArrowLeft className="h-5 w-5" />
            </Button>
          </Link>
          <h1 className="text-lg sm:text-xl font-bold text-slate-900">投标文件章节编辑</h1>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {chapters.length === 0 ? (
            <Button onClick={handleInitChapters}>
              <FileText className="mr-2 h-4 w-4" />
              初始化章节
            </Button>
          ) : (
            <>
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
              <Button
                onClick={handleCheckCoverage}
                disabled={coverageLoading || generatingAll}
                variant="outline"
              >
                {coverageLoading ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <CheckCircle2 className="mr-2 h-4 w-4" />
                )}
                {coverageLoading ? "检查中..." : "覆盖率检查"}
              </Button>
              <Button
                onClick={handleExport}
                disabled={exporting || generatingAll}
                variant="outline"
              >
                {exporting ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Download className="mr-2 h-4 w-4" />
                )}
                {exporting ? "导出中..." : "导出 Word"}
              </Button>
            </>
          )}
        </div>
      </div>

      {/* AI 占比仪表盘 */}
      {chapters.length > 0 && (
        <div className={`flex items-center gap-3 rounded-lg border p-3 ${
          aiRatioSafe ? "border-green-200 bg-green-50" : "border-amber-200 bg-amber-50"
        }`}>
          <div className={`text-sm font-medium ${aiRatioSafe ? "text-green-700" : "text-amber-700"}`}>
            {aiRatioSafe ? "✅" : "⚠️"} AI 内容占比
          </div>
          <div className="flex-1">
            <div className="h-2 overflow-hidden rounded-full bg-slate-200">
              <div
                className={`h-full rounded-full transition-all ${
                  aiRatioSafe ? "bg-green-500" : "bg-amber-500"
                }`}
                style={{ width: `${Math.min(aiRatioPct, 100)}%` }}
              />
            </div>
          </div>
          <span className={`text-sm font-bold ${aiRatioSafe ? "text-green-700" : "text-amber-700"}`}>
            {aiRatioPct}%
          </span>
          <span className="text-xs text-slate-500">
            {aiRatioSafe ? "反AI检测安全" : "建议人工润色降低AI占比"}
          </span>
        </div>
      )}

      {/* AI 七层管线实时进度面板 */}
      {generatingAll && <AIPipelineProgress state={pipelineState} />}

      {/* 评分覆盖率热力图 */}
      {showCoverage && (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-medium text-slate-700">评分覆盖率检查</h3>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setShowCoverage(false)}
              className="text-xs text-slate-400"
            >
              收起
            </Button>
          </div>
          {coverageLoading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-6 w-6 animate-spin text-slate-400" />
            </div>
          ) : coverageReport ? (
            <CoverageHeatmap report={coverageReport} />
          ) : (
            <p className="py-4 text-center text-sm text-slate-400">暂无数据</p>
          )}
        </div>
      )}

      {chapters.length > 0 && (
        <div className="flex flex-col md:flex-row gap-4" style={{ height: "calc(100vh - 220px)" }}>
          {/* 左侧章节列表 */}
          <div className="w-full md:w-72 shrink-0 max-h-48 md:max-h-none overflow-y-auto rounded-lg border bg-white">
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
                    id={`chapter-${ch.id}`}
                    onClick={() => handleSelectChapterWithReset(ch)}
                    className={`flex w-full items-start gap-2 rounded-md px-3 py-2 text-left text-sm transition-all duration-500 ${
                      isSelected
                        ? "bg-slate-100 text-slate-900"
                        : "text-slate-600 hover:bg-slate-50"
                    } ${
                      highlightActive && String(ch.id) === highlightChapterId
                        ? "ring-2 ring-red-400 ring-offset-1"
                        : ""
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
                        {/* 来源标签徽章 */}
                        {selectedChapter.source_tags && selectedChapter.source_tags.split(",").filter(Boolean).map((tag) => {
                          const cfg = SOURCE_TAG_CONFIG[tag.trim()];
                          return cfg ? (
                            <Badge key={tag} className={`text-xs ${cfg.color}`}>
                              {cfg.label}
                            </Badge>
                          ) : null;
                        })}
                        {/* 本章 AI 占比 */}
                        {selectedChapter.ai_ratio > 0 && (
                          <span className={`font-medium ${selectedChapter.ai_ratio > 0.3 ? "text-amber-600" : "text-green-600"}`}>
                            AI {Math.round(selectedChapter.ai_ratio * 100)}%
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      {/* AI 划词重写按钮组 — 选中文本时显示 */}
                      {selection && (
                        <div className="flex items-center gap-1 rounded-md border border-blue-200 bg-blue-50 px-2 py-1">
                          {rewriting || customRewriting ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin text-blue-500" />
                          ) : (
                            <>
                              <span className="mr-1 text-xs text-blue-600">AI:</span>
                              <Button size="sm" variant="ghost" className="h-6 px-2 text-xs" onClick={() => handleRewrite("polish")}>润色</Button>
                              <Button size="sm" variant="ghost" className="h-6 px-2 text-xs" onClick={() => handleRewrite("expand")}>扩写</Button>
                              <Button size="sm" variant="ghost" className="h-6 px-2 text-xs" onClick={() => handleRewrite("condense")}>精简</Button>
                              <Button size="sm" variant="ghost" className="h-6 px-2 text-xs" onClick={() => handleRewrite("rewrite")}>重写</Button>
                              <div className="mx-1 h-4 w-px bg-blue-200" />
                              <input
                                type="text"
                                placeholder="自定义指令..."
                                value={customInstruction}
                                onChange={(e) => setCustomInstruction(e.target.value)}
                                onKeyDown={(e) => e.key === "Enter" && handleCustomRewrite()}
                                className="h-6 w-32 rounded border border-blue-300 bg-white px-1.5 text-xs outline-none focus:ring-1 focus:ring-blue-400"
                              />
                              <Button
                                size="sm"
                                variant="ghost"
                                className="h-6 px-2 text-xs text-blue-700"
                                onClick={handleCustomRewrite}
                                disabled={!customInstruction.trim()}
                              >
                                执行
                              </Button>
                            </>
                          )}
                        </div>
                      )}
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
                        {generating && genStatus ? genStatus : selectedChapter.content ? "重新生成" : "AI 生成"}
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
                <CardContent className="flex-1 overflow-hidden p-0 flex flex-col">
                  <div className="flex-1 overflow-hidden">
                    <MarkdownEditor
                      value={editContent}
                      onChange={setEditContent}
                      placeholder="章节内容为空，点击「AI 生成」开始..."
                      onSelectionChange={setSelection}
                    />
                  </div>
                  {/* 反 AI 检测面板 */}
                  {selectedChapter.content && (
                    <div className="shrink-0 border-t px-4 py-3">
                      <AIDetectionPanel
                        result={detectionResult}
                        loading={detectLoading}
                        onDetect={handleDetectAI}
                        onHumanize={handleHumanize}
                        humanizing={humanizing}
                      />
                    </div>
                  )}
                  {/* AI 内容反馈（仅 AI 生成的章节显示） */}
                  {selectedChapter.source === "ai" && selectedChapter.content && (
                    <div className="shrink-0 border-t px-4 py-1">
                      <ChapterFeedback
                        projectId={projectId}
                        chapterNo={selectedChapter.chapter_no}
                        chapterTitle={selectedChapter.title}
                        content={selectedChapter.content}
                      />
                    </div>
                  )}
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
