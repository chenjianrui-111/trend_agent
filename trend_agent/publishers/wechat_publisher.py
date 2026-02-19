"""
微信公众号发布器 - 使用微信公众平台 API
"""

import logging
import time
from typing import Dict, Optional

from trend_agent.config.settings import settings
from trend_agent.models.message import PublishResult
from trend_agent.publishers.base import BasePublisher

logger = logging.getLogger(__name__)


class WechatPublisher(BasePublisher):
    """微信公众号 API 发布器"""

    name = "wechat"
    BASE_URL = "https://api.weixin.qq.com/cgi-bin"

    def __init__(self):
        super().__init__()
        self._access_token: str = ""
        self._token_expires_at: float = 0

    async def _ensure_token(self):
        """获取/刷新 access_token"""
        if self._access_token and time.time() < self._token_expires_at:
            return

        if not settings.publisher.wechat_app_id or not settings.publisher.wechat_app_secret:
            raise ValueError("WeChat app_id or app_secret not configured")

        session = await self._get_session()
        params = {
            "grant_type": "client_credential",
            "appid": settings.publisher.wechat_app_id,
            "secret": settings.publisher.wechat_app_secret,
        }
        async with session.get(f"{self.BASE_URL}/token", params=params) as resp:
            data = await resp.json()
            if "access_token" in data:
                self._access_token = data["access_token"]
                self._token_expires_at = time.time() + data.get("expires_in", 7200) - 300
            else:
                raise ValueError(f"WeChat token error: {data.get('errmsg', 'unknown')}")

    async def publish(self, draft: Dict) -> PublishResult:
        """发布草稿文章到微信公众号"""
        try:
            await self._ensure_token()
            session = await self._get_session()

            # Step 1: Add draft article
            article = {
                "articles": [{
                    "title": draft.get("title", ""),
                    "content": draft.get("body", ""),
                    "digest": draft.get("summary", "")[:120],
                    "content_source_url": "",
                    "need_open_comment": 0,
                    "only_fans_can_comment": 0,
                }]
            }

            async with session.post(
                f"{self.BASE_URL}/draft/add",
                params={"access_token": self._access_token},
                json=article,
            ) as resp:
                data = await resp.json()
                if data.get("errcode", 0) != 0:
                    return PublishResult(
                        draft_id=draft.get("draft_id", ""),
                        platform="wechat",
                        success=False,
                        error=data.get("errmsg", "Unknown error"),
                    )

                media_id = data.get("media_id", "")

            return PublishResult(
                draft_id=draft.get("draft_id", ""),
                platform="wechat",
                success=True,
                platform_post_id=media_id,
            )

        except Exception as e:
            logger.error("WeChat publish failed: %s", e)
            return PublishResult(
                draft_id=draft.get("draft_id", ""),
                platform="wechat",
                success=False,
                error=str(e),
            )

    async def validate_auth(self) -> bool:
        try:
            await self._ensure_token()
            return bool(self._access_token)
        except Exception:
            return False
