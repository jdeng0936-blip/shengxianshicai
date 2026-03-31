"use client";

import { useState, useEffect, useCallback } from "react";
import { useParams } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  ArrowLeft,
  Loader2,
  Save,
  Plus,
  Trash2,
  Building2,
  ShieldCheck,
  Truck,
  AlertTriangle,
  CheckCircle2,
  ImageIcon,
  Upload,
  X,
  Star,
} from "lucide-react";
import Link from "next/link";
import api from "@/lib/api";
import FileDropZone from "@/components/ui/file-drop-zone";

interface Enterprise {
  id: number;
  name: string;
  short_name?: string;
  credit_code?: string;
  legal_representative?: string;
  registered_capital?: string;
  established_date?: string;
  business_scope?: string;
  food_license_no?: string;
  food_license_expiry?: string;
  haccp_certified: boolean;
  iso22000_certified: boolean;
  sc_certified: boolean;
  cold_chain_vehicles: number;
  normal_vehicles: number;
  warehouse_area?: number;
  cold_storage_area?: number;
  cold_storage_temp?: string;
  address?: string;
  contact_person?: string;
  contact_phone?: string;
  contact_email?: string;
  employee_count?: number;
  annual_revenue?: string;
  service_customers?: number;
  description?: string;
  competitive_advantages?: string;
}

interface Credential {
  id: number;
  enterprise_id: number;
  cred_type: string;
  cred_name: string;
  cred_no?: string;
  issue_date?: string;
  expiry_date?: string;
  is_permanent: boolean;
  issuing_authority?: string;
  is_verified: boolean;
}

interface ImageAsset {
  id: number;
  enterprise_id: number;
  category: string;
  title: string;
  description?: string;
  file_name?: string;
  file_size?: number;
  width?: number;
  height?: number;
  tags?: string;
  suggested_chapter?: string;
  is_default: boolean;
}

interface BidProject {
  id: number;
  project_name: string;
  enterprise_id?: number;
}

const IMAGE_CATEGORIES = [
  { value: "cold_chain_vehicle", label: "冷链车辆" },
  { value: "warehouse", label: "仓库/冷库" },
  { value: "testing_equipment", label: "检测设备" },
  { value: "food_sample", label: "食材样品" },
  { value: "process_flow", label: "流程图/架构图" },
  { value: "company_environment", label: "公司环境" },
  { value: "sample_retention", label: "留样柜" },
  { value: "inspection_report", label: "检验报告" },
  { value: "certificate", label: "证书/奖项" },
  { value: "delivery_scene", label: "配送现场" },
  { value: "training", label: "培训场景" },
  { value: "canteen", label: "食堂/餐厅" },
  { value: "traceability", label: "追溯系统" },
  { value: "other", label: "其他" },
];

const IMAGE_CAT_LABELS: Record<string, string> = Object.fromEntries(
  IMAGE_CATEGORIES.map((c) => [c.value, c.label])
);

const CRED_TYPE_OPTIONS = [
  { value: "business_license", label: "营业执照" },
  { value: "food_license", label: "食品经营许可证" },
  { value: "haccp", label: "HACCP认证" },
  { value: "iso22000", label: "ISO22000认证" },
  { value: "sc", label: "SC认证" },
  { value: "animal_quarantine", label: "动物防疫合格证" },
  { value: "cold_chain_transport", label: "冷链运输资质" },
  { value: "health_certificate", label: "从业人员健康证" },
  { value: "liability_insurance", label: "公众责任险" },
  { value: "quality_inspection", label: "质量检验报告" },
  { value: "organic_cert", label: "有机认证" },
  { value: "green_food", label: "绿色食品认证" },
  { value: "performance", label: "业绩证明" },
  { value: "award", label: "荣誉证书" },
  { value: "other", label: "其他" },
];

const CRED_TYPE_LABELS: Record<string, string> = Object.fromEntries(
  CRED_TYPE_OPTIONS.map((o) => [o.value, o.label])
);

