"""
normalize_llm_cache.py — Normalize LLM genre cache with fuzzy matching.

Reads: data/llm_genre_cache.jsonl
Output:
  data/llm_genre_cache_normalized.jsonl  — normalized genres
  data/discovered_genres.json            — novel genres not in musicology graph

Matching strategy:
1. Exact match against genre_musicology.json nodes
2. Alias match via GENRE_VOCAB
3. Fuzzy match (>85% similarity)
4. discovered_genres from LLM with closest_known mapping
5. No match → added to discovered_genres.json for review
"""

import json
from difflib import SequenceMatcher
from pathlib import Path
import sys

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"

sys.path.insert(0, str(ROOT))
from parser.genre_extractor import GENRE_VOCAB

# Manual renames (from user-approved Excel review)
RENAME = {
    "Ghettohouse": "Ghetto House",
    "Ghettotech": "Ghetto Tech",
    "Electrohouse": "Electro House",
    "Tribal": "Tribal House",
    "Percussion-driven Electronic": "Percussion",
    "World": "World Music",
    "Deep Tech": "Tech House",
    "Acid": "Acid House",
    "Post-Punk": "Post Punk",
    "Synth-Pop": "Synth Pop",
    "Nu Disco": "Nu-Disco",
    "D&B": "Drum and Bass",
    "DnB": "Drum and Bass",
    "Drum & Bass": "Drum and Bass",
    "Garage": "UK Garage",
    "Speed Garage": "UK Garage",
    "Deep Techno": "Dub Techno",
    "Singer-Songwriter": "Folk",
    "Italian Folk": "Folk",
    "Sound Bath": "Ambient",
    "Meditation": "Ambient",
    "Spiritual": "New Age",
    "Acoustic": "Folk",
    "Minimalism": "Minimal Techno",
    "Juke": "Footwork",
    # Experimental variants
    "Experimental Electronic": "Experimental",
    "Experimental Electronics": "Experimental",
    "Experimental Electronica": "Experimental",
    "Experimental Club": "Experimental",
    "Experimental Bass": "Bass Music",
    "Experimental House": "House",
    "Experimental Hip Hop": "Hip Hop",
    "Experimental Pop": "Experimental",
    "Experimental Techno": "Experimental Techno",
    # House variants
    "Soulful House": "Deep House",
    "Detroit House": "Deep House",
    "Jazz House": "Deep House",
    "Vocal House": "House",
    "Funk House": "House",
    "Dub House": "Deep House",
    "Leftfield House": "House",
    "Acid House Music": "Acid House",
    "Italo House": "House",
    # Techno variants
    "Dark Techno": "Industrial Techno",
    "Groove Techno": "Techno",
    "Leftfield Techno": "Techno",
    "Warehouse Techno": "Techno",
    "Hypnotic Techno": "Techno",
    "Noise Techno": "Industrial Techno",
    "Broken Techno": "Broken Techno",
    "Deconstructed Techno": "Experimental Techno",
    "Atmospheric Techno": "Ambient Techno",
    "Stripped-back Techno": "Minimal Techno",
    "Loopy Techno": "Minimal Techno",
    "Rolling Techno": "Techno",
    "Peak-time Techno": "Techno",
    "UK Techno": "Techno",
    "Live Techno": "Techno",
    # DnB variants
    "Liquid Drum & Bass": "Drum and Bass",
    "Liquid Drum and Bass": "Drum and Bass",
    "Liquid DnB": "Drum and Bass",
    # Bass/club variants
    "Post-Dubstep": "Bass Music",
    "UK Club": "UK Bass",
    "UK Club Music": "UK Bass",
    # Other mappings
    "Contemporary Classical": "Classical",
    "Musique Concrète": "Electroacoustic",
    "Musique Concrete": "Electroacoustic",
    "Microsound": "Glitch",
    "Groove": "Funk",
    "Jazz Funk": "Funk",
    "Jazz Fusion": "Jazz",
    "Spiritual Jazz": "Jazz",
    "Free Jazz": "Jazz",
    "Afro-Jazz": "Jazz",
    "New Age": "Ambient",
    "Dark Ambient": "Dark Ambient",
    "Noise Music": "Noise",
    "Power Electronics": "Industrial",
    "Post-Rock": "Experimental",
    "Hyperpop": "Experimental",
    "Instrumental Hip-Hop": "Hip Hop",
    "Instrumental Hip Hop": "Hip Hop",
    "Abstract Hip Hop": "Hip Hop",
    "French Touch": "Electro House",
    "French Electro": "Electro",
    "Mutant Disco": "Nu-Disco",
    "Dark Disco": "Nu-Disco",
    "Cosmic Disco": "Cosmic Disco",
    "Space Disco": "Cosmic Disco",
    "Proto-House": "House",
    "Proto-Techno": "Techno",
    "Dancefloor Jazz": "Jazz",
    "World": "World Music",
    "Global Bass": "World Music",
    "Electroclash": "Electro",
    "Electro-Punk": "Electro",
    "Synthpunk": "Synth Pop",
    "Minimal Wave": "Minimal Wave",
    "Coldwave": "Cold Wave",
    "Darkwave": "Dark Wave",
}

