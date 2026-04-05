"""
围串标语义相似度检测器 — 三维度交叉检测

检测维度:
  1. 章节级 embedding 余弦相似度（vs 同租户历史标书）
  2. N-gram 文本指纹重复率（跨项目对比）
  3. 关键段落 MD5 哈希精确匹配

风险分级:
  danger:  embedding >= 0.85 或 ngram >= 0.70
  warning: embedding >= 0.70 或 ngram >= 0.50
  safe:    低于上述阈值

架构约束:
  - 所有 DB 查询强制绑定 tenant_id
  - embedding 调用通过 EmbeddingService（走 LLMSelector 路由）
  - 跨项目数据通过 Application 层逐步查询，严禁直接 SQL 联表
"""
import hashlib
import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bid_project import BidProject, BidChapter

logger = logging.getLogger("freshbid.similarity")

# ── 风险阈值 ─────────────────────────────────────────
EMBEDDING_DANGER = 0.85
EMBEDDING_WARNING = 0.70
NGRAM_DANGER = 0.70
NGRAM_WARNING = 0.50
# 对比的历史项目数上限
MAX_HISTORY_PROJECTS = 10


# ── 数据模型 ─────────────────────────────────────────

@dataclass
class SimilarityItem:
    """单条相似度检测项"""
    chapter_no: str
    chapter_title: str
    compared_project_id: int
    compared_project_name: str
    embedding_score: float = 0.0
    ngram_score: float = 0.0
    exact_paragraphs: list[str] = field(default_factory=list)
    risk_level: str = "safe"


@dataclass
class SimilarityReport:
    """完整相似度报告"""
    project_id: int
    generated_at: str = ""
    compared_count: int = 0
    max_similarity: float = 0.0
    danger_items: list[SimilarityItem] = field(default_factory=list)
    warning_items: list[SimilarityItem] = field(default_factory=list)
    safe_count: int = 0
    safe: bool = True


# ── 核心算法 ─────────────────────────────────────────

