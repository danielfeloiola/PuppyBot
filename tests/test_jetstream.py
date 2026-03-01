"""
test_jetstream.py — Connects to Jetstream and prints the structure of the first
English image posts, without doing anything else.

This lets you verify:
  - The connection works
  - The embed structure matches what puppybot.py expects
  - The CDN URL format is correct

Usage:
    python tests/test_jetstream.py
    python tests/test_jetstream.py 10   # capture 10 posts instead of the default 5
"""

import sys
import asyncio
import logging
from pathlib import Path

# Allow imports from the project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from jetstream import JetstreamConfig, JetstreamClient, EventHandler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("test_jetstream")


class StructureInspector(EventHandler):
    def __init__(self, max_posts: int = 5):
        self.max_posts = max_posts
        self.count = 0
        self.client: JetstreamClient | None = None

    async def on_post_create(self, did: str, rkey: str, record: dict, raw: dict):
        # Only care about English image posts
        langs = record.get("langs", [])
        if not any(lang.startswith("en") for lang in langs):
            return

        embed = record.get("embed", {})
        if embed.get("$type") != "app.bsky.embed.images":
            return

        self.count += 1
        images = embed.get("images", [])
        blob_cid = (
            images[0].get("image", {}).get("ref", {}).get("$link", "NOT FOUND")
            if images else "NO IMAGES"
        )
        commit_cid = raw.get("commit", {}).get("cid", "NOT FOUND")
        uri = f"at://{did}/app.bsky.feed.post/{rkey}"
        cdn_url = f"https://cdn.bsky.app/img/feed_thumbnail/plain/{did}/{blob_cid}@jpeg"

        print(f"\n{'='*60}")
        print(f"Post {self.count}/{self.max_posts}")
        print(f"  URI:       {uri}")
        print(f"  CID:       {commit_cid}")
        print(f"  Langs:     {langs}")
        print(f"  Images:    {len(images)}")
        print(f"  Blob CID:  {blob_cid}")
        print(f"  CDN URL:   {cdn_url}")
        print(f"  Text:      {record.get('text', '')[:80]}")

        if self.count >= self.max_posts:
            print(f"\nCaptured {self.max_posts} posts. Stopping.")
            await self.client.stop()


async def main():
    max_posts = int(sys.argv[1]) if len(sys.argv) > 1 else 5

    handler = StructureInspector(max_posts=max_posts)
    config = JetstreamConfig(
        wanted_collections=["app.bsky.feed.post"],
        stats_interval=5_000,
    )
    client = JetstreamClient(config, handler)
    handler.client = client

    log.info(f"Connecting to Jetstream... waiting for {max_posts} English image posts")
    await client.start()


if __name__ == "__main__":
    asyncio.run(main())
