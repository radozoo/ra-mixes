"""
run_pilot.py — orchestrace pilot runu na N epizodách.

Použití:
  python3 run_pilot.py                    # pilot na posledních 20 epizodách
  python3 run_pilot.py --count 50         # pilot na 50 epizodách
  python3 run_pilot.py --ids 1049,1048    # konkrétní epizody
  python3 run_pilot.py --from-id 1000     # epizody 1000..1049

Výstupy:
  data/episodes.jsonl
  data/tracks.jsonl
  data/genre_edges.jsonl
  data/pilot_report.json
"""

import argparse
import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import jsonlines

from scraper.fetch_episode import fetch_episodes_batch
from parser.episode_parser import parse_episode
from parser.tracklist_parser import parse_tracklist
from parser.genre_extractor import extract_genres

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger(__name__)

# Odhadovaný rozsah existujících epizod
LATEST_ID = 1049


def load_progress() -> set[str]:
    p = DATA_DIR / "progress.json"
    if p.exists():
        with open(p) as f:
            return set(json.load(f))
    return set()


def save_progress(done_ids: set[str]):
    p = DATA_DIR / "progress.json"
    with open(p, "w") as f:
        json.dump(sorted(done_ids), f)


async def run_pilot(
    podcast_ids: list[str],
    delay_range: tuple[float, float] = (2.0, 4.0),
    headless: bool = True,
    timeout: int = 30000,
) -> dict:
    """
    Hlavní orchestrace:
    1. Fetch raw data (Playwright)
    2. Parse episodes
    3. Parse tracklists
    4. Extract genres
    5. Uložit výstupy
    6. Vrátit report
    """
    logger.info(f"=== PILOT START: {len(podcast_ids)} epizod ===")

    # --- Krok 1: Fetch ---
    logger.info("Krok 1: Fetching epizod...")
    raw_results = await fetch_episodes_batch(
        podcast_ids,
        delay_range=delay_range,
        headless=headless,
        timeout=timeout,
    )

    # Načti raw soubory pro epizody, které už byly stažené dříve
    for pid in podcast_ids:
        if pid not in raw_results or raw_results[pid] is None:
            raw_path = DATA_DIR / "raw" / f"episode_{pid}.json"
            if raw_path.exists():
                with open(raw_path) as f:
                    raw_results[pid] = json.load(f)

    # --- Krok 2-4: Parse + Enrich ---
    logger.info("Krok 2-4: Parsing + enrichment...")

    episodes = []
    all_tracks = []
    all_genre_edges = []
    stats = {
        "total": len(podcast_ids),
        "scraped": 0,
        "failed": 0,
        "has_tracklist": 0,
        "total_tracks": 0,
        "total_genre_edges": 0,
        "scrape_quality": {},
    }

    for pid in podcast_ids:
        raw = raw_results.get(pid)
        if not raw:
            stats["failed"] += 1
            logger.warning(f"[{pid}] Chybí data — přeskakuji")
            continue

        stats["scraped"] += 1

        # Parse episode
        episode = parse_episode(raw)
        episodes.append(episode)

        q = episode["scrape_quality"]
        stats["scrape_quality"][q] = stats["scrape_quality"].get(q, 0) + 1

        # Parse tracklist
        if episode["has_tracklist"]:
            stats["has_tracklist"] += 1
            tracks = parse_tracklist(episode["tracklist_raw"], pid)
            all_tracks.extend(tracks)
            stats["total_tracks"] += len(tracks)
            logger.debug(f"[{pid}] {len(tracks)} tracků parsováno")

        # Extract genres
        genre_edges = extract_genres(episode)
        all_genre_edges.extend(genre_edges)
        stats["total_genre_edges"] += len(genre_edges)

    # --- Krok 5: Uložení výstupů ---
    logger.info("Krok 5: Ukládám výstupy...")

    episodes_path = DATA_DIR / "episodes.jsonl"
    tracks_path = DATA_DIR / "tracks.jsonl"
    genres_path = DATA_DIR / "genre_edges.jsonl"

    # Append mode (pro incremental runs)
    with jsonlines.open(episodes_path, mode="a") as w:
        for ep in episodes:
            w.write(ep)

    with jsonlines.open(tracks_path, mode="a") as w:
        for t in all_tracks:
            w.write(t)

    with jsonlines.open(genres_path, mode="a") as w:
        for g in all_genre_edges:
            w.write(g)

    # Uložit progress
    done_ids = load_progress()
    done_ids.update(pid for pid in podcast_ids if raw_results.get(pid))
    save_progress(done_ids)

    # --- Krok 6: Report ---
    report = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "podcast_ids": podcast_ids,
        **stats,
        "tracklist_rate": f"{stats['has_tracklist'] / max(stats['scraped'], 1) * 100:.1f}%",
        "avg_tracks_per_episode": (
            stats["total_tracks"] / max(stats["has_tracklist"], 1)
        ),
    }

    report_path = DATA_DIR / "pilot_report.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    logger.info(f"=== PILOT DONE ===")
    logger.info(f"Staženo: {stats['scraped']}/{stats['total']}")
    logger.info(f"S tracklist: {stats['has_tracklist']} ({report['tracklist_rate']})")
    logger.info(f"Tracků celkem: {stats['total_tracks']}")
    logger.info(f"Genre edges: {stats['total_genre_edges']}")
    logger.info(f"Report: {report_path}")

    return report


