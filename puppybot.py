"""
puppybot — Bluesky bot that reposts pictures of dogs.

Usage:
    export BSKY_HANDLE=your-handle.bsky.social
    export BSKY_APP_PASSWORD=your-app-password
    python puppybot.py

What the bot does:
    1. Connects to the Bluesky Jetstream (public WebSocket firehose)
    2. Filters English posts that contain images
    3. Downloads the image and detects dogs via ResNet50 (TensorFlow)
    4. If a dog is found: reposts
"""

import os
import time
import signal
import asyncio
import logging
import tempfile
from pathlib import Path
from collections import deque
from concurrent.futures import ThreadPoolExecutor

import requests

from jetstream import JetstreamConfig, JetstreamClient, EventHandler
from bluesky import BlueskyAccount, AccountConfig
from detector import dog_detector
from word_filter import load_blocked_words

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

_LOG_DIR = Path(__file__).parent / "logs"
_LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(_LOG_DIR / "puppybot.log", encoding="utf-8"),
    ],
    force=True,  # override any handlers set up by TensorFlow before this point
)
log = logging.getLogger("puppybot")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BSKY_HANDLE = os.environ.get("BSKY_HANDLE", "")
BSKY_APP_PASSWORD = os.environ.get("BSKY_APP_PASSWORD", "")

# Set DRY_RUN=1 to log detections without actually reposting
DRY_RUN = os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")

# Max concurrent TensorFlow detections.
# Must stay at 1: the ResNet50 model in detector.py is a single shared Keras
# object and is NOT thread-safe for concurrent inference. Running >1 at once
# makes each call stall past DETECTION_TIMEOUT; the timed-out threads can't be
# killed, so they permanently occupy the executor and every later detection
# times out too (zero reposts). Detection is off the read loop either way.
MAX_CONCURRENT_DETECTIONS = 1

# Max number of post URIs kept in memory for deduplication
DEDUP_MAX_SIZE = 1_000

# Cooldown between reposts in production mode
REPOST_COOLDOWN = 90 * 60  # 90 min

# Max seconds to wait for a single detection (image download + TF inference)
# before giving up and freeing the event loop.
DETECTION_TIMEOUT = 30

# Image download timeouts, as (connect, read) seconds passed to requests.
IMAGE_TIMEOUT = (5, 10)

# Keywords that must appear in the post text or image alt-text
# (checked before running TensorFlow — cheap pre-filter)
DOG_KEYWORDS = {
    "dog", "dogs", "puppy", "puppies",
    "doggo", "doggos", "pupper", "puppers",
    "pup", "pups", "woof", "canine",
    "hound", "dogsofbluesky",
}

# Words loaded from bad_words.json — posts containing any of these are skipped
BLOCKED_WORDS = load_blocked_words()

# Self-labels that disqualify a post from being reposted
BLOCKED_LABELS = {
    "porn",
    "sexual",
    "nudity",
    "graphic-media",
    "!warn",
    "!hide",
    "!no-unauthenticated",
}

# ---------------------------------------------------------------------------
# Dog detection (sync — runs in ThreadPoolExecutor)
# ---------------------------------------------------------------------------

def detect_dog_from_url(url: str) -> bool:
    """Download image from URL and return True if a dog is detected."""
    try:
        resp = requests.get(url, timeout=IMAGE_TIMEOUT)
        if resp.status_code != 200:
            log.debug(f"Image unreachable ({resp.status_code}): {url}")
            return False

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(resp.content)
            tmp_path = f.name

        try:
            return bool(dog_detector(tmp_path))
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    except Exception as e:
        log.debug(f"Error detecting dog at {url}: {e}")
        return False


# ---------------------------------------------------------------------------
# Event handler
# ---------------------------------------------------------------------------

