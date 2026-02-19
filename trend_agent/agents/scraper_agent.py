"""
ScraperAgent - 多源数据抓取协调 Agent
"""

import asyncio
import contextlib
import json
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from trend_agent.agents.base import BaseAgent
from trend_agent.config.settings import settings
from trend_agent.models.message import AgentMessage, TrendItem
from trend_agent.observability import metrics as obs
from trend_agent.scrapers.base import BaseScraper
from trend_agent.scrapers.twitter_scraper import TwitterScraper
from trend_agent.scrapers.youtube_scraper import YouTubeScraper
from trend_agent.scrapers.weibo_scraper import WeiboScraper
from trend_agent.scrapers.bilibili_scraper import BilibiliScraper
from trend_agent.scrapers.zhihu_scraper import ZhihuScraper
from trend_agent.scrapers.github_scraper import GitHubScraper
from trend_agent.services.content_store import ContentRepository
from trend_agent.services.dedup import DedupService
from trend_agent.services.heat_score import HeatScoreService
from trend_agent.services.multimodal_enricher import MultiModalEnricher
from trend_agent.services.source_normalizer import SourceNormalizer

logger = logging.getLogger(__name__)


@dataclass
class CircuitState:
    failures: int = 0
    open_until: float = 0.0
    half_open: bool = False


@dataclass
class ScrapeJob:
    source_name: str
    scraper: BaseScraper
    query: Optional[str]
    limit: int
    capture_mode: str
    start_time: Optional[str]
    end_time: Optional[str]
    sort_strategy: str
    future: asyncio.Future
    job_id: str = ""
    owner_id: str = ""


class CircuitOpenError(RuntimeError):
    pass


# Source name -> Scraper class
SCRAPER_REGISTRY: Dict[str, type] = {
    "twitter": TwitterScraper,
    "youtube": YouTubeScraper,
    "weibo": WeiboScraper,
    "bilibili": BilibiliScraper,
    "zhihu": ZhihuScraper,
    "github": GitHubScraper,
}


