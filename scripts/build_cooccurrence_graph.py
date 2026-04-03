"""
build_cooccurrence_graph.py — builds genre co-occurrence graph from LLM cache.

Edges = number of mixes sharing two genres (real data, not taxonomy).
Output: data/genre_cooccurrence.json
"""

import json
from collections import Counter
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"

# Family colors (soft tint, not strict categories)
FAMILY_MAP = {
    "Techno": ["Techno", "Minimal Techno", "Detroit Techno", "Berlin Techno",
               "Melodic Techno", "Dub Techno", "Ambient Techno", "Acid Techno",
               "Hard Techno", "Abstract Techno", "Broken Techno", "Microhouse",
               "Experimental Techno", "Percussive Techno", "Psychedelic Techno",
               "Hardgroove", "Trance", "Goa Trance", "Psychedelic", "Eurodance",
               "Electro", "Hardcore", "Gabber", "Breakcore", "Hi-NRG"],
    "House": ["House", "Deep House", "Tech House", "Chicago House", "Acid House",
              "Garage House", "Electro House", "Electrohouse", "Progressive House",
              "Organic House", "Afro House", "Dream House",
              "Jackin House", "Minimal House", "Tribal House", "Latin House"],
    "Groove": ["Disco", "Italo Disco", "Cosmic Disco", "Disco House",
               "Boogie", "Nu-Disco", "Balearic", "Funk", "Soul"],
    "Bass Culture": ["Drum and Bass", "Jungle", "Liquid Funk", "Techstep", "Dubstep",
                     "Bassline", "Bass Music", "Future Bass", "UK Bass", "UK Garage",
                     "2-step", "UK Funky", "Jersey Club", "Grime", "Breakbeat",
                     "Footwork", "Juke", "Broken Beat", "Baltimore Club", "Ghetto House",
                     "Ghetto Tech", "Booty Bass", "Miami Bass"],
    "Experimental": ["Ambient", "Drone", "Chillout", "Dark Ambient",
                     "Experimental", "Electroacoustic", "Glitch", "Minimalism",
                     "Electronica", "Percussion", "Noise", "IDM",
                     "Downtempo", "Trip Hop", "Lo-Fi", "Ambient House"],
    "Industrial": ["Industrial", "EBM", "Industrial Techno", "New Wave", "Synth Pop",
                   "Post Punk", "Wave", "Dark Wave", "Cold Wave",
                   "Minimal Wave", "Minimal Synth"],
    "Global Roots": ["Afrobeats", "Amapiano", "Gqom", "Highlife", "Afrobeat",
                     "Afrofuturism", "Singeli", "Latin", "Cumbia", "Reggaeton",
                     "Baile Funk", "Dembow", "Guaracha", "Reggae", "Dub", "Dancehall",
                     "Ragga", "Tropical", "Kuduro", "Batida", "World Music", "World",
                     "Folk", "Desert Blues", "Jazz", "R&B", "Tribal",
                     "Krautrock", "Kosmische", "Psychedelic Rock",
                     "Classical", "Pop", "Exotica", "Spoken Word", "Ballroom"],
    "Hip Hop": ["Hip Hop", "Club Rap", "Trap", "Drill", "Chopped and Screwed"],
}

FAMILY_COLORS = {
    "Techno": "#d41d4a",
    "House": "#f59e42",
    "Groove": "#fceba5",
    "Bass Culture": "#06b6d4",
    "Experimental": "#c77dff",
    "Industrial": "#94a3b8",
    "Global Roots": "#22c55e",
    "Hip Hop": "#fb7eb8",
}

# Invert: genre → family
GENRE_TO_FAMILY = {}
for family, genres in FAMILY_MAP.items():
    for g in genres:
        GENRE_TO_FAMILY[g] = family


def build(min_edge_weight=5, min_node_count=2):
    cache_path = DATA_DIR / "llm_genre_cache_normalized.jsonl"
    entries = {}
    with open(cache_path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                obj = json.loads(line)
                entries[obj["podcast_id"]] = obj

    # Count genres
    genre_count = Counter()
    for e in entries.values():
        genre_count.update(e["genres"])

    # Co-occurrences
    cooccur = Counter()
    for e in entries.values():
        genres = list(set(e["genres"]))
        for i in range(len(genres)):
            for j in range(i + 1, len(genres)):
                pair = tuple(sorted([genres[i], genres[j]]))
                cooccur[pair] += 1

    # Filter nodes
    valid_genres = {g for g, c in genre_count.items() if c >= min_node_count}

    # Build nodes
    nodes = []
    for g, count in sorted(genre_count.items(), key=lambda x: -x[1]):
        if g not in valid_genres:
            continue
        family = GENRE_TO_FAMILY.get(g, "Experimental")
        nodes.append({
            "id": g,
            "count": count,
            "family": family,
            "color": FAMILY_COLORS.get(family, "#888"),
        })

    node_ids = {n["id"] for n in nodes}

    # Build edges
    edges = []
    for (g1, g2), weight in sorted(cooccur.items(), key=lambda x: -x[1]):
        if weight < min_edge_weight:
            continue
        if g1 not in node_ids or g2 not in node_ids:
            continue
        edges.append({
            "source": g1,
            "target": g2,
            "weight": weight,
        })

    result = {"nodes": nodes, "edges": edges}
    out_path = DATA_DIR / "genre_cooccurrence.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"Nodes: {len(nodes)} genres (min {min_node_count} mixes)")
    print(f"Edges: {len(edges)} co-occurrences (min {min_edge_weight} shared mixes)")
    print(f"→ {out_path}")
    return result


if __name__ == "__main__":
    build()
