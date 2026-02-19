"""
工作流状态枚举
"""

from enum import Enum


class WorkflowState(str, Enum):
    INIT = "INIT"
    SCRAPING = "SCRAPING"
    CATEGORIZING = "CATEGORIZING"
    SUMMARIZING = "SUMMARIZING"
    QUALITY_CHECKING = "QUALITY_CHECKING"
    VIDEO_GENERATING = "VIDEO_GENERATING"
    PUBLISHING = "PUBLISHING"
    COMPLETED = "COMPLETED"
    ERROR = "ERROR"
    PAUSED = "PAUSED"
    PARTIALLY_COMPLETED = "PARTIALLY_COMPLETED"


class ContentStatus(str, Enum):
    SCRAPED = "scraped"
    CATEGORIZED = "categorized"
    SUMMARIZED = "summarized"
    QUALITY_CHECKED = "quality_checked"
    VIDEO_PENDING = "video_pending"
    VIDEO_READY = "video_ready"
    PUBLISHED = "published"
    REJECTED = "rejected"
    FAILED = "failed"
