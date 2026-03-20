"use client";

import { useState, useEffect, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  BookOpen,
  FileCode2,
  LayoutTemplate,
  Plus,
  Search,
  Trash2,
  ChevronDown,
  ChevronRight,
  Loader2,
  Sparkles,
} from "lucide-react";
import api from "@/lib/api";

const TABS = [
  { key: "semantic", label: "语义搜索", icon: Sparkles },
  { key: "cases", label: "工程案例", icon: BookOpen },
  { key: "snippets", label: "章节片段", icon: FileCode2 },
  { key: "templates", label: "文档模板", icon: LayoutTemplate },
] as const;
type Tab = (typeof TABS)[number]["key"];

interface Case {
  id: number;
  title: string;
  mine_name?: string;
  excavation_type?: string;
  rock_class?: string;
  summary?: string;
}
interface Snippet {
  id: number;
  chapter_no: string;
  chapter_name: string;
  content: string;
  sort_order?: number;
}
interface Template {
  id: number;
  name: string;
  description?: string;
  file_url?: string;
}

/** 知识库管理 — 对接 /knowledge/* CRUD API */
export default function KnowledgePage() {
  const [tab, setTab] = useState<Tab>("semantic");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // 数据
  const [cases, setCases] = useState<Case[]>([]);
  const [snippets, setSnippets] = useState<Snippet[]>([]);
  const [snippetPage, setSnippetPage] = useState(1);
  const PAGE_SIZE = 50;

  // 语义搜索状态
  const [semanticQuery, setSemanticQuery] = useState("");
  const [semanticResults, setSemanticResults] = useState<any[]>([]);
  const [searching, setSearching] = useState(false);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [expandedSnippet, setExpandedSnippet] = useState<number | null>(null);

  // 新建表单
  const [showCreate, setShowCreate] = useState(false);
  const [creating, setCreating] = useState(false);

  // 案例表单 — 仅 title 必填，其余 Optional（契合 EngCaseCreate Schema）
  const [caseForm, setCaseForm] = useState({
    title: "",
    mine_name: "",
    excavation_type: "",
    rock_class: "III",
    summary: "",
  });

  // 片段表单 — chapter_no / chapter_name / content 均必填 min_length=1（契合 ChapterSnippetCreate）
  const [snippetForm, setSnippetForm] = useState({
    chapter_no: "",
    chapter_name: "",
    content: "",
    sort_order: 0,
  });

  // 模板表单 — name + file_url 必填（契合 DocTemplateCreate）
  const [templateForm, setTemplateForm] = useState({
    name: "",
    description: "",
    file_url: "",
    is_default: false,
  });

  // 语义搜索
  const handleSemanticSearch = async () => {
    if (!semanticQuery.trim()) return;
    setSearching(true);
    try {
      const res = await api.get("/knowledge/search", { params: { q: semanticQuery, top_k: 15 } });
      setSemanticResults(res.data?.data || []);
    } catch (e: any) {
      alert("搜索失败: " + (e.response?.data?.detail || e.message));
    } finally { setSearching(false); }
  };

  // 统一数据加载
  const fetchData = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      if (tab === "cases") {
        const res = await api.get("/knowledge/cases");
        setCases(res.data?.data || []);
      } else if (tab === "snippets") {
        const res = await api.get("/knowledge/snippets");
        setSnippets(res.data?.data || []);
      } else {
        const res = await api.get("/knowledge/templates");
        setTemplates(res.data?.data || []);
      }
    } catch (e: any) {
      const detail = e.response?.data?.detail || e.message || "加载失败";
      setError(typeof detail === "string" ? detail : JSON.stringify(detail));
    } finally {
      setLoading(false);
    }
  }, [tab]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // ========== 创建案例 ==========
  const createCase = async () => {
    if (!caseForm.title.trim()) {
      alert("案例标题不能为空");
      return;
    }
    setCreating(true);
    try {
      // 构造 payload，过滤空字符串为 null（契合 Optional 字段）
      const payload: Record<string, any> = { title: caseForm.title.trim() };
      if (caseForm.mine_name.trim()) payload.mine_name = caseForm.mine_name.trim();
      if (caseForm.excavation_type.trim()) payload.excavation_type = caseForm.excavation_type.trim();
      if (caseForm.rock_class.trim()) payload.rock_class = caseForm.rock_class.trim();
      if (caseForm.summary.trim()) payload.summary = caseForm.summary.trim();

      await api.post("/knowledge/cases", payload);
      setCaseForm({ title: "", mine_name: "", excavation_type: "", rock_class: "III", summary: "" });
      setShowCreate(false);
      fetchData();
    } catch (e: any) {
      const detail = e.response?.data?.detail;
      alert("创建失败: " + (typeof detail === "string" ? detail : JSON.stringify(detail)));
    } finally {
      setCreating(false);
    }
  };

  // ========== 创建片段 ==========
  const createSnippet = async () => {
    // 前端校验必填字段（契合 ChapterSnippetCreate 的 min_length=1）
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
    } finally {
      setCreating(false);
    }
  };

  // ========== 创建模板 ==========
  const createTemplate = async () => {
    if (!templateForm.name.trim()) { alert("模板名称不能为空"); return; }
    if (!templateForm.file_url.trim()) { alert("模板文件地址不能为空"); return; }
    setCreating(true);
    try {
      await api.post("/knowledge/templates", {
        name: templateForm.name.trim(),
        description: templateForm.description.trim() || null,
        file_url: templateForm.file_url.trim(),
        is_default: templateForm.is_default,
      });
      setTemplateForm({ name: "", description: "", file_url: "", is_default: false });
      setShowCreate(false);
      fetchData();
    } catch (e: any) {
      const detail = e.response?.data?.detail;
      alert("创建失败: " + (typeof detail === "string" ? detail : JSON.stringify(detail)));
    } finally {
      setCreating(false);
    }
  };

  // ========== 删除 ==========
  const handleDelete = async (type: string, id: number) => {
    if (!confirm("确认删除？")) return;
    try {
      await api.delete(`/knowledge/${type}/${id}`);
      fetchData();
    } catch (e: any) {
      alert("删除失败: " + (e.response?.data?.detail || e.message));
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-slate-800 dark:text-white">知识库管理</h2>
          <p className="mt-1 text-sm text-slate-500">工程案例 · 章节片段 · 文档模板</p>
        </div>
        <Button className="gap-2" onClick={() => setShowCreate(!showCreate)}>
          <Plus className="h-4 w-4" />新增
        </Button>
      </div>

      {/* 标签页 */}
      <div className="flex gap-1 rounded-lg border bg-slate-100 p-1 dark:bg-slate-900">
        {TABS.map((t) => (
          <button
            key={t.key}
            className={`flex flex-1 items-center justify-center gap-2 rounded-md px-4 py-2 text-sm transition-colors ${
              tab === t.key ? "bg-white font-medium shadow dark:bg-slate-800" : "text-slate-500 hover:text-slate-700"
            }`}
            onClick={() => { setTab(t.key); setShowCreate(false); setError(""); }}
          >
            <t.icon className="h-4 w-4" /> {t.label}
          </button>
        ))}
      </div>

      {/* 语义搜索 Tab 内容 */}
      {tab === "semantic" && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-violet-500" /> 语义搜索知识库
            </CardTitle>
            <p className="text-xs text-slate-500">输入自然语言查询，向量检索 673 条标准条款 + 知识片段</p>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex gap-2">
              <Input
                placeholder="例如：突出矿井通风要求、高瓦斯支护标准、应急救援预案..."
                value={semanticQuery}
                onChange={(e) => setSemanticQuery(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSemanticSearch()}
                className="flex-1"
              />
              <Button onClick={handleSemanticSearch} disabled={searching} className="gap-2">
                {searching ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
                搜索
              </Button>
            </div>

            {semanticResults.length > 0 ? (
              <div className="space-y-2">
                <p className="text-xs text-slate-500">找到 {semanticResults.length} 条相关结果</p>
                {semanticResults.map((r: any, i: number) => (
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
                        {(r.similarity * 100).toFixed(1)}%
                      </span>
                    </div>
                    <p className="text-xs text-slate-600 leading-relaxed line-clamp-3">{r.content}</p>
                  </div>
                ))}
              </div>
            ) : semanticQuery && !searching ? (
              <div className="text-center py-8 text-slate-400">
                <Search className="h-8 w-8 mx-auto mb-2" />
                <p className="text-sm">未找到相关结果，请尝试其他关键词</p>
              </div>
            ) : null}
          </CardContent>
        </Card>
      )}

      {/* 新建案例表单 */}
      {showCreate && tab === "cases" && (
        <Card className="border-blue-200 bg-blue-50/50">
          <CardContent className="space-y-3 pt-4">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="mb-1 block text-xs font-medium">案例标题 <span className="text-red-500">*</span></label>
                <Input value={caseForm.title} onChange={(e) => setCaseForm({ ...caseForm, title: e.target.value })} placeholder="如：龙固3301回风巷" />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium">矿井名称</label>
                <Input value={caseForm.mine_name} onChange={(e) => setCaseForm({ ...caseForm, mine_name: e.target.value })} placeholder="矿井名称" />
              </div>
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className="mb-1 block text-xs font-medium">围岩级别</label>
                <Input value={caseForm.rock_class} onChange={(e) => setCaseForm({ ...caseForm, rock_class: e.target.value })} placeholder="III" />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium">掘进类型</label>
                <Input value={caseForm.excavation_type} onChange={(e) => setCaseForm({ ...caseForm, excavation_type: e.target.value })} placeholder="如：半煤岩巷" />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium">摘要</label>
                <Input value={caseForm.summary} onChange={(e) => setCaseForm({ ...caseForm, summary: e.target.value })} placeholder="案例简述" />
              </div>
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="outline" size="sm" onClick={() => setShowCreate(false)}>取消</Button>
              <Button size="sm" onClick={createCase} disabled={creating}>
                {creating && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}创建案例
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* 新建片段表单 */}
      {showCreate && tab === "snippets" && (
        <Card className="border-blue-200 bg-blue-50/50">
          <CardContent className="space-y-3 pt-4">
            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className="mb-1 block text-xs font-medium">章节编号 <span className="text-red-500">*</span></label>
                <Input value={snippetForm.chapter_no} onChange={(e) => setSnippetForm({ ...snippetForm, chapter_no: e.target.value })} placeholder="如：5.1" />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium">章节名称 <span className="text-red-500">*</span></label>
                <Input value={snippetForm.chapter_name} onChange={(e) => setSnippetForm({ ...snippetForm, chapter_name: e.target.value })} placeholder="如：顶板管理" />
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
          </CardContent>
        </Card>
      )}

      {/* 新建模板表单 */}
      {showCreate && tab === "templates" && (
        <Card className="border-blue-200 bg-blue-50/50">
          <CardContent className="space-y-3 pt-4">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="mb-1 block text-xs font-medium">模板名称 <span className="text-red-500">*</span></label>
                <Input value={templateForm.name} onChange={(e) => setTemplateForm({ ...templateForm, name: e.target.value })} placeholder="如：掘进作业规程标准模板" />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium">模板文件地址 <span className="text-red-500">*</span></label>
                <Input value={templateForm.file_url} onChange={(e) => setTemplateForm({ ...templateForm, file_url: e.target.value })} placeholder="OSS/S3 文件 URL" />
              </div>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium">描述</label>
              <Input value={templateForm.description} onChange={(e) => setTemplateForm({ ...templateForm, description: e.target.value })} placeholder="模板说明" />
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="outline" size="sm" onClick={() => setShowCreate(false)}>取消</Button>
              <Button size="sm" onClick={createTemplate} disabled={creating}>
                {creating && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}创建模板
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* 搜索 */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
        <Input className="pl-10" placeholder="搜索..." value={search} onChange={(e) => { setSearch(e.target.value); setSnippetPage(1); }} />
      </div>

      {/* 错误提示 */}
      {error && (
        <div className="rounded-md bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="h-8 w-8 animate-spin text-slate-300" />
        </div>
      ) : (
        <>
          {/* 工程案例 */}
          {tab === "cases" && (
            cases.length === 0 ? (
              <Card className="flex h-40 items-center justify-center">
                <div className="text-center text-slate-400">
                  <BookOpen className="mx-auto mb-2 h-10 w-10 opacity-30" />
                  <p className="text-sm">暂无案例，点击「新增」录入</p>
                </div>
              </Card>
            ) : (
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                {cases
                  .filter((c) => !search || c.title.includes(search))
                  .map((c) => (
                    <Card key={c.id}>
                      <CardHeader className="pb-2">
                        <CardTitle className="flex items-center justify-between text-base">
                          <span className="flex items-center gap-2">
                            <BookOpen className="h-4 w-4 text-blue-500" /> {c.title}
                          </span>
                          <Button variant="ghost" size="sm" onClick={() => handleDelete("cases", c.id)}>
                            <Trash2 className="h-3.5 w-3.5 text-red-400" />
                          </Button>
                        </CardTitle>
                      </CardHeader>
                      <CardContent>
                        <div className="mb-2 grid grid-cols-3 gap-2 text-xs text-slate-500">
                          <div>矿井：<span className="font-medium text-slate-700">{c.mine_name || "—"}</span></div>
                          <div>围岩：<span className="font-medium text-slate-700">{c.rock_class || "—"}类</span></div>
                          <div>类型：<span className="font-medium text-slate-700">{c.excavation_type || "—"}</span></div>
                        </div>
                        <p className="text-sm text-slate-600">{c.summary || "暂无摘要"}</p>
                      </CardContent>
                    </Card>
                  ))}
              </div>
            )
          )}

          {/* 章节片段 */}
          {tab === "snippets" && (
            snippets.length === 0 ? (
              <Card className="flex h-40 items-center justify-center">
                <div className="text-center text-slate-400">
                  <FileCode2 className="mx-auto mb-2 h-10 w-10 opacity-30" />
                  <p className="text-sm">暂无片段，点击「新增」录入</p>
                </div>
              </Card>
            ) : (
              <div className="space-y-2">
                {(() => {
                  const filtered = snippets.filter((s) => !search || s.chapter_name.includes(search) || s.content.includes(search));
                  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
                  const paged = filtered.slice((snippetPage - 1) * PAGE_SIZE, snippetPage * PAGE_SIZE);
                  return (
                    <>
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
                            <Button variant="ghost" size="sm" onClick={(e) => { e.stopPropagation(); handleDelete("snippets", s.id); }}>
                              <Trash2 className="h-3.5 w-3.5 text-red-400" />
                            </Button>
                          </div>
                          {expandedSnippet === s.id && (
                            <div className="border-t bg-slate-50 px-4 py-3 text-sm text-slate-600 whitespace-pre-wrap">{s.content}</div>
                          )}
                        </div>
                      ))}
                      {totalPages > 1 && (
                        <div className="flex items-center justify-center gap-2 pt-2">
                          <Button variant="outline" size="sm" disabled={snippetPage <= 1} onClick={() => setSnippetPage(snippetPage - 1)}>上一页</Button>
                          <span className="text-xs text-slate-500">{snippetPage} / {totalPages}</span>
                          <Button variant="outline" size="sm" disabled={snippetPage >= totalPages} onClick={() => setSnippetPage(snippetPage + 1)}>下一页</Button>
                        </div>
                      )}
                    </>
                  );
                })()}
              </div>
            )
          )}

          {/* 文档模板 */}
          {tab === "templates" && (
            templates.length === 0 ? (
              <Card className="flex h-40 items-center justify-center">
                <div className="text-center text-slate-400">
                  <LayoutTemplate className="mx-auto mb-2 h-10 w-10 opacity-30" />
                  <p className="text-sm">暂无模板（模板上传功能开发中）</p>
                </div>
              </Card>
            ) : (
              <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
                {templates.map((t) => (
                  <Card key={t.id}>
                    <CardContent className="flex items-center justify-between py-4">
                      <div>
                        <p className="font-medium">{t.name}</p>
                        <p className="text-xs text-slate-400">{t.description || "—"}</p>
                      </div>
                      <Button variant="ghost" size="sm" onClick={() => handleDelete("templates", t.id)}>
                        <Trash2 className="h-3.5 w-3.5 text-red-400" />
                      </Button>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )
          )}
        </>
      )}
    </div>
  );
}
