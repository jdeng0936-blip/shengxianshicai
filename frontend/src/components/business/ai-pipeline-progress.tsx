"use client";

import { motion, AnimatePresence } from "framer-motion";
import { CheckCircle2, Circle, Loader2, AlertCircle, Zap } from "lucide-react";

// ============================
// 七层流水线定义
// ============================
export interface PipelineLayer {
  id: string;
  name: string;
  desc: string;
  icon: string;
  color: string; // Tailwind 颜色
}

export const PIPELINE_LAYERS: PipelineLayer[] = [
  {
    id: "data_load",
    name: "项目数据加载",
    desc: "加载项目信息、企业资质、招标要求与评分标准",
    icon: "📋",
    color: "blue",
  },
  {
    id: "rag_retrieve",
    name: "RAG 知识检索",
    desc: "向量相似度检索法规条款、历史案例与模板片段",
    icon: "🔍",
    color: "violet",
  },
  {
    id: "prompt_build",
    name: "Prompt 策略构建",
    desc: "评分驱动模板选择、变量注入与专项要求拼装",
    icon: "🧩",
    color: "cyan",
  },
  {
    id: "llm_generate",
    name: "AI 草稿生成",
    desc: "调用大模型生成章节初稿，脱敏处理后还原",
    icon: "✍️",
    color: "teal",
  },
  {
    id: "critic_review",
    name: "Critic 质量审查",
    desc: "五项评分自评，低分项触发定向重写修复",
    icon: "🔬",
    color: "green",
  },
  {
    id: "safety_replace",
    name: "安全红线校验",
    desc: "高风险字段后置替换，严禁 LLM 编造数据",
    icon: "🛡️",
    color: "amber",
  },
  {
    id: "persist",
    name: "持久化存储",
    desc: "写入数据库、更新章节状态与来源标签",
    icon: "💾",
    color: "rose",
  },
];

// ============================
// 章节进度类型
// ============================
export interface ChapterStatus {
  name: string;
  layer: string;   // 当前所在流水线层 id
  done: boolean;
  words?: number;
}

// ============================
// 流水线状态类型
// ============================
export type LayerState = "pending" | "running" | "done" | "error";

export interface PipelineState {
  layers: Record<string, LayerState>;     // 每层全局状态
  chapters: ChapterStatus[];              // 各章节进度
  totalChapters: number;
  doneChapters: number;
  totalWords: number;
  elapsedSeconds: number;
}

// ============================
// 颜色映射工具
// ============================
const COLOR_MAP: Record<string, { bg: string; border: string; text: string; glow: string }> = {
  blue:   { bg: "bg-blue-500",   border: "border-blue-400",  text: "text-blue-400",  glow: "shadow-blue-500/30"  },
  violet: { bg: "bg-violet-500", border: "border-violet-400", text: "text-violet-400", glow: "shadow-violet-500/30" },
  cyan:   { bg: "bg-cyan-500",   border: "border-cyan-400",  text: "text-cyan-400",  glow: "shadow-cyan-500/30"  },
  teal:   { bg: "bg-teal-500",   border: "border-teal-400",  text: "text-teal-400",  glow: "shadow-teal-500/30"  },
  green:  { bg: "bg-green-500",  border: "border-green-400", text: "text-green-400", glow: "shadow-green-500/30" },
  amber:  { bg: "bg-amber-500",  border: "border-amber-400", text: "text-amber-400", glow: "shadow-amber-500/30" },
  rose:   { bg: "bg-rose-500",   border: "border-rose-400",  text: "text-rose-400",  glow: "shadow-rose-500/30"  },
};

// ============================
// 单层状态图标
// ============================
function LayerIcon({ state, color }: { state: LayerState; color: string }) {
  const c = COLOR_MAP[color] || COLOR_MAP.blue;
  if (state === "done") return (
    <motion.div initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ type: "spring" }}>
      <CheckCircle2 className={`h-5 w-5 ${c.text}`} />
    </motion.div>
  );
  if (state === "running") return (
    <Loader2 className={`h-5 w-5 ${c.text} animate-spin`} />
  );
  if (state === "error") return <AlertCircle className="h-5 w-5 text-red-400" />;
  return <Circle className="h-5 w-5 text-slate-600" />;
}

