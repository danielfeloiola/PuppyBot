"""
Jetstream client — consumes the Bluesky public firehose via WebSocket.

Connects to a Jetstream instance, filters by collection and/or DID,
reconnects automatically on failure (with cursor), and dispatches
events to an EventHandler subclass.
"""

import json
import asyncio
import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field

import websockets

log = logging.getLogger("puppybot")


@dataclass
class JetstreamConfig:
    # Public Bluesky instances:
    #   jetstream1.us-east.bsky.network
    #   jetstream2.us-east.bsky.network
    #   jetstream1.us-west.bsky.network
    #   jetstream2.us-west.bsky.network
    host: str = "jetstream2.us-east.bsky.network"

    # Collections to filter (empty = all).
    # e.g. "app.bsky.feed.post", "app.bsky.feed.like"
    wanted_collections: list[str] = field(default_factory=lambda: [
        "app.bsky.feed.post",
    ])

    # Specific DIDs to monitor (empty = everyone). Max 10,000 per connection.
    wanted_dids: list[str] = field(default_factory=list)

    # zstd compression (~56% smaller). Requires `zstandard` package.
    compress: bool = False

    # How often (in events) to log stats.
    stats_interval: int = 500

    # Reconnect backoff settings.
    reconnect_delay: float = 1.0
    reconnect_max_delay: float = 30.0

    def build_url(self, cursor: int | None = None) -> str:
        params = []
        for col in self.wanted_collections:
            params.append(f"wantedCollections={col}")
        for did in self.wanted_dids:
            params.append(f"wantedDids={did}")
        if self.compress:
            params.append("compress=true")
        if cursor is not None:
            params.append(f"cursor={cursor}")
        query = "&".join(params)
        return f"wss://{self.host}/subscribe?{query}" if query else f"wss://{self.host}/subscribe"


class EventHandler:
    """Base class — override the methods you need."""

    async def on_post_create(self, did: str, rkey: str, record: dict, raw: dict):
        pass

    async def on_post_delete(self, did: str, rkey: str, raw: dict):
        pass

    async def on_like(self, did: str, rkey: str, record: dict, raw: dict):
        pass

    async def on_repost(self, did: str, rkey: str, record: dict, raw: dict):
        pass

    async def on_follow(self, did: str, rkey: str, record: dict, raw: dict):
        pass

    async def on_identity(self, did: str, raw: dict):
        pass

    async def on_account(self, did: str, raw: dict):
        pass


class JetstreamClient:
    """Connects to Jetstream, dispatches events, and reconnects automatically."""

    def __init__(self, config: JetstreamConfig, handler: EventHandler):
        self.config = config
        self.handler = handler
        self.cursor: int | None = None
        self.running = False
        self.stats = {
            "events": 0, "posts": 0, "likes": 0,
            "reposts": 0, "follows": 0, "deletes": 0, "errors": 0,
        }
        self._started_at: datetime | None = None

    async def start(self):
        """Start the client with automatic reconnection."""
        self.running = True
        self._started_at = datetime.now(timezone.utc)
        delay = self.config.reconnect_delay

        log.info(f"Connecting to Jetstream ({self.config.host})...")
        log.info(f"  Collections: {self.config.wanted_collections}")

        while self.running:
            try:
                await self._connect()
                delay = self.config.reconnect_delay
            except (
                websockets.ConnectionClosed,
                websockets.InvalidStatusCode,
                ConnectionError,
                OSError,
            ) as e:
                log.warning(f"Connection lost: {e}")
            except Exception as e:
                log.error(f"Unexpected error: {e}", exc_info=True)
                self.stats["errors"] += 1

            if self.running:
                log.info(f"Reconnecting in {delay:.1f}s (cursor={self.cursor})...")
                await asyncio.sleep(delay)
                delay = min(delay * 2, self.config.reconnect_max_delay)

    async def stop(self):
        log.info("Stopping Jetstream client...")
        self.running = False

    async def update_filters(
        self,
        ws,
        collections: list[str] | None = None,
        dids: list[str] | None = None,
    ):
        """Update filters at runtime without reconnecting."""
        payload = {}
        if collections is not None:
            payload["wantedCollections"] = collections
        if dids is not None:
            payload["wantedDids"] = dids
        await ws.send(json.dumps({"type": "options_update", "payload": payload}))
        log.info(f"Filters updated: {payload}")

    def print_stats(self):
        elapsed = (datetime.now(timezone.utc) - self._started_at).total_seconds()
        rate = self.stats["events"] / elapsed if elapsed > 0 else 0
        log.info(
            f"STATS | events: {self.stats['events']} | posts: {self.stats['posts']} | "
            f"likes: {self.stats['likes']} | reposts: {self.stats['reposts']} | "
            f"follows: {self.stats['follows']} | deletes: {self.stats['deletes']} | "
            f"errors: {self.stats['errors']} | rate: {rate:.1f}/s | uptime: {elapsed:.0f}s"
        )

    async def _connect(self):
        url = self.config.build_url(cursor=self.cursor)
        log.info(f"Connecting: {url[:120]}...")
        async with websockets.connect(url) as ws:
            log.info("Connected!")
            async for raw_message in ws:
                if not self.running:
                    break
                try:
                    event = json.loads(raw_message)
                    await self._dispatch(event)
                except json.JSONDecodeError:
                    log.warning("Non-JSON message received, ignoring")
                    self.stats["errors"] += 1
                except Exception as e:
                    log.error(f"Error processing event: {e}", exc_info=True)
                    self.stats["errors"] += 1

    async def _dispatch(self, event: dict):
        self.stats["events"] += 1

        time_us = event.get("time_us")
        if time_us:
            self.cursor = time_us

        if self.stats["events"] % self.config.stats_interval == 0:
            self.print_stats()

        kind = event.get("kind")
        did = event.get("did", "")

        if kind == "identity":
            await self.handler.on_identity(did, event)
            return
        if kind == "account":
            await self.handler.on_account(did, event)
            return
        if kind != "commit":
            return

        commit = event.get("commit", {})
        operation = commit.get("operation", "")
        collection = commit.get("collection", "")
        rkey = commit.get("rkey", "")
        record = commit.get("record", {})

        if collection == "app.bsky.feed.post":
            if operation == "create":
                self.stats["posts"] += 1
                await self.handler.on_post_create(did, rkey, record, event)
            elif operation == "delete":
                self.stats["deletes"] += 1
                await self.handler.on_post_delete(did, rkey, event)
        elif collection == "app.bsky.feed.like":
            if operation == "create":
                self.stats["likes"] += 1
                await self.handler.on_like(did, rkey, record, event)
        elif collection == "app.bsky.feed.repost":
            if operation == "create":
                self.stats["reposts"] += 1
                await self.handler.on_repost(did, rkey, record, event)
        elif collection == "app.bsky.graph.follow":
            if operation == "create":
                self.stats["follows"] += 1
                await self.handler.on_follow(did, rkey, record, event)
