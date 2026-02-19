"""
Tests for content store (async SQLAlchemy).
"""

import sqlite3

import pytest
from sqlalchemy import text

from trend_agent.services.content_store import ContentRepository


@pytest.fixture
async def repo():
    repo = ContentRepository(db_url="sqlite+aiosqlite:///:memory:")
    await repo.init_db()
    yield repo
    await repo.close()


@pytest.mark.asyncio
async def test_upsert_and_list_sources(repo):
    source_id = await repo.upsert_source({
        "source_platform": "twitter",
        "source_id": "tw_001",
        "title": "Test tweet",
        "description": "Test description",
    })
    assert source_id

    sources = await repo.list_sources()
    assert len(sources) == 1
    assert sources[0]["title"] == "Test tweet"


@pytest.mark.asyncio
async def test_upsert_existing_source(repo):
    await repo.upsert_source({
        "source_platform": "twitter",
        "source_id": "tw_001",
        "title": "Original",
    })
    await repo.upsert_source({
        "source_platform": "twitter",
        "source_id": "tw_001",
        "title": "Updated",
    })
    sources = await repo.list_sources()
    assert len(sources) == 1
    assert sources[0]["title"] == "Updated"


@pytest.mark.asyncio
async def test_upsert_source_persists_structured_capture_fields(repo):
    source_row_id = await repo.upsert_source({
        "source_platform": "github",
        "source_channel": "github_trending",
        "source_type": "repository",
        "source_id": "openai/openai-python",
        "title": "openai/openai-python",
        "description": "Official library",
        "engagement_score": 1200,
        "normalized_heat_score": 0.88,
        "heat_breakdown": {"platform_percentile": 1.0},
        "capture_mode": "by_hot",
        "sort_strategy": "engagement",
        "published_at": "2026-02-19T00:00:00Z",
        "normalized_text": "openai openai-python official library",
        "hashtags": ["#ai#"],
        "mentions": ["@openai"],
        "external_urls": ["https://github.com/openai/openai-python"],
        "media_urls": ["https://avatars.githubusercontent.com/u/14957082"],
        "media_assets": [{"url": "https://avatars.githubusercontent.com/u/14957082", "media_type": "image"}],
        "multimodal": {"image_summary": "openai logo"},
        "platform_metrics": {"stars": 100000},
        "pipeline_run_id": "run_001",
        "content_hash": "hash_github_repo",
    })
    assert source_row_id

    pending_sources = await repo.list_sources_for_parsing(limit=10)
    assert any(s["id"] == source_row_id for s in pending_sources)
    row = next(s for s in pending_sources if s["id"] == source_row_id)
    assert row["source_channel"] == "github_trending"
    assert row["source_type"] == "repository"
    assert row["capture_mode"] == "by_hot"
    assert row["sort_strategy"] == "engagement"
    assert row["normalized_heat_score"] == 0.88
    assert row["platform_metrics"]["stars"] == 100000

    await repo.mark_source_parsed(source_row_id, {"summary": "parsed"})
    refreshed = await repo.list_sources_for_parsing(limit=10)
    assert all(s["id"] != source_row_id for s in refreshed)


@pytest.mark.asyncio
async def test_upsert_source_idempotent_by_updated_at(repo):
    first_id = await repo.upsert_source({
        "source_platform": "github",
        "source_id": "openai/openai-python",
        "title": "v1",
        "source_updated_at": "2026-02-19T00:00:00Z",
    })
    second_id = await repo.upsert_source({
        "source_platform": "github",
        "source_id": "openai/openai-python",
        "title": "v1-duplicate-should-skip",
        "source_updated_at": "2026-02-19T00:00:00Z",
    })
    assert first_id == second_id
    row = (await repo.list_sources(platform="github", limit=1))[0]
    assert row["title"] == "v1"

    await repo.upsert_source({
        "source_platform": "github",
        "source_id": "openai/openai-python",
        "title": "v2",
        "source_updated_at": "2026-02-20T00:00:00Z",
    })
    row = (await repo.list_sources(platform="github", limit=1))[0]
    assert row["title"] == "v2"


