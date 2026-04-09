"""
build_network_html.py — generates self-contained ra_genre_network.html.

Reads:
  data/raw/episode_*.json      (raw episode data with article/qa content)
  data/genre_edges_clean.jsonl (clean genre assignments per episode)
  data/tracks.jsonl            (parsed tracklist data)
  data/llm_genre_cache_with_categories.jsonl (LLM labels + categories)
  data/genre_musicology.json   (musicological genre relationships)
  src/css/style.css            (Tokyo Night theme CSS)
  src/js/main.js               (JS source, bundled by Parcel → dist/main.js)

Output:
  ra_genre_network.html     (single-file D3 visualization)
  genre_mapping_gaps.txt    (unmapped genres, if any)
"""

import json
import glob
import re
import html
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"


def _sanitize_html(html_str):
    """Strip script tags, ensure links open in new tab."""
    if not html_str:
        return None
    s = re.sub(r'<script[^>]*>.*?</script>', '', html_str, flags=re.DOTALL | re.IGNORECASE)
    s = re.sub(r'<a ', '<a target="_blank" rel="noopener" ', s)
    return s.strip() or None


def _split_content(html_str):
    """Split content into article + Q&A based on first <b>...?</b> tag."""
    if not html_str:
        return None, None
    # Find first bold tag containing a question mark
    m = re.search(r'<b>[^<]*\?[^<]*</b>', html_str)
    if m:
        article = html_str[:m.start()].strip()
        qa = html_str[m.start():].strip()
        # Clean up trailing whitespace / empty paragraphs from article
        article = re.sub(r'\s*(<br\s*/?>|\n)+\s*$', '', article)
        return article or None, qa or None
    return html_str, None


def _normalize_keywords(raw):
    """Normalize RA keywords: decode HTML entities, title case, deduplicate."""
    if not raw:
        return None
    seen = {}
    result = []
    for kw in raw.split(','):
        kw = html.unescape(kw).strip()
        if not kw:
            continue
        normalized = kw.title()
        key = normalized.lower()
        if key not in seen:
            seen[key] = True
            result.append(normalized)
    return ','.join(result) if result else None


