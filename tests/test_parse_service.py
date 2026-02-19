"""
Parse-stage regression tests.
"""

import pytest

from trend_agent.config.settings import settings
from trend_agent.services.parse_service import ParseService


def _valid_payload(source, confidence_model: float = 0.9):
    return {
        "schema_version": "v1",
        "source_platform": source["source_platform"],
        "source_id": source["source_id"],
        "title": source.get("title") or "title",
        "summary": "summary text for parse contract",
        "key_points": ["point1", "point2"],
        "keywords": ["ai", "agent"],
        "sentiment": "neutral",
        "language": source.get("language") or "zh",
        "confidence_model": confidence_model,
    }


@pytest.mark.asyncio
async def test_parse_contract_validation_and_persistence(content_repo, monkeypatch):
    monkeypatch.setattr(settings.parse, "enabled", True)
    monkeypatch.setattr(settings.parse, "backend", "heuristic")
    monkeypatch.setattr(settings.parse, "schema_version", "v1")
    monkeypatch.setattr(settings.parse, "low_confidence_threshold", 0.5)

    row_id = await content_repo.upsert_source({
        "source_platform": "github",
        "source_id": "openai/openai-python",
        "title": "OpenAI Python",
        "description": "Official Python library for OpenAI APIs.",
        "language": "en",
        "content_hash": "hash_parse_1",
    })
    source = await content_repo.get_source(row_id)
    assert source is not None

    async def parser_fn(s):
        return _valid_payload(s, confidence_model=0.92)

    svc = ParseService(content_repo, parser_func=parser_fn)
    result = await svc.parse_source_by_row_id(row_id)
    assert result["status"] == "parsed"

    refreshed = await content_repo.get_source(row_id)
    assert refreshed is not None
    assert refreshed["parse_status"] == "parsed"
    assert refreshed["parse_schema_version"] == "v1"
    assert refreshed["parse_confidence"] >= 0.5
    assert refreshed["parse_payload"]["schema_version"] == "v1"


@pytest.mark.asyncio
async def test_low_confidence_routes_to_delayed_then_manual(content_repo, monkeypatch):
    monkeypatch.setattr(settings.parse, "enabled", True)
    monkeypatch.setattr(settings.parse, "schema_version", "v1")
    monkeypatch.setattr(settings.parse, "max_attempts_per_run", 1)
    monkeypatch.setattr(settings.parse, "low_confidence_retry_attempts", 0)
    monkeypatch.setattr(settings.parse, "low_confidence_threshold", 0.95)
    monkeypatch.setattr(settings.parse, "low_confidence_manual_after_attempts", 2)

    row_id = await content_repo.upsert_source({
        "source_platform": "twitter",
        "source_id": "tw_1",
        "title": "hello",
        "description": "hello world",
        "content_hash": "hash_parse_low",
    })

    async def parser_fn(s):
        return _valid_payload(s, confidence_model=0.3)

    svc = ParseService(content_repo, parser_func=parser_fn)
    first = await svc.parse_source_by_row_id(row_id)
    assert first["status"] == "delayed"
    row = await content_repo.get_source(row_id)
    assert row is not None
    assert row["parse_status"] == "delayed"
    assert row["parse_attempts"] == 1

    second = await svc.parse_source_by_row_id(row_id, force=True)
    assert second["status"] == "manual_review"
    row2 = await content_repo.get_source(row_id)
    assert row2 is not None
    assert row2["parse_status"] == "manual_review"
    assert row2["parse_attempts"] == 2


@pytest.mark.asyncio
async def test_recoverable_error_retries_then_parsed(content_repo, monkeypatch):
    monkeypatch.setattr(settings.parse, "enabled", True)
    monkeypatch.setattr(settings.parse, "schema_version", "v1")
    monkeypatch.setattr(settings.parse, "max_attempts_per_run", 2)
    monkeypatch.setattr(settings.parse, "recoverable_max_attempts", 5)
    monkeypatch.setattr(settings.parse, "low_confidence_threshold", 0.5)

    row_id = await content_repo.upsert_source({
        "source_platform": "weibo",
        "source_id": "wb_1",
        "title": "topic",
        "description": "hot topic",
        "content_hash": "hash_recoverable",
    })
    source = await content_repo.get_source(row_id)
    assert source is not None

    calls = {"n": 0}

    async def parser_fn(s):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("temporary parser timeout")
        return _valid_payload(s, confidence_model=0.9)

    svc = ParseService(content_repo, parser_func=parser_fn)
    result = await svc.parse_source_row(source)
    assert result["status"] == "parsed"
    assert calls["n"] == 2

    refreshed = await content_repo.get_source(row_id)
    assert refreshed is not None
    assert refreshed["parse_status"] == "parsed"
    assert refreshed["parse_attempts"] == 2


