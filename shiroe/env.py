"""Environment-variable reads for the current Shiroe runtime."""

from __future__ import annotations

import os

__all__ = ["getenv", "PREFIX"]

PREFIX = "SHIROE_"


def getenv(name: str, default: str | None = None) -> str | None:
    """Read ``SHIROE_<name>``.

    ``name`` is the suffix without a prefix, e.g. ``ALLOW_NETWORK``.
    """
    return os.environ.get(PREFIX + name, default)
