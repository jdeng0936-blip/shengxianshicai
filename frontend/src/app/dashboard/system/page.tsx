"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  Users, Shield, Building2, FileText, BookOpen,
  ChevronLeft, Plus, Trash2, Pencil, RotateCcw, Power,
  Loader2, Search, X,
} from "lucide-react";
import api from "@/lib/api";

// ========== 类型定义 ==========
interface User {
  id: number; username: string; real_name: string | null;
  role_id: number | null; role_name: string | null;
  is_active: boolean; tenant_id: number; created_at: string | null;
}
interface Role {
  id: number; name: string; description: string | null; created_at: string | null;
}
interface Mine {
  id: number; name: string; company: string | null; gas_level: string | null;
  address: string | null; contact: string | null; phone: string | null; created_at: string | null;
}
interface AuditLogItem {
  id: number; user_id: number; username: string; action: string;
  resource: string; detail: string | null; ip_address: string | null;
  created_at: string | null;
}
interface DictItem {
  id: number; dict_type: string; dict_key: string; dict_value: string;
  sort_order: number; is_active: boolean; created_at: string | null;
}

interface ModuleInfo {
  key: string; label: string; icon: React.ElementType; desc: string;
}

const MODULES: ModuleInfo[] = [
  { key: "users", label: "用户管理", desc: "系统用户的增删改查、密码重置", icon: Users },
  { key: "roles", label: "角色权限", desc: "角色定义与权限矩阵配置", icon: Shield },
  { key: "mines", label: "企业配置", desc: "投标企业基础信息管理", icon: Building2 },
  { key: "logs", label: "操作日志", desc: "系统操作审计日志查询", icon: FileText },
  { key: "dicts", label: "数据字典", desc: "业务下拉选项数据源管理", icon: BookOpen },
];

