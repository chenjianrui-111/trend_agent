"""
Agent 抽象基类 - 所有子 Agent 的统一接口
"""

import logging
from abc import ABC, abstractmethod

from trend_agent.models.message import AgentMessage

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """
    Agent 抽象基类

    所有子 Agent 必须实现 process 方法。
    通过 __call__ 调用时自动包含错误处理。
    """

    def __init__(self, name: str):
        self.name = name
        self._initialized = False
        self.logger = logging.getLogger(f"agent.{name}")

    async def __call__(self, message: AgentMessage) -> AgentMessage:
        """统一调用入口 - 包含错误处理"""
        try:
            return await self.process(message)
        except Exception as e:
            self.logger.error(f"[{self.name}] Processing failed: {e}", exc_info=True)
            return message.create_error(
                error_code=f"{self.name}_error",
                error_msg=str(e),
            )

    @abstractmethod
    async def process(self, message: AgentMessage) -> AgentMessage:
        """处理消息 - 子类必须实现"""
        ...

    async def startup(self):
        """Agent 启动钩子"""
        self._initialized = True
        self.logger.info(f"[{self.name}] Started")

    async def shutdown(self):
        """Agent 关闭钩子"""
        self._initialized = False
        self.logger.info(f"[{self.name}] Shut down")
