"""
Prometheus 指标采集

如 prometheus_client 未安装, 使用 NoOp 占位。
"""

import time
import logging
from contextlib import contextmanager

logger = logging.getLogger(__name__)

try:
    from prometheus_client import Counter, Histogram, Gauge, Info

    APP_INFO = Info("trend_agent_app", "TrendAgent app metadata")

    HTTP_REQUESTS = Counter(
        "trend_agent_http_requests_total", "HTTP requests count",
        ["method", "path", "status"],
    )
    HTTP_REQUEST_LATENCY = Histogram(
        "trend_agent_http_request_duration_seconds", "HTTP request latency",
        ["method", "path"],
        buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
    )

    SCRAPE_COUNT = Counter(
        "trend_agent_scrape_total", "Scraping results count",
        ["source", "status"],
    )
    SCRAPE_LATENCY = Histogram(
        "trend_agent_scrape_duration_seconds", "Scraping latency per source",
        ["source"],
        buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
    )

    CATEGORIZE_COUNT = Counter(
        "trend_agent_categorize_total", "Categorization count",
        ["category"],
    )

    PUBLISH_COUNT = Counter(
        "trend_agent_publish_total", "Publish attempts",
        ["platform", "status"],
    )
    PUBLISH_LATENCY = Histogram(
        "trend_agent_publish_duration_seconds", "Publishing latency",
        ["platform"],
        buckets=[0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
    )

    VIDEO_COUNT = Counter(
        "trend_agent_video_total", "Video generation attempts",
        ["provider", "status"],
    )

    PIPELINE_COUNT = Counter(
        "trend_agent_pipeline_total", "Pipeline runs",
        ["trigger", "status"],
    )
    PIPELINE_LATENCY = Histogram(
        "trend_agent_pipeline_duration_seconds", "Full pipeline latency",
        buckets=[5, 10, 30, 60, 120, 300, 600],
    )

    QUALITY_SCORE = Histogram(
        "trend_agent_quality_score", "Quality check scores",
        buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
    )

    _METRICS_AVAILABLE = True
    logger.info("Prometheus metrics initialized")

except ImportError:
    _METRICS_AVAILABLE = False
    logger.info("prometheus_client not installed, metrics disabled")


def set_app_info(name: str, version: str, env: str):
    if _METRICS_AVAILABLE:
        APP_INFO.info({"name": name, "version": version, "env": env})


def observe_http_request(method: str, path: str, status: int, elapsed: float):
    if _METRICS_AVAILABLE:
        HTTP_REQUESTS.labels(method=method, path=path, status=str(status)).inc()
        HTTP_REQUEST_LATENCY.labels(method=method, path=path).observe(max(0.0, elapsed))


def record_scrape(source: str, status: str, latency: float = 0.0):
    if _METRICS_AVAILABLE:
        SCRAPE_COUNT.labels(source=source, status=status).inc()
        if latency > 0:
            SCRAPE_LATENCY.labels(source=source).observe(latency)


def record_categorize(category: str):
    if _METRICS_AVAILABLE:
        CATEGORIZE_COUNT.labels(category=category).inc()


def record_publish(platform: str, status: str, latency: float = 0.0):
    if _METRICS_AVAILABLE:
        PUBLISH_COUNT.labels(platform=platform, status=status).inc()
        if latency > 0:
            PUBLISH_LATENCY.labels(platform=platform).observe(latency)


def record_video(provider: str, status: str):
    if _METRICS_AVAILABLE:
        VIDEO_COUNT.labels(provider=provider, status=status).inc()


def record_pipeline(trigger: str, status: str, latency: float = 0.0):
    if _METRICS_AVAILABLE:
        PIPELINE_COUNT.labels(trigger=trigger, status=status).inc()
        if latency > 0:
            PIPELINE_LATENCY.observe(latency)


def record_quality(score: float):
    if _METRICS_AVAILABLE:
        QUALITY_SCORE.observe(score)


@contextmanager
def track_latency_ctx(observe_fn, *labels):
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        if _METRICS_AVAILABLE:
            observe_fn(*labels, elapsed)
