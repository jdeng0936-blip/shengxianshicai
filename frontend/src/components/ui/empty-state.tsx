"use client";

import { FileQuestion, Inbox, Search } from "lucide-react";

const ICON_MAP = {
  default: Inbox,
  search: Search,
  file: FileQuestion,
} as const;

interface EmptyStateProps {
  icon?: keyof typeof ICON_MAP;
  title?: string;
  description?: string;
  action?: React.ReactNode;
}

export default function EmptyState({
  icon = "default",
  title = "暂无数据",
  description,
  action,
}: EmptyStateProps) {
  const Icon = ICON_MAP[icon];

  return (
    <div className="flex flex-col items-center justify-center py-12 text-center">
      <div className="flex h-14 w-14 items-center justify-center rounded-full bg-slate-100">
        <Icon className="h-7 w-7 text-slate-400" />
      </div>
      <h3 className="mt-4 text-sm font-medium text-slate-700">{title}</h3>
      {description && (
        <p className="mt-1 text-sm text-slate-400">{description}</p>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
