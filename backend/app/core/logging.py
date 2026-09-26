"""Structured logging configuration."""

import logging
import sys
from typing import Any, Dict


def setup_logging(debug: bool = False) -> logging.Logger:
    """Configure and return the root application logger."""
    level = logging.DEBUG if debug else logging.INFO

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    logger = logging.getLogger("crop_risk_api")
    logger.setLevel(level)

    if not logger.handlers:
        logger.addHandler(handler)

    return logger


logger = setup_logging()
