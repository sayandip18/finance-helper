import json
import logging
import os
from datetime import datetime, timezone

_LOG_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
_LOG_PATH = os.path.join(_LOG_DIR, "events.log")


def _build_logger() -> logging.Logger:
    logger = logging.getLogger("finance_helper")
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)
    os.makedirs(_LOG_DIR, exist_ok=True)
    fmt = logging.Formatter("%(message)s")
    fh = logging.FileHandler(_LOG_PATH, encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(sh)
    logger.propagate = False
    return logger


_logger = _build_logger()


def log_event(**kwargs) -> None:
    payload = {"ts": datetime.now(timezone.utc).isoformat(), **kwargs}
    _logger.info(json.dumps(payload, ensure_ascii=False, default=str))
