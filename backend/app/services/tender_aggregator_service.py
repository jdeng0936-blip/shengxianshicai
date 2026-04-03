"""
商机抓取与风控研判引擎 — 真实数据抓取 + LLM 匹配分析 + 转化为投标项目

核心流程：
  1. 从中国政府采购网 (ccgp.gov.cn) 抓取食材配送类招标公告
  2. 调用 CapabilityGraphService 获取企业能力画像
  3. LLM 分析公告需求 vs 企业能力，输出匹配评分
  4. 用户确认后一键转化为 BidProject
"""
import asyncio
import json
import logging
import random
import re
import uuid
from typing import Optional

import httpx
from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm_selector import LLMSelector
from app.core.prompt_manager import prompt_manager
from app.models.tender_notice import TenderNotice
from app.models.bid_project import BidProject
from app.services.tender_notice_service import TenderNoticeService
from app.services.capability_graph_service import CapabilityGraphService

logger = logging.getLogger(__name__)

# 食材配送关键词组
FOOD_KEYWORDS = [
    "食材配送", "食堂食材", "生鲜配送", "餐饮食材",
    "食品原料", "蔬菜配送", "肉类配送", "中央厨房食材",
]

# 客户类型推断规则
CUSTOMER_TYPE_RULES = [
    (["学校", "中学", "小学", "高中", "大学", "学院", "幼儿园"], "school"),
    (["医院", "卫生", "诊所", "健康"], "hospital"),
    (["政府", "机关", "管理局", "管委会", "行政", "事务"], "government"),
    (["企业", "公司", "集团", "工业", "科技", "园区"], "enterprise"),
    (["团餐", "餐饮", "厨房", "食堂管理"], "canteen"),
]

# 中国各省/直辖市/自治区的 CCGP 地区代码
REGION_CODES: dict[str, str] = {
    "全国": "",
    "北京": "11", "天津": "12", "河北": "13", "山西": "14", "内蒙古": "15",
    "辽宁": "21", "吉林": "22", "黑龙江": "23",
    "上海": "31", "江苏": "32", "浙江": "33", "安徽": "34", "福建": "35", "江西": "36",
    "山东": "37", "河南": "41", "湖北": "42", "湖南": "43",
    "广东": "44", "广西": "45", "海南": "46",
    "重庆": "50", "四川": "51", "贵州": "52", "云南": "53", "西藏": "54",
    "陕西": "61", "甘肃": "62", "青海": "63", "宁夏": "64", "新疆": "65",
}


def _extract_json(text: str) -> dict:
    """从 LLM 响应中提取 JSON"""
    match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    json_str = match.group(1).strip() if match else text.strip()
    return json.loads(json_str)


def _infer_customer_type(title: str, buyer: str) -> str:
    """根据标题和采购方名称推断客户类型"""
    combined = f"{title} {buyer}"
    for keywords, ctype in CUSTOMER_TYPE_RULES:
        if any(kw in combined for kw in keywords):
            return ctype
    return "enterprise"


def _extract_budget(text: str) -> Optional[float]:
    """从文本中提取预算金额（转换为元）"""
    # 匹配 "XXX万元" 或 "XXX 万" 格式
    m = re.search(r'(\d+(?:\.\d+)?)\s*万(?:元)?', text)
    if m:
        return float(m.group(1)) * 10000
    # 匹配纯数字金额 "XXX元"
    m = re.search(r'(\d{4,})(?:\.\d+)?\s*元', text)
    if m:
        return float(m.group(1))
    return None


# ========== 多平台配置（通过 Jina Reader API 读取，无需爬虫） ==========
CRAWL_PLATFORMS = [
    {
        "name": "中国政府采购网",
        "code": "ccgp",
        "jina_url": "https://www.ccgp.gov.cn/cggg/zygg/",
        "enabled": True,
    },
    {
        "name": "安徽省政府采购网",
        "code": "anhui_gp",
        "jina_url": "https://www.ccgp-anhui.gov.cn/cggg/",
        "enabled": True,
    },
    {
        "name": "合肥公共资源交易中心",
        "code": "hf_ggzy",
        "jina_url": "https://ggzy.hefei.gov.cn/gcjyxx/",
        "enabled": True,
    },
    {
        "name": "安徽公共资源交易集团",
        "code": "anhui_ggzy",
        "jina_url": "https://www.ahggzy.com/jyxx/",
        "enabled": True,
    },
]