/** 系统管理页面 */
export default function SystemPage() {
  const [selected, setSelected] = useState<string | null>(null);

  if (!selected) {
    return (
      <div className="space-y-6">
        <div>
          <h2 className="text-2xl font-bold text-slate-800 dark:text-white">系统管理</h2>
          <p className="mt-1 text-sm text-slate-500">用户管理 · 角色权限 · 企业配置 · 操作日志 · 数据字典</p>
        </div>
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {MODULES.map((mod) => (
            <Card key={mod.key} className="cursor-pointer transition-all hover:shadow-md hover:border-blue-300"
              onClick={() => setSelected(mod.key)}>
              <CardContent className="flex items-center gap-4 py-5">
                <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br from-blue-50 to-indigo-100">
                  <mod.icon className="h-6 w-6 text-blue-600" />
                </div>
                <div className="flex-1">
                  <h3 className="font-semibold">{mod.label}</h3>
                  <p className="text-xs text-slate-500">{mod.desc}</p>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    );
  }

  const currentMod = MODULES.find((m) => m.key === selected)!;
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Button variant="outline" size="sm" onClick={() => setSelected(null)} className="gap-1">
          <ChevronLeft className="h-4 w-4" /> 返回
        </Button>
        <div>
          <h2 className="text-xl font-bold text-slate-800 dark:text-white">{currentMod.label}</h2>
          <p className="text-xs text-slate-500">{currentMod.desc}</p>
        </div>
      </div>
      {selected === "users" && <UserPanel />}
      {selected === "roles" && <RolePanel />}
      {selected === "mines" && <MinePanel />}
      {selected === "logs" && <LogPanel />}
      {selected === "dicts" && <DictPanel />}
    </div>
  );
}

// ==================== 用户管理面板 ====================
function UserPanel() {
  const [users, setUsers] = useState<User[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);
  const [roles, setRoles] = useState<Role[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ username: "", password: "", real_name: "", role_id: "" });
  const [resetPwd, setResetPwd] = useState<number | null>(null);
  const [newPwd, setNewPwd] = useState("");

  const fetchUsers = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get("/system/users", { params: { page, page_size: 15, username: search || undefined } });
      setUsers(res.data.data?.items || []); setTotal(res.data.data?.total || 0);
    } catch {} finally { setLoading(false); }
  }, [page, search]);

  const fetchRoles = useCallback(async () => {
    try { const r = await api.get("/system/roles"); setRoles(r.data.data || []); } catch {}
  }, []);

  useEffect(() => { fetchUsers(); fetchRoles(); }, [fetchUsers, fetchRoles]);

  const handleCreate = async () => {
    try {
      await api.post("/system/users", {
        username: form.username, password: form.password,
        real_name: form.real_name || null,
        role_id: form.role_id ? parseInt(form.role_id) : null,
      });
      setShowForm(false); setForm({ username: "", password: "", real_name: "", role_id: "" });
      fetchUsers();
    } catch (e: any) { alert(e.response?.data?.detail || "创建失败"); }
  };

  const handleToggle = async (id: number) => {
    await api.put(`/system/users/${id}/toggle`); fetchUsers();
  };

  const handleResetPwd = async () => {
    if (!resetPwd || !newPwd) return;
    await api.put(`/system/users/${resetPwd}/password`, { new_password: newPwd });
    setResetPwd(null); setNewPwd(""); alert("密码重置成功");
  };

  const pageSize = 15; const totalPages = Math.ceil(total / pageSize);

  return (
    <>
      {/* 工具栏 */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <Input placeholder="搜索用户名..." value={search} onChange={(e) => { setSearch(e.target.value); setPage(1); }} className="pl-10" />
        </div>
        <span className="text-sm text-slate-500">共 {total} 位用户</span>
        <Button className="gap-1 ml-auto" onClick={() => setShowForm(!showForm)}>
          <Plus className="h-4 w-4" /> 新增用户
        </Button>
      </div>

      {/* 新增表单 */}
      {showForm && (
        <Card className="border-blue-200 bg-blue-50/30">
          <CardContent className="pt-4">
            <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
              <Input placeholder="用户名 *" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} />
              <Input placeholder="密码 *" type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
              <Input placeholder="真实姓名" value={form.real_name} onChange={(e) => setForm({ ...form, real_name: e.target.value })} />
              <select className="rounded-md border px-3 py-2 text-sm" value={form.role_id} onChange={(e) => setForm({ ...form, role_id: e.target.value })}>
                <option value="">选择角色</option>
                {roles.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
              </select>
            </div>
            <div className="mt-3 flex justify-end gap-2">
              <Button variant="outline" size="sm" onClick={() => setShowForm(false)}>取消</Button>
              <Button size="sm" disabled={!form.username || !form.password} onClick={handleCreate}>创建</Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* 密码重置 */}
      {resetPwd && (
        <Card className="border-amber-200 bg-amber-50/30">
          <CardContent className="flex items-center gap-3 pt-4">
            <span className="text-sm font-medium">重置用户 #{resetPwd} 的密码：</span>
            <Input placeholder="新密码" type="password" value={newPwd} onChange={(e) => setNewPwd(e.target.value)} className="max-w-xs" />
            <Button size="sm" disabled={!newPwd} onClick={handleResetPwd}>确认重置</Button>
            <Button variant="ghost" size="sm" onClick={() => { setResetPwd(null); setNewPwd(""); }}><X className="h-4 w-4" /></Button>
          </CardContent>
        </Card>
      )}

      {/* 表格 */}
      <Card>
        <CardContent className="p-0">
          {loading ? (
            <div className="flex justify-center py-16"><Loader2 className="h-8 w-8 animate-spin text-blue-500" /></div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>ID</TableHead><TableHead>用户名</TableHead><TableHead>姓名</TableHead>
                  <TableHead>角色</TableHead><TableHead>状态</TableHead><TableHead className="text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {users.map((u) => (
                  <TableRow key={u.id}>
                    <TableCell>{u.id}</TableCell>
                    <TableCell className="font-medium">{u.username}</TableCell>
                    <TableCell>{u.real_name || "-"}</TableCell>
                    <TableCell><span className="rounded bg-slate-100 px-2 py-0.5 text-xs">{u.role_name || "-"}</span></TableCell>
                    <TableCell>
                      <span className={`rounded-full px-2 py-0.5 text-xs ${u.is_active ? "bg-green-100 text-green-700" : "bg-red-100 text-red-600"}`}>
                        {u.is_active ? "启用" : "禁用"}
                      </span>
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end gap-1">
                        <Button variant="ghost" size="sm" title="切换状态" onClick={() => handleToggle(u.id)}><Power className="h-4 w-4" /></Button>
                        <Button variant="ghost" size="sm" title="重置密码" onClick={() => setResetPwd(u.id)}><RotateCcw className="h-4 w-4" /></Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
          {totalPages > 1 && (
            <div className="flex items-center justify-between border-t px-4 py-3">
              <span className="text-sm text-slate-500">第 {page}/{totalPages} 页</span>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>上一页</Button>
                <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage(page + 1)}>下一页</Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </>
  );
}

// ==================== 角色管理面板 ====================
function RolePanel() {
  const [roles, setRoles] = useState<Role[]>([]);
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);
  const [form, setForm] = useState({ name: "", description: "" });

  const fetchRoles = useCallback(async () => {
    setLoading(true);
    try { const r = await api.get("/system/roles"); setRoles(r.data.data || []); } catch {} finally { setLoading(false); }
  }, []);
  useEffect(() => { fetchRoles(); }, [fetchRoles]);

  const handleSave = async () => {
    try {
      if (editId) {
        await api.put(`/system/roles/${editId}`, form);
      } else {
        await api.post("/system/roles", form);
      }
      resetForm(); fetchRoles();
    } catch (e: any) { alert(e.response?.data?.detail || "保存失败"); }
  };
  const handleDelete = async (id: number) => {
    if (!confirm("确定删除此角色？")) return;
    await api.delete(`/system/roles/${id}`); fetchRoles();
  };
  const startEdit = (r: Role) => { setEditId(r.id); setForm({ name: r.name, description: r.description || "" }); setShowForm(true); };
  const resetForm = () => { setEditId(null); setForm({ name: "", description: "" }); setShowForm(false); };

  return (
    <>
      <div className="flex items-center justify-between">
        <span className="text-sm text-slate-500">共 {roles.length} 个角色</span>
        <Button className="gap-1" onClick={() => { resetForm(); setShowForm(!showForm); }}><Plus className="h-4 w-4" /> 新增角色</Button>
      </div>
      {showForm && (
        <Card className="border-blue-200 bg-blue-50/30">
          <CardContent className="pt-4">
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              <Input placeholder="角色名 *" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
              <Input placeholder="描述" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
            </div>
            <div className="mt-3 flex justify-end gap-2">
              <Button variant="outline" size="sm" onClick={resetForm}>取消</Button>
              <Button size="sm" disabled={!form.name} onClick={handleSave}>{editId ? "保存" : "创建"}</Button>
            </div>
          </CardContent>
        </Card>
      )}
      <Card>
        <CardContent className="p-0">
          {loading ? <div className="flex justify-center py-16"><Loader2 className="h-8 w-8 animate-spin text-blue-500" /></div> : (
            <Table>
              <TableHeader><TableRow><TableHead>ID</TableHead><TableHead>角色名</TableHead><TableHead>描述</TableHead><TableHead className="text-right">操作</TableHead></TableRow></TableHeader>
              <TableBody>
                {roles.map((r) => (
                  <TableRow key={r.id}>
                    <TableCell>{r.id}</TableCell><TableCell className="font-medium">{r.name}</TableCell><TableCell className="text-sm text-slate-500">{r.description || "-"}</TableCell>
                    <TableCell className="text-right">
                      <Button variant="ghost" size="sm" onClick={() => startEdit(r)}><Pencil className="h-4 w-4" /></Button>
                      <Button variant="ghost" size="sm" className="text-red-500" onClick={() => handleDelete(r.id)}><Trash2 className="h-4 w-4" /></Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </>
  );
}

// ==================== 矿井配置面板 ====================
function MinePanel() {
  const [mines, setMines] = useState<Mine[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);
  const [form, setForm] = useState({ name: "", company: "", gas_level: "", address: "", contact: "", phone: "" });

  const fetchMines = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get("/system/mines", { params: { page, page_size: 15 } });
      setMines(r.data.data?.items || []); setTotal(r.data.data?.total || 0);
    } catch {} finally { setLoading(false); }
  }, [page]);
  useEffect(() => { fetchMines(); }, [fetchMines]);

  const handleSave = async () => {
    try {
      const payload = { ...form, company: form.company || null, gas_level: form.gas_level || null, address: form.address || null, contact: form.contact || null, phone: form.phone || null };
      if (editId) { await api.put(`/system/mines/${editId}`, payload); } else { await api.post("/system/mines", payload); }
      resetForm(); fetchMines();
    } catch (e: any) { alert(e.response?.data?.detail || "保存失败"); }
  };
  const handleDelete = async (id: number) => { if (!confirm("确定删除此矿井？")) return; await api.delete(`/system/mines/${id}`); fetchMines(); };
  const startEdit = (m: Mine) => {
    setEditId(m.id); setForm({ name: m.name, company: m.company || "", gas_level: m.gas_level || "", address: m.address || "", contact: m.contact || "", phone: m.phone || "" }); setShowForm(true);
  };
  const resetForm = () => { setEditId(null); setForm({ name: "", company: "", gas_level: "", address: "", contact: "", phone: "" }); setShowForm(false); };

  const pageSize = 15; const totalPages = Math.ceil(total / pageSize);

  return (
    <>
      <div className="flex items-center justify-between">
        <span className="text-sm text-slate-500">共 {total} 个矿井</span>
        <Button className="gap-1" onClick={() => { resetForm(); setShowForm(!showForm); }}><Plus className="h-4 w-4" /> 新增矿井</Button>
      </div>
      {showForm && (
        <Card className="border-blue-200 bg-blue-50/30">
          <CardContent className="pt-4">
            <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
              <Input placeholder="矿井名称 *" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
              <Input placeholder="所属公司" value={form.company} onChange={(e) => setForm({ ...form, company: e.target.value })} />
              <select className="rounded-md border px-3 py-2 text-sm" value={form.gas_level} onChange={(e) => setForm({ ...form, gas_level: e.target.value })}>
                <option value="">瓦斯等级</option>
                <option value="低瓦斯">低瓦斯</option><option value="高瓦斯">高瓦斯</option><option value="煤与瓦斯突出">煤与瓦斯突出</option>
              </select>
              <Input placeholder="矿井地址" value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} />
              <Input placeholder="联系人" value={form.contact} onChange={(e) => setForm({ ...form, contact: e.target.value })} />
              <Input placeholder="联系电话" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
            </div>
            <div className="mt-3 flex justify-end gap-2">
              <Button variant="outline" size="sm" onClick={resetForm}>取消</Button>
              <Button size="sm" disabled={!form.name} onClick={handleSave}>{editId ? "保存" : "创建"}</Button>
            </div>
          </CardContent>
        </Card>
      )}
      <Card>
        <CardContent className="p-0">
          {loading ? <div className="flex justify-center py-16"><Loader2 className="h-8 w-8 animate-spin text-blue-500" /></div> : (
            <Table>
              <TableHeader><TableRow>
                <TableHead>名称</TableHead><TableHead>公司</TableHead><TableHead>瓦斯等级</TableHead>
                <TableHead>联系人</TableHead><TableHead className="text-right">操作</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {mines.map((m) => (
                  <TableRow key={m.id}>
                    <TableCell className="font-medium">{m.name}</TableCell>
                    <TableCell className="text-sm text-slate-500">{m.company || "-"}</TableCell>
                    <TableCell><span className="rounded bg-slate-100 px-2 py-0.5 text-xs">{m.gas_level || "-"}</span></TableCell>
                    <TableCell className="text-sm">{m.contact || "-"}</TableCell>
                    <TableCell className="text-right">
                      <Button variant="ghost" size="sm" onClick={() => startEdit(m)}><Pencil className="h-4 w-4" /></Button>
                      <Button variant="ghost" size="sm" className="text-red-500" onClick={() => handleDelete(m.id)}><Trash2 className="h-4 w-4" /></Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
          {totalPages > 1 && (
            <div className="flex items-center justify-between border-t px-4 py-3">
              <span className="text-sm text-slate-500">第 {page}/{totalPages} 页</span>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>上一页</Button>
                <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage(page + 1)}>下一页</Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </>
  );
}

// ==================== 操作日志面板 ====================
function LogPanel() {
  const [logs, setLogs] = useState<AuditLogItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [filterAction, setFilterAction] = useState("");
  const [filterUser, setFilterUser] = useState("");

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get("/system/logs", { params: { page, page_size: 20, action: filterAction || undefined, username: filterUser || undefined } });
      setLogs(r.data.data?.items || []); setTotal(r.data.data?.total || 0);
    } catch {} finally { setLoading(false); }
  }, [page, filterAction, filterUser]);
  useEffect(() => { fetchLogs(); }, [fetchLogs]);

  const pageSize = 20; const totalPages = Math.ceil(total / pageSize);
  const actionColors: Record<string, string> = {
    create: "bg-green-100 text-green-700", update: "bg-blue-100 text-blue-700",
    delete: "bg-red-100 text-red-600", login: "bg-purple-100 text-purple-700",
  };

  return (
    <>
      <div className="flex items-center gap-3">
        <select className="rounded-md border px-3 py-2 text-sm" value={filterAction} onChange={(e) => { setFilterAction(e.target.value); setPage(1); }}>
          <option value="">全部操作</option>
          <option value="create">创建</option><option value="update">更新</option><option value="delete">删除</option><option value="login">登录</option>
        </select>
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <Input placeholder="搜索操作人..." value={filterUser} onChange={(e) => { setFilterUser(e.target.value); setPage(1); }} className="pl-10" />
        </div>
        <span className="text-sm text-slate-500 ml-auto">共 {total} 条日志</span>
      </div>
      <Card>
        <CardContent className="p-0">
          {loading ? <div className="flex justify-center py-16"><Loader2 className="h-8 w-8 animate-spin text-blue-500" /></div> : logs.length === 0 ? (
            <div className="flex flex-col items-center py-16 text-slate-400">
              <FileText className="mb-3 h-12 w-12 opacity-30" /><p className="text-sm">暂无操作日志</p>
            </div>
          ) : (
            <Table>
              <TableHeader><TableRow>
                <TableHead>时间</TableHead><TableHead>操作人</TableHead><TableHead>操作</TableHead>
                <TableHead>资源</TableHead><TableHead>详情</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {logs.map((l) => (
                  <TableRow key={l.id}>
                    <TableCell className="text-xs text-slate-500 whitespace-nowrap">{l.created_at ? new Date(l.created_at).toLocaleString("zh-CN") : "-"}</TableCell>
                    <TableCell className="font-medium">{l.username}</TableCell>
                    <TableCell><span className={`rounded-full px-2 py-0.5 text-xs ${actionColors[l.action] || "bg-slate-100"}`}>{l.action}</span></TableCell>
                    <TableCell className="text-sm">{l.resource}</TableCell>
                    <TableCell className="text-sm text-slate-500 max-w-[250px] truncate">{l.detail || "-"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
          {totalPages > 1 && (
            <div className="flex items-center justify-between border-t px-4 py-3">
              <span className="text-sm text-slate-500">第 {page}/{totalPages} 页</span>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>上一页</Button>
                <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage(page + 1)}>下一页</Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </>
  );
}

// ==================== 数据字典面板 ====================
function DictPanel() {
  const [items, setItems] = useState<DictItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [filterType, setFilterType] = useState("");
  const [types, setTypes] = useState<string[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);
  const [form, setForm] = useState({ dict_type: "", dict_key: "", dict_value: "", sort_order: "0" });

  const fetchTypes = useCallback(async () => {
    try { const r = await api.get("/system/dicts/types"); setTypes(r.data.data || []); } catch {}
  }, []);
  const fetchItems = useCallback(async () => {
    setLoading(true);
    try { const r = await api.get("/system/dicts", { params: { dict_type: filterType || undefined } }); setItems(r.data.data || []); } catch {} finally { setLoading(false); }
  }, [filterType]);
  useEffect(() => { fetchTypes(); fetchItems(); }, [fetchTypes, fetchItems]);

  const handleSave = async () => {
    try {
      const payload = { ...form, sort_order: parseInt(form.sort_order) || 0 };
      if (editId) { await api.put(`/system/dicts/${editId}`, payload); } else { await api.post("/system/dicts", payload); }
      resetForm(); fetchItems(); fetchTypes();
    } catch (e: any) { alert(e.response?.data?.detail || "保存失败"); }
  };
  const handleDelete = async (id: number) => { if (!confirm("确定删除？")) return; await api.delete(`/system/dicts/${id}`); fetchItems(); fetchTypes(); };
  const startEdit = (d: DictItem) => { setEditId(d.id); setForm({ dict_type: d.dict_type, dict_key: d.dict_key, dict_value: d.dict_value, sort_order: String(d.sort_order) }); setShowForm(true); };
  const resetForm = () => { setEditId(null); setForm({ dict_type: "", dict_key: "", dict_value: "", sort_order: "0" }); setShowForm(false); };

  // 按类型分组
  const grouped: Record<string, DictItem[]> = {};
  items.forEach((i) => { (grouped[i.dict_type] ||= []).push(i); });

  return (
    <>
      <div className="flex items-center gap-3">
        <select className="rounded-md border px-3 py-2 text-sm" value={filterType} onChange={(e) => setFilterType(e.target.value)}>
          <option value="">全部类型</option>
          {types.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <span className="text-sm text-slate-500">共 {items.length} 项</span>
        <Button className="gap-1 ml-auto" onClick={() => { resetForm(); setShowForm(!showForm); }}><Plus className="h-4 w-4" /> 新增字典项</Button>
      </div>
      {showForm && (
        <Card className="border-blue-200 bg-blue-50/30">
          <CardContent className="pt-4">
            <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
              <Input placeholder="类型 * (如 rock_class)" value={form.dict_type} onChange={(e) => setForm({ ...form, dict_type: e.target.value })} disabled={!!editId} />
              <Input placeholder="键 *" value={form.dict_key} onChange={(e) => setForm({ ...form, dict_key: e.target.value })} />
              <Input placeholder="值（显示文本）*" value={form.dict_value} onChange={(e) => setForm({ ...form, dict_value: e.target.value })} />
              <Input placeholder="排序" type="number" value={form.sort_order} onChange={(e) => setForm({ ...form, sort_order: e.target.value })} />
            </div>
            <div className="mt-3 flex justify-end gap-2">
              <Button variant="outline" size="sm" onClick={resetForm}>取消</Button>
              <Button size="sm" disabled={!form.dict_type || !form.dict_key || !form.dict_value} onClick={handleSave}>{editId ? "保存" : "创建"}</Button>
            </div>
          </CardContent>
        </Card>
      )}
      <Card>
        <CardContent className="p-0">
          {loading ? <div className="flex justify-center py-16"><Loader2 className="h-8 w-8 animate-spin text-blue-500" /></div> : items.length === 0 ? (
            <div className="flex flex-col items-center py-16 text-slate-400">
              <BookOpen className="mb-3 h-12 w-12 opacity-30" /><p className="text-sm">暂无字典项，点击「新增字典项」添加</p>
            </div>
          ) : (
            <Table>
              <TableHeader><TableRow>
                <TableHead>类型</TableHead><TableHead>键</TableHead><TableHead>值</TableHead>
                <TableHead>排序</TableHead><TableHead>状态</TableHead><TableHead className="text-right">操作</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {items.map((d) => (
                  <TableRow key={d.id}>
                    <TableCell><span className="rounded bg-indigo-50 px-2 py-0.5 text-xs text-indigo-600">{d.dict_type}</span></TableCell>
                    <TableCell className="font-medium">{d.dict_key}</TableCell>
                    <TableCell>{d.dict_value}</TableCell>
                    <TableCell className="text-sm text-slate-500">{d.sort_order}</TableCell>
                    <TableCell><span className={`rounded-full px-2 py-0.5 text-xs ${d.is_active ? "bg-green-100 text-green-700" : "bg-red-100 text-red-600"}`}>{d.is_active ? "启用" : "禁用"}</span></TableCell>
                    <TableCell className="text-right">
                      <Button variant="ghost" size="sm" onClick={() => startEdit(d)}><Pencil className="h-4 w-4" /></Button>
                      <Button variant="ghost" size="sm" className="text-red-500" onClick={() => handleDelete(d.id)}><Trash2 className="h-4 w-4" /></Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </>
  );
}
