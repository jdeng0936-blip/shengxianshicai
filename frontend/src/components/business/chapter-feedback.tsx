"use client";

/**
 * ChapterFeedback — 章节级反馈组件
 *
 * 架构铁律：AI 产出必须有「采纳/修改/拒绝」差分交互。
 * 用户操作后自动调用 POST /api/v1/feedback 持久化。
 */
import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Check,
  Pencil,
  X,
  Loader2,
  MessageSquare,
  ThumbsUp,
  ThumbsDown,
} from "lucide-react";
import api from "@/lib/api";

interface ChapterFeedbackProps {
  projectId: string | number;
  chapterNo: string;
  chapterTitle: string;
  content: string;
}

type FeedbackAction = "accept" | "edit" | "reject";
type FeedbackStatus = "idle" | "editing" | "submitting" | "submitted";

export default function ChapterFeedback({
  projectId,
  chapterNo,
  chapterTitle,
  content,
}: ChapterFeedbackProps) {
  const [status, setStatus] = useState<FeedbackStatus>("idle");
  const [action, setAction] = useState<FeedbackAction | null>(null);
  const [editedText, setEditedText] = useState(content);
  const [comment, setComment] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const submitFeedback = async (
    feedbackAction: FeedbackAction,
    modifiedText: string
  ) => {
    setSubmitting(true);
    setStatus("submitting");
    try {
      await api.post("/feedback", {
        project_id: Number(projectId),
        chapter_no: chapterNo,
        chapter_title: chapterTitle,
        original_text: content,
        modified_text: modifiedText,
        action: feedbackAction,
        comment: comment || null,
      });
      setAction(feedbackAction);
      setStatus("submitted");
    } catch (e: any) {
      console.error("反馈提交失败:", e);
      setStatus("idle");
    } finally {
      setSubmitting(false);
    }
  };

  // 已提交 → 显示状态标签
  if (status === "submitted") {
    const labels: Record<FeedbackAction, { text: string; cls: string }> = {
      accept: {
        text: "✅ 已采纳",
        cls: "bg-green-50 text-green-700 border-green-200",
      },
      edit: {
        text: "✏️ 已修改",
        cls: "bg-blue-50 text-blue-700 border-blue-200",
      },
      reject: {
        text: "❌ 已拒绝",
        cls: "bg-red-50 text-red-700 border-red-200",
      },
    };
    const badge = labels[action!];
    return (
      <div
        className={`mt-3 flex items-center justify-between rounded-lg border px-3 py-2 text-sm ${badge.cls}`}
      >
        <span className="font-medium">{badge.text}</span>
        <button
          className="text-xs underline opacity-60 hover:opacity-100"
          onClick={() => {
            setStatus("idle");
            setAction(null);
          }}
        >
          重新评价
        </button>
      </div>
    );
  }

  // 正在编辑 → 文本编辑区
  if (status === "editing") {
    return (
      <div className="mt-3 space-y-3">
        <div className="rounded-lg border border-blue-200 bg-blue-50/30 p-1">
          <textarea
            className="w-full min-h-[120px] rounded-md border-0 bg-transparent px-3 py-2 text-sm leading-relaxed focus:outline-none focus:ring-0 resize-y"
            value={editedText}
            onChange={(e) => setEditedText(e.target.value)}
            placeholder="修改后的内容..."
          />
        </div>
        <input
          className="w-full rounded-md border px-3 py-1.5 text-sm text-slate-600 placeholder:text-slate-300 focus:border-blue-300 focus:outline-none"
          placeholder="修改原因（可选）"
          value={comment}
          onChange={(e) => setComment(e.target.value)}
        />
        <div className="flex gap-2">
          <Button
            size="sm"
            className="gap-1.5 bg-blue-600 hover:bg-blue-700"
            disabled={submitting}
            onClick={() => submitFeedback("edit", editedText)}
          >
            {submitting ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Check className="h-3.5 w-3.5" />
            )}
            提交修改
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              setStatus("idle");
              setEditedText(content);
              setComment("");
            }}
          >
            取消
          </Button>
        </div>
      </div>
    );
  }

  // 默认状态 → 三个操作按钮
  return (
    <div className="mt-3 flex items-center gap-2 border-t border-dashed pt-3">
      <span className="mr-1 text-xs text-slate-400 flex items-center gap-1">
        <MessageSquare className="h-3 w-3" />
        AI 内容评价:
      </span>
      <Button
        size="sm"
        variant="outline"
        className="h-7 gap-1 text-xs text-green-600 border-green-200 hover:bg-green-50 hover:text-green-700"
        disabled={submitting}
        onClick={() => submitFeedback("accept", content)}
      >
        {submitting ? (
          <Loader2 className="h-3 w-3 animate-spin" />
        ) : (
          <ThumbsUp className="h-3 w-3" />
        )}
        采纳
      </Button>
      <Button
        size="sm"
        variant="outline"
        className="h-7 gap-1 text-xs text-blue-600 border-blue-200 hover:bg-blue-50 hover:text-blue-700"
        onClick={() => setStatus("editing")}
      >
        <Pencil className="h-3 w-3" />
        修改
      </Button>
      <Button
        size="sm"
        variant="outline"
        className="h-7 gap-1 text-xs text-red-500 border-red-200 hover:bg-red-50 hover:text-red-600"
        disabled={submitting}
        onClick={() => submitFeedback("reject", content)}
      >
        {submitting ? (
          <Loader2 className="h-3 w-3 animate-spin" />
        ) : (
          <ThumbsDown className="h-3 w-3" />
        )}
        拒绝
      </Button>
    </div>
  );
}
