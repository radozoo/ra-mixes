"""
build_network_html.py — generates self-contained ra_genre_network.html.

Reads:
  data/ra_full_export.xlsx  (Episodes + Genre Edges sheets)
  data/genre_hierarchy.json (nodes + edges DAG)

Output:
  ra_genre_network.html     (single-file D3 visualization)
  genre_mapping_gaps.txt    (unmapped genres, if any)
"""

import json
import glob
import re
from pathlib import Path
import openpyxl

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
            "keywords": d.get("keywords") or None,
        }
        sanitized = _sanitize_html(trans.get("content"))
        article, qa = _split_content(sanitized)
        raw_map[pid]["article"] = article
        raw_map[pid]["qa"] = qa

    # ── Genre edges from Excel ───────────────────────────────────────────
    wb = openpyxl.load_workbook(DATA_DIR / "ra_full_export.xlsx", read_only=True)

    ws_ge = wb["Genre Edges"]
    ge_rows = list(ws_ge.iter_rows(values_only=True))
    ge_headers = ge_rows[0]
    eid_col = ge_headers.index("entity_id")
    gc_col = ge_headers.index("genre_canonical")

    genre_map = {}
    for row in ge_rows[1:]:
        pid = str(row[eid_col])
        genre = row[gc_col]
        if pid not in genre_map:
            genre_map[pid] = []
        if genre not in genre_map[pid]:
            genre_map[pid].append(genre)

    # ── Parsed tracks from Excel ─────────────────────────────────────────
    ws_tr = wb["Tracks"]
    tr_rows = list(ws_tr.iter_rows(values_only=True))
    tr_headers = tr_rows[0]
    tc = {h: i for i, h in enumerate(tr_headers)}

    tracks_map = {}
    for row in tr_rows[1:]:
        pid = str(row[tc["podcast_id"]])
        if pid not in tracks_map:
            tracks_map[pid] = []
        t = {"artist": row[tc["artist"]], "title": row[tc["title"]]}
        if row[tc["label"]]:
            t["label"] = row[tc["label"]]
        tracks_map[pid].append(t)

    wb.close()

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
    nodes_json = json.dumps(graph["nodes"], ensure_ascii=False)
    edges_json = json.dumps(graph["edges"], ensure_ascii=False)
    mixes_json = json.dumps(mixes, ensure_ascii=False)

    total_mixes = len(mixes)
    total_genres = len(graph["nodes"])
    total_edges = len(graph["edges"])

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>RA Genre Network</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.9.0/d3.min.js"></script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600&display=swap" rel="stylesheet">
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
  background: #0a0a0a;
  color: #e0e0e0;
  font-family: 'SF Mono', 'Fira Code', 'Cascadia Code', monospace;
  overflow: hidden;
  height: 100vh;
}}

