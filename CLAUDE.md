# RA Genre Network

## Prehľad
Interaktívna D3.js vizualizácia žánrového grafu RA podcast mixov. Jeden self-contained HTML súbor (`ra_genre_network.html`) s embedovanými dátami.

## Architektúra

### Hlavné súbory
- `ra_genre_network.html` — výstupný HTML (~6.8MB), generovaný build skriptom
- `index.html` — alias pre GitHub Pages (`ra_genre_network.html` skopírovaný pre GitHub Pages publikáciu)
- `scripts/build_network_html.py` — hlavný build skript, generuje HTML z dát
- `data/genre_musicology.json` — **muzikologický knowledge graph** (136 nodes, 192 edges) — vzťahy medzi žánrami (evolved_from, influenced_by, shares_elements, regional_variant, subgenre_of) so strength 1-5
- `data/genre_hierarchy.json` — hierarchia žánrov (L1 families → L2 → L3), 8 rodín
- `data/genre_cooccurrence.json` — staré co-occurrence dáta (NEPOUŽÍVA SA v grafe, nahradené musicology)

### Dátový pipeline (pridanie nového mixu)
1. `python3 scripts/fetch_missing_httpx.py` — fetch raw JSON
2. `python3 run_pilot.py --ids {podcast_id}` — parse
3. Claude Code — LLM extrakcia žánrov + labels (bez API kľúča)
4. `python3 scripts/normalize_llm_cache.py` — normalize
5. `python3 scripts/normalize_labels.py` — label kategorizácia (7 kategórií)
6. `python3 normalize/genre_normalizer.py` — genre edges normalize
7. `python3 export/excel_exporter.py` — Excel export
8. `python3 scripts/build_network_html.py` — **finálny build**

### Genre family farby (Rain-Soaked Reflections paleta)
| Family | Color |
|---|---|
| Techno | `#d41d4a` |
| House | `#f59e42` |
| Groove | `#fceba5` |
| Bass Culture | `#06b6d4` |
| Experimental | `#c77dff` |
| Industrial | `#94a3b8` |
| Global Roots | `#22c55e` |
| Hip Hop | `#fb7eb8` |

Farby sú definované v 3 miestach: `build_genre_hierarchy.py`, `build_cooccurrence_graph.py`, `genre_musicology.json`

### UI dizajn — Tokyo Night / Cyberpunk
- **Téma**: Tmavý navy základ (`#080a18`), neon akcenty (pink, cyan, amber, violet, green)
- **Fonty**: Syne (display), Lexend (body), JetBrains Mono (data) — NEMENIŤ
- **Záložky**: "Genre Map" (D3 network graf) + "Explore" (label bubble chart)
- **Glassmorphism**: blur panely, film grain overlay
- **Network graf features**:
  - Muzikologické vzťahy (nie co-occurrence)
  - Hrúbka čiar = sila vzťahu (strength 1-5)
  - Farebné linky — blend farieb oboch prepojených rodín
  - Sémantický zoom (labels sa objavujú/schovávajú podľa zoom levelu)
  - Family district labels — veľké polopriehľadné názvy rodín priamo v SVG, posunuté za clustre k okrajom
  - Node glow intenzita viazaná na count
  - Idle pulse na top 5 nodoch
  - Klikací názov mixu nad prehrávačom → otvorí detail
  - **Search box** (bottom-right corner) — autocomplete dropdown, keyboard nav (↑↓/Enter/Esc), zoom-to-node s highlight neighbors
- **Explore tab features**:
  - Desktop: Label categories v 3 columns: **Col1**: Mood, Setting, Era | **Col2**: Energy, Geography | **Col3**: Vibe, Style
  - Mobile: Single-column layout s poradím: Mood → Setting → Energy → Geography → Vibe → Era (bez Style)
  - `display: flex` s rovnaký stĺpcami (flex: 1) — presný kontrola poradia
  - Visual hierarchy: Primary group (Mood, Energy, Vibe) so silnejším neon glow (box-shadow 0.18 alpha, 3px top bar); metadata group (Era) muted (75% opacity, hover→100%)
  - RA Tags (keywords) — **normalized**: case to title case, HTML entities decoded, deduplicated — zobrazujú sa na konci
  - Detail panel chips order: genres → LLM labels → RA Tags
  - Genre chip tooltips — hover → glassmorphism tooltip s popisom žánru + family label

