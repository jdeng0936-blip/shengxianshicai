"""
AI 智能路由引擎 — LLM Tool Calling 驱动的意图识别与引擎调度

核心设计：
  1. 定义 6 个 Tool（支护/通风/循环计算 + 规则匹配 + 标准库语义检索 + 安全建议）
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

from app.schemas.calc import SupportCalcInput
from app.schemas.vent import VentCalcInput
from app.schemas.cycle import CycleCalcInput
from app.services.calc_engine import SupportCalcEngine
from app.services.vent_engine import VentCalcEngine
from app.services.cycle_engine import CycleCalcEngine
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
SYSTEM_PROMPT = """你是"掘进智脑"——一个煤矿掘进工作面作业规程智能生成助手。

你的能力：
1. **支护计算** — 根据围岩级别、断面尺寸计算锚杆锚固力、最大间距、安全系数等
2. **通风计算** — 根据瓦斯涌出量、断面面积计算需风量，自动选型局扇
3. **循环作业计算** — 根据掘进方式计算循环进尺、日/月进尺
4. **标准规范检索** — 语义搜索国家标准、行业规范中的相关条款
5. **规程建议** — 根据工程条件给出安全技术措施建议

沟通规则：
- 使用专业但易懂的中文回答
- 如果用户提供了参数，直接调用对应工具计算
- 如果参数不完整，请友善地询问缺失项
- 计算结果需要解读关键数据，特别是合规预警要重点标红提示
- 引用检索到的标准条款时，标注来源（条款编号+规范名称）
- 对危险操作（如超限参数）要主动警告
"""

# ===== 工具定义（OpenAI Function Calling 格式） =====
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "calc_support",
            "description": "支护计算 — 根据围岩条件和断面参数,计算锚杆锚固力、最大间距、安全系数等。当用户询问锚杆、锚索、支护参数时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "rock_class": {"type": "string", "enum": ["I","II","III","IV","V"], "description": "围岩级别"},
                    "section_form": {"type": "string", "enum": ["矩形","拱形","梯形"], "description": "断面形式"},
                    "section_width": {"type": "number", "description": "断面宽度(m)"},
                    "section_height": {"type": "number", "description": "断面高度(m)"},
                    "bolt_spacing": {"type": "number", "description": "锚杆间距(mm),可选", "default": 1000},
                    "cable_count": {"type": "integer", "description": "锚索数量,可选", "default": 3},
                },
                "required": ["rock_class", "section_form", "section_width", "section_height"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calc_ventilation",
            "description": "通风计算 — 三法求需风量(瓦斯涌出法/人数法/炸药法) + 局扇选型。当用户询问通风、需风量、局扇时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "gas_emission": {"type": "number", "description": "瓦斯绝对涌出量(m³/min)"},
                    "gas_level": {"type": "string", "enum": ["低瓦斯","高瓦斯","突出"], "description": "瓦斯等级"},
                    "section_area": {"type": "number", "description": "巷道断面积(m²)"},
                    "excavation_length": {"type": "number", "description": "掘进长度(m)"},
                    "max_workers": {"type": "integer", "description": "最多同时工作人数", "default": 25},
                    "design_air_volume": {"type": "number", "description": "设计风量(m³/min),可选"},
                },
                "required": ["gas_emission", "gas_level", "section_area", "excavation_length"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calc_cycle",
            "description": "循环作业计算 — 工序编排 + 日/月进尺 + 正规循环率。当用户询问掘进速度、月进尺、循环时间时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "dig_method": {"type": "string", "enum": ["钻爆法","综掘"], "description": "掘进方式"},
                    "hole_depth": {"type": "number", "description": "炮眼深度(m),钻爆法用", "default": 2.0},
                    "cut_depth": {"type": "number", "description": "截割深度(m),综掘用", "default": 0.8},
                    "shifts_per_day": {"type": "integer", "description": "日班次", "default": 3},
                    "design_monthly_advance": {"type": "number", "description": "设计月进尺(m),用于校核"},
                },
                "required": ["dig_method"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_standards",
            "description": "标准规范语义检索 — 当用户询问国家标准、行业规范、法律法规条文、安全规程时调用。通过语义匹配找到最相关的条款原文。",
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
            "name": "query_standard_table",
            "description": "结构化参数查表 — 根据围岩级别、瓦斯等级、掘进方式等条件，精确查询标准参数推荐表（支护参数表、通风标准表、设备配置表）。当用户询问具体的推荐参数值、标准配置时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "table_name": {"type": "string", "enum": ["支护参数", "通风标准", "设备配置"], "description": "要查询的参数表"},
                    "rock_class": {"type": "string", "enum": ["I","II","III","IV","V"], "description": "围岩级别（查支护参数表时必填）"},
                    "section_form": {"type": "string", "enum": ["矩形","拱形","梯形"], "description": "断面形式"},
                    "gas_level": {"type": "string", "enum": ["低瓦斯","高瓦斯","突出"], "description": "瓦斯等级（查通风标准表时必填）"},
                    "tunnel_type": {"type": "string", "enum": ["煤巷","岩巷"], "description": "巷道类型"},
                    "dig_method": {"type": "string", "enum": ["钻爆法","综掘"], "description": "掘进方式（查设备配置表时必填）"},
                },
                "required": ["table_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_recommendations",
            "description": "规程建议 — 根据工程条件给出安全技术措施建议。当用户询问安全措施、注意事项、操作规程时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "rock_class": {"type": "string", "description": "围岩级别"},
                    "gas_level": {"type": "string", "description": "瓦斯等级"},
                    "dig_method": {"type": "string", "description": "掘进方式"},
                    "question": {"type": "string", "description": "用户具体问题"},
                },
                "required": ["question"],
            },
        },
    },
]


class AIRouter:
    """AI 智能路由引擎"""

    def __init__(self, session: Optional[AsyncSession] = None, tenant_id: int = 0, industry_type: str = "coal_excavation"):
        # 优先使用 OpenAI，兼容 Gemini（通过 OpenAI 兼容 API）
        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("GEMINI_API_KEY", "")
        base_url = os.getenv("OPENAI_BASE_URL")
        self.model = os.getenv("AI_MODEL", "gpt-4o-mini")
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

    def _execute_tool(self, name: str, args: dict) -> dict:
        """执行工具调用（同步计算引擎）"""
        if name == "calc_support":
            inp = SupportCalcInput(**args)
            r = SupportCalcEngine.calculate(inp)
            return r.model_dump()

        elif name == "calc_ventilation":
            inp = VentCalcInput(**args)
            r = VentCalcEngine.calculate(inp)
            return r.model_dump()

        elif name == "calc_cycle":
            inp = CycleCalcInput(**args)
            r = CycleCalcEngine.calculate(inp)
            return r.model_dump()

        elif name == "get_recommendations":
            return {"status": "ok", "context": args}

        elif name == "query_standard_table":
            from app.services.table_query_service import TableQueryService
            result = TableQueryService.query(
                table_name=args.get("table_name", ""),
                rock_class=args.get("rock_class", "III"),
                section_form=args.get("section_form", "拱形"),
                gas_level=args.get("gas_level", "低瓦斯"),
                tunnel_type=args.get("tunnel_type", "煤巷"),
                dig_method=args.get("dig_method", "钻爆法"),
            )
            return result if result else {"error": "未找到匹配的参数表记录", "query": args}

        else:
            return {"error": f"未知工具: {name}"}

    async def _execute_tool_async(self, name: str, args: dict) -> dict:
        """执行工具调用（支持异步 — 用于 search_standards）"""
        if name == "search_standards":
            return await self._search_standards(args)
        # 其他计算引擎是同步纯函数
        return self._execute_tool(name, args)

    async def _search_standards(self, args: dict) -> dict:
        """标准库融合检索 — L1 语义 + L2 查表 + L3 re-rank"""
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
                "table_count": len(result["table_results"]),
                "results": result["merged"],
            }
        except Exception as e:
            return {"error": f"融合检索失败: {str(e)}", "results": []}

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
        """SSE 流式对话"""
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

        # 第一轮：检测工具调用（非流式，以获取完整 tool_calls）
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
        )

        msg = response.choices[0].message

        if msg.tool_calls:
            # 有工具调用 → 先执行，再流式输出解读
            messages.append(msg.model_dump())
            full_reply = ""

            for tc in msg.tool_calls:
                fn_name = tc.function.name
                fn_args = json.loads(tc.function.arguments)

                # 通知前端正在调用工具
                yield f"data: {json.dumps({'type': 'tool_start', 'name': fn_name, 'args': fn_args}, ensure_ascii=False)}\n\n"

                if trace:
                    trace.span(name=f"tool_{fn_name}", input=fn_args)

                result = await self._execute_tool_async(fn_name, fn_args)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result, ensure_ascii=False),
                })

                yield f"data: {json.dumps({'type': 'tool_done', 'name': fn_name}, ensure_ascii=False)}\n\n"

            # 第二轮：流式输出 LLM 解读
            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=True,
            )

            async for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    full_reply += delta.content
                    yield f"data: {json.dumps({'type': 'text', 'content': delta.content}, ensure_ascii=False)}\n\n"

        else:
            # 无工具调用 → 直接流式输出
            full_reply = ""
            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=True,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    full_reply += delta.content
                    yield f"data: {json.dumps({'type': 'text', 'content': delta.content}, ensure_ascii=False)}\n\n"

        # LangFuse 记录
        if trace:
            trace.update(
                output=full_reply,
                metadata={"latency_s": round(time.time() - t0, 2)},
            )

        yield "data: [DONE]\n\n"
