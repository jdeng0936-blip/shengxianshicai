"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Upload,
  Grid3X3,
  FileImage,
  Shield,
  Ruler,
  LayoutPanelLeft,
  ClipboardList,
  Trash2,
  Eye,
  Download,
  X,
  ChevronLeft,
  Loader2,
  Search,
} from "lucide-react";
import api from "@/lib/api";

// ========== 类型定义 ==========
interface Drawing {
  id: number;
  name: string;
  category: string;
  description: string | null;
  file_url: string;
  file_format: string | null;
  file_size: number | null;
  version: number;
  is_current: boolean;
  created_at: string | null;
}

interface CategoryInfo {
  key: string;
  label: string;
  icon: React.ElementType;
  desc: string;
}

// ========== 常量 ==========
const CATEGORIES: CategoryInfo[] = [
  { key: "section", label: "断面图", icon: Grid3X3, desc: "巷道断面形状、尺寸标注图" },
  { key: "support", label: "支护图", icon: Shield, desc: "锚杆/锚索/金属网支护布置图" },
  { key: "layout", label: "布置图", icon: LayoutPanelLeft, desc: "掘进工作面设备布置图" },
  { key: "schedule", label: "作业图表", icon: ClipboardList, desc: "循环作业图表、工序安排图" },
  { key: "safety", label: "安全图", icon: Shield, desc: "避灾路线、通风示意等安全图" },
  { key: "measure", label: "测量图", icon: Ruler, desc: "巷道中腰线标定、测量布局图" },
];

