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
    source_id = Column(String(256), nullable=False)
    source_url = Column(String(1024), default="")
    title = Column(Text, default="")
    description = Column(Text, default="")
    author = Column(String(256), default="")
    author_id = Column(String(256), default="")
    language = Column(String(8), default="zh")
    engagement_score = Column(Float, default=0.0)
    raw_data = Column(JSON, default=dict)
    scraped_at = Column(DateTime, nullable=False, default=_utcnow)
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


class ScheduleConfig(Base):
    __tablename__ = "schedule_configs"

    id = Column(String(64), primary_key=True, default=_uuid)
    name = Column(String(128), nullable=False, unique=True)
    cron_expression = Column(String(64), nullable=False)
    sources = Column(JSON, nullable=False)
    categories = Column(JSON, default=list)
    target_platforms = Column(JSON, nullable=False)
    generate_video = Column(Boolean, default=False)
    video_provider = Column(String(32), default="")
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, onupdate=_utcnow)
