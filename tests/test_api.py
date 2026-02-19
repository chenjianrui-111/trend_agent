"""
Tests for API endpoints.
"""

import pytest
from httpx import AsyncClient, ASGITransport

from trend_agent.api.app import app


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
    # Register
    resp = await client.post("/api/v1/auth/register", json={
        "username": "testuser",
        "password": "testpass123",
        "tenant_id": "test_tenant",
    })
    assert resp.status_code == 200

    # Login
    resp = await client.post("/api/v1/auth/login", json={
        "username": "testuser",
        "password": "testpass123",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["username"] == "testuser"


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
async def test_list_pipeline_runs(client):
    resp = await client.get("/api/v1/pipeline/runs")
    assert resp.status_code == 200
