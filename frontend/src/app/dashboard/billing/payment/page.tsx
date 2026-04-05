"use client";

import { useState, useEffect, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Receipt,
  Loader2,
  RefreshCw,
  Copy,
  CheckCircle2,
  Clock,
  XCircle,
  AlertCircle,
} from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";

// ── 类型定义 ────────────────────────────────────────────

interface PaymentOrder {
  id: number;
  order_no: string;
  order_type: string;
  amount: number;
  status: string;
  payment_method: string;
  paid_at: string | null;
  created_at: string | null;
}

interface OrderListResponse {
  items: PaymentOrder[];
  total: number;
  page: number;
}

// ── 常量映射 ────────────────────────────────────────────

const STATUS_CONFIG: Record<string, { label: string; variant: "default" | "secondary" | "destructive" | "outline"; icon: any }> = {
  pending:  { label: "待支付", variant: "secondary", icon: Clock },
  paid:     { label: "已支付", variant: "default", icon: CheckCircle2 },
  failed:   { label: "失败",   variant: "destructive", icon: XCircle },
  refunded: { label: "已退款", variant: "outline", icon: AlertCircle },
  expired:  { label: "已过期", variant: "outline", icon: Clock },
};

const ORDER_TYPE_LABELS: Record<string, string> = {
  per_document: "按篇付费",
  quarterly: "季度包",
  yearly: "年度包",
};

const PAYMENT_METHOD_LABELS: Record<string, string> = {
  manual: "手动转账",
  alipay: "支付宝",
  wechat: "微信支付",
};

// ── 主组件 ──────────────────────────────────────────────

