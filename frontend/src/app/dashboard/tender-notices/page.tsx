"use client";

import { useState, useEffect, useCallback } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  Radar,
  Loader2,
  Search,
  XCircle,
  Sparkles,
  Building2,
  ArrowUpRight,
  ExternalLink,
  Globe,
  Database,
  Trash2,
  CheckSquare,
  Square,
} from "lucide-react";
import Link from "next/link";
import api from "@/lib/api";

interface TenderNotice {
  id: number;
  title: string;
  buyer_name?: string;
  buyer_region?: string;
  customer_type?: string;
  budget_amount?: number;
  deadline?: string;
  publish_date?: string;
  match_score?: number;
  match_level?: string;
  status: string;
  recommendation?: string;
  source?: string;
  source_url?: string;
  created_at?: string;
}

interface Stats {
  total: number;
  new_count: number;
  recommended: number;
  risky: number;
  converted: number;
}

interface Enterprise {
  id: number;
  name: string;
}

interface Region {
  code: string;
  name: string;
}

const MATCH_LEVEL_MAP: Record<string, { label: string; color: string }> = {
  high: { label: "强烈推荐", color: "bg-green-100 text-green-700 border-green-200" },
  medium: { label: "可以考虑", color: "bg-amber-100 text-amber-700 border-amber-200" },
  low: { label: "匹配度低", color: "bg-slate-100 text-slate-600 border-slate-200" },
  risky: { label: "风险较高", color: "bg-red-100 text-red-700 border-red-200" },
};

const STATUS_MAP: Record<string, { label: string; color: string }> = {
  new: { label: "待分析", color: "bg-blue-100 text-blue-700" },
  analyzing: { label: "分析中", color: "bg-blue-100 text-blue-700" },
  analyzed: { label: "已分析", color: "bg-slate-100 text-slate-600" },
  recommended: { label: "推荐", color: "bg-green-100 text-green-700" },
  dismissed: { label: "已忽略", color: "bg-slate-100 text-slate-400" },
  converted: { label: "已转化", color: "bg-purple-100 text-purple-700" },
  expired: { label: "已过期", color: "bg-red-100 text-red-600" },
};

const CUSTOMER_LABELS: Record<string, string> = {
  school: "学校", hospital: "医院", government: "政府",
  enterprise: "企业", canteen: "团餐",
};

const SOURCE_MAP: Record<string, { label: string; icon: any; color: string }> = {
  ccgp: { label: "政府采购网", icon: Globe, color: "text-blue-500" },
  anhui_gp: { label: "安徽省采购网", icon: Globe, color: "text-blue-500" },
  hf_ggzy: { label: "合肥交易中心", icon: Globe, color: "text-blue-500" },
  anhui_ggzy: { label: "安徽交易集团", icon: Globe, color: "text-blue-500" },
  paste: { label: "粘贴导入", icon: Sparkles, color: "text-violet-500" },
  manual: { label: "手动录入", icon: Building2, color: "text-slate-500" },
};

