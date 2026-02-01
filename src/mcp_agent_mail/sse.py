"""Server-Sent Events (SSE) support for real-time notifications."""

from __future__ import annotations

import asyncio
import contextlib
import json
from dataclasses import asdict, dataclass
from typing import Any, AsyncGenerator, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)

# Global broadcaster instance
_BROADCASTER: Optional["NotificationBroadcaster"] = None


@dataclass
class NotificationEvent:
    """A notification event payload."""

    timestamp: str
    project: str  # project_slug
    agent: str    # agent_name
    message: Optional[Dict[str, Any]] = None

    def to_json(self) -> str:
        return json.dumps(asdict(self))


class NotificationBroadcaster:
    """Manages SSE subscriptions and broadcasts events."""

    def __init__(self) -> None:
        # Maps (project_slug, agent_name) -> List[asyncio.Queue]
        self._channels: Dict[tuple[str, str], List[asyncio.Queue[NotificationEvent]]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, project_slug: str, agent_name: str) -> AsyncGenerator[NotificationEvent, None]:
        """Subscribe to notifications for a specific agent in a project."""
        queue: asyncio.Queue[NotificationEvent] = asyncio.Queue(maxsize=50)
        key = (project_slug, agent_name)

        async with self._lock:
            if key not in self._channels:
                self._channels[key] = []
            self._channels[key].append(queue)

        logger.info("sse_subscribe", project=project_slug, agent=agent_name, channels=len(self._channels[key]))

        try:
            while True:
                event = await queue.get()
                yield event
        finally:
            async with self._lock:
                if key in self._channels:
                    # Remove the queue from the list
                    self._channels[key] = [q for q in self._channels[key] if q is not queue]
                    if not self._channels[key]:
                        del self._channels[key]
            logger.info("sse_unsubscribe", project=project_slug, agent=agent_name)

    async def broadcast(self, event: NotificationEvent) -> None:
        """Broadcast an event to all subscribers."""
        key = (event.project, event.agent)

        # Also strictly log if no subscribers? No, that's fine.

        async with self._lock:
            queues = self._channels.get(key, [])
            if not queues:
                return

            for q in queues:
                try:
                    if q.full():
                        # Drop oldest event if full to handle backpressure
                        with contextlib.suppress(asyncio.QueueEmpty):
                            q.get_nowait()
                    q.put_nowait(event)
                except Exception:
                    pass


def get_broadcaster() -> NotificationBroadcaster:
    """Get the global broadcaster instance."""
    global _BROADCASTER
    if _BROADCASTER is None:
        _BROADCASTER = NotificationBroadcaster()
    return _BROADCASTER


async def broadcast_notification(
    project_slug: str,
    agent_name: str,
    timestamp: str,
    message_metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Public API to broadcast a notification."""
    event = NotificationEvent(
        timestamp=timestamp,
        project=project_slug,
        agent=agent_name,
        message=message_metadata,
    )
    broadcaster = get_broadcaster()
    await broadcaster.broadcast(event)
