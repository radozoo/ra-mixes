---
title: "Mix disappeared after deleting episode raw file (podcast_id ↔ RA.XXXX mapping)"
problem_type: logic-errors
component: data-model, git-versioning
symptoms:
  - Mix disappears from site after cleanup operation
  - Mix present in git history but not on live page
  - Duplicate mix on page after CI run
tags:
  - podcast_id
  - ra-number-offset
  - raw-file-deletion
  - data-integrity
  - git-recovery
date: 2026-04-13
---

# Mix disappeared after deleting episode raw file

## Problem

When cleaning up stale data (e.g. fixing a duplicate mix), a `data/raw/episode_XXXX.json` file
was deleted. The deletion removed the only source of data for a *different* mix — because
`podcast_id` (the file number) does not match the `RA.XXXX` display number.

**Concrete incident (2026-04-13):**
- `episode_1033.json` was deleted to fix a duplicate RA.1033 on page
- But `episode_1033.json` contained data for **RA.1014 Wax'o Paradiso** (podcast_id=1033 → RA.1014)
- RA.1014 vanished from the site completely

## Root Cause

### podcast_id ≠ RA.XXXX

| Field | Example | Meaning |
|---|---|---|
| `podcast_id` | `1033` | Internal scraper ID — filename in `data/raw/` |
| `RA.XXXX` | `RA.1014` | Display number — extracted from `title` field in raw JSON |

**These are different numbers.** For recent episodes (RA.1030+) the offset is **+19**:

```
podcast_id=1033 → RA.1014
podcast_id=1052 → RA.1033  (RA.1033 Isaac Carter — confirmed special case)
podcast_id=1053 → RA.1034
```

The offset has changed historically — it is NOT guaranteed to stay at +19. The only reliable
source of truth is the `title` field inside the raw JSON file itself.

### Raw file = single source of data

`data/raw/episode_{podcast_id}.json` is the primary source for every mix:
- `run_pilot.py` reads it to populate `episodes.jsonl` and `tracks.jsonl`
- `llm_genre_extract.py` reads it for tracklist and blurb
- If the file is deleted and not restored before the next pipeline run, all downstream data
  (episodes, genres, labels) is lost for that mix

## Solution

### Step 1 — Always verify before deleting

```bash
# Check what a raw file actually contains before deleting
python3 -c "import json; d=json.load(open('data/raw/episode_1033.json')); print(d.get('title'))"
# → RA.1014 Wax'o Paradiso   ← NOT what you think it is!
```

### Step 2 — Restore from git history (if already deleted)

```bash
# Find the last commit that had the file
git log --oneline -- data/raw/episode_1033.json | head -5

# Restore from that commit
git show {COMMIT_HASH}:data/raw/episode_1033.json > data/raw/episode_1033.json
```

### Step 3 — Re-run pipeline for the restored episode

```bash
python3 run_pilot.py --ids 1033
# Add manual LLM cache entry if API key unavailable (see integration-issues/weekly-pipeline-labels-missing.md)
python3 scripts/normalize_llm_cache.py
python3 scripts/normalize_labels.py
python3 normalize/genre_normalizer.py
python3 python/consolidated_exporter.py
python3 scripts/build_network_html.py
cp ra_genre_network.html index.html
```

### Step 4 — Verify and commit

```bash
# Confirm mix appears with correct data
python3 -c "
import json
count = sum(1 for l in open('data/episodes.jsonl') if '1033' in l)
entry = next((json.loads(l) for l in open('data/episodes.jsonl') if '\"1033\"' in l), None)
print(f'Found: {count} entry, title: {entry.get(\"title\") if entry else None}')
"

git add data/raw/episode_1033.json data/episodes.jsonl data/tracks.jsonl \
        data/llm_genre_cache.jsonl data/llm_genre_cache_normalized.jsonl \
        data/llm_genre_cache_with_categories.jsonl index.html ra_genre_network.html
git commit -m "fix: Restore RA.XXXX {artist} (episode_{pid}.json was deleted)"
git push origin main
```

## Prevention

**Rule: Never delete `data/raw/episode_*.json` without verifying the title field.**

The `podcast_id` in the filename does NOT match the RA.XXXX display number. Always run:
```bash
python3 -c "import json; d=json.load(open('data/raw/episode_XXXX.json')); print(d.get('title'))"
```

A file named `episode_1033.json` can legitimately contain data titled `RA.1014 Wax'o Paradiso`.

## Related

- [Weekly pipeline labels missing](../integration-issues/weekly-pipeline-labels-missing.md)
