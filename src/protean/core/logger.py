"""Logging setup: a rotating file only in `logs/` beside src/. Call once from main()."""

import logging
from logging.handlers import RotatingFileHandler

from protean import config

FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def setup_logging() -> None:
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    file = RotatingFileHandler(
        config.LOG_FILE,
        maxBytes=config.LOG_MAX_BYTES,
        backupCount=config.LOG_BACKUPS,
        encoding="utf-8",
    )
    logging.basicConfig(level=logging.INFO, format=FORMAT, handlers=[file], force=True)
