"""
应用配置 — 从 .env 环境变量加载
鲜标智投 — 生鲜食材配送投标文件智能生成平台
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    """全局配置项，由 .env 驱动"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # --- 应用 ---
    APP_NAME: str = "鲜标智投 — 生鲜食材配送投标文件智能生成平台"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    SECRET_KEY: str = "change-me-to-a-random-secret-key-at-least-32-chars"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120

    # --- 数据库 ---
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/fresh_bid_platform"

    # --- Redis ---
    REDIS_URL: str = "redis://localhost:6379/0"

    # --- 文件存储 ---
    OSS_ENDPOINT: str = ""
    OSS_ACCESS_KEY_ID: str = ""
    OSS_ACCESS_KEY_SECRET: str = ""
    OSS_BUCKET_NAME: str = "fresh-bid-platform"

    # --- CORS ---
    CORS_ORIGINS: List[str] = ["http://localhost:3000"]

    # --- AI / LLM 多 Provider 配置 ---
    # 每个 Provider 独立配置 API Key + Base URL
    # llm_registry.yaml 中通过 provider 字段路由到对应配置

    # Provider: openai（GPT 系列）
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    AI_MODEL: str = "gpt-5.4"

    # Provider: gemini（通过 OpenAI 兼容端点）
    GEMINI_API_KEY: str = ""
    GEMINI_BASE_URL: str = "https://generativelanguage.googleapis.com/v1beta/openai"

    # Provider: deepseek（国产合规）
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/v1"

    # Provider: qwen（通义千问，备选）
    QWEN_API_KEY: str = ""
    QWEN_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    # LiteLLM 代理网关（可选，统一路由多模型）
    LITELLM_BASE_URL: str = ""

    # --- 文档生成 ---
    # 单次生成允许的最大并发 AI 润色任务数
    DOC_GEN_MAX_CONCURRENCY: int = 5
    # 章节生成超时秒数
    DOC_GEN_CHAPTER_TIMEOUT: int = 60

    # --- 投标业务 ---
    # 报价下浮率合理区间（默认 5%-15%）
    QUOTATION_MIN_DISCOUNT: float = 0.05
    QUOTATION_MAX_DISCOUNT: float = 0.15
    # 资质证书到期提前预警天数
    CREDENTIAL_EXPIRY_WARN_DAYS: int = 90

    # --- 系统工具 ---
    SOFFICE_PATH: str = "soffice"
    ADMIN_INIT_PASSWORD: str = "admin123"


# 全局单例
settings = Settings()

# 安全红线：SECRET_KEY 启动校验
_DEFAULT_SECRET = "change-me-to-a-random-secret-key-at-least-32-chars"
if settings.SECRET_KEY == _DEFAULT_SECRET:
    if settings.DEBUG:
        import warnings
        warnings.warn(
            "⚠️ SECRET_KEY 使用默认值，仅允许在 DEBUG 模式下运行。"
            "请在 .env 中设置 SECRET_KEY 为 ≥32 字节的随机密钥。",
            stacklevel=1,
        )
    else:
        raise RuntimeError(
            "❌ 生产环境禁止使用默认 SECRET_KEY！"
            "请在 .env 中设置: SECRET_KEY=$(python -c \"import secrets; print(secrets.token_urlsafe(32))\")"
        )
