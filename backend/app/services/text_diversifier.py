"""
文本差异化引擎 — 降低跨项目文本相似度，防围串标检测

三层策略:
  L1 词汇层: 投标文书领域同义词替换（纯规则，毫秒级）
  L2 句法层: 主被动转换、从句调序（LLM 辅助）
  L3 段落层: 论述逻辑重组（LLM 驱动，重度模式）

架构约束:
  - LLM 调用通过 LLMSelector.call_with_fallback 走四级容灾
  - 占位符（{{xxx}} / 【请填写xxx】）和数字不被替换
  - 差异化结果可量化（返回变更统计）
"""
import logging
import random
import re
from dataclasses import dataclass, field
from typing import Optional

from openai import AsyncOpenAI

from app.core.llm_selector import LLMSelector

logger = logging.getLogger("freshbid.diversifier")

# ── 投标文书领域同义词库 ──────────────────────────────

_SYNONYM_MAP: dict[str, list[str]] = {
    # 主语称谓
    "我公司": ["我方", "本公司", "投标人", "我单位"],
    "我方": ["我公司", "本公司", "投标人", "本单位"],
    "本公司": ["我方", "我公司", "投标人", "我单位"],
    # 动词 — 拥有/具备
    "拥有": ["配备", "具备", "持有", "装备"],
    "具备": ["拥有", "配备", "持有", "具有"],
    "配备": ["拥有", "具备", "装备", "配置"],
    # 动词 — 保证/确保
    "确保": ["保证", "保障", "务必做到", "切实保证"],
    "保证": ["确保", "保障", "承诺", "担保"],
    "保障": ["确保", "保证", "维护", "守护"],
    # 名词 — 方案/计划
    "方案": ["措施", "计划", "策略", "规划"],
    "措施": ["方案", "办法", "手段", "对策"],
    "计划": ["方案", "规划", "安排", "部署"],
    # 形容词 — 严格/规范
    "严格": ["严密", "规范", "从严", "严谨"],
    "完善": ["健全", "完备", "周全", "齐全"],
    "先进": ["领先", "前沿", "一流", "卓越"],
    "专业": ["精湛", "专项", "资深", "精通"],
    # 行业术语 — 配送
    "配送": ["运送", "供应", "递送", "派送"],
    "运输": ["运送", "输送", "转运", "承运"],
    "供应": ["供给", "提供", "配送", "保供"],
    # 行业术语 — 冷链
    "冷链": ["低温物流", "全程控温", "冷藏运输"],
    "温控": ["控温", "温度管理", "恒温"],
    "冷藏": ["低温保存", "冷链储存", "冷库保鲜"],
    # 行业术语 — 食品安全
    "食品安全": ["食安", "食品质量安全", "膳食安全"],
    "质量": ["品质", "质量水准", "品质标准"],
    "检测": ["检验", "检查", "监测", "化验"],
    "合格": ["达标", "符合标准", "合乎要求"],
    # 连接词/副词
    "同时": ["与此同时", "此外", "并且"],
    "此外": ["另外", "除此之外", "同时"],
    "因此": ["故而", "所以", "鉴于此"],
    "根据": ["依据", "按照", "遵照", "依照"],
    "为了": ["旨在", "以便", "目的在于"],
    # 动词 — 建立/实施
    "建立": ["构建", "搭建", "创建", "设立"],
    "实施": ["执行", "推行", "落实", "开展"],
    "管理": ["管控", "运营", "治理", "把控"],
    "提供": ["供应", "给予", "出具", "呈交"],
    "覆盖": ["涵盖", "辐射", "触达", "延伸至"],
    "满足": ["达到", "符合", "胜任", "契合"],
}

# 保护模式：匹配占位符和数字表达式，这些不参与替换
_PROTECTED_PATTERN = re.compile(
    r"\{\{[^}]+\}\}"           # {{占位符}}
    r"|【请填写[^】]+】"        # 【请填写xxx】
    r"|\d+[\.\d]*\s*[辆台㎡平方米人名位万元%]"  # 数字+单位
    r"|[A-Z]{1,5}\d{6,}"       # 资质编号
)


# ── 数据模型 ─────────────────────────────────────────

@dataclass
class DiversifyChange:
    """单个差异化变更记录"""
    original: str
    replacement: str
    layer: str   # "L1" / "L2" / "L3"
    position: int = 0


@dataclass
class DiversifyResult:
    """差异化处理结果"""
    original_text: str
    diversified_text: str
    changes: list[DiversifyChange] = field(default_factory=list)
    l1_count: int = 0
    l2_applied: bool = False
    ngram_reduction: float = 0.0  # N-gram 重复率下降幅度


# ── L1 词汇层：同义替换 ─────────────────────────────

def _extract_protected_regions(text: str) -> list[tuple[int, int]]:
    """提取所有受保护区域的 (start, end) 范围"""
    return [(m.start(), m.end()) for m in _PROTECTED_PATTERN.finditer(text)]


