"""Internal serialization helpers shared by Repository implementations.

Not a layer of its own — a private convenience module inside Persistence.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any


def dumps(value: Any) -> str:
    return json.dumps(value)


def loads(value: str | None, default: Any = None) -> Any:
    if value is None:
        return default
    return json.loads(value)


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)