export default function PaymentOrdersPage() {
  const [orders, setOrders] = useState<PaymentOrder[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [selectedOrder, setSelectedOrder] = useState<PaymentOrder | null>(null);

  const pageSize = 10;

  const fetchOrders = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, any> = { page, page_size: pageSize };
      if (statusFilter !== "all") {
        params.status = statusFilter;
      }
      const res = await api.get("/payments/orders", { params });
      const data: OrderListResponse = res.data?.data;
      setOrders(data.items || []);
      setTotal(data.total || 0);
    } catch (err: any) {
      toast.error(err.response?.data?.detail || "获取订单列表失败");
    } finally {
      setLoading(false);
    }
  }, [page, statusFilter]);

  useEffect(() => {
    fetchOrders();
  }, [fetchOrders]);

  const handleCopyOrderNo = (orderNo: string) => {
    navigator.clipboard.writeText(orderNo);
    toast.success("订单号已复制");
  };

  const totalPages = Math.ceil(total / pageSize);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-slate-800">订单管理</h2>
        <Button variant="outline" size="sm" onClick={fetchOrders} disabled={loading}>
          <RefreshCw className={`mr-2 h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          刷新
        </Button>
      </div>

      {/* 筛选栏 */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <span className="text-sm text-slate-500">状态筛选:</span>
              <Select value={statusFilter} onValueChange={(v) => { setStatusFilter(v || "all"); setPage(1); }}>
                <SelectTrigger className="w-[140px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">全部</SelectItem>
                  <SelectItem value="pending">待支付</SelectItem>
                  <SelectItem value="paid">已支付</SelectItem>
                  <SelectItem value="failed">失败</SelectItem>
                  <SelectItem value="refunded">已退款</SelectItem>
                  <SelectItem value="expired">已过期</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="text-sm text-slate-400">
              共 {total} 条记录
            </div>
          </div>
        </CardContent>
      </Card>

      {/* 订单列表 */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Receipt className="h-5 w-5" />
            订单记录
          </CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-8 w-8 animate-spin text-slate-400" />
            </div>
          ) : orders.length === 0 ? (
            <div className="py-12 text-center text-slate-400">
              暂无订单记录
            </div>
          ) : (
            <>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>订单号</TableHead>
                    <TableHead>套餐类型</TableHead>
                    <TableHead>金额</TableHead>
                    <TableHead>支付方式</TableHead>
                    <TableHead>状态</TableHead>
                    <TableHead>创建时间</TableHead>
                    <TableHead className="text-right">操作</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {orders.map((order) => {
                    const statusCfg = STATUS_CONFIG[order.status] || STATUS_CONFIG.pending;
                    const StatusIcon = statusCfg.icon;
                    return (
                      <TableRow key={order.id}>
                        <TableCell className="font-mono text-xs">
                          <div className="flex items-center gap-1">
                            <span>{order.order_no}</span>
                            <button
                              onClick={() => handleCopyOrderNo(order.order_no)}
                              className="text-slate-400 hover:text-slate-600"
                            >
                              <Copy className="h-3 w-3" />
                            </button>
                          </div>
                        </TableCell>
                        <TableCell>{ORDER_TYPE_LABELS[order.order_type] || order.order_type}</TableCell>
                        <TableCell className="font-medium">¥{order.amount}</TableCell>
                        <TableCell>{PAYMENT_METHOD_LABELS[order.payment_method] || order.payment_method}</TableCell>
                        <TableCell>
                          <Badge variant={statusCfg.variant} className="gap-1">
                            <StatusIcon className="h-3 w-3" />
                            {statusCfg.label}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-sm text-slate-500">
                          {order.created_at
                            ? new Date(order.created_at).toLocaleString("zh-CN")
                            : "-"}
                        </TableCell>
                        <TableCell className="text-right">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => setSelectedOrder(order)}
                          >
                            详情
                          </Button>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>

              {/* 分页 */}
              {totalPages > 1 && (
                <div className="mt-4 flex items-center justify-between">
                  <div className="text-sm text-slate-400">
                    第 {page} / {totalPages} 页
                  </div>
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={page <= 1}
                      onClick={() => setPage((p) => p - 1)}
                    >
                      上一页
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={page >= totalPages}
                      onClick={() => setPage((p) => p + 1)}
                    >
                      下一页
                    </Button>
                  </div>
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>

      {/* 订单详情弹窗 */}
      <Dialog open={!!selectedOrder} onOpenChange={() => setSelectedOrder(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>订单详情</DialogTitle>
          </DialogHeader>
          {selectedOrder && <OrderDetail order={selectedOrder} />}
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ── 订单详情子组件 ──────────────────────────────────────

function OrderDetail({ order }: { order: PaymentOrder }) {
  const statusCfg = STATUS_CONFIG[order.status] || STATUS_CONFIG.pending;
  const StatusIcon = statusCfg.icon;

  const rows = [
    { label: "订单号", value: order.order_no },
    { label: "套餐类型", value: ORDER_TYPE_LABELS[order.order_type] || order.order_type },
    { label: "订单金额", value: `¥${order.amount}` },
    { label: "支付方式", value: PAYMENT_METHOD_LABELS[order.payment_method] || order.payment_method },
    {
      label: "创建时间",
      value: order.created_at ? new Date(order.created_at).toLocaleString("zh-CN") : "-",
    },
    {
      label: "支付时间",
      value: order.paid_at ? new Date(order.paid_at).toLocaleString("zh-CN") : "-",
    },
  ];

  return (
    <div className="space-y-4">
      {/* 状态大标签 */}
      <div className="flex items-center justify-center gap-2 rounded-lg bg-slate-50 py-4">
        <StatusIcon className="h-6 w-6" />
        <span className="text-lg font-bold">{statusCfg.label}</span>
      </div>

      {/* 详情字段 */}
      <div className="space-y-3">
        {rows.map((row) => (
          <div key={row.label} className="flex items-center justify-between border-b border-slate-100 pb-2">
            <span className="text-sm text-slate-500">{row.label}</span>
            <span className="text-sm font-medium">{row.value}</span>
          </div>
        ))}
      </div>

      {/* 复制订单号 */}
      <Button
        variant="outline"
        className="w-full"
        onClick={() => {
          navigator.clipboard.writeText(order.order_no);
          toast.success("订单号已复制到剪贴板");
        }}
      >
        <Copy className="mr-2 h-4 w-4" />
        复制订单号
      </Button>
    </div>
  );
}
