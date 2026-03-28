"""
fetch_episode.py — Playwright scraper pro RA podcast epizody.

Strategie:
1. Playwright naviguje na ra.co/podcast/{id}
2. Interceptuje všechny síťové odpovědi → hledá GraphQL response s podcast daty
3. Pokud GraphQL intercept selže, čte Apollo cache z window.__APOLLO_STATE__
4. Ukládá raw JSON do data/raw/episode_{id}.json
"""

import asyncio
import json
import logging
import random
import time
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright, Page, Response

BASE_URL = "https://ra.co/podcast"
DATA_DIR = Path(__file__).parent.parent / "data"
RAW_DIR = DATA_DIR / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger(__name__)


def raw_path(podcast_id: str) -> Path:
    return RAW_DIR / f"episode_{podcast_id}.json"


def already_scraped(podcast_id: str) -> bool:
    p = raw_path(podcast_id)
    return p.exists() and p.stat().st_size > 100


async def fetch_episode(
    podcast_id: str,
    page: Page,
    timeout: int = 30000,
) -> Optional[dict]:
    """
    Načte a vrátí raw data pro jednu epizodu.
    Ukládá do data/raw/episode_{id}.json.
    Vrátí None pokud se epizoda nepodaří načíst.
    """
    url = f"{BASE_URL}/{podcast_id}"
    captured: dict = {}

    async def on_response(response: Response):
        """Interceptuje GraphQL responses."""
        try:
            # RA posílá GraphQL na /api nebo inline — hledáme POST s podcast daty
            if response.request.method != "POST":
                return
            ct = response.headers.get("content-type", "")
            if "json" not in ct:
                return
            body = await response.json()
            # Hledáme response s podcast objektem
            data = body.get("data", {})
            if data.get("podcast"):
                captured["graphql"] = data["podcast"]
                logger.debug(f"[{podcast_id}] GraphQL intercept: podcast data captured")
        except Exception:
            pass

    page.on("response", on_response)

    try:
        response = await page.goto(url, wait_until="domcontentloaded", timeout=timeout)

        if response and response.status == 404:
            logger.info(f"[{podcast_id}] 404 — epizoda neexistuje")
            _save_failed(podcast_id, "404")
            return None

        # Čekáme na síťový klid (Apollo dokončí GraphQL volání)
        await page.wait_for_load_state("networkidle", timeout=timeout)

    except Exception as e:
        logger.warning(f"[{podcast_id}] Navigation failed: {e}")
        _save_failed(podcast_id, str(e))
        return None
    finally:
        page.remove_listener("response", on_response)

    # --- Strategie 1: GraphQL intercept ---
    if captured.get("graphql"):
        result = {"source": "graphql", "podcast_id": podcast_id, "url": url, **captured["graphql"]}
        _save_raw(podcast_id, result)
        return result

    # --- Strategie 2: Apollo cache z window ---
    try:
        apollo_raw = await page.evaluate("""
            () => {
                const state = (
                    window.__APOLLO_STATE__ ||
                    window.__NEXT_DATA__?.props?.apolloState ||
                    null
                );
                return JSON.stringify(state);
            }
        """)
        if apollo_raw:
            apollo = json.loads(apollo_raw)
            podcast_key = f'Podcast:{podcast_id}'
            for key in [podcast_key, f'PodcastEpisode:{podcast_id}']:
                if key in apollo:
                    # Resolve __ref pointers using full apollo state
                    resolved = _resolve_refs(apollo[key], apollo)
                    result = {
                        "source": "apollo_cache",
                        "podcast_id": podcast_id,
                        "url": url,
                        **resolved,
                    }
                    _save_raw(podcast_id, result)
                    return result
    except Exception as e:
        logger.debug(f"[{podcast_id}] Apollo cache read failed: {e}")

    # --- Strategie 3: DOM parsing jako poslední záchrana ---
    try:
        dom_data = await _extract_from_dom(page, podcast_id, url)
        if dom_data:
            _save_raw(podcast_id, dom_data)
            return dom_data
    except Exception as e:
        logger.debug(f"[{podcast_id}] DOM extraction failed: {e}")

    logger.warning(f"[{podcast_id}] Všechny strategie selhaly")
    _save_failed(podcast_id, "all_strategies_failed")
    return None