# Genres too generic to be useful — skip silently
BLACKLIST = {"Electronic", "Club Music", "Rave", "Live", "Dance Music", "Dance"}


def load_musicology_nodes():
    """Load genre node IDs from musicology graph."""
    path = DATA_DIR / "genre_musicology.json"
    if not path.exists():
        return set()
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return {n["id"] for n in data["nodes"]}


def build_alias_map():
    """Build alias → canonical map from GENRE_VOCAB."""
    alias_map = {}
    for canonical, aliases in GENRE_VOCAB.items():
        alias_map[canonical.lower()] = canonical
        for alias in aliases:
            alias_map[alias.lower()] = canonical
    return alias_map


def fuzzy_match(name, candidates, threshold=0.85):
    """Find best fuzzy match above threshold."""
    best_score = 0
    best_match = None
    name_lower = name.lower()
    for candidate in candidates:
        score = SequenceMatcher(None, name_lower, candidate.lower()).ratio()
        if score > best_score:
            best_score = score
            best_match = candidate
    if best_score >= threshold:
        return best_match
    return None


def resolve_genre(genre_name, musicology_nodes, alias_map, fuzzy_candidates):
    """
    Resolve a free-form genre name to a canonical name.
    Returns (canonical_name, resolution_method) or (None, None) if unresolved.
    """
    # 1. Exact match against musicology nodes
    if genre_name in musicology_nodes:
        return genre_name, "exact"

    # 2. Manual rename
    if genre_name in RENAME:
        renamed = RENAME[genre_name]
        if renamed in musicology_nodes:
            return renamed, "rename"

    # 3. Alias match via GENRE_VOCAB
    alias_result = alias_map.get(genre_name.lower())
    if alias_result and alias_result in musicology_nodes:
        return alias_result, "alias"

    # 4. Fuzzy match
    fuzzy_result = fuzzy_match(genre_name, fuzzy_candidates)
    if fuzzy_result:
        return fuzzy_result, "fuzzy"

    return None, None


def resolve_closest_known(closest_str, musicology_nodes, alias_map, fuzzy_candidates):
    """Split comma-separated closest_known and return first resolvable genre."""
    for candidate in closest_str.split(","):
        candidate = candidate.strip()
        if not candidate:
            continue
        resolved, method = resolve_genre(candidate, musicology_nodes, alias_map, fuzzy_candidates)
        if resolved:
            return resolved, method
    return None, None


