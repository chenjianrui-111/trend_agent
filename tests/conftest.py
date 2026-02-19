"""
Test fixtures
"""

import asyncio
import pytest
from typing import List, Dict

from trend_agent.models.message import AgentMessage, TrendItem, ContentDraftMsg
from trend_agent.services.content_store import ContentRepository


@pytest.fixture
def sample_trend_items() -> List[Dict]:
    return [
        TrendItem(
            item_id="test_001",
            source_platform="twitter",
            source_id="tw_123",
            source_url="https://twitter.com/test/123",
            title="OpenAI releases GPT-5",
            description="OpenAI has announced the release of GPT-5, featuring significant improvements in reasoning and coding.",
            author="OpenAI",
            language="en",
            engagement_score=50000,
            category="",
        ).__dict__,
        TrendItem(
            item_id="test_002",
            source_platform="weibo",
            source_id="wb_456",
            source_url="https://weibo.com/test/456",
            title="春节档电影票房创新高",
            description="2026年春节档总票房突破100亿元，刷新历史纪录。",
            author="电影资讯",
            language="zh",
            engagement_score=80000,
            category="",
        ).__dict__,
        TrendItem(
            item_id="test_003",
            source_platform="youtube",
            source_id="yt_789",
            source_url="https://youtube.com/watch?v=789",
            title="Bitcoin reaches $200K milestone",
            description="Bitcoin has surpassed the $200,000 mark for the first time, driven by institutional adoption.",
            author="CryptoNews",
            language="en",
            engagement_score=30000,
            category="",
        ).__dict__,
    ]


@pytest.fixture
def sample_categorized_items(sample_trend_items) -> List[Dict]:
    categories = ["AI", "娱乐", "财经"]
    for item, cat in zip(sample_trend_items, categories):
        item["category"] = cat
        item["confidence"] = 0.9
        item["tags"] = [f"#{cat}"]
    return sample_trend_items


@pytest.fixture
def sample_drafts() -> List[Dict]:
    return [
        ContentDraftMsg(
            draft_id="draft_001",
            source_item_id="test_001",
            target_platform="wechat",
            title="GPT-5来了！AI行业又将迎来巨变",
            body="OpenAI发布了GPT-5，在推理和编程能力上有显著提升...",
            summary="OpenAI发布GPT-5",
            hashtags=["#AI", "#GPT5"],
            language="zh",
        ).__dict__,
        ContentDraftMsg(
            draft_id="draft_002",
            source_item_id="test_002",
            target_platform="xiaohongshu",
            title="春节档票房破百亿！这些电影你看了吗？",
            body="春节档总票房突破100亿...",
            summary="春节档票房创新高",
            hashtags=["#春节档", "#电影"],
            language="zh",
        ).__dict__,
    ]


@pytest.fixture
def agent_message(sample_trend_items) -> AgentMessage:
    return AgentMessage(
        sender="test",
        payload={"items": sample_trend_items},
        trace_id="test-trace-001",
    )


@pytest.fixture
async def content_repo():
    """In-memory SQLite content repository for testing."""
    repo = ContentRepository(db_url="sqlite+aiosqlite:///:memory:")
    await repo.init_db()
    yield repo
    await repo.close()
