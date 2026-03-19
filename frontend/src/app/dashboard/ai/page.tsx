"use client";

import { useState, useRef, useEffect } from "react";
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
  RotateCcw,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { motion, AnimatePresence } from "framer-motion";

/** API 基础地址 — 统一使用 api.ts 的配置 */
const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

/** 快捷提示 */
const QUICK_PROMPTS = [
  { emoji: "🔩", text: "IV 类围岩拱形断面 5×4m，帮我算支护参数" },
  { emoji: "💨", text: "高瓦斯矿井掘进面风量怎么计算？" },
  { emoji: "⏱️", text: "钻爆法循环作业时间怎么排？" },
  { emoji: "🛡️", text: "帮我推荐掘进工作面安全措施" },
  { emoji: "📏", text: "锚索预紧力怎么计算？" },
  { emoji: "📋", text: "断面合规校验需要哪些参数？" },
];

interface Message {
  role: "user" | "assistant" | "tool";
  content: string;
  toolName?: string;
}

/** 消息气泡动画配置 */
const bubbleVariants = {
  hidden: { opacity: 0, y: 12, scale: 0.95 },
  visible: { opacity: 1, y: 0, scale: 1, transition: { duration: 0.25, ease: "easeOut" as const } },
};

export default function AIChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [industryType, setIndustryType] = useState("coal_excavation");
  const [industries, setIndustries] = useState<{key: string; label: string}[]>([]);
  const endRef = useRef<HTMLDivElement>(null);

  // 加载行业列表
  useEffect(() => {
    const token = localStorage.getItem("access_token");
    fetch(`${API_BASE}/ai/industries`, {
      headers: { Authorization: `Bearer ${token || ""}` },
    })
      .then((r) => r.json())
      .then((d) => {
        if (d.data) setIndustries(d.data);
      })
      .catch(() => {
        // 接口不可用时使用默认
        setIndustries([
          { key: "coal_excavation", label: "煤矿掘进工程" },
          { key: "municipal_road", label: "市政道路工程" },
        ]);
      });
  }, []);

  // 自动滚动到底部
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  /** 清空对话 */
  const clearChat = () => {
    setMessages([]);
    setInput("");
  };

  /** 发送消息（SSE 流式） */
  const sendMessage = async (text: string) => {
    if (!text.trim() || loading) return;

    const userMsg: Message = { role: "user", content: text };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    // 构建历史（最近 10 条）
    const history = messages.slice(-10).map((m) => ({
      role: m.role === "tool" ? "assistant" : m.role,
      content: m.content,
    }));

    try {
      const token =
        typeof window !== "undefined"
          ? localStorage.getItem("access_token")
          : "";
      const res = await fetch(`${API_BASE}/ai/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token || ""}`,
        },
        body: JSON.stringify({
          message: text,
          history,
          stream: true,
          industry_type: industryType,
        }),
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);

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
              // 显示工具调用
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
              // 工具完成
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
              // 文本流
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
            // 非 JSON，当做纯文本
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
    <div className="flex h-[calc(100vh-3.5rem)] flex-col bg-slate-50/60">
      {/* 顶部标题栏 */}
      <div className="flex items-center justify-between border-b bg-white/80 backdrop-blur px-6 py-3">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-blue-500 to-indigo-600 shadow-md shadow-blue-200">
            <Bot className="h-5 w-5 text-white" />
          </div>
          <div>
            <h2 className="text-base font-bold text-slate-800">AI 智能助手</h2>
            <p className="text-xs text-slate-400">
              支护计算 · 通风校核 · 循环排程 · 锚索分析 · 合规检测
            </p>
          </div>
        </div>
        {messages.length > 0 && (
          <Button
            variant="ghost"
            size="sm"
            onClick={clearChat}
            className="gap-1.5 text-slate-400 hover:text-slate-600"
          >
            <RotateCcw className="h-3.5 w-3.5" /> 清空
          </Button>
        )}
        {/* 行业选择下拉框 */}
        <select
          value={industryType}
          onChange={(e) => setIndustryType(e.target.value)}
          className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-600 shadow-sm transition hover:border-blue-300 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200"
        >
          {industries.map((ind) => (
            <option key={ind.key} value={ind.key}>
              {ind.label}
            </option>
          ))}
        </select>
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
                  /* 助手回复 → Markdown 渲染 */
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
                <span className="animate-bounce [animation-delay:0ms]">·</span>
                <span className="animate-bounce [animation-delay:150ms]">·</span>
                <span className="animate-bounce [animation-delay:300ms]">·</span>
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
            placeholder="输入问题，例如：帮我计算通风量..."
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
          AI 助手基于 Gemini 驱动，回答仅供参考，关键参数请以专业工程师审核为准
        </p>
      </div>
    </div>
  );
}