class TenderAggregatorService:
    """商机抓取与分析引擎"""

    def __init__(self, session: AsyncSession):
        self.session = session

    # ========== AI 文本解析（粘贴公告） ==========

    async def parse_raw_text(
        self, raw_text: str, tenant_id: int, enterprise_id: int, user_id: int,
        source_url: Optional[str] = None,
    ) -> TenderNotice:
        """
        从用户粘贴的公告原文中 AI 提取结构化信息，创建商机记录。
        覆盖任意平台，无需爬虫。
        """
        if len(raw_text.strip()) < 30:
            raise ValueError("公告内容过短，请粘贴完整的招标公告")

        # AI 提取结构化信息（带自动容灾 fallback）
        prompt_text = prompt_manager.format_prompt(
            "tender_text_parse", "v1_extract",
            raw_text=raw_text[:6000],
        )
        _temperature = LLMSelector.get_temperature("tender_text_parse")
        _max_tokens = LLMSelector.get_max_tokens("tender_text_parse")

        async def _do_parse(cfg: dict) -> str:
            client = AsyncOpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"] or None)
            response = await client.chat.completions.create(
                model=cfg["model"],
                messages=[{"role": "user", "content": prompt_text}],
                temperature=_temperature,
                max_tokens=_max_tokens,
            )
            return response.choices[0].message.content or ""

        resp_text = await LLMSelector.call_with_fallback("tender_text_parse", _do_parse)
        try:
            parsed = _extract_json(resp_text)
        except (json.JSONDecodeError, ValueError):
            raise ValueError("AI 无法从该文本中提取有效信息，请确保粘贴的是完整招标公告")

        title = parsed.get("title") or raw_text[:100].strip()

        # 标题去重
        existing = await self.session.execute(
            select(TenderNotice).where(
                TenderNotice.tenant_id == tenant_id,
                TenderNotice.title == title,
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError(f"已存在相同标题的商机：{title}")

        notice = TenderNotice(
            tenant_id=tenant_id,
            enterprise_id=enterprise_id,
            created_by=user_id,
            status="new",
            source="paste",
            source_url=source_url,
            source_id=f"paste-{uuid.uuid4().hex[:12]}",
            title=title,
            buyer_name=parsed.get("buyer_name"),
            buyer_region=parsed.get("buyer_region"),
            customer_type=parsed.get("customer_type"),
            tender_type=parsed.get("tender_type"),
            budget_amount=parsed.get("budget_amount"),
            deadline=parsed.get("deadline"),
            publish_date=parsed.get("publish_date"),
            delivery_scope=parsed.get("delivery_scope"),
            content_summary=parsed.get("content_summary") or raw_text[:500],
        )
        self.session.add(notice)
        await self.session.commit()
        await self.session.refresh(notice)
        return notice

    # ========== 多平台轮询抓取 ==========

    async def crawl_all_platforms(
        self, tenant_id: int, enterprise_id: int, user_id: int,
        region: Optional[str] = None, keywords: Optional[str] = None,
    ) -> dict:
        """
        多平台轮询抓取。每个平台独立 try/except，一个失败不影响其他。
        返回 {platform: count} 汇总。
        """
        results = {}
        all_created = []

        for platform in CRAWL_PLATFORMS:
            if not platform["enabled"]:
                continue
            code = platform["code"]
            try:
                # 所有平台统一通过 Jina Reader API + AI 解析
                jina_url = platform.get("jina_url", "")
                raw = await self._fetch_via_jina_reader(jina_url, code, region)

                # 去重 + 入库
                created = await self._save_raw_notices(raw, code, tenant_id, enterprise_id, user_id)
                results[platform["name"]] = len(created)
                all_created.extend(created)
                logger.info(f"{platform['name']} 抓取到 {len(created)} 条新公告")
            except Exception as e:
                results[platform["name"]] = f"失败: {str(e)[:50]}"
                logger.warning(f"{platform['name']} 抓取失败: {e}")

        return {
            "platforms": results,
            "total_new": len(all_created),
        }

    async def _fetch_via_jina_reader(
        self, url: str, platform_code: str, region: Optional[str],
    ) -> list[dict]:
        """
        通过 Jina Reader API (r.jina.ai) 读取网页内容，再用 AI 提取公告列表。
        优势：免费、无反爬、返回干净 Markdown。
        """
        jina_url = f"https://r.jina.ai/{url}"
        headers = {"Accept": "text/plain", "X-Timeout": "25"}

        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(jina_url, headers=headers)

        content = resp.text
        if len(content) < 100 or "error" in content[:50].lower():
            logger.warning(f"Jina Reader 返回内容过短或错误: {content[:100]}")
            return []

        # AI 从 Markdown 提取食材配送相关公告（带自动容灾 fallback）
        region_filter = ""
        if region:
            region_filter = f"\n重要：只提取地域为「{region}」的公告，忽略其他地区的项目。"

        prompt = (
            f"从以下网页内容中提取与「食材配送」「食堂食材」「生鲜配送」「伙食配送」相关的招标公告。{region_filter}\n\n"
            f"网页内容：\n{content[:6000]}\n\n"
            f"请输出 JSON 数组，每条包含：\n"
            f'{{"title":"项目名称","buyer_name":"采购方","buyer_region":"地区",'
            f'"publish_date":"YYYY-MM-DD","source_url":"公告链接","content_summary":"摘要"}}\n\n'
            f"只提取与食材/食堂/配送/伙食相关的公告，忽略无关项目。"
            f"如果没有相关公告，返回空数组 []。只输出 JSON。"
        )

        async def _do_extract_page(cfg: dict) -> str:
            ai_client = AsyncOpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"] or None)
            response = await ai_client.chat.completions.create(
                model=cfg["model"],
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=2048,
            )
            return response.choices[0].message.content or "[]"

        resp_text = await LLMSelector.call_with_fallback("tender_text_parse", _do_extract_page)
        try:
            items = _extract_json(resp_text)
            if isinstance(items, dict):
                items = items.get("notices", items.get("data", [items]))
            if not isinstance(items, list):
                items = []
        except (json.JSONDecodeError, ValueError):
            items = []

        results = []
        for item in items:
            if not item.get("title"):
                continue
            title = item["title"]
            results.append({
                "source_id": f"{platform_code}-{uuid.uuid4().hex[:8]}",
                "title": title,
                "buyer_name": item.get("buyer_name"),
                "buyer_region": item.get("buyer_region") or region or "",
                "customer_type": _infer_customer_type(title, item.get("buyer_name", "")),
                "budget_amount": _extract_budget(item.get("content_summary", "")),
                "deadline": item.get("deadline"),
                "publish_date": item.get("publish_date"),
                "delivery_scope": item.get("delivery_scope"),
                "content_summary": item.get("content_summary", ""),
                "source_url": item.get("source_url"),
            })

        logger.info(f"Jina Reader + AI 从 {platform_code} 提取到 {len(results)} 条食材配送公告")
        return results

    async def _save_raw_notices(
        self, raw_data: list[dict], source: str,
        tenant_id: int, enterprise_id: int, user_id: int,
    ) -> list[TenderNotice]:
        """去重后批量入库"""
        created = []
        for item in raw_data:
            # source_id 去重
            if item.get("source_id"):
                existing = await self.session.execute(
                    select(TenderNotice).where(
                        TenderNotice.source_id == item["source_id"],
                        TenderNotice.tenant_id == tenant_id,
                    )
                )
                if existing.scalar_one_or_none():
                    continue

            # 标题去重
            title = item.get("title", "")
            if title:
                existing = await self.session.execute(
                    select(TenderNotice).where(
                        TenderNotice.tenant_id == tenant_id,
                        TenderNotice.title == title,
                    )
                )
                if existing.scalar_one_or_none():
                    continue

            notice = TenderNotice(
                tenant_id=tenant_id,
                enterprise_id=enterprise_id,
                created_by=user_id,
                status="new",
                source=source,
                **item,
            )
            self.session.add(notice)
            created.append(notice)

        if created:
            await self.session.commit()
            for n in created:
                await self.session.refresh(n)

        return created

    @staticmethod
    def get_available_platforms() -> list[dict]:
        """返回可用的抓取平台列表"""
        return [{"name": p["name"], "code": p["code"], "enabled": p["enabled"]} for p in CRAWL_PLATFORMS]

    async def fetch_notices(
        self, tenant_id: int, enterprise_id: int, user_id: int,
        region: Optional[str] = None, keywords: Optional[str] = None,
        budget_min: Optional[float] = None, budget_max: Optional[float] = None,
    ) -> list[TenderNotice]:
        """抓取商机并存入数据库（仅真实数据，无 Mock）"""
        svc = TenderNoticeService(self.session)

        # 从政府采购网真实抓取
        raw_data = await self._fetch_from_ccgp(region=region, keywords=keywords)
        source = "ccgp"
        logger.info(f"从政府采购网抓取到 {len(raw_data)} 条公告")

        created = []
        for item in raw_data:
            # 去重：检查 source_id
            if item.get("source_id"):
                existing = await self.session.execute(
                    select(TenderNotice).where(
                        TenderNotice.source_id == item["source_id"],
                        TenderNotice.tenant_id == tenant_id,
                    )
                )
                if existing.scalar_one_or_none():
                    continue

            # 预算范围筛选
            budget = item.get("budget_amount")
            if budget_min and budget and budget < budget_min:
                continue
            if budget_max and budget and budget > budget_max:
                continue

            notice = TenderNotice(
                tenant_id=tenant_id,
                enterprise_id=enterprise_id,
                created_by=user_id,
                status="new",
                source=source,
                **item,
            )
            self.session.add(notice)
            created.append(notice)

        if created:
            await self.session.commit()
            for n in created:
                await self.session.refresh(n)

        return created

    # ========== 真实数据抓取 ==========

    async def _fetch_from_ccgp(
        self,
        region: Optional[str] = None,
        keywords: Optional[str] = None,
        max_pages: int = 2,
    ) -> list[dict]:
        """从中国政府采购网 (ccgp.gov.cn) 抓取食材配送类招标公告

        搜索接口：http://search.ccgp.gov.cn/bxsearch
        合规保护：单次最多 2 页，请求间隔 1-3 秒随机延迟
        """
        # 构建搜索关键词
        search_kw = keywords if keywords else "食材配送"

        # 地区代码
        region_code = ""
        if region and region in REGION_CODES:
            region_code = REGION_CODES[region]

        results: list[dict] = []
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": "http://search.ccgp.gov.cn/",
        }

        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            for page in range(1, max_pages + 1):
                try:
                    params = {
                        "searchtype": "1",       # 1=公告搜索
                        "page_index": str(page),
                        "bidSort": "0",          # 按时间排序
                        "buyerName": "",
                        "projectId": "",
                        "pinMu": "0",
                        "bidType": "1",          # 1=招标公告
                        "dbselect": "bidx",
                        "kw": search_kw,
                        "start_time": "",
                        "end_time": "",
                        "timeType": "6",         # 近半年
                        "displayZone": region_code,
                        "zoneId": "",
                        "pppStatus": "0",
                        "agession": "",
                    }

                    resp = await client.get(
                        "http://search.ccgp.gov.cn/bxsearch",
                        params=params,
                        headers=headers,
                    )
                    resp.raise_for_status()

                    # 解析 HTML 提取公告列表
                    page_results = self._parse_ccgp_html(resp.text, region)
                    results.extend(page_results)

                    logger.info(f"CCGP 第 {page} 页抓取到 {len(page_results)} 条")

                    # 如果没有更多结果，提前退出
                    if len(page_results) < 10:
                        break

                    # 合规延迟：1-3 秒随机
                    if page < max_pages:
                        await asyncio.sleep(random.uniform(1.0, 3.0))

                except httpx.HTTPError as e:
                    logger.error(f"CCGP 第 {page} 页请求失败: {e}")
                    break

        if not results:
            raise ValueError("政府采购网未返回有效数据")

        return results

    def _parse_ccgp_html(self, html: str, region: Optional[str] = None) -> list[dict]:
        """解析政府采购网搜索结果 HTML

        搜索结果页的 HTML 结构：
        <ul class="vT-srch-result-list-bid">
          <li>
            <a href="公告详情链接">公告标题</a>
            <span>采购方 | 地区 | 日期 | 金额</span>
          </li>
        </ul>
        """
        results = []

        # 提取列表项 — 使用正则解析，避免引入 lxml/bs4 重依赖
        # 匹配 <li> 中的链接和文本
        pattern = re.compile(
            r'<li[^>]*>.*?'
            r'<a\s+href="([^"]+)"[^>]*>(.+?)</a>'  # 链接 + 标题
            r'(.*?)</li>',
            re.DOTALL
        )

        for match in pattern.finditer(html):
            source_url = match.group(1).strip()
            title = re.sub(r'<[^>]+>', '', match.group(2)).strip()
            detail_html = match.group(3)
            detail_text = re.sub(r'<[^>]+>', ' ', detail_html).strip()

            # 跳过明显不相关的
            if not title or len(title) < 5:
                continue

            # 提取采购方（通常在 span 标签中）
            buyer_match = re.search(r'采购人[：:]\s*(.+?)(?:\s|$|[|｜])', detail_text)
            buyer_name = buyer_match.group(1).strip() if buyer_match else ""

            # 提取日期
            date_match = re.search(r'(\d{4}[年/-]\d{1,2}[月/-]\d{1,2})', detail_text)
            publish_date = ""
            if date_match:
                d = date_match.group(1).replace("年", "-").replace("月", "-").replace("日", "")
                publish_date = d

            # 提取预算金额
            budget = _extract_budget(detail_text)

            # 推断客户类型
            customer_type = _infer_customer_type(title, buyer_name)

            # 生成唯一 source_id（基于 URL 哈希）
            source_id = f"ccgp-{hash(source_url) & 0xFFFFFFFF:08x}"

            results.append({
                "source_id": source_id,
                "source_url": source_url,
                "title": title,
                "buyer_name": buyer_name or None,
                "buyer_region": region or None,
                "customer_type": customer_type,
                "tender_type": "open",
                "budget_amount": budget,
                "deadline": None,  # 搜索结果通常不含截止日期
                "publish_date": publish_date or None,
                "delivery_scope": None,
                "content_summary": detail_text[:500] if detail_text else None,
            })

        return results

    # ========== AI 匹配分析 ==========

    async def analyze_notice(
        self, notice_id: int, tenant_id: int, enterprise_id: int,
    ) -> TenderNotice:
        """对单条商机执行 LLM 匹配分析"""
        notice = await self.session.execute(
            select(TenderNotice).where(
                TenderNotice.id == notice_id,
                TenderNotice.tenant_id == tenant_id,
            )
        )
        notice = notice.scalar_one_or_none()
        if not notice:
            raise ValueError("商机不存在")

        notice.status = "analyzing"
        notice.enterprise_id = enterprise_id
        await self.session.commit()
        await self.session.refresh(notice)

        # 构建企业能力画像
        cap_svc = CapabilityGraphService(self.session)
        graph = await cap_svc.build_graph(enterprise_id, tenant_id)
        graph_text = cap_svc.graph_to_text(graph)

        try:
            prompt_text = prompt_manager.format_prompt(
                "tender_match_analysis", "v1_capability_match",
                notice_title=notice.title,
                buyer_name=notice.buyer_name or "未知",
                customer_type=notice.customer_type or "未知",
                budget_amount=str(notice.budget_amount or "未知"),
                deadline=notice.deadline or "未知",
                delivery_scope=notice.delivery_scope or "未知",
                content_summary=notice.content_summary or "无详细信息",
                capability_graph=graph_text,
            )
            _match_temp = LLMSelector.get_temperature("tender_match_analysis")
            _match_max = LLMSelector.get_max_tokens("tender_match_analysis")

            async def _do_match(cfg: dict) -> str:
                client = AsyncOpenAI(
                    api_key=cfg["api_key"],
                    base_url=cfg["base_url"] or None,
                )
                response = await client.chat.completions.create(
                    model=cfg["model"],
                    messages=[{"role": "user", "content": prompt_text}],
                    temperature=_match_temp,
                    max_tokens=_match_max,
                )
                return response.choices[0].message.content or ""

            resp_text = await LLMSelector.call_with_fallback(
                "tender_match_analysis", _do_match
            )
            result = _extract_json(resp_text)

            notice.match_score = result.get("match_score")
            notice.match_level = result.get("match_level", "medium")
            notice.match_analysis = json.dumps(result, ensure_ascii=False)
            notice.capability_gaps = json.dumps(result.get("gaps", []), ensure_ascii=False)
            notice.recommendation = result.get("recommendation", "")

            # 根据分数设置状态
            score = notice.match_score or 0
            if score >= 70:
                notice.status = "recommended"
            elif notice.match_level == "risky":
                notice.status = "analyzed"
            else:
                notice.status = "analyzed"

        except Exception as e:
            # LLM 失败：优雅降级
            logger.error(f"LLM 匹配分析失败: {type(e).__name__}: {e}")
            notice.status = "analyzed"
            notice.recommendation = f"AI 分析暂时不可用（{type(e).__name__}），请人工评估此商机。"

        await self.session.commit()
        await self.session.refresh(notice)
        return notice

    async def batch_analyze(
        self, tenant_id: int, enterprise_id: int, user_id: int,
        notice_ids: Optional[list[int]] = None,
    ) -> list[TenderNotice]:
        """批量分析商机"""
        if notice_ids:
            notices = []
            for nid in notice_ids:
                n = await self.analyze_notice(nid, tenant_id, enterprise_id)
                notices.append(n)
            return notices

        # 分析所有 new 状态的
        result = await self.session.execute(
            select(TenderNotice).where(
                TenderNotice.tenant_id == tenant_id,
                TenderNotice.status == "new",
            )
        )
        new_notices = list(result.scalars().all())
        analyzed = []
        for n in new_notices:
            a = await self.analyze_notice(n.id, tenant_id, enterprise_id)
            analyzed.append(a)
        return analyzed

    async def convert_to_project(
        self, notice_id: int, tenant_id: int, enterprise_id: int, user_id: int,
    ) -> BidProject:
        """将商机转化为投标项目"""
        notice = await self.session.execute(
            select(TenderNotice).where(
                TenderNotice.id == notice_id,
                TenderNotice.tenant_id == tenant_id,
            )
        )
        notice = notice.scalar_one_or_none()
        if not notice:
            raise ValueError("商机不存在")
        if notice.status == "converted":
            raise ValueError("该商机已转化为投标项目")

        project = BidProject(
            project_name=notice.title,
            tender_org=notice.buyer_name,
            customer_type=notice.customer_type,
            tender_type=notice.tender_type,
            deadline=notice.deadline,
            budget_amount=notice.budget_amount,
            delivery_scope=notice.delivery_scope,
            enterprise_id=enterprise_id,
            status="draft",
            tenant_id=tenant_id,
            created_by=user_id,
        )
        self.session.add(project)
        await self.session.flush()

        notice.status = "converted"
        notice.converted_project_id = project.id
        await self.session.commit()
        await self.session.refresh(project)

        return project

    @staticmethod
    def get_available_regions() -> list[dict]:
        """返回可选的地区列表"""
        return [
            {"code": code, "name": name}
            for name, code in REGION_CODES.items()
        ]
