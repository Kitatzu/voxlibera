"""Fan-out of caption events to audience connections.

In-memory implementation: one process serves every room. To run several server
replicas behind a load balancer, implement the same methods on top of Redis
Pub/Sub (publish -> PUBLISH to the room channel, subscribe -> SUBSCRIBE) — see
README "Scaling".
"""

import asyncio
from collections import defaultdict

SUBSCRIBER_QUEUE_SIZE = 500


class Subscription:
    def __init__(self) -> None:
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=SUBSCRIBER_QUEUE_SIZE)
        self.dropped = False

    async def next_message(self) -> dict | None:
        """Next event, or None once this subscriber was dropped for being too slow."""
        if self.dropped and self.queue.empty():
            return None
        return await self.queue.get()


class Broadcaster:
    def __init__(self) -> None:
        self._subscriptions: dict[str, set[Subscription]] = defaultdict(set)

    def subscribe(self, room_id: str) -> Subscription:
        subscription = Subscription()
        self._subscriptions[room_id].add(subscription)
        return subscription

    def unsubscribe(self, room_id: str, subscription: Subscription) -> None:
        self._subscriptions[room_id].discard(subscription)

    def publish(self, room_id: str, message: dict) -> None:
        for subscription in list(self._subscriptions[room_id]):
            try:
                subscription.queue.put_nowait(message)
            except asyncio.QueueFull:
                # A viewer that can't keep up is dropped; its client reconnects and gets history.
                subscription.dropped = True
                self.unsubscribe(room_id, subscription)

    def subscriber_count(self, room_id: str) -> int:
        return len(self._subscriptions[room_id])
