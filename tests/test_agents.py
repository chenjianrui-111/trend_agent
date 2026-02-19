"""
Tests for agent components.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from trend_agent.agents.categorizer_agent import CategorizerAgent
from trend_agent.agents.summarizer_agent import SummarizerAgent
from trend_agent.agents.quality_agent import QualityAgent
from trend_agent.models.message import AgentMessage


class TestCategorizerAgent:
    @pytest.mark.asyncio
    async def test_categorize_items(self, sample_trend_items):
        mock_llm = MagicMock()
        mock_llm.generate_sync = AsyncMock(return_value=json.dumps([
            {"id": 1, "category": "AI", "tags": ["GPT", "OpenAI"], "confidence": 0.95},
            {"id": 2, "category": "娱乐", "tags": ["电影", "票房"], "confidence": 0.9},
            {"id": 3, "category": "财经", "tags": ["Bitcoin"], "confidence": 0.85},
        ]))

        agent = CategorizerAgent(mock_llm)
        msg = AgentMessage(payload={"items": sample_trend_items})
        result = await agent.process(msg)

        items = result.payload["items"]
        assert len(items) == 3
        assert items[0]["category"] == "AI"
        assert items[1]["category"] == "娱乐"
        assert items[2]["category"] == "财经"

    @pytest.mark.asyncio
    async def test_categorize_invalid_response(self, sample_trend_items):
        mock_llm = MagicMock()
        mock_llm.generate_sync = AsyncMock(return_value="invalid json response")

        agent = CategorizerAgent(mock_llm)
        msg = AgentMessage(payload={"items": sample_trend_items})
        result = await agent.process(msg)

        items = result.payload["items"]
        assert len(items) == 3
        # Should fallback to "其他"
        for item in items:
            assert item["category"] == "其他"

    @pytest.mark.asyncio
    async def test_categorize_empty(self):
        mock_llm = MagicMock()
        agent = CategorizerAgent(mock_llm)
        msg = AgentMessage(payload={"items": []})
        result = await agent.process(msg)
        assert result.payload["items"] == []


class TestSummarizerAgent:
    @pytest.mark.asyncio
    async def test_summarize_for_wechat(self, sample_categorized_items):
        mock_llm = MagicMock()
        mock_llm.generate_sync = AsyncMock(return_value=json.dumps({
            "title": "AI突破性进展",
            "body": "详细内容...",
            "summary": "GPT-5发布",
            "hashtags": ["#AI"],
        }))

        agent = SummarizerAgent(mock_llm)
        msg = AgentMessage(payload={
            "items": sample_categorized_items[:1],
            "target_platforms": ["wechat"],
        })
        result = await agent.process(msg)

        drafts = result.payload["drafts"]
        assert len(drafts) == 1
        assert drafts[0]["target_platform"] == "wechat"
        assert drafts[0]["title"] == "AI突破性进展"

    @pytest.mark.asyncio
    async def test_summarize_multi_platform(self, sample_categorized_items):
        mock_llm = MagicMock()
        mock_llm.generate_sync = AsyncMock(return_value=json.dumps({
            "title": "标题",
            "body": "内容",
            "summary": "摘要",
            "hashtags": [],
        }))

        agent = SummarizerAgent(mock_llm)
        msg = AgentMessage(payload={
            "items": sample_categorized_items[:1],
            "target_platforms": ["wechat", "weibo"],
        })
        result = await agent.process(msg)

        drafts = result.payload["drafts"]
        assert len(drafts) == 2

    @pytest.mark.asyncio
    async def test_summarize_contains_generation_metadata(self, sample_categorized_items):
        mock_llm = MagicMock()
        mock_llm.generate_sync = AsyncMock(return_value=json.dumps({
            "title": "符合约束的标题测试内容",
            "body": "这是一段用于测试的正文内容。" * 120,
            "summary": "摘要内容",
            "hashtags": ["#AI"],
        }))

        agent = SummarizerAgent(mock_llm)
        msg = AgentMessage(payload={
            "items": sample_categorized_items[:1],
            "target_platforms": ["wechat"],
        })
        result = await agent.process(msg)
        drafts = result.payload["drafts"]
        assert len(drafts) == 1
        assert "generation_meta" in drafts[0]
        assert "prompt_hash" in drafts[0]["generation_meta"]


class TestQualityAgent:
    @pytest.mark.asyncio
    async def test_quality_pass(self, sample_drafts):
        mock_llm = MagicMock()
        agent = QualityAgent(mock_llm)
        # Override min body length for test
        agent._sensitive_words = set()

        msg = AgentMessage(payload={"drafts": sample_drafts})
        result = await agent.process(msg)

        drafts = result.payload["drafts"]
        quality = result.payload["quality_results"]
        assert len(drafts) == 2
        assert len(quality) == 2

    @pytest.mark.asyncio
    async def test_quality_sensitive_word(self):
        mock_llm = MagicMock()
        agent = QualityAgent(mock_llm)
        agent._sensitive_words = {"敏感词"}

        draft = {
            "draft_id": "d1",
            "title": "标题",
            "body": "这里包含敏感词在内容中" + "x" * 200,
            "target_platform": "wechat",
        }
        msg = AgentMessage(payload={"drafts": [draft]})
        result = await agent.process(msg)

        quality = result.payload["quality_results"]
        assert not quality[0]["passed"]
        assert "敏感词" in quality[0]["sensitive_words"]
