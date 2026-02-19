"""
Regression tests for scraper strategy controls.
"""

import asyncio
import time

import pytest

from trend_agent.agents.scraper_agent import ScrapeJob, ScraperAgent
from trend_agent.config.settings import settings
from trend_agent.models.message import AgentMessage, TrendItem


class _DummyScraper:
    def __init__(self, name: str, items):
        self.name = name
        self._items = items

    async def scrape(
        self,
        query=None,
        limit=50,
        capture_mode="hybrid",
        start_time=None,
        end_time=None,
        sort_strategy="hybrid",
    ):
        return self._items[:limit]

    async def health_check(self):
        return {"status": "healthy", "source": self.name}

    async def close(self):
        return None


class _FailingScraper:
    def __init__(self, name: str):
        self.name = name
        self.calls = 0

    async def scrape(
        self,
        query=None,
        limit=50,
        capture_mode="hybrid",
        start_time=None,
        end_time=None,
        sort_strategy="hybrid",
    ):
        self.calls += 1
        raise RuntimeError("boom")

    async def health_check(self):
        return {"status": "unhealthy", "source": self.name}

    async def close(self):
        return None


class _FakeRedisCoordination:
    def __init__(self):
        self._zsets = {}
        self._seq = {}
        self._hashes = {}

    async def ping(self):
        return True

    async def aclose(self):
        return None

    async def zcard(self, key):
        return len(self._zsets.get(key, []))

    async def eval(self, script, numkeys, *args):
        if script == ScraperAgent._REDIS_ENQUEUE_SCRIPT:
            queue_key, seq_key = args[0], args[1]
            max_size = int(args[2])
            payload = args[3]
            priority = int(args[4])
            q = self._zsets.setdefault(queue_key, [])
            if len(q) >= max_size:
                return [0, len(q)]
            seq_val = int(self._seq.get(seq_key, 0)) + 1
            self._seq[seq_key] = seq_val
            score = priority * 1_000_000_000 + seq_val
            q.append((score, payload))
            q.sort(key=lambda x: x[0])
            return [1, len(q)]

        if script == ScraperAgent._REDIS_CIRCUIT_ALLOW_SCRIPT:
            key = args[0]
            now_ts = int(args[1])
            threshold = int(args[2])
            state = self._hashes.setdefault(key, {"failures": 0, "open_until": 0, "half_open": 0})
            open_until = int(state.get("open_until", 0))
            if open_until <= 0:
                return 1
            if now_ts >= open_until:
                state["half_open"] = 1
                state["failures"] = max(1, threshold - 1)
                state["open_until"] = 0
                return 2
            return 0

        if script == ScraperAgent._REDIS_CIRCUIT_SUCCESS_SCRIPT:
            key = args[0]
            state = self._hashes.setdefault(key, {"failures": 0, "open_until": 0, "half_open": 0})
            state["failures"] = 0
            state["open_until"] = 0
            state["half_open"] = 0
            return 1

        if script == ScraperAgent._REDIS_CIRCUIT_FAILURE_SCRIPT:
            key = args[0]
            threshold = int(args[1])
            open_seconds = int(args[2])
            now_ts = int(args[3])
            state = self._hashes.setdefault(key, {"failures": 0, "open_until": 0, "half_open": 0})
            half_open = int(state.get("half_open", 0))
            failures = int(state.get("failures", 0))
            if half_open == 1:
                failures = threshold
            else:
                failures += 1
            state["half_open"] = 0
            state["failures"] = failures
            if failures >= threshold:
                state["open_until"] = now_ts + open_seconds
                return 1
            return 0

        raise RuntimeError("unsupported script")


@pytest.mark.asyncio
async def test_scraper_by_time_filters_window_and_uses_recency_sort():
    items = [
        TrendItem(
            source_platform="twitter",
            source_id="old",
            title="old",
            description="old",
            engagement_score=999,
            published_at="2026-02-17T00:00:00+00:00",
            scraped_at="2026-02-17T00:00:00+00:00",
            content_hash="h_old",
        ),
        TrendItem(
            source_platform="twitter",
            source_id="newer",
            title="newer",
            description="newer",
            engagement_score=10,
            published_at="2026-02-19T03:00:00+00:00",
            scraped_at="2026-02-19T03:00:00+00:00",
            content_hash="h_newer",
        ),
        TrendItem(
            source_platform="twitter",
            source_id="new",
            title="new",
            description="new",
            engagement_score=100,
            published_at="2026-02-19T01:00:00+00:00",
            scraped_at="2026-02-19T01:00:00+00:00",
            content_hash="h_new",
        ),
    ]
    agent = ScraperAgent()
    agent._scrapers = {"twitter": _DummyScraper("twitter", items)}

    msg = AgentMessage(
        payload={
            "sources": ["twitter"],
            "limit": 10,
            "capture_mode": "by_time",
            "sort_strategy": "hybrid",
            "start_time": "2026-02-19T00:00:00+00:00",
            "end_time": "2026-02-19T23:59:59+00:00",
        }
    )
    res = await agent.process(msg)
    data = res.payload["items"]

    assert len(data) == 2
    # by_time + hybrid should become recency sorting
    assert data[0]["source_id"] == "newer"
    assert data[1]["source_id"] == "new"


