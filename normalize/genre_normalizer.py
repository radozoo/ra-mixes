"""
genre_normalizer.py — filtruje a normalizuje genre_edges.jsonl.

Stratégia (bez LLM, čistý filter):
1. Načítaj genre_edges.jsonl
2. Ponechaj iba riadky kde genre_canonical je v GENRE_VOCAB (reálny žáner)
3. Odstrán blacklistované žánre (príliš generické)
4. Pre LLM-sourced žánre: povolí aj discovered genres s closest_known mapovaním
5. Zapíše genre_edges_clean.jsonl + genre_map.json (report mapovania)

Výstup:
  data/genre_edges_clean.jsonl  — čisté hrany pre D3
  data/genre_map.json           — {raw_canonical → final_canonical} mapa
"""

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from parser.genre_extractor import GENRE_VOCAB

DATA_DIR = Path(__file__).parent.parent / "data"

# Žánre na odstránenie (príliš generické alebo irelevantné)
BLACKLIST = {
    "Club Music",   # matchuje každé "club" → false positives
    "Rave",         # veľmi generické
    "Electronic",   # príliš broad
    "Live",         # nie žáner
}

# Voliteľné: zlúčenie variantov (canonical_source → canonical_target)
MERGE: dict[str, str] = {
    "Juke": "Footwork",   # Footwork a Juke sú synonymá — nechaj Footwork
}


def load_musicology_nodes():
    """Load genre node IDs from musicology graph."""
    path = DATA_DIR / "genre_musicology.json"
    if not path.exists():
        return set()
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return {n["id"] for n in data["nodes"]}


def load_discovered_genres():
    """Load discovered genres and build mapping to closest_known.
    Skip genres that already exist as musicology nodes — they don't need remapping."""
    path = DATA_DIR / "discovered_genres.json"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    musicology_nodes = load_musicology_nodes()
    mapping = {}
    for name, meta in data.items():
        if name in musicology_nodes:
            continue  # genre is a proper node now, don't remap
        closest = meta.get("closest_known", "")
        if closest:
            mapping[name] = closest
    return mapping


def normalize(input_path: Path = DATA_DIR / "genre_edges.jsonl",
              output_path: Path = DATA_DIR / "genre_edges_clean.jsonl") -> dict:
    """
    Filtruje a normalizuje genre_edges. Vracia report.
    """
    valid_genres = set(GENRE_VOCAB.keys()) - BLACKLIST
    discovered_map = load_discovered_genres()
    merge_map = {**MERGE, **discovered_map}

    rows_in = 0
    rows_out = 0
    skipped_not_genre = 0
    skipped_blacklist = 0
    merged = 0
    genre_counts: dict[str, int] = {}

    with (
        open(input_path, encoding="utf-8") as fin,
        open(output_path, "w", encoding="utf-8") as fout,
    ):
        for line in fin:
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            rows_in += 1

            canonical = obj.get("genre_canonical", "")

            # Filter 1: blacklist
            if canonical in BLACKLIST:
                skipped_blacklist += 1
                continue

            # Filter 2: musí byť v GENRE_VOCAB (skip for LLM-sourced)
            if obj.get("source") != "llm" and canonical not in valid_genres:
                skipped_not_genre += 1
                continue

            # Merge: nahraď canonical podľa merge_map (includes discovered genres)
            if canonical in merge_map:
                mapped = merge_map[canonical]
                # closest_known môže byť comma-separated → rozdeliť na viac edges
                targets = [t.strip() for t in mapped.split(",")]
                obj["genre_raw"] = obj.get("genre_raw", canonical)
                merged += 1
                for target in targets:
                    row = {**obj, "genre_canonical": target}
                    genre_counts[target] = genre_counts.get(target, 0) + 1
                    fout.write(json.dumps(row, ensure_ascii=False) + "\n")
                    rows_out += 1
                continue

            final = obj["genre_canonical"]
            genre_counts[final] = genre_counts.get(final, 0) + 1
            fout.write(json.dumps(obj, ensure_ascii=False) + "\n")
            rows_out += 1

    # Zapíš genre_map.json ako report
    genre_map_path = DATA_DIR / "genre_map.json"
    genre_map = {
        "valid_genres": sorted(valid_genres),
        "blacklisted": sorted(BLACKLIST),
        "merged": MERGE,
        "genre_counts": dict(sorted(genre_counts.items(), key=lambda x: -x[1])),
        "stats": {
            "rows_in": rows_in,
            "rows_out": rows_out,
            "skipped_not_genre": skipped_not_genre,
            "skipped_blacklist": skipped_blacklist,
            "merged_edges": merged,
            "unique_genres_kept": len(genre_counts),
        },
    }
    with open(genre_map_path, "w", encoding="utf-8") as f:
        json.dump(genre_map, f, ensure_ascii=False, indent=2)

    return genre_map["stats"]


if __name__ == "__main__":
    stats = normalize()
    print(f"Input rows:       {stats['rows_in']}")
    print(f"Output rows:      {stats['rows_out']}")
    print(f"Skipped (not genre): {stats['skipped_not_genre']}")
    print(f"Skipped (blacklist): {stats['skipped_blacklist']}")
    print(f"Merged edges:     {stats['merged_edges']}")
    print(f"Unique genres:    {stats['unique_genres_kept']}")
    print(f"→ data/genre_edges_clean.jsonl")
    print(f"→ data/genre_map.json")
