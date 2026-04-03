"""
反 AI 检测服务 — 分析文本的 AI 生成痕迹

检测维度（L1 统计特征）:
  1. 词汇多样性（Type-Token Ratio） — AI 生成文本 TTR 偏低
  2. 句长方差（Burstiness） — AI 生成文本句长趋于均匀
  3. 重复短语密度 — AI 倾向重复使用相似句式
  4. 连接词密度 — AI 偏爱「此外」「同时」「因此」等衔接词
  5. 段落结构一致性 — AI 段落长度高度一致

输出:
  - 综合风险分 0~100（≥60 高风险被识别为 AI）
  - 各维度明细 + 修改建议

架构红线:
  - 纯统计分析，不调用 LLM（零成本、零延迟）
  - 不存储原文，仅输出分析报告
"""
import re
import logging
from dataclasses import dataclass, field
from collections import Counter

logger = logging.getLogger("freshbid")


# ── 数据结构 ──────────────────────────────────────────────

@dataclass
class DimensionScore:
    """单维度检测结果"""
    name: str
    score: float         # 0~100，越高越像 AI
    detail: str          # 具体数值描述
    suggestion: str      # 修改建议


@dataclass
class DetectionReport:
    """反 AI 检测报告"""
    overall_score: float = 0.0          # 综合风险分 0~100
    risk_level: str = "low"             # low / medium / high
    dimensions: list[DimensionScore] = field(default_factory=list)
    summary: str = ""


# ── 文本预处理 ────────────────────────────────────────────

def _split_sentences(text: str) -> list[str]:
    """按中文句号/感叹号/问号分句"""
    sentences = re.split(r'[。！？\n]+', text)
    return [s.strip() for s in sentences if len(s.strip()) >= 4]


def _split_paragraphs(text: str) -> list[str]:
    """按换行分段"""
    paras = re.split(r'\n\s*\n|\n', text)
    return [p.strip() for p in paras if len(p.strip()) >= 10]


def _tokenize(text: str) -> list[str]:
    """简单分词：按标点和空格切分，保留 2 字以上词"""
    tokens = re.split(r'[，。、；：！？\s\u201c\u201d\u2018\u2019（）【】《》—·/\\-]+', text)
    return [t for t in tokens if len(t) >= 2]


# ── 检测维度 ──────────────────────────────────────────────

def _check_vocabulary_diversity(tokens: list[str]) -> DimensionScore:
    """词汇多样性（Type-Token Ratio）
    人类写作 TTR 通常 0.6~0.8，AI 生成偏低 0.3~0.5
    """
    if len(tokens) < 10:
        return DimensionScore("词汇多样性", 0, "文本过短，跳过检测", "")

    unique = len(set(tokens))
    total = len(tokens)
    ttr = unique / total

    # TTR → 风险分映射
    if ttr >= 0.65:
        score = max(0, 30 - (ttr - 0.65) * 200)
    elif ttr >= 0.50:
        score = 30 + (0.65 - ttr) * 200
    else:
        score = min(100, 60 + (0.50 - ttr) * 400)

    detail = f"TTR={ttr:.2f}（唯一词 {unique} / 总词 {total}）"

    if score >= 60:
        suggestion = "词汇重复度偏高，建议用同义词替换高频词汇，增加表述多样性"
    elif score >= 30:
        suggestion = "词汇多样性尚可，可适度引入行业术语提升专业性"
    else:
        suggestion = ""

    return DimensionScore("词汇多样性", round(score, 1), detail, suggestion)


