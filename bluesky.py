"""
Bluesky account — authenticates and performs actions via the atproto SDK.
"""

import logging
from dataclasses import dataclass

from atproto import Client

log = logging.getLogger("puppybot")


@dataclass
class AccountConfig:
    handle: str
    app_password: str


class BlueskyAccount:

    def __init__(self, config: AccountConfig):
        self.client = Client()
        self.config = config

    def login(self):
        profile = self.client.login(self.config.handle, self.config.app_password)
        log.info(f"Logged in as {profile.display_name} (@{profile.handle})")
        return profile

    def repost(self, uri: str, cid: str) -> dict:
        resp = self.client.repost(uri, cid)
        log.info(f"Reposted: {uri}")
        return resp
