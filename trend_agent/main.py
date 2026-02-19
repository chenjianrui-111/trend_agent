"""
TrendAgent 入口
"""

import logging
import uvicorn

from trend_agent.config.settings import settings

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
)


def main():
    uvicorn.run(
        "trend_agent.api.app:app",
        host=settings.host,
        port=settings.port,
        reload=settings.env == "development",
        log_level="info",
    )


if __name__ == "__main__":
    main()
