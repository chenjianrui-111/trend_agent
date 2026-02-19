"""
定时调度服务 - APScheduler 管理
"""

import logging
from typing import Optional

from trend_agent.config.settings import settings

logger = logging.getLogger(__name__)

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger
    SCHEDULER_AVAILABLE = True
except ImportError:
    SCHEDULER_AVAILABLE = False
    logger.info("APScheduler not installed, scheduling disabled")


class PipelineScheduler:
    """定时调度管理器"""

    def __init__(self):
        self._scheduler: Optional["AsyncIOScheduler"] = None
        self._orchestrator = None
        self._content_store = None

    async def start(self, orchestrator, content_store):
        """启动调度器并加载数据库中的调度配置"""
        if not SCHEDULER_AVAILABLE or not settings.scheduler.enabled:
            logger.info("Scheduler disabled")
            return

        self._orchestrator = orchestrator
        self._content_store = content_store
        self._scheduler = AsyncIOScheduler(timezone=settings.scheduler.timezone)

        # Load schedules from DB
        configs = await content_store.list_schedules(enabled=True)
        for cfg in configs:
            self._add_job(cfg)

        self._scheduler.start()
        logger.info("Pipeline scheduler started with %d jobs", len(configs))

    def _add_job(self, cfg: dict):
        if not self._scheduler:
            return
        try:
            self._scheduler.add_job(
                self._run_pipeline,
                CronTrigger.from_crontab(cfg["cron_expression"]),
                id=cfg["id"],
                name=cfg.get("name", cfg["id"]),
                kwargs={"config": cfg},
                misfire_grace_time=settings.scheduler.misfire_grace_time,
                replace_existing=True,
            )
            logger.info("Added schedule job: %s (%s)", cfg.get("name"), cfg["cron_expression"])
        except Exception as e:
            logger.error("Failed to add schedule job %s: %s", cfg.get("name"), e)

    async def _run_pipeline(self, config: dict):
        """Execute the full pipeline for a scheduled job."""
        if not self._orchestrator:
            return
        try:
            logger.info("Scheduled pipeline starting: %s", config.get("name"))
            await self._orchestrator.run_pipeline(
                sources=config.get("sources", ["twitter", "youtube"]),
                categories_filter=config.get("categories", []),
                target_platforms=config.get("target_platforms", ["wechat"]),
                generate_video=config.get("generate_video", False),
                video_provider=config.get("video_provider", ""),
                trigger_type="cron",
            )
        except Exception as e:
            logger.error("Scheduled pipeline failed: %s", e, exc_info=True)

    def add_schedule(self, cfg: dict):
        """Dynamically add a new schedule."""
        self._add_job(cfg)

    def remove_schedule(self, schedule_id: str):
        """Remove a schedule."""
        if self._scheduler:
            try:
                self._scheduler.remove_job(schedule_id)
            except Exception:
                pass

    def list_jobs(self) -> list:
        if not self._scheduler:
            return []
        return [
            {"id": job.id, "name": job.name, "next_run": str(job.next_run_time)}
            for job in self._scheduler.get_jobs()
        ]

    async def stop(self):
        if self._scheduler:
            self._scheduler.shutdown(wait=False)
            self._scheduler = None
