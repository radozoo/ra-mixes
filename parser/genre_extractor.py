"""
genre_extractor.py — extrakce žánrů bez LLM.

Strategie (v pořadí priority):
1. keywords pole z GraphQL (pokud není prázdné)
2. Regex match v description + blurb proti kurátorovanému slovníku
3. Regex match v title epizody

Výstup: seznam genre_edge objektů pro genre_edges.jsonl
"""

import json
import re
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Kurátorovaný genre slovník (~200 termínů)
# Formát: "canonical_name": ["alias1", "alias2", ...]
# ---------------------------------------------------------------------------
GENRE_VOCAB: dict[str, list[str]] = {
    "Techno": ["techno"],
    "House": ["house music", "house"],
    "Deep House": ["deep house"],
    "Tech House": ["tech house", "tech-house"],
    "Minimal Techno": ["minimal techno", "minimal tech", "minimal"],
    "Industrial Techno": ["industrial techno"],
    "Hard Techno": ["hard techno", "hardtechno"],
    "Ambient Techno": ["ambient techno"],
    "Detroit Techno": ["detroit techno"],
    "Berlin Techno": ["berlin techno"],
    "Acid Techno": ["acid techno"],
    "Acid House": ["acid house"],
    "Chicago House": ["chicago house"],
    "Garage House": ["garage house"],
    "UK Garage": ["uk garage", "ukg", "speed garage", "2-step", "2step"],
    "Electro": ["electro", "elektro"],
    "Electro House": ["electro house"],
    "Ambient": ["ambient", "dark ambient"],
    "Drone": ["drone music", "drone"],
    "Dub Techno": ["dub techno"],
    "Dub": ["dub music", "dub"],
    "Drum and Bass": ["drum and bass", "drum'n'bass", "dnb", "d&b", "d'n'b"],
    "Jungle": ["jungle music", "jungle", "ragga jungle"],
    "Breakbeat": ["breakbeat", "breaks", "nu breaks", "rave"],
    "Hardcore": ["hardcore techno", "hardcore", "gabber"],
    "Trance": ["trance music", "trance", "progressive trance", "psy-trance", "psytrance"],
    "Goa Trance": ["goa trance", "goa"],
    "Progressive House": ["progressive house"],
    "Nu-Disco": ["nu-disco", "nu disco", "disco"],
    "Italo Disco": ["italo disco", "italo"],
    "Funk": ["funk music", "funk"],
    "Soul": ["soul music", "soul"],
    "R&B": ["r&b", "rnb", "rhythm and blues"],
    "Hip Hop": ["hip hop", "hip-hop", "rap"],
    "Grime": ["grime"],
    "Dubstep": ["dubstep"],
    "Bass Music": ["bass music"],
    "Future Bass": ["future bass"],
    "Footwork": ["footwork", "juke"],
    "Juke": ["juke"],
    "Club Music": ["club music", "club"],
    "EBM": ["ebm", "electronic body music"],
    "Industrial": ["industrial music", "industrial"],
    "New Wave": ["new wave"],
    "Synth Pop": ["synth pop", "synthpop", "synth-pop"],
    "Post Punk": ["post punk", "post-punk"],
    "Noise": ["noise music", "noise"],
    "Experimental": ["experimental", "avant-garde", "avant garde"],
    "Electroacoustic": ["electroacoustic"],
    "Microhouse": ["microhouse", "micro-house"],
    "Glitch": ["glitch", "glitch hop"],
    "Downtempo": ["downtempo", "down tempo"],
    "Trip Hop": ["trip hop", "trip-hop"],
    "Chillout": ["chillout", "chill out", "chill-out"],
    "IDM": ["idm", "intelligent dance music"],
    "Electronic": ["electronic music", "electronic"],
    "Club Rap": ["club rap"],
    "Afrobeats": ["afrobeats", "afrobeat"],
    "Afro House": ["afro house", "afrohouse"],
    "Latin": ["latin house", "latin"],
    "Cumbia": ["cumbia"],
    "Baile Funk": ["baile funk", "funk carioca"],
    "Reggae": ["reggae"],
    "Reggaeton": ["reggaeton"],
    "Dancehall": ["dancehall"],
    "Ragga": ["ragga", "raggamuffin"],
    "UK Bass": ["uk bass"],
    "Rave": ["rave music", "rave"],
    "Wave": ["wave", "cold wave", "dark wave", "darkwave", "coldwave"],
    "Melodic Techno": ["melodic techno", "melodic house"],
    "Organic House": ["organic house"],
    "Lo-Fi": ["lo-fi", "lofi", "lo fi"],
    "Spoken Word": ["spoken word"],
    "Jazz": ["jazz", "jazz fusion"],
    "Classical": ["classical music", "classical"],
    "Krautrock": ["krautrock"],
    "Kosmische": ["kosmische", "kosmische musik"],
    "Balearic": ["balearic", "balearic beat"],
    "Tropical": ["tropical house", "tropical"],
}

