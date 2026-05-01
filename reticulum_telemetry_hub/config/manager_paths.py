"""Path helpers shared by configuration modules."""

from __future__ import annotations

import os
from pathlib import Path


def _expand_user_path(value: Path | str) -> Path:
    """Expand user paths honoring HOME overrides on Windows."""

    value_str = str(value)
    if value_str.startswith("~"):
        home = os.environ.get("HOME")
        if home:
            tail = value_str[1:]
            if tail.startswith(("/", "\\")):
                tail = tail[1:]
            return Path(home) / tail
    return Path(value_str).expanduser()

