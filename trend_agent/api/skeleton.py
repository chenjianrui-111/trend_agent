"""API skeleton endpoints for quick bootstrap and capability introspection."""

from typing import Any, Dict

from fastapi import APIRouter

from trend_agent.config.settings import settings

router = APIRouter(prefix="/api/v1", tags=["system"])


@router.get("", summary="API index")
async def api_index() -> Dict[str, Any]:
    return {
        "name": "TrendAgent API",
        "app": settings.app_name,
        "env": settings.env,
        "docs": "/docs",
        "health": "/api/v1/health",
        "metrics": "/metrics",
        "modules": [
            "auth",
            "content",
            "pipeline",
            "publish",
            "video",
            "schedule",
            "parse",
            "dashboard",
        ],
    }


@router.get("/capabilities", summary="Runtime capability matrix")
async def capabilities() -> Dict[str, Any]:
    return {
        "orchestration": {
            "langgraph_required": settings.orchestration.langgraph_required,
            "checkpoint_auto_save": settings.orchestration.checkpoint_auto_save,
            "checkpoint_store": settings.orchestration.checkpoint_store,
        },
        "llm": {
            "primary_backend": settings.llm.primary_backend,
            "fallback_enabled": settings.llm.fallback_enabled,
            "fallback_backend": settings.llm.fallback_backend,
        },
        "scraper": {
            "enabled_sources": settings.scraper.enabled_sources,
            "concurrent_scrapers": settings.scraper.concurrent_scrapers,
            "timeout_seconds": settings.scraper.request_timeout_seconds,
            "coordination_backend": settings.scraper.coordination_backend,
            "redis_key_prefix": settings.scraper.redis_key_prefix,
            "queue_max_size": settings.scraper.queue_max_size,
            "retry_max_attempts": settings.scraper.retry_max_attempts,
            "circuit_breaker_failure_threshold": settings.scraper.circuit_breaker_failure_threshold,
            "circuit_breaker_open_seconds": settings.scraper.circuit_breaker_open_seconds,
            "source_rps": settings.scraper.source_rps,
        },
        "video": {
            "default_provider": settings.video.default_provider,
            "fallback_enabled": settings.video.fallback_enabled,
        },
        "multimodal": {
            "enabled": settings.multimodal.enabled,
            "enrich_top_n": settings.multimodal.enrich_top_n,
            "max_media_per_item": settings.multimodal.max_media_per_item,
        },
        "heat_score": {
            "weights": {
                "platform_percentile": settings.heat_score.weight_platform_percentile,
                "velocity": settings.heat_score.weight_velocity,
                "freshness": settings.heat_score.weight_freshness,
                "cross_platform": settings.heat_score.weight_cross_platform,
            },
            "github_weights": {
                "star_velocity": settings.heat_score.github_weight_star_velocity,
                "contributor_activity": settings.heat_score.github_weight_contributor_activity,
                "release_adoption": settings.heat_score.github_weight_release_adoption,
            },
            "github_boost": {
                "base": settings.heat_score.github_boost_base,
                "range": settings.heat_score.github_boost_range,
            },
            "freshness_half_life_hours": settings.heat_score.freshness_half_life_hours,
            "freshness_max_age_hours": settings.heat_score.freshness_max_age_hours,
            "platform_weights": settings.heat_score.platform_weights,
        },
        "parse": {
            "enabled": settings.parse.enabled,
            "schema_version": settings.parse.schema_version,
            "backend": settings.parse.backend,
            "cache_enabled": settings.parse.cache_enabled,
            "max_attempts_per_run": settings.parse.max_attempts_per_run,
            "low_confidence_threshold": settings.parse.low_confidence_threshold,
            "recoverable_max_attempts": settings.parse.recoverable_max_attempts,
        },
        "generation": {
            "stage_timeout_seconds": settings.generation.stage_timeout_seconds,
            "self_repair_max_attempts": settings.generation.self_repair_max_attempts,
            "min_quality_score": settings.generation.min_quality_score,
            "min_compliance_score": settings.generation.min_compliance_score,
            "max_repeat_ratio": settings.generation.max_repeat_ratio,
            "banned_words_count": len(settings.generation.banned_words),
        },
        "publish_gate": {
            "enabled": settings.publisher.gate_enabled,
            "min_quality_score": settings.publisher.gate_min_quality_score,
            "min_compliance_score": settings.publisher.gate_min_compliance_score,
            "max_repeat_ratio": settings.publisher.gate_max_repeat_ratio,
        },
        "scheduler": {
            "enabled": settings.scheduler.enabled,
            "timezone": settings.scheduler.timezone,
        },
    }