@pytest.mark.asyncio
async def test_unrecoverable_contract_error_goes_dlq(content_repo, monkeypatch):
    monkeypatch.setattr(settings.parse, "enabled", True)
    monkeypatch.setattr(settings.parse, "schema_version", "v1")
    monkeypatch.setattr(settings.parse, "max_attempts_per_run", 2)
    monkeypatch.setattr(settings.parse, "recoverable_max_attempts", 5)

    row_id = await content_repo.upsert_source({
        "source_platform": "zhihu",
        "source_id": "zh_1",
        "title": "q1",
        "description": "desc",
        "content_hash": "hash_unrecoverable",
    })

    async def parser_fn(_s):
        # Missing required fields for contract.
        return {"schema_version": "v1", "source_platform": "zhihu"}

    svc = ParseService(content_repo, parser_func=parser_fn)
    result = await svc.parse_source_by_row_id(row_id)
    assert result["status"] == "dlq"

    refreshed = await content_repo.get_source(row_id)
    assert refreshed is not None
    assert refreshed["parse_status"] == "dlq"
    assert refreshed["parse_error_kind"] == "unrecoverable"

    dlq_rows = await content_repo.list_parse_dead_letters(status="pending", limit=10)
    assert len(dlq_rows) == 1
    assert dlq_rows[0]["source_row_id"] == row_id


@pytest.mark.asyncio
async def test_parse_cache_by_content_hash_skips_duplicate_parse(content_repo, monkeypatch):
    monkeypatch.setattr(settings.parse, "enabled", True)
    monkeypatch.setattr(settings.parse, "schema_version", "v1")
    monkeypatch.setattr(settings.parse, "cache_enabled", True)
    monkeypatch.setattr(settings.parse, "low_confidence_threshold", 0.5)

    row_1 = await content_repo.upsert_source({
        "source_platform": "github",
        "source_id": "repo_1",
        "title": "repo one",
        "description": "same content",
        "content_hash": "hash_same_content",
    })
    row_2 = await content_repo.upsert_source({
        "source_platform": "github",
        "source_id": "repo_2",
        "title": "repo two",
        "description": "same content",
        "content_hash": "hash_same_content",
    })

    calls = {"n": 0}

    async def parser_fn(s):
        calls["n"] += 1
        return _valid_payload(s, confidence_model=0.9)

    svc = ParseService(content_repo, parser_func=parser_fn)
    first = await svc.parse_source_by_row_id(row_1)
    second = await svc.parse_source_by_row_id(row_2)
    assert first["status"] == "parsed"
    assert second["status"] == "parsed"
    assert second.get("cached") is True
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_replay_dlq_success(content_repo, monkeypatch):
    monkeypatch.setattr(settings.parse, "enabled", True)
    monkeypatch.setattr(settings.parse, "schema_version", "v1")
    monkeypatch.setattr(settings.parse, "low_confidence_threshold", 0.5)

    row_id = await content_repo.upsert_source({
        "source_platform": "bilibili",
        "source_id": "bv1",
        "title": "video",
        "description": "video desc",
        "content_hash": "hash_dlq_replay",
    })

    async def bad_parser(_s):
        return {"schema_version": "v1"}

    svc = ParseService(content_repo, parser_func=bad_parser)
    first = await svc.parse_source_by_row_id(row_id)
    assert first["status"] == "dlq"

    dlq_rows = await content_repo.list_parse_dead_letters(status="pending", limit=10)
    assert len(dlq_rows) == 1
    dlq_id = dlq_rows[0]["id"]

    async def good_parser(s):
        return _valid_payload(s, confidence_model=0.91)

    svc._parser_func = good_parser
    replay = await svc.replay_dead_letter(dlq_id)
    assert replay["status"] == "parsed"

    dlq_row = await content_repo.get_parse_dead_letter(dlq_id)
    assert dlq_row is not None
    assert dlq_row["status"] == "resolved"