export default function TenderNoticesPage() {
  const [notices, setNotices] = useState<TenderNotice[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [enterprises, setEnterprises] = useState<Enterprise[]>([]);
  const [regions, setRegions] = useState<Region[]>([]);
  const [loading, setLoading] = useState(true);
  const [fetching, setFetching] = useState(false);
  const [filterStatus, setFilterStatus] = useState("");
  const [search, setSearch] = useState("");
  const [selectedEnterprise, setSelectedEnterprise] = useState<number | null>(null);
  const [selectedRegion, setSelectedRegion] = useState("全国");

  // 粘贴公告
  const [showPaste, setShowPaste] = useState(false);
  const [pasteText, setPasteText] = useState("");
  const [pasteUrl, setPasteUrl] = useState("");
  const [parsing, setParsing] = useState(false);

  // 多选状态
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [deleting, setDeleting] = useState(false);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [noticeRes, statsRes, entRes, regRes] = await Promise.all([
        api.get("/tender-notices", { params: { page: 1, page_size: 50, status: filterStatus || undefined } }),
        api.get("/tender-notices/stats"),
        api.get("/enterprises"),
        api.get("/tender-notices/regions").catch(() => ({ data: { data: [] } })),
      ]);
      setNotices(noticeRes.data?.data?.items || []);
      setStats(statsRes.data?.data || null);
      const ents = entRes.data?.data || [];
      setEnterprises(ents);
      if (ents.length > 0 && !selectedEnterprise) {
        setSelectedEnterprise(ents[0].id);
      }
      setRegions(regRes.data?.data || []);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [filterStatus, selectedEnterprise]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleFetch = async () => {
    if (!selectedEnterprise) {
      alert("请先创建或选择一个企业（在任意投标项目中关联企业）");
      return;
    }
    setFetching(true);
    try {
      await api.post("/tender-notices/crawl-all", {
        enterprise_id: selectedEnterprise,
        region: selectedRegion !== "全国" ? selectedRegion : undefined,
      });
      await fetchData();
    } catch (err: any) {
      alert(err.response?.data?.detail || "抓取失败");
    } finally {
      setFetching(false);
    }
  };

  const handlePaste = async () => {
    if (!selectedEnterprise || !pasteText.trim()) return;
    setParsing(true);
    try {
      await api.post("/tender-notices/parse-text", {
        raw_text: pasteText,
        enterprise_id: selectedEnterprise,
        source_url: pasteUrl || undefined,
      });
      setPasteText("");
      setPasteUrl("");
      setShowPaste(false);
      await fetchData();
    } catch (err: any) {
      alert(err.response?.data?.detail || "解析失败");
    } finally {
      setParsing(false);
    }
  };

  // 单条删除
  const handleDelete = async (id: number) => {
    if (!confirm("确认删除此条商机？")) return;
    try {
      await api.delete(`/tender-notices/${id}`);
      await fetchData();
      selectedIds.delete(id);
      setSelectedIds(new Set(selectedIds));
    } catch (err: any) {
      alert(err.response?.data?.detail || "删除失败");
    }
  };

  // 批量删除
  const handleBatchDelete = async () => {
    if (selectedIds.size === 0) return;
    if (!confirm(`确认删除选中的 ${selectedIds.size} 条商机？`)) return;
    setDeleting(true);
    try {
      await api.post("/tender-notices/batch-delete", {
        notice_ids: Array.from(selectedIds),
      });
      setSelectedIds(new Set());
      await fetchData();
    } catch (err: any) {
      alert(err.response?.data?.detail || "批量删除失败");
    } finally {
      setDeleting(false);
    }
  };

  const handleConvert = async (id: number) => {
    if (!selectedEnterprise) {
      alert("请先选择企业");
      return;
    }
    try {
      const res = await api.post(`/tender-notices/${id}/convert?enterprise_id=${selectedEnterprise}`);
      const projectId = res.data?.data?.project_id;
      if (projectId) {
        window.location.href = `/dashboard/bid-projects/${projectId}`;
      } else {
        await fetchData();
      }
    } catch (err: any) {
      alert(err.response?.data?.detail || "转化失败");
    }
  };

  // 全选/取消全选
  const toggleSelectAll = () => {
    if (selectedIds.size === filtered.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(filtered.map((n) => n.id)));
    }
  };

  const toggleSelect = (id: number) => {
    const next = new Set(selectedIds);
    if (next.has(id)) {
      next.delete(id);
    } else {
      next.add(id);
    }
    setSelectedIds(next);
  };

  const filtered = notices.filter((n) => !search || n.title.includes(search) || (n.buyer_name || "").includes(search));
  const allSelected = filtered.length > 0 && selectedIds.size === filtered.length;

  return (
    <div className="space-y-6">
      {/* 页头 */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-slate-800 flex items-center gap-2">
            <Radar className="h-6 w-6 text-blue-500" />
            商机雷达
          </h2>
          <p className="mt-1 text-sm text-slate-500">从中国政府采购网实时抓取招标公告，AI 分析匹配度，一键转为投标项目</p>
        </div>
        <div className="flex items-center gap-2">
          {enterprises.length > 0 && (
            <select
              className="h-9 rounded-md border border-slate-200 px-3 text-sm"
              value={selectedEnterprise || ""}
              onChange={(e) => setSelectedEnterprise(Number(e.target.value))}
            >
              {enterprises.map((ent) => (
                <option key={ent.id} value={ent.id}>{ent.name}</option>
              ))}
            </select>
          )}
          <select
            className="h-9 rounded-md border border-slate-200 px-3 text-sm"
            value={selectedRegion}
            onChange={(e) => setSelectedRegion(e.target.value)}
          >
            {regions.length > 0 ? (
              regions.map((r) => (
                <option key={r.name} value={r.name}>{r.name}</option>
              ))
            ) : (
              <>
                <option value="全国">全国</option>
                <option value="广东">广东</option>
                <option value="浙江">浙江</option>
                <option value="江苏">江苏</option>
              </>
            )}
          </select>
          <Button onClick={handleFetch} disabled={fetching}>
            {fetching ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Radar className="mr-2 h-4 w-4" />}
            {fetching ? "抓取分析中..." : "抓取商机"}
          </Button>
          <Button variant="outline" onClick={() => setShowPaste(!showPaste)}>
            <Sparkles className="mr-2 h-4 w-4" />
            粘贴公告
          </Button>
        </div>
      </div>

      {/* 粘贴公告区域 */}
      {showPaste && (
        <Card className="border-violet-200">
          <CardContent className="space-y-3 pt-4">
            <div className="text-sm font-medium text-slate-700">
              从任意招标平台复制公告内容，AI 自动提取结构化信息
            </div>
            <textarea
              className="w-full min-h-[150px] rounded-md border border-slate-200 px-3 py-2 text-sm placeholder:text-slate-400 focus:border-blue-300 focus:outline-none resize-y"
              placeholder="在此粘贴完整的招标公告内容...&#10;&#10;支持从以下平台复制：&#10;- 中国政府采购网&#10;- 安徽省政府采购网&#10;- 合肥公共资源交易中心&#10;- 安徽公共资源交易集团&#10;- 优质采 / 安天e采&#10;- 或任意其他招标平台"
              value={pasteText}
              onChange={(e) => setPasteText(e.target.value)}
            />
            <div className="flex items-center gap-3">
              <Input
                className="flex-1"
                placeholder="公告原始链接（可选，方便后续查看原文）"
                value={pasteUrl}
                onChange={(e) => setPasteUrl(e.target.value)}
              />
              <Button onClick={handlePaste} disabled={parsing || !pasteText.trim() || !selectedEnterprise}>
                {parsing ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Sparkles className="mr-2 h-4 w-4" />}
                {parsing ? "AI 解析中..." : "AI 解析入库"}
              </Button>
              <Button variant="ghost" onClick={() => { setShowPaste(false); setPasteText(""); setPasteUrl(""); }}>取消</Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* 统计卡片 */}
      {stats && (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
          <Card><CardContent className="pt-4"><div className="text-sm text-slate-500">全部商机</div><div className="mt-1 text-2xl font-bold">{stats.total}</div></CardContent></Card>
          <Card><CardContent className="pt-4"><div className="text-sm text-slate-500">待分析</div><div className="mt-1 text-2xl font-bold text-blue-600">{stats.new_count}</div></CardContent></Card>
          <Card className="border-green-200"><CardContent className="pt-4"><div className="text-sm text-green-600">推荐投标</div><div className="mt-1 text-2xl font-bold text-green-600">{stats.recommended}</div></CardContent></Card>
          <Card className="border-red-200"><CardContent className="pt-4"><div className="text-sm text-red-500">风险提醒</div><div className="mt-1 text-2xl font-bold text-red-600">{stats.risky}</div></CardContent></Card>
          <Card className="border-purple-200"><CardContent className="pt-4"><div className="text-sm text-purple-600">已转化</div><div className="mt-1 text-2xl font-bold text-purple-600">{stats.converted}</div></CardContent></Card>
        </div>
      )}

      {/* 筛选栏 + 批量操作 */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <Input className="pl-10" placeholder="搜索项目名称或采购方..." value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>

        {/* 批量操作栏 */}
        {selectedIds.size > 0 && (
          <Button
            variant="destructive"
            size="sm"
            onClick={handleBatchDelete}
            disabled={deleting}
          >
            {deleting ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> : <Trash2 className="mr-1 h-3.5 w-3.5" />}
            删除选中 ({selectedIds.size})
          </Button>
        )}

        <div className="flex gap-1">
          {[
            { value: "", label: "全部" },
            { value: "recommended", label: "推荐" },
            { value: "analyzed", label: "已分析" },
            { value: "new", label: "待分析" },
            { value: "converted", label: "已转化" },
          ].map((f) => (
            <button
              key={f.value}
              className={`rounded-full px-3 py-1 text-xs transition-colors ${
                filterStatus === f.value ? "bg-slate-800 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"
              }`}
              onClick={() => { setFilterStatus(f.value); setSelectedIds(new Set()); }}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {/* 商机列表 */}
      {loading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="h-8 w-8 animate-spin text-slate-300" />
        </div>
      ) : filtered.length === 0 ? (
        <Card className="flex h-60 items-center justify-center">
          <div className="text-center text-slate-400">
            <Radar className="mx-auto mb-3 h-12 w-12 opacity-30" />
            <p className="text-sm font-medium">暂无商机</p>
            <p className="mt-1 text-xs">选择地区后点击「抓取商机」开始发现招标机会</p>
          </div>
        </Card>
      ) : (
        <div className="space-y-2">
          {/* 全选栏 */}
          <div className="flex items-center gap-3 rounded-lg bg-slate-50 px-4 py-2">
            <button onClick={toggleSelectAll} className="flex items-center gap-2 text-sm text-slate-600 hover:text-slate-800">
              {allSelected ? <CheckSquare className="h-4 w-4 text-blue-500" /> : <Square className="h-4 w-4" />}
              {allSelected ? "取消全选" : "全选"}
            </button>
            <span className="text-xs text-slate-400">共 {filtered.length} 条</span>
          </div>

          {filtered.map((n) => {
            const matchInfo = MATCH_LEVEL_MAP[n.match_level || ""] || null;
            const statusInfo = STATUS_MAP[n.status] || STATUS_MAP.new;
            const sourceInfo = SOURCE_MAP[n.source || "manual"] || SOURCE_MAP.manual;
            const isSelected = selectedIds.has(n.id);
            return (
              <Card key={n.id} className={`transition-shadow hover:shadow-md ${isSelected ? "ring-2 ring-blue-300 bg-blue-50/30" : ""}`}>
                <CardContent className="flex items-start gap-3 py-4">
                  {/* 复选框 */}
                  <button
                    className="mt-4 shrink-0"
                    onClick={() => toggleSelect(n.id)}
                  >
                    {isSelected ? (
                      <CheckSquare className="h-5 w-5 text-blue-500" />
                    ) : (
                      <Square className="h-5 w-5 text-slate-300 hover:text-slate-500" />
                    )}
                  </button>

                  {/* 匹配分数 */}
                  <div className={`flex h-14 w-14 shrink-0 items-center justify-center rounded-xl text-lg font-bold ${
                    n.match_score != null
                      ? n.match_score >= 70 ? "bg-green-100 text-green-700"
                        : n.match_score >= 40 ? "bg-amber-100 text-amber-700"
                        : "bg-red-100 text-red-700"
                      : "bg-slate-100 text-slate-400"
                  }`}>
                    {n.match_score != null ? n.match_score : "—"}
                  </div>

                  {/* 内容 */}
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <Link href={`/dashboard/tender-notices/${n.id}`} className="truncate font-medium text-slate-800 hover:text-blue-600">
                        {n.title}
                      </Link>
                      {matchInfo && <Badge className={matchInfo.color}>{matchInfo.label}</Badge>}
                      <Badge className={statusInfo.color}>{statusInfo.label}</Badge>
                    </div>
                    <div className="mt-1 flex flex-wrap items-center gap-3 text-xs text-slate-500">
                      {n.buyer_name && <span className="flex items-center gap-1"><Building2 className="h-3 w-3" />{n.buyer_name}</span>}
                      {n.customer_type && <span>{CUSTOMER_LABELS[n.customer_type] || n.customer_type}</span>}
                      {n.budget_amount && <span className="font-medium text-slate-700">{(n.budget_amount / 10000).toFixed(1)}万</span>}
                      {n.deadline && <span>截止: {n.deadline}</span>}
                      {n.publish_date && <span>发布: {n.publish_date}</span>}
                      <span className={`flex items-center gap-1 ${sourceInfo.color}`}>
                        <sourceInfo.icon className="h-3 w-3" />
                        {sourceInfo.label}
                      </span>
                    </div>
                    {n.recommendation && (
                      <p className="mt-1.5 text-xs text-slate-500 line-clamp-1">
                        <Sparkles className="mr-1 inline h-3 w-3 text-blue-400" />{n.recommendation}
                      </p>
                    )}
                  </div>

                  {/* 操作 */}
                  <div className="flex shrink-0 items-center gap-2">
                    {n.source_url && (
                      <a
                        href={n.source_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 rounded-md border border-blue-200 bg-blue-50 px-2.5 py-1.5 text-xs font-medium text-blue-600 transition-colors hover:bg-blue-100"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <ExternalLink className="h-3 w-3" />
                        查看原文
                      </a>
                    )}
                    {n.status !== "converted" && n.match_score != null && (
                      <Button size="sm" onClick={() => handleConvert(n.id)}>
                        <ArrowUpRight className="mr-1 h-3.5 w-3.5" />
                        转为项目
                      </Button>
                    )}
                    {n.status === "converted" && (
                      <Badge className="bg-purple-100 text-purple-700">已转化</Badge>
                    )}
                    {/* 单条删除 */}
                    <Button
                      size="sm"
                      variant="ghost"
                      className="text-slate-400 hover:text-red-500"
                      onClick={() => handleDelete(n.id)}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
