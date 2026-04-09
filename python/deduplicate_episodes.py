"""
Deduplicate episodes.jsonl by podcast_id.
Keeps the entry with the latest scraped_at timestamp per podcast_id.
"""
from pathlib import Path
import json

DATA_DIR = Path(__file__).parent.parent / "data"
EPISODES_FILE = DATA_DIR / "episodes.jsonl"
BACKUP_FILE = DATA_DIR / "archive" / "deprecated" / "episodes_pre_dedup.jsonl"


def load_episodes(path: Path) -> list[dict]:
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def deduplicate(episodes: list[dict]) -> list[dict]:
    seen: dict[str, dict] = {}
    for ep in episodes:
        pid = ep["podcast_id"]
        if pid not in seen:
            seen[pid] = ep
        else:
            # Keep entry with latest scraped_at (or keep new one if no scraped_at)
            existing_ts = seen[pid].get("scraped_at", "")
            new_ts = ep.get("scraped_at", "")
            if new_ts > existing_ts:
                seen[pid] = ep
    return list(seen.values())


def write_episodes(episodes: list[dict], path: Path) -> None:
    with open(path, "w") as f:
        for ep in episodes:
            f.write(json.dumps(ep, ensure_ascii=False) + "\n")


def main() -> None:
    episodes = load_episodes(EPISODES_FILE)
    print(f"Loaded {len(episodes)} episodes")

    deduped = deduplicate(episodes)
    removed = len(episodes) - len(deduped)
    print(f"After dedup: {len(deduped)} episodes ({removed} duplicates removed)")

    if removed > 0:
        dupes = {}
        from collections import Counter
        counts = Counter(e["podcast_id"] for e in episodes)
        for pid, cnt in counts.items():
            if cnt > 1:
                kept = next(e for e in deduped if e["podcast_id"] == pid)
                dupes[pid] = {
                    "count": cnt,
                    "kept": {"title": kept["title"], "date": kept["date"], "scraped_at": kept.get("scraped_at")},
                }
        print("\nDeduplicated entries:")
        for pid, info in dupes.items():
            print(f"  podcast_id={pid}: {info['count']} → 1, kept: {info['kept']['title']} ({info['kept']['date']})")

    write_episodes(deduped, EPISODES_FILE)
    print(f"\nWrote {len(deduped)} episodes to {EPISODES_FILE}")
    print(f"Backup at: {BACKUP_FILE}")


if __name__ == "__main__":
    main()
