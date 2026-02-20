"""
API 层 - FastAPI 应用

TrendAgent 热门信息聚合与自动发稿系统
"""

import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional, Literal

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from trend_agent.api.auth import (
    AuthContext, authenticate_user, get_auth_context,
    issue_access_token, register_user,
)
from trend_agent.config.settings import settings
from trend_agent.api.skeleton import router as skeleton_router
from trend_agent.observability import metrics as obs
from trend_agent.services.content_store import ContentRepository
from trend_agent.services.llm_client import LLMServiceClient
from trend_agent.services.parse_service import ParseService
from trend_agent.services.scheduler import PipelineScheduler
from trend_agent.agents.orchestrator import get_orchestrator

logger = logging.getLogger(__name__)

# Global singletons
content_store = ContentRepository()
llm_client = LLMServiceClient()
parse_service = ParseService(content_store=content_store, llm_client=llm_client)
orchestrator = get_orchestrator()
pipeline_scheduler = PipelineScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("TrendAgent starting up")
    await content_store.init_db()
    await orchestrator.startup()
    await pipeline_scheduler.start(orchestrator=orchestrator, content_store=content_store)
    obs.set_app_info(settings.app_name, app.version, settings.env)
    yield
    logger.info("TrendAgent shutting down")
    await pipeline_scheduler.stop()
    await orchestrator.shutdown()
    await llm_client.close()
    await content_store.close()


app = FastAPI(
    title="TrendAgent API",
    description="热门信息聚合与跨平台自动发稿系统",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

WEB_DIR = Path(__file__).resolve().parents[1] / "web"
if WEB_DIR.exists():
    app.mount("/web", StaticFiles(directory=str(WEB_DIR)), name="web")

app.include_router(skeleton_router)


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    route = request.scope.get("route")
    path = getattr(route, "path", request.url.path)
    method = request.method
    status_code = 500
    start = time.perf_counter()
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        if path != "/metrics":
            obs.observe_http_request(method, path, status_code, time.perf_counter() - start)


# ===================================================================
# Request / Response Models
# ===================================================================

class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=6, max_length=128)
    tenant_id: str = Field(default="default")
    role: str = Field(default="user")


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=3)
    password: str = Field(..., min_length=6)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 86400
    username: str = ""
    tenant_id: str = ""
    role: str = "user"


class PipelineRunRequest(BaseModel):
    sources: List[str] = Field(default_factory=lambda: ["twitter", "youtube"])
    query: str = ""
    categories_filter: List[str] = Field(default_factory=list)
    target_platforms: List[str] = Field(default_factory=lambda: ["wechat", "xiaohongshu"])
    capture_mode: Literal["by_time", "by_hot", "hybrid"] = "hybrid"
    sort_strategy: Literal["engagement", "recency", "hybrid"] = "hybrid"
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    generate_video: bool = False
    video_provider: str = ""
    max_items: int = 50


class ContentUpdateRequest(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    summary: Optional[str] = None
    hashtags: Optional[List[str]] = None
    status: Optional[str] = None


class PublishRequest(BaseModel):
    draft_ids: List[str] = Field(..., min_length=1)
    platforms: List[str] = Field(default_factory=lambda: ["wechat"])


class ScheduleCreateRequest(BaseModel):
    name: str = Field(..., min_length=1)
    cron_expression: str = Field(..., min_length=5)
    sources: List[str] = Field(default_factory=lambda: ["twitter", "youtube"])
    query: str = ""
    categories: List[str] = Field(default_factory=list)
    target_platforms: List[str] = Field(default_factory=lambda: ["wechat"])
    capture_mode: Literal["by_time", "by_hot", "hybrid"] = "hybrid"
    sort_strategy: Literal["engagement", "recency", "hybrid"] = "hybrid"
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    generate_video: bool = False
    video_provider: str = ""


class ScheduleUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1)
    cron_expression: Optional[str] = Field(default=None, min_length=5)
    sources: Optional[List[str]] = None
    query: Optional[str] = None
    categories: Optional[List[str]] = None
    target_platforms: Optional[List[str]] = None
    capture_mode: Optional[Literal["by_time", "by_hot", "hybrid"]] = None
    sort_strategy: Optional[Literal["engagement", "recency", "hybrid"]] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    generate_video: Optional[bool] = None
    video_provider: Optional[str] = None
    enabled: Optional[bool] = None


class VideoGenerateRequest(BaseModel):
    draft_id: str
    provider: str = ""


class ParseRunRequest(BaseModel):
    limit: int = Field(default=20, ge=1, le=200)
    platform: Optional[str] = None
    parse_statuses: List[str] = Field(default_factory=lambda: ["pending", "delayed"])
    force: bool = False


# ===================================================================
# Auth Endpoints
# ===================================================================

@app.get("/", include_in_schema=False)
async def frontend_home():
    if not WEB_DIR.exists():
        raise HTTPException(status_code=404, detail="frontend not found")
    return FileResponse(WEB_DIR / "index.html")


