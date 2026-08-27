"""Rotating file + console logging (stdlib only). Idempotent."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

_CONFIGURED = False


def configure_logging(cfg: dict) -> logging.Logger:
    global _CONFIGURED
    root = logging.getLogger()
    if _CONFIGURED:
        return root

    lg = cfg.get("logging", {})
    level = getattr(logging, str(lg.get("level", "INFO")).upper(), logging.INFO)
    root.setLevel(level)

    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S")

    log_path = Path(cfg["paths"]["logs"]) / "app.log"
    fh = RotatingFileHandler(
        log_path, maxBytes=int(lg.get("max_bytes", 1_048_576)),
        backupCount=int(lg.get("backups", 5)), encoding="utf-8",
    )
    fh.setFormatter(fmt)
    root.addHandler(fh)

    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    root.addHandler(ch)

    _CONFIGURED = True
    root.info("Logging configured -> %s", log_path)
    return root
