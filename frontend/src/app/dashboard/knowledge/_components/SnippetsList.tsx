"use client";

import { useState, useEffect, useCallback } from "react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  FileCode2,
  ChevronDown,
  ChevronRight,
  Trash2,
  Loader2,
} from "lucide-react";
import api from "@/lib/api";

interface Snippet {
  id: number;
  chapter_no: string;
  chapter_name: string;
  content: string;
  sort_order?: number;
}

interface SnippetsListProps {
  search: string;
  showCreate: boolean;
  setShowCreate: (show: boolean) => void;
}

const PAGE_SIZE = 50;

export default function SnippetsList({ search, showCreate, setShowCreate }: SnippetsListProps) {
  const [snippets, setSnippets] = useState<Snippet[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [expandedSnippet, setExpandedSnippet] = useState<number | null>(null);
  const [snippetPage, setSnippetPage] = useState(1);
  const [snippetForm, setSnippetForm] = useState({ chapter_no: "", chapter_name: "", content: "", sort_order: 0 });

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get("/knowledge/snippets");
      setSnippets(res.data?.data || []);
    } catch { setSnippets([]); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);
  useEffect(() => { setSnippetPage(1); }, [search]);

  const createSnippet = async () => {
    if (!snippetForm.chapter_no.trim()) { alert("章节编号不能为空"); return; }
    if (!snippetForm.chapter_name.trim()) { alert("章节名称不能为空"); return; }
    if (!snippetForm.content.trim()) { alert("内容不能为空"); return; }
    setCreating(true);
    try {
      await api.post("/knowledge/snippets", {
        chapter_no: snippetForm.chapter_no.trim(),
        chapter_name: snippetForm.chapter_name.trim(),
        content: snippetForm.content.trim(),
        sort_order: snippetForm.sort_order || 0,
      });
      setSnippetForm({ chapter_no: "", chapter_name: "", content: "", sort_order: 0 });
      setShowCreate(false);
      fetchData();
    } catch (e: any) {
      const detail = e.response?.data?.detail;
      alert("创建失败: " + (typeof detail === "string" ? detail : JSON.stringify(detail)));
    } finally { setCreating(false); }
  };

  const handleDelete = async (id: number) => {
    if (!confirm("确认删除？")) return;
    try { await api.delete(`/knowledge/snippets/${id}`); fetchData(); }
    catch (e: any) { alert("删除失败: " + (e.response?.data?.detail || e.message)); }
  };

  if (loading) {
    return <div className="flex items-center justify-center py-20"><Loader2 className="h-8 w-8 animate-spin text-slate-300" /></div>;
  }

  const filtered = snippets.filter((s) => !search || s.chapter_name.includes(search) || s.content.includes(search));
  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
  const paged = filtered.slice((snippetPage - 1) * PAGE_SIZE, snippetPage * PAGE_SIZE);

  return (
    <>
      {showCreate && (
        <Card className="border-blue-200 bg-blue-50/50">
          <div className="space-y-3 p-4">
            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className="mb-1 block text-xs font-medium">章节编号 <span className="text-red-500">*</span></label>
                <Input value={snippetForm.chapter_no} onChange={(e) => setSnippetForm({ ...snippetForm, chapter_no: e.target.value })} placeholder="如：5.1" />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium">章节名称 <span className="text-red-500">*</span></label>
                <Input value={snippetForm.chapter_name} onChange={(e) => setSnippetForm({ ...snippetForm, chapter_name: e.target.value })} placeholder="如：食材验收管理" />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium">排序权重</label>
                <Input type="number" value={snippetForm.sort_order} onChange={(e) => setSnippetForm({ ...snippetForm, sort_order: parseInt(e.target.value) || 0 })} />
              </div>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium">内容 <span className="text-red-500">*</span></label>
              <textarea
                className="w-full rounded-md border px-3 py-2 text-sm"
                rows={3}
                value={snippetForm.content}
                onChange={(e) => setSnippetForm({ ...snippetForm, content: e.target.value })}
                placeholder="规程正文内容..."
              />
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="outline" size="sm" onClick={() => setShowCreate(false)}>取消</Button>
              <Button size="sm" onClick={createSnippet} disabled={creating}>
                {creating && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}创建片段
              </Button>
            </div>
          </div>
        </Card>
      )}

      {snippets.length === 0 ? (
        <Card className="flex h-40 items-center justify-center">
          <div className="text-center text-slate-400">
            <FileCode2 className="mx-auto mb-2 h-10 w-10 opacity-30" />
            <p className="text-sm">暂无片段，点击「新增」录入</p>
          </div>
        </Card>
      ) : (
        <div className="space-y-2">
          <div className="flex items-center justify-between rounded-lg bg-slate-50 px-4 py-2 text-sm text-slate-500 dark:bg-slate-900">
            <span>共 <strong className="text-slate-700">{filtered.length}</strong> 条片段</span>
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" disabled={snippetPage <= 1} onClick={() => setSnippetPage(snippetPage - 1)}>上一页</Button>
              <span className="text-xs">{snippetPage} / {totalPages || 1}</span>
              <Button variant="outline" size="sm" disabled={snippetPage >= totalPages} onClick={() => setSnippetPage(snippetPage + 1)}>下一页</Button>
            </div>
          </div>
          {paged.map((s) => (
            <div key={s.id} className="overflow-hidden rounded-lg border">
              <div
                className="flex cursor-pointer items-center justify-between px-4 py-3 transition-colors hover:bg-slate-50"
                onClick={() => setExpandedSnippet(expandedSnippet === s.id ? null : s.id)}
              >
                <div className="flex items-center gap-3">
                  {expandedSnippet === s.id ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                  <span className="font-mono text-xs text-slate-400">{s.chapter_no}</span>
                  <span className="font-medium">{s.chapter_name}</span>
                </div>
                <Button variant="ghost" size="sm" onClick={(e) => { e.stopPropagation(); handleDelete(s.id); }}>
                  <Trash2 className="h-3.5 w-3.5 text-red-400" />
                </Button>
              </div>
              {expandedSnippet === s.id && (
                <div className="border-t bg-slate-50 px-4 py-3 text-sm text-slate-600 whitespace-pre-wrap">{s.content}</div>
              )}
            </div>
          ))}
        </div>
      )}
    </>
  );
}
