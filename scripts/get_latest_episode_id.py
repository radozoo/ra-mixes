#!/usr/bin/env python3
"""
Fetch the latest podcast episode ID from ra.co/podcast list.

Usage:
    python scripts/get_latest_episode_id.py

Output:
    Prints episode ID (e.g., "1052") to stdout
    Returns 0 on success, 1 on error
"""
import httpx
import json
import re
import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


def get_latest_episode_id() -> int | None:
    """
    Fetch latest episode ID from ra.co/podcast list.

    Returns:
        Latest episode ID (int) or None if not found

    Raises:
        Exception on network/parsing errors
    """
    url = "https://ra.co/podcast"

    # Fetch list page
    with httpx.Client(headers=HEADERS, timeout=15) as client:
        logger.info(f"Fetching {url}...")
        resp = client.get(url, follow_redirects=True)
        resp.raise_for_status()

    # Extract __NEXT_DATA__ JSON from HTML
    match = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
        resp.text,
        re.DOTALL,
    )

    if not match:
        raise ValueError("Could not find __NEXT_DATA__ in HTML")

    # Parse JSON
    data = json.loads(match.group(1))
    apollo = data.get("props", {}).get("apolloState", {})

    # Find all Podcast entries and get highest ID
    podcast_ids = []
    for key in apollo.keys():
        if key.startswith("Podcast:"):
            try:
                podcast_id = int(key.split(":")[1])
                podcast_ids.append(podcast_id)
            except (ValueError, IndexError):
                pass

    if not podcast_ids:
        raise ValueError("No Podcast entries found in apolloState")

    latest_id = max(podcast_ids)
    logger.info(f"Latest episode ID: {latest_id}")
    return latest_id


def main():
    try:
        episode_id = get_latest_episode_id()
        if episode_id is None:
            print("Error: Could not determine latest episode ID", file=sys.stderr)
            sys.exit(1)

        # Print just the ID (for use in GitHub Actions)
        print(episode_id)
        sys.exit(0)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
