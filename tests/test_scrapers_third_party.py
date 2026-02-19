"""
Third-party platform scraper regression tests (offline with mocked responses).
"""

from unittest.mock import AsyncMock

import pytest

from trend_agent.config.settings import settings
from trend_agent.scrapers.bilibili_scraper import BilibiliScraper
from trend_agent.scrapers.github_scraper import GitHubScraper
from trend_agent.scrapers.twitter_scraper import TwitterScraper
from trend_agent.scrapers.weibo_scraper import WeiboScraper
from trend_agent.scrapers.youtube_scraper import YouTubeScraper
from trend_agent.scrapers.zhihu_scraper import ZhihuScraper


class _MockResponse:
    def __init__(self, status: int, json_data=None, text_data: str = "", headers=None):
        self.status = status
        self._json_data = json_data or {}
        self._text_data = text_data
        self.headers = headers or {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def json(self):
        return self._json_data

    async def text(self):
        return self._text_data


class _MockSession:
    def __init__(self, responses):
        self._responses = responses
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        if callable(self._responses):
            return self._responses(url, **kwargs)
        if not self._responses:
            raise AssertionError("No mocked response left")
        return self._responses.pop(0)


@pytest.mark.asyncio
async def test_twitter_scrape_parses_metrics_and_time_window(monkeypatch):
    monkeypatch.setattr(settings.scraper, "twitter_bearer_token", "token-123")
    scraper = TwitterScraper()
    session = _MockSession([
        _MockResponse(
            200,
            json_data={
                "data": [
                    {
                        "id": "tw_1",
                        "text": "hello world",
                        "author_id": "u_1",
                        "lang": "en",
                        "created_at": "2026-02-19T00:00:00Z",
                        "public_metrics": {"like_count": 10, "retweet_count": 2, "reply_count": 3},
                    }
                ],
                "includes": {"users": [{"id": "u_1", "name": "Alice", "username": "alice"}]},
            },
        )
    ])
    scraper._get_session = AsyncMock(return_value=session)

    items = await scraper.scrape(
        query="AI",
        limit=10,
        start_time="2026-02-18T00:00:00Z",
        end_time="2026-02-19T00:00:00Z",
    )
    assert len(items) == 1
    item = items[0]
    assert item.source_id == "tw_1"
    assert item.author == "Alice"
    assert item.engagement_score == 17.0
    assert item.published_at == "2026-02-19T00:00:00Z"
    assert item.platform_metrics["retweet_count"] == 2

    params = session.calls[0]["params"]
    assert params["query"] == "AI"
    assert params["start_time"] == "2026-02-18T00:00:00Z"
    assert params["end_time"] == "2026-02-19T00:00:00Z"


@pytest.mark.asyncio
async def test_youtube_scrape_by_time_uses_date_order(monkeypatch):
    monkeypatch.setattr(settings.scraper, "youtube_api_key", "yt-key")
    scraper = YouTubeScraper()
    scraper._get_session = AsyncMock(return_value=object())
    scraper._search_videos = AsyncMock(return_value=["vid_1"])
    scraper._get_video_details = AsyncMock(
        return_value=[
            {
                "id": "vid_1",
                "snippet": {
                    "title": "yt title",
                    "description": "yt desc",
                    "publishedAt": "2026-02-19T01:00:00Z",
                    "channelTitle": "YT Channel",
                    "channelId": "ch_1",
                    "defaultLanguage": "en",
                    "thumbnails": {"high": {"url": "https://img.test/1.jpg"}},
                },
                "statistics": {"viewCount": "1000", "likeCount": "50", "commentCount": "20"},
            }
        ]
    )

    items = await scraper.scrape(
        query="robot",
        limit=5,
        capture_mode="by_time",
        start_time="2026-02-18T00:00:00Z",
        end_time="2026-02-19T00:00:00Z",
    )
    assert len(items) == 1
    item = items[0]
    assert item.source_id == "vid_1"
    assert item.engagement_score == 100.0  # 1000/100 + 50 + 20*2
    assert item.published_at == "2026-02-19T01:00:00Z"
    assert item.platform_metrics["view_count"] == 1000
    assert item.media_urls == ["https://img.test/1.jpg"]

    assert scraper._search_videos.await_count == 1
    _, kwargs = scraper._search_videos.call_args
    assert kwargs["order"] == "date"
    assert kwargs["start_time"] == "2026-02-18T00:00:00Z"
    assert kwargs["end_time"] == "2026-02-19T00:00:00Z"


@pytest.mark.asyncio
async def test_weibo_scrape_parses_hot_payload(monkeypatch):
    monkeypatch.setattr(settings.scraper, "weibo_access_token", "")
    scraper = WeiboScraper()
    session = _MockSession([
        _MockResponse(
            200,
            json_data={
                "data": {
                    "realtime": [
                        {"mid": 123, "word": "AIGC", "note": "AIGC爆发", "raw_hot": 8888},
                    ]
                }
            },
        )
    ])
    scraper._get_session = AsyncMock(return_value=session)

    items = await scraper.scrape(limit=1)
    assert len(items) == 1
    item = items[0]
    assert item.source_id == "123"
    assert item.engagement_score == 8888.0
    assert item.hashtags == ["#AIGC#"]
    assert item.platform_metrics["raw_hot"] == 8888


@pytest.mark.asyncio
async def test_bilibili_scrape_parses_stat_and_pubdate(monkeypatch):
    monkeypatch.setattr(settings.scraper, "bilibili_sessdata", "")
    scraper = BilibiliScraper()
    session = _MockSession([
        _MockResponse(
            200,
            json_data={
                "data": {
                    "list": [
                        {
                            "bvid": "BV1xx",
                            "title": "bili title",
                            "desc": "bili desc",
                            "pic": "https://img.bili/test.jpg",
                            "pubdate": 1760000000,
                            "owner": {"name": "UP", "mid": 9},
                            "stat": {"view": 10000, "like": 300, "reply": 20},
                        }
                    ]
                }
            },
        )
    ])
    scraper._get_session = AsyncMock(return_value=session)

    items = await scraper.scrape(limit=1)
    assert len(items) == 1
    item = items[0]
    assert item.source_id == "BV1xx"
    assert item.engagement_score == 440.0  # 10000/100 + 300 + 20*2
    assert item.platform_metrics["comment_count"] == 20
    assert item.media_urls == ["https://img.bili/test.jpg"]
    assert item.published_at != ""


@pytest.mark.asyncio
async def test_zhihu_scrape_parses_hot_score_and_created_at():
    scraper = ZhihuScraper()
    session = _MockSession([
        _MockResponse(
            200,
            json_data={
                "data": [
                    {
                        "detail_text": "12.3 万热度",
                        "target": {
                            "id": 321,
                            "title": "知乎问题",
                            "excerpt": "问题摘要",
                            "created": 1760000000,
                            "author": {"name": "答主"},
                        },
                    }
                ]
            },
        )
    ])
    scraper._get_session = AsyncMock(return_value=session)

    items = await scraper.scrape(limit=1)
    assert len(items) == 1
    item = items[0]
    assert item.source_id == "321"
    assert item.engagement_score == 123000.0
    assert item.platform_metrics["hot_score_raw"] == "12.3 万热度"
    assert item.published_at != ""


@pytest.mark.asyncio
async def test_github_scrape_returns_trending_and_release_channels(monkeypatch):
    monkeypatch.setattr(settings.scraper, "github_token", "ghp_test")
    monkeypatch.setattr(settings.scraper, "github_api_base_url", "https://api.github.test")

    def _responses(url, **kwargs):
        if url.endswith("/search/repositories"):
            return _MockResponse(
                200,
                json_data={
                    "items": [
                        {
                            "id": 11,
                            "full_name": "openai/openai-python",
                            "description": "Official Python library",
                            "html_url": "https://github.com/openai/openai-python",
                            "homepage": "https://platform.openai.com/docs",
                            "created_at": "2026-02-10T00:00:00Z",
                            "updated_at": "2026-02-19T00:00:00Z",
                            "stargazers_count": 10,
                            "forks_count": 2,
                            "watchers_count": 10,
                            "open_issues_count": 4,
                            "topics": ["ai", "python"],
                            "owner": {
                                "id": 101,
                                "login": "openai",
                                "avatar_url": "https://avatars.example/openai.png",
                            },
                        }
                    ]
                },
            )
        if url.endswith("/repos/openai/openai-python/releases"):
            return _MockResponse(
                200,
                json_data=[
                    {
                        "id": 1001,
                        "name": "v1.2.3",
                        "tag_name": "v1.2.3",
                        "body": "release notes",
                        "html_url": "https://github.com/openai/openai-python/releases/tag/v1.2.3",
                        "published_at": "2026-02-19T01:00:00Z",
                        "comments": 3,
                        "assets": [
                            {"download_count": 50},
                            {"download_count": 20},
                        ],
                        "reactions": {"+1": 5, "heart": 2},
                        "author": {"id": 101, "login": "openai"},
                    }
                ],
            )
        if url.endswith("/rate_limit"):
            return _MockResponse(200, json_data={})
        raise AssertionError(f"unexpected url: {url}")

    scraper = GitHubScraper()
    session = _MockSession(_responses)
    scraper._get_session = AsyncMock(return_value=session)

    items = await scraper.scrape(query="agent", limit=5, capture_mode="hybrid")
    assert len(items) == 2
    repo_item = next(i for i in items if i.source_channel == "github_trending")
    rel_item = next(i for i in items if i.source_channel == "github_release")

    assert repo_item.source_type == "repository"
    assert repo_item.source_id == "openai/openai-python"
    assert repo_item.platform_metrics["stars"] == 10
    assert repo_item.media_urls == ["https://avatars.example/openai.png"]

    assert rel_item.source_type == "release"
    assert rel_item.source_id == "openai/openai-python#release#1001"
    assert rel_item.platform_metrics["download_count"] == 70
    assert rel_item.engagement_score > 0


@pytest.mark.asyncio
async def test_github_scrape_by_time_builds_query_and_filters_releases(monkeypatch):
    monkeypatch.setattr(settings.scraper, "github_token", "ghp_test")
    monkeypatch.setattr(settings.scraper, "github_api_base_url", "https://api.github.test")

    def _responses(url, **kwargs):
        if url.endswith("/search/repositories"):
            return _MockResponse(
                200,
                json_data={
                    "items": [
                        {
                            "id": 12,
                            "full_name": "example/repo",
                            "description": "test repo",
                            "html_url": "https://github.com/example/repo",
                            "created_at": "2026-02-01T00:00:00Z",
                            "updated_at": "2026-02-19T00:00:00Z",
                            "stargazers_count": 100,
                            "forks_count": 10,
                            "watchers_count": 100,
                            "open_issues_count": 0,
                            "topics": [],
                            "owner": {"id": 201, "login": "example"},
                        }
                    ]
                },
            )
        if url.endswith("/repos/example/repo/releases"):
            return _MockResponse(
                200,
                json_data=[
                    {
                        "id": 2001,
                        "name": "v0.1.0",
                        "tag_name": "v0.1.0",
                        "body": "initial",
                        "html_url": "https://github.com/example/repo/releases/tag/v0.1.0",
                        "published_at": "2026-02-10T01:00:00Z",
                        "comments": 0,
                        "assets": [],
                        "reactions": {},
                        "author": {"id": 201, "login": "example"},
                    }
                ],
            )
        raise AssertionError(f"unexpected url: {url}")

    scraper = GitHubScraper()
    session = _MockSession(_responses)
    scraper._get_session = AsyncMock(return_value=session)

    items = await scraper.scrape(
        query="agent",
        limit=5,
        capture_mode="by_time",
        start_time="2026-02-18T00:00:00Z",
        end_time="2026-02-19T23:59:59Z",
    )

    assert len(items) == 1
    assert items[0].source_channel == "github_trending"

    search_params = session.calls[0]["params"]
    assert "pushed:2026-02-18..2026-02-19" in search_params["q"]


@pytest.mark.asyncio
async def test_github_scrape_new_channels_and_incremental_cursor_etag(monkeypatch):
    monkeypatch.setattr(settings.scraper, "github_token", "ghp_test")
    monkeypatch.setattr(settings.scraper, "github_api_base_url", "https://api.github.test")

    state = {"round": 1}

    def _responses(url, **kwargs):
        headers = kwargs.get("headers", {}) or {}
        params = kwargs.get("params", {}) or {}
        query = str(params.get("q", ""))

        if state["round"] == 2:
            # second round must reuse ETag
            assert "If-None-Match" in headers

        if url.endswith("/search/repositories"):
            payload = {
                "items": [
                    {
                        "id": 11,
                        "full_name": "openai/openai-python",
                        "description": "Official Python library",
                        "html_url": "https://github.com/openai/openai-python",
                        "homepage": "https://platform.openai.com/docs",
                        "created_at": "2026-02-10T00:00:00Z",
                        "updated_at": "2026-02-19T00:00:00Z",
                        "pushed_at": "2026-02-19T00:00:00Z",
                        "stargazers_count": 100,
                        "forks_count": 20,
                        "watchers_count": 100,
                        "open_issues_count": 10,
                        "topics": ["ai", "python"],
                        "owner": {"id": 101, "login": "openai"},
                    }
                ]
            }
            return _MockResponse(200, json_data=payload, headers={"ETag": "repo-v1"})

        if url.endswith("/repos/openai/openai-python/releases"):
            if state["round"] == 1:
                return _MockResponse(
                    200,
                    json_data=[
                        {
                            "id": 1001,
                            "name": "v1.2.3",
                            "tag_name": "v1.2.3",
                            "body": "release notes",
                            "html_url": "https://github.com/openai/openai-python/releases/tag/v1.2.3",
                            "published_at": "2026-02-19T01:00:00Z",
                            "comments": 3,
                            "assets": [{"download_count": 50}],
                            "reactions": {"+1": 5},
                            "author": {"id": 101, "login": "openai"},
                        }
                    ],
                    headers={"ETag": "rel-v1"},
                )
            return _MockResponse(304, json_data={}, headers={"ETag": "rel-v1"})

        if url.endswith("/search/issues") and "is:issue" in query:
            if state["round"] == 1:
                return _MockResponse(
                    200,
                    json_data={
                        "items": [
                            {
                                "id": 2001,
                                "number": 77,
                                "title": "Issue title",
                                "body": "Issue body",
                                "html_url": "https://github.com/openai/openai-python/issues/77",
                                "repository_url": "https://api.github.test/repos/openai/openai-python",
                                "updated_at": "2026-02-19T02:00:00Z",
                                "comments": 8,
                                "state": "open",
                                "user": {"id": 101, "login": "openai"},
                            }
                        ]
                    },
                    headers={"ETag": "issue-v1"},
                )
            return _MockResponse(304, json_data={}, headers={"ETag": "issue-v1"})

        if url.endswith("/search/issues") and "is:pr" in query:
            if state["round"] == 1:
                return _MockResponse(
                    200,
                    json_data={
                        "items": [
                            {
                                "id": 3001,
                                "number": 99,
                                "title": "PR title",
                                "body": "PR body",
                                "html_url": "https://github.com/openai/openai-python/pull/99",
                                "repository_url": "https://api.github.test/repos/openai/openai-python",
                                "updated_at": "2026-02-19T03:00:00Z",
                                "comments": 5,
                                "state": "open",
                                "user": {"id": 101, "login": "openai"},
                            }
                        ]
                    },
                    headers={"ETag": "pr-v1"},
                )
            return _MockResponse(304, json_data={}, headers={"ETag": "pr-v1"})

        if url.endswith("/repos/openai/openai-python/discussions"):
            if state["round"] == 1:
                return _MockResponse(
                    200,
                    json_data=[
                        {
                            "id": 4001,
                            "number": 12,
                            "title": "Discussion title",
                            "body": "Discussion body",
                            "html_url": "https://github.com/openai/openai-python/discussions/12",
                            "updated_at": "2026-02-19T04:00:00Z",
                            "comments": 4,
                            "upvote_count": 6,
                            "user": {"id": 101, "login": "openai"},
                            "category": {"name": "Q&A"},
                        }
                    ],
                    headers={"ETag": "disc-v1"},
                )
            return _MockResponse(304, json_data={}, headers={"ETag": "disc-v1"})

        if url.endswith("/advisories"):
            if state["round"] == 1:
                return _MockResponse(
                    200,
                    json_data=[
                        {
                            "ghsa_id": "GHSA-xxxx-yyyy-zzzz",
                            "summary": "OpenAI critical vuln",
                            "description": "Security advisory",
                            "severity": "critical",
                            "updated_at": "2026-02-19T05:00:00Z",
                            "html_url": "https://github.com/advisories/GHSA-xxxx-yyyy-zzzz",
                            "cvss": {"score": 9.8},
                            "epss": {"percentage": 0.7},
                            "cves": ["CVE-2026-0001"],
                        }
                    ],
                    headers={"ETag": "adv-v1"},
                )
            return _MockResponse(304, json_data={}, headers={"ETag": "adv-v1"})

        raise AssertionError(f"unexpected url: {url}")

    scraper = GitHubScraper()
    session = _MockSession(_responses)
    scraper._get_session = AsyncMock(return_value=session)

    first = await scraper.scrape(query="openai", limit=10, capture_mode="hybrid")
    channels = {item.source_channel for item in first}
    assert "github_trending" in channels
    assert "github_release" in channels
    assert "github_issue" in channels
    assert "github_pull_request" in channels
    assert "github_discussion" in channels
    assert "github_security_advisory" in channels

    # round 2: ETag conditional requests + updated_at cursor should avoid duplicate outputs
    state["round"] = 2
    second = await scraper.scrape(query="openai", limit=10, capture_mode="hybrid")
    assert second == []