@pytest.mark.asyncio
async def test_scraper_state_roundtrip(repo):
    state_payload = {
        "cursor": {"github_trending": "2026-02-19T00:00:00+00:00"},
        "etag_cache": {"repo:key": "W/\"abc\""},
    }
    await repo.upsert_scraper_state("github", state_payload)
    state = await repo.get_scraper_state("github")
    assert state == state_payload


@pytest.mark.asyncio
async def test_parse_cache_roundtrip(repo):
    await repo.upsert_parse_cache(
        content_hash="h1",
        schema_version="v1",
        parse_payload={"summary": "ok"},
        parse_confidence=0.88,
    )
    row = await repo.get_parse_cache("h1", "v1")
    assert row is not None
    assert row["parse_payload"]["summary"] == "ok"
    assert row["parse_confidence"] == 0.88


@pytest.mark.asyncio
async def test_parse_dead_letter_crud(repo):
    dlq_id = await repo.create_parse_dead_letter({
        "source_row_id": "row_1",
        "source_platform": "github",
        "source_id": "openai/openai-python",
        "content_hash": "h1",
        "schema_version": "v1",
        "error_kind": "unrecoverable",
        "error_code": "contract_validation",
        "error_message": "bad payload",
        "attempts": 2,
        "status": "pending",
    })
    assert dlq_id
    row = await repo.get_parse_dead_letter(dlq_id)
    assert row is not None
    assert row["error_code"] == "contract_validation"

    await repo.update_parse_dead_letter(dlq_id, {"status": "resolved"})
    refreshed = await repo.get_parse_dead_letter(dlq_id)
    assert refreshed is not None
    assert refreshed["status"] == "resolved"


@pytest.mark.asyncio
async def test_draft_crud(repo):
    draft_id = await repo.save_draft({
        "source_id": "src_001",
        "target_platform": "wechat",
        "title": "Test Article",
        "body": "Test body content here",
        "status": "summarized",
    })
    assert draft_id

    draft = await repo.get_draft(draft_id)
    assert draft["title"] == "Test Article"

    await repo.update_draft(draft_id, {"status": "published"})
    draft = await repo.get_draft(draft_id)
    assert draft["status"] == "published"

    await repo.delete_draft(draft_id)
    draft = await repo.get_draft(draft_id)
    assert draft is None


@pytest.mark.asyncio
async def test_pipeline_run(repo):
    run_id = await repo.create_pipeline_run({
        "trigger_type": "manual",
        "status": "running",
    })
    assert run_id

    run = await repo.get_pipeline_run(run_id)
    assert run["status"] == "running"

    await repo.update_pipeline_run(run_id, {"status": "completed", "items_scraped": 10})
    run = await repo.get_pipeline_run(run_id)
    assert run["status"] == "completed"
    assert run["items_scraped"] == 10


@pytest.mark.asyncio
async def test_stats(repo):
    await repo.upsert_source({"source_platform": "twitter", "source_id": "tw_1", "title": "t1"})
    await repo.upsert_source({"source_platform": "youtube", "source_id": "yt_1", "title": "t2"})
    await repo.save_draft({"source_id": "s1", "target_platform": "wechat", "body": "b1"})

    stats = await repo.get_stats()
    assert stats["total_sources"] == 2
    assert stats["total_drafts"] == 1


@pytest.mark.asyncio
async def test_schedule_crud(repo):
    sid = await repo.save_schedule({
        "name": "daily_run",
        "cron_expression": "0 8 * * *",
        "sources": ["twitter", "youtube"],
        "query": "AI",
        "target_platforms": ["wechat"],
        "capture_mode": "by_time",
        "sort_strategy": "recency",
        "start_time": "2026-02-18T00:00:00Z",
        "end_time": "2026-02-19T00:00:00Z",
    })
    assert sid

    schedules = await repo.list_schedules()
    assert len(schedules) == 1
    assert schedules[0]["name"] == "daily_run"
    assert schedules[0]["capture_mode"] == "by_time"
    assert schedules[0]["sort_strategy"] == "recency"
    assert schedules[0]["query"] == "AI"

    await repo.delete_schedule(sid)
    schedules = await repo.list_schedules()
    assert len(schedules) == 0


