"""
Fetch missing episodes directly via HTTP (no Playwright).
Parses __NEXT_DATA__ from HTML — much faster than Playwright.
"""
import httpx
import re
import json
import time
import glob
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"
RAW_DIR = DATA_DIR / "raw"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


def get_missing_ids():
    raw_ids = set()
    for f in glob.glob(str(RAW_DIR / "episode_*.json")):
        try:
            raw_ids.add(int(Path(f).stem.split("_")[-1]))
        except ValueError:
            pass

    failed_path = DATA_DIR / "failed_ids.json"
    if not failed_path.exists():
        logger.error("failed_ids.json not found")
        return []

    with open(failed_path) as f:
        failed = [int(x) for x in json.load(f)]

    return [id for id in failed if id not in raw_ids]


def fetch_episode(client: httpx.Client, ep_id: int) -> dict | None:
    url = f"https://ra.co/podcast/{ep_id}"
    try:
        r = client.get(url)
        if r.status_code == 404:
            logger.info(f"[{ep_id}] 404")
            return None

        match = re.search(
            r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
            r.text,
            re.DOTALL,
        )
        if not match:
            logger.warning(f"[{ep_id}] No __NEXT_DATA__ in HTML")
            return None

        apollo = json.loads(match.group(1)).get("props", {}).get("apolloState", {})
        podcast = apollo.get(f"Podcast:{ep_id}")
        if not podcast:
            logger.warning(f"[{ep_id}] Podcast:{ep_id} not in apolloState")
            return None

        result = {
            "source": "httpx_next_data",
            "podcast_id": str(ep_id),
            "url": url,
            **podcast,
        }
        return result

    except Exception as e:
        logger.warning(f"[{ep_id}] Error: {e}")
        return None


def main():
    missing = get_missing_ids()
    if not missing:
        logger.info("Nič na stiahnutie.")
        return

    logger.info(f"Sťahujem {len(missing)} epizód...")
    ok = 0
    fail = 0

    with httpx.Client(timeout=10, follow_redirects=True, headers=HEADERS) as client:
        for i, ep_id in enumerate(missing, 1):
            t0 = time.time()
            result = fetch_episode(client, ep_id)
            elapsed = time.time() - t0

            if result:
                out_path = RAW_DIR / f"episode_{ep_id}.json"
                with open(out_path, "w") as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)
                logger.info(f"[{i}/{len(missing)}] {ep_id} OK ({elapsed:.1f}s) — {result.get('title', '?')}")
                ok += 1
            else:
                fail += 1
                logger.warning(f"[{i}/{len(missing)}] {ep_id} FAIL ({elapsed:.1f}s)")

    logger.info(f"Hotovo: {ok} OK, {fail} failed z {len(missing)}")


if __name__ == "__main__":
    main()
