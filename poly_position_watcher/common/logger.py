import os
import sys

from loguru import logger

_LOG_LEVEL = os.getenv("poly_position_watcher_LOG_LEVEL", "INFO").upper()


def setup_logger() -> None:
    logger.remove()
    log_levels = {
        "DEBUG": "DEBUG",
        "INFO": "INFO",
        "WARNING": "WARNING",
        "ERROR": "ERROR",
        "CRITICAL": "CRITICAL"
    }

    level = log_levels.get(_LOG_LEVEL, "INFO")

    # 配置控制台输出
    logger.add(
        sys.stdout,
        level=level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
               "<level>{level: <8}</level> | "
               "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
               "<level>{message}</level>",
        colorize=True,
        backtrace=True,
        diagnose=True,
    )


setup_logger()
