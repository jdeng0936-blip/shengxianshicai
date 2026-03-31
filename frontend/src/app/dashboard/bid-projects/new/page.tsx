"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { ArrowLeft, Loader2, Sparkles, CheckCircle2 } from "lucide-react";
import Link from "next/link";
import api from "@/lib/api";
import FileDropZone from "@/components/ui/file-drop-zone";

export default function NewBidProjectPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({
    project_name: "",
    tender_org: "",
    customer_type: "",
    tender_type: "",
    deadline: "",
    budget_amount: "",
    delivery_scope: "",
    delivery_period: "",
    description: "",
  });

  // 招标文件上传相关状态
  const [tenderFile, setTenderFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadError, setUploadError] = useState("");
  const [parsing, setParsing] = useState(false);
  const [parsed, setParsed] = useState(false);
  const [tempFilePath, setTempFilePath] = useState("");

  const handleTenderUpload = async (file: File) => {
    setTenderFile(file);
    setUploading(true);
    setUploadProgress(0);
    setUploadError("");
    setParsed(false);

    try {
      const formData = new FormData();
      formData.append("file", file);

      // 上传并预览解析
      setUploading(true);
      const res = await api.post("/bid-projects/preview-tender", formData, {
        headers: { "Content-Type": "multipart/form-data" },
        timeout: 120000,
        onUploadProgress: (progressEvent) => {
          if (progressEvent.total) {
            const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total);
            setUploadProgress(percent);
          }
        },
      });

      setUploadProgress(100);
      setUploading(false);
      setParsing(true);

      const data = res.data?.data;
      if (data) {
        // 保存临时文件路径
        if (data.temp_file_path) setTempFilePath(data.temp_file_path);

        // 自动填充表单（仅填充非空字段）
        setForm((prev) => ({
          ...prev,
          ...(data.project_name && { project_name: data.project_name }),
          ...(data.buyer_name && { tender_org: data.buyer_name }),
          ...(data.customer_type && { customer_type: data.customer_type }),
          ...(data.tender_type && { tender_type: data.tender_type }),
          ...(data.deadline && { deadline: data.deadline }),
          ...(data.budget_amount && { budget_amount: String(data.budget_amount) }),
          ...(data.delivery_scope && { delivery_scope: data.delivery_scope }),
          ...(data.delivery_period && { delivery_period: data.delivery_period }),
        }));
        setParsed(true);
      }
    } catch (err: any) {
      setUploadError(err.response?.data?.detail || "文件上传或解析失败");
    } finally {
      setUploading(false);
      setParsing(false);
    }
  };

  const handleRemoveFile = () => {
    setTenderFile(null);
    setUploadError("");
    setUploadProgress(0);
    setParsed(false);
    setTempFilePath("");
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.project_name.trim()) return;

    setLoading(true);
    try {
      const payload = {
        ...form,
        budget_amount: form.budget_amount ? parseFloat(form.budget_amount) : undefined,
      };
      const res = await api.post("/bid-projects", payload);
      const project = res.data?.data;
      if (project?.id) {
        // 如果有临时文件，关联到项目
        if (tempFilePath) {
          try {
            await api.post(`/bid-projects/${project.id}/associate-tender`, {
              temp_file_path: tempFilePath,
            });
          } catch {
            // 关联失败不阻塞，用户可在项目详情页重新上传
          }
        }
        router.push(`/dashboard/bid-projects/${project.id}`);
      }
    } catch (err: any) {
      alert(err.response?.data?.detail || "创建失败");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Link href="/dashboard/bid-projects">
          <Button variant="ghost" size="icon">
            <ArrowLeft className="h-5 w-5" />
          </Button>
        </Link>
        <h1 className="text-2xl font-bold text-slate-900">新建投标项目</h1>
      </div>

      {/* 上传招标文件 */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-blue-500" />
            智能填写
          </CardTitle>
          <CardDescription>
            上传招标文件，AI 自动提取项目信息并填充下方表单，您可以修改任何字段
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <FileDropZone
            accept={[".pdf", ".docx", ".doc"]}
            file={tenderFile}
            onFileSelect={handleTenderUpload}
            onFileRemove={handleRemoveFile}
            uploading={uploading}
            progress={uploadProgress}
            error={uploadError}
            disabled={uploading || parsing}
            hint="上传招标文件（PDF/DOCX/DOC），AI 将自动提取项目基本信息"
          />

          {parsing && (
            <div className="flex items-center gap-3 rounded-md bg-blue-50 p-3 dark:bg-blue-950">
              <Loader2 className="h-5 w-5 animate-spin text-blue-500" />
              <span className="text-sm text-blue-700 dark:text-blue-300">
                AI 正在分析招标文件，提取项目信息...
              </span>
            </div>
          )}

          {parsed && (
            <div className="flex items-center gap-3 rounded-md bg-green-50 p-3 dark:bg-green-950">
              <CheckCircle2 className="h-5 w-5 text-green-500" />
              <span className="text-sm text-green-700 dark:text-green-300">
                已自动填充项目信息，请核对并修改下方表单
              </span>
            </div>
          )}
        </CardContent>
      </Card>

      {/* 项目基本信息表单 */}
      <form onSubmit={handleSubmit}>
        <Card>
          <CardHeader>
            <CardTitle>项目基本信息</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="project_name">招标项目名称 *</Label>
                <Input
                  id="project_name"
                  placeholder="如：XX学校2026年食材配送服务采购项目"
                  value={form.project_name}
                  onChange={(e) => setForm({ ...form, project_name: e.target.value })}
                  required
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="tender_org">招标方/采购方名称</Label>
                <Input
                  id="tender_org"
                  placeholder="如：XX市第一中学"
                  value={form.tender_org}
                  onChange={(e) => setForm({ ...form, tender_org: e.target.value })}
                />
              </div>
              <div className="space-y-2">
                <Label>客户类型</Label>
                <Select
                  value={form.customer_type || ""}
                  onValueChange={(v: string | null) => setForm({ ...form, customer_type: v || "" })}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="选择客户类型" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="school">学校食堂</SelectItem>
                    <SelectItem value="hospital">医院</SelectItem>
                    <SelectItem value="government">政府机关</SelectItem>
                    <SelectItem value="enterprise">企业食堂</SelectItem>
                    <SelectItem value="canteen">团餐公司</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>招标方式</Label>
                <Select
                  value={form.tender_type || ""}
                  onValueChange={(v: string | null) => setForm({ ...form, tender_type: v || "" })}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="选择招标方式" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="open">公开招标</SelectItem>
                    <SelectItem value="invite">邀请招标</SelectItem>
                    <SelectItem value="negotiate">竞争性谈判</SelectItem>
                    <SelectItem value="inquiry">询价</SelectItem>
                    <SelectItem value="single">单一来源</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="deadline">投标截止时间</Label>
                <Input
                  id="deadline"
                  type="datetime-local"
                  value={form.deadline}
                  onChange={(e) => setForm({ ...form, deadline: e.target.value })}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="budget_amount">预算金额（元）</Label>
                <Input
                  id="budget_amount"
                  type="number"
                  placeholder="如：500000"
                  value={form.budget_amount}
                  onChange={(e) => setForm({ ...form, budget_amount: e.target.value })}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="delivery_period">配送周期/合同期限</Label>
                <Input
                  id="delivery_period"
                  placeholder="如：1年（可续签）"
                  value={form.delivery_period}
                  onChange={(e) => setForm({ ...form, delivery_period: e.target.value })}
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="delivery_scope">配送范围描述</Label>
              <Textarea
                id="delivery_scope"
                placeholder="如：XX市城区范围内5所学校食堂，日均供餐3000人"
                value={form.delivery_scope}
                onChange={(e) => setForm({ ...form, delivery_scope: e.target.value })}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="description">备注说明</Label>
              <Textarea
                id="description"
                placeholder="其他补充信息..."
                value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
              />
            </div>
            <div className="flex justify-end gap-3 pt-4">
              <Link href="/dashboard/bid-projects">
                <Button variant="outline" type="button">取消</Button>
              </Link>
              <Button type="submit" disabled={loading || !form.project_name.trim()}>
                {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                创建项目
              </Button>
            </div>
          </CardContent>
        </Card>
      </form>
    </div>
  );
}
