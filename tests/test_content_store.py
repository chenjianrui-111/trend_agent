"""
Tests for content store (async SQLAlchemy).
"""

import pytest
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
        "target_platforms": ["wechat"],
    })
    assert sid

    schedules = await repo.list_schedules()
    assert len(schedules) == 1
    assert schedules[0]["name"] == "daily_run"

    await repo.delete_schedule(sid)
    schedules = await repo.list_schedules()
    assert len(schedules) == 0