### Mobile Optimizations (2026-04-04/05/06)
- **Bottom tab bar**: 3-tab navigation (Mixes | Genre Map | Explore) — mobile-only, hidden on desktop
- **Mixes tab**: Kompaktný list view (RA.1032 · Artist · Date with year), in-tab detail view s Back tlačidlom, search box (hides during detail view)
  - **Search box** (top of list) — real-time filter by artist name or mix number (e.g., "TC80", "635", "RA.635")
  - **Date display**: Shows year (e.g., "29 Mar 2018") — formatted via `formatMixDate()`
  - **Listen button**: Uses `playMix()` which converts `api.soundcloud.com/tracks/ID` → proper embed URL via `getEmbedInfo()` (fixes old mixes like RA.635)
- **Detail panel**: Bottom sheet pattern — default 50vh, expandable na 90vh on swipe
- **Touch targets**: Minimum 44px (iOS HIG) — invisible hit circles on nodes (`node-hit`), 8px 14px padding na chips
- **D3 graph mobile**: **Interactive** (opacity 1.0, pointer-events: auto), pinch-zoom native (D3), semantic zoom adjusted for mobile (lower thresholds)
  - Node drag disabled on touch (`.filter(event => event.pointerType === 'mouse')`) — prioritizuje pan/zoom gestures
  - 1 prst = pan graf, 2 prsty = pinch-zoom
- **Graph search**: Repositioned to top (full-width), autocomplete keyboard nav
- **Click vs pan**: Distinguish between tap and pan gesture (>5px = drag, don't trigger clearSelection)
- **Tooltips**: Hidden on mobile (`display: none !important`)
- **Clickable elements**: Genre chips, label chips have onclick handlers in all views
- **Interactive states**: `:hover` → `:active` + `:focus-visible` na všetkých tapovateľných elementoch
- **Safe area support**: `env(safe-area-inset-bottom)` na tab bar; header uses `env(safe-area-inset-top)`
- **Fixed (5/4/2026)**: Mixes tab detail panel now displays correctly when mix is clicked (was hidden due to missing `display` style assignment). Pan/zoom on Genre Map now works smoothly on mobile (node drag disabled on touch).
- **Fixed (6/4/2026)**: Years added to all date displays. Listen button fixed for old SoundCloud API URLs (RA.635 now plays correctly). Mixes search box added with real-time filtering. Search box hides when detail view opens.
- **Fixed (6/4/2026)** — **Build & sorting fixes**: 
  - Build script now sorts mixes by **date DESC** (newest first), not podcast_id DESC. This is critical for proper chronological ordering.
  - Mobile Mixes tab now correctly uses `detailPanel` (bottom sheet) via `selectEpisode()`, while desktop uses `mixesDetail()`. Viewport detection: `window.innerWidth < 768`.
  - When adding new mixes, ensure raw JSON (`data/raw/episode_NNNN.json`) and `episodes.jsonl` have **correct dates** — mismatched dates cause mixes to appear in wrong positions.
- **Known issue — Mixes detail scroll**: Detail view stays scrolled to previous mix's position instead of resetting to top (mobile only). Root cause unknown after extensive debugging (scrollTop, requestAnimationFrame, element recreation, CSS overflow changes all failed). May be browser behavior or CSS property interaction. Workaround: user can manually scroll to top.

## Publikácia

**GitHub Pages**: https://radozoo.github.io/ra-mixes/
- Repo musí byť **public** (GitHub Pages na private repo vyžaduje GitHub Pro)
- `index.html` je automatically servírovaný ako homepage (GitHub Pages serves `index.html`, NOT `ra_genre_network.html`)
- **CRITICAL**: Po každej úprave `ra_genre_network.html` musíš synchronizovať `index.html`:
  ```bash
  cp ra_genre_network.html index.html
  git add index.html && git commit -m "sync: Update index.html ..."
  git push origin main
  ```
- Po `git push origin main` sa stránka updatne za ~30 sekúnd

## Skills

- **frontend-design**: See [skills/frontend-design-skill.md](skills/frontend-design-skill.md) — use when building or modifying web UI components.