// 文件大小格式化
function formatFileSize(bytes: number | null): string {
  if (!bytes) return "-";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// 判断是否可以在浏览器中预览
function isPreviewable(format: string | null): boolean {
  if (!format) return false;
  return ["png", "jpg", "jpeg", "svg", "pdf"].includes(format.toLowerCase());
}

/** 图纸管理页面 */
export default function DrawingsPage() {
  // ===== 状态 =====
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [categoryCounts, setCategoryCounts] = useState<Record<string, number>>({});
  const [drawings, setDrawings] = useState<Drawing[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [searchName, setSearchName] = useState("");
  const [loading, setLoading] = useState(false);

  // 上传表单状态
  const [showUploadForm, setShowUploadForm] = useState(false);
  const [uploadName, setUploadName] = useState("");
  const [uploadDesc, setUploadDesc] = useState("");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // 预览状态
  const [previewDrawing, setPreviewDrawing] = useState<Drawing | null>(null);

  const pageSize = 12;

  // ===== 数据获取 =====

  // 获取分类数量统计
  const fetchCategoryCounts = useCallback(async () => {
    try {
      const res = await api.get("/drawings/categories");
      setCategoryCounts(res.data.data || {});
    } catch {
      console.error("获取分类统计失败");
    }
  }, []);

  // 获取图纸列表
  const fetchDrawings = useCallback(async () => {
    if (!selectedCategory) return;
    setLoading(true);
    try {
      const res = await api.get("/drawings", {
        params: {
          page,
          page_size: pageSize,
          category: selectedCategory,
          name: searchName || undefined,
        },
      });
      setDrawings(res.data.data?.items || []);
      setTotal(res.data.data?.total || 0);
    } catch {
      console.error("获取图纸列表失败");
    } finally {
      setLoading(false);
    }
  }, [selectedCategory, page, searchName]);

  useEffect(() => {
    fetchCategoryCounts();
  }, [fetchCategoryCounts]);

  useEffect(() => {
    if (selectedCategory) {
      fetchDrawings();
    }
  }, [selectedCategory, page, fetchDrawings]);

  // ===== 操作处理 =====

  // 切换分类
  const handleSelectCategory = (key: string) => {
    setSelectedCategory(key);
    setPage(1);
    setSearchName("");
    setShowUploadForm(false);
    setPreviewDrawing(null);
  };

  // 返回分类总览
  const handleBackToCategories = () => {
    setSelectedCategory(null);
    setDrawings([]);
    setPreviewDrawing(null);
    fetchCategoryCounts();
  };

  // 上传图纸
  const handleUpload = async () => {
    if (!uploadFile || !uploadName || !selectedCategory) return;
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", uploadFile);
      formData.append("name", uploadName);
      formData.append("category", selectedCategory);
      if (uploadDesc) formData.append("description", uploadDesc);

      await api.post("/drawings/upload", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });

      // 重置表单
      setUploadName("");
      setUploadDesc("");
      setUploadFile(null);
      setShowUploadForm(false);
      if (fileInputRef.current) fileInputRef.current.value = "";

      // 刷新列表和统计
      fetchDrawings();
      fetchCategoryCounts();
    } catch (err: any) {
      alert(err.response?.data?.detail || "上传失败");
    } finally {
      setUploading(false);
    }
  };

  // 删除图纸
  const handleDelete = async (id: number) => {
    if (!confirm("确定要删除这张图纸吗？此操作不可撤销。")) return;
    try {
      await api.delete(`/drawings/${id}`);
      fetchDrawings();
      fetchCategoryCounts();
      if (previewDrawing?.id === id) setPreviewDrawing(null);
    } catch {
      alert("删除失败");
    }
  };

  // 下载图纸
  const handleDownload = async (drawing: Drawing) => {
    try {
      const res = await api.get(`/drawings/${drawing.id}/file`, {
        responseType: "blob",
      });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement("a");
      link.href = url;
      link.download = `${drawing.name}.${drawing.file_format || "bin"}`;
      link.click();
      window.URL.revokeObjectURL(url);
    } catch {
      alert("下载失败");
    }
  };

  // 预览图纸
  const handlePreview = (drawing: Drawing) => {
    setPreviewDrawing(drawing);
  };

  // ===== 渲染 =====

  // 分类总览视图
  if (!selectedCategory) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-bold text-slate-800 dark:text-white">
              图纸管理
            </h2>
            <p className="mt-1 text-sm text-slate-500">
              管理断面图、支护图、布置图、作业图表等配套图纸模板
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {CATEGORIES.map((cat) => (
            <Card
              key={cat.key}
              className="cursor-pointer transition-all hover:shadow-md hover:border-blue-300"
              onClick={() => handleSelectCategory(cat.key)}
            >
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-base">
                  <cat.icon className="h-5 w-5 text-blue-500" />
                  {cat.label}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-slate-500">{cat.desc}</p>
                <div className="mt-3 flex items-center justify-between">
                  <span className="text-xs font-medium text-blue-600">
                    {categoryCounts[cat.key] || 0} 份图纸
                  </span>
                  <FileImage className="h-4 w-4 text-slate-300" />
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    );
  }

  // 分类详情视图
  const currentCat = CATEGORIES.find((c) => c.key === selectedCategory);
  const totalPages = Math.ceil(total / pageSize);

  return (
    <div className="space-y-6">
      {/* 顶部导航 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Button
            variant="outline"
            size="sm"
            onClick={handleBackToCategories}
            className="gap-1"
          >
            <ChevronLeft className="h-4 w-4" />
            返回
          </Button>
          <div>
            <h2 className="text-xl font-bold text-slate-800 dark:text-white">
              {currentCat?.label}
            </h2>
            <p className="text-xs text-slate-500">{currentCat?.desc}</p>
          </div>
        </div>
        <Button
          className="gap-2"
          onClick={() => setShowUploadForm(!showUploadForm)}
        >
          <Upload className="h-4 w-4" />
          上传图纸
        </Button>
      </div>

      {/* 上传表单 */}
      {showUploadForm && (
        <Card className="border-blue-200 bg-blue-50/30">
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center justify-between text-base">
              上传新图纸
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setShowUploadForm(false)}
              >
                <X className="h-4 w-4" />
              </Button>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <div>
                <label className="mb-1 block text-sm font-medium text-slate-700">
                  图纸名称 *
                </label>
                <Input
                  placeholder="例如：矩形断面 5.0×3.6m"
                  value={uploadName}
                  onChange={(e) => setUploadName(e.target.value)}
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-slate-700">
                  选择文件 *
                </label>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".png,.jpg,.jpeg,.svg,.pdf,.dwg,.dxf"
                  onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
                  className="block w-full text-sm text-slate-500 file:mr-4 file:rounded-md file:border-0 file:bg-blue-50 file:px-4 file:py-2 file:text-sm file:font-medium file:text-blue-700 hover:file:bg-blue-100"
                />
              </div>
              <div className="md:col-span-2">
                <label className="mb-1 block text-sm font-medium text-slate-700">
                  描述（可选）
                </label>
                <Input
                  placeholder="图纸用途或补充说明"
                  value={uploadDesc}
                  onChange={(e) => setUploadDesc(e.target.value)}
                />
              </div>
              <div className="md:col-span-2 flex justify-end">
                <Button
                  disabled={!uploadFile || !uploadName || uploading}
                  onClick={handleUpload}
                  className="gap-2"
                >
                  {uploading ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Upload className="h-4 w-4" />
                  )}
                  {uploading ? "上传中..." : "确认上传"}
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* 搜索栏 */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <Input
            placeholder="搜索图纸名称..."
            value={searchName}
            onChange={(e) => {
              setSearchName(e.target.value);
              setPage(1);
            }}
            className="pl-10"
          />
        </div>
        <span className="text-sm text-slate-500">共 {total} 份图纸</span>
      </div>

      {/* 图纸列表 */}
      <Card>
        <CardContent className="p-0">
          {loading ? (
            <div className="flex items-center justify-center py-16">
              <Loader2 className="h-8 w-8 animate-spin text-blue-500" />
            </div>
          ) : drawings.length === 0 ? (
            <div className="flex flex-col items-center py-16 text-slate-400">
              <FileImage className="mb-3 h-12 w-12 opacity-30" />
              <p className="text-sm">暂无图纸，点击「上传图纸」添加</p>
              <p className="mt-1 text-xs">
                支持 PNG, JPG, SVG, DWG, PDF 格式
              </p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[240px]">名称</TableHead>
                  <TableHead>格式</TableHead>
                  <TableHead>大小</TableHead>
                  <TableHead>版本</TableHead>
                  <TableHead>描述</TableHead>
                  <TableHead className="text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {drawings.map((d) => (
                  <TableRow key={d.id}>
                    <TableCell className="font-medium">{d.name}</TableCell>
                    <TableCell>
                      <span className="inline-flex items-center rounded-md bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600 uppercase">
                        {d.file_format || "-"}
                      </span>
                    </TableCell>
                    <TableCell className="text-sm text-slate-500">
                      {formatFileSize(d.file_size)}
                    </TableCell>
                    <TableCell className="text-sm">v{d.version}</TableCell>
                    <TableCell className="text-sm text-slate-500 max-w-[200px] truncate">
                      {d.description || "-"}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end gap-1">
                        {isPreviewable(d.file_format) && (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handlePreview(d)}
                            title="预览"
                          >
                            <Eye className="h-4 w-4" />
                          </Button>
                        )}
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleDownload(d)}
                          title="下载"
                        >
                          <Download className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleDelete(d.id)}
                          title="删除"
                          className="text-red-500 hover:text-red-700"
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}

          {/* 分页 */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between border-t px-4 py-3">
              <span className="text-sm text-slate-500">
                第 {page}/{totalPages} 页
              </span>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page <= 1}
                  onClick={() => setPage(page - 1)}
                >
                  上一页
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page >= totalPages}
                  onClick={() => setPage(page + 1)}
                >
                  下一页
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* 预览区 */}
      {previewDrawing && (
        <Card className="border-blue-200">
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center justify-between text-base">
              <span>预览：{previewDrawing.name}</span>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setPreviewDrawing(null)}
              >
                <X className="h-4 w-4" />
              </Button>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <PreviewContent drawing={previewDrawing} />
          </CardContent>
        </Card>
      )}
    </div>
  );
}

