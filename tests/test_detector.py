"""
test_detector.py — Tests the dog detector with known images.

Verifies:
  - TensorFlow and Keras imports work
  - ResNet50 model loads correctly
  - detect_dog_from_url returns True for a dog image
  - detect_dog_from_url returns False for a non-dog image

Usage:
    python tests/test_detector.py

You can also pass a custom image URL as an argument:
    python tests/test_detector.py https://example.com/some-image.jpg
"""

import sys
import logging
from pathlib import Path

# Allow imports from the project root
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("test_detector")

# ---------------------------------------------------------------------------
# Known test images (stable Wikimedia Commons URLs)
# ---------------------------------------------------------------------------

TEST_CASES = [
    {
        "name": "Labrador (should detect dog)",
        "url": "https://upload.wikimedia.org/wikipedia/commons/2/26/YellowLabradorLooking_new.jpg",
        "expected": True,
    },
    {
        "name": "Cat (should NOT detect dog)",
        "url": "https://upload.wikimedia.org/wikipedia/commons/thumb/4/4d/Cat_November_2010-1a.jpg/640px-Cat_November_2010-1a.jpg",
        "expected": False,
    },
    {
        "name": "Eiffel Tower (should NOT detect dog)",
        "url": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a8/Tour_Eiffel_Wikimedia_Commons.jpg/640px-Tour_Eiffel_Wikimedia_Commons.jpg",
        "expected": False,
    },
]


def run_tests(urls: list[str] | None = None):
    log.info("Loading dog detector (this may take a moment for ResNet50)...")
    from puppybot import detect_dog_from_url

    if urls:
        # Custom URLs from command line — just run and print result
        for url in urls:
            result = detect_dog_from_url(url)
            print(f"\n  URL:    {url}")
            print(f"  Result: {'DOG DETECTED' if result else 'no dog'}")
        return

    # Run standard test cases
    passed = 0
    failed = 0

    for case in TEST_CASES:
        log.info(f"Testing: {case['name']}")
        result = detect_dog_from_url(case["url"])
        ok = result == case["expected"]

        status = "PASS" if ok else "FAIL"
        expected_str = "dog" if case["expected"] else "no dog"
        got_str = "dog" if result else "no dog"
        print(f"  [{status}] {case['name']}")
        print(f"         expected={expected_str}, got={got_str}")

        if ok:
            passed += 1
        else:
            failed += 1

    print(f"\n{'='*40}")
    print(f"Results: {passed} passed, {failed} failed out of {len(TEST_CASES)} tests")
    if failed == 0:
        print("All tests passed!")
    else:
        print("Some tests failed. Check the detector or test images.")
    print("=" * 40)


if __name__ == "__main__":
    custom_urls = sys.argv[1:] if len(sys.argv) > 1 else None
    run_tests(custom_urls)
