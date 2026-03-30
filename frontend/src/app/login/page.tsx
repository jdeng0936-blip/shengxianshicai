"use client";

import { useState, FormEvent } from "react";
import { useRouter } from "next/navigation";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Eye, EyeOff, Sparkles, Loader2 } from "lucide-react";
import api from "@/lib/api";
import { useAuthStore } from "@/lib/stores/auth-store";

/** 登录页 — 对接真实后端 /auth/login */
export default function LoginPage() {
  const router = useRouter();
  const setAuth = useAuthStore((s) => s.setAuth);

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPwd, setShowPwd] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleLogin = async (e: FormEvent) => {
    e.preventDefault();
    if (!username || !password) {
      setError("请输入用户名和密码");
      return;
    }
    setError("");
    setLoading(true);

    try {
      // 调用后端 JWT 登录接口
      const res = await api.post("/auth/login", { username, password });
      const token = res.data?.data?.access_token;
      if (!token) throw new Error("未返回 Token");

      // 存入认证 store + localStorage
      setAuth(token, { id: 0, username, tenant_id: 0 });
      localStorage.setItem("access_token", token);

      // 获取用户信息
      try {
        const profileRes = await api.get("/auth/profile", {
          headers: { Authorization: `Bearer ${token}` },
        });
        const profile = profileRes.data?.data;
        if (profile) {
          setAuth(token, profile);
        }
      } catch {
        // profile 获取失败不阻塞登录
      }

      router.push("/dashboard");
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      setError(detail || "登录失败，请检查用户名和密码");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-slate-900 via-blue-900 to-slate-800">
      <div className="w-full max-w-md space-y-6 rounded-2xl bg-slate-800/60 p-8 shadow-2xl backdrop-blur-xl">
        {/* Logo */}
        <div className="flex flex-col items-center gap-2">
          <div className="flex h-14 w-14 items-center justify-center rounded-xl bg-blue-600 shadow-lg">
            <Sparkles className="h-7 w-7 text-white" />
          </div>
          <h1 className="text-xl font-bold text-white">鲜标智投</h1>
          <p className="text-sm text-slate-400">生鲜食材配送投标文件智能生成平台</p>
        </div>

        {/* 表单 */}
        <form onSubmit={handleLogin} className="space-y-4">
          <div>
            <label className="mb-1.5 block text-sm text-slate-300">用户名</label>
            <Input
              placeholder="请输入用户名"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="bg-slate-700/50 text-white placeholder:text-slate-500"
              autoFocus
            />
          </div>
          <div>
            <label className="mb-1.5 block text-sm text-slate-300">密码</label>
            <div className="relative">
              <Input
                type={showPwd ? "text" : "password"}
                placeholder="请输入密码"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="bg-slate-700/50 pr-10 text-white placeholder:text-slate-500"
              />
              <button
                type="button"
                onClick={() => setShowPwd(!showPwd)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white"
              >
                {showPwd ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
          </div>

          {error && (
            <p className="rounded-md bg-red-900/30 px-3 py-2 text-sm text-red-400">{error}</p>
          )}

          <Button
            type="submit"
            className="w-full bg-blue-600 hover:bg-blue-700"
            disabled={loading}
          >
            {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            登 录
          </Button>
        </form>

        <button
          type="button"
          onClick={() => { setUsername("admin"); setPassword("admin123"); setTimeout(() => { const form = document.querySelector("form"); form?.requestSubmit(); }, 100); }}
          className="w-full rounded-md border border-slate-600 py-2 text-sm text-slate-300 transition hover:bg-slate-700 hover:text-white"
        >
          🧪 测试账号一键登录 (admin)
        </button>
      </div>
    </div>
  );
}
