"""
Tests for API endpoints.
"""

import pytest
from uuid import uuid4
from httpx import AsyncClient, ASGITransport

from trend_agent.api.app import app, content_store


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_health_check(client):
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["app"] == "trend_agent"


@pytest.mark.asyncio
async def test_register_and_login(client):
    username = f"testuser_{uuid4().hex[:8]}"
    # Register
    resp = await client.post("/api/v1/auth/register", json={
        "username": username,
        "password": "testpass123",
        "tenant_id": "test_tenant",
    })
    assert resp.status_code == 200

    # Login
    resp = await client.post("/api/v1/auth/login", json={
        "username": username,
        "password": "testpass123",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["username"] == username


@pytest.mark.asyncio
async def test_list_content_dev_mode(client):
    resp = await client.get("/api/v1/content")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_dashboard_stats(client):
    resp = await client.get("/api/v1/dashboard/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_sources" in data


@pytest.mark.asyncio
async def test_list_schedules(client):
    resp = await client.get("/api/v1/schedules")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_create_schedule_with_strategy_fields(client):
    await content_store.init_db()
    name = f"strategy_schedule_{uuid4().hex[:8]}"
    resp = await client.post("/api/v1/schedules", json={
        "name": name,
        "cron_expression": "0 8 * * *",
        "sources": ["twitter"],
        "query": "AI",
        "target_platforms": ["wechat"],
        "capture_mode": "by_time",
        "sort_strategy": "recency",
        "start_time": "2026-02-18T00:00:00Z",
        "end_time": "2026-02-19T00:00:00Z",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "schedule_id" in data


@pytest.mark.asyncio
async def test_update_schedule_with_strategy_fields(client):
    await content_store.init_db()
    name = f"strategy_schedule_{uuid4().hex[:8]}"
    created = await client.post("/api/v1/schedules", json={
        "name": name,
        "cron_expression": "0 8 * * *",
        "sources": ["twitter"],
        "query": "AI",
        "target_platforms": ["wechat"],
    })
    assert created.status_code == 200
    schedule_id = created.json()["schedule_id"]

    resp = await client.put(f"/api/v1/schedules/{schedule_id}", json={
        "query": "AIGC",
        "capture_mode": "by_time",
        "sort_strategy": "recency",
        "start_time": "2026-02-18T00:00:00Z",
        "end_time": "2026-02-19T00:00:00Z",
        "enabled": False,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["schedule"]["query"] == "AIGC"
    assert data["schedule"]["capture_mode"] == "by_time"
    assert data["schedule"]["sort_strategy"] == "recency"
    assert data["schedule"]["enabled"] is False


@pytest.mark.asyncio
async def test_update_schedule_not_found_returns_404(client):
    await content_store.init_db()
    resp = await client.put("/api/v1/schedules/non-existent-id", json={
        "query": "AIGC",
        "capture_mode": "by_hot",
    })
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_schedule_no_updates_returns_400(client):
    await content_store.init_db()
    name = f"schedule_empty_update_{uuid4().hex[:8]}"
    created = await client.post("/api/v1/schedules", json={
        "name": name,
        "cron_expression": "0 8 * * *",
        "sources": ["twitter"],
        "target_platforms": ["wechat"],
    })
    assert created.status_code == 200
    schedule_id = created.json()["schedule_id"]

    resp = await client.put(f"/api/v1/schedules/{schedule_id}", json={})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_patch_schedule_enable_toggle(client):
    await content_store.init_db()
    name = f"schedule_toggle_{uuid4().hex[:8]}"
    created = await client.post("/api/v1/schedules", json={
        "name": name,
        "cron_expression": "0 8 * * *",
        "sources": ["twitter"],
        "target_platforms": ["wechat"],
    })
    assert created.status_code == 200
    schedule_id = created.json()["schedule_id"]

    first = await client.patch(f"/api/v1/schedules/{schedule_id}/enable")
    assert first.status_code == 200
    assert first.json()["enabled"] is False

    second = await client.patch(f"/api/v1/schedules/{schedule_id}/enable")
    assert second.status_code == 200
    assert second.json()["enabled"] is True


@pytest.mark.asyncio
async def test_patch_schedule_enable_not_found_returns_404(client):
    await content_store.init_db()
    resp = await client.patch("/api/v1/schedules/non-existent-id/enable")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_pipeline_runs(client):
    resp = await client.get("/api/v1/pipeline/runs")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_parse_run_endpoint(client):
    await content_store.init_db()
    resp = await client.post("/api/v1/parse/run", json={"limit": 10})
    assert resp.status_code == 200
    data = resp.json()
    assert "processed" in data


@pytest.mark.asyncio
async def test_parse_dlq_replay_not_found(client):
    await content_store.init_db()
    resp = await client.post("/api/v1/parse/dlq/non-existent/replay")
    assert resp.status_code == 404