// ============================
// 主组件
// ============================
export default function AIPipelineProgress({
  state,
}: {
  state: PipelineState;
}) {
  const progress = state.totalChapters > 0
    ? Math.round((state.doneChapters / state.totalChapters) * 100)
    : 0;

  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900/80 backdrop-blur-sm p-6 space-y-6">
      {/* 顶部统计 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Zap className="h-5 w-5 text-amber-400 animate-pulse" />
          <span className="text-sm font-semibold text-white">AI 七层流水线 · 生成中</span>
        </div>
        <div className="flex items-center gap-4 text-sm text-slate-400">
          <span>
            <span className="text-white font-bold">{state.doneChapters}</span>
            <span>/{state.totalChapters} 章节</span>
          </span>
          <span>
            <span className="text-white font-bold">{(state.totalWords / 1000).toFixed(1)}k</span>
            <span> 字</span>
          </span>
          <span>
            <span className="text-white font-bold">{state.elapsedSeconds}s</span>
          </span>
        </div>
      </div>

      {/* 总体进度条 */}
      <div className="space-y-1.5">
        <div className="h-2 rounded-full bg-slate-800 overflow-hidden">
          <motion.div
            className="h-full rounded-full bg-gradient-to-r from-blue-500 via-violet-500 to-rose-500"
            initial={{ width: 0 }}
            animate={{ width: `${progress}%` }}
            transition={{ duration: 0.5, ease: "easeOut" }}
          />
        </div>
        <div className="flex justify-between text-xs text-slate-500">
          <span>数据加载</span>
          <span className="text-slate-400 font-medium">{progress}%</span>
          <span>持久化</span>
        </div>
      </div>

      {/* 七层流水线列表 */}
      <div className="space-y-2">
        {PIPELINE_LAYERS.map((layer, idx) => {
          const layerState = state.layers[layer.id] || "pending";
          const c = COLOR_MAP[layer.color] || COLOR_MAP.blue;
          const isRunning = layerState === "running";
          const isDone = layerState === "done";

          return (
            <motion.div
              key={layer.id}
              initial={{ opacity: 0, x: -12 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: idx * 0.06 }}
              className={`
                flex items-start gap-3 rounded-xl border p-3 transition-all duration-300
                ${isRunning
                  ? `border-${layer.color}-500/50 bg-${layer.color}-500/10 shadow-lg ${c.glow}`
                  : isDone
                  ? "border-slate-700 bg-slate-800/40"
                  : "border-slate-800/50 bg-slate-900/30"
                }
              `}
            >
              {/* 步骤序号 */}
              <div className={`
                flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-bold
                ${isDone ? `${c.bg} text-white` : isRunning ? `border-2 ${c.border} ${c.text}` : "border border-slate-700 text-slate-600"}
              `}>
                {isDone ? "✓" : idx + 1}
              </div>

              {/* 内容 */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-base">{layer.icon}</span>
                  <span className={`text-sm font-medium ${isDone ? "text-slate-300" : isRunning ? "text-white" : "text-slate-500"}`}>
                    {layer.name}
                  </span>
                  {isRunning && (
                    <motion.span
                      animate={{ opacity: [0.4, 1, 0.4] }}
                      transition={{ duration: 1.2, repeat: Infinity }}
                      className={`text-xs ${c.text} font-medium`}
                    >
                      处理中...
                    </motion.span>
                  )}
                  {isDone && (
                    <span className="text-xs text-slate-500">完成</span>
                  )}
                </div>
                <p className="mt-0.5 text-xs text-slate-500 truncate">{layer.desc}</p>
              </div>

              {/* 状态图标 */}
              <div className="shrink-0">
                <LayerIcon state={layerState} color={layer.color} />
              </div>
            </motion.div>
          );
        })}
      </div>

      {/* 章节进度气泡 */}
      {state.chapters.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs text-slate-500 font-medium">章节生成进度</p>
          <div className="flex flex-wrap gap-1.5">
            <AnimatePresence>
              {state.chapters.map((ch, i) => (
                <motion.div
                  key={ch.name}
                  initial={{ scale: 0, opacity: 0 }}
                  animate={{ scale: 1, opacity: 1 }}
                  transition={{ delay: i * 0.03, type: "spring" }}
                  className={`
                    rounded-md px-2 py-0.5 text-xs font-medium border
                    ${ch.done
                      ? "bg-emerald-900/40 border-emerald-700/50 text-emerald-300"
                      : ch.layer
                      ? "bg-blue-900/40 border-blue-700/50 text-blue-300 animate-pulse"
                      : "bg-slate-800/60 border-slate-700/50 text-slate-500"
                    }
                  `}
                >
                  {ch.done ? "✓" : ch.layer ? "⟳" : "○"} {ch.name}
                  {ch.done && ch.words && (
                    <span className="ml-1 text-emerald-500">{Math.round(ch.words / 100) / 10}k</span>
                  )}
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        </div>
      )}
    </div>
  );
}
