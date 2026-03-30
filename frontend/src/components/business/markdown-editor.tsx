"use client";

import { useState, useRef, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Button } from "@/components/ui/button";
import {
  Bold,
  Italic,
  Heading1,
  Heading2,
  List,
  ListOrdered,
  Table,
  Minus,
  Eye,
  Pencil,
  Columns2,
  Maximize2,
  Minimize2,
} from "lucide-react";

interface MarkdownEditorProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  /** 当用户选中文本时回调，传递 { text, start, end } */
  onSelectionChange?: (selection: { text: string; start: number; end: number } | null) => void;
}

type ViewMode = "edit" | "preview" | "split";

const TOOLBAR_ACTIONS = [
  { icon: Bold, label: "加粗", prefix: "**", suffix: "**", placeholder: "粗体文本" },
  { icon: Italic, label: "斜体", prefix: "*", suffix: "*", placeholder: "斜体文本" },
  { icon: Heading1, label: "一级标题", prefix: "# ", suffix: "", placeholder: "标题" },
  { icon: Heading2, label: "二级标题", prefix: "## ", suffix: "", placeholder: "子标题" },
  { icon: List, label: "无序列表", prefix: "- ", suffix: "", placeholder: "列表项" },
  { icon: ListOrdered, label: "有序列表", prefix: "1. ", suffix: "", placeholder: "列表项" },
  { icon: Minus, label: "分隔线", prefix: "\n---\n", suffix: "", placeholder: "" },
];

const TABLE_TEMPLATE = `\n| 项目 | 内容 | 备注 |\n| --- | --- | --- |\n| | | |\n| | | |\n`;

export default function MarkdownEditor({
  value,
  onChange,
  placeholder = "输入 Markdown 内容...",
  onSelectionChange,
}: MarkdownEditorProps) {
  const [viewMode, setViewMode] = useState<ViewMode>("split");
  const [isFullscreen, setIsFullscreen] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const insertMarkdown = useCallback(
    (prefix: string, suffix: string, placeholder: string) => {
      const ta = textareaRef.current;
      if (!ta) return;

      const start = ta.selectionStart;
      const end = ta.selectionEnd;
      const selected = value.slice(start, end);
      const insert = selected || placeholder;
      const newValue =
        value.slice(0, start) + prefix + insert + suffix + value.slice(end);
      onChange(newValue);

      // 恢复光标位置
      requestAnimationFrame(() => {
        ta.focus();
        const cursorPos = start + prefix.length + insert.length + suffix.length;
        ta.setSelectionRange(cursorPos, cursorPos);
      });
    },
    [value, onChange]
  );

  const insertTable = useCallback(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    const pos = ta.selectionStart;
    const newValue = value.slice(0, pos) + TABLE_TEMPLATE + value.slice(pos);
    onChange(newValue);
  }, [value, onChange]);

  const handleSelectionChange = useCallback(() => {
    if (!onSelectionChange) return;
    const ta = textareaRef.current;
    if (!ta) return;
    const start = ta.selectionStart;
    const end = ta.selectionEnd;
    if (start !== end) {
      onSelectionChange({ text: value.slice(start, end), start, end });
    } else {
      onSelectionChange(null);
    }
  }, [value, onSelectionChange]);

  const containerClass = isFullscreen
    ? "fixed inset-0 z-50 flex flex-col bg-white"
    : "flex flex-col h-full";

  return (
    <div className={containerClass}>
      {/* 工具栏 */}
      <div className="flex items-center gap-1 border-b bg-slate-50 px-2 py-1">
        {TOOLBAR_ACTIONS.map((action) => (
          <Button
            key={action.label}
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            title={action.label}
            onClick={() =>
              insertMarkdown(action.prefix, action.suffix, action.placeholder)
            }
          >
            <action.icon className="h-3.5 w-3.5" />
          </Button>
        ))}
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7"
          title="插入表格"
          onClick={insertTable}
        >
          <Table className="h-3.5 w-3.5" />
        </Button>

        <div className="mx-2 h-4 w-px bg-slate-200" />

        {/* 视图模式切换 */}
        <Button
          variant={viewMode === "edit" ? "secondary" : "ghost"}
          size="icon"
          className="h-7 w-7"
          title="编辑模式"
          onClick={() => setViewMode("edit")}
        >
          <Pencil className="h-3.5 w-3.5" />
        </Button>
        <Button
          variant={viewMode === "split" ? "secondary" : "ghost"}
          size="icon"
          className="h-7 w-7"
          title="分栏模式"
          onClick={() => setViewMode("split")}
        >
          <Columns2 className="h-3.5 w-3.5" />
        </Button>
        <Button
          variant={viewMode === "preview" ? "secondary" : "ghost"}
          size="icon"
          className="h-7 w-7"
          title="预览模式"
          onClick={() => setViewMode("preview")}
        >
          <Eye className="h-3.5 w-3.5" />
        </Button>

        <div className="flex-1" />

        <span className="mr-2 text-xs text-slate-400">
          {value.length} 字
        </span>

        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7"
          title={isFullscreen ? "退出全屏" : "全屏编辑"}
          onClick={() => setIsFullscreen(!isFullscreen)}
        >
          {isFullscreen ? (
            <Minimize2 className="h-3.5 w-3.5" />
          ) : (
            <Maximize2 className="h-3.5 w-3.5" />
          )}
        </Button>
      </div>

      {/* 编辑区 */}
      <div className="flex flex-1 overflow-hidden">
        {/* 编辑面板 */}
        {(viewMode === "edit" || viewMode === "split") && (
          <div
            className={`${
              viewMode === "split" ? "w-1/2 border-r" : "w-full"
            } overflow-hidden`}
          >
            <textarea
              ref={textareaRef}
              className="h-full w-full resize-none border-0 bg-white p-4 font-mono text-sm outline-none focus:ring-0"
              placeholder={placeholder}
              value={value}
              onChange={(e) => onChange(e.target.value)}
              onSelect={handleSelectionChange}
              onMouseUp={handleSelectionChange}
            />
          </div>
        )}

        {/* 预览面板 */}
        {(viewMode === "preview" || viewMode === "split") && (
          <div
            className={`${
              viewMode === "split" ? "w-1/2" : "w-full"
            } overflow-y-auto bg-white p-4`}
          >
            {value ? (
              <div className="prose prose-sm prose-slate max-w-none">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {value}
                </ReactMarkdown>
              </div>
            ) : (
              <p className="text-sm text-slate-300">预览区域</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
