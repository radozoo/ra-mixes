"""
dedup_jsonl.py — odstráni duplikáty z JSONL súborov.

Deduplikuje podľa:
  episodes.jsonl   → podcast_id
  tracks.jsonl     → track_id
  genre_edges.jsonl → (podcast_id, genre_canonical)
"""

import json
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"


def dedup_by_key(path: Path, key: str) -> tuple[int, int]:
    """Deduplikuje JSONL súbor podľa jedného kľúča. Vracia (pred, po)."""
    lines = path.read_text(encoding="utf-8").splitlines()
    before = len(lines)
    seen = set()
    out = []
    skipped = 0
    for line in lines:
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            skipped += 1
            continue
        val = obj.get(key)
        if val not in seen:
            seen.add(val)
            out.append(line)
    if skipped:
        print(f"  ! {path.name}: skipped {skipped} corrupt lines")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return before, len(out)


def dedup_genre_edges(path: Path) -> tuple[int, int]:
    """Deduplikuje genre_edges.jsonl podľa (podcast_id, genre_canonical)."""
    lines = path.read_text(encoding="utf-8").splitlines()
    before = len(lines)
    seen = set()
    out = []
    skipped = 0
    for line in lines:
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            skipped += 1
            continue
        key = (obj.get("podcast_id"), obj.get("genre_canonical"))
        if key not in seen:
            seen.add(key)
            out.append(line)
    if skipped:
        print(f"  ! {path.name}: skipped {skipped} corrupt lines")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return before, len(out)


if __name__ == "__main__":
    ep_path = DATA_DIR / "episodes.jsonl"
    tr_path = DATA_DIR / "tracks.jsonl"
    ge_path = DATA_DIR / "genre_edges.jsonl"

    b, a = dedup_by_key(ep_path, "podcast_id")
    print(f"episodes.jsonl:    {b} → {a} (removed {b-a})")

    b, a = dedup_by_key(tr_path, "track_id")
    print(f"tracks.jsonl:      {b} → {a} (removed {b-a})")

    b, a = dedup_genre_edges(ge_path)
    print(f"genre_edges.jsonl: {b} → {a} (removed {b-a})")