class ScraperAgent(BaseAgent):
    """多源数据抓取协调 Agent"""

    _REDIS_ENQUEUE_SCRIPT = """
local q = KEYS[1]
local seq = KEYS[2]
local max_size = tonumber(ARGV[1])
local member = ARGV[2]
local priority = tonumber(ARGV[3])
local current = redis.call('ZCARD', q)
if current >= max_size then
  return {0, current}
end
local s = redis.call('INCR', seq)
local score = priority * 1000000000 + s
redis.call('ZADD', q, score, member)
return {1, current + 1}
"""

    _REDIS_CIRCUIT_ALLOW_SCRIPT = """
local key = KEYS[1]
local now_ts = tonumber(ARGV[1])
local threshold = tonumber(ARGV[2])
local open_until = tonumber(redis.call('HGET', key, 'open_until') or '0')
if open_until <= 0 then
  return 1
end
if now_ts >= open_until then
  redis.call('HSET', key, 'half_open', '1')
  redis.call('HSET', key, 'failures', tostring(math.max(1, threshold - 1)))
  redis.call('HSET', key, 'open_until', '0')
  return 2
end
return 0
"""

    _REDIS_CIRCUIT_SUCCESS_SCRIPT = """
local key = KEYS[1]
local ttl = tonumber(ARGV[1])
redis.call('HSET', key, 'failures', '0')
redis.call('HSET', key, 'open_until', '0')
redis.call('HSET', key, 'half_open', '0')
redis.call('EXPIRE', key, ttl)
return 1
"""

    _REDIS_CIRCUIT_FAILURE_SCRIPT = """
local key = KEYS[1]
local threshold = tonumber(ARGV[1])
local open_seconds = tonumber(ARGV[2])
local now_ts = tonumber(ARGV[3])
local ttl = tonumber(ARGV[4])
local half_open = tonumber(redis.call('HGET', key, 'half_open') or '0')
local failures = tonumber(redis.call('HGET', key, 'failures') or '0')
if half_open == 1 then
  failures = threshold
else
  failures = failures + 1
end
local opened = 0
local open_until = tonumber(redis.call('HGET', key, 'open_until') or '0')
if failures >= threshold then
  open_until = now_ts + open_seconds
  opened = 1
end
redis.call('HSET', key, 'half_open', '0')
redis.call('HSET', key, 'failures', tostring(failures))
redis.call('HSET', key, 'open_until', tostring(open_until))
redis.call('EXPIRE', key, ttl)
return opened
"""

    def __init__(self, llm_client=None, content_store: Optional[ContentRepository] = None):
        super().__init__("scraper")
        self._scrapers: Dict[str, BaseScraper] = {}
        self._dedup = DedupService()
        self._normalizer = SourceNormalizer()
        self._heat = HeatScoreService()
        self._multimodal = MultiModalEnricher(llm_client) if llm_client else None
        self._content_store = content_store

        self._queue: Optional[asyncio.PriorityQueue] = None
        self._queue_seq: int = 0
        self._queue_lock = asyncio.Lock()
        self._workers: List[asyncio.Task] = []
        self._result_listener: Optional[asyncio.Task] = None
        self._pending_jobs: Dict[str, asyncio.Future] = {}
        self._instance_id: str = uuid.uuid4().hex
        self._coordination_backend: str = "memory"
        self._redis = None

        self._circuit_states: Dict[str, CircuitState] = {}
        self._circuit_locks: Dict[str, asyncio.Lock] = {}
        self._rate_locks: Dict[str, asyncio.Lock] = {}
        self._source_last_call_ts: Dict[str, float] = {}

    def set_content_store(self, content_store: ContentRepository) -> None:
        self._content_store = content_store

    async def startup(self):
        await super().startup()
        for name in settings.scraper.enabled_sources:
            cls = SCRAPER_REGISTRY.get(name)
            if cls:
                self._scrapers[name] = cls()
            else:
                self.logger.warning("Unknown scraper source: %s", name)
        await self._init_coordination_backend()
        await self._ensure_workers()
        await self._load_scraper_states()

    async def shutdown(self):
        await self._persist_scraper_states()
        if self._result_listener:
            self._result_listener.cancel()
            with contextlib.suppress(Exception):
                await self._result_listener
            self._result_listener = None
        for worker in self._workers:
            worker.cancel()
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers = []
        for future in self._pending_jobs.values():
            if not future.done():
                future.cancel()
        self._pending_jobs.clear()
        self._queue = None
        if self._redis is not None:
            with contextlib.suppress(Exception):
                await self._redis.aclose()
            self._redis = None
        self._coordination_backend = "memory"
        for scraper in self._scrapers.values():
            await scraper.close()
        await super().shutdown()

    async def _init_coordination_backend(self) -> None:
        desired = str(settings.scraper.coordination_backend or "memory").strip().lower()
        if desired != "redis":
            self._coordination_backend = "memory"
            return

        try:
            from redis import asyncio as redis_asyncio  # type: ignore
        except Exception as e:
            self.logger.warning("redis package unavailable, fallback to memory coordination: %s", e)
            self._coordination_backend = "memory"
            return

        try:
            self._redis = redis_asyncio.from_url(
                settings.scraper.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
            await self._redis.ping()
            self._coordination_backend = "redis"
            self.logger.info("Scraper coordination backend: redis")
        except Exception as e:
            self.logger.warning("redis unreachable, fallback to memory coordination: %s", e)
            self._coordination_backend = "memory"
            if self._redis is not None:
                with contextlib.suppress(Exception):
                    await self._redis.aclose()
            self._redis = None

    def _using_redis_coordination(self) -> bool:
        return self._coordination_backend == "redis" and self._redis is not None

    def _coord_key(self, suffix: str) -> str:
        prefix = str(settings.scraper.redis_key_prefix or "trend_agent:scraper").strip(":")
        return f"{prefix}:{suffix}"

    def _redis_queue_key(self) -> str:
        return self._coord_key("queue")

    def _redis_queue_seq_key(self) -> str:
        return self._coord_key("queue_seq")

    def _redis_result_channel(self, owner_id: str) -> str:
        return self._coord_key(f"results:{owner_id}")

    def _redis_circuit_key(self, source_name: str) -> str:
        return self._coord_key(f"circuit:{source_name}")

    async def process(self, message: AgentMessage) -> AgentMessage:
        """
        payload 输入: {"sources": ["twitter", "youtube"], "query": "AI", "limit": 50}
        payload 输出: {"items": List[TrendItem_dict]}
        """
        sources = message.payload.get("sources", list(self._scrapers.keys()))
        query = message.payload.get("query")
        limit = message.payload.get("limit", 50)
        capture_mode = message.payload.get("capture_mode", "hybrid")
        start_time = message.payload.get("start_time")
        end_time = message.payload.get("end_time")
        sort_strategy = message.payload.get("sort_strategy", "hybrid")
        source_priorities = message.payload.get("source_priorities", {})

        active_scrapers = {
            name: scraper for name, scraper in self._scrapers.items()
            if name in sources
        }
        if not active_scrapers:
            return message.create_reply("scraper", {"items": [], "error": "No active scrapers"})

        jobs = []
        for name, scraper in active_scrapers.items():
            jobs.append(
                ScrapeJob(
                    source_name=name,
                    scraper=scraper,
                    query=query,
                    limit=limit,
                    capture_mode=capture_mode,
                    start_time=start_time,
                    end_time=end_time,
                    sort_strategy=sort_strategy,
                    future=asyncio.get_running_loop().create_future(),
                )
            )

        if self._initialized:
            results = await self._run_with_queue(jobs, source_priorities=source_priorities)
        else:
            # Test / local direct mode when startup() was not called.
            results = await self._run_direct(jobs)

        all_items: List[TrendItem] = []
        for name, result in results:
            if isinstance(result, Exception):
                self.logger.error("Scraper %s failed: %s", name, result)
                obs.record_scrape(name, "error")
                continue
            for item in result:
                all_items.append(self._normalizer.normalize(item))

        if capture_mode in ("by_time", "hybrid") and (start_time or end_time):
            all_items = self._filter_by_time_window(all_items, start_time=start_time, end_time=end_time)

        self._dedup.clear()
        unique_items = []
        for item in all_items:
            text = item.normalized_text or (item.title + " " + item.description)
            if not text.strip():
                text = f"{item.source_platform}:{item.source_id}"
            if not self._dedup.check_and_add(text=text, media_urls=item.media_urls):
                unique_items.append(item)

        unique_items = self._heat.score_batch(unique_items)
        if self._multimodal:
            unique_items = await self._multimodal.enrich(unique_items)

        effective_sort = sort_strategy
        if effective_sort == "hybrid" and capture_mode == "by_time":
            effective_sort = "recency"
        elif effective_sort == "hybrid" and capture_mode == "by_hot":
            effective_sort = "engagement"
        sorted_items = self._heat.sort_items(unique_items, strategy=effective_sort)

        items_data = [item.__dict__ for item in sorted_items[:limit]]
        self.logger.info(
            "Scraping complete: %d raw -> %d unique items from %d sources",
            len(all_items), len(sorted_items), len(active_scrapers),
        )
        return message.create_reply(
            "scraper",
            {
                "items": items_data,
                "meta": {
                    "capture_mode": capture_mode,
                    "sort_strategy": effective_sort,
                    "start_time": start_time,
                    "end_time": end_time,
                    "raw_count": len(all_items),
                    "unique_count": len(sorted_items),
                    "queue_size": await self._queue_size(),
                },
            },
        )

    async def _run_direct(self, jobs: List[ScrapeJob]) -> List[Tuple[str, Any]]:
        semaphore = asyncio.Semaphore(max(1, int(settings.scraper.concurrent_scrapers)))

        async def _one(job: ScrapeJob) -> Tuple[str, Any]:
            async with semaphore:
                try:
                    items = await self._execute_scrape_job(job)
                    return job.source_name, items
                except Exception as e:
                    return job.source_name, e

        return await asyncio.gather(*[_one(job) for job in jobs])

    async def _run_with_queue(self, jobs: List[ScrapeJob], source_priorities: Any) -> List[Tuple[str, Any]]:
        await self._ensure_workers()

        for job in jobs:
            try:
                await self._enqueue_job(
                    job=job,
                    priority=self._resolve_priority(job.source_name, job.capture_mode, source_priorities),
                )
            except Exception as e:
                if not job.future.done():
                    job.future.set_exception(e)

        values = await asyncio.gather(*[job.future for job in jobs], return_exceptions=True)
        return [(job.source_name, value) for job, value in zip(jobs, values)]

    async def _ensure_workers(self) -> None:
        if self._workers:
            return
        async with self._queue_lock:
            if self._workers:
                return
            if self._using_redis_coordination():
                if self._result_listener is None:
                    self._result_listener = asyncio.create_task(
                        self._redis_result_listener(),
                        name=f"scrape-result-listener-{self._instance_id[:8]}",
                    )
            else:
                maxsize = max(1, int(settings.scraper.queue_max_size))
                self._queue = asyncio.PriorityQueue(maxsize=maxsize)
            worker_count = max(1, int(settings.scraper.concurrent_scrapers))
            self._workers = [
                asyncio.create_task(self._worker_loop(), name=f"scrape-worker-{i}")
                for i in range(worker_count)
            ]

    async def _enqueue_job(self, job: ScrapeJob, priority: int) -> None:
        if self._using_redis_coordination():
            await self._enqueue_job_redis(job=job, priority=priority)
            return
        if self._queue is None:
            raise RuntimeError("scrape queue not initialized")
        self._queue_seq += 1
        timeout = max(0.01, float(settings.scraper.queue_enqueue_timeout_seconds))
        try:
            await asyncio.wait_for(
                self._queue.put((priority, self._queue_seq, job)),
                timeout=timeout,
            )
        except asyncio.TimeoutError as e:
            obs.record_scrape_request(job.source_name, "queue_backpressure")
            raise RuntimeError(f"scrape queue full for {job.source_name}") from e

    async def _queue_size(self) -> int:
        if self._using_redis_coordination():
            assert self._redis is not None
            try:
                return int(await self._redis.zcard(self._redis_queue_key()))
            except Exception:
                return 0
        return self._queue.qsize() if self._queue else 0

    async def _enqueue_job_redis(self, job: ScrapeJob, priority: int) -> None:
        if not self._using_redis_coordination():
            raise RuntimeError("redis coordination unavailable")
        assert self._redis is not None
        timeout = max(0.01, float(settings.scraper.queue_enqueue_timeout_seconds))
        started = time.monotonic()
        job.job_id = uuid.uuid4().hex
        job.owner_id = self._instance_id
        self._pending_jobs[job.job_id] = job.future

        payload = json.dumps(
            {
                "job_id": job.job_id,
                "owner_id": job.owner_id,
                "source_name": job.source_name,
                "query": job.query,
                "limit": job.limit,
                "capture_mode": job.capture_mode,
                "start_time": job.start_time,
                "end_time": job.end_time,
                "sort_strategy": job.sort_strategy,
            },
            ensure_ascii=True,
            separators=(",", ":"),
        )
        max_size = max(1, int(settings.scraper.queue_max_size))

        while True:
            try:
                ok, _ = await self._redis.eval(
                    self._REDIS_ENQUEUE_SCRIPT,
                    2,
                    self._redis_queue_key(),
                    self._redis_queue_seq_key(),
                    max_size,
                    payload,
                    int(priority),
                )
            except Exception as e:
                self._pending_jobs.pop(job.job_id, None)
                raise RuntimeError(f"redis enqueue failed for {job.source_name}") from e
            if int(ok) == 1:
                return
            if time.monotonic() - started >= timeout:
                self._pending_jobs.pop(job.job_id, None)
                obs.record_scrape_request(job.source_name, "queue_backpressure")
                raise RuntimeError(f"scrape queue full for {job.source_name}")
            await asyncio.sleep(0.05)

    async def _dequeue_job_redis(self) -> Optional[ScrapeJob]:
        if not self._using_redis_coordination():
            return None
        assert self._redis is not None
        timeout = max(1, int(float(settings.scraper.redis_pop_timeout_seconds)))
        try:
            popped = await self._redis.bzpopmin(self._redis_queue_key(), timeout=timeout)
        except Exception:
            await asyncio.sleep(0.2)
            return None
        if not popped or len(popped) < 3:
            return None
        payload_raw = popped[1]
        try:
            payload = json.loads(payload_raw)
        except Exception:
            return None
        source_name = str(payload.get("source_name") or "").strip().lower()
        scraper = self._scrapers.get(source_name)
        if not scraper:
            owner = str(payload.get("owner_id") or "")
            if owner and payload.get("job_id"):
                await self._publish_result_redis(
                    owner_id=owner,
                    job_id=str(payload.get("job_id")),
                    source_name=source_name,
                    items=[],
                    error=RuntimeError(f"unknown scraper source: {source_name}"),
                )
            return None
        try:
            limit = int(payload.get("limit") or 50)
        except (TypeError, ValueError):
            limit = 50
        return ScrapeJob(
            source_name=source_name,
            scraper=scraper,
            query=payload.get("query"),
            limit=limit,
            capture_mode=str(payload.get("capture_mode") or "hybrid"),
            start_time=payload.get("start_time"),
            end_time=payload.get("end_time"),
            sort_strategy=str(payload.get("sort_strategy") or "hybrid"),
            future=asyncio.get_running_loop().create_future(),
            job_id=str(payload.get("job_id") or ""),
            owner_id=str(payload.get("owner_id") or ""),
        )

    async def _publish_result_redis(
        self,
        owner_id: str,
        job_id: str,
        source_name: str,
        items: List[TrendItem],
        error: Optional[Exception],
    ) -> None:
        if not self._using_redis_coordination():
            return
        if not owner_id or not job_id:
            return
        future = self._pending_jobs.pop(job_id, None)
        if owner_id == self._instance_id and future and not future.done():
            if error is None:
                future.set_result(items)
            else:
                future.set_exception(error)
            return
        assert self._redis is not None
        payload: Dict[str, Any] = {
            "job_id": job_id,
            "source_name": source_name,
            "ok": error is None,
        }
        if error is None:
            payload["items"] = [item.__dict__ for item in items]
        else:
            payload["error"] = str(error)
        data = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
        try:
            await self._redis.publish(self._redis_result_channel(owner_id), data)
        except Exception:
            if future and not future.done():
                if error is None:
                    future.set_result(items)
                else:
                    future.set_exception(error)

    async def _redis_result_listener(self) -> None:
        if not self._using_redis_coordination():
            return
        assert self._redis is not None
        pubsub = self._redis.pubsub()
        channel = self._redis_result_channel(self._instance_id)
        await pubsub.subscribe(channel)
        try:
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                data_raw = message.get("data")
                if not isinstance(data_raw, str):
                    continue
                try:
                    payload = json.loads(data_raw)
                except Exception:
                    continue
                job_id = str(payload.get("job_id") or "")
                if not job_id:
                    continue
                future = self._pending_jobs.pop(job_id, None)
                if not future or future.done():
                    continue
                if bool(payload.get("ok")):
                    items_data = payload.get("items", [])
                    items = [
                        TrendItem(**item)
                        for item in items_data
                        if isinstance(item, dict)
                    ]
                    future.set_result(items)
                else:
                    future.set_exception(RuntimeError(str(payload.get("error") or "scrape failed")))
        except asyncio.CancelledError:
            raise
        finally:
            with contextlib.suppress(Exception):
                await pubsub.unsubscribe(channel)
            with contextlib.suppress(Exception):
                await pubsub.aclose()

    async def _worker_loop(self) -> None:
        while True:
            if self._using_redis_coordination():
                job = await self._dequeue_job_redis()
                if job is None:
                    continue
                queue_task_done = False
            else:
                assert self._queue is not None
                _, _, job = await self._queue.get()
                queue_task_done = True
            try:
                items = await self._execute_scrape_job(job)
                if self._using_redis_coordination():
                    await self._publish_result_redis(
                        owner_id=job.owner_id,
                        job_id=job.job_id,
                        source_name=job.source_name,
                        items=items,
                        error=None,
                    )
                elif not job.future.done():
                    job.future.set_result(items)
            except Exception as e:
                if self._using_redis_coordination():
                    await self._publish_result_redis(
                        owner_id=job.owner_id,
                        job_id=job.job_id,
                        source_name=job.source_name,
                        items=[],
                        error=e,
                    )
                elif not job.future.done():
                    job.future.set_exception(e)
            finally:
                if queue_task_done and self._queue is not None:
                    self._queue.task_done()

    def _resolve_priority(self, source_name: str, capture_mode: str, raw: Any) -> int:
        default = 100
        if isinstance(raw, dict):
            val = raw.get(source_name)
            if isinstance(val, (int, float)):
                default = int(val)
        if capture_mode == "by_hot":
            default -= 10
        if source_name == "github":
            default -= 5
        return default

    async def _execute_scrape_job(self, job: ScrapeJob) -> List[TrendItem]:
        await self._rate_limit_wait(job.source_name)
        items = await self._scrape_with_resilience(
            scraper=job.scraper,
            source_name=job.source_name,
            query=job.query,
            limit=job.limit,
            capture_mode=job.capture_mode,
            start_time=job.start_time,
            end_time=job.end_time,
            sort_strategy=job.sort_strategy,
        )
        await self._persist_one_scraper_state(job.source_name, job.scraper)
        return items

    async def _scrape_with_resilience(
        self,
        scraper: BaseScraper,
        source_name: str,
        query: Optional[str],
        limit: int,
        capture_mode: str,
        start_time: Optional[str],
        end_time: Optional[str],
        sort_strategy: str,
    ) -> List[TrendItem]:
        max_attempts = max(1, int(settings.scraper.retry_max_attempts))
        base_delay = max(0.01, float(settings.scraper.retry_base_delay_seconds))

        for attempt in range(max_attempts):
            if not await self._circuit_allow(source_name):
                obs.record_scrape(source_name, "circuit_open")
                obs.record_scrape_request(source_name, "circuit_open")
                raise CircuitOpenError(f"circuit open for source={source_name}")

            start = time.perf_counter()
            try:
                items = await scraper.scrape(
                    query=query,
                    limit=limit,
                    capture_mode=capture_mode,
                    start_time=start_time,
                    end_time=end_time,
                    sort_strategy=sort_strategy,
                )
                latency = time.perf_counter() - start
                obs.record_scrape(source_name, "success", latency)
                obs.record_scrape_request(source_name, "success")
                obs.record_scrape_items(source_name, len(items))
                obs.record_scrape_cost(source_name, request_units=1.0, item_units=float(len(items)))
                await self._circuit_record_success(source_name)
                return items
            except Exception:
                latency = time.perf_counter() - start
                obs.record_scrape(source_name, "error", latency)
                obs.record_scrape_request(source_name, "error")
                opened = await self._circuit_record_failure(source_name)
                if opened:
                    obs.record_scrape(source_name, "circuit_opened")
                if attempt >= max_attempts - 1:
                    raise
                delay = base_delay * (2 ** attempt)
                obs.record_scrape_request(source_name, "retry")
                await asyncio.sleep(delay)

        return []

    def _get_circuit_lock(self, source_name: str) -> asyncio.Lock:
        lock = self._circuit_locks.get(source_name)
        if lock is None:
            lock = asyncio.Lock()
            self._circuit_locks[source_name] = lock
        return lock

    def _get_circuit_state(self, source_name: str) -> CircuitState:
        state = self._circuit_states.get(source_name)
        if state is None:
            state = CircuitState()
            self._circuit_states[source_name] = state
        return state

    async def _circuit_allow(self, source_name: str) -> bool:
        if self._using_redis_coordination():
            return await self._circuit_allow_redis(source_name)
        state = self._get_circuit_state(source_name)
        lock = self._get_circuit_lock(source_name)
        threshold = max(1, int(settings.scraper.circuit_breaker_failure_threshold))
        async with lock:
            now = time.monotonic()
            if state.open_until <= 0:
                return True
            if now >= state.open_until:
                state.half_open = True
                state.failures = max(1, threshold - 1)
                state.open_until = 0.0
                obs.record_scrape_request(source_name, "circuit_half_open")
                return True
            return False

    async def _circuit_record_success(self, source_name: str) -> None:
        if self._using_redis_coordination():
            await self._circuit_record_success_redis(source_name)
            return
        state = self._get_circuit_state(source_name)
        lock = self._get_circuit_lock(source_name)
        async with lock:
            state.failures = 0
            state.open_until = 0.0
            state.half_open = False

    async def _circuit_record_failure(self, source_name: str) -> bool:
        if self._using_redis_coordination():
            return await self._circuit_record_failure_redis(source_name)
        state = self._get_circuit_state(source_name)
        lock = self._get_circuit_lock(source_name)
        threshold = max(1, int(settings.scraper.circuit_breaker_failure_threshold))
        open_seconds = max(1.0, float(settings.scraper.circuit_breaker_open_seconds))
        async with lock:
            if state.half_open:
                state.failures = threshold
            else:
                state.failures += 1
            state.half_open = False
            if state.failures >= threshold:
                state.open_until = time.monotonic() + open_seconds
                return True
            return False

    async def _circuit_allow_redis(self, source_name: str) -> bool:
        assert self._redis is not None
        threshold = max(1, int(settings.scraper.circuit_breaker_failure_threshold))
        try:
            result = await self._redis.eval(
                self._REDIS_CIRCUIT_ALLOW_SCRIPT,
                1,
                self._redis_circuit_key(source_name),
                int(time.time()),
                threshold,
            )
        except Exception:
            # Fail-open to reduce global outage blast radius from Redis itself.
            return True
        if int(result) == 2:
            obs.record_scrape_request(source_name, "circuit_half_open")
            return True
        return int(result) == 1

    async def _circuit_record_success_redis(self, source_name: str) -> None:
        assert self._redis is not None
        ttl = max(300, int(float(settings.scraper.circuit_breaker_open_seconds) * 20))
        with contextlib.suppress(Exception):
            await self._redis.eval(
                self._REDIS_CIRCUIT_SUCCESS_SCRIPT,
                1,
                self._redis_circuit_key(source_name),
                ttl,
            )

    async def _circuit_record_failure_redis(self, source_name: str) -> bool:
        assert self._redis is not None
        threshold = max(1, int(settings.scraper.circuit_breaker_failure_threshold))
        open_seconds = max(1.0, float(settings.scraper.circuit_breaker_open_seconds))
        ttl = max(300, int(open_seconds * 20))
        try:
            opened = await self._redis.eval(
                self._REDIS_CIRCUIT_FAILURE_SCRIPT,
                1,
                self._redis_circuit_key(source_name),
                threshold,
                int(open_seconds),
                int(time.time()),
                ttl,
            )
        except Exception:
            return False
        return int(opened) == 1

    def _get_rate_lock(self, source_name: str) -> asyncio.Lock:
        lock = self._rate_locks.get(source_name)
        if lock is None:
            lock = asyncio.Lock()
            self._rate_locks[source_name] = lock
        return lock

    async def _rate_limit_wait(self, source_name: str) -> None:
        rate = settings.scraper.source_rps.get(source_name.lower(), 0.0)
        if rate <= 0:
            return
        min_interval = 1.0 / rate
        lock = self._get_rate_lock(source_name)
        async with lock:
            now = time.monotonic()
            last = self._source_last_call_ts.get(source_name, 0.0)
            wait_time = min_interval - (now - last)
            if wait_time > 0:
                await asyncio.sleep(wait_time)
            self._source_last_call_ts[source_name] = time.monotonic()

    async def _load_scraper_states(self) -> None:
        if not self._content_store:
            return
        for name, scraper in self._scrapers.items():
            try:
                state = await self._content_store.get_scraper_state(name)
                if state:
                    scraper.load_state(state)
            except Exception as e:
                self.logger.warning("Failed to load scraper state for %s: %s", name, e)

    async def _persist_one_scraper_state(self, source_name: str, scraper: BaseScraper) -> None:
        if not self._content_store:
            return
        try:
            state = scraper.dump_state()
            if state:
                await self._content_store.upsert_scraper_state(source_name, state)
        except Exception as e:
            self.logger.warning("Failed to persist scraper state for %s: %s", source_name, e)

    async def _persist_scraper_states(self) -> None:
        if not self._content_store:
            return
        for name, scraper in self._scrapers.items():
            await self._persist_one_scraper_state(name, scraper)

    async def get_scraper_health(self) -> Dict:
        results = {}
        for name, scraper in self._scrapers.items():
            results[name] = await scraper.health_check()
        return results

    def _filter_by_time_window(
        self,
        items: List[TrendItem],
        start_time: Optional[str],
        end_time: Optional[str],
    ) -> List[TrendItem]:
        start_dt = self._to_dt(start_time) if start_time else None
        end_dt = self._to_dt(end_time) if end_time else None
        if not start_dt and not end_dt:
            return items

        filtered: List[TrendItem] = []
        for item in items:
            dt = self._to_dt(item.published_at or item.scraped_at)
            if start_dt and dt < start_dt:
                continue
            if end_dt and dt > end_dt:
                continue
            filtered.append(item)
        return filtered

    @staticmethod
    def _to_dt(value: Optional[str]) -> datetime:
        if not value:
            return datetime.now(timezone.utc)
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return datetime.now(timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
