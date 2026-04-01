"""
build_genre_hierarchy.py — builds genre hierarchy DAG (L1/L2/L3) + cross-genre edges.

Output: data/genre_hierarchy.json
"""

import json
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"

# ── L1 Families ──────────────────────────────────────────────────────────────

FAMILIES = {
    "Techno": "#f2355b",
    "House": "#f59e42",
    "Bass": "#00c9a7",
    "Disco & Soul": "#ffc857",
    "Experimental": "#c77dff",
    "Global": "#45e89d",
    "Industrial & Wave": "#7eb8d4",
    "Downtempo": "#a78bfa",
}

# ── Hierarchy: family → { L2: [L3, ...] } ───────────────────────────────────

HIERARCHY = {
    "Techno": {
        "Techno": ["Minimal Techno", "Detroit Techno", "Berlin Techno",
                    "Melodic Techno", "Dub Techno", "Ambient Techno",
                    "Acid Techno", "Industrial Techno", "Hard Techno",
                    "Abstract Techno", "Broken Techno", "Experimental Techno",
                    "Percussive Techno", "Psychedelic Techno", "Hardgroove"],
        "Trance": ["Goa Trance", "Psychedelic", "Eurodance"],
        "Electro": [],
        "Hardcore": ["Gabber", "Breakcore", "Hi-NRG"],
    },
    "House": {
        "House": ["Deep House", "Tech House", "Chicago House", "Acid House",
                  "Garage House", "Microhouse", "Electro House",
                  "Progressive House", "Organic House", "Afro House",
                  "Ambient House", "Dream House", "Jackin House",
                  "Minimal House", "Tribal House", "Latin House"],
    },
    "Bass": {
        "Drum and Bass": ["Jungle", "Liquid Funk", "Techstep"],
        "Dubstep": ["Bassline"],
        "Bass Music": ["Future Bass", "UK Bass"],
        "UK Garage": ["2-step", "UK Funky", "Jersey Club"],
        "Grime": ["Drill"],
        "Breakbeat": ["Footwork", "Broken Beat", "Baltimore Club"],
        "Ghetto House": ["Ghetto Tech", "Booty Bass", "Miami Bass"],
    },
    "Disco & Soul": {
        "Disco": ["Italo Disco", "Cosmic Disco", "Disco House", "Boogie"],
        "Nu-Disco": ["Balearic"],
        "Funk": [],
        "Soul": ["R&B"],
        "Hip Hop": ["Club Rap", "Trap", "Chopped and Screwed"],
    },
    "Experimental": {
        "Ambient": ["Drone", "Chillout", "Dark Ambient"],
        "Experimental": ["Electroacoustic", "Glitch", "Minimalism",
                         "Electronica", "Exotica", "Percussion"],
        "Noise": [],
        "IDM": [],
        "Krautrock": ["Kosmische", "Psychedelic Rock"],
    },
    "Global": {
        "Afrobeats": ["Amapiano", "Gqom", "Highlife", "Afrobeat",
                      "Afrofuturism", "Singeli"],
        "Latin": ["Cumbia", "Reggaeton", "Baile Funk", "Dembow", "Guaracha"],
        "Reggae": ["Dub", "Dancehall", "Ragga"],
        "Tropical": ["Kuduro", "Batida"],
        "World Music": ["Folk", "Desert Blues"],
    },
    "Industrial & Wave": {
        "Industrial": ["EBM"],
        "New Wave": ["Synth Pop", "Post Punk"],
        "Wave": ["Dark Wave", "Cold Wave", "Minimal Wave", "Minimal Synth"],
    },
    "Downtempo": {
        "Downtempo": ["Trip Hop", "Lo-Fi"],
        "Spoken Word": [],
        "Jazz": [],
        "Classical": [],
        "Pop": [],
        "Ballroom": [],
    },
}

# ── Cross-genre edges ────────────────────────────────────────────────────────

