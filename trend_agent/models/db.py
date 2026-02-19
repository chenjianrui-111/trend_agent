"""
SQLAlchemy ORM 数据模型
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, DateTime, Float, Index, Integer, String, Text,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import JSON


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class TrendSource(Base):
    __tablename__ = "trend_sources"

    id = Column(String(64), primary_key=True, default=_uuid)
    source_platform = Column(String(32), nullable=False)
    source_channel = Column(String(64), default="")
    source_type = Column(String(32), default="")
    source_id = Column(String(256), nullable=False)
    source_url = Column(String(1024), default="")
    title = Column(Text, default="")
    description = Column(Text, default="")
    author = Column(String(256), default="")
    author_id = Column(String(256), default="")
    language = Column(String(8), default="zh")
    engagement_score = Column(Float, default=0.0)
    normalized_heat_score = Column(Float, default=0.0)
    heat_breakdown = Column(JSON, default=dict)
    capture_mode = Column(String(16), default="hybrid")
    sort_strategy = Column(String(16), default="hybrid")
    published_at = Column(DateTime)
    source_updated_at = Column(DateTime, index=True)
    normalized_text = Column(Text, default="")
    hashtags = Column(JSON, default=list)
    mentions = Column(JSON, default=list)
    external_urls = Column(JSON, default=list)
    media_urls = Column(JSON, default=list)
    media_assets = Column(JSON, default=list)
    multimodal = Column(JSON, default=dict)
    platform_metrics = Column(JSON, default=dict)
    parse_status = Column(String(16), default="pending")
    parse_payload = Column(JSON, default=dict)
    parse_schema_version = Column(String(16), default="")
    parse_confidence = Column(Float, default=0.0)
    parse_attempts = Column(Integer, default=0)
    parse_error_kind = Column(String(16), default="")
    parse_last_error = Column(Text, default="")
    parse_retry_at = Column(DateTime)
    parsed_at = Column(DateTime)
    pipeline_run_id = Column(String(64), default="")
    raw_data = Column(JSON, default=dict)
    scraped_at = Column(DateTime, nullable=False, default=_utcnow)
    last_seen_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)
    content_hash = Column(String(64), index=True, default="")

    __table_args__ = (
        Index("ix_source_platform_id", "source_platform", "source_id", unique=True),
    )


class CategorizedContent(Base):
    __tablename__ = "categorized_content"

    id = Column(String(64), primary_key=True, default=_uuid)
    source_id = Column(String(64), nullable=False, index=True)
    category = Column(String(32), nullable=False, index=True)
    subcategory = Column(String(64), default="")
    confidence = Column(Float, default=0.0)
    tags = Column(JSON, default=list)
    categorized_at = Column(DateTime, nullable=False, default=_utcnow)


class ContentDraft(Base):
    __tablename__ = "content_drafts"

    id = Column(String(64), primary_key=True, default=_uuid)
    source_id = Column(String(64), nullable=False, index=True)
    category_id = Column(String(64), default="")
    target_platform = Column(String(32), nullable=False, index=True)
    title = Column(Text, default="")
    body = Column(Text, nullable=False)
    summary = Column(Text, default="")
    hashtags = Column(JSON, default=list)
    media_urls = Column(JSON, default=list)
    video_url = Column(String(1024), default="")
    video_provider = Column(String(32), default="")
    language = Column(String(8), default="zh")
    status = Column(String(32), default="summarized", index=True)
    quality_score = Column(Float, default=0.0)
    quality_details = Column(JSON, default=dict)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, onupdate=_utcnow)


class DraftVersion(Base):
    __tablename__ = "draft_versions"

    id = Column(String(64), primary_key=True, default=_uuid)
    draft_id = Column(String(64), nullable=False, index=True)
    version_no = Column(Integer, nullable=False)
    title = Column(Text, default="")
    body = Column(Text, default="")
    summary = Column(Text, default="")
    hashtags = Column(JSON, default=list)
    media_urls = Column(JSON, default=list)
    generation_meta = Column(JSON, default=dict)
    quality_snapshot = Column(JSON, default=dict)
    output_hash = Column(String(64), default="", index=True)
    is_active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)

    __table_args__ = (
        Index("ix_draft_versions_draft_ver", "draft_id", "version_no", unique=True),
    )


class PublishRecord(Base):
    __tablename__ = "publish_records"

    id = Column(String(64), primary_key=True, default=_uuid)
    draft_id = Column(String(64), nullable=False, index=True)
    platform = Column(String(32), nullable=False)
    platform_post_id = Column(String(256), default="")
    platform_url = Column(String(1024), default="")
    status = Column(String(16), default="pending")
    error_message = Column(Text, default="")
    published_at = Column(DateTime)
    retry_count = Column(Integer, default=0)


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id = Column(String(64), primary_key=True, default=_uuid)
    trigger_type = Column(String(16), default="manual")
    config = Column(JSON, default=dict)
    status = Column(String(16), default="running", index=True)
    items_scraped = Column(Integer, default=0)
    items_published = Column(Integer, default=0)
    items_rejected = Column(Integer, default=0)
    started_at = Column(DateTime, nullable=False, default=_utcnow)
    completed_at = Column(DateTime)
    error_message = Column(Text, default="")
    state_history = Column(JSON, default=list)
    timing = Column(JSON, default=dict)


class SourceIngestRecord(Base):
    __tablename__ = "source_ingest_records"

    id = Column(String(64), primary_key=True, default=_uuid)
    source_platform = Column(String(32), nullable=False)
    source_id = Column(String(256), nullable=False)
    source_updated_at = Column(DateTime)
    idempotency_key = Column(String(256), nullable=False, unique=True, index=True)
    first_seen_at = Column(DateTime, nullable=False, default=_utcnow)


class ScraperState(Base):
    __tablename__ = "scraper_states"

    source = Column(String(64), primary_key=True)
    state = Column(JSON, default=dict)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)


class ParseCache(Base):
    __tablename__ = "parse_cache"

    id = Column(String(64), primary_key=True, default=_uuid)
    content_hash = Column(String(64), nullable=False, index=True)
    schema_version = Column(String(16), nullable=False, index=True)
    parse_payload = Column(JSON, default=dict)
    parse_confidence = Column(Float, default=0.0)
    hit_count = Column(Integer, default=0)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        Index("ix_parse_cache_hash_schema", "content_hash", "schema_version", unique=True),
    )


class ParseDeadLetter(Base):
    __tablename__ = "parse_dead_letters"

    id = Column(String(64), primary_key=True, default=_uuid)
    source_row_id = Column(String(64), nullable=False, index=True)
    source_platform = Column(String(32), nullable=False)
    source_id = Column(String(256), nullable=False)
    content_hash = Column(String(64), default="")
    schema_version = Column(String(16), default="")
    error_kind = Column(String(16), default="")
    error_code = Column(String(32), default="")
    error_message = Column(Text, default="")
    retryable = Column(Boolean, default=False)
    attempts = Column(Integer, default=0)
    status = Column(String(16), default="pending", index=True)  # pending/replayed/resolved
    payload_snapshot = Column(JSON, default=dict)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    replayed_at = Column(DateTime)


class ScheduleConfig(Base):
    __tablename__ = "schedule_configs"

    id = Column(String(64), primary_key=True, default=_uuid)
    name = Column(String(128), nullable=False, unique=True)
    cron_expression = Column(String(64), nullable=False)
    sources = Column(JSON, nullable=False)
    query = Column(String(256), default="")
    categories = Column(JSON, default=list)
    target_platforms = Column(JSON, nullable=False)
    capture_mode = Column(String(16), default="hybrid")
    sort_strategy = Column(String(16), default="hybrid")
    start_time = Column(String(64), default="")
    end_time = Column(String(64), default="")
    generate_video = Column(Boolean, default=False)
    video_provider = Column(String(32), default="")
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, onupdate=_utcnow)
