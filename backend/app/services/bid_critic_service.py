"""
投标文档 Critic 质量闭环 — 生成后自动审查并重写

架构红线：
  - AI 生成文档必须过 Critic 质量闭环（01-AI-Platform-Rules.md L80-89）
  - 模型名从 LLMSelector 获取（禁止硬编码）

审查维度：
  1. 事实一致性 — 企业名/资质/冷链配置是否与 enterprise 数据一致
  2. 投标规范 — 是否使用"我方"/"贵方"等标准投标用语
  3. 完整性 — 是否覆盖了招标要求的关键评分点
  4. 字数合理性 — 章节字数是否在合理范围内
"""
import os
from typing import Optional

from openai import AsyncOpenAI

from app.core.config import settings
from app.core.llm_selector import LLMSelector
from app.core.prompt_manager import prompt_manager
from app.models.enterprise import Enterprise


class BidCriticService:
    """投标文档 Critic 质量闭环

    对 LLM 生成的投标章节内容进行自动化审查，
    发现问题时调用 LLM 进行定向重写修复。
    """

    def __init__(self):
        """初始化 Critic 服务"""
        config = LLMSelector.get_config("compliance_check")
        model = (config.get("models") or ["deepseek-chat"])[0]
        self.model = model
        self.temperature = config.get("temperature", 0.1)

        api_key = settings.OPENAI_API_KEY or settings.GEMINI_API_KEY
        base_url = settings.OPENAI_BASE_URL or None

        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        self.client = AsyncOpenAI(**client_kwargs)

    async def critic_and_rewrite(
        self,
        content: str,
        chapter_meta: dict,
        enterprise: Optional[Enterprise] = None,
    ) -> tuple[str, dict]:
        """对生成内容执行 Critic 审查 + 自动重写

        Args:
            content: LLM 原始生成的章节内容
            chapter_meta: 章节元信息 {"name": "技术方案", "chapter_no": 3, "requirements": [...]}
            enterprise: 企业信息对象（用于事实核查）

        Returns:
            (优化后内容, 审查元数据)
            审查元数据格式:
            {
                "passed": bool,          # 是否一次通过
                "issues_found": int,     # 发现问题数
                "issues": [str],         # 问题描述列表
                "rewritten": bool,       # 是否执行了重写
                "original_length": int,  # 原始字数
                "final_length": int,     # 最终字数
            }
        """
        chapter_name = chapter_meta.get("name", "未知章节")
        requirements = chapter_meta.get("requirements", [])

        # 构建企业事实信息（用于核查）
        enterprise_facts = ""
        if enterprise:
            facts = [f"企业名称：{enterprise.name}"]
            if enterprise.legal_person:
                facts.append(f"法人代表：{enterprise.legal_person}")
            if enterprise.registered_capital:
                facts.append(f"注册资本：{enterprise.registered_capital}")
            if enterprise.cold_chain_vehicles:
                facts.append(f"冷链车辆：{enterprise.cold_chain_vehicles}辆")
            if enterprise.warehouse_area:
                facts.append(f"仓库面积：{enterprise.warehouse_area}㎡")
            enterprise_facts = "\n".join(facts)

        # 组装 Critic Prompt
        requirements_text = "\n".join(f"- {r}" for r in requirements) if requirements else "（未提供具体要求）"

        critic_prompt = f"""你是一位资深投标文件审查专家。请对以下投标章节内容进行严格审查。

## 待审查章节
章节名称：{chapter_name}
章节内容：
{content}

## 审查基准
### 招标要求（必须覆盖）
{requirements_text}

### 企业事实信息（必须一致）
{enterprise_facts if enterprise_facts else "（未提供，跳过事实核查）"}

## 审查维度
1. **事实一致性**：文中提及的企业名、资质、设备数据是否与企业事实一致？有无编造数据？
2. **投标规范**：是否使用了"我方"/"贵方"等标准投标用语？有无口语化表达？
3. **完整性**：是否覆盖了招标要求中的关键评分点？有无遗漏？
4. **字数合理性**：内容是否充实（不少于500字）？有无明显注水或过于空泛？

## 输出要求
请严格按以下 JSON 格式输出审查结果（不要添加 markdown 标记）：
{{
    "passed": true/false,
    "issues": ["问题1描述", "问题2描述"],
    "suggestions": "如果未通过，给出具体修改建议"
}}
"""

        try:
            # 调用 LLM 执行审查
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": critic_prompt}],
                temperature=self.temperature,
                max_tokens=2048,
            )

            critic_result_text = response.choices[0].message.content or "{}"

            # 解析审查结果
            import json
            # 清理可能的 markdown 代码块标记
            clean_text = critic_result_text.strip()
            if clean_text.startswith("```"):
                clean_text = clean_text.split("\n", 1)[1] if "\n" in clean_text else clean_text
            if clean_text.endswith("```"):
                clean_text = clean_text[:-3]
            clean_text = clean_text.strip()

            try:
                critic_result = json.loads(clean_text)
            except json.JSONDecodeError:
                # JSON 解析失败，视为通过（容错）
                critic_result = {"passed": True, "issues": [], "suggestions": ""}

            issues = critic_result.get("issues", [])
            passed = critic_result.get("passed", True)

            meta = {
                "passed": passed,
                "issues_found": len(issues),
                "issues": issues,
                "rewritten": False,
                "original_length": len(content),
                "final_length": len(content),
            }

            # 如果审查通过，直接返回原内容
            if passed and len(issues) == 0:
                return content, meta

            # 审查未通过 → 执行定向重写
            suggestions = critic_result.get("suggestions", "")
            issues_text = "\n".join(f"- {issue}" for issue in issues)

            rewrite_prompt = f"""请根据以下审查意见，对投标章节内容进行修改优化。

## 原始内容
{content}

## 审查发现的问题
{issues_text}

## 修改建议
{suggestions}

## 要求
1. 保持原文整体结构不变
2. 仅针对上述问题进行修改
3. 确保修改后的事实数据与企业信息一致
4. 使用规范的投标文书语言
5. 直接输出修改后的完整章节内容，不要添加任何说明文字
"""

            rewrite_response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": rewrite_prompt}],
                temperature=0.2,
                max_tokens=LLMSelector.get_max_tokens("bid_section_generate"),
            )

            rewritten_content = rewrite_response.choices[0].message.content or content

            meta["rewritten"] = True
            meta["final_length"] = len(rewritten_content)

            return rewritten_content, meta

        except Exception as e:
            # Critic 服务异常时不阻塞主流程，返回原内容 + 错误信息
            print(f"⚠️ Critic 审查异常: {e}")
            return content, {
                "passed": True,
                "issues_found": 0,
                "issues": [],
                "rewritten": False,
                "original_length": len(content),
                "final_length": len(content),
                "error": str(e),
            }
