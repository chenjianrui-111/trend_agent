"""
抖音发布器 - 抖音开放平台 API
"""

import logging
from typing import Dict

from trend_agent.config.settings import settings
from trend_agent.models.message import PublishResult
from trend_agent.publishers.base import BasePublisher

logger = logging.getLogger(__name__)


class DouyinPublisher(BasePublisher):
    """抖音开放平台发布器"""

    name = "douyin"
    BASE_URL = "https://open.douyin.com"

    async def publish(self, draft: Dict) -> PublishResult:
        """发布内容到抖音"""
        if not settings.publisher.douyin_access_token:
            return PublishResult(
                draft_id=draft.get("draft_id", ""),
                platform="douyin",
                success=False,
                error="Douyin access token not configured",
            )

        try:
            session = await self._get_session()
            video_url = draft.get("video_url", "")

            if video_url:
                # Publish video
                return await self._publish_video(session, draft, video_url)
            else:
                # Publish image/text post
                return await self._publish_note(session, draft)

        except Exception as e:
            logger.error("Douyin publish failed: %s", e)
            return PublishResult(
                draft_id=draft.get("draft_id", ""),
                platform="douyin",
                success=False,
                error=str(e),
            )

    async def _publish_video(self, session, draft: Dict, video_url: str) -> PublishResult:
        """Publish video to Douyin."""
        headers = {
            "Authorization": f"Bearer {settings.publisher.douyin_access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "video_url": video_url,
            "text": draft.get("body", "")[:300],
            "poi_id": "",
            "micro_app_info": {},
        }
        async with session.post(
            f"{self.BASE_URL}/api/douyin/v1/video/create_by_url/",
            json=payload, headers=headers,
        ) as resp:
            data = await resp.json()
            if data.get("data", {}).get("error_code", -1) == 0:
                item_id = data.get("data", {}).get("item_id", "")
                return PublishResult(
                    draft_id=draft.get("draft_id", ""),
                    platform="douyin",
                    success=True,
                    platform_post_id=item_id,
                )
            return PublishResult(
                draft_id=draft.get("draft_id", ""),
                platform="douyin",
                success=False,
                error=data.get("data", {}).get("description", "Unknown error"),
            )

    async def _publish_note(self, session, draft: Dict) -> PublishResult:
        """Publish text/image note to Douyin."""
        headers = {
            "Authorization": f"Bearer {settings.publisher.douyin_access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "title": draft.get("title", ""),
            "text": draft.get("body", "")[:300],
        }
        async with session.post(
            f"{self.BASE_URL}/api/douyin/v1/note/publish/",
            json=payload, headers=headers,
        ) as resp:
            data = await resp.json()
            item_id = data.get("data", {}).get("item_id", "")
            success = data.get("data", {}).get("error_code", -1) == 0
            return PublishResult(
                draft_id=draft.get("draft_id", ""),
                platform="douyin",
                success=success,
                platform_post_id=item_id,
                error="" if success else data.get("data", {}).get("description", ""),
            )

    async def validate_auth(self) -> bool:
        return bool(settings.publisher.douyin_access_token)