def _check_burstiness(sentences: list[str]) -> DimensionScore:
    """句长方差（Burstiness）
    人类写作句长变化大（方差高），AI 趋于均匀（方差低）
    """
    if len(sentences) < 5:
        return DimensionScore("句长波动性", 0, "句子数不足，跳过检测", "")

    lengths = [len(s) for s in sentences]
    mean = sum(lengths) / len(lengths)
    variance = sum((l - mean) ** 2 for l in lengths) / len(lengths)
    cv = (variance ** 0.5) / mean if mean > 0 else 0  # 变异系数

    # CV → 风险分映射（CV 越小越像 AI）
    if cv >= 0.6:
        score = max(0, 20 - (cv - 0.6) * 100)
    elif cv >= 0.35:
        score = 20 + (0.6 - cv) * 160
    else:
        score = min(100, 60 + (0.35 - cv) * 200)

    detail = f"变异系数={cv:.2f}（均长 {mean:.0f} 字，方差 {variance:.0f}）"

    if score >= 60:
        suggestion = "句子长度过于均匀，建议穿插长短句：用短句强调要点，用长句展开论述"
    elif score >= 30:
        suggestion = "句长节奏尚可，可适当增加几句简短有力的总结句"
    else:
        suggestion = ""

    return DimensionScore("句长波动性", round(score, 1), detail, suggestion)


def _check_repetitive_phrases(text: str) -> DimensionScore:
    """重复短语检测
    提取 4-gram，统计高频重复
    """
    chars = re.sub(r'\s+', '', text)
    if len(chars) < 50:
        return DimensionScore("短语重复度", 0, "文本过短，跳过检测", "")

    # 4-gram 统计
    ngram_size = 4
    ngrams = [chars[i:i + ngram_size] for i in range(len(chars) - ngram_size + 1)]
    counter = Counter(ngrams)

    # 高频重复（出现 3 次以上）
    repeated = {k: v for k, v in counter.items() if v >= 3}
    repeat_ratio = sum(repeated.values()) / len(ngrams) if ngrams else 0

    top_repeats = sorted(repeated.items(), key=lambda x: -x[1])[:5]
    top_str = "、".join(f"「{k}」×{v}" for k, v in top_repeats) if top_repeats else "无"

    # ratio → 风险分
    if repeat_ratio <= 0.05:
        score = max(0, repeat_ratio * 400)
    elif repeat_ratio <= 0.15:
        score = 20 + (repeat_ratio - 0.05) * 400
    else:
        score = min(100, 60 + (repeat_ratio - 0.15) * 300)

    detail = f"重复率={repeat_ratio:.1%}，高频: {top_str}"

    if score >= 60:
        suggestion = "存在大量重复句式，建议重写高频重复段落，变换表述方式"
    elif score >= 30:
        suggestion = "部分短语重复，可针对性替换"
    else:
        suggestion = ""

    return DimensionScore("短语重复度", round(score, 1), detail, suggestion)


# AI 高频衔接词
_AI_CONNECTORS = [
    "此外", "同时", "另外", "与此同时", "不仅如此",
    "因此", "综上所述", "总而言之", "值得注意的是",
    "具体而言", "在此基础上", "进一步", "需要指出的是",
    "一方面", "另一方面", "从而", "以确保", "旨在",
]


def _check_connector_density(text: str) -> DimensionScore:
    """连接词密度
    AI 文本高频使用程式化衔接词
    """
    if len(text) < 100:
        return DimensionScore("连接词密度", 0, "文本过短，跳过检测", "")

    total_chars = len(text)
    hits = []
    for conn in _AI_CONNECTORS:
        count = text.count(conn)
        if count > 0:
            hits.append((conn, count))

    total_hits = sum(c for _, c in hits)
    density = total_hits / (total_chars / 100)  # 每百字命中次数

    top_str = "、".join(f"「{k}」×{v}" for k, v in sorted(hits, key=lambda x: -x[1])[:5]) if hits else "无"

    # density → 风险分
    if density <= 0.5:
        score = max(0, density * 30)
    elif density <= 1.5:
        score = 15 + (density - 0.5) * 45
    else:
        score = min(100, 60 + (density - 1.5) * 40)

    detail = f"每百字 {density:.1f} 次，共 {total_hits} 次，高频: {top_str}"

    if score >= 60:
        suggestion = "衔接词使用过于程式化，建议删除冗余连接词，用逻辑关系自然过渡"
    elif score >= 30:
        suggestion = "连接词略多，可适当精简"
    else:
        suggestion = ""

    return DimensionScore("连接词密度", round(score, 1), detail, suggestion)