def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """余弦相似度计算"""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = sum(a * a for a in vec_a) ** 0.5
    norm_b = sum(b * b for b in vec_b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def ngram_fingerprint(text_a: str, text_b: str, n: int = 3) -> float:
    """N-gram 文本指纹重复率

    计算两段文本的 N-gram 集合 Jaccard 相似度。
    返回 0.0~1.0，值越高越相似。
    """
    if not text_a or not text_b:
        return 0.0
    # 移除空白后提取 N-gram
    clean_a = text_a.replace(" ", "").replace("\n", "")
    clean_b = text_b.replace(" ", "").replace("\n", "")
    if len(clean_a) < n or len(clean_b) < n:
        return 0.0

    grams_a = Counter(clean_a[i:i + n] for i in range(len(clean_a) - n + 1))
    grams_b = Counter(clean_b[i:i + n] for i in range(len(clean_b) - n + 1))

    # Jaccard 相似度 = 交集 / 并集
    intersection = sum((grams_a & grams_b).values())
    union = sum((grams_a | grams_b).values())
    return intersection / union if union > 0 else 0.0


def paragraph_hash_match(text_a: str, text_b: str, min_length: int = 20) -> list[str]:
    """段落级 MD5 精确匹配

    将文本按段落切分，对每段计算 MD5，返回完全重复的段落列表。
    仅检测长度 >= min_length 的段落（过短段落无意义）。
    注: 中文字符信息密度高，20 字符约等于英文 50 字符的内容量。
    """
    def _split_and_hash(text: str) -> dict[str, str]:
        result = {}
        for para in text.split("\n"):
            para = para.strip()
            if len(para) >= min_length:
                h = hashlib.md5(para.encode("utf-8")).hexdigest()
                result[h] = para
        return result

    hashes_a = _split_and_hash(text_a)
    hashes_b = _split_and_hash(text_b)
    common = set(hashes_a.keys()) & set(hashes_b.keys())
    return [hashes_a[h] for h in common]


def classify_risk(embedding_score: float, ngram_score: float, exact_count: int) -> str:
    """综合三维度判定风险级别"""
    if embedding_score >= EMBEDDING_DANGER or ngram_score >= NGRAM_DANGER or exact_count >= 3:
        return "danger"
    if embedding_score >= EMBEDDING_WARNING or ngram_score >= NGRAM_WARNING or exact_count >= 1:
        return "warning"
    return "safe"


# ── 检测服务 ─────────────────────────────────────────

class SimilarityDetector:
    """围串标语义相似度检测器"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def detect(
        self, project_id: int, tenant_id: int
    ) -> SimilarityReport:
        """执行全量相似度检测

        流程:
          1. 加载当前项目章节
          2. 加载同租户历史项目章节（最近 N 个，排除当前）
          3. 逐章节 × 逐历史项目 三维度对比
          4. 汇总风险报告
        """
        report = SimilarityReport(
            project_id=project_id,
            generated_at=datetime.now().isoformat(),
        )

        # 1. 加载当前项目章节
        current_chapters = await self._load_chapters(project_id, tenant_id)
        if not current_chapters:
            report.safe = True
            return report

        # 2. 加载历史项目（Application 层逐步查询，不联表）
        history_projects = await self._load_history_projects(
            project_id, tenant_id
        )
        report.compared_count = len(history_projects)
        if not history_projects:
            report.safe = True
            return report

        # 3. 对每个历史项目加载章节并对比
        max_sim = 0.0
        for hist_proj_id, hist_proj_name in history_projects:
            hist_chapters = await self._load_chapters(hist_proj_id, tenant_id)
            if not hist_chapters:
                continue

            items = await self._compare_project_chapters(
                current_chapters, hist_chapters,
                hist_proj_id, hist_proj_name,
            )
            for item in items:
                combined = max(item.embedding_score, item.ngram_score)
                max_sim = max(max_sim, combined)
                if item.risk_level == "danger":
                    report.danger_items.append(item)
                elif item.risk_level == "warning":
                    report.warning_items.append(item)
                else:
                    report.safe_count += 1

        report.max_similarity = round(max_sim, 4)
        report.safe = len(report.danger_items) == 0
        return report

    async def _load_chapters(
        self, project_id: int, tenant_id: int
    ) -> list[dict]:
        """加载项目章节（内容非空的）"""
        result = await self.session.execute(
            select(BidChapter).join(BidProject).where(
                BidChapter.project_id == project_id,
                BidProject.tenant_id == tenant_id,
                BidChapter.content.isnot(None),
                BidChapter.content != "",
            )
        )
        chapters = result.scalars().all()
        return [
            {
                "chapter_no": ch.chapter_no,
                "title": ch.title,
                "content": ch.content,
            }
            for ch in chapters
        ]

    async def _load_history_projects(
        self, exclude_project_id: int, tenant_id: int
    ) -> list[tuple[int, str]]:
        """加载同租户最近 N 个历史项目（排除当前）"""
        result = await self.session.execute(
            select(BidProject.id, BidProject.project_name).where(
                BidProject.tenant_id == tenant_id,
                BidProject.id != exclude_project_id,
                BidProject.status.in_(["generated", "completed", "submitted", "won"]),
            ).order_by(BidProject.id.desc()).limit(MAX_HISTORY_PROJECTS)
        )
        return [(row[0], row[1]) for row in result.fetchall()]

    async def _compare_project_chapters(
        self, current: list[dict], history: list[dict],
        hist_project_id: int, hist_project_name: str,
    ) -> list[SimilarityItem]:
        """对比当前项目 vs 一个历史项目的所有章节"""
        items = []

        # 按章节编号对齐（同编号章节对比）
        hist_by_no = {ch["chapter_no"]: ch for ch in history}

        for cur_ch in current:
            hist_ch = hist_by_no.get(cur_ch["chapter_no"])
            if not hist_ch:
                continue

            cur_text = cur_ch["content"]
            hist_text = hist_ch["content"]

            # 维度2: N-gram 指纹（纯计算，无外部依赖）
            ngram_score = ngram_fingerprint(cur_text, hist_text)

            # 维度3: 段落精确匹配
            exact_paras = paragraph_hash_match(cur_text, hist_text)

            # 维度1: embedding 余弦（降级容错：失败时置 0）
            try:
                emb_score = await self._embedding_compare(cur_text, hist_text)
            except Exception as e:
                logger.warning(f"[相似度检测] embedding 对比异常（降级为0）: {e}")
                emb_score = 0.0

            risk = classify_risk(emb_score, ngram_score, len(exact_paras))

            items.append(SimilarityItem(
                chapter_no=cur_ch["chapter_no"],
                chapter_title=cur_ch["title"],
                compared_project_id=hist_project_id,
                compared_project_name=hist_project_name,
                embedding_score=round(emb_score, 4),
                ngram_score=round(ngram_score, 4),
                exact_paragraphs=exact_paras[:5],  # 最多返回 5 段
                risk_level=risk,
            ))

        return items

    async def _embedding_compare(self, text_a: str, text_b: str) -> float:
        """维度1: embedding 余弦相似度（容错降级）"""
        try:
            from app.services.embedding_service import EmbeddingService
            emb_svc = EmbeddingService(self.session)

            # 截断到合理长度
            vec_a = await emb_svc.embed_text(text_a[:2000])
            vec_b = await emb_svc.embed_text(text_b[:2000])

            if vec_a and vec_b:
                return _cosine_similarity(vec_a, vec_b)
        except Exception as e:
            logger.warning(f"[相似度检测] embedding 对比失败（降级为0）: {e}")
        return 0.0
