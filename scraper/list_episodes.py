"""
list_episodes.py — získá seznam ID epizod z RA.

Dvě metody:
1. Scraping /podcast list stránky (pomalejší, ale spolehlivý)
2. Sekvenční sweep ID (rychlý, doporučeno pro full run)

Výstup: data/episode_ids.json
"""

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright

DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger(__name__)


def ids_from_range(start: int = 1, end: int = 1100) -> list[str]:
    """
    Nejjednodušší metoda: sekvenční ID range.
    Neexistující ID jsou automaticky přeskočena při scraping (404 → failed_ids.json).
    """
    return [str(i) for i in range(start, end + 1)]


async def scrape_list_page(
    max_pages: int = 50,
    headless: bool = True,
) -> list[str]:
    """
    Scrape seznam epizod z ra.co/podcast.
    Iteruje stránky dokud nenajde "Load more" button nebo stránka neobsahuje nové epizody.
    Vrátí seřazený seznam ID od nejnovějšího.
    """
    episode_ids = set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()

        await page.goto("https://ra.co/podcast", wait_until="networkidle", timeout=40000)

        for page_num in range(max_pages):
            # Extrahuj links na epizody
            links = await page.evaluate("""
                () => Array.from(document.querySelectorAll('a'))
                           .map(a => a.href)
                           .filter(h => /\\/podcast\\/\\d+$/.test(h))
            """)

            new_ids = set()
            for link in links:
                m = re.search(r"/podcast/(\d+)$", link)
                if m:
                    new_ids.add(m.group(1))

            before = len(episode_ids)
            episode_ids.update(new_ids)
            logger.info(f"Stránka {page_num + 1}: nalezeno {len(new_ids)} linků, celkem {len(episode_ids)}")

            if len(episode_ids) == before and page_num > 0:
                logger.info("Žádné nové epizody — konec paginace")
                break

            # Klikni "Load more" nebo paginator
            try:
                # RA může používat "Load more" button
                btn = await page.query_selector("button:has-text('Load more')")
                if not btn:
                    btn = await page.query_selector("[data-testid='load-more']")
                if btn:
                    await btn.click()
                    await page.wait_for_load_state("networkidle", timeout=15000)
                else:
                    logger.info("Žádný Load more button — konec")
                    break
            except Exception as e:
                logger.debug(f"Load more click failed: {e}")
                break

        await browser.close()

    sorted_ids = sorted(episode_ids, key=lambda x: int(x), reverse=True)
    logger.info(f"Celkem nalezeno {len(sorted_ids)} epizod")
    return sorted_ids


def save_episode_ids(ids: list[str], path: Optional[Path] = None):
    if path is None:
        path = DATA_DIR / "episode_ids.json"
    with open(path, "w") as f:
        json.dump(ids, f, indent=2)
    logger.info(f"Uloženo {len(ids)} IDs do {path}")


def load_episode_ids(path: Optional[Path] = None) -> list[str]:
    if path is None:
        path = DATA_DIR / "episode_ids.json"
    if not path.exists():
        return []
    with open(path) as f:
        return json.load(f)


# --- CLI ---
if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    mode = sys.argv[1] if len(sys.argv) > 1 else "range"

    if mode == "scrape":
        ids = asyncio.run(scrape_list_page())
    else:
        # Default: range sweep 1..1100
        # Ve skutečnosti přeskočí neexistující při fetchování
        latest = int(sys.argv[2]) if len(sys.argv) > 2 else 1049
        ids = ids_from_range(1, latest)
        print(f"Generuji range 1..{latest}: {len(ids)} IDs")

    save_episode_ids(ids)
    print(f"Uloženo: {len(ids)} IDs")
    print("Ukázka (první 5):", ids[:5])
    print("Ukázka (posledních 5):", ids[-5:])
