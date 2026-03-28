"""
normalize_llm_cache.py — Apply normalization rules to LLM genre cache.

Reads: data/llm_genre_cache.jsonl
Output: data/llm_genre_cache_normalized.jsonl
"""

import json
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"

# Normalization rules (from user-approved Excel review)
RENAME = {
    "Ghettohouse": "Ghetto House",
    "Ghettotech": "Ghetto Tech",
    "Electrohouse": "Electro House",
    "Tribal": "Tribal House",
    "Percussion-driven Electronic": "Percussion",
    "World": "World Music",
}


def normalize():
    cache_path = DATA_DIR / "llm_genre_cache.jsonl"
    out_path = DATA_DIR / "llm_genre_cache_normalized.jsonl"

    entries = {}
    with open(cache_path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                obj = json.loads(line)
                entries[obj["podcast_id"]] = obj

    renamed_count = 0
    with open(out_path, "w", encoding="utf-8") as f:
        for entry in entries.values():
            new_genres = []
            for g in entry["genres"]:
                if g in RENAME:
                    new_genres.append(RENAME[g])
                    renamed_count += 1
                else:
                    new_genres.append(g)
            # Dedupe (rename may create duplicates)
            seen = set()
            deduped = []
            for g in new_genres:
                if g not in seen:
                    seen.add(g)
                    deduped.append(g)
            entry["genres"] = deduped
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(f"Normalized {len(entries)} episodes, {renamed_count} genre renames")
    print(f"→ {out_path}")


if __name__ == "__main__":
    normalize()
