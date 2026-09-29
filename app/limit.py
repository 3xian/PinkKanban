from __future__ import annotations

import time

from fastapi import HTTPException, Request

_hits: dict[str, list[float]] = {}


def limit(request: Request, scope: str, count: int, window: float) -> None:
    host = request.client.host if request.client else "local"
    key = f"{scope}:{host}"
    now = time.monotonic()
    recent = [stamp for stamp in _hits.get(key, []) if now - stamp < window]
    if len(recent) >= count:
        raise HTTPException(429, "操作太频繁，请稍后再试")
    recent.append(now)
    _hits[key] = recent[-count:]