# Předkompilované regex pro rychlost
_COMPILED: list[tuple[str, list[re.Pattern]]] = []

def _build_patterns():
    global _COMPILED
    _COMPILED = []
    for canonical, aliases in GENRE_VOCAB.items():
        patterns = []
        for alias in aliases:
            # Word boundary matching, case insensitive
            escaped = re.escape(alias)
            patterns.append(re.compile(r"\b" + escaped + r"\b", re.IGNORECASE))
        _COMPILED.append((canonical, patterns))

_build_patterns()

# ---------------------------------------------------------------------------
# LLM genre cache (loaded once, used by extract_genres)
# ---------------------------------------------------------------------------
_LLM_CACHE: dict[str, dict] = {}

def _load_llm_cache():
    global _LLM_CACHE
    cache_path = Path(__file__).parent.parent / "data" / "llm_genre_cache_normalized.jsonl"
    if not cache_path.exists():
        return
    with open(cache_path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    obj = json.loads(line)
                    _LLM_CACHE[obj["podcast_id"]] = obj
                except (json.JSONDecodeError, KeyError):
                    pass

_load_llm_cache()


def extract_genres_from_text(text: Optional[str]) -> list[dict]:
    """
    Hledá žánry v textu pomocí regex slovníku.
    Vrátí seznam {genre_raw, genre_canonical, confidence}.
    """
    if not text:
        return []
    found = {}
    for canonical, patterns in _COMPILED:
        for pat in patterns:
            m = pat.search(text)
            if m:
                raw = m.group(0).strip()
                if canonical not in found:
                    found[canonical] = raw
                break  # jeden hit na canonical stačí
    return [
        {"genre_raw": raw, "genre_canonical": canonical, "confidence": 0.7}
        for canonical, raw in found.items()
    ]


def extract_genres(episode: dict) -> list[dict]:
    """
    Extrahuje žánry z epizody a vrátí seznam genre_edge objektů.

    Priorita: LLM cache > regex fallback.
    episode: výstup parse_episode() z episode_parser.py
    """
    podcast_id = episode["podcast_id"]

    # 1. LLM cache (highest quality)
    if podcast_id in _LLM_CACHE:
        llm = _LLM_CACHE[podcast_id]
        return [
            {
                "entity_type": "episode",
                "entity_id": podcast_id,
                "genre_raw": g,
                "genre_canonical": g,
                "source": "llm",
                "confidence": 0.85,
            }
            for g in llm.get("genres", [])
        ]

    # 2. Fallback: regex extraction (for episodes not in LLM cache)
    edges = []

    for kw in episode.get("keywords", []):
        if kw:
            edges.append({
                "entity_type": "episode",
                "entity_id": podcast_id,
                "genre_raw": kw,
                "genre_canonical": _match_canonical(kw),
                "source": "keywords_field",
                "confidence": 0.9,
            })

    description_genres = extract_genres_from_text(episode.get("description"))
    for g in description_genres:
        edges.append({
            "entity_type": "episode",
            "entity_id": podcast_id,
            "genre_raw": g["genre_raw"],
            "genre_canonical": g["genre_canonical"],
            "source": "description",
            "confidence": 0.5,
        })

    blurb_genres = extract_genres_from_text(episode.get("blurb"))
    for g in blurb_genres:
        existing_canonicals = {e["genre_canonical"] for e in edges}
        if g["genre_canonical"] not in existing_canonicals:
            edges.append({
                "entity_type": "episode",
                "entity_id": podcast_id,
                "genre_raw": g["genre_raw"],
                "genre_canonical": g["genre_canonical"],
                "source": "blurb",
                "confidence": 0.4,
            })

    best: dict[str, dict] = {}
    for e in edges:
        key = e["genre_canonical"] if e["genre_canonical"] else e["genre_raw"]
        if key not in best or e["confidence"] > best[key]["confidence"]:
            best[key] = e

    return list(best.values())


def _match_canonical(raw: str) -> Optional[str]:
    """Najde kanonický název pro raw string."""
    for canonical, patterns in _COMPILED:
        for pat in patterns:
            if pat.search(raw):
                return canonical
    return raw  # neznámý žánr → vrátit raw jako canonical


# --- Quick test ---
if __name__ == "__main__":
    test_episode = {
        "podcast_id": "1049",
        "keywords": [],
        "description": "From the post-lockdown school of UK garage producers, Adam Emil Schierbeck, AKA Main Phase, is a rare international graduate. The Copenhagen producer has closely studied the British sound, shaping an international garage revival in his wake. Opening with a dub techno sound bath, Schierbeck's RA Mix draws us straight into the aqueous core of his style.",
        "blurb": "The ATW boss and honorary prince of UK garage steps up with a mix that might surprise you.",
    }
    genres = extract_genres(test_episode)
    print(f"Found {len(genres)} genres:")
    for g in genres:
        print(f"  [{g['source']}] {g['genre_raw']} → {g['genre_canonical']} (conf={g['confidence']})")
