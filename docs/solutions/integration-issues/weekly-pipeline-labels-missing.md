---
title: "Weekly pipeline runs but new mix has no genre labels"
problem_type: integration-issues
component: workflow, requirements, environment-variables, llm-pipeline
symptoms:
  - New mix appears on site but label chips (Mood, Energy, Vibe, Setting) are empty
  - consolidated_exporter.py reports "Missing labels: 1"
  - normalize_labels.py log shows N episodes (not N+1 after new mix)
  - CI logs show ModuleNotFoundError: No module named 'anthropic'
tags:
  - github-actions
  - anthropic-api
  - requirements-txt
  - normalize-llm-cache
  - missing-pipeline-step
  - env-var-mismatch
date: 2026-04-13
---

# Weekly pipeline runs but new mix has no genre labels

## Problem

Monday automated pipeline (GitHub Actions) completes successfully and the new mix appears on the
site — but without any label chips (Mood, Energy, Vibe, Setting, Geography). The mix shows genres
but not the descriptive LLM-generated labels.

**Concrete incident (2026-04-13):** RA.1034 RamonPang (podcast_id=1053) appeared without labels
after the automated Monday run.

## Root Cause

Three separate failures that must ALL be fixed:

### Failure 1 — `anthropic` missing from requirements.txt

`llm_genre_extract.py` line 23: `import anthropic` — crashes with `ModuleNotFoundError` if the
package is not installed. Without this, no LLM extraction runs and `llm_genre_cache.jsonl` gets
no new entry for the episode.

### Failure 2 — Wrong environment variable name in workflow

GitHub Actions workflow set:
```yaml
env:
  CLAUDE_API_KEY: ${{ secrets.CLAUDE_API_KEY }}
```

But `anthropic.Anthropic()` (line 297 in llm_genre_extract.py) reads `ANTHROPIC_API_KEY` by
default. The client got no API key → authentication error.

**Correct form:**
```yaml
env:
  ANTHROPIC_API_KEY: ${{ secrets.CLAUDE_API_KEY }}
```
(Secret in GitHub is named `CLAUDE_API_KEY` — this is fine. The env var exposed to the process
must be `ANTHROPIC_API_KEY`.)

### Failure 3 — `normalize_llm_cache.py` missing from workflow

The LLM cache data flow has two files:
```
llm_genre_extract.py  →  data/llm_genre_cache.jsonl          (raw output)
normalize_llm_cache.py →  data/llm_genre_cache_normalized.jsonl  (normalized — what normalize_labels.py reads)
```

`normalize_labels.py` reads `llm_genre_cache_normalized.jsonl`, NOT the raw cache. If
`normalize_llm_cache.py` is not called between them, new episodes never get labels.

### Bonus: data files not committed

Originally the workflow only committed `index.html` + `ra_genre_network.html`. All JSONL caches
(genre cache, normalized cache, with_categories) were discarded after each CI run. This meant:
- Next run had to re-extract everything from scratch
- Manual cache entries written locally were lost after push

## Solution

### Fix 1 — requirements.txt

Ensure `anthropic` is present (no version pin needed):
```
playwright==1.49.0
httpx==0.27.2
jsonlines==4.0.0
openpyxl==3.1.5
pydantic>=2.0
anthropic
```

### Fix 2 & 3 — Workflow (`.github/workflows/weekly-pipeline.yml`)

The "Parse and extract genres" step must look like this:
```yaml
- name: Parse and extract genres
  env:
    ANTHROPIC_API_KEY: ${{ secrets.CLAUDE_API_KEY }}
  run: |
    python run_pilot.py --ids ${{ steps.latest.outputs.episode_id }}
    python scripts/llm_genre_extract.py || echo "LLM extraction skipped, continuing with regex genres..."
    python scripts/normalize_llm_cache.py || echo "Cache normalization skipped"
```

And the commit step must include all data files:
```yaml
git add index.html ra_genre_network.html \
  data/raw/ \
  data/episodes.jsonl data/tracks.jsonl \
  data/genre_edges.jsonl data/genre_edges_clean.jsonl data/genre_map.json \
  data/llm_genre_cache.jsonl data/llm_genre_cache_normalized.jsonl \
  data/llm_genre_cache_with_categories.jsonl
```

## Manual recovery (when API key is unavailable locally)

If the Anthropic API key is expired or unavailable, add the cache entry manually:

```python
import json

entry = {
    "podcast_id": "1053",          # the episode's podcast_id
    "genres": ["House", "Techno"], # 2–8 genres
    "labels": ["dark", "club"],    # 3–10 descriptive labels
    "notes": "Brief rationale",
    "model": "claude-sonnet-4-6 (manual)"
}
with open("data/llm_genre_cache.jsonl", "a") as f:
    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
```

**IMPORTANT:** Always append to `llm_genre_cache.jsonl` (raw), NOT to
`llm_genre_cache_normalized.jsonl`. The normalize script OVERWRITES `_normalized.jsonl` from the
raw cache — manual entries in `_normalized.jsonl` will be lost on the next normalize run.

Then re-run the pipeline from step 4:
```bash
python3 scripts/normalize_llm_cache.py
python3 scripts/normalize_labels.py
python3 normalize/genre_normalizer.py
python3 python/consolidated_exporter.py
python3 scripts/build_network_html.py
cp ra_genre_network.html index.html
```

## Diagnosis checklist

When a new mix has no labels:

1. **Check normalize_labels.py log** — should report `N` episodes where N = total mix count. If N-1, the new episode has no cache entry.
2. **Check consolidated_exporter.py log** — "Missing labels: 1" confirms the issue.
3. **Check CI logs** — search for `ModuleNotFoundError` or `authentication_error` in the "Parse and extract genres" step.
4. **Check llm_genre_cache.jsonl** — grep for the podcast_id: `grep '"1053"' data/llm_genre_cache.jsonl`

## Related

- [podcast_id ↔ RA.XXXX mapping](../logic-errors/podcast-id-ra-number-mapping.md)
