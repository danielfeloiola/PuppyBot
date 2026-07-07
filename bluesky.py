"""
Bluesky account — authenticates and performs actions via the atproto SDK.
"""

import logging
import time
from dataclasses import dataclass

from atproto import Client

log = logging.getLogger("puppybot")


@dataclass
class AccountConfig:
    handle: str
    app_password: str


def _extract_rate_limit_reset(exc) -> float | None:
    """Try to pull the ratelimit-reset unix timestamp out of an atproto exception."""
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None) if response else None
    if not headers:
        return None
    reset = headers.get("ratelimit-reset") or headers.get("Ratelimit-Reset")
    if reset is None:
        return None
    try:
        return float(reset)
    except (TypeError, ValueError):
        return None


def _is_rate_limited(exc) -> bool:
    return "RateLimitExceeded" in str(exc) or "429" in str(exc)


class BlueskyAccount:

    def __init__(self, config: AccountConfig):
        self.client = Client()
        self.config = config
        # Unix timestamp until which we should NOT attempt to log in again.
        self._login_backoff_until: float = 0.0

    def login(self):
        now = time.time()
        if now < self._login_backoff_until:
            wait_left = int(self._login_backoff_until - now)
            raise RuntimeError(
                f"Skipping login attempt — still in rate-limit backoff for {wait_left}s"
            )

        try:
            profile = self.client.login(self.config.handle, self.config.app_password)
        except Exception as e:
            if _is_rate_limited(e):
                reset_ts = _extract_rate_limit_reset(e)
                if reset_ts is None:
                    # No header available — fall back to a conservative 15 minute cooldown.
                    reset_ts = time.time() + 15 * 60
                self._login_backoff_until = reset_ts
                wait_left = int(reset_ts - time.time())
                log.error(
                    f"Login rate-limited by Bluesky — backing off for {wait_left}s "
                    f"(until {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(reset_ts))})"
                )
            raise

        log.info(f"Logged in as {profile.display_name} (@{profile.handle})")
        return profile

    def repost(self, uri: str, cid: str) -> dict:
        try:
            resp = self.client.repost(uri, cid)
        except Exception as e:
            if _is_rate_limited(e):
                # Don't try to log in again — that's what's causing the rate limit.
                # Just skip this repost and let the caller move on.
                log.warning(f"Repost rate-limited, skipping: {uri}")
                raise
            if "ExpiredToken" in str(e) or "Token" in str(e):
                if time.time() < self._login_backoff_until:
                    log.warning(
                        "Session token expired but still in login backoff — skipping repost"
                    )
                    raise
                log.warning("Session token expired — re-logging in...")
                self.login()
                resp = self.client.repost(uri, cid)
            else:
                raise
        log.info(f"Reposted: {uri}")
        return resp
