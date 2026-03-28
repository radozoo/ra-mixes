"""
tracklist_parser.py — parsuje raw tracklist text na seznam strukturovaných tracků.

Bez LLM. Regex heuristiky pro různé formáty RA tracklist textů.

Typické formáty:
  "01. Artist - Title"
  "01. Artist - Title [Label]"
  "01. Artist - Title (Label)"
  "HH:MM Artist - Title"
  "HH:MM:SS Artist - Title"
  "Artist - Title"
  "01. Title (Artist Remix)"   ← remix varianty
"""

import re
from html.parser import HTMLParser
from typing import Optional


class _HTMLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self._parts = []

    def handle_data(self, data):
        self._parts.append(data)

    def get_text(self):
        return "".join(self._parts)


def _strip_html(s: str) -> str:
    stripper = _HTMLStripper()
    stripper.feed(s)
    return stripper.get_text()


# Separator: regular dash OR em-dash OR en-dash (with surrounding spaces)
_SEP = r"\s*[-–—]\s+"

# Hlavní regex patterns (od nejpřesnějšího po nejvolnější)
_PATTERNS = [
    # "01. Artist - Title [Label]" nebo "01. Artist - Title (Label)"
    re.compile(
        r"^(?P<pos>\d{1,3})[.)]\s+"
        r"(?P<artist>.+?)" + _SEP +
        r"(?P<title>.+?)"
        r"(?:\s+[\[(](?P<label>[^\])\n]+)[\])])?$",
        re.IGNORECASE,
    ),
    # "01. Artist 'Title' Label"  (starý RA formát s apostrofmi)
    re.compile(
        r"^(?P<pos>\d{1,3})[.)]\s+"
        r"(?P<artist>.+?)\s+"
        r"['\u2018\u2019](?P<title>[^''\u2018\u2019]+)['\u2018\u2019]"
        r"(?:\s+(?P<label>.+))?$",
        re.IGNORECASE,
    ),
    # "01. Artist \"Title\" (Label)"  — greedy artist, posledný quoted string = title
    re.compile(
        r"^(?P<pos>\d{1,3})[.)]\s+"
        r"(?P<artist>.+)\s+"
        r"[\"\u201c\u201d](?P<title>[^\"\u201c\u201d]+)[\"\u201c\u201d]"
        r"(?:\s+\((?P<label>[^)]+)\))?$",
        re.IGNORECASE,
    ),
    # "HH:MM Artist - Title" nebo "HH:MM:SS Artist - Title"
    re.compile(
        r"^(?P<ts>\d{1,2}:\d{2}(?::\d{2})?)\s+"
        r"(?P<artist>.+?)" + _SEP +
        r"(?P<title>.+)$",
        re.IGNORECASE,
    ),
    # "Artist - Title" (bez čísla)
    re.compile(
        r"^(?P<artist>.+?)" + _SEP + r"(?P<title>.+)$",
        re.IGNORECASE,
    ),
]

# Řádky, které přeskočíme (nejsou tracky)
_SKIP_PATTERNS = [
    re.compile(r"^\s*$"),                          # prázdné
    re.compile(r"^tracklist", re.IGNORECASE),      # "Tracklist:" header
    re.compile(r"^\[.*\]$"),                       # [annotation only]
    re.compile(r"^#\d+"),                          # "#1" popularity indicators
    re.compile(r"^<b>", re.IGNORECASE),            # <b>header</b> riadky
    re.compile(r"^artists?\s+featured", re.IGNORECASE),  # "Artists featured in..."
]

# Riadok je zrejme header/anotácia ak po strip_html neobsahuje separator
_HAS_HTML = re.compile(r"<[^>]+>")


def parse_tracklist(raw_tracklist: str, podcast_id: str) -> list[dict]:
    """
    Parsuje raw tracklist string → seznam track objektů.

    Každý track:
      track_id, podcast_id, position, artist, title, label,
      timestamp, raw_line, parse_confidence
    """
    if not raw_tracklist or not raw_tracklist.strip():
        return []

    lines = raw_tracklist.splitlines()
    tracks = []
    position = 0

    for raw_line in lines:
        raw_line = raw_line.strip()

        # Přeskoč nerelevantní řádky (na raw_line, pred HTML stripom)
        if any(pat.match(raw_line) for pat in _SKIP_PATTERNS):
            continue

        # Strip HTML pred matchovaním patternom
        line = _strip_html(raw_line).strip() if _HAS_HTML.search(raw_line) else raw_line

        if not line:
            continue

        position += 1
        track = _parse_line(line, raw_line, podcast_id, position)
        tracks.append(track)

    return tracks


def _parse_line(line: str, raw_line: str, podcast_id: str, position: int) -> dict:
    """Parsuje jeden řádek tracklist."""
    base = {
        "track_id": f"{podcast_id}_{position:03d}",
        "podcast_id": podcast_id,
        "position": position,
        "artist": None,
        "title": None,
        "label": None,
        "timestamp": None,
        "raw_line": raw_line,
        "parse_confidence": "low",
    }

    # Pattern 1: číslo + artist - title [label]
    m = _PATTERNS[0].match(line)
    if m:
        base.update({
            "position": int(m.group("pos")),
            "artist": _clean(m.group("artist")),
            "title": _clean(m.group("title")),
            "label": _clean(m.group("label")) if m.group("label") else None,
            "parse_confidence": "high",
        })
        return base

    # Pattern 2: číslo + artist 'title' label
    m = _PATTERNS[1].match(line)
    if m:
        base.update({
            "position": int(m.group("pos")),
            "artist": _clean(m.group("artist")),
            "title": _clean(m.group("title")),
            "label": _clean(m.group("label")) if m.group("label") else None,
            "parse_confidence": "high",
        })
        return base

    # Pattern 3: číslo + artist "title" (label)
    m = _PATTERNS[2].match(line)
    if m:
        base.update({
            "position": int(m.group("pos")),
            "artist": _clean(m.group("artist")),
            "title": _clean(m.group("title")),
            "label": _clean(m.group("label")) if m.group("label") else None,
            "parse_confidence": "high",
        })
        return base

    # Pattern 4: timestamp + artist - title
    m = _PATTERNS[3].match(line)
    if m:
        base.update({
            "timestamp": m.group("ts"),
            "artist": _clean(m.group("artist")),
            "title": _clean(m.group("title")),
            "parse_confidence": "high",
        })
        return base

    # Pattern 5: artist - title (bez čísla/timestampu)
    m = _PATTERNS[4].match(line)
    if m:
        base.update({
            "artist": _clean(m.group("artist")),
            "title": _clean(m.group("title")),
            "parse_confidence": "medium",
        })
        return base

    # Žádný pattern nesedí → uložíme čistý text, nízká confidence
    base["title"] = line
    return base


def _clean(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    if _HAS_HTML.search(s):
        s = _strip_html(s)
    return s.strip().strip("'\"") or None


# --- Quick test ---
if __name__ == "__main__":
    sample = """01. Recondite - Drifting [Ghostly International]
02. Burial – Archangel
HH:MM Objekt - Needle & Thread
Artist Without Number - Title Here
<b>Artists featured in the podcast:</b>
just a random line without dash
1. <a href="/dj-page.aspx?id=1731">Move D</a> – Like I Was King - <a href="">Compost</a>"""

    tracks = parse_tracklist(sample, "999")
    for t in tracks:
        print(t["artist"], "—", t["title"])
