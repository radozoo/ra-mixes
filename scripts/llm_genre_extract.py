"""
llm_genre_extract.py — LLM-based genre extraction using Claude API.

Uses tool_use for structured output, per-track analysis for tracklist-based
episodes, and temperature=0 for deterministic results.

Usage:
  python scripts/llm_genre_extract.py --episodes 1037,1040    # specific episodes
  python scripts/llm_genre_extract.py                          # all uncached
  python scripts/llm_genre_extract.py --force                  # re-extract all

Output: data/llm_genre_cache.jsonl
"""

import argparse
import json
import glob
import re
import sys
import time
from pathlib import Path

import anthropic

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
CACHE_PATH = DATA_DIR / "llm_genre_cache.jsonl"

SYSTEM_PROMPT = """You are a music expert specializing in electronic, dance, and underground music.
You will receive information about a DJ mix from the Resident Advisor (RA) podcast series.
Your task is to classify the mix by genres and descriptive labels.

IMPORTANT:
- Use the TRACKLIST as the primary signal. Analyze each track's artist to determine genres.
- The editorial blurb/article is supplementary context only — do NOT let it override what the tracklist tells you.
- Include ANY genre that is genuinely represented, even obscure, regional, or emerging genres (e.g. Budots, Amapiano, Kuduro, Singeli).
- Do NOT force-fit into well-known genres. If the music is Budots, say Budots — not "Juke" or "Footwork"."""

# --- Tool schemas for structured output ---

TRACK_ANALYSIS_ITEM = {
    "type": "object",
    "properties": {
        "artist": {"type": "string"},
        "genre_signals": {
            "type": "array",
            "items": {"type": "string"},
            "description": "1-3 genres this artist/track represents. Use the actual genre name — any genre is valid, not limited to a vocabulary.",
        },
    },
    "required": ["artist", "genre_signals"],
}

DISCOVERED_GENRE_ITEM = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Genre name"},
        "description": {
            "type": "string",
            "description": "Brief description of the genre (1-2 sentences)",
        },
        "closest_known": {
            "type": "string",
            "description": "Nearest well-known genre (e.g. Baile Funk, Footwork, Dancehall)",
        },
        "family": {
            "type": "string",
            "enum": [
                "Techno",
                "House",
                "Groove",
                "Bass Culture",
                "Experimental",
                "Industrial",
                "Global Roots",
                "Hip Hop",
            ],
            "description": "Which genre family this belongs to",
        },
    },
    "required": ["name", "description", "closest_known", "family"],
}

CLASSIFY_TOOL_WITH_TRACKS = [
    {
        "name": "classify_mix",
        "description": "Submit genre classification for a DJ mix based on track-by-track analysis",
        "input_schema": {
            "type": "object",
            "properties": {
                "track_analysis": {
                    "type": "array",
                    "items": TRACK_ANALYSIS_ITEM,
                    "description": "Genre analysis for each track in the tracklist. Analyze every track.",
                },
                "mix_genres": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "2-8 overall genres for this mix, synthesized from the track analysis. Include ANY genre that is genuinely represented, even obscure or regional.",
                },
                "discovered_genres": {
                    "type": "array",
                    "items": DISCOVERED_GENRE_ITEM,
                    "description": "Genres not in the standard electronic music vocabulary (regional, emerging, niche). Leave empty if all genres are well-known.",
                },
                "labels": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "3-10 free-form descriptive tags: mood, setting, era, geography, tempo, vibe.",
                },
                "notes": {
                    "type": "string",
                    "description": "Brief notes on the classification rationale.",
                },
            },
            "required": ["track_analysis", "mix_genres", "labels"],
        },
    }
]

CLASSIFY_TOOL_NO_TRACKS = [
    {
        "name": "classify_mix",
        "description": "Submit genre classification for a DJ mix based on editorial content and artist knowledge",
        "input_schema": {
            "type": "object",
            "properties": {
                "mix_genres": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "2-6 overall genres for this mix. Include ANY genre that is genuinely represented, even obscure or regional.",
                },
                "discovered_genres": {
                    "type": "array",
                    "items": DISCOVERED_GENRE_ITEM,
                    "description": "Genres not in the standard electronic music vocabulary. Leave empty if all genres are well-known.",
                },
                "labels": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "3-10 free-form descriptive tags: mood, setting, era, geography, tempo, vibe.",
                },
                "notes": {
                    "type": "string",
                    "description": "Brief notes on the classification rationale.",
                },
            },
            "required": ["mix_genres", "labels"],
        },
    }
]

# --- Prompts ---

PROMPT_WITH_TRACKLIST = """Analyze this DJ mix. First, identify the genre(s) each track/artist represents.
Then synthesize the overall genre profile of the mix.

Artist: {artist}

Tracklist:
{tracklist}

---
Editorial blurb (supplementary — the tracklist above is the primary signal):
{blurb}

Editorial article (supplementary context only):
{content}"""