@pytest.mark.asyncio
async def test_scraper_by_hot_prefers_engagement_sort():
    items = [
        TrendItem(
            source_platform="twitter",
            source_id="lo",
            title="lo",
            description="lo",
            engagement_score=100,
            published_at="2026-02-19T10:00:00+00:00",
            scraped_at="2026-02-19T10:00:00+00:00",
            content_hash="a1",
        ),
        TrendItem(
            source_platform="twitter",
            source_id="hi",
            title="hi",
            description="hi",
            engagement_score=3000,
            published_at="2026-02-18T10:00:00+00:00",
            scraped_at="2026-02-18T10:00:00+00:00",
            content_hash="a2",
        ),
    ]
    agent = ScraperAgent()
    agent._scrapers = {"twitter": _DummyScraper("twitter", items)}

    msg = AgentMessage(
        payload={
            "sources": ["twitter"],
            "limit": 10,
            "capture_mode": "by_hot",
            "sort_strategy": "hybrid",
        }
    )
    res = await agent.process(msg)
    data = res.payload["items"]

    assert len(data) == 2
    # by_hot + hybrid should become engagement sorting
    assert data[0]["source_id"] == "hi"
    assert data[1]["source_id"] == "lo"


@pytest.mark.asyncio
async def test_scraper_source_circuit_breaker_opens_and_short_circuits(monkeypatch):
    monkeypatch.setattr(settings.scraper, "retry_max_attempts", 1)
    monkeypatch.setattr(settings.scraper, "circuit_breaker_failure_threshold", 2)
    monkeypatch.setattr(settings.scraper, "circuit_breaker_open_seconds", 60.0)
    scraper = _FailingScraper("twitter")
    agent = ScraperAgent()
    agent._scrapers = {"twitter": scraper}

    msg = AgentMessage(payload={"sources": ["twitter"], "limit": 5})
    await agent.process(msg)  # fail #1
    await agent.process(msg)  # fail #2 -> open circuit
    before = scraper.calls
    await agent.process(msg)  # should be circuit-open short-circuit

    assert scraper.calls == before
    state = agent._circuit_states["twitter"]
    assert state.open_until > time.monotonic()


@pytest.mark.asyncio
async def test_redis_queue_backpressure_shared_across_instances(monkeypatch):
    monkeypatch.setattr(settings.scraper, "queue_max_size", 1)
    monkeypatch.setattr(settings.scraper, "queue_enqueue_timeout_seconds", 0.05)
    fake_redis = _FakeRedisCoordination()

    agent_a = ScraperAgent()
    agent_b = ScraperAgent()
    agent_a._coordination_backend = "redis"
    agent_b._coordination_backend = "redis"
    agent_a._redis = fake_redis
    agent_b._redis = fake_redis

    scraper = _DummyScraper("twitter", [])
    loop = asyncio.get_running_loop()
    job_a = ScrapeJob(
        source_name="twitter",
        scraper=scraper,
        query=None,
        limit=10,
        capture_mode="hybrid",
        start_time=None,
        end_time=None,
        sort_strategy="hybrid",
        future=loop.create_future(),
    )
    await agent_a._enqueue_job(job_a, priority=100)
    assert await agent_a._queue_size() == 1

    job_b = ScrapeJob(
        source_name="twitter",
        scraper=scraper,
        query=None,
        limit=10,
        capture_mode="hybrid",
        start_time=None,
        end_time=None,
        sort_strategy="hybrid",
        future=loop.create_future(),
    )
    with pytest.raises(RuntimeError, match="queue full"):
        await agent_b._enqueue_job(job_b, priority=100)
    assert not agent_b._pending_jobs


@pytest.mark.asyncio
async def test_redis_circuit_state_shared_across_instances(monkeypatch):
    monkeypatch.setattr(settings.scraper, "circuit_breaker_failure_threshold", 1)
    monkeypatch.setattr(settings.scraper, "circuit_breaker_open_seconds", 60.0)
    fake_redis = _FakeRedisCoordination()

    agent_a = ScraperAgent()
    agent_b = ScraperAgent()
    agent_a._coordination_backend = "redis"
    agent_b._coordination_backend = "redis"
    agent_a._redis = fake_redis
    agent_b._redis = fake_redis

    opened = await agent_a._circuit_record_failure("twitter")
    assert opened is True
    allowed = await agent_b._circuit_allow("twitter")
    assert allowed is False