def _check_paragraph_uniformity(paragraphs: list[str]) -> DimensionScore:
    """段落结构一致性
    AI 段落长度高度一致，人类写作段落参差不齐
    """
    if len(paragraphs) < 3:
        return DimensionScore("段落均匀度", 0, "段落不足，跳过检测", "")

    lengths = [len(p) for p in paragraphs]
    mean = sum(lengths) / len(lengths)
    variance = sum((l - mean) ** 2 for l in lengths) / len(lengths)
    cv = (variance ** 0.5) / mean if mean > 0 else 0

    # CV 越小越像 AI
    if cv >= 0.5:
        score = max(0, 20 - (cv - 0.5) * 80)
    elif cv >= 0.3:
        score = 20 + (0.5 - cv) * 200
    else:
        score = min(100, 60 + (0.3 - cv) * 200)

    detail = f"段落变异系数={cv:.2f}（均长 {mean:.0f} 字，{len(paragraphs)} 段）"

    if score >= 60:
        suggestion = "段落长度过于整齐，建议合并短段落、拆分长段落，制造自然的层次感"
    elif score >= 30:
        suggestion = "段落结构基本自然，可微调"
    else:
        suggestion = ""

    return DimensionScore("段落均匀度", round(score, 1), detail, suggestion)


# ── L2: N-gram 基线对比 ───────────────────────────────────

# 人类投标文本高频 bigram 基线（从典型中标文件统计）
# 值为相对频率（占全部 bigram 的比例），AI 文本在这些 bigram 上分布会异常集中
_HUMAN_BIGRAM_BASELINE: dict[str, float] = {
    "公司": 0.018, "配送": 0.015, "食材": 0.014, "服务": 0.013,
    "管理": 0.012, "方案": 0.011, "质量": 0.010, "安全": 0.010,
    "人员": 0.009, "设备": 0.009, "保障": 0.008, "制度": 0.008,
    "客户": 0.007, "要求": 0.007, "标准": 0.007, "采购": 0.006,
    "冷链": 0.006, "检测": 0.006, "培训": 0.006, "流程": 0.005,
    "仓储": 0.005, "运输": 0.005, "温度": 0.005, "监控": 0.005,
    "供应": 0.004, "车辆": 0.004, "投标": 0.004, "能力": 0.004,
    "体系": 0.004, "措施": 0.004, "验收": 0.003, "资质": 0.003,
}


def _kl_divergence(p: dict[str, float], q: dict[str, float], epsilon: float = 1e-8) -> float:
    """计算 KL 散度 D_KL(P || Q)，衡量分布 P 偏离基线 Q 的程度"""
    all_keys = set(p.keys()) | set(q.keys())
    kl = 0.0
    for k in all_keys:
        pk = p.get(k, epsilon)
        qk = q.get(k, epsilon)
        if pk > epsilon:
            kl += pk * (pk / qk if qk > 0 else 1e6)
    # 归一化：取 log 形式的 KL 散度
    import math
    kl_log = 0.0
    for k in all_keys:
        pk = p.get(k, epsilon)
        qk = q.get(k, epsilon)
        if pk > epsilon:
            kl_log += pk * math.log(pk / max(qk, epsilon))
    return kl_log


