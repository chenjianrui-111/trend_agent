"""
全局配置 - TrendAgent 系统运行参数
支持通过环境变量切换 开发/测试/生产 环境
"""

import os
from dataclasses import dataclass, field
from typing import List


@dataclass
class ScraperConfig:
    """数据抓取配置"""
    twitter_bearer_token: str = os.getenv("TWITTER_BEARER_TOKEN", "")
    twitter_max_results: int = int(os.getenv("TWITTER_MAX_RESULTS", "100"))
    youtube_api_key: str = os.getenv("YOUTUBE_API_KEY", "")
    youtube_max_results: int = int(os.getenv("YOUTUBE_MAX_RESULTS", "50"))
    youtube_region_code: str = os.getenv("YOUTUBE_REGION_CODE", "US")
    weibo_access_token: str = os.getenv("WEIBO_ACCESS_TOKEN", "")
    bilibili_sessdata: str = os.getenv("BILIBILI_SESSDATA", "")
    zhihu_cookie: str = os.getenv("ZHIHU_COOKIE", "")
    request_timeout_seconds: float = float(os.getenv("SCRAPER_TIMEOUT_SECONDS", "30"))
    concurrent_scrapers: int = int(os.getenv("CONCURRENT_SCRAPERS", "5"))
    enabled_sources: List[str] = field(default_factory=lambda: [
        s.strip() for s in os.getenv(
            "SCRAPER_ENABLED_SOURCES", "twitter,youtube,weibo,bilibili"
        ).split(",") if s.strip()
    ])


@dataclass
class PublisherConfig:
    """发布平台配置"""
    wechat_app_id: str = os.getenv("WECHAT_APP_ID", "")
    wechat_app_secret: str = os.getenv("WECHAT_APP_SECRET", "")
    xiaohongshu_cookie: str = os.getenv("XIAOHONGSHU_COOKIE", "")
    douyin_access_token: str = os.getenv("DOUYIN_ACCESS_TOKEN", "")
    weibo_publish_token: str = os.getenv("WEIBO_PUBLISH_TOKEN", "")
    publish_retry_max: int = int(os.getenv("PUBLISH_RETRY_MAX", "3"))
    publish_retry_delay_seconds: float = float(os.getenv("PUBLISH_RETRY_DELAY", "5"))


@dataclass
class VideoConfig:
    """AI 视频生成配置"""
    default_provider: str = os.getenv("VIDEO_DEFAULT_PROVIDER", "keling")
    runway_api_key: str = os.getenv("RUNWAY_API_KEY", "")
    runway_base_url: str = os.getenv("RUNWAY_BASE_URL", "https://api.dev.runwayml.com/v1")
    pika_api_key: str = os.getenv("PIKA_API_KEY", "")
    pika_base_url: str = os.getenv("PIKA_BASE_URL", "https://api.pika.art/v1")
    keling_access_key: str = os.getenv("KELING_ACCESS_KEY", "")
    keling_secret_key: str = os.getenv("KELING_SECRET_KEY", "")
    keling_base_url: str = os.getenv("KELING_BASE_URL", "https://api.klingai.com/v1")
    poll_interval_seconds: int = int(os.getenv("VIDEO_POLL_INTERVAL", "10"))
    poll_max_wait_seconds: int = int(os.getenv("VIDEO_POLL_MAX_WAIT", "600"))
    fallback_enabled: bool = os.getenv("VIDEO_FALLBACK_ENABLED", "true").lower() == "true"


