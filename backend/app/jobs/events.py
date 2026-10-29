"""
In-process pub/sub for WebSocket events.
Any backend component can call broadcast(); connected WS clients receive it.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

_subscribers: list[asyncio.Queue] = []


def subscribe() -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=200)
    _subscribers.append(q)
    return q


def unsubscribe(q: asyncio.Queue) -> None:
    try:
        _subscribers.remove(q)
    except ValueError:
        pass


def broadcast(event_type: str, data: Any) -> None:
    """Non-blocking broadcast to all connected WS clients."""
    msg = json.dumps({"type": event_type, "data": data}, default=str)
    dead = []
    for q in _subscribers:
        try:
            q.put_nowait(msg)
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        _subscribers.remove(q)


async def broadcast_async(event_type: str, data: Any) -> None:
    """Async broadcast (use from async context)."""
    broadcast(event_type, data)
    await asyncio.sleep(0)  # yield to let WS tasks drain
