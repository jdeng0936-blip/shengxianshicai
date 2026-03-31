"use client";

import { useState, useEffect, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  BookOpen,
  FileCode2,
  LayoutTemplate,
  Search,
  Loader2,
  Sparkles,
  Scale,
  ChevronDown,
  ChevronRight,
  Trash2,
} from "lucide-react";
import api from "@/lib/api";

interface SemanticResult {
  type: string;
  title: string;
  clause_no?: string;
  content: string;
  distance: number;
}

export default function SemanticSearchTab() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SemanticResult[]>([]);
  const [searching, setSearching] = useState(false);

  const handleSearch = async () => {
    if (!query.trim()) return;
    setSearching(true);
    try {
      const res = await api.get("/knowledge/search", { params: { q: query, top_k: 15 } });
      setResults(res.data?.data || []);
    } catch (e: any) {
      alert("搜索失败: " + (e.response?.data?.detail || e.message));
    } finally {
      setSearching(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-violet-500" /> 语义搜索知识库
        </CardTitle>
        <p className="text-xs text-slate-500">输入自然语言查询，向量检索标准条款 + 知识片段</p>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex gap-2">
          <Input
            placeholder="例如：冷链运输温度要求、食品留样制度、学校食堂管理规定..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSearch()}
            className="flex-1"
          />
          <Button onClick={handleSearch} disabled={searching} className="gap-2">
            {searching ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
            搜索
          </Button>
        </div>

        {results.length > 0 ? (
          <div className="space-y-2">
            <p className="text-xs text-slate-500">找到 {results.length} 条相关结果</p>
            {results.map((r, i) => (
              <div key={i} className="rounded-lg border p-3 hover:bg-slate-50 transition-colors">
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-2">
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                      r.type === "标准条款" ? "bg-blue-100 text-blue-700" : "bg-purple-100 text-purple-700"
                    }`}>{r.type}</span>
                    <span className="text-sm font-medium text-slate-700">{r.title}</span>
                    {r.clause_no && <span className="text-xs text-slate-400">{r.clause_no}</span>}
                  </div>
                  <span className="text-xs font-mono text-emerald-600">
                    {((1 - r.distance) * 100).toFixed(1)}%
                  </span>
                </div>
                <p className="text-xs text-slate-600 leading-relaxed line-clamp-3">{r.content}</p>
              </div>
            ))}
          </div>
        ) : query && !searching ? (
          <div className="text-center py-8 text-slate-400">
            <Search className="h-8 w-8 mx-auto mb-2" />
            <p className="text-sm">未找到相关结果，请尝试其他关键词</p>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
