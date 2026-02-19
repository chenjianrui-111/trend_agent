"""
微博发布器 - 微博开放平台 API
"""

import logging
from typing import Dict

from trend_agent.config.settings import settings
from trend_agent.models.message import PublishResult
from trend_agent.publishers.base import BasePublisher

logger = logging.getLogger(__name__)


class WeiboPublisher(BasePublisher):
    """微博开放平台发布器"""

    name = "weibo"
    BASE_URL = "https://api.weibo.com/2"

    async def publish(self, draft: Dict) -> PublishResult:
        """发布微博"""
        if not settings.publisher.weibo_publish_token:
            return PublishResult(
                draft_id=draft.get("draft_id", ""),
                platform="weibo",
                success=False,
                error="Weibo publish token not configured",
            )

        try:
            session = await self._get_session()

            # Build status text with hashtags
            body = draft.get("body", "")
            hashtags = draft.get("hashtags", [])
            status = body
            if hashtags:
                tags_str = " ".join(hashtags[:3])
                status = f"{body}\n{tags_str}"

            # Ensure within Weibo character limit
            if len(status) > 2000:
                status = status[:1997] + "..."

            payload = {
                "access_token": settings.publisher.weibo_publish_token,
                "status": status,
            }

            async with session.post(
                f"{self.BASE_URL}/statuses/share.json",
                data=payload,
            ) as resp:
                data = await resp.json()
                if "id" in data:
                    weibo_id = str(data["id"])
                    return PublishResult(
                        draft_id=draft.get("draft_id", ""),
                        platform="weibo",
                        success=True,
                        platform_post_id=weibo_id,
                        platform_url=f"https://weibo.com/{data.get('user', {}).get('id', '')}/{weibo_id}",
                    )
                else:
                    return PublishResult(
                        draft_id=draft.get("draft_id", ""),
                        platform="weibo",
                        success=False,
                        error=data.get("error", str(data)),
                    )

        except Exception as e:
            logger.error("Weibo publish failed: %s", e)
            return PublishResult(
                draft_id=draft.get("draft_id", ""),
                platform="weibo",
                success=False,
                error=str(e),
            )

    async def validate_auth(self) -> bool:
        return bool(settings.publisher.weibo_publish_token)