@pytest.mark.asyncio
async def test_schedule_update_strategy_fields(repo):
    sid = await repo.save_schedule({
        "name": "daily_run_update",
        "cron_expression": "0 8 * * *",
        "sources": ["twitter"],
        "query": "AI",
        "target_platforms": ["wechat"],
    })
    await repo.update_schedule(sid, {
        "query": "AIGC",
        "capture_mode": "by_hot",
        "sort_strategy": "engagement",
        "start_time": "2026-02-18T00:00:00Z",
        "end_time": "2026-02-19T00:00:00Z",
        "enabled": False,
    })
    schedule = await repo.get_schedule(sid)
    assert schedule is not None
    assert schedule["query"] == "AIGC"
    assert schedule["capture_mode"] == "by_hot"
    assert schedule["sort_strategy"] == "engagement"
    assert schedule["start_time"] == "2026-02-18T00:00:00Z"
    assert schedule["end_time"] == "2026-02-19T00:00:00Z"
    assert schedule["enabled"] is False


@pytest.mark.asyncio
async def test_schedule_schema_migration_adds_strategy_fields(tmp_path):
    db_path = tmp_path / "legacy_schedule.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE schedule_configs (
            id VARCHAR(64) PRIMARY KEY,
            name VARCHAR(128) NOT NULL UNIQUE,
            cron_expression VARCHAR(64) NOT NULL,
            sources JSON NOT NULL,
            categories JSON,
            target_platforms JSON NOT NULL,
            generate_video BOOLEAN,
            video_provider VARCHAR(32),
            enabled BOOLEAN,
            created_at DATETIME,
            updated_at DATETIME
        )
        """
    )
    conn.commit()
    conn.close()

    repo = ContentRepository(db_url=f"sqlite+aiosqlite:///{db_path}")
    await repo.init_db()

    async with repo._engine.begin() as db:
        result = await db.execute(text("PRAGMA table_info(schedule_configs)"))
        columns = {row[1] for row in result.fetchall()}

    await repo.close()

    assert "query" in columns
    assert "capture_mode" in columns
    assert "sort_strategy" in columns
    assert "start_time" in columns
    assert "end_time" in columns


@pytest.mark.asyncio
async def test_trend_source_schema_migration_adds_structured_fields(tmp_path):
    db_path = tmp_path / "legacy_trend_source.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE trend_sources (
            id VARCHAR(64) PRIMARY KEY,
            source_platform VARCHAR(32) NOT NULL,
            source_id VARCHAR(256) NOT NULL,
            source_url VARCHAR(1024),
            title TEXT,
            description TEXT,
            author VARCHAR(256),
            author_id VARCHAR(256),
            language VARCHAR(8),
            engagement_score FLOAT,
            raw_data JSON,
            scraped_at DATETIME,
            content_hash VARCHAR(64)
        )
        """
    )
    conn.commit()
    conn.close()

    repo = ContentRepository(db_url=f"sqlite+aiosqlite:///{db_path}")
    await repo.init_db()

    async with repo._engine.begin() as db:
        result = await db.execute(text("PRAGMA table_info(trend_sources)"))
        columns = {row[1] for row in result.fetchall()}

    await repo.close()

    assert "source_channel" in columns
    assert "source_type" in columns
    assert "normalized_heat_score" in columns
    assert "heat_breakdown" in columns
    assert "capture_mode" in columns
    assert "sort_strategy" in columns
    assert "published_at" in columns
    assert "source_updated_at" in columns
    assert "normalized_text" in columns
    assert "hashtags" in columns
    assert "mentions" in columns
    assert "external_urls" in columns
    assert "media_urls" in columns
    assert "media_assets" in columns
    assert "multimodal" in columns
    assert "platform_metrics" in columns
    assert "parse_status" in columns
    assert "parse_payload" in columns
    assert "parse_schema_version" in columns
    assert "parse_confidence" in columns
    assert "parse_attempts" in columns
    assert "parse_error_kind" in columns
    assert "parse_last_error" in columns
    assert "parse_retry_at" in columns
    assert "parsed_at" in columns
    assert "pipeline_run_id" in columns
    assert "last_seen_at" in columns
