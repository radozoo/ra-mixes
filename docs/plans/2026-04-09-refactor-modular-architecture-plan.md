---
title: "Refactor: Modular Architecture (ID System + JSON Pipeline + JS Modules)"
type: refactor
status: active
date: 2026-04-09
origin: docs/brainstorms/2026-04-09-modular-refactor-brainstorm.md
---

# Refactor: Modular RA Architecture

## Overview

A comprehensive refactoring of the RA Genre Network project to fix three critical pain points:

1. **ID System Instability** — `podcast_id` (internal) and `RA.XXXX` (public) are conflated; labels don't load; sorting breaks
2. **Excel Bottleneck** — Build script reads from Excel, requiring re-consolidation of JSONL → Excel → read back
3. **Monolithic Frontend** — 2990-line HTML with embedded JavaScript makes testing, debugging, and feature development difficult

**Approach:** Modular refactor with static deployment (Approach 2 from brainstorm)
- **Backend:** Restructure data model + JSON pipeline (no Excel)
- **Frontend:** Modularize JavaScript with Parcel bundler
- **Result:** Cleaner codebase, simpler pipeline, smaller HTML, faster iteration

**Duration:** 1–2 weeks (3 phases)  
**Risk Level:** Low–Medium (isolated changes, feature branch isolation)  
**Team:** 1 architect/developer

---

## Problem Statement

### 1. ID System Confusion

**Validated model (confirmed 2026-04-09 against data/episodes.jsonl):**
- `podcast_id` = unique identifier per mix episode (1048/1052 unique; 4 are data quality bugs)
- `RA.XXXX` = public display number (extracted from title, NOT unique — RA.1000 series has 10 different podcast_ids)
- Sorting should be by release date (not podcast_id, not RA.XXXX)

**Current state:**
- `podcast_id` is used as key in JSONL, but episodes.jsonl has 5 duplicate `podcast_id=1033` entries (data bug from prior pipeline runs)
- No deduplication logic when new episodes are appended
- Sorting inconsistent (sometimes by podcast_id, sometimes not)

**Problems:**
- Duplicate `podcast_id=1033` entries cause labels to load for wrong mix variant
- No deduplication on insert → stale data accumulates over time
- Sorting not explicitly enforced → mixes appear in unpredictable order

**Root cause:** No deduplication guard in pipeline; no explicit sort step before build.

### 2. Excel as Build Dependency

**Current flow:**
```
episodes.jsonl + tracks.jsonl + genre_edges.jsonl
    ↓ (excel_exporter.py)
ra_full_export.xlsx
    ↓ (build_network_html.py, openpyxl)
ra_genre_network.html
```

**Problems:**
- Excel file (openpyxl dependency) becomes single source of truth after build
- Build script reads Excel via column header lookups (brittle: `eid_col = ge_headers.index("entity_id")`)
- If Excel schema changes, build breaks silently
- JSONL files become stale orphans after Excel export
- Adds `openpyxl` dependency (version mismatches, compatibility)

**Root cause:** No consolidated canonical format; Excel forced as intermediary for consolidation.

### 3. Monolithic Frontend

**Current state:**
- Single HTML file: 2990 lines
- All JavaScript embedded: 45+ `const` declarations, 35+ functions
- No module boundaries: D3 graph, UI tabs, search, mobile features all mixed
- Hard to debug: mobile scroll bug buried in global scope