def _check_ngram_divergence(text: str) -> DimensionScore:
    """L2 N-gram 基线对比
    计算文本 bigram 频率分布与人类基线的 KL 散度。
    AI 文本在高频术语上过度集中（散度高），人类文本分布更均匀。
    """
    chars = re.sub(r'[\s，。、；：！？\n]+', '', text)
    if len(chars) < 80:
        return DimensionScore("N-gram 基线偏离", 0, "文本过短，跳过检测", "")

    # 统计文本 bigram 频率
    bigrams = [chars[i:i + 2] for i in range(len(chars) - 1)]
    total = len(bigrams)
    counter = Counter(bigrams)
    text_freq = {k: v / total for k, v in counter.items()}

    # 只关注基线中的关键 bigram
    baseline_keys = set(_HUMAN_BIGRAM_BASELINE.keys())
    text_subset = {k: text_freq.get(k, 0.0) for k in baseline_keys}
    baseline_subset = _HUMAN_BIGRAM_BASELINE

    # 计算 KL 散度
    kl = _kl_divergence(text_subset, baseline_subset)

    # 计算集中度：top-5 bigram 占比
    sorted_freq = sorted(text_freq.values(), reverse=True)
    top5_ratio = sum(sorted_freq[:5]) / max(sum(sorted_freq), 1e-8) if sorted_freq else 0

    # KL + 集中度 → 风险分
    # KL 散度通常在 0~2 范围，越高越异常
    if kl <= 0.3:
        kl_score = max(0, kl * 60)
    elif kl <= 0.8:
        kl_score = 18 + (kl - 0.3) * 84
    else:
        kl_score = min(100, 60 + (kl - 0.8) * 80)

    # 集中度修正
    if top5_ratio > 0.15:
        kl_score = min(100, kl_score + (top5_ratio - 0.15) * 100)

    # 找偏离最大的 bigram
    deviations = []
    for k in baseline_keys:
        text_val = text_freq.get(k, 0)
        base_val = baseline_subset[k]
        if text_val > 0:
            ratio = text_val / base_val
            if ratio > 2.0 or ratio < 0.3:
                deviations.append((k, ratio))
    deviations.sort(key=lambda x: abs(x[1] - 1), reverse=True)
    top_devs = deviations[:3]
    dev_str = "、".join(
        f"「{k}」{'↑' if r > 1 else '↓'}{r:.1f}x" for k, r in top_devs
    ) if top_devs else "无显著偏离"

    detail = f"KL散度={kl:.3f}，Top5集中度={top5_ratio:.1%}，偏离: {dev_str}"

    if kl_score >= 60:
        suggestion = "用词分布偏离人类基线，建议增加口语化表述、减少术语堆砌，穿插具体案例和数字"
    elif kl_score >= 30:
        suggestion = "用词分布略有偏离，可适当增加细节描写"
    else:
        suggestion = ""

    return DimensionScore("N-gram 基线偏离", round(kl_score, 1), detail, suggestion)


# ── 主入口 ────────────────────────────────────────────────

# 各维度权重（L1 五维 + L2 一维）
_WEIGHTS = {
    "词汇多样性": 0.20,
    "句长波动性": 0.15,
    "短语重复度": 0.15,
    "连接词密度": 0.15,
    "段落均匀度": 0.10,
    "N-gram 基线偏离": 0.25,
}


def detect_ai_text(text: str) -> DetectionReport:
    """分析文本的 AI 生成痕迹

    Args:
        text: 待检测文本

    Returns:
        DetectionReport 含综合风险分、各维度明细和修改建议
    """
    if not text or len(text) < 50:
        return DetectionReport(
            overall_score=0,
            risk_level="low",
            summary="文本过短，无法有效检测",
        )

    sentences = _split_sentences(text)
    paragraphs = _split_paragraphs(text)
    tokens = _tokenize(text)

    dimensions = [
        _check_vocabulary_diversity(tokens),
        _check_burstiness(sentences),
        _check_repetitive_phrases(text),
        _check_connector_density(text),
        _check_paragraph_uniformity(paragraphs),
        _check_ngram_divergence(text),
    ]

    # 加权综合分
    overall = sum(
        d.score * _WEIGHTS.get(d.name, 0.2)
        for d in dimensions
    )
    overall = round(min(100, max(0, overall)), 1)

    if overall >= 60:
        risk_level = "high"
        summary = f"AI 痕迹风险较高（{overall}分），建议重点修改标记维度后再提交"
    elif overall >= 35:
        risk_level = "medium"
        summary = f"存在一定 AI 痕迹（{overall}分），建议针对性润色"
    else:
        risk_level = "low"
        summary = f"AI 痕迹风险较低（{overall}分），文本自然度良好"

    return DetectionReport(
        overall_score=overall,
        risk_level=risk_level,
        dimensions=dimensions,
        summary=summary,
    )
