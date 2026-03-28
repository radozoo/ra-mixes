"""
d3_exporter.py — generuje D3 network graph data z episodes.jsonl + genre_edges.jsonl.

Výstup:
  data/d3_nodes.json   — pole node objektů
  data/d3_links.json   — pole link objektů

Node typy:
  - "artist"   : jméno umělce (z episodes)
  - "genre"    : kanonický název žánru (z genre_edges)

Link typy:
  - "artist_genre"  : artist → genre (přes epizodu)
  - "genre_genre"   : genre → genre (sdílené v epizodě, silné kookurence)
"""

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

import jsonlines

DATA_DIR = Path(__file__).parent.parent / "data"


def build_graph(
    min_artist_episodes: int = 1,
    min_genre_edges: int = 1,
    include_genre_cooccurrence: bool = True,
    min_cooccurrence: int = 2,
) -> tuple[list[dict], list[dict]]:
    """
    Sestaví nodes + links pro D3 network visualization.

    Returns:
        nodes: list of node dicts
        links: list of link dicts
    """
    # Načti epizody
    episodes: dict[str, dict] = {}
    with jsonlines.open(DATA_DIR / "episodes.jsonl") as r:
        for ep in r:
            episodes[ep["podcast_id"]] = ep

    # Načti genre edges (čisté, normalizované)
    genre_edges: list[dict] = []
    clean_path = DATA_DIR / "genre_edges_clean.jsonl"
    fallback_path = DATA_DIR / "genre_edges.jsonl"
    with jsonlines.open(clean_path if clean_path.exists() else fallback_path) as r:
        genre_edges = list(r)

    # --- Statistiky pro nodes ---
    artist_ep_count: Counter = Counter()
    artist_genres: dict[str, Counter] = defaultdict(Counter)
    genre_ep_count: Counter = Counter()

    ep_genres: dict[str, list[str]] = defaultdict(list)  # podcast_id → [canonical genres]

    for ep in episodes.values():
        artist = ep.get("artist_name")
        if artist:
            artist_ep_count[artist] += 1

    for edge in genre_edges:
        pid = edge["entity_id"]
        canonical = edge["genre_canonical"]
        genre_ep_count[canonical] += 1
        ep_genres[pid].append(canonical)

        ep = episodes.get(pid, {})
        artist = ep.get("artist_name")
        if artist:
            artist_genres[artist][canonical] += 1

    # --- Nodes ---
    nodes = []
    node_ids = set()

    # Artist nodes
    for artist, count in artist_ep_count.items():
        if count < min_artist_episodes:
            continue
        node_id = f"artist:{artist}"
        nodes.append({
            "id": node_id,
            "type": "artist",
            "label": artist,
            "episode_count": count,
            "top_genres": [g for g, _ in artist_genres[artist].most_common(3)],
        })
        node_ids.add(node_id)

    # Genre nodes
    for genre, count in genre_ep_count.items():
        if count < min_genre_edges:
            continue
        node_id = f"genre:{genre}"
        nodes.append({
            "id": node_id,
            "type": "genre",
            "label": genre,
            "episode_count": count,
        })
        node_ids.add(node_id)

    # --- Links ---
    links = []
    seen_links: Counter = Counter()

    # Artist → Genre links
    for artist, genre_counts in artist_genres.items():
        artist_id = f"artist:{artist}"
        if artist_id not in node_ids:
            continue
        for genre, weight in genre_counts.items():
            genre_id = f"genre:{genre}"
            if genre_id not in node_ids:
                continue
            links.append({
                "source": artist_id,
                "target": genre_id,
                "type": "artist_genre",
                "weight": weight,
            })

    # Genre–Genre kookurence (žánry sdílené v epizodě)
    if include_genre_cooccurrence:
        for pid, genres in ep_genres.items():
            unique_genres = list(set(genres))
            for i in range(len(unique_genres)):
                for j in range(i + 1, len(unique_genres)):
                    g1, g2 = sorted([unique_genres[i], unique_genres[j]])
                    seen_links[(g1, g2)] += 1

        for (g1, g2), count in seen_links.items():
            if count < min_cooccurrence:
                continue
            id1, id2 = f"genre:{g1}", f"genre:{g2}"
            if id1 not in node_ids or id2 not in node_ids:
                continue
            links.append({
                "source": id1,
                "target": id2,
                "type": "genre_genre",
                "weight": count,
            })

    return nodes, links


def export(
    nodes_path: Optional[Path] = None,
    links_path: Optional[Path] = None,
    **kwargs,
):
    if nodes_path is None:
        nodes_path = DATA_DIR / "d3_nodes.json"
    if links_path is None:
        links_path = DATA_DIR / "d3_links.json"

    nodes, links = build_graph(**kwargs)

    with open(nodes_path, "w", encoding="utf-8") as f:
        json.dump(nodes, f, ensure_ascii=False, indent=2)

    with open(links_path, "w", encoding="utf-8") as f:
        json.dump(links, f, ensure_ascii=False, indent=2)

    print(f"Nodes: {len(nodes)} ({sum(1 for n in nodes if n['type']=='artist')} artists, {sum(1 for n in nodes if n['type']=='genre')} genres)")
    print(f"Links: {len(links)} ({sum(1 for l in links if l['type']=='artist_genre')} artist→genre, {sum(1 for l in links if l['type']=='genre_genre')} genre↔genre)")
    print(f"Uloženo: {nodes_path}, {links_path}")

    return nodes, links


if __name__ == "__main__":
    nodes, links = export()

    # Ukázka
    print("\nUkázka nodes (5):")
    for n in nodes[:5]:
        print(" ", n)
    print("\nUkázka links (5):")
    for l in links[:5]:
        print(" ", l)
