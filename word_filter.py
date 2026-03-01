"""
word_filter.py — Loads the blocked-word list from bad_words.json.

The file lives at the project root (same directory as this module).
Each entry is checked against the post text and image alt-text before reposting.

To add or remove words, edit bad_words.json directly.
"""

import json
import logging
from pathlib import Path

log = logging.getLogger("puppybot")

_BAD_WORDS_FILE = Path(__file__).parent / "bad_words.json"


def load_blocked_words() -> frozenset[str]:
    """Load the blocked-word list from bad_words.json and return as a frozenset."""
    if not _BAD_WORDS_FILE.exists():
        log.warning(f"bad_words.json not found at {_BAD_WORDS_FILE} — no word filter applied")
        return frozenset()

    with _BAD_WORDS_FILE.open(encoding="utf-8") as f:
        words = json.load(f)

    if not isinstance(words, list):
        log.error("bad_words.json must contain a JSON array of strings")
        return frozenset()

    result = frozenset(w.lower().strip() for w in words if isinstance(w, str) and w.strip())
    log.info(f"Loaded {len(result)} blocked words from bad_words.json")
    return result