def load_mixes():
    """Load mixes from raw JSON + Excel (genres, parsed tracks)."""
    # ── Raw JSON episodes ────────────────────────────────────────────────
    raw_map = {}
    for fpath in glob.glob(str(DATA_DIR / "raw" / "episode_*.json")):
        with open(fpath, encoding="utf-8") as f:
            d = json.load(f)
        pid = d.get("podcast_id") or d.get("id")
        if not pid:
            continue
        pid = str(pid)
        title = d.get("title") or ""
        mix_m = re.match(r'RA\.(\d+)', title)
        mix_number = mix_m.group(1) if mix_m else pid
        artist_obj = d.get("artist") or {}
        trans = d.get("translation") or {}
        raw_map[pid] = {
            "mix_number": mix_number,
            "artist": re.sub(r'^RA\.\d+\s*', '', title).strip()
                      or (artist_obj.get("name") if artist_obj.get("name") not in (None, "None") else None)
                      or "Unknown",
            "artist_id": artist_obj.get("id"),
            "date": (d.get("date") or "")[:10] or None,
            "duration": d.get("duration"),
            "blurb": (trans.get("blurb") or "").strip() or None,
            "article": None,  # set below
            "qa": None,       # set below
            "imageUrl": d.get("imageUrl"),
            "streamingUrl": d.get("streamingUrl") or None,
            "url": d.get("url"),
            "keywords": _normalize_keywords(d.get("keywords")),
        }
        sanitized = _sanitize_html(trans.get("content"))
        article, qa = _split_content(sanitized)
        raw_map[pid]["article"] = article
        raw_map[pid]["qa"] = qa

    # ── Genre edges from genre_edges_clean.jsonl ────────────────────────
    import jsonlines as _jsonlines
    genre_map = {}
    ge_path = DATA_DIR / "genre_edges_clean.jsonl"
    if ge_path.exists():
        with _jsonlines.open(ge_path) as reader:
            for edge in reader:
                pid = str(edge["entity_id"])
                genre = edge["genre_canonical"]
                if pid not in genre_map:
                    genre_map[pid] = []
                if genre not in genre_map[pid]:
                    genre_map[pid].append(genre)

    # ── Parsed tracks from tracks.jsonl ─────────────────────────────────
    tracks_map = {}
    tr_path = DATA_DIR / "tracks.jsonl"
    if tr_path.exists():
        with _jsonlines.open(tr_path) as reader:
            for row in reader:
                pid = str(row["podcast_id"])
                if pid not in tracks_map:
                    tracks_map[pid] = []
                t = {"artist": row.get("artist", ""), "title": row.get("title", "")}
                if row.get("label"):
                    t["label"] = row["label"]
                tracks_map[pid].append(t)

    # ── LLM cache (labels + genres) ─────────────────────────────────────
    llm_cache = {}
    # Prefer enriched cache with label_categories if available
    for llm_path in [
        DATA_DIR / "llm_genre_cache_with_categories.jsonl",
        DATA_DIR / "llm_genre_cache_normalized.jsonl",
    ]:
        if llm_path.exists():
            with open(llm_path, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        obj = json.loads(line)
                        llm_cache[obj["podcast_id"]] = obj
            break

    # ── Merge ────────────────────────────────────────────────────────────
    mixes = []
    for pid in sorted(raw_map.keys(), key=lambda x: int(x), reverse=True):
        ep = raw_map[pid]
        ep["genres"] = genre_map.get(pid, [])
        ep["tracks"] = tracks_map.get(pid, [])
        ep["labels"] = llm_cache.get(pid, {}).get("labels", [])
        ep["label_categories"] = llm_cache.get(pid, {}).get("label_categories", {})
        ep["id"] = pid
        mixes.append(ep)

    # ── Sort by date DESC (newest first) for proper chronological display ────
    mixes.sort(key=lambda m: m.get("date") or "", reverse=True)

    return mixes


def check_gaps(mixes, hierarchy):
    """Find genres in mixes that aren't in the hierarchy."""
    node_ids = {n["id"] for n in hierarchy["nodes"]}
    all_mix_genres = set()
    for m in mixes:
        all_mix_genres.update(m["genres"])

    gaps = sorted(all_mix_genres - node_ids)
    if gaps:
        gap_path = ROOT / "genre_mapping_gaps.txt"
        with open(gap_path, "w") as f:
            f.write("Genres in Excel that have no node in genre_hierarchy.json:\n\n")
            for g in gaps:
                count = sum(1 for m in mixes if g in m["genres"])
                f.write(f"  {g} ({count} episodes)\n")
        print(f"WARNING: {len(gaps)} unmapped genres → genre_mapping_gaps.txt")
    else:
        print("All genres mapped successfully.")
    return gaps


def build_html(mixes, graph):
    """Build self-contained HTML from src/ files + data.

    1. Runs Parcel to bundle src/js/main.js → dist/main.js
    2. Reads CSS from src/css/style.css
    3. Injects window.__RA_DATA__ with graph + mix data
    4. Produces ra_genre_network.html (no external runtime deps except D3 CDN + Google Fonts)
    """
    # Recalculate node counts from actual mixes data
    genre_counts = {}
    for m in mixes:
        for g in m.get("genres", []):
            genre_counts[g] = genre_counts.get(g, 0) + 1
    for node in graph["nodes"]:
        node["count"] = genre_counts.get(node["id"], 0)

    nodes_json = json.dumps(graph["nodes"], ensure_ascii=False)
    edges_for_js = []
    for e in graph["edges"]:
        ejs = {"source": e["source"], "target": e["target"], "weight": e.get("strength", e.get("weight", 1))}
        if "note" in e:
            ejs["note"] = e["note"]
        if "type" in e:
            ejs["type"] = e["type"]
        edges_for_js.append(ejs)
    edges_json = json.dumps(edges_for_js, ensure_ascii=False)
    mixes_json = json.dumps(mixes, ensure_ascii=False)

    total_mixes = len(mixes)
    total_genres = len(graph["nodes"])
    total_edges = len(graph["edges"])
    total_artists = len(set(m.get("artist", "") for m in mixes if m.get("artist")))

    # ── Bundle JS with Parcel ────────────────────────────────────────────
    print("  Running Parcel build...")
    result = subprocess.run(
        ["npm", "run", "build"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"  Parcel stderr: {result.stderr}")
        raise RuntimeError("Parcel build failed — check npm run build output above")
    bundle_js = (ROOT / "dist" / "main.js").read_text(encoding="utf-8")
    print(f"  Bundle: {len(bundle_js) // 1024} KB")

    # ── Read CSS ─────────────────────────────────────────────────────────
    css = (ROOT / "src" / "css" / "style.css").read_text(encoding="utf-8")

    # ── Body HTML template ───────────────────────────────────────────────
    body_html = (
        '<body>\n\n<div class="header">\n  <span class="title" style="cursor:pointer" onclick="resetApp()">RA Podcast Mixes</span>\n  <span class="stat"><span>{total_mixes}</span> mixes</span>\n  <span class="stat"><span>{total_artists}</span> artists</span>\n  <span class="stat"><span>{total_genres}</span> genres</span>\n</div>\n\n<div class="container">\n  <!-- Left: episode list -->\n  <div class="sidebar">\n    <div class="search-box">\n      <input type="text" id="search" placeholder="Search episodes...">\n      <button class="search-clear" id="searchClear" style="display:none">✕</button>\n    </div>\n    <div class="episode-list" id="episodeList"></div>\n    <div class="sidebar-player" id="sidebarPlayer"></div>\n  </div>\n\n  <!-- Center: tabs + views -->\n  <div class="center-panel">\n    <div class="center-tabs">\n      <button class="center-tab active" data-view="graph">Genre Map</button>\n      <button class="center-tab" data-view="labels">Explore</button>\n    </div>\n    <div class="graph-area" id="graphArea">\n      <svg id="graph"></svg>\n      <div class="graph-search" id="graphSearch">\n        <span class="graph-search-icon">⌕</span>\n        <input type="text" class="graph-search-input" id="graphSearchInput" placeholder="Search genres..." autocomplete="off">\n        <button class="graph-search-clear" id="graphSearchClear">✕</button>\n        <div class="graph-search-dropdown" id="graphSearchDropdown"></div>\n      </div>\n    </div>\n    <div class="tooltip" id="tooltip"></div>\n    <div class="label-filter-area" id="labelFilterArea" style="display:none">\n      <div class="label-search-box">\n        <input type="text" id="labelSearch" placeholder="Search labels and genres...">\n        <button class="label-search-clear" id="labelSearchClear" style="display:none">✕</button>\n      </div>\n      <div class="active-filters" id="activeFilters"></div>\n      <div class="genre-filter-section" id="genreFilterSection"></div>\n      <div class="label-masonry" id="labelMasonry"></div>\n    </div>\n    <div id="mixesArea">\n      <div id="mixesList"></div>\n      <div id="mixesDetail" style="display:none"></div>\n    </div>\n  </div>\n\n  <!-- Right: episode detail -->\n  <div class="detail-panel collapsed" id="detailPanel">\n    <div class="sheet-handle"></div>\n    <div id="detailContent">\n      <div class="detail-placeholder">Select an episode to see details</div>\n    </div>\n  </div>\n</div>\n\n<!-- Mobile bottom tab bar -->\n<nav class="mobile-tab-bar" id="mobileTabBar">\n  <button class="mobile-tab" data-view="mixes">\n    <svg viewBox="0 0 24 24">\n      <line x1="4" y1="6" x2="20" y2="6"/>\n      <line x1="4" y1="12" x2="20" y2="12"/>\n      <line x1="4" y1="18" x2="20" y2="18"/>\n    </svg>\n    <span>Mixes</span>\n  </button>\n  <button class="mobile-tab active" data-view="graph">\n    <svg viewBox="0 0 24 24">\n      <circle cx="6" cy="6" r="1.5"/><circle cx="18" cy="6" r="1.5"/><circle cx="12" cy="12" r="1.5"/>\n      <circle cx="6" cy="18" r="1.5"/><circle cx="18" cy="18" r="1.5"/>\n      <line x1="6" y1="6" x2="12" y2="12"/><line x1="18" y1="6" x2="12" y2="12"/>\n      <line x1="6" y1="18" x2="12" y2="12"/><line x1="18" y1="18" x2="12" y2="12"/>\n    </svg>\n    <span>Genre Map</span>\n  </button>\n  <button class="mobile-tab" data-view="labels">\n    <svg viewBox="0 0 24 24">\n      <circle cx="12" cy="12" r="9"/>\n      <circle cx="12" cy="12" r="5"/>\n      <circle cx="12" cy="12" r="1"/>\n    </svg>\n    <span>Explore</span>\n  </button>\n</nav>'
    ).format(
        total_mixes=total_mixes,
        total_artists=total_artists,
        total_genres=total_genres,
    )

    # ── Assemble HTML ────────────────────────────────────────────────────
    data_script = (
        "window.__RA_DATA__={"
        f'"nodes":{nodes_json},'
        f'"edges":{edges_json},'
        f'"mixes":{mixes_json}'
        "};"
    )

    return (
        '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>RA Podcast Mixes</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.9.0/d3.min.js"></script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;500;600;700;800&family=Lexend:wght@300;400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>'''
        + css
        + '''</style>
</head>
'''
        + body_html
        + '''

<script>'''
        + data_script
        + '''</script>
<script>'''
        + bundle_js
        + '''</script>
</body>
</html>'''
    )


def main():
    print("Loading mixes (from JSONL, no Excel)...")
    mixes = load_mixes()
    print(f"  {len(mixes)} episodes loaded")

    print("Loading genre musicology graph...")
    with open(DATA_DIR / "genre_musicology.json") as f:
        graph = json.load(f)
    print(f"  {len(graph['nodes'])} nodes, {len(graph['edges'])} edges")

    check_gaps(mixes, graph)

    print("Building HTML...")
    html = build_html(mixes, graph)

    out_path = ROOT / "ra_genre_network.html"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  → {out_path} ({len(html)//1024} KB)")


if __name__ == "__main__":
    main()
