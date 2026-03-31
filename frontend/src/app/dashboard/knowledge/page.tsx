"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  BookOpen,
  FileCode2,
  Plus,
  Search,
  Sparkles,
  Scale,
  FileText,
} from "lucide-react";

import SemanticSearch from "./_components/SemanticSearch";
import StandardsList from "./_components/StandardsList";
import CasesList from "./_components/CasesList";
import SnippetsList from "./_components/SnippetsList";
import BidDocsList from "./_components/BidDocsList";

const TABS = [
  { key: "semantic", label: "语义搜索", icon: Sparkles },
  { key: "standards", label: "法规标准", icon: Scale },
  { key: "biddocs", label: "优选标书", icon: FileText },
  { key: "cases", label: "工程案例", icon: BookOpen },
  { key: "snippets", label: "章节片段", icon: FileCode2 },
] as const;
type Tab = (typeof TABS)[number]["key"];

/** 知识库管理 — 精简主壳 + 5 个子组件 */
export default function KnowledgePage() {
  const [tab, setTab] = useState<Tab>("semantic");
  const [search, setSearch] = useState("");
  const [showCreate, setShowCreate] = useState(false);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-slate-800 dark:text-white">知识库管理</h2>
          <p className="mt-1 text-sm text-slate-500">法规标准 · 工程案例 · 章节片段</p>
        </div>
        {tab !== "semantic" && (
          <Button className="gap-2" onClick={() => setShowCreate(!showCreate)}>
            <Plus className="h-4 w-4" />
            {tab === "standards" ? "上传法规" : tab === "biddocs" ? "上传标书" : "新增"}
          </Button>
        )}
      </div>

      {/* 标签页 */}
      <div className="flex gap-1 rounded-lg border bg-slate-100 p-1 dark:bg-slate-900">
        {TABS.map((t) => (
          <button
            key={t.key}
            className={`flex flex-1 items-center justify-center gap-2 rounded-md px-4 py-2 text-sm transition-colors ${
              tab === t.key ? "bg-white font-medium shadow dark:bg-slate-800" : "text-slate-500 hover:text-slate-700"
            }`}
            onClick={() => { setTab(t.key); setShowCreate(false); }}
          >
            <t.icon className="h-4 w-4" /> {t.label}
          </button>
        ))}
      </div>

      {/* 搜索（语义搜索 Tab 有自己的搜索，不显示全局搜索） */}
      {tab !== "semantic" && (
        <div className="relative">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <Input className="pl-10" placeholder="搜索..." value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
      )}

      {/* Tab 内容 */}
      {tab === "semantic" && <SemanticSearch />}
      {tab === "standards" && (
        <StandardsList search={search} showCreate={showCreate} setShowCreate={setShowCreate} />
      )}
      {tab === "biddocs" && (
        <BidDocsList search={search} showCreate={showCreate} setShowCreate={setShowCreate} />
      )}
      {tab === "cases" && (
        <CasesList search={search} showCreate={showCreate} setShowCreate={setShowCreate} />
      )}
      {tab === "snippets" && (
        <SnippetsList search={search} showCreate={showCreate} setShowCreate={setShowCreate} />
      )}
      {/* 文档模板 Tab 已移除 — 后端 bid_doc_exporter.py 未使用 templates 表 */}
    </div>
  );
}
