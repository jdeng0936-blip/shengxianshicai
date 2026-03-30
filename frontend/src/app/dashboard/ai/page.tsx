"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Bot,
  Send,
  User,
  Loader2,
  Sparkles,
  Wrench,
  AlertTriangle,
  Plus,
  MessageSquare,
  Trash2,
  Archive,
  ChevronLeft,
  ChevronRight as ChevronRightIcon,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { motion, AnimatePresence } from "framer-motion";
import api from "@/lib/api";

/** API 基础地址 */
const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

/** 快捷提示 */
const QUICK_PROMPTS = [
  { emoji: "📄", text: "帮我分析这份学校食堂食材配送招标文件的评分标准" },
  { emoji: "🧊", text: "冷链配送温控方案应该怎么写才能得高分？" },
  { emoji: "📊", text: "帮我核查企业资质是否满足招标要求" },
  { emoji: "💰", text: "这个项目预算500万，下浮率多少合适？" },
  { emoji: "🔍", text: "检索食品安全法中关于进货查验的条款" },
  { emoji: "✍️", text: "帮我优化第三章食材采购与质量保障方案" },
];

interface Message {
  role: "user" | "assistant" | "tool";
  content: string;
  toolName?: string;
}

interface ChatSessionData {
  id: number;
  title: string | null;
  project_id: number | null;
  message_count: number;
  created_at: string | null;
  updated_at: string | null;
}

/** 消息气泡动画配置 */
const bubbleVariants = {
  hidden: { opacity: 0, y: 12, scale: 0.95 },
  visible: {
    opacity: 1,
    y: 0,
    scale: 1,
    transition: { duration: 0.25, ease: "easeOut" as const },
  },
};

