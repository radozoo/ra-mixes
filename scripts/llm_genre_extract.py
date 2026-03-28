"""
llm_genre_extract.py — LLM-based genre extraction using Claude API.

Usage:
  python scripts/llm_genre_extract.py --episodes 1037,1015,1,200    # specific episodes
  python scripts/llm_genre_extract.py                                # all uncached
  python scripts/llm_genre_extract.py --force                        # re-extract all

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

sys.path.insert(0, str(ROOT))
from parser.genre_extractor import GENRE_VOCAB

GENRE_LIST = sorted(GENRE_VOCAB.keys())

SYSTEM_PROMPT = """You are a music expert specializing in electronic and dance music.
You will receive information about a DJ mix from the Resident Advisor (RA) podcast series.
Your task is to classify the mix by genres AND descriptive labels."""

PROMPT_WITH_TRACKLIST = """Analyze this RA podcast mix and provide two things:

1. **genres**: Choose 2-6 genres from this vocabulary:
{genres}
The tracklist is a strong signal — use the track artists and titles to identify genres.
Combine with editorial context from the blurb and article.

2. **labels**: Free-form descriptive tags (3-10) that capture non-genre characteristics of this mix. Examples of label categories (use your own words, not limited to these):
- Mood/energy: hypnotic, euphoric, dark, introspective, high-energy, melancholic, dreamy
- Setting: club, festival, afterhours, home listening, sunrise, warehouse
- Era/influence: 90s, classic, contemporary, futuristic, retro
- Geography: Detroit, Berlin, UK, Chicago, Tokyo, Caribbean, West Africa
- Tempo/style: slow-burn, fast, vinyl-only, live, sample-heavy, vocal, instrumental
- Vibe: underground, leftfield, peak-time, warm-up, eclectic, psychedelic

IMPORTANT:
- For genres: only tag a genre if the music is actually that style, not because the word appears in English text.
- For labels: be specific and evocative, based on the actual content. Avoid generic tags.
- If the music's primary genre is NOT in the vocabulary, include it in "genres" anyway alongside the closest vocabulary matches. Real accuracy matters more than staying in the list.

Artist: {artist}
Blurb: {blurb}

Tracklist:
{tracklist}

Editorial content:
{content}

Return valid JSON only, no other text:
{{"genres": ["Genre1", "Genre2"], "labels": ["label1", "label2", "label3"], "notes": "optional"}}"""

PROMPT_WITHOUT_TRACKLIST = """Analyze this RA podcast mix and provide two things:

1. **genres**: Choose 2-6 genres from this vocabulary:
{genres}
No tracklist is available. Use the editorial content and the artist's known style.

2. **labels**: Free-form descriptive tags (3-10) that capture non-genre characteristics of this mix. Examples of label categories (use your own words, not limited to these):
- Mood/energy: hypnotic, euphoric, dark, introspective, high-energy, melancholic, dreamy
- Setting: club, festival, afterhours, home listening, sunrise, warehouse
- Era/influence: 90s, classic, contemporary, futuristic, retro
- Geography: Detroit, Berlin, UK, Chicago, Tokyo, Caribbean, West Africa
- Tempo/style: slow-burn, fast, vinyl-only, live, sample-heavy, vocal, instrumental
- Vibe: underground, leftfield, peak-time, warm-up, eclectic, psychedelic

IMPORTANT:
- For genres: only tag a genre if the music is actually that style, not because the word appears in English text.
- For labels: be specific and evocative, based on the actual content. Avoid generic tags.
- If the music's primary genre is NOT in the vocabulary, include it in "genres" anyway alongside the closest vocabulary matches. Real accuracy matters more than staying in the list.

Artist: {artist}
Blurb: {blurb}

Editorial content:
{content}

Return valid JSON only, no other text:
{{"genres": ["Genre1", "Genre2"], "labels": ["label1", "label2", "label3"], "notes": "optional"}}"""


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
    """Extract genres for one episode via Claude API."""
    raw = load_episode(podcast_id)
    if not raw:
        print(f"  EP {podcast_id}: raw file not found, skipping")
        return None

    title = raw.get("title", "")
    # Artist from title: "RA.1018 DJ Love..." → "DJ Love..."
    artist = re.sub(r'^RA\.\d+\s*', '', title).strip()
    if not artist:
        artist = (raw.get("artist") or {}).get("name") or "Unknown"

    blurb = (raw.get("translation") or {}).get("blurb", "") or ""
    content = (raw.get("translation") or {}).get("content", "") or ""
    tracklist = (raw.get("tracklist") or "").strip()

    # Truncate content to save tokens
    if len(content) > 1500:
        content = content[:1500] + "..."

    if tracklist:
        user_msg = PROMPT_WITH_TRACKLIST.format(
            genres=", ".join(GENRE_LIST),
            artist=artist,
            blurb=blurb,
            tracklist=tracklist,
            content=content,
        )
    else:
        user_msg = PROMPT_WITHOUT_TRACKLIST.format(
            genres=", ".join(GENRE_LIST),
            artist=artist,
            blurb=blurb,
            content=content,
        )

    response = client.messages.create(
        model=model,
        max_tokens=300,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )

    # Parse response
    text = response.content[0].text.strip()
    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        # Try to extract JSON from response
        m = re.search(r'\{.*\}', text, re.DOTALL)
        if m:
            result = json.loads(m.group())
        else:
            print(f"  EP {podcast_id}: failed to parse response: {text[:100]}")
            return None

    # Token usage
    usage = {
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    }

    entry = {
        "podcast_id": str(podcast_id),
        "genres": result.get("genres", []),
        "labels": result.get("labels", []),
        "notes": result.get("notes", ""),
        "model": model,
        "usage": usage,
    }

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
        # All episodes
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
                print(f"→ genres={entry['genres']}"
                      f"\n         labels={entry['labels']}"
                      f" ({entry['usage']['input_tokens']}+{entry['usage']['output_tokens']} tok)"
                      f"{' [' + entry['notes'] + ']' if entry['notes'] else ''}")
            # Rate limit: ~50 req/min for haiku
            if i < len(episode_ids) - 1:
                time.sleep(0.5)
        except Exception as e:
            print(f"ERROR: {e}")

    print(f"\nDone. Total tokens: {total_input} input + {total_output} output = {total_input + total_output}")
    print(f"Estimated cost (Haiku): ${total_input * 0.80 / 1_000_000 + total_output * 4.0 / 1_000_000:.4f}")
    print(f"Extrapolated for 1046 episodes: "
          f"~{total_input * 1046 / len(episode_ids):.0f} input + "
          f"~{total_output * 1046 / len(episode_ids):.0f} output tokens, "
          f"~${(total_input * 1046 / len(episode_ids)) * 0.80 / 1_000_000 + (total_output * 1046 / len(episode_ids)) * 4.0 / 1_000_000:.2f}")


if __name__ == "__main__":
    main()
