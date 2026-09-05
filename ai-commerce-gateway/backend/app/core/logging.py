import logging
import sys

from app.core.config import get_settings

settings = get_settings()


def setup_logging() -> None:
    level = logging.DEBUG if settings.ENVIRONMENT == "development" else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


setup_logging()
logger = logging.getLogger("ai_commerce_gateway")