PROMPT_WITHOUT_TRACKLIST = """Analyze this DJ mix and classify its genres based on the editorial content
and the artist's known style.

No tracklist is available — use the editorial content and artist knowledge.

Artist: {artist}

Editorial blurb:
{blurb}

Editorial article:
{content}"""


def load_cache():
    """Load existing cache as {podcast_id: entry}."""
    cache = {}
    if CACHE_PATH.exists():
        with open(CACHE_PATH, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        obj = json.loads(line)
                        cache[obj["podcast_id"]] = obj
                    except (json.JSONDecodeError, KeyError):
                        pass
    return cache


def save_to_cache(entry):
    """Append one entry to cache file."""
    with open(CACHE_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def load_episode(podcast_id):
    """Load raw episode JSON."""
    path = DATA_DIR / "raw" / f"episode_{podcast_id}.json"
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def extract_one(client, podcast_id, model="claude-haiku-4-5-20251001"):
    """Extract genres for one episode via Claude API with tool_use."""
    raw = load_episode(podcast_id)
    if not raw:
        print(f"  EP {podcast_id}: raw file not found, skipping")
        return None

    title = raw.get("title", "")
    artist = re.sub(r'^RA\.\d+\s*', '', title).strip()
    if not artist:
        artist = (raw.get("artist") or {}).get("name") or "Unknown"

    blurb = (raw.get("translation") or {}).get("blurb", "") or ""
    content = (raw.get("translation") or {}).get("content", "") or ""
    tracklist = (raw.get("tracklist") or "").strip()

    # Truncate content to save tokens
    if len(content) > 1500:
        content = content[:1500] + "..."

    has_tracklist = bool(tracklist)

    if has_tracklist:
        user_msg = PROMPT_WITH_TRACKLIST.format(
            artist=artist, blurb=blurb, tracklist=tracklist, content=content,
        )
        tools = CLASSIFY_TOOL_WITH_TRACKS
    else:
        user_msg = PROMPT_WITHOUT_TRACKLIST.format(
            artist=artist, blurb=blurb, content=content,
        )
        tools = CLASSIFY_TOOL_NO_TRACKS

    response = client.messages.create(
        model=model,
        max_tokens=8192,
        temperature=0,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
        tools=tools,
        tool_choice={"type": "tool", "name": "classify_mix"},
    )

    # Parse tool_use response
    tool_block = next(
        (b for b in response.content if b.type == "tool_use"), None
    )
    if not tool_block:
        print(f"  EP {podcast_id}: no tool_use block in response")
        return None

    result = tool_block.input

    usage = {
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    }

    entry = {
        "podcast_id": str(podcast_id),
        "genres": result.get("mix_genres", []),
        "labels": result.get("labels", []),
        "notes": result.get("notes", ""),
        "model": model,
        "usage": usage,
    }

    if has_tracklist and "track_analysis" in result:
        entry["track_analysis"] = result["track_analysis"]

    if result.get("discovered_genres"):
        entry["discovered_genres"] = result["discovered_genres"]

    return entry


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--episodes", help="Comma-separated episode IDs")
    parser.add_argument("--force", action="store_true", help="Re-extract even if cached")
    parser.add_argument("--model", default="claude-haiku-4-5-20251001")
    args = parser.parse_args()

    client = anthropic.Anthropic()
    cache = load_cache()

    # Determine which episodes to process
    if args.episodes:
        episode_ids = [e.strip() for e in args.episodes.split(",")]
    else:
        episode_ids = []
        for f in sorted(glob.glob(str(DATA_DIR / "raw" / "episode_*.json")),
                        key=lambda x: int(x.split("_")[-1].replace(".json", ""))):
            pid = f.split("_")[-1].replace(".json", "")
            episode_ids.append(pid)

    # Filter cached (unless --force)
    if not args.force:
        episode_ids = [eid for eid in episode_ids if eid not in cache]

    print(f"Episodes to process: {len(episode_ids)}")
    if not episode_ids:
        print("Nothing to do.")
        return

    total_input = 0
    total_output = 0

    for i, eid in enumerate(episode_ids):
        print(f"[{i+1}/{len(episode_ids)}] EP {eid}...", end=" ", flush=True)
        try:
            entry = extract_one(client, eid, model=args.model)
            if entry:
                save_to_cache(entry)
                total_input += entry["usage"]["input_tokens"]
                total_output += entry["usage"]["output_tokens"]
                discovered = entry.get("discovered_genres", [])
                disc_str = f" | discovered: {[d['name'] for d in discovered]}" if discovered else ""
                print(f"-> genres={entry['genres']}"
                      f"\n         labels={entry['labels']}{disc_str}"
                      f" ({entry['usage']['input_tokens']}+{entry['usage']['output_tokens']} tok)")
            # Rate limit
            if i < len(episode_ids) - 1:
                time.sleep(0.5)
        except Exception as e:
            print(f"ERROR: {e}")

    print(f"\nDone. Total tokens: {total_input} input + {total_output} output = {total_input + total_output}")
    print(f"Estimated cost (Haiku): ${total_input * 0.80 / 1_000_000 + total_output * 4.0 / 1_000_000:.4f}")


if __name__ == "__main__":
    main()
