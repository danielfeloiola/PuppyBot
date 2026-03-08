# puppybot 🐶

A Bluesky bot that finds and reposts pictures of dogs.

It listens to the public Bluesky firehose, spots posts with dog photos using a ResNet50 image classifier, and shares them — once every ~55 minutes so it doesn't flood your feed.

## How it works

1. Connects to the [Bluesky Jetstream](https://docs.bsky.app/blog/jetstream) (public WebSocket firehose)
2. Filters English posts that have images and mention dogs in the text or alt-text
3. Runs the image through ResNet50 (TensorFlow) to confirm there's actually a dog
4. Reposts — and then waits 55 minutes before looking for the next one

## Setup

```bash
# Install dependencies
poetry install

# Set credentials
export BSKY_HANDLE=your-handle.bsky.social
export BSKY_APP_PASSWORD=your-app-password

# Run
python puppybot.py
```

## Test mode

```bash
DRY_RUN=1 python puppybot.py
```

Logs every dog it would have reposted without actually posting anything. No cooldown in this mode, so you see every match.

## To-do

- [x] Investigate Labrador false negative in `tests/test_detector.py` — ResNet50 not detecting that specific Wikimedia image
- [x] First real production run — set credentials, run without `DRY_RUN`, confirm reposts land on the account
- [ ] Opt-out: watch for replies/mentions from the original poster asking to remove the repost (e.g. "delete", "remove", "opt out") and automatically call `unrepost()` + reply confirming

## Project structure

```
puppybot.py        — main bot
jetstream.py       — Bluesky Jetstream WebSocket client
bluesky.py         — Bluesky account API (login, repost)
detector.py        — ResNet50 dog detector
word_filter.py     — loads bad_words.json blocklist
tests/
  test_detector.py — tests the dog detector with known images
  test_jetstream.py — connects to Jetstream and prints matching posts
```