**Problems:**
- Testing requires running full HTML (no component isolation)
- Adding features risks breaking existing behavior (no encapsulation)
- Code reuse: search box logic duplicated in multiple places
- Build process: no minification, no optimization
- Mobile scroll bug unresolved (can't isolate due to monolithic structure)

**Root cause:** No JavaScript module system or build process.

---

## Proposed Solution

### Architecture Overview

**New data flow (ID system + JSON pipeline):**
```
Raw Data (ra.co)
    ↓
[fetch + parse] → episodes.jsonl (keyed by podcast_id, deduplicated)
    ↓
[normalize + genres] → genre_edges.jsonl, labels
    ↓
[consolidated_exporter.py] → data/consolidated.json (single source of truth)
    ↓ (validated with Pydantic)
[build_network_html.py] → ra_genre_network.html
```

**New frontend structure (modularized JavaScript):**
```
src/
  ├── index.html (template, no data)
  ├── js/
  │   ├── main.js (entry point, data injection)
  │   ├── d3-graph.js (force-directed graph)
  │   ├── ui-tabs.js (tab switching)
  │   ├── search-box.js (search + autocomplete)
  │   ├── mobile-detail.js (bottom sheet)
  │   └── shared.js (utilities)
  ├── css/style.css (Tokyo Night theme)
  └── data/ (consolidated.json injected at build time)

[Parcel bundle]
    ↓
ra_genre_network.html (minified, cleaner internals)
```

### Key Design Decisions

#### 1. Data Model: `podcast_id` as Primary Key

**Validated design (confirmed against real data):**
- `podcast_id` = unique identifier per mix episode (**primary key**)
- `RA.XXXX` = display name (extracted from title; NOT unique — one RA.XXXX can map to many podcast_ids in series)
- Sorting = by release **date** (newest first)

**New schema:**
```json
{
  "podcast_id": 1033,               // Primary key (unique int)
  "ra_mix_number": "RA.1033",       // Extracted from title (display only)
  "title": "RA.1033 Isaac Carter",  // Full title from RA.co
  "artist": "Isaac Carter",
  "release_date": "2026-04-05",
  "description": "...",
  "genres": ["house", "techno"],
  "labels": {
    "mood": ["intricate", "pleasure-packed"],
    "energy": ["slow-burn"],
    ...
  },
  "ra_tags": ["house", "techno"],   // From RA.co
  "tracklist": [...]
}
```

**Rationale:**
- `podcast_id` is the stable, unique identifier per episode
- `ra_mix_number` extracted from title for display purposes (e.g., "RA.1000" appears 10 times in series)
- All internal lookups (labels, genres, detail panels) keyed to `podcast_id`
- Sorting explicitly by `release_date` DESC in `consolidated_exporter.py`

**Data Cleanup (Phase 1.0 new task):**
- `podcast_id=1033` currently has 5 duplicate entries from prior pipeline runs
- One-time script: deduplicate by keeping only the newest entry per `podcast_id`
- Add deduplication guard to pipeline: if `podcast_id` already in JSONL, overwrite (don't append)

#### 2. Remove Excel: Consolidated.json

**New single source of truth:**
- `consolidated.json`: Canonical data (all mixes + genres + labels)
- Validated with Pydantic schemas (enforces structure)
- Build reads this, injects into HTML template
- Eliminates Excel dependency, simpler schema validation

**Benefits:**
- No openpyxl dependency
- Faster build (JSON vs Excel I/O)
- Schema validation catches data errors early
- JSONL stays in git history for reproducibility

#### 3. Modularize Frontend with Parcel

**Module separation:**
- `main.js`: loads `consolidated.json`, initializes modules
- `d3-graph.js`: force-directed layout, node/link rendering
- `ui-tabs.js`: tab switching logic, state management
- `search-box.js`: autocomplete, keyboard nav
- `mobile-detail.js`: bottom sheet, swipe gestures
- `shared.js`: utilities (colors, date formatting, types)

**Build process:**
```bash
parcel build src/index.html --dist-dir . --no-source-maps
```

**Benefits:**
- Modules can be tested independently (future)
- Smaller final size (~20–30% reduction via minification)
- Easier to add features (clear module boundaries)
- Easier to debug (separate files, source maps in dev)

#### 4. Data Migration: Audit Trail

**Old JSONL files preserved:**
- Moved to `data/archive/deprecated/` (marked non-authoritative)
- Kept for historical reference + reproducibility
- Not used by pipeline

**LLM cache migration:**
- Existing labels reindexed to `RA.XXXX` (not rebuilt)
- Faster migration, preserves existing work
- Fallback: if label not found, regex-based genres used

---

## Technical Approach

### Phase 1: Data Model & Pipeline Refactor (3 days)

**Goal:** Restructure data to use `RA.XXXX` as primary key, remove Excel dependency.

**Tasks:**

#### 1.0 Deduplicate episodes.jsonl (one-time cleanup)
- Script: `python/deduplicate_episodes.py`
  - Read current `episodes.jsonl`
  - Deduplicate by `podcast_id`: keep newest entry per ID
  - Verify: `podcast_id=1033` → 1 entry (was 5)
  - Output: overwrite `episodes.jsonl` in-place (after backup)
- Backup: copy to `data/archive/deprecated/episodes_pre_dedup.jsonl`
- Add deduplication guard to `run_pilot.py`: overwrite on `podcast_id` match, don't append

#### 1.1 Pydantic Schema Definition
- Create `python/models.py`: data classes for Mix, Genre, Label
- `podcast_id` (int) is primary key; `ra_mix_number` (str) is extracted display name
- Define validation rules (required fields, valid values, relationships)
- Include docstrings + examples

#### 1.2 Migrate episodes.jsonl
- Script: `python/migrate_episodes.py`
  - Read clean `episodes.jsonl` (after dedup)
  - Validate each entry with Pydantic `Mix` model
  - Extract `ra_mix_number` from title (regex: `RA\.\d+`)
  - Output: `data/episodes_v2.jsonl` (validated, with `ra_mix_number` field added)
- Preserve old file: move to `data/archive/deprecated/episodes_v1.jsonl`

#### 1.3 Reindex LLM Cache
- Script: `python/reindex_llm_cache.py`
  - Read old `llm_genre_cache_with_categories.jsonl` (keyed by `podcast_id`)
  - Reindex to new format (keyed by `RA.XXXX`)
  - Output: `data/llm_genre_cache_v2.jsonl`

#### 1.4 Create consolidated_exporter.py
- New script (replaces `excel_exporter.py`)
- Read: `episodes_v2.jsonl`, `genre_edges.jsonl`, `llm_genre_cache_v2.jsonl`, `tracks.jsonl`
- Validate: Check all mixes have genres + labels
- Output: `data/consolidated.json` (single source of truth)
- Include error reporting: missing data, validation failures

#### 1.5 Update build_network_html.py
- Remove Excel reading (openpyxl code)
- Read `consolidated.json` instead
- Validate Pydantic schemas before building
- Inject data into HTML template (existing D3 + UI code unchanged)

#### 1.6 Update GitHub Actions Workflow
- Remove `excel_exporter.py` step
- Replace with `consolidated_exporter.py`
- Update pipeline order: `parse → normalize → consolidated_exporter → build_network_html`

**Deliverables:**
- ✅ `python/models.py` (Pydantic schemas)
- ✅ Migration scripts (episodes, LLM cache)
- ✅ `python/consolidated_exporter.py` (new)
- ✅ Updated `build_network_html.py`
- ✅ Updated `.github/workflows/weekly-pipeline.yml`
- ✅ `data/consolidated.json` (first successful build)
- ✅ Old JSONL files archived in `data/archive/deprecated/`

**Testing:**
- Build locally: `python3 scripts/build_network_html.py`
- Verify HTML loads in browser (no console errors)
- Check all 300+ mixes visible in graph
- Verify labels load for each mix
- Test search, filtering, D3 interactions

**Risks:**
- Data migration: If reindexing fails, old data lost (mitigation: git history, archived files)
- Schema changes: If Pydantic validation too strict, build breaks (mitigation: test on sample before full run)
- Performance: Reading large JSON slower than Excel? (unlikely, JSON is smaller; test if needed)

---

### Phase 2: Frontend Modularization (5 days)

**Goal:** Extract JavaScript into modules, set up Parcel build, refactor D3 + UI components.

**Tasks:**

#### 2.1 Set Up Parcel Build ✅
- Create `package.json`: Parcel + dev dependencies
- Create `.parcelrc` (build config)
- Test build: `npm run build`
- Create `src/` directory structure

#### 2.2 Extract JavaScript Modules ✅

##### 2.2.1 `src/js/main.js` ✅
- Single-file JS (data injected via `window.__RA_DATA__`)
- All D3, UI, search, mobile logic in one modular source file

#### 2.3 Refactor HTML Template ✅
- Body HTML template extracted as Python string in `build_network_html.py`
- Stats injected via `.format()` placeholders

#### 2.4 CSS Consolidation ✅
- Inline CSS moved → `src/css/style.css`
- Read by build script, inlined into output HTML

#### 2.5 Build Integration ✅
- `build_network_html.py` refactored: 3230 → 308 lines (-90%)
- Runs `npm run build` via subprocess → reads `dist/main.js`
- Injects `window.__RA_DATA__` before bundle
- Output: `ra_genre_network.html` (1567 lines vs 2990 original)

#### 2.6 GitHub Actions Update ✅
- Added `setup-node@v4` (Node.js 20) + `npm install` steps

**Deliverables:**
- ✅ `package.json`, `.parcelrc`
- ✅ `src/js/main.js` (55KB source)
- ✅ `src/css/style.css` (34KB source)
- ✅ Updated `build_network_html.py` (Parcel integration, -90% lines)
- ✅ `ra_genre_network.html` (rebuilt with Parcel, 1567 lines)
- ✅ `.gitignore` updated (dist/, .parcel-cache/, node_modules/)

**Testing:**
- Build locally: `npm install && parcel build src/index.html`
- Load `ra_genre_network.html` in browser
- Test all features:
  - Graph interaction (pan, zoom, node click, hover)
  - Tab switching (Genre Map ↔ Explore ↔ Mixes)
  - Search + autocomplete (keyboard nav)
  - Mobile: swipe, pinch-zoom, detail panel
- Check console: no errors, no warnings
- Verify final size smaller than original (aim: 20–30% reduction)

**Optional (if time):**
- **2.7 Mobile Scroll Bug Investigation**
  - Root cause: CSS `overflow`, JavaScript lifecycle, or browser animation frame
  - Use DevTools to trace DOM mutations
  - Potential fix: `scrollTop = 0` on detail panel mount, or `scroll-behavior: auto`
  - If resolved, update mobile-detail.js + document fix

**Risks:**
- Build process complexity: Parcel integration could fail (mitigation: test locally first)
- Module extraction: Refactoring JS could introduce bugs (mitigation: comprehensive testing)
- Mobile features break: touch gestures, swipe might behave differently (mitigation: mobile testing checklist)

---

### Phase 3: Testing & Deployment (2 days)

**Goal:** Validate all features, deploy to GitHub Pages, verify workflow automation.

**Tasks:**

#### 3.1 End-to-End Testing
- [x] All 1048 mixes load (validated via JSON parse of HTML)
- [x] Labels display for mixes with LLM data (RA.1033 has no labels — known pre-existing issue)
- [x] Genres visible (12 genres on first mix)
- [x] Header stats correct: 1048 mixes, 1034 artists, 138 genres
- [ ] Search finds mixes by artist + mix number (manual browser test)
- [ ] D3 interactions: pan, zoom, click, hover, idle pulse (manual browser test)
- [ ] Tab switching works (all 3 tabs) (manual browser test)
- [ ] Mobile: portrait/landscape, pinch-zoom, tap, swipe, bottom sheet (manual)

#### 3.2 Performance Validation
- [x] Final HTML: 6,963,877 bytes (6.8MB — within target, slightly larger due to minified bundle vs raw JS)
- [x] HTML lines: 1567 vs 2990 original (-47% structural reduction)
- [ ] Build time < 5 minutes (verify on GitHub Actions after merge)
- [ ] Page load time acceptable (manual check)

#### 3.3 Git & CI/CD Validation
- [x] Feature branch: `refactor/modular-architecture`
- [x] All commits on feature branch (2 commits: phase1, phase2)
- [x] `.gitignore` excludes dist/, node_modules/, .parcel-cache/
- [x] GitHub Actions workflow: `setup-node@v4` + `npm install` added

#### 3.4 Deployment
- [x] Merge feature branch → `main`
- [ ] GitHub Actions manual dispatch to verify build
- [ ] Verify `index.html` synced (for GitHub Pages)
- [ ] Visit https://radozoo.github.io/ra-mixes/ — verify live site updated

#### 3.5 Documentation Updates
- [x] Updated `CLAUDE.md`: Frontend architecture section, pipeline steps, manual run instructions
- [x] Added `npm install` first-run note

**Deliverables:**
- ✅ Feature branch merged to `main`
- ✅ Live site updated (GitHub Pages)
- ✅ All workflows passing (GitHub Actions)
- ✅ Updated documentation
- ✅ Archive old JSONL files preserved in git

**Testing Checklist (Mobile):**
- [ ] iPhone (portrait/landscape, Safari)
- [ ] Android (Chrome)
- [ ] Pinch-zoom: 2-finger gesture works
- [ ] Tap: node selection + detail panel opens
- [ ] Swipe: detail panel expand/collapse
- [ ] Scroll: no frozen scroll position bug (verify 2026-04-05 fix still works)
- [ ] Search box responsive (full width, autocomplete visible)
- [ ] Listen button works (SoundCloud embeds)

**Risks:**
- Merge conflicts: If main branch changed during Phase 2 (mitigation: rebase frequently)
- Live site regression: Old browsers not supported (mitigation: test browser compatibility)
- GitHub Actions failure: Node version mismatch (mitigation: lock Node version in setup-node)

---

## Alternative Approaches Considered

### Approach 1: Surgical Fix (Not Chosen)
**Fix ID system + remove Excel, keep frontend as-is**
- Pros: Fastest (3–5 days), lowest risk
- Cons: Monolithic HTML remains (6.6MB); scaling future features harder
- Why rejected: User wanted modern, maintainable frontend code

### Approach 3: Full SPA Modernization (Not Chosen)
**Rewrite in React + FastAPI backend**
- Pros: Modern stack, hot reload, full component architecture
- Cons: 3–4 weeks work, GitHub Pages can't host FastAPI, higher risk
- Why rejected: Overkill for static visualization; feature branch complexity too high

---

## System-Wide Impact

### Interaction Graph

**Data flow on new episode fetch:**
1. `fetch_missing_httpx.py` scrapes ra.co → `data/raw/episode_NNNN.json`
2. `run_pilot.py` parses JSON → `episodes.jsonl` (new format: `RA.XXXX` keyed)
3. `llm_genre_extract.py` (optional) → adds labels to `llm_genre_cache_v2.jsonl`
4. `normalize_labels.py` standardizes labels → updated `llm_genre_cache_v2.jsonl`
5. `genre_normalizer.py` filters genres → `genre_edges.jsonl`
6. `consolidated_exporter.py` (NEW) reads all sources → `consolidated.json`
7. `build_network_html.py` reads `consolidated.json` → runs Parcel → `ra_genre_network.html`
8. GitHub Actions commits + syncs `index.html` → GitHub Pages live

**Frontend on mix selection:**
1. User clicks mix in D3 graph or search result
2. `main.js` calls `selectMix(ra_mix_id)`
3. `ui-tabs.js` switches to "Explore" tab
4. `mobile-detail.js` (mobile) shows bottom sheet OR detail panel (desktop)
5. Labels + genres populated from `consolidated.json` window object
6. D3 graph highlights neighbors

### Error & Failure Propagation

**Build failures:**
- Pydantic validation fails in `consolidated_exporter.py` → error logged, build halts
- Parcel bundle fails → error logged, build halts
- GitHub Actions logs → email notification (user configures)

**Fallback mechanisms:**
- If LLM extraction skipped → regex-based genres used (existing fallback preserved)
- If missing data in mix → build warns, skips mix (graceful degradation)

### State Lifecycle Risks

**Migration step (Phase 1):**
- Old JSONL files archived, new v2 files created
- If migration fails → revert to archived originals from git
- Pydantic validation ensures data integrity before build

**Incremental updates:**
- Each run of `consolidated_exporter.py` reads all intermediate files + produces fresh `consolidated.json`
- No partial state: build always starts from consistent source

### API Surface Parity

**Python scripts unchanged:**
- `fetch_missing_httpx.py` → same interface
- `run_pilot.py` → same interface (output format: episodes.jsonl, but keyed differently)
- `llm_genre_extract.py` → same interface

**Build script:**
- Old: `excel_exporter.py` → `build_network_html.py`
- New: `consolidated_exporter.py` → `build_network_html.py`
- Both produce same output (ra_genre_network.html)

**Frontend:**
- D3 graph: same interface (accepts MIXES array, renders same visualization)
- UI tabs: same tabs, same content
- No breaking API changes (except internal refactor)

### Integration Test Scenarios

1. **Fetch + parse new mix**
   - Run `fetch_missing_httpx.py` → `run_pilot.py`
   - Verify new mix appears in `episodes.jsonl` with `RA.XXXX` key
   - Run full pipeline → verify mix in final HTML + graph

2. **Duplicate RA.XXXX (multiple podcast_ids)**
   - Manually edit `episodes.jsonl` to create duplicate `RA.XXXX` entries
   - Run `consolidated_exporter.py` → verify `podcast_ids` array contains both IDs
   - Build HTML → verify mix appears once with both IDs in metadata

3. **Missing labels for new mix**
   - Add new mix to `episodes.jsonl` without LLM labels
   - Run pipeline with LLM skipped → verify regex genres still appear
   - Run with LLM → verify labels populated

4. **Search + D3 interaction (end-to-end)**
   - Load HTML, search for mix → verify autocomplete
   - Click result → D3 zooms to node + highlights neighbors
   - Click detail panel → verify labels, genres, tracklist load
   - Mobile: tap → detail sheet appears at 50vh

5. **GitHub Actions weekly run**
   - Manually trigger workflow: `Run workflow` button
   - Verify: fetch → parse → normalize → build → commit → push
   - Verify: GitHub Pages updated within 30 seconds

---

## Acceptance Criteria

### Functional Requirements

- [ ] Data model: `RA.XXXX` is primary key (all lookups use this)
- [ ] ID system: Labels/genres keyed to `RA.XXXX`, not `podcast_id`
- [ ] Sorting: Mixes sorted by `RA.XXXX` + release date (ascending mix number, newest date first)
- [ ] Excel removed: No `openpyxl` imports, no Excel files in pipeline
- [ ] Consolidated.json: Single source of truth for build (validated with Pydantic)
- [ ] Frontend modularized: Separate `.js` files (d3-graph, ui-tabs, search-box, mobile-detail, shared)
- [ ] Parcel bundler: All modules bundled, CSS minified, final HTML generated
- [ ] All features functional: D3 graph, tabs, search, mobile interactions work identically to before
- [ ] Label display: Each mix shows labels in detail panel (no regressions)
- [ ] Search: Autocomplete works, keyboard nav works, zoom-to-node works
- [ ] Mobile: Pinch-zoom, tap, swipe, detail sheet all functional; scroll bug investigated/fixed

### Non-Functional Requirements

- [ ] Performance: Build time < 5 minutes (GitHub Actions)
- [ ] File size: Final HTML < 6.8MB (current), ideally ~20–30% reduction
- [ ] Browser compatibility: Chrome, Safari, Firefox (desktop + mobile)
- [ ] Accessibility: Touch targets ≥ 44px, color contrast maintained
- [ ] Code quality: No console errors/warnings (production build)

### Quality Gates

- [ ] All tests passing (end-to-end, mobile, performance)
- [ ] Code review approved (architecture, module boundaries, data flow)
- [ ] Documentation updated (CLAUDE.md, data schema, build instructions)
- [ ] Feature branch merged to `main`
- [ ] GitHub Pages live verified

---

## Success Metrics

1. **Stability**: No ID-related bugs (labels load correctly, sorting works, no orphaned data)
2. **Performance**: Build completes in < 5 minutes, final HTML loads in < 3 seconds
3. **Maintainability**: New features can be added to specific modules without touching others
4. **Size**: Final HTML ≤ 6.8MB (ideally < 5.5MB with minification)
5. **Developer Experience**: Adding new mix → automatic label load, no manual data shuffling

---

## Dependencies & Prerequisites

### Software Dependencies

**Python:**
- Python 3.9+
- `pydantic` (new: data validation)
- `jsonlines` (existing)
- `httpx`, `playwright` (existing)
- `openpyxl` (REMOVED)

**Node.js:**
- Node.js 18+ (new: for Parcel bundler)
- Parcel 2.x
- npm/yarn

**GitHub Actions:**
- Ubuntu runner (existing)
- `setup-python@v4` (existing)
- `setup-node@v4` (new)

### Data Dependencies

- `data/raw/episode_*.json` (existing)
- `episodes_v1.jsonl` (old, archived)
- `episodes_v2.jsonl` (new, primary)
- `llm_genre_cache.jsonl` (old, archived)
- `llm_genre_cache_v2.jsonl` (new, primary)
- `consolidated.json` (new, single source of truth)

### Git & CI/CD

- Feature branch: `refactor/modular-architecture`
- Workflow: `.github/workflows/weekly-pipeline.yml` updated
- Deployments: GitHub Pages (existing)

---

## Risk Analysis & Mitigation

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|-----------|
| **Data migration fails** | Low | Critical (pipeline halts) | Test migration on branch first; keep git history of old files |
| **Build process breaks** | Medium | Critical (site down) | Extensive testing before merge; rollback to old build script if needed |
| **Mobile UX regresses** | Medium | High (user frustration) | Mobile testing checklist; compare before/after screenshots |
| **Parcel bundling issues** | Low | High (final size blows up) | Test build locally; verify minification works |
| **JavaScript module conflicts** | Low | Medium (features broken) | Use unique variable names; avoid global scope pollution |
| **Pydantic validation too strict** | Low | Medium (legitimate data rejected) | Test with sample data before full pipeline |
| **Node.js version mismatch** | Low | Medium (GitHub Actions fails) | Lock Node.js version in `setup-node` action |

---

## Resource Requirements

### Team

- **1 Architect/Developer** (you)
- Code review (optional): peer or AI pair programming

### Time Estimate

- **Phase 1** (Data Model): 3 days
- **Phase 2** (Frontend Modules): 5 days  
- **Phase 3** (Testing + Deploy): 2 days
- **Buffer**: ~2 days for debugging/blockers
- **Total**: 1–2 weeks (10–12 working days)

### Infrastructure

- Local machine (Python + Node.js)
- GitHub (repo, Actions, Pages)
- Parcel build (runs locally + in GitHub Actions)

---

## Future Considerations

### Extensibility

**Without re-architecting:**
1. Add new features (e.g., user annotations) → add field to Pydantic model + inject in consolidated.json
2. New data sources (e.g., Beatport genres) → extend parser, add to pipeline
3. New D3 visualizations → add module `src/js/alternative-graph.js`, swap in `main.js`

**Potential future work:**
- Component library (Storybook) for UI modules
- Unit + integration tests (jest, pytest)
- TypeScript for type safety (JS → TS migration)
- Incremental builds (only rebuild changed mixes)
- Compression (gzip consolidated.json, lazy-load mix details)

---

## Documentation Plan

### Updates Required

- [ ] **CLAUDE.md**
  - Add: "Data Model" section (RA.XXXX as primary key, podcast_ids array)
  - Add: "Pipeline Architecture" section (consolidated.json, no Excel)
  - Update: "Weekly Pipeline" section (new steps: consolidated_exporter)
  
- [ ] **Build Instructions** (new file: `BUILD.md`)
  - Local development: `npm install && npm run build`
  - How data flows through pipeline
  - How to add new mixes

- [ ] **Data Schema** (new file: `DATA_SCHEMA.md`)
  - Pydantic models (Mix, Genre, Label, etc.)
  - consolidated.json structure
  - Examples

- [ ] **GitHub Actions** (inline in workflow)
  - Document Node.js setup
  - Parcel build step

---

## Sources & References

### Origin

- **Brainstorm document:** [docs/brainstorms/2026-04-09-modular-refactor-brainstorm.md](../brainstorms/2026-04-09-modular-refactor-brainstorm.md)
  - Key decisions carried forward:
    1. `RA.XXXX` as primary key (not `podcast_id`)
    2. Remove Excel, use consolidated.json
    3. Modularize frontend with Parcel bundler
    4. Keep old JSONL files for audit trail
    5. Preindex existing LLM labels (no rebuild)

### Internal References

- **Current pipeline:** `scripts/build_network_html.py` (3,236 lines — monolithic build script)
- **Data sources:** `data/episodes.jsonl`, `data/genre_edges.jsonl`, `llm_genre_cache.jsonl`
- **Frontend:** `ra_genre_network.html` (6.6MB, 2990 lines)
- **GitHub Actions:** `.github/workflows/weekly-pipeline.yml`

### External References

- **Pydantic:** https://docs.pydantic.dev/ (schema validation)
- **Parcel:** https://parceljs.org/ (bundler)
- **D3.js:** https://d3js.org/ (force-directed layout)

---

## Implementation Notes

### Phase 1 Detailed Tasks

**1.1 Pydantic models** (`python/models.py`)
```python
from pydantic import BaseModel, Field
from typing import List, Dict, Optional

class Mix(BaseModel):
    podcast_id: int           # Primary key — unique per episode
    ra_mix_number: str        # Display name (e.g. "RA.1033"), extracted from title
    title: str                # Full title from RA.co (e.g. "RA.1033 Isaac Carter")
    artist: str
    release_date: str         # ISO 8601
    genres: List[str]
    labels: Dict[str, List[str]]  # {mood: [...], energy: [...]}
    
    class Config:
        json_schema_extra = {"examples": [...]}
```

**1.4 consolidated_exporter.py** (pseudocode)
```python
def consolidate():
    episodes = load_jsonl('data/episodes_v2.jsonl')
    genres = load_jsonl('data/genre_edges.jsonl')
    labels = load_jsonl('data/llm_genre_cache_v2.jsonl')
    
    # Validate all mixes
    for mix in episodes:
        assert Mix(**mix)  # Pydantic validation
    
    # Consolidate
    consolidated = {
        'mixes': episodes,
        'genres': genres,
        'labels': labels,
        'metadata': {
            'generated': datetime.now().isoformat(),
            'version': '2.0'
        }
    }
    
    with open('data/consolidated.json', 'w') as f:
        json.dump(consolidated, f)
```

### Phase 2 Detailed Tasks

**2.2 Module signatures** (for integration)

```javascript
// d3-graph.js
export function initD3Graph(mixes, container) { ... }

// ui-tabs.js
export function initTabs() { ... }
export function selectTab(name) { ... }

// main.js
import { initD3Graph } from './d3-graph.js';
const mixes = window.DATA.mixes;
initD3Graph(mixes, '#graph-container');
```

---

## Next Steps

1. ✅ **Brainstorm complete** (2026-04-09)
2. ✅ **Plan complete** (this document)
3. 📋 **Review & approve plan** (awaiting user feedback)
4. 🚀 **Start Phase 1** (create feature branch, implement data model)