async def _extract_from_dom(page: Page, podcast_id: str, url: str) -> Optional[dict]:
    """Záchranná extrakce přímo z DOM — méně spolehlivá."""
    data = await page.evaluate("""
        () => {
            const getText = (sel) => document.querySelector(sel)?.textContent?.trim() || null;
            const getAttr = (sel, attr) => document.querySelector(sel)?.getAttribute(attr) || null;

            return {
                title: getText('h1') || getText('[data-testid="podcast-title"]'),
                artist: getText('[data-testid="podcast-artist"]') || getText('h2'),
                description: getText('[data-testid="podcast-description"]') || getText('.description'),
                tracklist: getText('[data-testid="tracklist"]') || getText('.tracklist'),
                date: getAttr('time', 'datetime') || getText('time'),
            };
        }
    """)
    if not any(data.values()):
        return None
    return {"source": "dom", "podcast_id": podcast_id, "url": url, **data}


def _resolve_refs(obj: any, apollo: dict, depth: int = 0) -> any:
    """Rekurzivně resolvuje Apollo __ref pointery v objektu."""
    if depth > 5:
        return obj
    if isinstance(obj, dict):
        if "__ref" in obj and len(obj) == 1:
            ref_key = obj["__ref"]
            if ref_key in apollo:
                return _resolve_refs(apollo[ref_key], apollo, depth + 1)
            return None
        return {k: _resolve_refs(v, apollo, depth + 1) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_resolve_refs(item, apollo, depth + 1) for item in obj]
    return obj


def _save_raw(podcast_id: str, data: dict):
    p = raw_path(podcast_id)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info(f"[{podcast_id}] Uloženo: {p} (source={data.get('source')})")


def _save_failed(podcast_id: str, reason: str):
    failed_path = DATA_DIR / "failed_ids.json"
    failed = {}
    if failed_path.exists():
        with open(failed_path) as f:
            failed = json.load(f)
    failed[podcast_id] = {"reason": reason, "timestamp": time.time()}
    with open(failed_path, "w") as f:
        json.dump(failed, f, indent=2)


async def fetch_episodes_batch(
    podcast_ids: list[str],
    delay_range: tuple[float, float] = (2.0, 4.0),
    headless: bool = True,
    timeout: int = 30000,
) -> dict[str, Optional[dict]]:
    """
    Fetchne více epizod s jednou sdílenou browser instancí.
    Přeskakuje epizody, které už jsou stažené.
    """
    results = {}
    to_fetch = [pid for pid in podcast_ids if not already_scraped(pid)]
    skipped = len(podcast_ids) - len(to_fetch)

    if skipped:
        logger.info(f"Přeskakuji {skipped} již stažených epizod")

    if not to_fetch:
        logger.info("Nic ke stažení")
        return results

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
        )
        page = await context.new_page()

        for i, podcast_id in enumerate(to_fetch):
            logger.info(f"[{i+1}/{len(to_fetch)}] Fetching episode {podcast_id}")
            result = await fetch_episode(podcast_id, page, timeout=timeout)
            results[podcast_id] = result

            # Rate limiting mezi requesty
            if i < len(to_fetch) - 1:
                delay = random.uniform(*delay_range)
                logger.debug(f"Čekám {delay:.1f}s")
                await asyncio.sleep(delay)

        await browser.close()

    return results


# --- CLI pro rychlé testování ---
if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    ids = sys.argv[1:] if len(sys.argv) > 1 else ["1100"]

    async def main():
        results = await fetch_episodes_batch(ids, headless=True)
        for pid, data in results.items():
            if data:
                print(f"\n=== Episode {pid} (source: {data.get('source')}) ===")
                # Tiskni klíče které máme
                for k, v in data.items():
                    if k not in ("source", "podcast_id", "url"):
                        val_preview = str(v)[:120] if v else "null"
                        print(f"  {k}: {val_preview}")
            else:
                print(f"\n=== Episode {pid}: FAILED ===")

    asyncio.run(main())
