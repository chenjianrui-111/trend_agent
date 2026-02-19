"""
数据模型 - Agent 间消息传递的数据结构
"""

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class TrendItem:
    """原始抓取的热门条目"""
    item_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source_platform: str = ""       # twitter, youtube, weibo, bilibili, zhihu
    source_id: str = ""             # 平台原生 ID
    source_url: str = ""
    title: str = ""
    description: str = ""
    author: str = ""
    author_id: str = ""
    language: str = "zh"
    engagement_score: float = 0.0   # 综合互动分 (likes + shares + comments)
    category: str = ""              # 由 CategorizerAgent 填充
    subcategory: str = ""
    confidence: float = 0.0         # 分类置信度
    tags: List[str] = field(default_factory=list)
    media_urls: List[str] = field(default_factory=list)
    scraped_at: str = ""
    raw_data: Dict[str, Any] = field(default_factory=dict)
    content_hash: str = ""          # 内容去重 hash


@dataclass
class ContentDraftMsg:
    """平台定制化内容草稿"""
    draft_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source_item_id: str = ""
    target_platform: str = ""       # wechat, xiaohongshu, douyin, weibo
    title: str = ""
    body: str = ""
    summary: str = ""
    hashtags: List[str] = field(default_factory=list)
    media_urls: List[str] = field(default_factory=list)
    video_url: str = ""
    video_provider: str = ""
    language: str = "zh"
    quality_score: float = 0.0
    quality_passed: bool = False
    quality_issues: List[str] = field(default_factory=list)


@dataclass
class QualityResult:
    """质量检查结果"""
    passed: bool = True
    overall_score: float = 0.0
    sensitive_words: List[str] = field(default_factory=list)
    compliance_issues: List[str] = field(default_factory=list)
    originality_score: float = 1.0
    suggestions: List[str] = field(default_factory=list)


@dataclass
class PublishResult:
    """发布结果"""
    draft_id: str = ""
    platform: str = ""
    success: bool = False
    platform_post_id: str = ""
    platform_url: str = ""
    error: str = ""


@dataclass
class VideoResult:
    """视频生成结果"""
    draft_id: str = ""
    provider: str = ""
    task_id: str = ""
    status: str = "pending"     # pending, processing, completed, failed
    video_url: str = ""
    error: str = ""


@dataclass
class AgentMessage:
    """Agent 间通信的统一消息格式"""
    msg_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    sender: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    error_code: str = ""
    error_msg: str = ""
    trace_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def has_error(self) -> bool:
        return bool(self.error_code)

    def create_error(self, error_code: str, error_msg: str) -> "AgentMessage":
        return AgentMessage(
            sender=self.sender,
            error_code=error_code,
            error_msg=error_msg,
            trace_id=self.trace_id,
        )

    def create_reply(self, sender: str, payload: Optional[Dict] = None) -> "AgentMessage":
        return AgentMessage(
            sender=sender,
            payload=payload or {},
            trace_id=self.trace_id,
        )
