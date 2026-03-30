"use client";

import AppSidebar from "@/components/business/app-sidebar";

/** Dashboard 布局 — 侧边栏 + 顶栏 + 内容区 */
export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex h-screen overflow-hidden">
      {/* 侧边栏 */}
      <AppSidebar />

      {/* 主内容区 */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* 顶栏 */}
        <header className="flex h-14 items-center justify-between border-b bg-white px-6 dark:bg-slate-950">
          <h1 className="text-sm font-medium text-slate-600">
            鲜标智投 — 生鲜食材配送投标文件智能生成平台
          </h1>
          <div className="flex items-center gap-4 text-sm text-slate-500">
            <span>智能投标 · 精准报价</span>
          </div>
        </header>

        {/* 页面内容 */}
        <main className="flex-1 overflow-y-auto bg-slate-100 p-6 dark:bg-slate-950">
          {children}
        </main>
      </div>
    </div>
  );
}
