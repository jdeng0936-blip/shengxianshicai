"use client";

import { useEffect, useRef, useCallback, useState } from "react";
import type { PipelineState, LayerState } from "@/components/business/ai-pipeline-progress";

// 后端 phase → 前端 layer id 映射
const PHASE_TO_LAYER: Record<string, string> = {
  data_load: "data_load",
  rag_retrieve: "rag_retrieve",
  prompt_build: "prompt_build",
  llm_generate: "llm_generate",
  critic_review: "critic_review",
  safety_replace: "safety_replace",
  persist: "persist",
};

// 有序层 ID 列表（用于判断前序层完成）
const LAYER_ORDER = [
  "data_load",
  "rag_retrieve",
  "prompt_build",
  "llm_generate",
  "critic_review",
  "safety_replace",
  "persist",
];

function buildWsUrl(projectId: string): string {
  const httpBase =
    process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
  const wsBase = httpBase.replace(/^http/, "ws");
  return `${wsBase}/ws/generation/${projectId}`;
}

function emptyState(): PipelineState {
  const layers: Record<string, LayerState> = {};
  for (const id of LAYER_ORDER) {
    layers[id] = "pending";
  }
  return {
    layers,
    chapters: [],
    totalChapters: 0,
    doneChapters: 0,
    totalWords: 0,
    elapsedSeconds: 0,
  };
}

/**
 * WebSocket 钩子：订阅生成管线实时进度
 *
 * 返回:
 *   state     — 当前 PipelineState（驱动 AIPipelineProgress 组件）
 *   connected — WS 是否已连接
 *   connect   — 手动触发连接
 *   disconnect — 手动断开
 */
export function useGenerationSocket(projectId: string) {
  const [state, setState] = useState<PipelineState>(emptyState);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const startTimeRef = useRef<number>(0);

  const disconnect = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setConnected(false);
  }, []);

  const connect = useCallback(() => {
    disconnect();
    setState(emptyState());
    startTimeRef.current = Date.now();

    const ws = new WebSocket(buildWsUrl(projectId));
    wsRef.current = ws;

    // 计时器：每秒更新 elapsedSeconds
    timerRef.current = setInterval(() => {
      setState((prev) => ({
        ...prev,
        elapsedSeconds: Math.round((Date.now() - startTimeRef.current) / 1000),
      }));
    }, 1000);

    ws.onopen = () => setConnected(true);

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        setState((prev) => applyEvent(prev, msg));
      } catch {
        // 忽略解析错误
      }
    };

    ws.onclose = () => {
      setConnected(false);
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };

    ws.onerror = () => {
      ws.close();
    };
  }, [projectId, disconnect]);

  // 组件卸载时清理
  useEffect(() => {
    return () => disconnect();
  }, [disconnect]);

  return { state, connected, connect, disconnect };
}

/**
 * 根据后端事件更新 PipelineState（纯函数）
 */
function applyEvent(prev: PipelineState, msg: any): PipelineState {
  switch (msg.type) {
    case "pipeline_start":
      return {
        ...emptyState(),
        totalChapters: msg.total_chapters,
        chapters: (msg.chapters || []).map((ch: any) => ({
          name: ch.chapter_no,
          layer: "",
          done: false,
        })),
      };

    case "chapter_start":
      return {
        ...prev,
        chapters: prev.chapters.map((ch) =>
          ch.name === msg.chapter_no
            ? { ...ch, layer: "data_load", done: false }
            : ch
        ),
      };

    case "phase": {
      const layerId = PHASE_TO_LAYER[msg.phase] || msg.phase;
      const layerIdx = LAYER_ORDER.indexOf(layerId);

      // 标记当前层为 running，前序层为 done
      const newLayers = { ...prev.layers };
      for (let i = 0; i < LAYER_ORDER.length; i++) {
        if (i < layerIdx) newLayers[LAYER_ORDER[i]] = "done";
        else if (i === layerIdx) newLayers[LAYER_ORDER[i]] = "running";
        // 后续保持不变
      }

      return {
        ...prev,
        layers: newLayers,
        chapters: prev.chapters.map((ch) =>
          ch.name === msg.chapter_no ? { ...ch, layer: layerId } : ch
        ),
      };
    }

    case "chapter_done": {
      const newLayers = { ...prev.layers };
      // 所有层标记 done（当前章节完成）
      for (const id of LAYER_ORDER) {
        newLayers[id] = "done";
      }
      const newDone = prev.doneChapters + 1;
      return {
        ...prev,
        layers: newLayers,
        doneChapters: newDone,
        totalWords: prev.totalWords + (msg.word_count || 0),
        chapters: prev.chapters.map((ch) =>
          ch.name === msg.chapter_no
            ? { ...ch, done: true, words: msg.word_count, layer: "" }
            : ch
        ),
      };
    }

    case "chapter_error":
      return {
        ...prev,
        layers: { ...prev.layers },
        chapters: prev.chapters.map((ch) =>
          ch.name === msg.chapter_no
            ? { ...ch, done: true, layer: "error" }
            : ch
        ),
      };

    case "pipeline_done":
      // 最终状态：所有层 done
      const finalLayers: Record<string, LayerState> = {};
      for (const id of LAYER_ORDER) {
        finalLayers[id] = "done";
      }
      return {
        ...prev,
        layers: finalLayers,
        doneChapters: msg.completed,
      };

    default:
      return prev;
  }
}
