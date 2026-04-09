"""
consolidated_exporter.py — replaces excel_exporter.py

Reads all intermediate JSONL files and produces data/consolidated.json,
the single source of truth for build_network_html.py.

Data model:
  - podcast_id is the primary key (unique per episode)
  - ra_mix_number is extracted from title (display only; NOT unique — RA.1000 has 10 episodes)
  - Sorting: by release date DESC (newest first)
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from python.models import ConsolidatedData, ConsolidatedMix, Episode, extract_ra_mix_number

DATA_DIR = Path(__file__).parent.parent / "data"
OUTPUT_FILE = DATA_DIR / "consolidated.json"


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def build_genre_index(edges: list[dict]) -> dict[str, list[str]]:
    """Map entity_id → list of canonical genre names."""
    index: dict[str, list[str]] = defaultdict(list)
    seen: dict[str, set] = defaultdict(set)
    for edge in edges:
        eid = edge["entity_id"]
        genre = edge["genre_canonical"]
        if genre not in seen[eid]:
            seen[eid].add(genre)
            index[eid].append(genre)
    return dict(index)


def build_label_index(cache: list[dict]) -> dict[str, dict]:
    """Map podcast_id → {labels, label_categories, notes}."""
    index: dict[str, dict] = {}
    for entry in cache:
        pid = str(entry.get("podcast_id", ""))
        if pid and pid not in index:
            index[pid] = {
                "labels": entry.get("labels", []),
                "label_categories": entry.get("label_categories", {}),
                "notes": entry.get("notes", ""),
            }
    return index


def consolidate() -> ConsolidatedData:
    print("Loading data files...")

    episodes = load_jsonl(DATA_DIR / "episodes.jsonl")
    genre_edges = load_jsonl(DATA_DIR / "genre_edges_clean.jsonl")
    llm_cache = load_jsonl(DATA_DIR / "llm_genre_cache_with_categories.jsonl")

    print(f"  Episodes: {len(episodes)}")
    print(f"  Genre edges (clean): {len(genre_edges)}")
    print(f"  LLM cache entries: {len(llm_cache)}")

    genre_index = build_genre_index(genre_edges)
    label_index = build_label_index(llm_cache)

    mixes: list[ConsolidatedMix] = []
    missing_labels = 0
    missing_genres = 0

    for raw_ep in episodes:
        pid = str(raw_ep.get("podcast_id", ""))
        title = raw_ep.get("title", "")

        labels_data = label_index.get(pid, {})
        genres = genre_index.get(pid, [])

        if not labels_data:
            missing_labels += 1
        if not genres:
            missing_genres += 1

        mix = ConsolidatedMix(
            podcast_id=pid,
            ra_mix_number=extract_ra_mix_number(title),
            title=title,
            artist_name=raw_ep.get("artist_name") or "",
            date=raw_ep.get("date", ""),
            image_url=raw_ep.get("image_url"),
            streaming_url=raw_ep.get("streaming_url"),
            description=raw_ep.get("description"),
            blurb=raw_ep.get("blurb"),
            keywords=raw_ep.get("keywords", []),
            has_tracklist=raw_ep.get("has_tracklist", False),
            duration_raw=raw_ep.get("duration_raw"),
            genres=genres,
            labels=labels_data.get("labels", []),
            label_categories=labels_data.get("label_categories", {}),
            notes=labels_data.get("notes", ""),
        )
        mixes.append(mix)

    # Sort by date DESC (newest first), then podcast_id DESC for ties
    mixes.sort(key=lambda m: (m.date or "", int(m.podcast_id or 0)), reverse=True)

    print(f"\nConsolidation summary:")
    print(f"  Total mixes: {len(mixes)}")
    print(f"  Missing labels: {missing_labels}")
    print(f"  Missing genres: {missing_genres}")

    return ConsolidatedData(
        version="2.0",
        generated_at=datetime.now(timezone.utc).isoformat(),
        total_mixes=len(mixes),
        mixes=mixes,
    )


def main() -> None:
    data = consolidate()

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data.model_dump(), f, ensure_ascii=False, separators=(",", ":"))

    size_kb = OUTPUT_FILE.stat().st_size / 1024
    print(f"\nWrote {OUTPUT_FILE} ({size_kb:.0f} KB)")
    print("Done.")


if __name__ == "__main__":
    main()
