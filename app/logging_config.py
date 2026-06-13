"""Non-blocking logging configuration for the async application.

The request path is fully async, so synchronous file writes from
``logging.FileHandler`` would block the event loop under load. This module
routes all log records through an in-memory queue that a background thread
drains into a rotating file handler, keeping the event loop free of disk I/O.
"""

from __future__ import annotations

import logging
import queue
from logging.handlers import QueueHandler, QueueListener, RotatingFileHandler

_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_MAX_BYTES = 10 * 1024 * 1024
_BACKUP_COUNT = 5


def configure_logging(
    level: str = "INFO",
    log_file: str = "app.log",
) -> QueueListener:
    """Install a non-blocking, rotating logging pipeline on the root logger.

    Returns the started ``QueueListener`` so the caller can stop it cleanly
    during application shutdown.
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    log_queue: queue.Queue = queue.Queue(-1)
    queue_handler = QueueHandler(log_queue)

    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    for existing_handler in root_logger.handlers[:]:
        root_logger.removeHandler(existing_handler)
    root_logger.addHandler(queue_handler)

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(logging.Formatter(_LOG_FORMAT))

    listener = QueueListener(log_queue, file_handler, respect_handler_level=True)
    listener.start()
    return listener