@app.post("/api/v1/auth/register")
async def auth_register(req: RegisterRequest):
    if not settings.auth.registration_enabled:
        raise HTTPException(status_code=403, detail="Registration disabled")
    ok, msg = register_user(req.username, req.password, req.tenant_id, req.role)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"message": "Registration successful"}


@app.post("/api/v1/auth/login", response_model=LoginResponse)
async def auth_login(req: LoginRequest):
    user = authenticate_user(req.username, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = issue_access_token(
        username=user["username"],
        tenant_id=user["tenant_id"],
        role=user["role"],
        expires_in_seconds=settings.auth.token_expires_seconds,
    )
    return LoginResponse(
        access_token=token,
        expires_in=settings.auth.token_expires_seconds,
        username=user["username"],
        tenant_id=user["tenant_id"],
        role=user["role"],
    )


# ===================================================================
# Content Endpoints
# ===================================================================

@app.get("/api/v1/content")
async def list_content(
    status: Optional[str] = None,
    platform: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    auth: AuthContext = Depends(get_auth_context),
):
    return await content_store.list_drafts(status=status, platform=platform, limit=limit, offset=offset)


@app.get("/api/v1/content/{draft_id}")
async def get_content(draft_id: str, auth: AuthContext = Depends(get_auth_context)):
    draft = await content_store.get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Content not found")
    return draft


@app.get("/api/v1/content/{draft_id}/versions")
async def list_content_versions(
    draft_id: str,
    limit: int = 50,
    offset: int = 0,
    auth: AuthContext = Depends(get_auth_context),
):
    return await content_store.list_draft_versions(draft_id=draft_id, limit=limit, offset=offset)


@app.post("/api/v1/content/{draft_id}/versions/{version_no}/rollback")
async def rollback_content_version(
    draft_id: str,
    version_no: int,
    auth: AuthContext = Depends(get_auth_context),
):
    ok = await content_store.rollback_draft_to_version(draft_id=draft_id, version_no=version_no)
    if not ok:
        raise HTTPException(status_code=404, detail="Draft or version not found")
    return {"success": True, "draft_id": draft_id, "version_no": version_no}


@app.put("/api/v1/content/{draft_id}")
async def update_content(
    draft_id: str,
    req: ContentUpdateRequest,
    auth: AuthContext = Depends(get_auth_context),
):
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No updates provided")
    await content_store.update_draft(draft_id, updates)
    return {"success": True, "draft_id": draft_id}


@app.delete("/api/v1/content/{draft_id}")
async def delete_content(draft_id: str, auth: AuthContext = Depends(get_auth_context)):
    await content_store.delete_draft(draft_id)
    return {"success": True, "draft_id": draft_id}


@app.get("/api/v1/content/categories/stats")
async def category_stats(auth: AuthContext = Depends(get_auth_context)):
    return await content_store.get_category_distribution()


@app.get("/api/v1/sources")
async def list_sources(
    platform: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    auth: AuthContext = Depends(get_auth_context),
):
    return await content_store.list_sources(platform=platform, limit=limit, offset=offset)


@app.post("/api/v1/parse/run")
async def run_parse(
    req: ParseRunRequest,
    auth: AuthContext = Depends(get_auth_context),
):
    return await parse_service.parse_pending_sources(
        limit=req.limit,
        platform=req.platform,
        parse_statuses=req.parse_statuses,
        force=req.force,
    )


@app.get("/api/v1/parse/dlq")
async def list_parse_dlq(
    status: Optional[str] = "pending",
    limit: int = 50,
    offset: int = 0,
    auth: AuthContext = Depends(get_auth_context),
):
    return await content_store.list_parse_dead_letters(status=status, limit=limit, offset=offset)


@app.post("/api/v1/parse/dlq/{dlq_id}/replay")
async def replay_parse_dlq(
    dlq_id: str,
    auth: AuthContext = Depends(get_auth_context),
):
    row = await content_store.get_parse_dead_letter(dlq_id)
    if not row:
        raise HTTPException(status_code=404, detail="DLQ record not found")
    result = await parse_service.replay_dead_letter(dlq_id)
    return {"success": True, "dlq_id": dlq_id, "result": result}


# ===================================================================
# Pipeline Endpoints (stubs - implemented in Phase 4)
# ===================================================================

@app.post("/api/v1/pipeline/run")
async def run_pipeline(req: PipelineRunRequest, auth: AuthContext = Depends(get_auth_context)):
    """Trigger the full scrape -> categorize -> summarize -> publish pipeline."""
    run_id = await orchestrator.run_pipeline(
        sources=req.sources,
        query=req.query,
        categories_filter=req.categories_filter,
        target_platforms=req.target_platforms,
        capture_mode=req.capture_mode,
        start_time=req.start_time or "",
        end_time=req.end_time or "",
        sort_strategy=req.sort_strategy,
        generate_video=req.generate_video,
        video_provider=req.video_provider,
        max_items=req.max_items,
        trigger_type="manual",
    )
    return {"success": True, "pipeline_run_id": run_id}


@app.get("/api/v1/pipeline/runs")
async def list_pipeline_runs(
    limit: int = 20, offset: int = 0,
    auth: AuthContext = Depends(get_auth_context),
):
    return await content_store.list_pipeline_runs(limit=limit, offset=offset)


@app.get("/api/v1/pipeline/runs/{run_id}")
async def get_pipeline_run(run_id: str, auth: AuthContext = Depends(get_auth_context)):
    run = await content_store.get_pipeline_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Pipeline run not found")
    return run


# ===================================================================
# Publish Endpoints (stubs - implemented in Phase 5)
# ===================================================================

@app.post("/api/v1/publish")
async def publish_content(req: PublishRequest, auth: AuthContext = Depends(get_auth_context)):
    """Publish specific drafts to platforms."""
    return {"message": "Publishing initiated", "draft_ids": req.draft_ids, "platforms": req.platforms}


@app.get("/api/v1/publish/history")
async def publish_history(
    limit: int = 50, offset: int = 0,
    auth: AuthContext = Depends(get_auth_context),
):
    return await content_store.list_publish_records(limit=limit, offset=offset)


# ===================================================================
# Schedule Endpoints (stubs - implemented in Phase 7)
# ===================================================================

@app.get("/api/v1/schedules")
async def list_schedules(auth: AuthContext = Depends(get_auth_context)):
    return await content_store.list_schedules()


@app.post("/api/v1/schedules")
async def create_schedule(req: ScheduleCreateRequest, auth: AuthContext = Depends(get_auth_context)):
    payload = req.model_dump()
    schedule_id = await content_store.save_schedule(payload)
    pipeline_scheduler.add_schedule({"id": schedule_id, **payload})
    return {"success": True, "schedule_id": schedule_id}


@app.put("/api/v1/schedules/{schedule_id}")
async def update_schedule(
    schedule_id: str,
    req: ScheduleUpdateRequest,
    auth: AuthContext = Depends(get_auth_context),
):
    existing = await content_store.get_schedule(schedule_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Schedule not found")

    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No updates provided")

    await content_store.update_schedule(schedule_id, updates)
    refreshed = await content_store.get_schedule(schedule_id)
    if not refreshed:
        raise HTTPException(status_code=404, detail="Schedule not found after update")

    pipeline_scheduler.remove_schedule(schedule_id)
    if refreshed.get("enabled", True):
        pipeline_scheduler.add_schedule(refreshed)

    return {"success": True, "schedule_id": schedule_id, "schedule": refreshed}


@app.patch("/api/v1/schedules/{schedule_id}/enable")
async def toggle_schedule_enable(
    schedule_id: str,
    auth: AuthContext = Depends(get_auth_context),
):
    existing = await content_store.get_schedule(schedule_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Schedule not found")

    target_enabled = not bool(existing.get("enabled", True))
    await content_store.update_schedule(schedule_id, {"enabled": target_enabled})
    refreshed = await content_store.get_schedule(schedule_id)
    if not refreshed:
        raise HTTPException(status_code=404, detail="Schedule not found after update")

    pipeline_scheduler.remove_schedule(schedule_id)
    if refreshed.get("enabled", True):
        pipeline_scheduler.add_schedule(refreshed)

    return {
        "success": True,
        "schedule_id": schedule_id,
        "enabled": bool(refreshed.get("enabled", False)),
    }


@app.delete("/api/v1/schedules/{schedule_id}")
async def delete_schedule(schedule_id: str, auth: AuthContext = Depends(get_auth_context)):
    await content_store.delete_schedule(schedule_id)
    pipeline_scheduler.remove_schedule(schedule_id)
    return {"success": True}


# ===================================================================
# Video Endpoints (stubs - implemented in Phase 6)
# ===================================================================

@app.post("/api/v1/video/generate")
async def generate_video(req: VideoGenerateRequest, auth: AuthContext = Depends(get_auth_context)):
    return {"message": "Video generation initiated", "draft_id": req.draft_id}


# ===================================================================
# Dashboard & System Endpoints
# ===================================================================

@app.get("/api/v1/dashboard/stats")
async def dashboard_stats(auth: AuthContext = Depends(get_auth_context)):
    return await content_store.get_stats()


@app.get("/api/v1/health")
async def health_check():
    llm_health = await llm_client.health_check()
    return {
        "status": "healthy",
        "app": settings.app_name,
        "env": settings.env,
        "llm": llm_health,
    }


@app.get("/metrics")
async def prometheus_metrics():
    try:
        from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
        from fastapi.responses import Response
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
    except ImportError:
        raise HTTPException(status_code=501, detail="prometheus_client not installed")