def _is_protected(pos: int, length: int, regions: list[tuple[int, int]]) -> bool:
    """检查某个位置是否在受保护区域内"""
    end = pos + length
    for rs, re_ in regions:
        if pos < re_ and end > rs:
            return True
    return False


def diversify_l1(text: str, replace_ratio: float = 0.5) -> tuple[str, list[DiversifyChange]]:
    """L1 词汇层差异化 — 纯规则同义替换

    Args:
        text: 原始文本
        replace_ratio: 替换概率（0~1），控制差异化强度

    Returns:
        (替换后文本, 变更记录列表)
    """
    if not text:
        return text, []

    protected = _extract_protected_regions(text)
    changes: list[DiversifyChange] = []
    result = text

    # 按关键词长度降序排列，避免短词误替换长词的一部分
    sorted_words = sorted(_SYNONYM_MAP.keys(), key=len, reverse=True)

    for word in sorted_words:
        if word not in result:
            continue
        synonyms = _SYNONYM_MAP[word]
        # 查找所有匹配位置
        start = 0
        while True:
            idx = result.find(word, start)
            if idx == -1:
                break
            if _is_protected(idx, len(word), protected):
                start = idx + len(word)
                continue
            if random.random() < replace_ratio:
                replacement = random.choice(synonyms)
                changes.append(DiversifyChange(
                    original=word,
                    replacement=replacement,
                    layer="L1",
                    position=idx,
                ))
                result = result[:idx] + replacement + result[idx + len(word):]
                # 更新保护区域偏移
                offset = len(replacement) - len(word)
                protected = [(s + offset if s > idx else s, e + offset if e > idx else e) for s, e in protected]
                start = idx + len(replacement)
            else:
                start = idx + len(word)

    return result, changes


# ── L2 句法层：LLM 辅助句式重组 ──────────────────────

_L2_SYSTEM = """你是一位资深的投标文件润色专家。请对以下投标文件段落进行句式差异化改写：

改写规则：
1. 保持所有事实数据（数字、编号、名称）完全不变
2. 变换句式结构：主动变被动、长句拆短、短句合并
3. 调整段内论述顺序，但不改变核心含义
4. 保持投标文件的专业性和规范性
5. 占位符（{{xxx}}、【请填写xxx】）原样保留
6. 不要添加任何解释，直接输出改写后的文本"""


async def diversify_l2(text: str) -> tuple[str, bool]:
    """L2 句法层差异化 — LLM 辅助句式重组

    Returns:
        (改写后文本, 是否成功应用)
    """
    if not text or len(text) < 100:
        return text, False

    temperature = 0.6  # 较高温度增加多样性
    try:
        max_tokens = LLMSelector.get_max_tokens("bid_section_generate")
    except Exception:
        max_tokens = 8192

    async def _do_call(cfg: dict) -> str:
        client = AsyncOpenAI(
            api_key=cfg["api_key"],
            base_url=cfg["base_url"] or None,
        )
        resp = await client.chat.completions.create(
            model=cfg["model"],
            temperature=temperature,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": _L2_SYSTEM},
                {"role": "user", "content": text},
            ],
        )
        return resp.choices[0].message.content or text

    try:
        result = await LLMSelector.call_with_fallback("bid_section_generate", _do_call)
        if result and len(result) > len(text) * 0.5:
            return result, True
        return text, False
    except Exception as e:
        logger.warning(f"[差异化L2] LLM 句式重组失败（保留原文）: {e}")
        return text, False


# ── 主入口 ───────────────────────────────────────────

async def diversify(
    text: str,
    intensity: str = "medium",
) -> DiversifyResult:
    """全层级差异化处理

    Args:
        text: 原始投标文本
        intensity:
          "light"  → 仅 L1（同义替换 30%）
          "medium" → L1(50%) + L2（句式重组）
          "heavy"  → L1(70%) + L2（句式重组，高温度）
    """
    result = DiversifyResult(original_text=text, diversified_text=text)

    if not text:
        return result

    # L1 词汇层
    ratio_map = {"light": 0.3, "medium": 0.5, "heavy": 0.7}
    replace_ratio = ratio_map.get(intensity, 0.5)

    l1_text, l1_changes = diversify_l1(text, replace_ratio)
    result.diversified_text = l1_text
    result.changes.extend(l1_changes)
    result.l1_count = len(l1_changes)

    # L2 句法层（medium / heavy 模式）
    if intensity in ("medium", "heavy"):
        l2_text, l2_ok = await diversify_l2(l1_text)
        if l2_ok:
            result.diversified_text = l2_text
            result.l2_applied = True

    # 计算 N-gram 降幅
    from app.services.similarity_detector import ngram_fingerprint
    original_self_sim = 1.0
    new_sim = ngram_fingerprint(text, result.diversified_text)
    result.ngram_reduction = round(original_self_sim - new_sim, 4)

    return result
