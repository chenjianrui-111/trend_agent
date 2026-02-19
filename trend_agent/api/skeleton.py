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
        },
        "video": {
            "default_provider": settings.video.default_provider,
            "fallback_enabled": settings.video.fallback_enabled,
        },
        "scheduler": {
            "enabled": settings.scheduler.enabled,
            "timezone": settings.scheduler.timezone,
        },
    }
