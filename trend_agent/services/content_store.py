"""
内容存储仓库 - 异步 SQLAlchemy CRUD
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select, func, delete, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from trend_agent.config.settings import settings
from trend_agent.models.db import (
    Base, TrendSource, CategorizedContent, ContentDraft,
    PublishRecord, PipelineRun, ScheduleConfig,
)

logger = logging.getLogger(__name__)


class ContentRepository:
    """异步内容存储仓库"""

    def __init__(self, db_url: Optional[str] = None):
        self._engine = create_async_engine(
            db_url or settings.database.url,
            echo=settings.database.echo,
        )
        self._session_factory = async_sessionmaker(
            self._engine, class_=AsyncSession, expire_on_commit=False,
        )

    async def init_db(self):
        """创建所有表"""
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables initialized")

    async def close(self):
        await self._engine.dispose()

    # --- TrendSource ---

    async def upsert_source(self, data: Dict[str, Any]) -> str:
        async with self._session_factory() as session:
            # Check existing
            stmt = select(TrendSource).where(
                TrendSource.source_platform == data["source_platform"],
                TrendSource.source_id == data["source_id"],
            )
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()
            if existing:
                for key, value in data.items():
                    if hasattr(existing, key) and key not in ("id",):
                        setattr(existing, key, value)
                await session.commit()
                return existing.id
            else:
                source = TrendSource(**data)
                session.add(source)
                await session.commit()
                return source.id

    async def list_sources(
        self,
        platform: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict]:
        async with self._session_factory() as session:
            stmt = select(TrendSource).order_by(TrendSource.scraped_at.desc())
            if platform:
                stmt = stmt.where(TrendSource.source_platform == platform)
            stmt = stmt.offset(offset).limit(limit)
            result = await session.execute(stmt)
            rows = result.scalars().all()
            return [self._row_to_dict(r) for r in rows]

    # --- CategorizedContent ---

    async def save_categorized(self, data: Dict[str, Any]) -> str:
        async with self._session_factory() as session:
            record = CategorizedContent(**data)
            session.add(record)
            await session.commit()
            return record.id

    # --- ContentDraft ---

    async def save_draft(self, data: Dict[str, Any]) -> str:
        async with self._session_factory() as session:
            draft = ContentDraft(**data)
            session.add(draft)
            await session.commit()
            return draft.id

    async def update_draft(self, draft_id: str, updates: Dict[str, Any]):
        async with self._session_factory() as session:
            stmt = update(ContentDraft).where(ContentDraft.id == draft_id).values(**updates)
            await session.execute(stmt)
            await session.commit()

    async def get_draft(self, draft_id: str) -> Optional[Dict]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(ContentDraft).where(ContentDraft.id == draft_id)
            )
            row = result.scalar_one_or_none()
            return self._row_to_dict(row) if row else None

    async def list_drafts(
        self,
        status: Optional[str] = None,
        platform: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict]:
        async with self._session_factory() as session:
            stmt = select(ContentDraft).order_by(ContentDraft.created_at.desc())
            if status:
                stmt = stmt.where(ContentDraft.status == status)
            if platform:
                stmt = stmt.where(ContentDraft.target_platform == platform)
            stmt = stmt.offset(offset).limit(limit)
            result = await session.execute(stmt)
            return [self._row_to_dict(r) for r in result.scalars().all()]

    async def delete_draft(self, draft_id: str):
        async with self._session_factory() as session:
            await session.execute(delete(ContentDraft).where(ContentDraft.id == draft_id))
            await session.commit()

    # --- PublishRecord ---

    async def save_publish_record(self, data: Dict[str, Any]) -> str:
        async with self._session_factory() as session:
            record = PublishRecord(**data)
            session.add(record)
            await session.commit()
            return record.id

    async def list_publish_records(self, limit: int = 50, offset: int = 0) -> List[Dict]:
        async with self._session_factory() as session:
            stmt = select(PublishRecord).order_by(
                PublishRecord.published_at.desc().nulls_last()
            ).offset(offset).limit(limit)
            result = await session.execute(stmt)
            return [self._row_to_dict(r) for r in result.scalars().all()]

    # --- PipelineRun ---

    async def create_pipeline_run(self, data: Dict[str, Any]) -> str:
        async with self._session_factory() as session:
            run = PipelineRun(**data)
            session.add(run)
            await session.commit()
            return run.id

    async def update_pipeline_run(self, run_id: str, updates: Dict[str, Any]):
        async with self._session_factory() as session:
            stmt = update(PipelineRun).where(PipelineRun.id == run_id).values(**updates)
            await session.execute(stmt)
            await session.commit()

    async def get_pipeline_run(self, run_id: str) -> Optional[Dict]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(PipelineRun).where(PipelineRun.id == run_id)
            )
            row = result.scalar_one_or_none()
            return self._row_to_dict(row) if row else None

    async def list_pipeline_runs(self, limit: int = 20, offset: int = 0) -> List[Dict]:
        async with self._session_factory() as session:
            stmt = select(PipelineRun).order_by(
                PipelineRun.started_at.desc()
            ).offset(offset).limit(limit)
            result = await session.execute(stmt)
            return [self._row_to_dict(r) for r in result.scalars().all()]

    # --- ScheduleConfig ---

    async def list_schedules(self, enabled: Optional[bool] = None) -> List[Dict]:
        async with self._session_factory() as session:
            stmt = select(ScheduleConfig)
            if enabled is not None:
                stmt = stmt.where(ScheduleConfig.enabled == enabled)
            result = await session.execute(stmt)
            return [self._row_to_dict(r) for r in result.scalars().all()]

    async def save_schedule(self, data: Dict[str, Any]) -> str:
        async with self._session_factory() as session:
            schedule = ScheduleConfig(**data)
            session.add(schedule)
            await session.commit()
            return schedule.id

    async def update_schedule(self, schedule_id: str, updates: Dict[str, Any]):
        async with self._session_factory() as session:
            stmt = update(ScheduleConfig).where(ScheduleConfig.id == schedule_id).values(**updates)
            await session.execute(stmt)
            await session.commit()

    async def delete_schedule(self, schedule_id: str):
        async with self._session_factory() as session:
            await session.execute(delete(ScheduleConfig).where(ScheduleConfig.id == schedule_id))
            await session.commit()

    # --- Dashboard Stats ---

    async def get_stats(self) -> Dict:
        async with self._session_factory() as session:
            sources_count = (await session.execute(select(func.count(TrendSource.id)))).scalar() or 0
            drafts_count = (await session.execute(select(func.count(ContentDraft.id)))).scalar() or 0
            published_count = (await session.execute(
                select(func.count(PublishRecord.id)).where(PublishRecord.status == "success")
            )).scalar() or 0
            pipeline_count = (await session.execute(select(func.count(PipelineRun.id)))).scalar() or 0
            return {
                "total_sources": sources_count,
                "total_drafts": drafts_count,
                "total_published": published_count,
                "total_pipeline_runs": pipeline_count,
            }

    async def get_category_distribution(self) -> List[Dict]:
        async with self._session_factory() as session:
            stmt = select(
                CategorizedContent.category,
                func.count(CategorizedContent.id).label("count"),
            ).group_by(CategorizedContent.category)
            result = await session.execute(stmt)
            return [{"category": row[0], "count": row[1]} for row in result.all()]

    @staticmethod
    def _row_to_dict(row) -> Dict:
        if row is None:
            return {}
        d = {}
        for col in row.__table__.columns:
            val = getattr(row, col.name)
            if isinstance(val, datetime):
                val = val.isoformat()
            d[col.name] = val
        return d
