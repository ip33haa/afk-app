"""Log state changes only. Never log passwords or face embeddings."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from app.paths import data_dir


def setup() -> logging.Logger:
    logger = logging.getLogger("afk")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if logger.handlers:
        return logger
    handler = RotatingFileHandler(
        data_dir() / "afk.log",
        maxBytes=1_000_000,
        backupCount=2,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    return logger