def normalize():
    cache_path = DATA_DIR / "llm_genre_cache.jsonl"
    out_path = DATA_DIR / "llm_genre_cache_normalized.jsonl"
    discovered_path = DATA_DIR / "discovered_genres.json"

    musicology_nodes = load_musicology_nodes()
    alias_map = build_alias_map()
    fuzzy_candidates = list(musicology_nodes)

    # Load existing discovered genres
    discovered = {}
    if discovered_path.exists():
        with open(discovered_path, encoding="utf-8") as f:
            discovered = json.load(f)

    # Deduplicate cache (keep last entry per podcast_id)
    entries = {}
    with open(cache_path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    obj = json.loads(line)
                    entries[obj["podcast_id"]] = obj
                except (json.JSONDecodeError, KeyError):
                    pass

    stats = {"exact": 0, "rename": 0, "alias": 0, "fuzzy": 0, "discovered": 0, "unresolved": 0}
    fuzzy_log = []

    with open(out_path, "w", encoding="utf-8") as f:
        for entry in entries.values():
            new_genres = []
            seen = set()

            for g in entry.get("genres", []):
                if g in BLACKLIST:
                    continue

                canonical, method = resolve_genre(g, musicology_nodes, alias_map, fuzzy_candidates)

                if canonical:
                    stats[method] += 1
                    if method == "fuzzy":
                        fuzzy_log.append(f"  {g} -> {canonical}")
                    if canonical not in seen:
                        new_genres.append(canonical)
                        seen.add(canonical)
                else:
                    # Check if LLM provided discovered_genres metadata
                    llm_discovered = {d["name"]: d for d in entry.get("discovered_genres", [])}
                    if g in llm_discovered:
                        meta = llm_discovered[g]
                        closest = meta.get("closest_known", "")
                        closest_resolved, _ = resolve_closest_known(closest, musicology_nodes, alias_map, fuzzy_candidates)
                        if closest_resolved and closest_resolved not in seen:
                            new_genres.append(closest_resolved)
                            seen.add(closest_resolved)
                        # Add to discovered registry
                        if g not in discovered:
                            discovered[g] = {
                                "description": meta.get("description", ""),
                                "closest_known": closest_resolved or closest,
                                "family": meta.get("family", ""),
                                "episodes": [entry["podcast_id"]],
                                "status": "review",
                            }
                        elif entry["podcast_id"] not in discovered[g]["episodes"]:
                            discovered[g]["episodes"].append(entry["podcast_id"])
                        stats["discovered"] += 1
                    elif g in discovered:
                        # Step 5: Fallback via discovered_genres.json registry
                        meta = discovered[g]
                        closest = meta.get("closest_known", "")
                        closest_resolved, _ = resolve_closest_known(closest, musicology_nodes, alias_map, fuzzy_candidates)
                        if closest_resolved and closest_resolved not in seen:
                            new_genres.append(closest_resolved)
                            seen.add(closest_resolved)
                        if entry["podcast_id"] not in discovered[g].get("episodes", []):
                            discovered[g]["episodes"].append(entry["podcast_id"])
                        stats["discovered"] += 1
                    else:
                        # Completely unresolved — add to discovered for review
                        if g not in discovered:
                            discovered[g] = {
                                "description": "",
                                "closest_known": "",
                                "family": "",
                                "episodes": [entry["podcast_id"]],
                                "status": "review",
                            }
                        elif entry["podcast_id"] not in discovered[g]["episodes"]:
                            discovered[g]["episodes"].append(entry["podcast_id"])
                        stats["unresolved"] += 1

            entry["genres"] = new_genres
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # Save discovered genres
    with open(discovered_path, "w", encoding="utf-8") as f:
        json.dump(discovered, f, ensure_ascii=False, indent=2)

    print(f"Normalized {len(entries)} episodes")
    print(f"  Exact matches:    {stats['exact']}")
    print(f"  Renames:          {stats['rename']}")
    print(f"  Alias matches:    {stats['alias']}")
    print(f"  Fuzzy matches:    {stats['fuzzy']}")
    print(f"  Discovered:       {stats['discovered']}")
    print(f"  Unresolved:       {stats['unresolved']}")
    if fuzzy_log:
        print("  Fuzzy log:")
        for line in fuzzy_log:
            print(line)
    print(f"-> {out_path}")
    print(f"-> {discovered_path} ({len(discovered)} genres)")


if __name__ == "__main__":
    normalize()