@dataclass
class LLMConfig:
    """LLM 服务配置"""
    primary_backend: str = os.getenv("LLM_PRIMARY_BACKEND", "zhipu")
    # Zhipu
    zhipu_api_key: str = os.getenv("ZHIPU_API_KEY", "")
    zhipu_base_url: str = os.getenv("ZHIPU_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
    zhipu_model: str = os.getenv("ZHIPU_MODEL", "glm-4-flash")
    # OpenAI-compatible
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    # Ollama
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
    # Generation params
    temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.7"))
    max_tokens: int = int(os.getenv("LLM_MAX_TOKENS", "2048"))
    # Reliability
    retry_max_attempts: int = int(os.getenv("LLM_RETRY_MAX_ATTEMPTS", "3"))
    retry_base_delay_seconds: float = float(os.getenv("LLM_RETRY_BASE_DELAY_SECONDS", "0.5"))
    timeout_seconds: float = float(os.getenv("LLM_TIMEOUT_SECONDS", "60"))
    # Fallback
    fallback_enabled: bool = os.getenv("LLM_FALLBACK_ENABLED", "true").lower() == "true"
    fallback_backend: str = os.getenv("LLM_FALLBACK_BACKEND", "ollama")


@dataclass
class DatabaseConfig:
    """数据库配置"""
    url: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///trend_agent.db")
    echo: bool = os.getenv("DB_ECHO", "false").lower() == "true"
    pool_size: int = int(os.getenv("DB_POOL_SIZE", "10"))


@dataclass
class SchedulerConfig:
    """定时调度配置"""
    enabled: bool = os.getenv("SCHEDULER_ENABLED", "true").lower() == "true"
    timezone: str = os.getenv("SCHEDULER_TIMEZONE", "Asia/Shanghai")
    misfire_grace_time: int = int(os.getenv("SCHEDULER_MISFIRE_GRACE", "300"))


@dataclass
class QualityConfig:
    """内容质量检查配置"""
    sensitive_word_list_path: str = os.getenv("SENSITIVE_WORD_LIST", "")
    min_body_length: int = int(os.getenv("QUALITY_MIN_BODY_LENGTH", "100"))
    max_similarity_threshold: float = float(os.getenv("QUALITY_MAX_SIMILARITY", "0.85"))
    enable_llm_review: bool = os.getenv("QUALITY_LLM_REVIEW", "false").lower() == "true"


@dataclass
class MediaConfig:
    """媒体资产存储配置"""
    backend: str = os.getenv("MEDIA_BACKEND", "local")
    local_path: str = os.getenv("MEDIA_LOCAL_PATH", "./media")
    s3_bucket: str = os.getenv("MEDIA_S3_BUCKET", "")
    s3_endpoint: str = os.getenv("MEDIA_S3_ENDPOINT", "")
    s3_access_key: str = os.getenv("MEDIA_S3_ACCESS_KEY", "")
    s3_secret_key: str = os.getenv("MEDIA_S3_SECRET_KEY", "")


@dataclass
class AuthConfig:
    """认证配置"""
    jwt_secret: str = os.getenv("JWT_SECRET", "trend-agent-jwt-secret-change-in-production")
    token_expires_seconds: int = int(os.getenv("AUTH_TOKEN_EXPIRES_SECONDS", "86400"))
    registration_enabled: bool = os.getenv("AUTH_REGISTRATION_ENABLED", "true").lower() == "true"


@dataclass
class OrchestrationConfig:
    """编排执行配置"""
    langgraph_required: bool = os.getenv("LANGGRAPH_REQUIRED", "false").lower() == "true"
    checkpoint_auto_save: bool = os.getenv("CHECKPOINT_AUTO_SAVE", "true").lower() == "true"
    checkpoint_store: str = os.getenv("CHECKPOINT_STORE", "memory").lower()


@dataclass
class AppConfig:
    """应用总配置"""
    app_name: str = "trend_agent"
    env: str = os.getenv("APP_ENV", "development")
    debug: bool = os.getenv("DEBUG", "true").lower() == "true"
    host: str = "0.0.0.0"
    port: int = int(os.getenv("PORT", "8090"))

    scraper: ScraperConfig = field(default_factory=ScraperConfig)
    publisher: PublisherConfig = field(default_factory=PublisherConfig)
    video: VideoConfig = field(default_factory=VideoConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)
    quality: QualityConfig = field(default_factory=QualityConfig)
    media: MediaConfig = field(default_factory=MediaConfig)
    auth: AuthConfig = field(default_factory=AuthConfig)
    orchestration: OrchestrationConfig = field(default_factory=OrchestrationConfig)


# 全局配置单例
settings = AppConfig()
