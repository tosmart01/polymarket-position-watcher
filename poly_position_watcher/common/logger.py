"""Lightweight logger used throughout the position watcher package."""

from __future__ import annotations

import logging
import os
from typing import Any

_LOG_LEVEL = os.getenv("poly_position_watcher_LOG_LEVEL", "INFO").upper()


class _BraceAdapter:
    """Simple adapter that supports ``logger.info("foo {}", bar)`` formatting."""

    def __init__(self) -> None:
        logging.basicConfig(
            level=getattr(logging, _LOG_LEVEL, logging.INFO),
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )
        self._logger = logging.getLogger("poly_position_watcher")

    def _log(self, level: int, msg: str, *args: Any, **kwargs: Any) -> None:
        if args or kwargs:
            try:
                msg = msg.format(*args, **kwargs)
            except Exception:  # pragma: no cover - fallback to raw message
                msg = " ".join([msg, *map(str, args)])
        self._logger.log(level, msg, **kwargs)

    def debug(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._log(logging.DEBUG, msg, *args, **kwargs)

    def info(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._log(logging.INFO, msg, *args, **kwargs)

    def warning(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._log(logging.WARNING, msg, *args, **kwargs)

    def error(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._log(logging.ERROR, msg, *args, **kwargs)

    def exception(self, msg: str, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("exc_info", True)
        self._log(logging.ERROR, msg, *args, **kwargs)


logger = _BraceAdapter()

__all__ = ["logger"]
