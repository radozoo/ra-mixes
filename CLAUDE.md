# RA Genre Network

## Prehľad
Interaktívna D3.js vizualizácia žánrového grafu RA podcast mixov. Jeden self-contained HTML súbor (`ra_genre_network.html`) s embedovanými dátami.

## Architektúra

### Hlavné súbory
- `ra_genre_network.html` — výstupný HTML (~6.8MB), generovaný build skriptom
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

## Skills

- **frontend-design**: See [skills/frontend-design-skill.md](skills/frontend-design-skill.md) — use when building or modifying web UI components.