export default function AIChatPage() {
  // 会话列表状态
  const [sessions, setSessions] = useState<ChatSessionData[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<number | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [loadingSessions, setLoadingSessions] = useState(false);

  // 对话状态
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  // 自动滚动到底部
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  /** 加载会话列表 */
  const loadSessions = useCallback(async () => {
    setLoadingSessions(true);
    try {
      const res = await api.get("/chat/sessions");
      setSessions(res.data?.data || []);
    } catch {
      // 接口不可用时静默
    } finally {
      setLoadingSessions(false);
    }
  }, []);

  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  /** 加载指定会话的消息历史 */
  const loadSessionMessages = useCallback(async (sessionId: number) => {
    try {
      const res = await api.get(`/chat/sessions/${sessionId}/messages`);
      const msgs: Message[] = (res.data?.data || []).map((m: any) => ({
        role: m.role === "tool" ? "tool" : m.role,
        content: m.content,
        toolName: m.tool_name,
      }));
      setMessages(msgs);
    } catch {
      setMessages([]);
    }
  }, []);

  /** 切换会话 */
  const switchSession = useCallback(
    async (sessionId: number) => {
      setActiveSessionId(sessionId);
      await loadSessionMessages(sessionId);
    },
    [loadSessionMessages]
  );

  /** 创建新对话 */
  const startNewChat = () => {
    setActiveSessionId(null);
    setMessages([]);
    setInput("");
  };

  /** 删除会话 */
  const deleteSession = async (sessionId: number, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm("确定删除此会话及其所有消息？")) return;
    try {
      await api.delete(`/chat/sessions/${sessionId}`);
      setSessions((prev) => prev.filter((s) => s.id !== sessionId));
      if (activeSessionId === sessionId) {
        startNewChat();
      }
    } catch {
      /* 静默 */
    }
  };

  /** 发送消息（SSE 流式 + 持久化） */
  const sendMessage = async (text: string) => {
    if (!text.trim() || loading) return;

    const userMsg: Message = { role: "user", content: text };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    try {
      const token =
        typeof window !== "undefined"
          ? localStorage.getItem("access_token")
          : "";
      const res = await fetch(`${API_BASE}/chat/send`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token || ""}`,
        },
        body: JSON.stringify({
          session_id: activeSessionId,
          message: text,
          stream: true,
          industry_type: "fresh_food",
        }),
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      // 从响应头获取会话 ID
      const newSessionId = res.headers.get("X-Session-Id");
      if (newSessionId && !activeSessionId) {
        const sid = parseInt(newSessionId, 10);
        setActiveSessionId(sid);
        // 刷新会话列表
        loadSessions();
      }

      const reader = res.body?.getReader();
      if (!reader) throw new Error("No reader");

      const decoder = new TextDecoder();
      let assistantContent = "";
      let buffer = "";

      // 先添加空的助手消息
      setMessages((prev) => [...prev, { role: "assistant", content: "" }]);

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const data = line.slice(6).trim();
          if (data === "[DONE]") continue;

          try {
            const evt = JSON.parse(data);

            if (evt.type === "tool_start") {
              const toolName = evt.name || evt.tool_name;
              setMessages((prev) => [
                ...prev.slice(0, -1),
                {
                  role: "tool",
                  content: `正在调用: ${toolName}`,
                  toolName,
                },
                { role: "assistant", content: assistantContent },
              ]);
            } else if (evt.type === "tool_done") {
              const toolName = evt.name || evt.tool_name;
              setMessages((prev) => {
                const list = [...prev];
                const toolIdx = list.findLastIndex((m) => m.role === "tool");
                if (toolIdx >= 0) {
                  list[toolIdx].content = `✅ ${toolName} 完成`;
                }
                return list;
              });
            } else if (evt.type === "text" || evt.type === "content") {
              assistantContent += evt.content || evt.text || "";
              setMessages((prev) => {
                const list = [...prev];
                list[list.length - 1] = {
                  role: "assistant",
                  content: assistantContent,
                };
                return list;
              });
            }
          } catch {
            assistantContent += data;
            setMessages((prev) => {
              const list = [...prev];
              list[list.length - 1] = {
                role: "assistant",
                content: assistantContent,
              };
              return list;
            });
          }
        }
      }

      // 流结束后刷新会话列表（更新消息计数等）
      loadSessions();
    } catch (err: any) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `⚠️ 请求失败: ${err.message}。请检查后端是否运行以及 API Key 是否配置。`,
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex h-[calc(100vh-3.5rem)] bg-slate-50/60">
      {/* ============ 左侧：会话列表 ============ */}
      <AnimatePresence initial={false}>
        {sidebarOpen && (
          <motion.div
            initial={{ width: 0, opacity: 0 }}
            animate={{ width: 280, opacity: 1 }}
            exit={{ width: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="flex flex-col border-r bg-white/90 backdrop-blur overflow-hidden"
          >
            {/* 新建对话按钮 */}
            <div className="flex items-center gap-2 border-b px-3 py-3">
              <Button
                onClick={startNewChat}
                className="flex-1 gap-2 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 shadow-md shadow-blue-200/40 text-sm"
                size="sm"
              >
                <Plus className="h-4 w-4" /> 新对话
              </Button>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setSidebarOpen(false)}
                className="h-8 w-8 shrink-0"
              >
                <ChevronLeft className="h-4 w-4" />
              </Button>
            </div>

            {/* 会话列表 */}
            <div className="flex-1 overflow-y-auto py-1">
              {loadingSessions && sessions.length === 0 && (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="h-5 w-5 animate-spin text-slate-300" />
                </div>
              )}

              {sessions.length === 0 && !loadingSessions && (
                <div className="px-4 py-8 text-center text-sm text-slate-400">
                  暂无对话记录
                </div>
              )}

              {sessions.map((s) => (
                <div
                  key={s.id}
                  onClick={() => switchSession(s.id)}
                  className={`group mx-2 mb-0.5 flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors ${
                    activeSessionId === s.id
                      ? "bg-blue-50 text-blue-700 border border-blue-200"
                      : "text-slate-600 hover:bg-slate-50"
                  }`}
                >
                  <MessageSquare className="h-4 w-4 shrink-0 opacity-50" />
                  <div className="flex-1 min-w-0">
                    <div className="truncate font-medium">
                      {s.title || "新对话"}
                    </div>
                    <div className="mt-0.5 text-xs text-slate-400">
                      {s.message_count} 条消息
                    </div>
                  </div>
                  <button
                    onClick={(e) => deleteSession(s.id, e)}
                    className="hidden group-hover:flex h-6 w-6 items-center justify-center rounded-md text-slate-400 hover:bg-red-50 hover:text-red-500 transition-colors"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ============ 右侧：聊天区 ============ */}
      <div className="flex flex-1 flex-col">
        {/* 顶部标题栏 */}
        <div className="flex items-center justify-between border-b bg-white/80 backdrop-blur px-6 py-3">
          <div className="flex items-center gap-3">
            {!sidebarOpen && (
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setSidebarOpen(true)}
                className="h-8 w-8"
              >
                <ChevronRightIcon className="h-4 w-4" />
              </Button>
            )}
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-blue-500 to-indigo-600 shadow-md shadow-blue-200">
              <Bot className="h-5 w-5 text-white" />
            </div>
            <div>
              <h2 className="text-base font-bold text-slate-800">
                AI 智能助手
              </h2>
              <p className="text-xs text-slate-400">
                招标解析 · 方案生成 · 报价优化 · 知识检索 · 合规检测
              </p>
            </div>
          </div>
          {activeSessionId && (
            <span className="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-500">
              会话 #{activeSessionId}
            </span>
          )}
        </div>

        {/* 消息区 */}
        <div className="flex-1 overflow-y-auto px-4 md:px-6 py-4 space-y-4">
          <AnimatePresence initial={false}>
            {messages.length === 0 && (
              <motion.div
                key="welcome"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                className="flex flex-col items-center justify-center h-full gap-6"
              >
                <div className="flex h-20 w-20 items-center justify-center rounded-3xl bg-gradient-to-br from-blue-500 via-indigo-500 to-purple-600 shadow-xl shadow-blue-200/50">
                  <Sparkles className="h-10 w-10 text-white" />
                </div>
                <div className="text-center">
                  <h3 className="text-xl font-bold text-slate-700">
                    有什么可以帮你？
                  </h3>
                  <p className="mt-1.5 text-sm text-slate-400">
                    试试下面的快捷问题，或直接输入你的需求
                  </p>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 max-w-3xl w-full">
                  {QUICK_PROMPTS.map((p, i) => (
                    <motion.button
                      key={i}
                      whileHover={{ scale: 1.02 }}
                      whileTap={{ scale: 0.98 }}
                      onClick={() => sendMessage(p.text)}
                      className="rounded-xl border bg-white px-4 py-3.5 text-left text-sm text-slate-600 transition-colors hover:border-blue-300 hover:bg-blue-50/50 hover:shadow-sm"
                    >
                      <span className="mr-2">{p.emoji}</span>
                      {p.text}
                    </motion.button>
                  ))}
                </div>
              </motion.div>
            )}

            {messages.map((msg, i) => (
              <motion.div
                key={i}
                variants={bubbleVariants}
                initial="hidden"
                animate="visible"
                className={`flex gap-3 ${msg.role === "user" ? "justify-end" : ""}`}
              >
                {/* 头像 — 非用户消息左侧 */}
                {msg.role !== "user" && (
                  <div
                    className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${
                      msg.role === "tool"
                        ? "bg-amber-100 text-amber-600"
                        : "bg-gradient-to-br from-blue-500 to-indigo-600 text-white shadow-sm"
                    }`}
                  >
                    {msg.role === "tool" ? (
                      <Wrench className="h-4 w-4" />
                    ) : (
                      <Bot className="h-4 w-4" />
                    )}
                  </div>
                )}

                {/* 消息气泡 */}
                <div
                  className={`max-w-[75%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                    msg.role === "user"
                      ? "bg-gradient-to-br from-blue-600 to-blue-700 text-white shadow-md shadow-blue-200/40"
                      : msg.role === "tool"
                        ? "border border-amber-200 bg-amber-50 text-amber-800 italic"
                        : "border bg-white text-slate-700 shadow-sm"
                  }`}
                >
                  {msg.content.includes("⚠️") ? (
                    <div className="flex items-start gap-2">
                      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-red-500" />
                      <span>{msg.content}</span>
                    </div>
                  ) : msg.role === "assistant" ? (
                    <div className="prose prose-sm prose-slate max-w-none prose-headings:text-slate-800 prose-p:my-1.5 prose-li:my-0.5 prose-code:bg-slate-100 prose-code:px-1 prose-code:rounded prose-code:text-blue-700 prose-code:before:content-[''] prose-code:after:content-[''] prose-pre:bg-slate-900 prose-pre:text-slate-100 prose-table:text-xs">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {msg.content}
                      </ReactMarkdown>
                    </div>
                  ) : (
                    <span>{msg.content}</span>
                  )}
                </div>

                {/* 头像 — 用户消息右侧 */}
                {msg.role === "user" && (
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-slate-200">
                    <User className="h-4 w-4 text-slate-600" />
                  </div>
                )}
              </motion.div>
            ))}
          </AnimatePresence>

          {/* 加载指示器 */}
          {loading && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="flex gap-3"
            >
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-blue-500 to-indigo-600 shadow-sm">
                <Loader2 className="h-4 w-4 animate-spin text-white" />
              </div>
              <div className="flex items-center gap-1.5 rounded-2xl border bg-white px-4 py-3 text-sm text-slate-400 shadow-sm">
                <span className="inline-flex gap-0.5">
                  <span className="animate-bounce [animation-delay:0ms]">
                    ·
                  </span>
                  <span className="animate-bounce [animation-delay:150ms]">
                    ·
                  </span>
                  <span className="animate-bounce [animation-delay:300ms]">
                    ·
                  </span>
                </span>
                思考中
              </div>
            </motion.div>
          )}

          <div ref={endRef} />
        </div>

        {/* 输入区 */}
        <div className="border-t bg-white/80 backdrop-blur px-4 md:px-6 py-4">
          <div className="mx-auto flex max-w-3xl gap-3">
            <Input
              className="flex-1 rounded-xl"
              placeholder="输入问题，例如：帮我分析这份招标文件..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) =>
                e.key === "Enter" && !e.shiftKey && sendMessage(input)
              }
              disabled={loading}
            />
            <Button
              onClick={() => sendMessage(input)}
              disabled={loading || !input.trim()}
              className="gap-2 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 shadow-md shadow-blue-200/40"
            >
              <Send className="h-4 w-4" /> 发送
            </Button>
          </div>
          <p className="mt-2 text-center text-xs text-slate-300">
            AI 助手基于大模型驱动，回答仅供参考 · 对话自动保存
          </p>
        </div>
      </div>
    </div>
  );
}
