"""
AI 智能路由引擎 — LLM Tool Calling 驱动的意图识别与引擎调度

核心设计：
  1. 定义 8 个 Tool（支护/通风/循环计算 + 规则匹配 + 标准库语义检索
     + 安全建议 + 设备材料匹配 + 知识库摘要）
  2. LLM 解析用户自然语言 → 决定调用哪个工具 + 提取参数
  3. 执行工具 → 将结果回传 LLM → 生成中文解读
  4. 支持 SSE 流式输出
  5. LangFuse 可观测性（可选，缺配置时静默降级）

架构红线：
  - 意图路由由 LLM Tool Calling 驱动，严禁 if-else 硬编码
  - 单向流式输出用 SSE
  - API Key 存后端 .env，严禁暴露给前端
"""
import json
import os
import time
from typing import AsyncGenerator, Optional

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.industry_vocab import IndustryVocabService

# ========== LangFuse 可观测性（可选） ==========
_langfuse = None
try:
    _lf_public = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    _lf_secret = os.getenv("LANGFUSE_SECRET_KEY", "")
    if _lf_public and _lf_secret:
        from langfuse import Langfuse
        _langfuse = Langfuse(
            public_key=_lf_public,
            secret_key=_lf_secret,
            host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
        )
        print("✅ LangFuse 可观测性已启用")
    else:
        print("ℹ️ LangFuse 未配置，跳过可观测性追踪")
except ImportError:
    print("ℹ️ langfuse 未安装，跳过可观测性追踪")
except Exception as e:
    print(f"⚠️ LangFuse 初始化失败: {e}")


# 系统提示词 — 定义 AI 角色
SYSTEM_PROMPT = """你是"鲜标智投助手"——一个生鲜食材配送投标文件智能生成助手。

你的能力：
1. **招标文件解析** — 分析招标文件，提取评分标准、废标项、资格要求等
2. **法规标准检索** — 语义搜索食品安全法规、冷链标准、采购规范等
3. **资质核验** — 比对招标资格要求与企业已有证照，找出缺口
4. **投标章节生成** — 根据招标要求+企业信息+模板生成技术/商务方案
5. **报价策略分析** — 基于历史中标数据给出下浮率建议
6. **合规审查** — 五维合规检查（废标项/资质/评分覆盖/报价/食品安全）
7. **历史案例检索** — 从中标案例库检索相似项目供参考
8. **知识库摘要** — 从已有模板知识库检索内容片段并生成摘要

沟通规则：
- 使用专业的投标文件用语回答
- 如果用户提供了招标文件信息，直接调用对应工具分析
- 废标项是最危险的，发现风险必须重点警告
- 报价数值只能给建议区间，最终定价由用户决定（安全红线）
- 引用法规时标注来源（如《食品安全法》第XX条）
- 资质缺口要具体到证书名称和办理建议
"""

# ===== 工具定义（OpenAI Function Calling 格式） =====
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_regulations",
            "description": "食品安全法规/冷链标准语义检索 — 当用户询问法规条款、行业标准、食品安全规范时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词或自然语言描述"},
                    "top_k": {"type": "integer", "description": "返回最相关的前K条", "default": 5},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_credentials",
            "description": "资质核验 — 比对招标资格要求与企业已有证照，找出缺口。当用户询问资质是否齐全、缺少什么证照时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "integer", "description": "投标项目ID"},
                },
                "required": ["project_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_pricing",
            "description": "报价策略分析 — 基于客户类型和预算给出下浮率建议。当用户询问报价、定价、下浮率时调用。注意：只给建议，最终定价由用户决定。",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "integer", "description": "投标项目ID"},
                },
                "required": ["project_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_bid_cases",
            "description": "历史中标案例检索 — 从案例库中搜索相似投标项目供参考。当用户询问类似项目、历史案例、中标经验时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词（如: 学校食材配送）"},
                    "top_k": {"type": "integer", "description": "返回最相关的前K条", "default": 5},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "summarize_knowledge",
            "description": "知识库摘要 — 从已有模板知识库中检索指定主题的内容片段并生成摘要。当用户询问模板内容、行业方案参考时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "检索主题（如：冷链配送方案、食品安全管理体系）"},
                    "top_k": {"type": "integer", "description": "返回最相关的前K条片段", "default": 10},
                },
                "required": ["topic"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_project_summary",
            "description": "获取投标项目概况 — 查询项目基本信息、招标要求、章节状态等。当用户询问某个项目的详情时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "integer", "description": "投标项目ID"},
                },
                "required": ["project_id"],
            },
        },
    },
]