/* Header */
.header {{
  height: 40px;
  background: #1a1a1a;
  border-bottom: 1px solid #333;
  display: flex;
  align-items: center;
  padding: 0 16px;
  gap: 16px;
  font-size: 13px;
}}
.header .title {{ font-weight: 700; color: #fff; letter-spacing: 1px; }}
.header .stat {{ color: #888; }}
.header .stat span {{ color: #ccc; }}

/* Layout: 3-panel */
.container {{
  display: flex;
  height: calc(100vh - 40px);
}}

/* Left sidebar — episode list */
.sidebar {{
  width: 260px;
  min-width: 260px;
  background: #1a1a1a;
  border-right: 1px solid #333;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}}
.search-box {{
  padding: 10px;
  border-bottom: 1px solid #333;
}}
.search-box input {{
  width: 100%;
  padding: 8px 10px;
  background: #0a0a0a;
  border: 1px solid #444;
  border-radius: 4px;
  color: #e0e0e0;
  font-family: inherit;
  font-size: 12px;
  outline: none;
}}
.search-box input:focus {{ border-color: #666; }}
.episode-list {{
  flex: 1;
  overflow-y: auto;
  padding: 4px 0;
}}
.episode-list::-webkit-scrollbar {{ width: 6px; }}
.episode-list::-webkit-scrollbar-track {{ background: #1a1a1a; }}
.episode-list::-webkit-scrollbar-thumb {{ background: #444; border-radius: 3px; }}

.ep-item {{
  padding: 6px 12px;
  cursor: pointer;
  font-size: 11px;
  color: #999;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  transition: background 0.15s;
}}
.ep-item:hover {{ background: #252525; color: #ddd; }}
.ep-item.active {{
  background: #2a2a2a;
  color: #fff;
  border-left: 2px solid #e63946;
}}
.ep-item .ep-num {{ color: #666; margin-right: 6px; }}
.ep-item.active .ep-num {{ color: #e63946; }}

/* Center panel — tabs + views */
.center-panel {{
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}}
.center-tabs {{
  display: flex;
  background: #1a1a1a;
  border-bottom: 1px solid #333;
  flex-shrink: 0;
}}
.center-tab {{
  background: none;
  border: none;
  color: #888;
  padding: 10px 22px;
  cursor: pointer;
  font-family: inherit;
  font-size: 15px;
  border-bottom: 2px solid transparent;
  transition: color 0.15s;
}}
.center-tab:hover {{ color: #ccc; }}
.center-tab.active {{ color: #fff; border-bottom-color: #4fc3f7; }}

/* Center — graph */
.graph-area {{
  flex: 1;
  position: relative;
  overflow: hidden;
}}
.graph-area svg {{ width: 100%; height: 100%; }}

/* Label filter area */
.label-filter-area {{
  flex: 1;
  padding: 14px 18px;
  overflow-y: auto;
  font-family: 'DM Sans', sans-serif;
}}
.label-filter-area::-webkit-scrollbar {{ width: 6px; }}
.label-filter-area::-webkit-scrollbar-track {{ background: #0a0a0a; }}
.label-filter-area::-webkit-scrollbar-thumb {{ background: #444; border-radius: 3px; }}

/* Active filters bar */
.active-filters {{
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 5px;
  min-height: 28px;
  margin-bottom: 14px;
  padding-bottom: 10px;
  border-bottom: 1px solid #222;
}}
.active-filters:empty {{ display: none; }}
.active-filter-chip.label-chip {{
  font-size: 13px;
  padding: 4px 10px 4px 12px;
  font-style: normal;
  border-radius: 10px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  transition: opacity 0.15s;
}}
.active-filter-chip:hover {{ opacity: 0.8; }}
.active-filter-chip .remove {{ opacity: 0.5; font-size: 16px; }}
.active-filter-chip .remove:hover {{ opacity: 1; }}
.clear-filters-btn {{
  font-size: 13px;
  color: #666;
  cursor: pointer;
  padding: 2px 8px;
  border: 1px solid #333;
  border-radius: 10px;
  background: none;
  font-family: inherit;
  transition: color 0.15s;
}}
.clear-filters-btn:hover {{ color: #e63946; border-color: #e63946; }}
.filter-match-count {{
  font-size: 13px;
  color: #666;
  margin-left: auto;
}}

/* Genre filter section (full width, above masonry) */
.genre-filter-section {{
  margin-bottom: 16px;
  padding: 12px 14px;
  background: #111;
  border: 1px solid #252525;
  border-radius: 8px;
}}
.genre-filter-title {{
  font-size: 11px;
  text-transform: uppercase;
  color: #888;
  margin-bottom: 10px;
  letter-spacing: 1px;
  font-weight: 600;
}}
.genre-filter-items {{
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}}
.genre-filter-chip {{
  font-size: 13px;
  padding: 4px 10px;
  border-radius: 10px;
  cursor: pointer;
  color: #fff;
  opacity: 0.7;
  font-family: inherit;
  border: none;
  transition: opacity 0.15s, box-shadow 0.15s;
}}
.genre-filter-chip:hover {{ opacity: 1; }}
.genre-filter-chip.selected {{
  opacity: 1;
  box-shadow: 0 0 0 1.5px rgba(255,255,255,0.6);
}}
.genre-filter-chip .chip-count {{
  font-size: 10px;
  opacity: 0.55;
  margin-left: 3px;
}}

/* Masonry layout for label categories */
.label-masonry {{
  columns: 2;
  column-gap: 14px;
}}
@media (min-width: 1200px) {{
  .label-masonry {{ columns: 3; }}
}}

/* Category tile */
.label-cat-section {{
  break-inside: avoid;
  margin-bottom: 14px;
  padding: 10px 12px 8px;
  background: #111;
  border: 1px solid #252525;
  border-radius: 8px;
  border-left: 3px solid #444;
}}
.label-cat-section[data-cat="mood"]      {{ border-left-color: #7c4fa0; }}
.label-cat-section[data-cat="energy"]    {{ border-left-color: #c76b00; }}
.label-cat-section[data-cat="setting"]   {{ border-left-color: #0080b0; }}
.label-cat-section[data-cat="geography"] {{ border-left-color: #007a40; }}
.label-cat-section[data-cat="style"]     {{ border-left-color: #0050c0; }}
.label-cat-section[data-cat="era"]       {{ border-left-color: #a08000; }}
.label-cat-section[data-cat="vibe"]      {{ border-left-color: #a0006a; }}

.label-cat-title {{
  font-size: 11px;
  text-transform: uppercase;
  color: #666;
  margin-bottom: 8px;
  letter-spacing: 1px;
  font-weight: 600;
}}
.label-cat-items {{
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}}
.label-filter-area .filter-label-chip.label-chip {{
  font-size: 13px;
  padding: 4px 10px;
  border-radius: 10px;
  cursor: pointer;
  border: 1px solid;
  opacity: 0.65;
  font-style: normal;
  transition: opacity 0.15s, box-shadow 0.15s;
}}
.label-filter-area .filter-label-chip:hover {{ opacity: 1; }}
.label-filter-area .filter-label-chip.selected {{
  opacity: 1;
  box-shadow: 0 0 0 1px rgba(255,255,255,0.5);
}}
.label-filter-area .filter-label-chip .chip-count {{
  font-size: 10px;
  opacity: 0.5;
  margin-left: 2px;
}}
.show-more-btn {{
  font-size: 11px;
  color: #555;
  cursor: pointer;
  padding: 3px 8px;
  background: none;
  border: 1px solid #333;
  border-radius: 8px;
  font-family: inherit;
  margin-top: 6px;
  transition: color 0.15s;
}}
.show-more-btn:hover {{ color: #aaa; border-color: #555; }}

/* Active filter chip for genres */
.active-filter-chip.genre-chip {{
  font-size: 12px;
  padding: 3px 8px 3px 10px;
  border-radius: 10px;
  cursor: pointer;
  color: #fff;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  border: none;
}}

/* Edge filter buttons */
.edge-filters {{
  position: absolute;
  bottom: 12px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  gap: 6px;
  background: rgba(26, 26, 26, 0.9);
  padding: 6px 10px;
  border-radius: 6px;
  border: 1px solid #333;
}}
.edge-btn {{
  padding: 4px 10px;
  font-size: 11px;
  font-family: inherit;
  background: #252525;
  border: 1px solid #444;
  border-radius: 3px;
  color: #999;
  cursor: pointer;
  transition: all 0.15s;
}}
.edge-btn:hover {{ color: #ddd; border-color: #666; }}
.edge-btn.active {{ color: #fff; border-color: #888; background: #333; }}

/* Tooltip */
.tooltip {{
  position: absolute;
  pointer-events: none;
  background: rgba(0,0,0,0.85);
  border: 1px solid #555;
  border-radius: 4px;
  padding: 6px 10px;
  font-size: 11px;
  color: #fff;
  white-space: nowrap;
  display: none;
}}

/* Node labels */
.node-label {{
  fill: #ccc;
  text-anchor: middle;
  pointer-events: none;
  font-family: 'SF Mono', 'Fira Code', monospace;
}}

/* Pulse animation */
@keyframes pulse-ring {{
  0% {{ stroke-opacity: 0.8; stroke-width: 3; }}
  100% {{ stroke-opacity: 0; stroke-width: 8; }}
}}
.pulse {{ animation: pulse-ring 1.2s ease-out infinite; }}

/* Right panel — episode detail */
.detail-panel {{
  width: 360px;
  min-width: 360px;
  background: #141414;
  border-left: 1px solid #333;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  overflow-x: hidden;
  transition: width 0.2s;
}}
.detail-panel::-webkit-scrollbar {{ width: 6px; }}
.detail-panel::-webkit-scrollbar-track {{ background: #141414; }}
.detail-panel::-webkit-scrollbar-thumb {{ background: #333; border-radius: 3px; }}
.detail-panel.collapsed {{
  width: 0;
  min-width: 0;
  border-left: none;
}}
.detail-header {{
  padding: 14px 16px 10px;
  border-bottom: 1px solid #2a2a2a;
}}
.detail-header .ep-title {{
  font-size: 16px;
  font-weight: 700;
  color: #fff;
  margin-bottom: 2px;
}}
.detail-header .ep-artist {{
  font-size: 13px;
  color: #ccc;
  margin-bottom: 8px;
}}
.detail-meta {{
  display: flex;
  gap: 12px;
  font-size: 11px;
  color: #777;
  margin-bottom: 10px;
}}
.detail-meta .meta-item {{ display: flex; align-items: center; gap: 4px; }}
.detail-meta .meta-val {{ color: #aaa; }}

/* Genre chips */
.genre-chips {{
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 4px;
}}
.genre-chip {{
  font-size: 10px;
  padding: 2px 8px;
  border-radius: 10px;
  color: #fff;
  opacity: 0.9;
  cursor: pointer;
  transition: opacity 0.15s;
}}
.genre-chip:hover {{ opacity: 1; }}

/* Cover image */
.detail-cover {{
  width: 100%;
  height: 180px;
  overflow: hidden;
  border-bottom: 1px solid #2a2a2a;
}}
.detail-cover img {{
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: top;
}}

/* Links */
.detail-links {{
  display: flex;
  gap: 6px;
  margin-bottom: 8px;
}}
.detail-link {{
  font-size: 10px;
  padding: 3px 10px;
  border-radius: 3px;
  background: #252525;
  border: 1px solid #444;
  color: #ccc;
  text-decoration: none;
  transition: all 0.15s;
}}
.detail-link:hover {{ background: #333; color: #fff; border-color: #666; }}

/* Keyword chips */
.kw-chips {{
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 6px;
}}
.kw-chip {{
  font-size: 9px;
  padding: 1px 7px;
  border-radius: 8px;
  border: 1px solid #444;
  color: #888;
}}

/* Label chips */
.label-chips {{
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 6px;
}}
.label-chip {{
  font-size: 9px;
  padding: 1px 7px;
  border-radius: 8px;
  border: 1px solid #555;
  color: #aaa;
  background: #1a1a1a;
  font-style: italic;
}}
/* Category-colored label chips */
.label-chip[data-cat="mood"]      {{ background: #2d1b3d; border-color: #7c4fa0; color: #c4a0e8; }}
.label-chip[data-cat="energy"]    {{ background: #2d1a00; border-color: #c76b00; color: #ffb040; }}
.label-chip[data-cat="setting"]   {{ background: #001e2d; border-color: #0080b0; color: #50bce8; }}
.label-chip[data-cat="geography"] {{ background: #001a0e; border-color: #007a40; color: #40c878; }}
.label-chip[data-cat="style"]     {{ background: #001530; border-color: #0050c0; color: #5090f0; }}
.label-chip[data-cat="era"]       {{ background: #2a2000; border-color: #a08000; color: #e0c040; }}
.label-chip[data-cat="vibe"]      {{ background: #2a001a; border-color: #a0006a; color: #f060c0; }}
/* Category group header */
.label-cat-group {{
  display: contents;
}}
.label-cat-dot {{
  display: inline-block;
  width: 6px; height: 6px;
  border-radius: 50%;
  margin-right: 2px;
  vertical-align: middle;
}}

/* Blurb */
.detail-blurb {{
  padding: 10px 16px;
  font-size: 11px;
  line-height: 1.5;
  color: #bbb;
  font-style: italic;
  border-bottom: 1px solid #2a2a2a;
}}

/* Article (full content) */
.detail-article {{
  padding: 12px 16px;
  font-size: 11px;
  line-height: 1.6;
  color: #999;
  border-bottom: 1px solid #2a2a2a;
}}
.detail-article b {{ color: #ddd; font-weight: 600; }}
.detail-article i {{ color: #aaa; }}
.detail-article a {{ color: #6ba3d6; text-decoration: none; }}
.detail-article a:hover {{ text-decoration: underline; }}
.detail-section-header {{
  padding: 10px 16px 4px;
  font-size: 10px;
  font-weight: 600;
  color: #555;
  text-transform: uppercase;
  letter-spacing: 1px;
  border-top: 1px solid #2a2a2a;
}}
.detail-qa b {{
  display: block;
  margin-top: 12px;
  margin-bottom: 4px;
  color: #ccc;
  font-size: 11px;
}}

/* Tracklist */

.tracklist-header {{
  padding: 10px 16px 6px;
  font-size: 11px;
  font-weight: 600;
  color: #666;
  text-transform: uppercase;
  letter-spacing: 1px;
  position: sticky;
  top: 0;
  background: #141414;
}}
.track-item {{
  padding: 5px 16px;
  font-size: 11px;
  line-height: 1.4;
  border-bottom: 1px solid #1a1a1a;
}}
.track-item .track-num {{
  color: #555;
  display: inline-block;
  width: 24px;
  text-align: right;
  margin-right: 8px;
}}
.track-item .track-artist {{
  color: #ccc;
}}
.track-item .track-title {{
  color: #888;
}}
.track-item .track-label {{
  color: #555;
  font-style: italic;
}}
.no-tracklist {{
  padding: 16px;
  color: #555;
  font-size: 11px;
  font-style: italic;
}}

/* Detail placeholder */
.detail-placeholder {{
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #444;
  font-size: 12px;
  text-align: center;
  padding: 20px;
}}

/* Close/clear button */
.detail-close {{
  position: absolute;
  top: 12px;
  right: 12px;
  background: none;
  border: 1px solid #444;
  border-radius: 3px;
  color: #888;
  font-size: 11px;
  padding: 2px 8px;
  cursor: pointer;
  font-family: inherit;
}}
.detail-close:hover {{ color: #ccc; border-color: #666; }}

/* Sidebar player */
.sidebar-player {{
  border-top: 1px solid #333;
  background: #111;
  padding: 0;
  min-height: 0;
}}
.sidebar-player .player-info {{
  padding: 6px 12px 4px;
  font-size: 10px;
}}
.sidebar-player .player-ep {{ color: #666; }}
.sidebar-player .player-artist {{ color: #ccc; font-weight: 600; }}
.sidebar-player iframe {{
  width: 100%;
  border: none;
  display: block;
}}
.sidebar-player.sc iframe {{ height: 125px; }}
.sidebar-player.mc iframe {{ height: 90px; }}
.sidebar-player:empty {{ display: none; }}
</style>
</head>
<body>

<div class="header">
  <span class="title">RA GENRE NETWORK</span>
  <span class="stat"><span>{total_mixes}</span> mixes</span>
  <span class="stat"><span>{total_genres}</span> genres</span>
  <span class="stat"><span>{total_edges}</span> connections</span>
</div>

<div class="container">
  <!-- Left: episode list -->
  <div class="sidebar">
    <div class="search-box">
      <input type="text" id="search" placeholder="Search episodes...">
    </div>
    <div class="episode-list" id="episodeList"></div>
    <div class="sidebar-player" id="sidebarPlayer"></div>
  </div>

  <!-- Center: tabs + views -->
  <div class="center-panel">
    <div class="center-tabs">
      <button class="center-tab active" data-view="graph">Network Graph</button>
      <button class="center-tab" data-view="labels">Labels</button>
    </div>
    <div class="graph-area" id="graphArea">
      <svg id="graph"></svg>
      <div class="tooltip" id="tooltip"></div>
    </div>
    <div class="label-filter-area" id="labelFilterArea" style="display:none">
      <div class="active-filters" id="activeFilters"></div>
      <div class="genre-filter-section" id="genreFilterSection"></div>
      <div class="label-masonry" id="labelMasonry"></div>
    </div>
  </div>

  <!-- Right: episode detail -->
  <div class="detail-panel collapsed" id="detailPanel">
    <div id="detailContent">
      <div class="detail-placeholder">Select an episode to see details</div>
    </div>
  </div>
</div>

<script>
// ── Embedded Data ───────────────────────────────────────────────────────────
const GRAPH_NODES = {nodes_json};
const GRAPH_EDGES = {edges_json};
const MIXES = {mixes_json};

// ── Lookups ─────────────────────────────────────────────────────────────────
const nodeMap = new Map(GRAPH_NODES.map(n => [n.id, n]));
const mixMap = new Map(MIXES.map(m => [m.id, m]));

// Adjacency: genre → set of neighbor genres
const adjacency = new Map();
GRAPH_EDGES.forEach(e => {{
  if (!adjacency.has(e.source)) adjacency.set(e.source, new Set());
  if (!adjacency.has(e.target)) adjacency.set(e.target, new Set());
  adjacency.get(e.source).add(e.target);
  adjacency.get(e.target).add(e.source);
}});

const maxWeight = Math.max(...GRAPH_EDGES.map(e => e.weight));
const maxCount = Math.max(...GRAPH_NODES.map(n => n.count));
function nodeRadius(count) {{ return 4 + 18 * Math.sqrt(count / maxCount); }}


// ── Episode List ────────────────────────────────────────────────────────────
const episodeList = document.getElementById('episodeList');
const searchInput = document.getElementById('search');
const detailPanel = document.getElementById('detailPanel');
const detailContent = document.getElementById('detailContent');

function renderEpisodeList(filter = '') {{
  const lower = filter.toLowerCase();
  episodeList.innerHTML = '';
  MIXES.forEach(m => {{
    if (filter && !m.artist.toLowerCase().includes(lower) &&
        !m.id.includes(filter)) return;
    const div = document.createElement('div');
    div.className = 'ep-item';
    div.dataset.id = m.id;
    div.innerHTML = `<span class="ep-num">RA.${{m.mix_number.padStart(3,'0')}}</span>${{m.artist}}`;
    div.addEventListener('click', () => selectEpisode(m));
    episodeList.appendChild(div);
  }});
}}

function renderEpisodeListByGenres(genreSet) {{
  episodeList.innerHTML = '';
  MIXES.forEach(m => {{
    if (!m.genres.some(g => genreSet.has(g))) return;
    const div = document.createElement('div');
    div.className = 'ep-item';
    div.dataset.id = m.id;
    div.innerHTML = `<span class="ep-num">RA.${{m.mix_number.padStart(3,'0')}}</span>${{m.artist}}`;
    div.addEventListener('click', () => selectEpisode(m));
    episodeList.appendChild(div);
  }});
}}

searchInput.addEventListener('input', e => renderEpisodeList(e.target.value));
renderEpisodeList();

// ── Label & Genre Filter Panel ─────────────────────────────────────────────
const CAT_ORDER = ['mood','energy','vibe','style','geography','setting','era'];
const CAT_NAMES = {{ mood:'Mood', energy:'Energy', vibe:'Vibe', style:'Style', geography:'Geography', setting:'Setting', era:'Era' }};
const DEFAULT_SHOW = 50;

// Precompute label counts per category
const LABEL_COUNTS = {{}};
CAT_ORDER.forEach(cat => {{ LABEL_COUNTS[cat] = {{}}; }});
MIXES.forEach(m => {{
  if (!m.label_categories) return;
  CAT_ORDER.forEach(cat => {{
    (m.label_categories[cat] || []).forEach(l => {{
      LABEL_COUNTS[cat][l] = (LABEL_COUNTS[cat][l] || 0) + 1;
    }});
  }});
}});

// Precompute genre counts
const GENRE_COUNTS = {{}};
MIXES.forEach(m => {{
  (m.genres || []).forEach(g => {{
    GENRE_COUNTS[g] = (GENRE_COUNTS[g] || 0) + 1;
  }});
}});
const SORTED_GENRES = Object.entries(GENRE_COUNTS).sort((a, b) => b[1] - a[1]);

let activeFilters = [];  // [{{category, label}}]  category='genre' for genres
let expandedCats = new Set();

function getFilteredMixes() {{
  if (activeFilters.length === 0) return MIXES;
  return MIXES.filter(m => {{
    const cats = m.label_categories || {{}};
    return activeFilters.every(f => {{
      if (f.category === 'genre') return (m.genres || []).includes(f.label);
      return (cats[f.category] || []).includes(f.label);
    }});
  }});
}}

function computeFilteredCounts(filteredMixes) {{
  const labelCounts = {{}};
  CAT_ORDER.forEach(cat => {{ labelCounts[cat] = {{}}; }});
  const genreCounts = {{}};
  filteredMixes.forEach(m => {{
    if (m.label_categories) {{
      CAT_ORDER.forEach(cat => {{
        (m.label_categories[cat] || []).forEach(l => {{
          labelCounts[cat][l] = (labelCounts[cat][l] || 0) + 1;
        }});
      }});
    }}
    (m.genres || []).forEach(g => {{
      genreCounts[g] = (genreCounts[g] || 0) + 1;
    }});
  }});
  return {{ labelCounts, genreCounts }};
}}

function renderGenreFilterSection() {{
  const container = document.getElementById('genreFilterSection');
  container.innerHTML = '';

  const filteredMixes = getFilteredMixes();
  const displayCounts = activeFilters.length > 0
    ? computeFilteredCounts(filteredMixes).genreCounts
    : GENRE_COUNTS;

  const entries = Object.entries(displayCounts).sort((a, b) => b[1] - a[1]);
  if (!entries.length) return;

  const expanded = expandedCats.has('genre');
  const visible = expanded ? entries : entries.slice(0, 30);
  const hasMore = entries.length > 30;

  const title = document.createElement('div');
  title.className = 'genre-filter-title';
  title.textContent = `Genres (${{entries.length}})`;
  container.appendChild(title);

  const items = document.createElement('div');
  items.className = 'genre-filter-items';

  visible.forEach(([genre, count]) => {{
    const chip = document.createElement('span');
    chip.className = 'genre-filter-chip';
    const node = nodeMap.get(genre);
    const color = node ? node.color : '#666';
    chip.style.background = color;
    chip.innerHTML = `${{genre}}<span class="chip-count">${{count}}</span>`;
    if (activeFilters.some(f => f.category === 'genre' && f.label === genre)) {{
      chip.classList.add('selected');
    }}
    chip.addEventListener('click', () => toggleLabelFilter('genre', genre));
    items.appendChild(chip);
  }});

  container.appendChild(items);

  if (hasMore) {{
    const btn = document.createElement('button');
    btn.className = 'show-more-btn';
    btn.textContent = expanded ? 'Show less' : `Show all ${{entries.length}}`;
    btn.addEventListener('click', () => {{
      if (expanded) expandedCats.delete('genre');
      else expandedCats.add('genre');
      renderFilterPanel();
    }});
    container.appendChild(btn);
  }}
}}

function renderLabelMasonry() {{
  const container = document.getElementById('labelMasonry');
  container.innerHTML = '';

  const filteredMixes = getFilteredMixes();
  const displayCounts = activeFilters.length > 0
    ? computeFilteredCounts(filteredMixes).labelCounts
    : LABEL_COUNTS;

  CAT_ORDER.forEach(cat => {{
    const entries = Object.entries(displayCounts[cat] || {{}})
      .sort((a, b) => b[1] - a[1]);
    if (!entries.length) return;

    const expanded = expandedCats.has(cat);
    const visible = expanded ? entries : entries.slice(0, DEFAULT_SHOW);
    const hasMore = entries.length > DEFAULT_SHOW;

    const section = document.createElement('div');
    section.className = 'label-cat-section';
    section.setAttribute('data-cat', cat);

    const title = document.createElement('div');
    title.className = 'label-cat-title';
    title.textContent = `${{CAT_NAMES[cat]}} (${{entries.length}})`;
    section.appendChild(title);

    const items = document.createElement('div');
    items.className = 'label-cat-items';

    visible.forEach(([label, count]) => {{
      const chip = document.createElement('span');
      chip.className = 'filter-label-chip label-chip';
      chip.setAttribute('data-cat', cat);
      chip.innerHTML = `${{label}}<span class="chip-count">${{count}}</span>`;
      if (activeFilters.some(f => f.category === cat && f.label === label)) {{
        chip.classList.add('selected');
      }}
      chip.addEventListener('click', () => toggleLabelFilter(cat, label));
      items.appendChild(chip);
    }});

    section.appendChild(items);

    if (hasMore) {{
      const btn = document.createElement('button');
      btn.className = 'show-more-btn';
      btn.textContent = expanded ? 'Show less' : `Show all ${{entries.length}}`;
      btn.addEventListener('click', () => {{
        if (expanded) expandedCats.delete(cat);
        else expandedCats.add(cat);
        renderFilterPanel();
      }});
      section.appendChild(btn);
    }}

    container.appendChild(section);
  }});
}}

function renderFilterPanel() {{
  renderGenreFilterSection();
  renderLabelMasonry();
}}

function renderActiveFilters() {{
  const container = document.getElementById('activeFilters');
  container.innerHTML = '';
  if (activeFilters.length === 0) return;

  activeFilters.forEach((f, idx) => {{
    const chip = document.createElement('span');
    if (f.category === 'genre') {{
      chip.className = 'active-filter-chip genre-chip';
      const node = nodeMap.get(f.label);
      chip.style.background = node ? node.color : '#666';
    }} else {{
      chip.className = 'active-filter-chip label-chip';
      chip.setAttribute('data-cat', f.category);
    }}
    chip.innerHTML = `${{f.label}} <span class="remove" data-idx="${{idx}}">&times;</span>`;
    chip.querySelector('.remove').addEventListener('click', (e) => {{
      e.stopPropagation();
      activeFilters.splice(idx, 1);
      onFiltersChanged();
    }});
    container.appendChild(chip);
  }});

  // Match count
  const count = document.createElement('span');
  count.className = 'filter-match-count';
  const matchCount = getFilteredMixes().length;
  count.textContent = `${{matchCount}} mix${{matchCount !== 1 ? 'es' : ''}}`;
  container.appendChild(count);

  // Clear all
  const clear = document.createElement('button');
  clear.className = 'clear-filters-btn';
  clear.textContent = 'Clear all';
  clear.addEventListener('click', clearAllFilters);
  container.appendChild(clear);
}}

function toggleLabelFilter(cat, label) {{
  const idx = activeFilters.findIndex(f => f.category === cat && f.label === label);
  if (idx >= 0) {{
    activeFilters.splice(idx, 1);
  }} else {{
    activeFilters.push({{ category: cat, label: label }});
  }}
  onFiltersChanged();
}}

function onFiltersChanged() {{
  renderActiveFilters();
  renderFilterPanel();
  applyLabelFilters();
}}

function applyLabelFilters() {{
  if (activeFilters.length === 0) {{
    // Collapse detail panel when no filters
    detailPanel.classList.add('collapsed');
    return;
  }}

  const filtered = getFilteredMixes();

  // Show filtered mixes in right detail panel (like genre detail)
  detailPanel.classList.remove('collapsed');

  const filterDesc = activeFilters.map(f => f.label).join(' + ');
  const epList = filtered.slice(0, 50).map(m =>
    `<div class="track-item" style="cursor:pointer" onclick="selectEpisode(mixMap.get('${{m.id}}'))">` +
    `<span class="track-num">${{m.mix_number}}</span>` +
    `<span class="track-artist">${{m.artist}}</span></div>`
  ).join('');

  detailContent.innerHTML = `
    <div style="position:relative">
      <button class="detail-close" onclick="clearAllFilters()">Close</button>
      <div class="detail-header">
        <div class="ep-title">Label Filter</div>
        <div class="ep-artist">${{filterDesc}}</div>
        <div class="detail-meta">
          <div class="meta-item"><span class="meta-val">${{filtered.length}} episodes</span></div>
        </div>
      </div>
    </div>
    <div class="tracklist-section">
      <div class="tracklist-header">Episodes (${{filtered.length}})</div>
      ${{epList}}
      ${{filtered.length > 50 ? '<div class="no-tracklist">...and ' + (filtered.length - 50) + ' more</div>' : ''}}
    </div>
  `;

  detailPanel.scrollTop = 0;
}}

function clearAllFilters() {{
  activeFilters = [];
  expandedCats.clear();
  onFiltersChanged();
}}

function showLabelMixes(cat, label) {{
  // Find all mixes with this label in this category
  const matches = MIXES.filter(m => {{
    const cats = m.label_categories || {{}};
    return (cats[cat] || []).includes(label);
  }});

  detailPanel.classList.remove('collapsed');

  const epList = matches.slice(0, 50).map(m =>
    `<div class="track-item" style="cursor:pointer" onclick="selectEpisode(mixMap.get('${{m.id}}'))">` +
    `<span class="track-num">${{m.mix_number}}</span>` +
    `<span class="track-artist">${{m.artist}}</span></div>`
  ).join('');

  detailContent.innerHTML = `
    <div style="position:relative">
      <button class="detail-close" onclick="clearSelection()">Close</button>
      <div class="detail-header">
        <div class="ep-title"><span class="label-chip" data-cat="${{cat}}">${{label}}</span></div>
        <div class="detail-meta">
          <div class="meta-item"><span class="meta-val">${{matches.length}} episodes</span></div>
        </div>
      </div>
    </div>
    <div class="tracklist-section">
      <div class="tracklist-header">Episodes (${{matches.length}})</div>
      ${{epList}}
      ${{matches.length > 50 ? '<div class="no-tracklist">...and ' + (matches.length - 50) + ' more</div>' : ''}}
    </div>
  `;

  detailPanel.scrollTop = 0;
}}

// Tab switching
document.querySelectorAll('.center-tab').forEach(tab => {{
  tab.addEventListener('click', () => {{
    document.querySelectorAll('.center-tab').forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
    const view = tab.dataset.view;
    document.getElementById('graphArea').style.display = view === 'graph' ? '' : 'none';
    document.getElementById('labelFilterArea').style.display = view === 'labels' ? '' : 'none';
    if (view === 'labels') renderFilterPanel();
    if (view === 'graph') setTimeout(resizeGraph, 100);
  }});
}});

// ── Selection State ─────────────────────────────────────────────────────────
let highlightedNodes = new Set();
let directGenres = new Set();
let highlightedEdges = new Set();
let activeFilter = 'all';
let selectedMixId = null;

function selectEpisode(mix) {{
  // Toggle: if already selected, clear
  if (selectedMixId === mix.id) {{
    clearSelection();
    return;
  }}
  selectedMixId = mix.id;

  // Active state in list
  episodeList.querySelectorAll('.ep-item').forEach(el => {{
    el.classList.toggle('active', el.dataset.id === mix.id);
  }});

  // Highlight direct genres + their neighbors
  directGenres = new Set(mix.genres);
  highlightedNodes = new Set(mix.genres);
  // Add neighbors of direct genres
  mix.genres.forEach(g => {{
    const neighbors = adjacency.get(g);
    if (neighbors) neighbors.forEach(n => highlightedNodes.add(n));
  }});

  highlightedEdges = new Set();
  GRAPH_EDGES.forEach((e, i) => {{
    if (highlightedNodes.has(e.source) && highlightedNodes.has(e.target)) {{
      highlightedEdges.add(i);
    }}
  }});

  // Build detail panel
  showEpisodeDetail(mix);
  updateVisuals();
}}

function showEpisodeDetail(mix) {{
  detailPanel.classList.remove('collapsed');

  const dur = mix.duration || '';
  const chips = mix.genres.map(g => {{
    const node = nodeMap.get(g);
    const color = node ? node.color : '#666';
    return `<span class="genre-chip" style="background:${{color}}" onclick="selectGenreNode('${{g}}')">${{g}}</span>`;
  }}).join('');

  // Keywords chips
  const kwHtml = mix.keywords ? mix.keywords.split(',').map(k => k.trim()).filter(Boolean)
    .map(k => `<span class="kw-chip">${{k}}</span>`).join('') : '';

  // Labels chips — use label_categories if available, else fall back to flat labels
  let labelsHtml = '';
  if (mix.label_categories && Object.keys(mix.label_categories).length > 0) {{
    const chips = [];
    // Render in category order, skip 'other'
    CAT_ORDER.forEach(cat => {{
      const items = mix.label_categories[cat];
      if (items && items.length) {{
        items.forEach(l => chips.push(`<span class="label-chip" data-cat="${{cat}}" style="cursor:pointer" onclick="showLabelMixes('${{cat}}','${{l.replace(/'/g, "\\\\'")}}')">${{l}}</span>`));
      }}
    }});
    labelsHtml = chips.join('');
  }} else if (mix.labels && mix.labels.length) {{
    labelsHtml = mix.labels.map(l => `<span class="label-chip">${{l}}</span>`).join('');
  }}

  // Links
  const links = [];
  if (mix.streamingUrl) links.push(`<a href="#" onclick="event.preventDefault(); playMix(mixMap.get('${{mix.id}}'))" class="detail-link">Listen</a>`);
  if (mix.url) links.push(`<a href="${{mix.url}}" target="_blank" rel="noopener noreferrer" class="detail-link">RA page</a>`);
  if (mix.artist_id) links.push(`<a href="https://ra.co/dj/${{mix.artist_id}}" target="_blank" rel="noopener noreferrer" class="detail-link">Artist</a>`);
  const linksHtml = links.length ? `<div class="detail-links">${{links.join('')}}</div>` : '';

  // Tracklist
  let tracklistHtml = '';
  if (mix.tracks && mix.tracks.length > 0) {{
    const tracks = mix.tracks.map((t, i) => {{
      const num = `<span class="track-num">${{i + 1}}</span>`;
      const artist = t.artist ? `<span class="track-artist">${{t.artist}}</span> ` : '';
      const title = t.title ? `<span class="track-title">${{artist ? '- ' : ''}}${{t.title}}</span>` : '';
      const label = t.label ? ` <span class="track-label">[${{t.label}}]</span>` : '';
      return `<div class="track-item">${{num}}${{artist}}${{title}}${{label}}</div>`;
    }}).join('');
    tracklistHtml = `
      <div class="tracklist-header">Tracklist (${{mix.tracks.length}})</div>
      ${{tracks}}`;
  }} else {{
    tracklistHtml = '<div class="no-tracklist">No tracklist available</div>';
  }}

  detailContent.innerHTML = `
    ${{mix.imageUrl ? `<div class="detail-cover"><img src="${{mix.imageUrl}}" alt="${{mix.artist}}"></div>` : ''}}
    <div style="position:relative">
      <button class="detail-close" onclick="clearSelection()">Close</button>
      <div class="detail-header">
        <div class="ep-title">RA.${{mix.mix_number.padStart(3,'0')}}</div>
        <div class="ep-artist">${{mix.artist}}</div>
        <div class="detail-meta">
          ${{mix.date ? `<div class="meta-item"><span class="meta-val">${{mix.date}}</span></div>` : ''}}
          ${{dur ? `<div class="meta-item"><span class="meta-val">${{dur}}</span></div>` : ''}}
          <div class="meta-item"><span class="meta-val">${{mix.tracks ? mix.tracks.length : 0}} tracks</span></div>
        </div>
        ${{linksHtml}}
        <div class="genre-chips">${{chips}}</div>
        ${{kwHtml ? `<div class="kw-chips">${{kwHtml}}</div>` : ''}}
        ${{labelsHtml ? `<div class="label-chips">${{labelsHtml}}</div>` : ''}}
      </div>
    </div>
    ${{mix.blurb ? `<div class="detail-blurb">${{mix.blurb}}</div>` : ''}}
    ${{mix.article ? `<div class="detail-section-header">About</div><div class="detail-article">${{mix.article}}</div>` : ''}}
    ${{mix.qa ? `<div class="detail-section-header">Q&A</div><div class="detail-article detail-qa">${{mix.qa}}</div>` : ''}}
    ${{tracklistHtml}}
  `;

  // Scroll to top + resize graph after panel opens
  detailPanel.scrollTop = 0;
  setTimeout(resizeGraph, 250);
}}

function showGenreDetail(nodeId) {{
  detailPanel.classList.remove('collapsed');

  const n = nodeMap.get(nodeId);
  const count = n ? (n.count || 0) : 0;
  const family = n ? n.family : '';
  const color = n ? n.color : '#666';

  // Find episodes with this genre
  const eps = MIXES.filter(m => m.genres.includes(nodeId));

  const epList = eps.slice(0, 50).map(m =>
    `<div class="track-item" style="cursor:pointer" onclick="selectEpisode(mixMap.get('${{m.id}}'))">` +
    `<span class="track-num">${{m.mix_number}}</span>` +
    `<span class="track-artist">${{m.artist}}</span></div>`
  ).join('');

  detailContent.innerHTML = `
    <div style="position:relative">
      <button class="detail-close" onclick="clearSelection()">Close</button>
      <div class="detail-header">
        <div class="ep-title" style="color:${{color}}">${{nodeId}}</div>
        <div class="ep-artist">${{family}}</div>
        <div class="detail-meta">
          <div class="meta-item"><span class="meta-val">${{count}} episodes</span></div>
        </div>
      </div>
    </div>
    <div class="tracklist-section">
      <div class="tracklist-header">Episodes (${{eps.length}})</div>
      ${{epList}}
      ${{eps.length > 50 ? '<div class="no-tracklist">...and ' + (eps.length - 50) + ' more</div>' : ''}}
    </div>
  `;

  setTimeout(resizeGraph, 250);
}}

function selectGenreNode(nodeId) {{
  directGenres = new Set([nodeId]);
  highlightedNodes = new Set([nodeId]);
  const neighbors = adjacency.get(nodeId);
  if (neighbors) neighbors.forEach(n => highlightedNodes.add(n));

  highlightedEdges = new Set();
  GRAPH_EDGES.forEach((e, i) => {{
    if (highlightedNodes.has(e.source) && highlightedNodes.has(e.target)) {{
      highlightedEdges.add(i);
    }}
  }});

  selectedMixId = null;

  // Show genre detail in right panel (don't filter left sidebar)

  showGenreDetail(nodeId);
  updateVisuals();
}}

function clearSelection() {{
  selectedMixId = null;
  highlightedNodes = new Set();
  directGenres = new Set();
  highlightedEdges = new Set();
  renderEpisodeList(searchInput.value);
  detailPanel.classList.add('collapsed');
  detailContent.innerHTML = '<div class="detail-placeholder">Select an episode to see details</div>';
  setTimeout(resizeGraph, 250);
  updateVisuals();
}}

// ── D3 Graph (co-occurrence) ─────────────────────────────────────────────
const svg = d3.select('#graph');
const graphArea = document.getElementById('graphArea');
let width = graphArea.clientWidth;
let height = graphArea.clientHeight;

svg.attr('viewBox', [0, 0, width, height]);

// Glow filter
const defs = svg.append('defs');
const glowFilter = defs.append('filter').attr('id', 'glow');
glowFilter.append('feGaussianBlur').attr('stdDeviation', '3').attr('result', 'blur');
glowFilter.append('feComposite').attr('in', 'SourceGraphic').attr('in2', 'blur').attr('operator', 'over');

const gRoot = svg.append('g');

const zoom = d3.zoom()
  .scaleExtent([0.2, 5])
  .on('zoom', (event) => gRoot.attr('transform', event.transform));
svg.call(zoom);

function resizeGraph() {{
  width = graphArea.clientWidth;
  height = graphArea.clientHeight;
  svg.attr('viewBox', [0, 0, width, height]);
}}

// Prepare simulation data
const simNodes = GRAPH_NODES.map(n => ({{ ...n }}));
const simEdges = GRAPH_EDGES.map((e, i) => ({{ ...e, index: i }}));
const cx = width / 2, cy = height / 2;

// Family gravity centers — arranged in a ring
const families = [...new Set(GRAPH_NODES.map(n => n.family))];
const familyAngle = {{}};
const familyCenter = {{}};
const ringR = Math.min(width, height) * 0.25;
families.forEach((f, i) => {{
  const angle = (2 * Math.PI * i / families.length) - Math.PI / 2;
  familyCenter[f] = {{ x: cx + ringR * Math.cos(angle), y: cy + ringR * Math.sin(angle) }};
}});

// Simulation — co-occurrence links + soft family gravity
const simulation = d3.forceSimulation(simNodes)
  .force('link', d3.forceLink(simEdges)
    .id(d => d.id)
    .distance(d => 30 + 120 * (1 - d.weight / maxWeight))
    .strength(d => 0.1 + 0.6 * (d.weight / maxWeight))
  )
  .force('charge', d3.forceManyBody()
    .strength(d => -30 - 100 * Math.sqrt(d.count / maxCount))
  )
  .force('center', d3.forceCenter(cx, cy).strength(0.03))
  .force('familyX', d3.forceX(d => {{
    const fc = familyCenter[d.family];
    return fc ? fc.x : cx;
  }}).strength(0.08))
  .force('familyY', d3.forceY(d => {{
    const fc = familyCenter[d.family];
    return fc ? fc.y : cy;
  }}).strength(0.08))
  .force('collide', d3.forceCollide().radius(d => nodeRadius(d.count) + 4))
  .alphaDecay(0.015);

// Draw edges
const linkG = gRoot.append('g');
const links = linkG.selectAll('line')
  .data(simEdges)
  .join('line')
  .attr('stroke', '#fff')
  .attr('stroke-width', d => 0.5 + 3 * (d.weight / maxWeight))
  .attr('stroke-opacity', d => 0.06 + 0.25 * (d.weight / maxWeight));

// Draw nodes
const nodeG = gRoot.append('g');
const nodeGroups = nodeG.selectAll('g')
  .data(simNodes)
  .join('g')
  .attr('cursor', 'pointer')
  .call(d3.drag()
    .on('start', (event, d) => {{ if (!event.active) simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; }})
    .on('drag', (event, d) => {{ d.fx = event.x; d.fy = event.y; }})
    .on('end', (event, d) => {{ if (!event.active) simulation.alphaTarget(0); d.fx = null; d.fy = null; }})
  );

// Glow circle (behind main node)
nodeGroups.append('circle').attr('class', 'node-glow')
  .attr('r', d => nodeRadius(d.count) + 6)
  .attr('fill', d => d.color || '#666')
  .attr('opacity', 0.15)
  .attr('filter', 'url(#glow)');

// Pulse ring
nodeGroups.append('circle').attr('class', 'pulse-ring')
  .attr('r', d => nodeRadius(d.count) + 4)
  .attr('fill', 'none').attr('stroke', '#fff')
  .attr('stroke-opacity', 0).attr('stroke-width', 0);

// Main circle
nodeGroups.append('circle').attr('class', 'node-circle')
  .attr('r', d => nodeRadius(d.count))
  .attr('fill', d => d.color || '#666')
  .attr('opacity', 0.9);

// Labels
nodeGroups.append('text').attr('class', 'node-label')
  .attr('dy', d => nodeRadius(d.count) + 12)
  .attr('font-size', d => d.count > 50 ? 11 : d.count > 10 ? 9 : 8)
  .attr('font-weight', d => d.count > 50 ? 700 : 400)
  .attr('opacity', d => d.count >= 10 ? 1 : 0)
  .text(d => d.id);

// Tooltip
const tooltip = document.getElementById('tooltip');
nodeGroups.on('mouseover', function(event, d) {{
  d3.select(this).select('.node-label').attr('opacity', 1);
  d3.select(this).select('.node-glow').attr('opacity', 0.4);
  // Build tooltip with top connections
  const neighbors = adjacency.get(d.id);
  let conns = '';
  if (neighbors) {{
    const top = GRAPH_EDGES
      .filter(e => e.source.id === d.id || e.target.id === d.id)
      .sort((a, b) => b.weight - a.weight)
      .slice(0, 3)
      .map(e => {{
        const other = e.source.id === d.id ? e.target.id : e.source.id;
        return `${{other}} (${{e.weight}})`;
      }});
    if (top.length) conns = ' | ' + top.join(', ');
  }}
  tooltip.style.display = 'block';
  tooltip.textContent = `${{d.id}} — ${{d.count}} mixes${{conns}}`;
}})
.on('mousemove', function(event) {{
  tooltip.style.left = (event.clientX + 12) + 'px';
  tooltip.style.top = (event.clientY - 10) + 'px';
}})
.on('mouseout', function(event, d) {{
  if (!highlightedNodes.has(d.id) && d.count < 10) {{
    d3.select(this).select('.node-label').attr('opacity', 0);
  }}
  d3.select(this).select('.node-glow').attr('opacity', 0.15);
  tooltip.style.display = 'none';
}})
.on('click', function(event, d) {{
  event.stopPropagation();
  selectGenreNode(d.id);
}});

svg.on('click', () => clearSelection());

simulation.on('tick', () => {{
  links.attr('x1', d => d.source.x).attr('y1', d => d.source.y)
    .attr('x2', d => d.target.x).attr('y2', d => d.target.y);
  nodeGroups.attr('transform', d => `translate(${{d.x}},${{d.y}})`);
}});

// ── Visual Update ───────────────────────────────────────────────────────────
function updateVisuals() {{
  const has = highlightedNodes.size > 0;

  nodeGroups.each(function(d) {{
    const el = d3.select(this);
    const isDirect = directGenres.has(d.id);
    const isNeighbor = highlightedNodes.has(d.id);

    const nodeOpacity = !has ? 0.9
      : isDirect ? 1
      : isNeighbor ? 0.4
      : 0.06;
    el.select('.node-circle').transition().duration(300).attr('opacity', nodeOpacity);
    el.select('.node-glow').transition().duration(300)
      .attr('opacity', isDirect && has ? 0.5 : has ? 0.03 : 0.15);

    el.select('.pulse-ring')
      .classed('pulse', isDirect && has)
      .attr('stroke-opacity', isDirect && has ? 0.8 : 0);

    const labelOpacity = !has ? (d.count >= 10 ? 1 : 0)
      : isDirect ? 1
      : isNeighbor ? 0.4
      : 0;
    el.select('.node-label').transition().duration(300).attr('opacity', labelOpacity);
  }});

  links.transition().duration(300)
    .attr('stroke-opacity', (d, i) => {{
      if (!has) return 0.06 + 0.25 * (d.weight / maxWeight);
      return highlightedEdges.has(i) ? 0.15 + 0.5 * (d.weight / maxWeight) : 0.02;
    }});
}}

// ── Player (in detail panel) ─────────────────────────────────────────────
function getEmbedInfo(streamingUrl) {{
  if (!streamingUrl) return null;
  if (streamingUrl.includes('soundcloud.com')) {{
    const encoded = encodeURIComponent(streamingUrl);
    return {{
      type: 'sc',
      url: `https://w.soundcloud.com/player/?url=${{encoded}}&color=%23e63946&auto_play=true&hide_related=true&show_comments=false&show_user=false&show_reposts=false&show_teaser=false&visual=false`
    }};
  }}
  if (streamingUrl.includes('mixcloud.com')) {{
    const path = new URL(streamingUrl).pathname;
    return {{
      type: 'mc',
      url: `https://www.mixcloud.com/widget/iframe/?feed=${{encodeURIComponent(path)}}&autoplay=1&light=0`
    }};
  }}
  return null;
}}

function playMix(mix) {{
  const info = getEmbedInfo(mix.streamingUrl);
  const el = document.getElementById('sidebarPlayer');
  if (!info || !el) {{
    if (mix.streamingUrl) window.open(mix.streamingUrl, '_blank');
    return;
  }}
  el.className = `sidebar-player ${{info.type}}`;
  el.innerHTML = `<div class="player-info"><span class="player-ep">RA.${{mix.mix_number.padStart(3,'0')}}</span> <span class="player-artist">${{mix.artist}}</span></div>` +
    `<iframe src="${{info.url}}" allow="autoplay"></iframe>`;
}}

// ── Keyboard navigation ──────────────────────────────────────────────────
document.addEventListener('keydown', (e) => {{
  if (e.target.tagName === 'INPUT') return; // don't hijack search
  if (e.key !== 'ArrowUp' && e.key !== 'ArrowDown') return;
  if (!selectedMixId) return;

  e.preventDefault();
  const items = Array.from(episodeList.querySelectorAll('.ep-item'));
  if (!items.length) return;

  const currentIdx = items.findIndex(el => el.dataset.id === selectedMixId);
  let nextIdx;
  if (e.key === 'ArrowDown') {{
    nextIdx = currentIdx < items.length - 1 ? currentIdx + 1 : currentIdx;
  }} else {{
    nextIdx = currentIdx > 0 ? currentIdx - 1 : currentIdx;
  }}

  if (nextIdx !== currentIdx) {{
    const nextId = items[nextIdx].dataset.id;
    const nextMix = mixMap.get(nextId);
    if (nextMix) {{
      selectEpisode(nextMix);
      items[nextIdx].scrollIntoView({{ block: 'nearest' }});
    }}
  }}
}});

// Initial zoom
setTimeout(() => {{
  svg.call(zoom.transform, d3.zoomIdentity.translate(width * 0.05, height * 0.05).scale(0.9));
}}, 2000);
</script>
</body>
</html>"""

    return html


def main():
    print("Loading mixes from Excel...")
    mixes = load_mixes()
    print(f"  {len(mixes)} episodes loaded")

    print("Loading genre co-occurrence graph...")
    with open(DATA_DIR / "genre_cooccurrence.json") as f:
        graph = json.load(f)
    print(f"  {len(graph['nodes'])} nodes, {len(graph['edges'])} edges")

    print("Building HTML...")
    html = build_html(mixes, graph)

    out_path = ROOT / "ra_genre_network.html"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  → {out_path} ({len(html)//1024} KB)")


if __name__ == "__main__":
    main()