/** 预览内容组件 — 根据文件格式自动选择渲染方式 */
function PreviewContent({ drawing }: { drawing: Drawing }) {
  const token =
    typeof window !== "undefined"
      ? localStorage.getItem("access_token")
      : null;
  const baseURL =
    process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001/api/v1";
  const fileUrl = `${baseURL}/drawings/${drawing.id}/file`;

  const [blobUrl, setBlobUrl] = useState<string | null>(null);

  useEffect(() => {
    // 使用带 Token 的 API 请求获取文件内容
    api
      .get(`/drawings/${drawing.id}/file`, { responseType: "blob" })
      .then((res) => {
        const url = window.URL.createObjectURL(new Blob([res.data]));
        setBlobUrl(url);
      })
      .catch(() => {
        setBlobUrl(null);
      });

    return () => {
      if (blobUrl) window.URL.revokeObjectURL(blobUrl);
    };
  }, [drawing.id]);

  if (!blobUrl) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-6 w-6 animate-spin text-blue-500" />
      </div>
    );
  }

  const format = drawing.file_format?.toLowerCase();

  if (format === "pdf") {
    return (
      <iframe
        src={blobUrl}
        className="h-[600px] w-full rounded-lg border"
        title={drawing.name}
      />
    );
  }

  if (["png", "jpg", "jpeg", "svg"].includes(format || "")) {
    return (
      <div className="flex justify-center rounded-lg bg-slate-50 p-4">
        <img
          src={blobUrl}
          alt={drawing.name}
          className="max-h-[500px] object-contain"
        />
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center py-12 text-slate-400">
      <FileImage className="mb-3 h-12 w-12 opacity-30" />
      <p className="text-sm">该格式暂不支持在线预览，请下载后查看</p>
    </div>
  );
}
