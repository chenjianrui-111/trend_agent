"""
内容存储仓库 - 异步 SQLAlchemy CRUD
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select, func, delete, update, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from trend_agent.config.settings import settings
from trend_agent.models.db import (
    Base, TrendSource, CategorizedContent, ContentDraft,
    PublishRecord, PipelineRun, ScheduleConfig, SourceIngestRecord, ScraperState,
    ParseCache, ParseDeadLetter,
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
            await conn.run_sync(self._migrate_schema)
        logger.info("Database tables initialized")

    @staticmethod
    def _migrate_schema(sync_conn):
        """
        Lightweight schema migration for incremental fields without Alembic.
        """
        insp = inspect(sync_conn)

        if insp.has_table("schedule_configs"):
            existing = {c["name"] for c in insp.get_columns("schedule_configs")}
            # SQLite/Postgres compatible simple ADD COLUMN statements.
            schedule_migrations = [
                ("query", "VARCHAR(256) DEFAULT ''"),
                ("capture_mode", "VARCHAR(16) DEFAULT 'hybrid'"),
                ("sort_strategy", "VARCHAR(16) DEFAULT 'hybrid'"),
                ("start_time", "VARCHAR(64) DEFAULT ''"),
                ("end_time", "VARCHAR(64) DEFAULT ''"),
            ]
            for col_name, col_sql in schedule_migrations:
                if col_name not in existing:
                    sync_conn.execute(
                        text(f"ALTER TABLE schedule_configs ADD COLUMN {col_name} {col_sql}")
                    )

        if insp.has_table("trend_sources"):
            existing = {c["name"] for c in insp.get_columns("trend_sources")}
            source_migrations = [
                ("source_channel", "VARCHAR(64) DEFAULT ''"),
                ("source_type", "VARCHAR(32) DEFAULT ''"),
                ("normalized_heat_score", "FLOAT DEFAULT 0"),
                ("heat_breakdown", "JSON"),
                ("capture_mode", "VARCHAR(16) DEFAULT 'hybrid'"),
                ("sort_strategy", "VARCHAR(16) DEFAULT 'hybrid'"),
                ("published_at", "DATETIME"),
                ("source_updated_at", "DATETIME"),
                ("normalized_text", "TEXT DEFAULT ''"),
                ("hashtags", "JSON"),
                ("mentions", "JSON"),
                ("external_urls", "JSON"),
                ("media_urls", "JSON"),
                ("media_assets", "JSON"),
                ("multimodal", "JSON"),
                ("platform_metrics", "JSON"),
                ("parse_status", "VARCHAR(16) DEFAULT 'pending'"),
                ("parse_payload", "JSON"),
                ("parse_schema_version", "VARCHAR(16) DEFAULT ''"),
                ("parse_confidence", "FLOAT DEFAULT 0"),
                ("parse_attempts", "INTEGER DEFAULT 0"),
                ("parse_error_kind", "VARCHAR(16) DEFAULT ''"),
                ("parse_last_error", "TEXT DEFAULT ''"),
                ("parse_retry_at", "DATETIME"),
                ("parsed_at", "DATETIME"),
                ("pipeline_run_id", "VARCHAR(64) DEFAULT ''"),
                ("last_seen_at", "DATETIME"),
            ]
            for col_name, col_sql in source_migrations:
                if col_name not in existing:
                    sync_conn.execute(
                        text(f"ALTER TABLE trend_sources ADD COLUMN {col_name} {col_sql}")
                    )

    async def close(self):
        await self._engine.dispose()

    # --- TrendSource ---

    async def upsert_source(self, data: Dict[str, Any]) -> str:
        payload = self._normalize_source_payload(data)
        orm_payload = {k: v for k, v in payload.items() if k != "idempotency_key"}

        if payload.get("source_updated_at") is not None:
            accepted = await self._register_ingest_event(payload)
            if not accepted:
                async with self._session_factory() as session:
                    result = await session.execute(
                        select(TrendSource.id).where(
                            TrendSource.source_platform == payload["source_platform"],
                            TrendSource.source_id == payload["source_id"],
                        )
                    )
                    existing_id = result.scalar_one_or_none()
                    return existing_id or ""

        async with self._session_factory() as session:
            # Check existing
            stmt = select(TrendSource).where(
                TrendSource.source_platform == orm_payload["source_platform"],
                TrendSource.source_id == orm_payload["source_id"],
            )
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()
            if existing:
                for key, value in orm_payload.items():
                    if hasattr(existing, key) and key not in ("id",):
                        setattr(existing, key, value)
                await session.commit()
                return existing.id
            else:
                source = TrendSource(**orm_payload)
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

    async def get_source(self, source_row_id: str) -> Optional[Dict]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(TrendSource).where(TrendSource.id == source_row_id)
            )
            row = result.scalar_one_or_none()
            return self._row_to_dict(row) if row else None

    async def list_sources_for_parsing(
        self,
        limit: int = 100,
        platform: Optional[str] = None,
        parse_status: str = "pending",
        parse_statuses: Optional[List[str]] = None,
        due_before: Optional[datetime] = None,
    ) -> List[Dict]:
        async with self._session_factory() as session:
            statuses = [s for s in (parse_statuses or [parse_status]) if s]
            if statuses:
                stmt = select(TrendSource).where(TrendSource.parse_status.in_(statuses))
            else:
                stmt = select(TrendSource)
            if platform:
                stmt = stmt.where(TrendSource.source_platform == platform)
            if due_before:
                # pending/manual_review are immediately eligible, delayed/retry rely on parse_retry_at.
                stmt = stmt.where(
                    (TrendSource.parse_retry_at.is_(None)) | (TrendSource.parse_retry_at <= due_before)
                )
            stmt = stmt.order_by(
                TrendSource.normalized_heat_score.desc(),
                TrendSource.published_at.desc(),
                TrendSource.scraped_at.desc(),
            ).limit(limit)
            result = await session.execute(stmt)
            return [self._row_to_dict(r) for r in result.scalars().all()]

    async def mark_source_parsed(
        self,
        source_row_id: str,
        parse_payload: Optional[Dict[str, Any]] = None,
        parse_status: str = "parsed",
    ) -> None:
        async with self._session_factory() as session:
            stmt = (
                update(TrendSource)
                .where(TrendSource.id == source_row_id)
                .values(
                    parse_status=parse_status,
                    parse_payload=parse_payload or {},
                    parsed_at=datetime.now(timezone.utc),
                )
            )
            await session.execute(stmt)
            await session.commit()

    async def update_source_parse_state(
        self,
        source_row_id: str,
        *,
        parse_status: str,
        parse_payload: Optional[Dict[str, Any]] = None,
        parse_schema_version: str = "",
        parse_confidence: Optional[float] = None,
        parse_attempts: Optional[int] = None,
        parse_error_kind: str = "",
        parse_last_error: str = "",
        parse_retry_at: Optional[datetime] = None,
        parsed_at: Optional[datetime] = None,
    ) -> None:
        updates: Dict[str, Any] = {
            "parse_status": parse_status,
            "parse_schema_version": parse_schema_version,
            "parse_error_kind": parse_error_kind,
            "parse_last_error": parse_last_error,
            "parse_retry_at": parse_retry_at,
        }
        if parse_payload is not None:
            updates["parse_payload"] = parse_payload
        if parse_confidence is not None:
            updates["parse_confidence"] = float(parse_confidence)
        if parse_attempts is not None:
            updates["parse_attempts"] = int(parse_attempts)
        if parsed_at is not None:
            updates["parsed_at"] = parsed_at
        elif parse_status == "parsed":
            updates["parsed_at"] = datetime.now(timezone.utc)

        async with self._session_factory() as session:
            stmt = (
                update(TrendSource)
                .where(TrendSource.id == source_row_id)
                .values(**updates)
            )
            await session.execute(stmt)
            await session.commit()

    async def _register_ingest_event(self, payload: Dict[str, Any]) -> bool:
        key = str(payload.get("idempotency_key") or "").strip()
        if not key:
            return True
        async with self._session_factory() as session:
            record = SourceIngestRecord(
                source_platform=payload["source_platform"],
                source_id=payload["source_id"],
                source_updated_at=payload.get("source_updated_at"),
                idempotency_key=key,
            )
            session.add(record)
            try:
                await session.commit()
                return True
            except IntegrityError:
                await session.rollback()
                return False

    # --- ScraperState ---

    async def get_scraper_state(self, source: str) -> Dict[str, Any]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(ScraperState).where(ScraperState.source == source)
            )
            row = result.scalar_one_or_none()
            if not row:
                return {}
            state = row.state if isinstance(row.state, dict) else {}
            return dict(state)

    async def upsert_scraper_state(self, source: str, state: Dict[str, Any]) -> None:
        payload = state if isinstance(state, dict) else {}
        async with self._session_factory() as session:
            result = await session.execute(
                select(ScraperState).where(ScraperState.source == source)
            )
            existing = result.scalar_one_or_none()
            if existing:
                existing.state = payload
                existing.updated_at = datetime.now(timezone.utc)
            else:
                session.add(ScraperState(source=source, state=payload))
            await session.commit()

    # --- Parse Cache ---

    async def get_parse_cache(self, content_hash: str, schema_version: str) -> Optional[Dict[str, Any]]:
        if not content_hash or not schema_version:
            return None
        async with self._session_factory() as session:
            result = await session.execute(
                select(ParseCache).where(
                    ParseCache.content_hash == content_hash,
                    ParseCache.schema_version == schema_version,
                )
            )
            row = result.scalar_one_or_none()
            if not row:
                return None
            row.hit_count = int(row.hit_count or 0) + 1
            row.updated_at = datetime.now(timezone.utc)
            await session.commit()
            return self._row_to_dict(row)

    async def upsert_parse_cache(
        self,
        *,
        content_hash: str,
        schema_version: str,
        parse_payload: Dict[str, Any],
        parse_confidence: float,
    ) -> None:
        if not content_hash or not schema_version:
            return
        payload = parse_payload if isinstance(parse_payload, dict) else {}
        async with self._session_factory() as session:
            result = await session.execute(
                select(ParseCache).where(
                    ParseCache.content_hash == content_hash,
                    ParseCache.schema_version == schema_version,
                )
            )
            existing = result.scalar_one_or_none()
            if existing:
                existing.parse_payload = payload
                existing.parse_confidence = float(parse_confidence)
                existing.updated_at = datetime.now(timezone.utc)
            else:
                session.add(
                    ParseCache(
                        content_hash=content_hash,
                        schema_version=schema_version,
                        parse_payload=payload,
                        parse_confidence=float(parse_confidence),
                    )
                )
            await session.commit()

    # --- Parse DLQ ---

    async def create_parse_dead_letter(self, data: Dict[str, Any]) -> str:
        payload = dict(data)
        async with self._session_factory() as session:
            row = ParseDeadLetter(
                source_row_id=str(payload.get("source_row_id") or ""),
                source_platform=str(payload.get("source_platform") or ""),
                source_id=str(payload.get("source_id") or ""),
                content_hash=str(payload.get("content_hash") or ""),
                schema_version=str(payload.get("schema_version") or ""),
                error_kind=str(payload.get("error_kind") or ""),
                error_code=str(payload.get("error_code") or ""),
                error_message=str(payload.get("error_message") or ""),
                retryable=bool(payload.get("retryable") or False),
                attempts=int(payload.get("attempts") or 0),
                status=str(payload.get("status") or "pending"),
                payload_snapshot=payload.get("payload_snapshot") if isinstance(payload.get("payload_snapshot"), dict) else {},
            )
            session.add(row)
            await session.commit()
            return row.id

    async def get_parse_dead_letter(self, dlq_id: str) -> Optional[Dict[str, Any]]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(ParseDeadLetter).where(ParseDeadLetter.id == dlq_id)
            )
            row = result.scalar_one_or_none()
            return self._row_to_dict(row) if row else None

    async def list_parse_dead_letters(
        self,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        async with self._session_factory() as session:
            stmt = select(ParseDeadLetter).order_by(ParseDeadLetter.created_at.desc())
            if status:
                stmt = stmt.where(ParseDeadLetter.status == status)
            stmt = stmt.offset(offset).limit(limit)
            result = await session.execute(stmt)
            return [self._row_to_dict(r) for r in result.scalars().all()]

    async def update_parse_dead_letter(self, dlq_id: str, updates: Dict[str, Any]) -> None:
        payload = {k: v for k, v in updates.items() if k in {"status", "error_message", "replayed_at"}}
        if not payload:
            return
        async with self._session_factory() as session:
            stmt = update(ParseDeadLetter).where(ParseDeadLetter.id == dlq_id).values(**payload)
            await session.execute(stmt)
            await session.commit()

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

    async def get_schedule(self, schedule_id: str) -> Optional[Dict]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(ScheduleConfig).where(ScheduleConfig.id == schedule_id)
            )
            row = result.scalar_one_or_none()
            return self._row_to_dict(row) if row else None

    async def save_schedule(self, data: Dict[str, Any]) -> str:
        payload = dict(data)
        payload.setdefault("query", "")
        payload.setdefault("capture_mode", "hybrid")
        payload.setdefault("sort_strategy", "hybrid")
        payload["start_time"] = payload.get("start_time") or ""
        payload["end_time"] = payload.get("end_time") or ""
        async with self._session_factory() as session:
            schedule = ScheduleConfig(**payload)
            session.add(schedule)
            await session.commit()
            return schedule.id

    async def update_schedule(self, schedule_id: str, updates: Dict[str, Any]):
        payload = dict(updates)
        if "query" in payload:
            payload["query"] = payload.get("query") or ""
        if "capture_mode" in payload:
            payload["capture_mode"] = payload.get("capture_mode") or "hybrid"
        if "sort_strategy" in payload:
            payload["sort_strategy"] = payload.get("sort_strategy") or "hybrid"
        if "start_time" in payload:
            payload["start_time"] = payload.get("start_time") or ""
        if "end_time" in payload:
            payload["end_time"] = payload.get("end_time") or ""
        async with self._session_factory() as session:
            stmt = update(ScheduleConfig).where(ScheduleConfig.id == schedule_id).values(**payload)
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
    def _to_utc_dt(value: Any) -> Optional[datetime]:
        if value is None or value == "":
            return None
        if isinstance(value, datetime):
            dt = value
        elif isinstance(value, (int, float)):
            if float(value) <= 0:
                return None
            dt = datetime.fromtimestamp(float(value), tz=timezone.utc)
        elif isinstance(value, str):
            text_value = value.strip()
            if not text_value:
                return None
            if text_value.endswith("Z"):
                text_value = text_value[:-1] + "+00:00"
            try:
                dt = datetime.fromisoformat(text_value)
            except ValueError:
                return None
        else:
            return None

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    @staticmethod
    def _to_dict(value: Any) -> Dict[str, Any]:
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _to_list(value: Any) -> List[Any]:
        if isinstance(value, list):
            return value
        if isinstance(value, tuple):
            return list(value)
        return []

    def _normalize_source_payload(self, data: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(data)
        now = datetime.now(timezone.utc)
        source_platform = str(payload.get("source_platform") or "").strip()
        source_id = str(payload.get("source_id") or "").strip()
        if not source_platform or not source_id:
            raise ValueError("source_platform and source_id are required")

        normalized = {
            "source_platform": source_platform,
            "source_channel": str(payload.get("source_channel") or source_platform),
            "source_type": str(payload.get("source_type") or "post"),
            "source_id": source_id,
            "source_url": str(payload.get("source_url") or ""),
            "title": str(payload.get("title") or ""),
            "description": str(payload.get("description") or ""),
            "author": str(payload.get("author") or ""),
            "author_id": str(payload.get("author_id") or ""),
            "language": str(payload.get("language") or "zh"),
            "engagement_score": float(payload.get("engagement_score") or 0.0),
            "normalized_heat_score": float(payload.get("normalized_heat_score") or 0.0),
            "heat_breakdown": self._to_dict(payload.get("heat_breakdown")),
            "capture_mode": str(payload.get("capture_mode") or "hybrid"),
            "sort_strategy": str(payload.get("sort_strategy") or "hybrid"),
            "published_at": self._to_utc_dt(payload.get("published_at")),
            "source_updated_at": self._to_utc_dt(payload.get("source_updated_at") or payload.get("published_at")),
            "normalized_text": str(payload.get("normalized_text") or ""),
            "hashtags": self._to_list(payload.get("hashtags")),
            "mentions": self._to_list(payload.get("mentions")),
            "external_urls": self._to_list(payload.get("external_urls")),
            "media_urls": self._to_list(payload.get("media_urls")),
            "media_assets": self._to_list(payload.get("media_assets")),
            "multimodal": self._to_dict(payload.get("multimodal")),
            "platform_metrics": self._to_dict(payload.get("platform_metrics")),
            "parse_status": str(payload.get("parse_status") or "pending"),
            "parse_payload": self._to_dict(payload.get("parse_payload")),
            "parse_schema_version": str(payload.get("parse_schema_version") or ""),
            "parse_confidence": float(payload.get("parse_confidence") or 0.0),
            "parse_attempts": int(payload.get("parse_attempts") or 0),
            "parse_error_kind": str(payload.get("parse_error_kind") or ""),
            "parse_last_error": str(payload.get("parse_last_error") or ""),
            "parse_retry_at": self._to_utc_dt(payload.get("parse_retry_at")),
            "parsed_at": self._to_utc_dt(payload.get("parsed_at")),
            "pipeline_run_id": str(payload.get("pipeline_run_id") or ""),
            "raw_data": self._to_dict(payload.get("raw_data")),
            "scraped_at": self._to_utc_dt(payload.get("scraped_at")) or now,
            "last_seen_at": self._to_utc_dt(payload.get("last_seen_at")) or now,
            "content_hash": str(payload.get("content_hash") or ""),
        }
        source_updated_at = normalized.get("source_updated_at")
        updated_key = source_updated_at.isoformat() if isinstance(source_updated_at, datetime) else ""
        normalized["idempotency_key"] = f"{source_platform}:{source_id}:{updated_key}" if updated_key else ""
        return normalized

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