class AIRouter:
    """AI 智能路由引擎"""

    def __init__(self, session: Optional[AsyncSession] = None, tenant_id: int = 0, industry_type: str = "coal_excavation"):
        # 优先使用 OpenAI，兼容 Gemini（通过 OpenAI 兼容 API）
        from app.core.config import settings
        api_key = settings.OPENAI_API_KEY or settings.GEMINI_API_KEY
        base_url = settings.OPENAI_BASE_URL or None
        self.model = settings.AI_MODEL
        self.session = session  # 数据库 session（用于向量检索）
        self.tenant_id = tenant_id
        self.industry_type = industry_type

        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url

        self.client = AsyncOpenAI(**client_kwargs)

    def _build_system_prompt(self) -> str:
        """构建 System Prompt — 基础角色 + 行业词库动态注入"""
        prompt = SYSTEM_PROMPT
        # 铁律：行业词库注入
        injection = IndustryVocabService.build_prompt_injection(self.industry_type)
        if injection:
            prompt += injection
        return prompt

    async def _execute_tool_async(self, name: str, args: dict) -> dict:
        """执行工具调用（统一异步入口）"""
        if name == "search_regulations":
            return await self._search_regulations(args)
        elif name == "check_credentials":
            return await self._check_credentials(args)
        elif name == "analyze_pricing":
            return await self._analyze_pricing(args)
        elif name == "search_bid_cases":
            return await self._search_bid_cases(args)
        elif name == "summarize_knowledge":
            return await self._summarize_knowledge_tool(args)
        elif name == "get_project_summary":
            return await self._get_project_summary(args)
        else:
            return {"error": f"未知工具: {name}"}

    async def _check_credentials(self, args: dict) -> dict:
        """Tool: 资质核验 — 比对招标要求 vs 企业已有证照"""
        if not self.session:
            return {"error": "数据库连接不可用"}
        try:
            from sqlalchemy import select
            from sqlalchemy.orm import selectinload
            from app.models.bid_project import BidProject, TenderRequirement
            from app.models.credential import Credential

            project_id = args.get("project_id")
            result = await self.session.execute(
                select(BidProject)
                .where(BidProject.id == project_id, BidProject.tenant_id == self.tenant_id)
                .options(selectinload(BidProject.requirements))
            )
            project = result.scalar_one_or_none()
            if not project:
                return {"error": "投标项目不存在"}

            # 获取企业证照
            creds = []
            if project.enterprise_id:
                cred_result = await self.session.execute(
                    select(Credential).where(
                        Credential.enterprise_id == project.enterprise_id,
                        Credential.tenant_id == self.tenant_id,
                    )
                )
                creds = list(cred_result.scalars().all())

            qual_reqs = [r for r in project.requirements if r.category == "qualification"]
            return {
                "status": "ok",
                "qualification_requirements": [r.content for r in qual_reqs],
                "enterprise_credentials": [
                    {"type": c.cred_type, "name": c.cred_name, "expiry": c.expiry_date, "verified": c.is_verified}
                    for c in creds
                ],
                "credential_count": len(creds),
                "requirement_count": len(qual_reqs),
            }
        except Exception as e:
            return {"error": f"资质核验失败: {str(e)}"}

    async def _analyze_pricing(self, args: dict) -> dict:
        """Tool: 报价策略分析 — 返回项目报价相关信息（建议由 LLM 解读）"""
        if not self.session:
            return {"error": "数据库连接不可用"}
        try:
            from sqlalchemy import select
            from app.models.bid_project import BidProject
            project_id = args.get("project_id")
            result = await self.session.execute(
                select(BidProject).where(
                    BidProject.id == project_id, BidProject.tenant_id == self.tenant_id
                )
            )
            project = result.scalar_one_or_none()
            if not project:
                return {"error": "投标项目不存在"}

            return {
                "status": "ok",
                "project_name": project.project_name,
                "customer_type": project.customer_type,
                "budget_amount": project.budget_amount,
                "delivery_scope": project.delivery_scope,
                "note": "报价数值仅供参考，最终定价必须由用户确认（安全红线）",
            }
        except Exception as e:
            return {"error": f"报价分析失败: {str(e)}"}

    async def _search_bid_cases(self, args: dict) -> dict:
        """Tool: 历史中标案例检索"""
        if not self.session:
            return {"error": "数据库连接不可用"}
        try:
            from app.services.embedding_service import EmbeddingService
            emb_svc = EmbeddingService(self.session)
            results = await emb_svc.search_snippets(
                query=args.get("query", ""),
                tenant_id=self.tenant_id,
                top_k=args.get("top_k", 5),
                threshold=0.4,
            )
            if not results:
                return {"status": "no_results", "message": "未找到相似中标案例"}
            return {
                "status": "ok",
                "total": len(results),
                "cases": [
                    {"chapter": r.get("chapter_name", ""), "content": r.get("content", "")[:500]}
                    for r in results
                ],
            }
        except Exception as e:
            return {"error": f"案例检索失败: {str(e)}"}

    async def _get_project_summary(self, args: dict) -> dict:
        """Tool: 获取投标项目概况"""
        if not self.session:
            return {"error": "数据库连接不可用"}
        try:
            from app.services.bid_project_service import BidProjectService
            svc = BidProjectService(self.session)
            project = await svc.get_project(args.get("project_id", 0), self.tenant_id)
            if not project:
                return {"error": "投标项目不存在"}
            return {
                "status": "ok",
                "project_name": project.project_name,
                "tender_org": project.tender_org,
                "customer_type": project.customer_type,
                "budget_amount": project.budget_amount,
                "deadline": project.deadline,
                "status": project.status,
                "requirements_count": len(project.requirements),
                "chapters_count": len(project.chapters),
                "disqualification_count": sum(
                    1 for r in project.requirements if r.category == "disqualification"
                ),
            }
        except Exception as e:
            return {"error": f"查询失败: {str(e)}"}

    async def _search_regulations(self, args: dict) -> dict:
        """食品安全法规/冷链标准语义检索"""
        if not self.session:
            return {"error": "数据库连接不可用", "results": []}

        try:
            from app.services.retriever import HybridRetriever
            retriever = HybridRetriever(self.session, self.tenant_id)

            # 从 args 中提取上下文参数（如果有）
            context = {}
            for key in ["rock_class", "section_form", "gas_level", "tunnel_type", "dig_method"]:
                if args.get(key):
                    context[key] = args[key]

            result = await retriever.retrieve(
                query=args.get("query", ""),
                context=context,
                top_k=args.get("top_k", 5),
            )

            if not result["merged"]:
                return {
                    "status": "no_results",
                    "message": "未找到相关条款或参数表记录",
                }
            return {
                "status": "ok",
                "summary": result["summary"],
                "total": len(result["merged"]),
                "semantic_count": len(result["semantic_results"]),
                "snippet_count": len(result.get("snippet_results", [])),
                "table_count": len(result["table_results"]),
                "results": result["merged"],
            }
        except Exception as e:
            return {"error": f"融合检索失败: {str(e)}", "results": []}

    async def _summarize_knowledge_tool(self, args: dict) -> dict:
        """Tool: 知识库文档摘要 — 检索客户已有规程片段并结构化输出"""
        if not self.session:
            return {"error": "数据库连接不可用"}

        topic = args.get("topic", "")
        top_k = args.get("top_k", 10)

        try:
            from app.services.embedding_service import EmbeddingService
            emb_svc = EmbeddingService(self.session)

            # 从知识库检索
            results = await emb_svc.search_snippets(
                query=topic, tenant_id=self.tenant_id,
                top_k=top_k, threshold=0.35,
            )

            if not results:
                return {
                    "status": "no_results",
                    "message": f"知识库中未找到与'{topic}'相关的内容",
                }

            # 结构化输出
            snippets = []
            for r in results:
                snippets.append({
                    "chapter": r.get("chapter_name", "未知章节"),
                    "content": r["content"][:2000],  # 截取前 2000 字符
                    "similarity": round(r.get("similarity", 0), 3),
                })

            return {
                "status": "ok",
                "topic": topic,
                "total": len(snippets),
                "snippets": snippets,
            }
        except Exception as e:
            return {"error": f"知识库检索失败: {str(e)}"}

    async def chat(self, user_message: str, history: Optional[list] = None) -> str:
        """非流式对话（完整响应）"""
        messages = [{"role": "system", "content": self._build_system_prompt()}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        # LangFuse trace（可选）
        trace = None
        if _langfuse:
            trace = _langfuse.trace(
                name="ai_chat",
                input=user_message,
                metadata={"stream": False},
            )

        t0 = time.time()

        # 第一轮：LLM 决定是否调用工具
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
        )

        msg = response.choices[0].message

        # 如果有工具调用
        if msg.tool_calls:
            messages.append(msg.model_dump())

            for tc in msg.tool_calls:
                fn_name = tc.function.name
                fn_args = json.loads(tc.function.arguments)

                # LangFuse 记录 tool span
                if trace:
                    trace.span(name=f"tool_{fn_name}", input=fn_args)

                result = await self._execute_tool_async(fn_name, fn_args)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result, ensure_ascii=False),
                })

            # 第二轮：LLM 解读工具结果
            response2 = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
            )
            reply = response2.choices[0].message.content or ""
        else:
            reply = msg.content or ""

        # LangFuse 记录输出
        if trace:
            trace.update(
                output=reply,
                metadata={"latency_s": round(time.time() - t0, 2)},
            )

        return reply

    async def chat_stream(
        self, user_message: str, history: Optional[list] = None
    ) -> AsyncGenerator[str, None]:
        """SSE 流式对话 — 带完整异常处理和超时保护"""
        import asyncio

        messages = [{"role": "system", "content": self._build_system_prompt()}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        # LangFuse trace
        trace = None
        if _langfuse:
            trace = _langfuse.trace(
                name="ai_chat_stream",
                input=user_message,
                metadata={"stream": True},
            )

        t0 = time.time()
        full_reply = ""

        try:
            # 第一轮：检测工具调用（非流式，带超时保护）
            response = await asyncio.wait_for(
                self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=TOOLS,
                    tool_choice="auto",
                ),
                timeout=60,
            )

            msg = response.choices[0].message

            if msg.tool_calls:
                # 有工具调用 → 先执行，再流式输出解读
                # Gemini 兼容 API 不接受 null 值，必须排除
                assistant_msg = msg.model_dump(exclude_none=True)
                messages.append(assistant_msg)

                for tc in msg.tool_calls:
                    fn_name = tc.function.name
                    fn_args = json.loads(tc.function.arguments)

                    yield f"data: {json.dumps({'type': 'tool_start', 'name': fn_name, 'args': fn_args}, ensure_ascii=False)}\n\n"

                    if trace:
                        trace.span(name=f"tool_{fn_name}", input=fn_args)

                    try:
                        result = await asyncio.wait_for(
                            self._execute_tool_async(fn_name, fn_args),
                            timeout=30,
                        )
                    except asyncio.TimeoutError:
                        result = {"error": f"工具 {fn_name} 执行超时"}
                    except Exception as e:
                        result = {"error": f"工具 {fn_name} 执行失败: {str(e)}"}

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(result, ensure_ascii=False),
                    })

                    yield f"data: {json.dumps({'type': 'tool_done', 'name': fn_name}, ensure_ascii=False)}\n\n"

                # 第二轮：流式输出 LLM 解读
                stream = await asyncio.wait_for(
                    self.client.chat.completions.create(
                        model=self.model,
                        messages=messages,
                        stream=True,
                    ),
                    timeout=60,
                )

                async for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        content = chunk.choices[0].delta.content
                        full_reply += content
                        yield f"data: {json.dumps({'type': 'text', 'content': content}, ensure_ascii=False)}\n\n"

            else:
                # 无工具调用 → 直接流式输出
                stream = await asyncio.wait_for(
                    self.client.chat.completions.create(
                        model=self.model,
                        messages=messages,
                        stream=True,
                    ),
                    timeout=60,
                )
                async for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        content = chunk.choices[0].delta.content
                        full_reply += content
                        yield f"data: {json.dumps({'type': 'text', 'content': content}, ensure_ascii=False)}\n\n"

        except asyncio.TimeoutError:
            yield f"data: {json.dumps({'type': 'error', 'content': 'AI 响应超时，请稍后重试'}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': f'AI 服务异常: {str(e)}'}, ensure_ascii=False)}\n\n"

        # LangFuse 记录
        if trace:
            trace.update(
                output=full_reply,
                metadata={"latency_s": round(time.time() - t0, 2)},
            )

        yield "data: [DONE]\n\n"
