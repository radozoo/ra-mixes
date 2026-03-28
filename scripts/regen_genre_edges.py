"""
regen_genre_edges.py — regeneruje genre_edges.jsonl z episodes.jsonl.

Používaj po dokončení scrapingu a dedupu, pred genre_normalizer.
Prepíše genre_edges.jsonl (nie append), potom automaticky spustí normalizer.
"""

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from parser.genre_extractor import extract_genres

DATA_DIR = Path(__file__).parent.parent / "data"


def regen():
    eps_path = DATA_DIR / "episodes.jsonl"
    genre_path = DATA_DIR / "genre_edges.jsonl"

    episodes = []
    with open(eps_path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    episodes.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    print(f"Načítaných epizód: {len(episodes)}")

    all_edges = []
    for ep in episodes:
        edges = extract_genres(ep)
        all_edges.extend(edges)

    # Deduplicate by (entity_id, genre_canonical)
    seen = set()
    unique_edges = []
    for e in all_edges:
        key = (e.get("entity_id"), e.get("genre_canonical"))
        if key not in seen:
            seen.add(key)
            unique_edges.append(e)

    with open(genre_path, "w", encoding="utf-8") as f:
        for e in unique_edges:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    print(f"Zapísaných genre_edges: {len(unique_edges)}")
    genres_used = set(e["genre_canonical"] for e in unique_edges)
    print(f"Unikátnych genre_canonical hodnôt: {len(genres_used)}")

    return len(unique_edges)


if __name__ == "__main__":
    regen()
    print()
    print("Spúšťam genre_normalizer...")
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from normalize.genre_normalizer import normalize
    stats = normalize()
    print(f"Normalizácia: {stats['rows_in']} → {stats['rows_out']} (unique genres: {stats['unique_genres_kept']})")