function isExpiringSoon(expiryDate?: string): boolean {
  if (!expiryDate) return false;
  const expiry = new Date(expiryDate);
  const now = new Date();
  const diffDays = (expiry.getTime() - now.getTime()) / (1000 * 60 * 60 * 24);
  return diffDays >= 0 && diffDays <= 90;
}

function isExpired(expiryDate?: string): boolean {
  if (!expiryDate) return false;
  return new Date(expiryDate) < new Date();
}

export default function EnterprisePage() {
  const params = useParams();
  const projectId = params.id as string;

  const [project, setProject] = useState<BidProject | null>(null);
  const [enterprise, setEnterprise] = useState<Enterprise | null>(null);
  const [enterprises, setEnterprises] = useState<Enterprise[]>([]);
  const [credentials, setCredentials] = useState<Credential[]>([]);
  const [form, setForm] = useState<Partial<Enterprise>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  // 图片管理
  const [images, setImages] = useState<ImageAsset[]>([]);
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [imageUploading, setImageUploading] = useState(false);
  const [imageUploadProgress, setImageUploadProgress] = useState(0);
  const [imageUploadError, setImageUploadError] = useState("");
  const [imageCategory, setImageCategory] = useState("other");
  const [imageTitle, setImageTitle] = useState("");
  const [showImageUpload, setShowImageUpload] = useState(false);
  const [imageCatFilter, setImageCatFilter] = useState("");

  const [showNewCred, setShowNewCred] = useState(false);
  const [newCred, setNewCred] = useState({
    cred_type: "business_license",
    cred_name: "",
    cred_no: "",
    issue_date: "",
    expiry_date: "",
    is_permanent: false,
    issuing_authority: "",
  });

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      // 加载项目
      const projRes = await api.get(`/bid-projects/${projectId}`);
      const proj = projRes.data?.data as BidProject;
      setProject(proj);

      // 加载企业列表（供选择）
      const entListRes = await api.get("/enterprises");
      setEnterprises(entListRes.data?.data || []);

      // 如果项目已关联企业，加载详情和资质
      if (proj?.enterprise_id) {
        const entRes = await api.get(`/enterprises/${proj.enterprise_id}`);
        const ent = entRes.data?.data as Enterprise;
        setEnterprise(ent);
        setForm(ent);

        const credRes = await api.get(`/credentials/enterprise/${proj.enterprise_id}`);
        setCredentials(credRes.data?.data || []);

        // 加载图片
        try {
          const imgRes = await api.get(`/images/enterprise/${proj.enterprise_id}`);
          setImages(imgRes.data?.data || []);
        } catch { /* ignore */ }
      }
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleFormChange = (field: string, value: any) => {
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  const handleCreateEnterprise = async () => {
    if (!form.name) {
      alert("请填写企业名称");
      return;
    }
    setSaving(true);
    try {
      const res = await api.post("/enterprises", form);
      const ent = res.data?.data as Enterprise;
      // 关联到项目
      await api.put(`/bid-projects/${projectId}`, { enterprise_id: ent.id });
      await fetchData();
    } catch (err: any) {
      alert(err.response?.data?.detail || "创建失败");
    } finally {
      setSaving(false);
    }
  };

  const handleSaveEnterprise = async () => {
    if (!enterprise) return;
    setSaving(true);
    try {
      await api.put(`/enterprises/${enterprise.id}`, form);
      await fetchData();
    } catch (err: any) {
      alert(err.response?.data?.detail || "保存失败");
    } finally {
      setSaving(false);
    }
  };

  const handleSelectEnterprise = async (entId: number) => {
    try {
      await api.put(`/bid-projects/${projectId}`, { enterprise_id: entId });
      await fetchData();
    } catch {
      alert("关联失败");
    }
  };

  const handleAddCredential = async () => {
    if (!enterprise || !newCred.cred_name) return;
    try {
      await api.post("/credentials", {
        enterprise_id: enterprise.id,
        ...newCred,
      });
      setShowNewCred(false);
      setNewCred({
        cred_type: "business_license", cred_name: "", cred_no: "",
        issue_date: "", expiry_date: "", is_permanent: false, issuing_authority: "",
      });
      await fetchData();
    } catch (err: any) {
      alert(err.response?.data?.detail || "添加失败");
    }
  };

  const handleUploadImage = async () => {
    if (!enterprise || !imageFile) return;
    setImageUploading(true);
    setImageUploadProgress(0);
    setImageUploadError("");
    try {
      const formData = new FormData();
      formData.append("file", imageFile);
      formData.append("enterprise_id", String(enterprise.id));
      formData.append("category", imageCategory);
      formData.append("title", imageTitle || imageFile.name);
      await api.post("/images/upload", formData, {
        headers: { "Content-Type": "multipart/form-data" },
        onUploadProgress: (e) => {
          if (e.total) setImageUploadProgress(Math.round((e.loaded * 100) / e.total));
        },
      });
      setImageUploadProgress(100);
      setImageFile(null);
      setImageTitle("");
      setImageCategory("other");
      setShowImageUpload(false);
      await fetchData();
    } catch (err: any) {
      setImageUploadError(err.response?.data?.detail || "上传失败");
    } finally {
      setImageUploading(false);
    }
  };

  const handleDeleteImage = async (imageId: number) => {
    if (!confirm("确认删除此图片？")) return;
    try {
      await api.delete(`/images/${imageId}`);
      setImages((prev) => prev.filter((i) => i.id !== imageId));
    } catch {
      alert("删除失败");
    }
  };

  const handleDeleteCredential = async (credId: number) => {
    try {
      await api.delete(`/credentials/${credId}`);
      await fetchData();
    } catch {
      alert("删除失败");
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-8 w-8 animate-spin text-slate-400" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* 页头 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link href={`/dashboard/bid-projects/${projectId}`}>
            <Button variant="ghost" size="icon">
              <ArrowLeft className="h-5 w-5" />
            </Button>
          </Link>
          <h1 className="text-xl font-bold text-slate-900">企业信息管理</h1>
        </div>
        {enterprise && (
          <Button onClick={handleSaveEnterprise} disabled={saving}>
            {saving ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Save className="mr-2 h-4 w-4" />
            )}
            保存企业信息
          </Button>
        )}
      </div>

      {/* 未关联企业 → 新建或选择 */}
      {!enterprise && (
        <Card>
          <CardHeader>
            <CardTitle>关联投标企业</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {enterprises.length > 0 && (
              <div>
                <p className="mb-2 text-sm text-slate-500">选择已有企业：</p>
                <div className="flex flex-wrap gap-2">
                  {enterprises.map((ent) => (
                    <Button
                      key={ent.id}
                      variant="outline"
                      size="sm"
                      onClick={() => handleSelectEnterprise(ent.id)}
                    >
                      <Building2 className="mr-1 h-3.5 w-3.5" />
                      {ent.name}
                    </Button>
                  ))}
                </div>
                <div className="my-4 border-t" />
              </div>
            )}
            <p className="text-sm text-slate-500">或新建企业：</p>
            <Input
              placeholder="企业名称（必填）"
              value={form.name || ""}
              onChange={(e) => handleFormChange("name", e.target.value)}
            />
            <Button onClick={handleCreateEnterprise} disabled={saving || !form.name}>
              {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Plus className="mr-2 h-4 w-4" />}
              创建并关联
            </Button>
          </CardContent>
        </Card>
      )}

      {/* 企业基本信息表单 */}
      {enterprise && (
        <>
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Building2 className="h-5 w-5" />
                工商信息
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
                <div>
                  <label className="mb-1 block text-xs text-slate-500">企业名称 *</label>
                  <Input value={form.name || ""} onChange={(e) => handleFormChange("name", e.target.value)} />
                </div>
                <div>
                  <label className="mb-1 block text-xs text-slate-500">企业简称</label>
                  <Input value={form.short_name || ""} onChange={(e) => handleFormChange("short_name", e.target.value)} />
                </div>
                <div>
                  <label className="mb-1 block text-xs text-slate-500">统一社会信用代码</label>
                  <Input value={form.credit_code || ""} onChange={(e) => handleFormChange("credit_code", e.target.value)} />
                </div>
                <div>
                  <label className="mb-1 block text-xs text-slate-500">法定代表人</label>
                  <Input value={form.legal_representative || ""} onChange={(e) => handleFormChange("legal_representative", e.target.value)} />
                </div>
                <div>
                  <label className="mb-1 block text-xs text-slate-500">注册资本（万元）</label>
                  <Input value={form.registered_capital || ""} onChange={(e) => handleFormChange("registered_capital", e.target.value)} />
                </div>
                <div>
                  <label className="mb-1 block text-xs text-slate-500">成立日期</label>
                  <Input type="date" value={form.established_date || ""} onChange={(e) => handleFormChange("established_date", e.target.value)} />
                </div>
                <div>
                  <label className="mb-1 block text-xs text-slate-500">员工人数</label>
                  <Input type="number" value={form.employee_count ?? ""} onChange={(e) => handleFormChange("employee_count", e.target.value ? parseInt(e.target.value) : null)} />
                </div>
                <div>
                  <label className="mb-1 block text-xs text-slate-500">年营收（万元）</label>
                  <Input value={form.annual_revenue || ""} onChange={(e) => handleFormChange("annual_revenue", e.target.value)} />
                </div>
                <div>
                  <label className="mb-1 block text-xs text-slate-500">服务客户数</label>
                  <Input type="number" value={form.service_customers ?? ""} onChange={(e) => handleFormChange("service_customers", e.target.value ? parseInt(e.target.value) : null)} />
                </div>
              </div>
              <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
                <div>
                  <label className="mb-1 block text-xs text-slate-500">公司地址</label>
                  <Input value={form.address || ""} onChange={(e) => handleFormChange("address", e.target.value)} />
                </div>
                <div className="grid grid-cols-3 gap-2">
                  <div>
                    <label className="mb-1 block text-xs text-slate-500">联系人</label>
                    <Input value={form.contact_person || ""} onChange={(e) => handleFormChange("contact_person", e.target.value)} />
                  </div>
                  <div>
                    <label className="mb-1 block text-xs text-slate-500">联系电话</label>
                    <Input value={form.contact_phone || ""} onChange={(e) => handleFormChange("contact_phone", e.target.value)} />
                  </div>
                  <div>
                    <label className="mb-1 block text-xs text-slate-500">邮箱</label>
                    <Input value={form.contact_email || ""} onChange={(e) => handleFormChange("contact_email", e.target.value)} />
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* 食品行业资质 */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <ShieldCheck className="h-5 w-5" />
                食品行业资质
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
                <div>
                  <label className="mb-1 block text-xs text-slate-500">食品经营许可证号</label>
                  <Input value={form.food_license_no || ""} onChange={(e) => handleFormChange("food_license_no", e.target.value)} />
                </div>
                <div>
                  <label className="mb-1 block text-xs text-slate-500">食品经营许可证到期日</label>
                  <Input type="date" value={form.food_license_expiry || ""} onChange={(e) => handleFormChange("food_license_expiry", e.target.value)} />
                </div>
                <div className="flex items-end gap-4 pb-1">
                  <label className="flex items-center gap-2 text-sm">
                    <input type="checkbox" checked={form.haccp_certified || false} onChange={(e) => handleFormChange("haccp_certified", e.target.checked)} className="h-4 w-4 rounded border-slate-300" />
                    HACCP
                  </label>
                  <label className="flex items-center gap-2 text-sm">
                    <input type="checkbox" checked={form.iso22000_certified || false} onChange={(e) => handleFormChange("iso22000_certified", e.target.checked)} className="h-4 w-4 rounded border-slate-300" />
                    ISO22000
                  </label>
                  <label className="flex items-center gap-2 text-sm">
                    <input type="checkbox" checked={form.sc_certified || false} onChange={(e) => handleFormChange("sc_certified", e.target.checked)} className="h-4 w-4 rounded border-slate-300" />
                    SC
                  </label>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* 冷链资产 */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Truck className="h-5 w-5" />
                冷链资产
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 gap-4 md:grid-cols-5">
                <div>
                  <label className="mb-1 block text-xs text-slate-500">冷链车辆（辆）</label>
                  <Input type="number" value={form.cold_chain_vehicles ?? 0} onChange={(e) => handleFormChange("cold_chain_vehicles", parseInt(e.target.value) || 0)} />
                </div>
                <div>
                  <label className="mb-1 block text-xs text-slate-500">常温车辆（辆）</label>
                  <Input type="number" value={form.normal_vehicles ?? 0} onChange={(e) => handleFormChange("normal_vehicles", parseInt(e.target.value) || 0)} />
                </div>
                <div>
                  <label className="mb-1 block text-xs text-slate-500">仓储面积（㎡）</label>
                  <Input type="number" value={form.warehouse_area ?? ""} onChange={(e) => handleFormChange("warehouse_area", e.target.value ? parseFloat(e.target.value) : null)} />
                </div>
                <div>
                  <label className="mb-1 block text-xs text-slate-500">冷库面积（㎡）</label>
                  <Input type="number" value={form.cold_storage_area ?? ""} onChange={(e) => handleFormChange("cold_storage_area", e.target.value ? parseFloat(e.target.value) : null)} />
                </div>
                <div>
                  <label className="mb-1 block text-xs text-slate-500">冷库温度范围</label>
                  <Input placeholder="-18℃~4℃" value={form.cold_storage_temp || ""} onChange={(e) => handleFormChange("cold_storage_temp", e.target.value)} />
                </div>
              </div>
            </CardContent>
          </Card>

          {/* 企业简介 & 竞争优势 */}
          <Card>
            <CardHeader>
              <CardTitle>企业简介与竞争优势</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <label className="mb-1 block text-xs text-slate-500">企业简介（用于投标文件第二章）</label>
                <Textarea
                  rows={4}
                  value={form.description || ""}
                  onChange={(e) => handleFormChange("description", e.target.value)}
                  placeholder="介绍企业的基本情况、发展历程、主营业务等..."
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-slate-500">核心竞争优势（用于技术方案章节）</label>
                <Textarea
                  rows={4}
                  value={form.competitive_advantages || ""}
                  onChange={(e) => handleFormChange("competitive_advantages", e.target.value)}
                  placeholder="如：自有基地直供、全程冷链可追溯、服务XX所学校食堂等..."
                />
              </div>
            </CardContent>
          </Card>

          {/* 资质证书库 */}
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="flex items-center gap-2">
                  <ShieldCheck className="h-5 w-5" />
                  资质证书库（{credentials.length} 项）
                </CardTitle>
                <Button size="sm" variant="outline" onClick={() => setShowNewCred(!showNewCred)}>
                  <Plus className="mr-1 h-4 w-4" />
                  添加证书
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              {/* 新增证书表单 */}
              {showNewCred && (
                <div className="mb-4 rounded-lg border border-blue-200 bg-blue-50 p-4">
                  <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
                    <div>
                      <label className="mb-1 block text-xs text-slate-500">证书类型</label>
                      <select
                        className="h-9 w-full rounded-md border border-slate-200 px-3 text-sm"
                        value={newCred.cred_type}
                        onChange={(e) => setNewCred({ ...newCred, cred_type: e.target.value })}
                      >
                        {CRED_TYPE_OPTIONS.map((o) => (
                          <option key={o.value} value={o.value}>{o.label}</option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="mb-1 block text-xs text-slate-500">证书名称 *</label>
                      <Input value={newCred.cred_name} onChange={(e) => setNewCred({ ...newCred, cred_name: e.target.value })} placeholder="如：食品经营许可证" />
                    </div>
                    <div>
                      <label className="mb-1 block text-xs text-slate-500">证书编号</label>
                      <Input value={newCred.cred_no} onChange={(e) => setNewCred({ ...newCred, cred_no: e.target.value })} />
                    </div>
                    <div>
                      <label className="mb-1 block text-xs text-slate-500">到期日期</label>
                      <Input type="date" value={newCred.expiry_date} onChange={(e) => setNewCred({ ...newCred, expiry_date: e.target.value })} />
                    </div>
                  </div>
                  <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-4">
                    <div>
                      <label className="mb-1 block text-xs text-slate-500">发证机关</label>
                      <Input value={newCred.issuing_authority} onChange={(e) => setNewCred({ ...newCred, issuing_authority: e.target.value })} />
                    </div>
                    <div className="flex items-end pb-1">
                      <label className="flex items-center gap-2 text-sm">
                        <input type="checkbox" checked={newCred.is_permanent} onChange={(e) => setNewCred({ ...newCred, is_permanent: e.target.checked })} className="h-4 w-4 rounded border-slate-300" />
                        长期有效
                      </label>
                    </div>
                    <div className="col-span-2 flex items-end gap-2">
                      <Button size="sm" onClick={handleAddCredential} disabled={!newCred.cred_name}>
                        <Plus className="mr-1 h-3.5 w-3.5" />
                        添加
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => setShowNewCred(false)}>取消</Button>
                    </div>
                  </div>
                </div>
              )}

              {/* 证书列表 */}
              {credentials.length === 0 ? (
                <p className="py-8 text-center text-sm text-slate-400">
                  暂无资质证书，点击「添加证书」录入
                </p>
              ) : (
                <div className="space-y-2">
                  {credentials.map((cred) => {
                    const expired = isExpired(cred.expiry_date);
                    const expiring = isExpiringSoon(cred.expiry_date);
                    return (
                      <div
                        key={cred.id}
                        className={`flex items-center justify-between rounded-lg border p-3 ${
                          expired ? "border-red-200 bg-red-50" :
                          expiring ? "border-amber-200 bg-amber-50" :
                          "border-slate-200"
                        }`}
                      >
                        <div className="flex items-center gap-3">
                          <Badge variant="secondary" className="shrink-0">
                            {CRED_TYPE_LABELS[cred.cred_type] || cred.cred_type}
                          </Badge>
                          <div>
                            <div className="text-sm font-medium">{cred.cred_name}</div>
                            <div className="flex items-center gap-2 text-xs text-slate-400">
                              {cred.cred_no && <span>编号: {cred.cred_no}</span>}
                              {cred.issuing_authority && <span>发证: {cred.issuing_authority}</span>}
                              {cred.is_permanent ? (
                                <span className="text-green-600">长期有效</span>
                              ) : cred.expiry_date ? (
                                <span className={expired ? "text-red-600 font-medium" : expiring ? "text-amber-600" : ""}>
                                  {expired ? "已过期: " : expiring ? "即将到期: " : "有效期至: "}
                                  {cred.expiry_date}
                                </span>
                              ) : null}
                            </div>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          {expired && <AlertTriangle className="h-4 w-4 text-red-500" />}
                          {expiring && !expired && <AlertTriangle className="h-4 w-4 text-amber-500" />}
                          {cred.is_verified && <CheckCircle2 className="h-4 w-4 text-green-500" />}
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7 text-slate-400 hover:text-red-500"
                            onClick={() => handleDeleteCredential(cred.id)}
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>
          {/* 图片资源库 */}
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="flex items-center gap-2">
                  <ImageIcon className="h-5 w-5" />
                  图片资源库（{images.length} 张）
                </CardTitle>
                <Button size="sm" variant="outline" onClick={() => setShowImageUpload(!showImageUpload)}>
                  <Upload className="mr-1 h-4 w-4" />
                  上传图片
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              {/* 上传表单 */}
              {showImageUpload && (
                <div className="mb-4 rounded-lg border border-blue-200 bg-blue-50 p-4 space-y-3">
                  <FileDropZone
                    accept={[".jpg", ".jpeg", ".png", ".gif", ".webp"]}
                    file={imageFile}
                    onFileSelect={(f) => { setImageFile(f); setImageUploadError(""); }}
                    onFileRemove={() => { setImageFile(null); setImageUploadError(""); }}
                    uploading={imageUploading}
                    progress={imageUploadProgress}
                    error={imageUploadError}
                    hint="支持 JPG/PNG/GIF/WebP 格式"
                  />
                  <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                    <div>
                      <label className="mb-1 block text-xs text-slate-500">图片分类</label>
                      <select
                        className="h-9 w-full rounded-md border border-slate-200 px-3 text-sm"
                        value={imageCategory}
                        onChange={(e) => setImageCategory(e.target.value)}
                      >
                        {IMAGE_CATEGORIES.map((c) => (
                          <option key={c.value} value={c.value}>{c.label}</option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="mb-1 block text-xs text-slate-500">图片标题</label>
                      <Input
                        value={imageTitle}
                        onChange={(e) => setImageTitle(e.target.value)}
                        placeholder="如：冷链配送车-京A12345"
                      />
                    </div>
                    <div className="flex items-end gap-2">
                      <Button size="sm" onClick={handleUploadImage} disabled={!imageFile || imageUploading}>
                        {imageUploading ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> : <Upload className="mr-1 h-3.5 w-3.5" />}
                        上传
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => { setShowImageUpload(false); setImageFile(null); }}>取消</Button>
                    </div>
                  </div>
                </div>
              )}

              {/* 分类筛选 */}
              {images.length > 0 && (
                <div className="mb-3 flex flex-wrap gap-1">
                  <button
                    className={`rounded-full px-3 py-1 text-xs transition-colors ${!imageCatFilter ? "bg-slate-800 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"}`}
                    onClick={() => setImageCatFilter("")}
                  >
                    全部
                  </button>
                  {[...new Set(images.map((i) => i.category))].map((cat) => (
                    <button
                      key={cat}
                      className={`rounded-full px-3 py-1 text-xs transition-colors ${imageCatFilter === cat ? "bg-slate-800 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"}`}
                      onClick={() => setImageCatFilter(cat)}
                    >
                      {IMAGE_CAT_LABELS[cat] || cat}（{images.filter((i) => i.category === cat).length}）
                    </button>
                  ))}
                </div>
              )}

              {/* 图片网格 */}
              {images.length === 0 ? (
                <p className="py-8 text-center text-sm text-slate-400">
                  暂无图片，点击「上传图片」添加企业资质照片、冷链车辆照片等
                </p>
              ) : (
                <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                  {images
                    .filter((i) => !imageCatFilter || i.category === imageCatFilter)
                    .map((img) => (
                      <div key={img.id} className="group relative overflow-hidden rounded-lg border bg-slate-50">
                        <div className="aspect-[4/3] flex items-center justify-center bg-slate-100">
                          <img
                            src={`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1"}/images/file/${img.id}`}
                            alt={img.title}
                            className="h-full w-full object-cover"
                            onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
                          />
                        </div>
                        <div className="p-2">
                          <p className="truncate text-xs font-medium text-slate-700">{img.title}</p>
                          <div className="flex items-center justify-between mt-1">
                            <Badge variant="secondary" className="text-xs">
                              {IMAGE_CAT_LABELS[img.category] || img.category}
                            </Badge>
                            {img.is_default && <Star className="h-3 w-3 text-amber-500 fill-amber-500" />}
                          </div>
                        </div>
                        {/* 悬浮删除 */}
                        <button
                          className="absolute top-1 right-1 rounded-full bg-black/50 p-1 text-white opacity-0 transition-opacity group-hover:opacity-100"
                          onClick={() => handleDeleteImage(img.id)}
                        >
                          <X className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    ))}
                </div>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
