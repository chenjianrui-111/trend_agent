"""
小红书发布器 - 小红书开放平台 API
"""

import logging
from typing import Dict

from trend_agent.config.settings import settings
from trend_agent.models.message import PublishResult
from trend_agent.publishers.base import BasePublisher

logger = logging.getLogger(__name__)


class XiaohongshuPublisher(BasePublisher):
    """小红书笔记发布器"""

    name = "xiaohongshu"

    async def publish(self, draft: Dict) -> PublishResult:
        """发布笔记到小红书"""
        if not settings.publisher.xiaohongshu_cookie:
            return PublishResult(
                draft_id=draft.get("draft_id", ""),
                platform="xiaohongshu",
                success=False,
                error="Xiaohongshu credentials not configured",
            )

        try:
            session = await self._get_session()

            # Xiaohongshu publish API (simplified)
            # Note: Real implementation requires OAuth2 or cookie-based auth
            payload = {
                "title": draft.get("title", ""),
                "desc": draft.get("body", ""),
                "hash_tag": draft.get("hashtags", []),
            }

            headers = {
                "Cookie": settings.publisher.xiaohongshu_cookie,
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0",
            }

            # Xiaohongshu web API endpoint
            async with session.post(
                "https://edith.xiaohongshu.com/api/sns/web/v1/feed/create",
                json=payload,
                headers=headers,
            ) as resp:
                data = await resp.json()
                if data.get("success") or data.get("code") == 0:
                    note_id = data.get("data", {}).get("note_id", "")
                    return PublishResult(
                        draft_id=draft.get("draft_id", ""),
                        platform="xiaohongshu",
                        success=True,
                        platform_post_id=note_id,
                        platform_url=f"https://www.xiaohongshu.com/explore/{note_id}" if note_id else "",
                    )
                else:
                    return PublishResult(
                        draft_id=draft.get("draft_id", ""),
                        platform="xiaohongshu",
                        success=False,
                        error=data.get("msg", str(data)),
                    )

        except Exception as e:
            logger.error("Xiaohongshu publish failed: %s", e)
            return PublishResult(
                draft_id=draft.get("draft_id", ""),
                platform="xiaohongshu",
                success=False,
                error=str(e),
            )

    async def validate_auth(self) -> bool:
        return bool(settings.publisher.xiaohongshu_cookie)