def main():
    parser = argparse.ArgumentParser(description="RA Podcast Pilot Scraper")
    parser.add_argument("--count", type=int, default=20, help="Počet posledních epizod")
    parser.add_argument("--ids", type=str, help="Konkrétní IDs oddělené čárkou")
    parser.add_argument("--from-id", type=int, help="Od ID do LATEST_ID")
    parser.add_argument("--latest-id", type=int, default=LATEST_ID, help=f"Nejvyšší ID (default: {LATEST_ID})")
    parser.add_argument("--visible", action="store_true", help="Zobrazit browser okno")
    parser.add_argument("--delay-min", type=float, default=2.0)
    parser.add_argument("--delay-max", type=float, default=4.0)
    parser.add_argument("--timeout", type=int, default=30000, help="Playwright timeout v ms (default: 30000)")
    parser.add_argument("--retry-failed", action="store_true", help="Retry IDs z failed_ids.json (len timeout failures)")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    # Určení seznamu IDs
    if args.retry_failed:
        failed_path = DATA_DIR / "failed_ids.json"
        if not failed_path.exists():
            print("failed_ids.json nenájdený — nič na retry")
            return
        with open(failed_path) as f:
            failed = json.load(f)
        # Retry iba timeout failures (nie 404 / all_strategies_failed)
        podcast_ids = [
            pid for pid, v in failed.items()
            if "Timeout" in v.get("reason", "")
        ]
        print(f"Retry {len(podcast_ids)} timeout-failed epizód s timeout={args.timeout}ms")
    elif args.ids:
        podcast_ids = [x.strip() for x in args.ids.split(",")]
    elif args.from_id:
        podcast_ids = [str(i) for i in range(args.from_id, args.latest_id + 1)]
    else:
        # Posledních N epizod od latest_id
        start = max(1, args.latest_id - args.count + 1)
        podcast_ids = [str(i) for i in range(start, args.latest_id + 1)]
        # Reverse: od nejnovějšího
        podcast_ids = list(reversed(podcast_ids))

    print(f"Plánuji stáhnout {len(podcast_ids)} epizod: {podcast_ids[:5]}{'...' if len(podcast_ids) > 5 else ''}")

    report = asyncio.run(
        run_pilot(
            podcast_ids,
            delay_range=(args.delay_min, args.delay_max),
            headless=not args.visible,
            timeout=args.timeout,
        )
    )

    print("\n=== REPORT ===")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
