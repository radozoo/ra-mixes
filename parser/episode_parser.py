"""
episode_parser.py — mapuje raw GraphQL JSON → strukturovaná epizoda pro episodes.jsonl
"""

import re
from datetime import datetime, timezone
from typing import Optional


def parse_duration(duration_str: Optional[str]) -> Optional[int]:
    """'HH:MM:SS' nebo 'MM:SS' → počet sekund."""
    if not duration_str:
        return None
    parts = duration_str.split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
    except ValueError:
        pass
    return None


def strip_html(text: Optional[str]) -> Optional[str]:
    """Odstraní HTML tagy z textu."""
    if not text:
        return None
    return re.sub(r"<[^>]+>", "", text).strip() or None


def parse_episode(raw: dict) -> dict:
    """
    Převede raw GraphQL response na strukturovanou epizodu.

    Vstup: dict z data/raw/episode_{id}.json
    Výstup: dict odpovídající schématu episodes.jsonl
    """
    podcast_id = str(raw.get("id") or raw.get("podcast_id", ""))
    url = f"https://ra.co/podcast/{podcast_id}"

    artist_obj = raw.get("artist") or {}
    artist_name = artist_obj.get("name") if isinstance(artist_obj, dict) else None
    artist_id = str(artist_obj.get("id", "")) if isinstance(artist_obj, dict) else None

    # Fallback: odvoď meno umelca z titulu "RA.XXX Artist Name"
    if not artist_name:
        import re as _re
        _m = _re.match(r"^RA\.\d+\s+(.+)$", raw.get("title", ""), _re.IGNORECASE)
        if _m:
            artist_name = _m.group(1).strip()

    translation = raw.get("translation") or {}
    description_html = translation.get("content") if isinstance(translation, dict) else None
    blurb = translation.get("blurb") if isinstance(translation, dict) else None
    description = strip_html(description_html)

    tracklist_raw = raw.get("tracklist") or None
    if tracklist_raw == "":
        tracklist_raw = None
    has_tracklist = bool(tracklist_raw)

    # keywords — bývají oddělené čárkou nebo mezerou
    keywords_raw = raw.get("keywords") or ""
    keywords = [k.strip() for k in re.split(r"[,\n]", keywords_raw) if k.strip()]

    # Datum
    date_str = raw.get("date")
    date_iso = None
    if date_str:
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            date_iso = dt.strftime("%Y-%m-%d")
        except ValueError:
            date_iso = date_str[:10] if len(date_str) >= 10 else date_str

    # Určení kvality scrape
    if raw.get("source") == "failed":
        quality = "failed"
    elif raw.get("source") == "dom":
        quality = "partial"
    elif has_tracklist:
        quality = "full"
    else:
        quality = "no_tracklist"

    return {
        "podcast_id": podcast_id,
        "url": url,
        "title": raw.get("title"),
        "artist_name": artist_name,
        "artist_id": artist_id,
        "date": date_iso,
        "duration_seconds": parse_duration(raw.get("duration")),
        "duration_raw": raw.get("duration"),
        "image_url": raw.get("imageUrl"),
        "streaming_url": raw.get("streamingUrl"),
        "description": description,
        "blurb": blurb,
        "keywords": keywords,
        "has_tracklist": has_tracklist,
        "tracklist_raw": tracklist_raw,
        "archived": raw.get("archived"),
        "scrape_source": raw.get("source", "unknown"),
        "scrape_quality": quality,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }
