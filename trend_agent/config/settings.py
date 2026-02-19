"""
全局配置 - TrendAgent 系统运行参数
支持通过环境变量切换 开发/测试/生产 环境
"""

import os
import json
from dataclasses import dataclass, field
from typing import Dict, List


def _load_platform_weights() -> Dict[str, float]:
    """
    Parse HEAT_PLATFORM_WEIGHTS from JSON or comma-separated format.
    Examples:
      {"twitter":1.0,"youtube":1.1}
      twitter=1.0,youtube=1.1
    """
    raw = os.getenv("HEAT_PLATFORM_WEIGHTS", "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            out = {}
            for k, v in parsed.items():
                try:
                    out[str(k).strip().lower()] = float(v)
                except (TypeError, ValueError):
                    continue
            return out
    except json.JSONDecodeError:
        pass

    out: Dict[str, float] = {}
    for part in raw.split(","):
        token = part.strip()
        if not token or "=" not in token:
            continue
        name, value = token.split("=", 1)
        name = name.strip().lower()
        if not name:
            continue
        try:
            out[name] = float(value.strip())
        except ValueError:
            continue
    return out


def _load_source_rps() -> Dict[str, float]:
    """
    Parse SCRAPER_SOURCE_RPS from JSON or comma-separated format.
    Examples:
      {"github":1.0,"twitter":2.0}
      github=1.0,twitter=2.0
    """
    raw = os.getenv("SCRAPER_SOURCE_RPS", "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            out = {}
            for k, v in parsed.items():
                try:
                    rate = float(v)
                except (TypeError, ValueError):
                    continue
                if rate > 0:
                    out[str(k).strip().lower()] = rate
            return out
    except json.JSONDecodeError:
        pass

    out: Dict[str, float] = {}
    for part in raw.split(","):
        token = part.strip()
        if not token or "=" not in token:
            continue
        name, value = token.split("=", 1)
        name = name.strip().lower()
        if not name:
            continue
        try:
            rate = float(value.strip())
        except ValueError:
            continue
        if rate > 0:
            out[name] = rate
    return out


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
    github_token: str = os.getenv("GITHUB_TOKEN", "")
    github_api_base_url: str = os.getenv("GITHUB_API_BASE_URL", "https://api.github.com")
    request_timeout_seconds: float = float(os.getenv("SCRAPER_TIMEOUT_SECONDS", "30"))
    concurrent_scrapers: int = int(os.getenv("CONCURRENT_SCRAPERS", "5"))
    coordination_backend: str = os.getenv("SCRAPER_COORDINATION_BACKEND", "memory").strip().lower()
    redis_url: str = os.getenv("SCRAPER_REDIS_URL", "redis://127.0.0.1:6379/0")
    redis_key_prefix: str = os.getenv("SCRAPER_REDIS_KEY_PREFIX", "trend_agent:scraper")
    redis_pop_timeout_seconds: float = float(os.getenv("SCRAPER_REDIS_POP_TIMEOUT_SECONDS", "1.0"))
    queue_max_size: int = int(os.getenv("SCRAPER_QUEUE_MAX_SIZE", "200"))
    queue_enqueue_timeout_seconds: float = float(os.getenv("SCRAPER_QUEUE_ENQUEUE_TIMEOUT_SECONDS", "1.0"))
    retry_max_attempts: int = int(os.getenv("SCRAPER_RETRY_MAX_ATTEMPTS", "3"))
    retry_base_delay_seconds: float = float(os.getenv("SCRAPER_RETRY_BASE_DELAY_SECONDS", "0.5"))
    circuit_breaker_failure_threshold: int = int(os.getenv("SCRAPER_CIRCUIT_BREAKER_FAILURE_THRESHOLD", "3"))
    circuit_breaker_open_seconds: float = float(os.getenv("SCRAPER_CIRCUIT_BREAKER_OPEN_SECONDS", "30"))
    source_rps: Dict[str, float] = field(default_factory=_load_source_rps)
    enabled_sources: List[str] = field(default_factory=lambda: [
        s.strip() for s in os.getenv(
            "SCRAPER_ENABLED_SOURCES", "twitter,youtube,weibo,bilibili,zhihu,github"
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
class MultiModalConfig:
    """多模态增强配置"""
    enabled: bool = os.getenv("MULTIMODAL_ENABLED", "false").lower() == "true"
    enrich_top_n: int = int(os.getenv("MULTIMODAL_ENRICH_TOP_N", "10"))
    max_media_per_item: int = int(os.getenv("MULTIMODAL_MAX_MEDIA_PER_ITEM", "2"))
    min_heat_score: float = float(os.getenv("MULTIMODAL_MIN_HEAT_SCORE", "0.35"))


@dataclass
class HeatScoreConfig:
    """热度评分配置"""
    weight_platform_percentile: float = float(os.getenv("HEAT_WEIGHT_PLATFORM_PERCENTILE", "0.45"))
    weight_velocity: float = float(os.getenv("HEAT_WEIGHT_VELOCITY", "0.25"))
    weight_freshness: float = float(os.getenv("HEAT_WEIGHT_FRESHNESS", "0.20"))
    weight_cross_platform: float = float(os.getenv("HEAT_WEIGHT_CROSS_PLATFORM", "0.10"))
    freshness_half_life_hours: float = float(os.getenv("HEAT_FRESHNESS_HALF_LIFE_HOURS", "24"))
    freshness_max_age_hours: float = float(os.getenv("HEAT_FRESHNESS_MAX_AGE_HOURS", "168"))
    platform_weights: Dict[str, float] = field(default_factory=_load_platform_weights)
    github_weight_star_velocity: float = float(os.getenv("HEAT_GITHUB_WEIGHT_STAR_VELOCITY", "0.45"))
    github_weight_contributor_activity: float = float(os.getenv("HEAT_GITHUB_WEIGHT_CONTRIBUTOR_ACTIVITY", "0.35"))
    github_weight_release_adoption: float = float(os.getenv("HEAT_GITHUB_WEIGHT_RELEASE_ADOPTION", "0.20"))
    github_star_velocity_norm_cap: float = float(os.getenv("HEAT_GITHUB_STAR_VELOCITY_NORM_CAP", "200"))
    github_contributor_activity_norm_cap: float = float(os.getenv("HEAT_GITHUB_CONTRIBUTOR_ACTIVITY_NORM_CAP", "400"))
    github_release_adoption_norm_cap: float = float(os.getenv("HEAT_GITHUB_RELEASE_ADOPTION_NORM_CAP", "50000"))
    github_boost_base: float = float(os.getenv("HEAT_GITHUB_BOOST_BASE", "0.75"))
    github_boost_range: float = float(os.getenv("HEAT_GITHUB_BOOST_RANGE", "0.50"))


@dataclass
class ParseConfig:
    """解析阶段配置"""
    enabled: bool = os.getenv("PARSE_ENABLED", "true").lower() == "true"
    schema_version: str = os.getenv("PARSE_SCHEMA_VERSION", "v1")
    backend: str = os.getenv("PARSE_BACKEND", "heuristic").strip().lower()
    cache_enabled: bool = os.getenv("PARSE_CACHE_ENABLED", "true").lower() == "true"
    max_attempts_per_run: int = int(os.getenv("PARSE_MAX_ATTEMPTS_PER_RUN", "2"))
    low_confidence_threshold: float = float(os.getenv("PARSE_LOW_CONFIDENCE_THRESHOLD", "0.65"))
    low_confidence_retry_attempts: int = int(os.getenv("PARSE_LOW_CONFIDENCE_RETRY_ATTEMPTS", "1"))
    low_confidence_manual_after_attempts: int = int(os.getenv("PARSE_LOW_CONFIDENCE_MANUAL_AFTER_ATTEMPTS", "3"))
    recoverable_max_attempts: int = int(os.getenv("PARSE_RECOVERABLE_MAX_ATTEMPTS", "5"))
    retry_base_delay_seconds: float = float(os.getenv("PARSE_RETRY_BASE_DELAY_SECONDS", "60"))
    retry_max_delay_seconds: float = float(os.getenv("PARSE_RETRY_MAX_DELAY_SECONDS", "1800"))
    batch_size: int = int(os.getenv("PARSE_BATCH_SIZE", "20"))


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
    multimodal: MultiModalConfig = field(default_factory=MultiModalConfig)
    heat_score: HeatScoreConfig = field(default_factory=HeatScoreConfig)
    parse: ParseConfig = field(default_factory=ParseConfig)
    auth: AuthConfig = field(default_factory=AuthConfig)
    orchestration: OrchestrationConfig = field(default_factory=OrchestrationConfig)


# 全局配置单例
settings = AppConfig()
