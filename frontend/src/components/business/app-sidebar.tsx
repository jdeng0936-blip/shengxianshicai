"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Database,
  LayoutDashboard,
  LogOut,
  Bot,
  Library,
  ClipboardList,
  CreditCard,
  Radar,
} from "lucide-react";
import { useAuthStore } from "@/lib/stores/auth-store";

/** 侧边栏导航项配置 */
const NAV_ITEMS = [
  { href: "/dashboard", label: "工作台", icon: LayoutDashboard },
  { href: "/dashboard/bid-projects", label: "投标项目", icon: ClipboardList },
  { href: "/dashboard/tender-notices", label: "商机雷达", icon: Radar },
  { href: "/dashboard/ai", label: "AI 助手", icon: Bot },
  { href: "/dashboard/knowledge", label: "知识库", icon: Library },
  { href: "/dashboard/billing", label: "计费中心", icon: CreditCard },
  { href: "/dashboard/system", label: "系统管理", icon: Database },
];

export default function AppSidebar() {
  const pathname = usePathname();
  const logout = useAuthStore((s) => s.logout);

  return (
    <aside className="flex h-screen w-60 flex-col border-r bg-slate-50 dark:bg-slate-900">
      {/* Logo 区域 */}
      <div className="flex h-14 items-center border-b px-4">
        <span className="text-lg font-bold text-slate-800 dark:text-white">
          鲜标智投
        </span>
      </div>

      {/* 导航菜单 */}
      <nav className="flex-1 overflow-y-auto py-4">
        <ul className="space-y-1 px-2">
          {NAV_ITEMS.map((item) => {
            const isActive = pathname === item.href || pathname.startsWith(item.href + "/");
            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                    isActive
                      ? "bg-slate-200 text-slate-900 dark:bg-slate-800 dark:text-white"
                      : "text-slate-600 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
                  }`}
                >
                  <item.icon className="h-4 w-4" />
                  {item.label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      {/* 底部退出 */}
      <div className="border-t p-2">
        <button
          onClick={() => {
            logout();
            window.location.href = "/login";
          }}
          className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800"
        >
          <LogOut className="h-4 w-4" />
          退出登录
        </button>
      </div>
    </aside>
  );
}