class PuppyHandler(EventHandler):
    """
    Listens to Jetstream posts, detects dogs, and reposts.
    """

    def __init__(self, bsky: BlueskyAccount | None, dry_run: bool = False):
        self.bsky = bsky
        self.dry_run = dry_run
        self.client: "JetstreamClient | None" = None
        self.cooldown_requested: bool = False
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_DETECTIONS)
        self._reposted: deque[str] = deque(maxlen=DEDUP_MAX_SIZE)
        self._reposted_set: set[str] = set()
        self._executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_DETECTIONS)
        self._last_repost_at: float = -REPOST_COOLDOWN
        # In-flight detection tasks, so they aren't garbage-collected mid-run.
        self._pending: set[asyncio.Task] = set()
        # Serialises the repost decision — only one post wins per listen cycle.
        self._repost_lock = asyncio.Lock()
        # Set once we've triggered a repost + stop; new work bails out.
        self._stopping = False

    def reset_cycle(self):
        """Re-arm the handler after a cooldown so it accepts posts again."""
        self._stopping = False

    async def on_post_create(self, did: str, rkey: str, record: dict, raw: dict):
        # This runs inline in the Jetstream read loop, so it must stay cheap —
        # only fast filters here. The expensive detection is spawned as a task.

        # 0. Already reposting / shutting down this cycle
        if self._stopping:
            return

        # 1. Language filter — English only
        langs = record.get("langs", [])
        if not any(lang.startswith("en") for lang in langs):
            return

        # 2. Cooldown — skip everything while waiting (production only)
        if not self.dry_run:
            if time.monotonic() - self._last_repost_at < REPOST_COOLDOWN:
                return

        # 3. Must have an image embed
        embed = record.get("embed", {})
        if embed.get("$type") != "app.bsky.embed.images":
            return
        images = embed.get("images", [])
        if not images:
            return

        # 4. Keyword pre-filter — text or alt-text must mention a dog
        text_lower = record.get("text", "").lower()
        alt_lower = " ".join(img.get("alt", "") for img in images).lower()
        if not any(kw in text_lower or kw in alt_lower for kw in DOG_KEYWORDS):
            return

        # 5. Bad-word filter
        if any(w in text_lower or w in alt_lower for w in BLOCKED_WORDS):
            return

        # 6. Dedup check
        uri = f"at://{did}/app.bsky.feed.post/{rkey}"
        if uri in self._reposted_set:
            return

        # 7. Self-labels safety filter
        self_labels = [
            lbl.get("val", "")
            for lbl in record.get("labels", {}).get("values", [])
        ]
        blocked = [l for l in self_labels if l in BLOCKED_LABELS]
        if blocked:
            if self.dry_run:
                log.info(f"[DRY RUN] Rejected (label: {blocked}): {uri}")
            return

        # 8. Must have a usable image blob
        blob_cid = images[0].get("image", {}).get("ref", {}).get("$link", "")
        if not blob_cid:
            return

        # Claim the URI now so concurrent tasks don't process it twice.
        self._track_dedup(uri)

        # 9. Spawn the expensive detection off the read loop (bounded by the
        # semaphore inside _process). The read loop keeps consuming meanwhile.
        task = asyncio.create_task(
            self._process(did, rkey, uri, blob_cid, self_labels, record, raw)
        )
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)

    async def _process(
        self,
        did: str,
        rkey: str,
        uri: str,
        blob_cid: str,
        self_labels: list,
        record: dict,
        raw: dict,
    ):
        async with self._semaphore:
            # State may have changed while queued on the semaphore.
            if self._stopping:
                return

            img_url = (
                f"https://cdn.bsky.app/img/feed_thumbnail/plain/"
                f"{did}/{blob_cid}@jpeg"
            )

            # Dog detection — most expensive step (network + CPU). Bounded by a
            # hard timeout so a slow/stuck detection can't wedge the loop.
            # NOTE: on timeout the underlying thread can't be killed, but the
            # event loop is freed and the download timeout caps the usual cause.
            loop = asyncio.get_event_loop()
            try:
                is_dog = await asyncio.wait_for(
                    loop.run_in_executor(self._executor, detect_dog_from_url, img_url),
                    timeout=DETECTION_TIMEOUT,
                )
            except asyncio.TimeoutError:
                log.warning(f"Detection timed out after {DETECTION_TIMEOUT}s: {uri}")
                return

            if not is_dog:
                return

            # Dry-run: just log, no repost, no stop.
            if self.dry_run:
                text = record.get("text", "").replace("\n", " ")
                post_url = f"https://bsky.app/profile/{did}/post/{rkey}"
                log.info(
                    f"[DRY RUN] Would repost\n"
                    f"  URL:    {post_url}\n"
                    f"  Image:  {img_url}\n"
                    f"  Text:   {text[:200]}\n"
                    f"  Labels: {self_labels if self_labels else 'none'}"
                )
                return

            # Only one task may win the repost per cycle.
            async with self._repost_lock:
                if self._stopping:
                    return
                commit_cid = raw.get("commit", {}).get("cid", "")
                try:
                    self.bsky.repost(uri, commit_cid)
                    log.info(f"WOOF! Reposted: {uri}")
                except Exception as e:
                    # Auth/rate-limit/etc. Enter cooldown instead of hammering
                    # login on every matching post.
                    log.error(f"Failed to repost {uri} — cooling down: {e}")
                # Whether it succeeded or failed, start the cooldown and stop.
                self._last_repost_at = time.monotonic()
                self._stopping = True
                self.cooldown_requested = True
                await self.client.stop()

    def _track_dedup(self, uri: str):
        if len(self._reposted_set) >= DEDUP_MAX_SIZE:
            oldest = self._reposted.popleft()
            self._reposted_set.discard(oldest)
        self._reposted.append(uri)
        self._reposted_set.add(uri)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

async def main():
    if DRY_RUN:
        log.info("DRY RUN mode — no reposts will be made")
        bsky = None
    else:
        if not BSKY_HANDLE or not BSKY_APP_PASSWORD:
            raise RuntimeError(
                "Set BSKY_HANDLE and BSKY_APP_PASSWORD environment variables before running."
            )
        config = AccountConfig(handle=BSKY_HANDLE, app_password=BSKY_APP_PASSWORD)
        bsky = BlueskyAccount(config)
        bsky.login()

    # Set up handler and Jetstream client
    handler = PuppyHandler(bsky, dry_run=DRY_RUN)
    jetstream_config = JetstreamConfig(
        wanted_collections=["app.bsky.feed.post"],
        stats_interval=1_000,
    )
    client = JetstreamClient(jetstream_config, handler)
    handler.client = client

    # Graceful shutdown on Ctrl+C / SIGTERM
    shutdown = asyncio.Event()
    loop = asyncio.get_event_loop()
    def _shutdown():
        shutdown.set()
        asyncio.create_task(client.stop())
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _shutdown)

    log.info("puppybot starting... WOOF!")

    while not shutdown.is_set():
        client.running = True
        await client.start()

        if shutdown.is_set():
            break

        if handler.cooldown_requested:
            handler.cooldown_requested = False
            mins = REPOST_COOLDOWN // 60
            log.info(f"Disconnected from Jetstream. Cooling down for {mins} min...")
            try:
                await asyncio.wait_for(shutdown.wait(), timeout=REPOST_COOLDOWN)
            except asyncio.TimeoutError:
                log.info("Cooldown done — reconnecting to Jetstream...")
                handler.reset_cycle()

    client.print_stats()


if __name__ == "__main__":
    asyncio.run(main())
