"use client";

import { useState, useCallback, useRef } from "react";
import { Upload, FileText, X, AlertCircle } from "lucide-react";
import { Progress } from "@/components/ui/progress";

interface FileDropZoneProps {
  /** 允许的文件扩展名，如 [".pdf", ".docx", ".doc"] */
  accept: string[];
  /** 选中文件回调 */
  onFileSelect: (file: File) => void;
  /** 移除文件回调 */
  onFileRemove?: () => void;
  /** 当前选中的文件 */
  file?: File | null;
  /** 上传进度 0-100 */
  progress?: number;
  /** 是否正在上传 */
  uploading?: boolean;
  /** 错误信息 */
  error?: string;
  /** 提示文字 */
  hint?: string;
  /** 是否禁用 */
  disabled?: boolean;
  className?: string;
}

export default function FileDropZone({
  accept,
  onFileSelect,
  onFileRemove,
  file = null,
  progress = 0,
  uploading = false,
  error = "",
  hint,
  disabled = false,
  className = "",
}: FileDropZoneProps) {
  const [isDragOver, setIsDragOver] = useState(false);
  const [localError, setLocalError] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const acceptStr = accept.join(",");
  const acceptLabel = accept.join(" / ");
  const displayError = error || localError;

  const validateFile = useCallback(
    (f: File): boolean => {
      const ext = f.name.substring(f.name.lastIndexOf(".")).toLowerCase();
      if (!accept.includes(ext)) {
        setLocalError(`不支持的文件格式: ${ext}，仅支持 ${acceptLabel}`);
        return false;
      }
      setLocalError("");
      return true;
    },
    [accept, acceptLabel]
  );

  const handleFileSelect = useCallback(
    (files: FileList | null) => {
      if (!files || files.length === 0) return;
      const f = files[0];
      if (validateFile(f)) {
        onFileSelect(f);
      }
    },
    [validateFile, onFileSelect]
  );

  const handleDragOver = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      if (!disabled && !uploading) setIsDragOver(true);
    },
    [disabled, uploading]
  );

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      setIsDragOver(false);
      if (disabled || uploading) return;
      const files = e.dataTransfer.files;
      if (files && files.length > 0) {
        const f = files[0];
        if (validateFile(f)) {
          onFileSelect(f);
        }
      }
    },
    [disabled, uploading, validateFile, onFileSelect]
  );

  const handleClick = useCallback(() => {
    if (!disabled && !uploading) {
      inputRef.current?.click();
    }
  }, [disabled, uploading]);

  const handleRemove = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      setLocalError("");
      onFileRemove?.();
    },
    [onFileRemove]
  );

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div className={className}>
      <div
        className={`relative flex flex-col items-center justify-center rounded-lg border-2 border-dashed p-6 transition-colors ${
          disabled || uploading
            ? "cursor-not-allowed opacity-60"
            : "cursor-pointer"
        } ${
          isDragOver
            ? "border-blue-500 bg-blue-50 dark:bg-blue-950"
            : file
            ? "border-green-400 bg-green-50 dark:bg-green-950"
            : "border-slate-300 hover:border-blue-400 hover:bg-slate-50 dark:border-slate-700 dark:hover:border-blue-500 dark:hover:bg-slate-900"
        }`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={handleClick}
      >
        <input
          ref={inputRef}
          type="file"
          accept={acceptStr}
          className="hidden"
          onChange={(e) => {
            handleFileSelect(e.target.files);
            if (inputRef.current) inputRef.current.value = "";
          }}
        />

        {file ? (
          <div className="flex w-full items-center gap-3">
            <FileText className="h-8 w-8 shrink-0 text-green-500" />
            <div className="min-w-0 flex-1">
              <p className="truncate font-medium text-slate-800 dark:text-white">
                {file.name}
              </p>
              <p className="text-xs text-slate-500">{formatSize(file.size)}</p>
            </div>
            {!uploading && (
              <button
                className="shrink-0 rounded-full p-1 hover:bg-slate-200 dark:hover:bg-slate-700"
                onClick={handleRemove}
              >
                <X className="h-4 w-4 text-slate-400" />
              </button>
            )}
          </div>
        ) : (
          <>
            <Upload className="mb-2 h-10 w-10 text-slate-400" />
            <p className="text-sm font-medium text-slate-600 dark:text-slate-300">
              拖拽文件到此处，或点击选择文件
            </p>
            <p className="mt-1 text-xs text-slate-400">
              {hint || `支持 ${acceptLabel} 格式`}
            </p>
          </>
        )}
      </div>

      {/* 上传进度 */}
      {uploading && (
        <div className="mt-3 space-y-1.5">
          <div className="flex items-center justify-between text-xs text-slate-500">
            <span>正在上传...</span>
            <span>{Math.round(progress)}%</span>
          </div>
          <Progress value={progress} />
        </div>
      )}

      {/* 错误提示 */}
      {displayError && (
        <div className="mt-2 flex items-center gap-2 rounded-md bg-red-50 p-2.5 text-sm text-red-600 dark:bg-red-950 dark:text-red-400">
          <AlertCircle className="h-4 w-4 shrink-0" />
          {displayError}
        </div>
      )}
    </div>
  );
}