CROSS_EDGES = [
    ("Dub", "Dub Techno", "production_technique",
     "Dub production (echo, delay, space) applied to techno"),
    ("Dub", "Dubstep", "cultural_origin",
     "Dubstep emerged from UK dub/reggae sound system culture"),
    ("Reggae", "Jungle", "cultural_origin",
     "Jungle originated from ragga/reggae breakbeat culture"),
    ("Hip Hop", "Grime", "cultural_origin",
     "Grime emerged from UK hip hop + garage MC culture"),
    ("Hip Hop", "Trip Hop", "cultural_origin",
     "Trip Hop = Bristol hip hop + soul + dub fusion"),
    ("UK Garage", "Dubstep", "rhythm_origin",
     "Dubstep evolved from dark garage / 2-step rhythms"),
    ("UK Garage", "Grime", "rhythm_origin",
     "Grime MCs came from UK garage pirate radio scene"),
    ("Detroit Techno", "Electro", "cultural_origin",
     "Both rooted in Detroit/Belleville Three + Kraftwerk"),
    ("Acid House", "Acid Techno", "production_technique",
     "Shared TB-303 acid bassline production"),
    ("Chicago House", "Footwork", "cultural_origin",
     "Footwork/juke originated in Chicago from house DJs"),
    ("Industrial", "EBM", "cultural_origin",
     "EBM is the dancefloor arm of industrial music"),
    ("Industrial", "Hard Techno", "production_technique",
     "Hard techno borrows industrial textures + distortion"),
    ("Ambient", "Downtempo", "mood_texture",
     "Shared atmospheric, slow, contemplative mood"),
    ("Ambient", "Kosmische", "mood_texture",
     "Kosmische pioneered ambient electronics"),
    ("Afro House", "Afrobeats", "cultural_origin",
     "Shared African rhythmic and cultural roots"),
    ("Nu-Disco", "Funk", "cultural_origin",
     "Nu-disco is modern re-edits of funk and disco records"),
    ("Post Punk", "Wave", "mood_texture",
     "Wave (cold/dark wave) shares post-punk sonic aesthetics"),
    ("Breakbeat", "Drum and Bass", "rhythm_origin",
     "DnB evolved from breakbeat / amen break culture"),
]


def build():
    # Load episode counts from genre_map.json if available
    ep_counts = {}
    genre_map_path = DATA_DIR / "genre_map.json"
    if genre_map_path.exists():
        with open(genre_map_path) as f:
            gm = json.load(f)
            ep_counts = gm.get("genre_counts", {})

    nodes = []
    edges = []

    # Track all genre IDs for gap detection
    all_genre_ids = set()

    # Build L1 nodes
    for family, color in FAMILIES.items():
        fam_id = f"{family}_family"
        nodes.append({
            "id": fam_id,
            "label": family,
            "level": "L1",
            "family": family,
            "color": color,
        })

    # Build L2/L3 nodes + hierarchical edges
    for family, branches in HIERARCHY.items():
        fam_id = f"{family}_family"
        for l2_genre, l3_genres in branches.items():
            all_genre_ids.add(l2_genre)
            nodes.append({
                "id": l2_genre,
                "label": l2_genre,
                "level": "L2",
                "family": family,
                "color": FAMILIES[family],
                "episode_count": ep_counts.get(l2_genre, 0),
            })
            edges.append({
                "source": fam_id,
                "target": l2_genre,
                "edge_type": "hierarchical",
            })

            for l3_genre in l3_genres:
                all_genre_ids.add(l3_genre)
                nodes.append({
                    "id": l3_genre,
                    "label": l3_genre,
                    "level": "L3",
                    "family": family,
                    "color": FAMILIES[family],
                    "parent": l2_genre,
                    "episode_count": ep_counts.get(l3_genre, 0),
                })
                edges.append({
                    "source": l2_genre,
                    "target": l3_genre,
                    "edge_type": "hierarchical",
                })

    # Cross-genre edges
    for src, tgt, rel_type, notes in CROSS_EDGES:
        edges.append({
            "source": src,
            "target": tgt,
            "edge_type": "cross",
            "relationship_type": rel_type,
            "notes": notes,
        })

    result = {"nodes": nodes, "edges": edges}

    out_path = DATA_DIR / "genre_hierarchy.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # Stats
    l1 = sum(1 for n in nodes if n["level"] == "L1")
    l2 = sum(1 for n in nodes if n["level"] == "L2")
    l3 = sum(1 for n in nodes if n["level"] == "L3")
    hier = sum(1 for e in edges if e["edge_type"] == "hierarchical")
    cross = sum(1 for e in edges if e["edge_type"] == "cross")
    print(f"Nodes: {len(nodes)} (L1={l1}, L2={l2}, L3={l3})")
    print(f"Edges: {len(edges)} (hierarchical={hier}, cross={cross})")
    print(f"→ {out_path}")

    return all_genre_ids


if __name__ == "__main__":
    build()
