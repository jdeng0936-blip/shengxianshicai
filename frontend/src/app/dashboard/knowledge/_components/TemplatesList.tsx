"use client";

import { useState, useEffect, useCallback } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  LayoutTemplate,
  Trash2,
  Loader2,
} from "lucide-react";
import api from "@/lib/api";

interface Template {
  id: number;
  name: string;
  description?: string;
  file_url?: string;
}

interface TemplatesListProps {
  search: string;
  showCreate: boolean;
  setShowCreate: (show: boolean) => void;
}

export default function TemplatesList({ search, showCreate, setShowCreate }: TemplatesListProps) {
  const [templates, setTemplates] = useState<Template[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [templateForm, setTemplateForm] = useState({ name: "", description: "", file_url: "", is_default: false });

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get("/knowledge/templates");
      setTemplates(res.data?.data || []);
    } catch { setTemplates([]); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

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
    } finally { setCreating(false); }
  };

  const handleDelete = async (id: number) => {
    if (!confirm("确认删除？")) return;
    try { await api.delete(`/knowledge/templates/${id}`); fetchData(); }
    catch (e: any) { alert("删除失败: " + (e.response?.data?.detail || e.message)); }
  };

  if (loading) {
    return <div className="flex items-center justify-center py-20"><Loader2 className="h-8 w-8 animate-spin text-slate-300" /></div>;
  }

  return (
    <>
      {showCreate && (
        <Card className="border-blue-200 bg-blue-50/50">
          <CardContent className="space-y-3 pt-4">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="mb-1 block text-xs font-medium">模板名称 <span className="text-red-500">*</span></label>
                <Input value={templateForm.name} onChange={(e) => setTemplateForm({ ...templateForm, name: e.target.value })} placeholder="如：学校食堂配送投标文件模板" />
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

      {templates.length === 0 ? (
        <Card className="flex h-40 items-center justify-center">
          <div className="text-center text-slate-400">
            <LayoutTemplate className="mx-auto mb-2 h-10 w-10 opacity-30" />
            <p className="text-sm">暂无模板（模板上传功能开发中）</p>
          </div>
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          {templates.filter((t) => !search || t.name.includes(search)).map((t) => (
            <Card key={t.id}>
              <CardContent className="flex items-center justify-between py-4">
                <div>
                  <p className="font-medium">{t.name}</p>
                  <p className="text-xs text-slate-400">{t.description || "—"}</p>
                </div>
                <Button variant="ghost" size="sm" onClick={() => handleDelete(t.id)}>
                  <Trash2 className="h-3.5 w-3.5 text-red-400" />
                </Button>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </>
  );
}
