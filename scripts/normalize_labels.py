"""
normalize_labels.py — Normalizes free-form LLM labels into structured categories.

Reads:  data/llm_genre_cache_normalized.jsonl
Writes: data/label_normalization.json          (raw → [{category, canonical}])
        data/llm_genre_cache_with_categories.jsonl  (original + label_categories field)

Categories: mood, energy, setting, geography, style, era, vibe
"""

import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

# Load .env if present
_env_path = Path(__file__).parent.parent / ".env"
if _env_path.exists():
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip().strip('"'))

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"

CACHE_IN  = DATA_DIR / "llm_genre_cache_normalized.jsonl"
NORM_OUT  = DATA_DIR / "label_normalization.json"
CACHE_OUT = DATA_DIR / "llm_genre_cache_with_categories.jsonl"

# ── Taxonomy ──────────────────────────────────────────────────────────────────
# Each (pattern, category, canonical) is tried in order.
# pattern: regex applied to the lowercased raw label.
# First match wins unless the rule is marked compound (handled separately).

RULES = [
    # ── MOOD ──────────────────────────────────────────────────────────────────
    (r"euphor",          "mood", "euphoric"),
    (r"hypnot",          "mood", "hypnotic"),
    (r"melanchol",       "mood", "melancholic"),
    (r"dream[yi]",       "mood", "dreamy"),
    (r"playful",         "mood", "playful"),
    (r"tense|tension",   "mood", "tense"),
    (r"uplift",          "mood", "uplifting"),
    (r"meditat",         "mood", "meditative"),
    (r"cerebral",        "mood", "cerebral"),
    (r"atmospheric",     "mood", "atmospheric"),
    (r"warm.+soul|soul.+warm",  "mood", "warm and soulful"),
    (r"\bwarm\b",        "mood", "warm"),
    (r"\bmelodic\b",     "mood", "melodic"),
    (r"\bdark\b",        "mood", "dark"),
    (r"introspect",      "mood", "introspective"),
    (r"moody",           "mood", "dark"),
    (r"^dark\s+and|^dark\s*$",   "mood", "dark"),
    (r"brooding",        "mood", "dark"),
    (r"cinematic",       "mood", "cinematic"),
    (r"joyful|jubilant", "mood", "uplifting"),
    (r"nostalgic|nostalgik", "mood", "nostalgic"),
    (r"^emotional",      "mood", "emotional"),

    # ── ENERGY ────────────────────────────────────────────────────────────────
    (r"peak.?time|peak energy|peak intensity|dancefloor.?peak|peak.?floor", "energy", "peak-time"),
    (r"warm.?up",        "energy", "warm-up"),
    (r"slow.?burn",      "energy", "slow-burn"),
    (r"high.?energy|high.?octane|intense.energy|frenetic|relentless.energy|stadium.energy|arena.energy|massive.energy", "energy", "high-energy"),
    (r"stadium|arena.sized|arena.scale", "energy", "high-energy"),
    (r"low.?energy|subdued energy", "energy", "low-energy"),
    (r"after.?hour",     "energy", "afterhours"),
    (r"late.?night",     "energy", "afterhours"),
    (r"sunrise|dawn",    "energy", "sunrise"),
    (r"mid.?tempo",      "energy", "mid-tempo"),
    (r"160 bpm|fast bpm|rapid|breakneck", "energy", "high-energy"),

    # ── SETTING ───────────────────────────────────────────────────────────────
    (r"festival",        "setting", "festival"),
    (r"home.?listen|listening.?at.?home", "setting", "home-listening"),
    (r"warehouse",       "setting", "warehouse"),
    (r"\boutdoor\b",     "setting", "outdoor"),
    (r"\bradio\b",       "setting", "radio"),
    (r"community.?radio","setting", "radio"),
    (r"\bclub\b",        "setting", "club"),

    # ── GEOGRAPHY ─────────────────────────────────────────────────────────────
    (r"\bberlin\b",      "geography", "Berlin"),
    (r"\blondon\b",      "geography", "London"),
    (r"\bdetroit\b",     "geography", "Detroit"),
    (r"\bchicago\b",     "geography", "Chicago"),
    (r"\bnew york\b|\bnyc\b|\bny\b underground", "geography", "NYC"),
    (r"\btokyo\b",       "geography", "Tokyo"),
    (r"\bmanchester\b",  "geography", "Manchester"),
    (r"\bglasgow\b",     "geography", "Glasgow"),
    (r"\bbristol\b",     "geography", "Bristol"),
    (r"\bamsterdam\b",   "geography", "Amsterdam"),
    (r"\bbirmingham\b",  "geography", "Birmingham"),
    (r"\bbrusses\b|\bbrussels\b", "geography", "Brussels"),
    (r"\bparis\b",       "geography", "Paris"),
    (r"\bdublin\b",      "geography", "Dublin"),
    (r"\bnorthern irish\b|\bnorthern ireland\b", "geography", "Northern Ireland"),
    (r"\birish\b|\bireland\b", "geography", "Ireland"),
    (r"\bbarcelo\b",     "geography", "Barcelona"),
    (r"\bavao\b|\bdavao\b", "geography", "Davao"),
    (r"\bfilipino\b|\bphilippines\b|\bphilipine\b", "geography", "Philippines"),
    (r"\bjapan\b|\bjapanese\b",  "geography", "Japan"),
    (r"\bkorean\b|\bkorea\b",    "geography", "Korea"),
    (r"\bscandinav\b|\bnordic\b|\bswedish\b|\bnorwegian\b|\bdanish\b|\bfinnish\b", "geography", "Scandinavia"),
    (r"\bafric\b|\bwest african\b|\bsouth african\b|\bnigerian\b|\bghanaian\b|\bkenyans\b", "geography", "Africa"),
    (r"\bcaribbean\b|\bjamaic\b|\btrinidad\b|\bbarbados\b", "geography", "Caribbean"),
    (r"\bbrazil\b|\bbrazilian\b|\brio\b|\bsão paulo\b", "geography", "Brazil"),
    (r"\blatin\b",       "geography", "Latin America"),
    (r"\bmidwest\b",     "geography", "US Midwest"),
    (r"\bamerican\b|\busa\b|\bus-based\b", "geography", "US"),
    (r"\buk\b|\bbritish\b",   "geography", "UK"),
    (r"\beuropean\b|\beurope\b", "geography", "Europe"),
    (r"\bglobal\b|\binternational\b", "geography", "Global"),

    # ── STYLE ─────────────────────────────────────────────────────────────────
    (r"vinyl.focus|vinyl.sourc|vinyl.inform|vinyl.centr|vinyl.driven|vinyl.only|vinyl.based", "style", "vinyl-focused"),
    (r"sample.heavy|sample.driven|sample.based|sample.rich|sample.laden", "style", "sample-heavy"),
    (r"vocal.driven|vocal.focus|vocal.heavy|vocals?.led|singer.driven|voice.led", "style", "vocal-driven"),
    (r"\binstrumental\b", "style", "instrumental"),
    (r"live.record|recorded live|live.perform|live.set", "style", "live-recorded"),
    (r"genre.fluid|genre.blend|genre.defying|multi.genre|cross.genre|eclectic.blend", "style", "genre-fluid"),
    (r"\blo.?fi\b",      "style", "lo-fi"),
    (r"bass.heavy|bass.driven|bass.focused|bass.forward|low.end.focus", "style", "bass-heavy"),
    (r"dub.influen|dub.infused|reggae.influen", "style", "dub-influenced"),
    (r"synth.based|synth.driven|synthesizer.heavy", "style", "synth-driven"),
    (r"drum.machine|machine.driven", "style", "drum machine"),
    (r"ambient.influenced|ambient.infused", "style", "ambient-influenced"),
    (r"jazz.influenced|jazz.inflect|jazz.infused", "style", "jazz-influenced"),
    (r"funk.influenced|funk.infused|funky", "style", "funky"),
    (r"turntabli|scratch", "style", "turntablism"),
    (r"pitched.up|pitched.vocals", "style", "pitched vocals"),
    (r"loop.driven|looped", "style", "loop-driven"),
    (r"groove.focus|groove.driven|groove.based|groove.orient|groove.heavy", "style", "groove-focused"),
    (r"mixing.flow|mix.flow|seamless.mix|mix.master|impeccable.mix", "style", "precise mixing"),
    (r"studio.craft|studio.produc|studio.made", "style", "studio-crafted"),
    (r"dark.gritty|gritty.dark|raw.gritty|gritty", "mood", "dark"),

    # ── ERA ───────────────────────────────────────────────────────────────────
    (r"\b80s\b|nineteen.eight|1980s", "era", "80s"),
    (r"\b90s\b|nineteen.nine|1990s", "era", "90s"),
    (r"\b2000s\b|\b00s\b|early.2000s|noughties", "era", "00s"),
    (r"\b2010s\b|\b10s\b", "era", "2010s"),
    (r"contemporary|modern.era|current.era|present.day", "era", "contemporary"),
    (r"\bclassic\b",     "era", "classic"),
    (r"futuristic|forward.thinking|cutting.edge|forward.looking", "era", "futuristic"),
    (r"\bretro\b",       "era", "retro"),
    (r"golden.age|golden.era", "era", "classic"),
    (r"pioneer|legendary|seminal|foundational", "era", "classic"),

    # ── VIBE ──────────────────────────────────────────────────────────────────
    (r"underground",     "vibe", "underground"),
    (r"leftfield|left.field|unconventional|experimental", "vibe", "leftfield"),
    (r"\beclectic\b",    "vibe", "eclectic"),
    (r"psychedel",       "vibe", "psychedelic"),
    (r"dancefloor|dance.floor|floor.focused|floor.driven|floor.orient",
                         "vibe", "dancefloor"),
    (r"community.focus|community.driven|grassroots", "vibe", "community-focused"),
    (r"\bsoulful\b",     "vibe", "soulful"),
    (r"groove.orient|groov[ey]",  "vibe", "groovy"),
    (r"minimalist|minimalism|minimal aesthetic", "vibe", "minimal"),
    (r"maximalist",      "vibe", "maximalist"),
    (r"trippy",          "vibe", "trippy"),
    (r"spiritual",       "vibe", "spiritual"),
    (r"political|activist|protest", "vibe", "political"),
    (r"queer|lgbtq",     "vibe", "queer"),
    (r"afro.beat|afrobeat", "vibe", "afrobeat-influenced"),
]

# Compound rules: labels that should produce TWO mappings
# Each entry: (pattern, [(category1, canonical1), (category2, canonical2)])
COMPOUND_RULES = [
    (r"uk.underground|underground.uk",      [("geography", "UK"),      ("vibe", "underground")]),
    (r"berlin.underground|underground.berlin", [("geography", "Berlin"), ("vibe", "underground")]),
    (r"london.underground|underground.london", [("geography", "London"), ("vibe", "underground")]),
    (r"detroit.underground",                [("geography", "Detroit"),  ("vibe", "underground")]),
    (r"new york.underground|nyc.underground", [("geography", "NYC"),    ("vibe", "underground")]),
    (r"chicago.underground",                [("geography", "Chicago"),  ("vibe", "underground")]),
    (r"berlin.based",                       [("geography", "Berlin"),   ("vibe", "underground")]),
    (r"detroit.influen",                    [("geography", "Detroit"),  ("era", "classic")]),
    (r"contemporary.underground",           [("era", "contemporary"),   ("vibe", "underground")]),
    (r"contemporary.uk|uk.contemporary",    [("geography", "UK"),       ("era", "contemporary")]),
    (r"peak.time.+club|club.+peak.time",    [("energy", "peak-time"),   ("setting", "club")]),
    (r"warm.up.+peak|warm.to.peak",         [("energy", "warm-up"),     ("energy", "peak-time")]),
    (r"late.night.+club|club.+late.night",  [("energy", "afterhours"),  ("setting", "club")]),
]


def match_label(raw: str) -> list[dict]:
    """Return list of {category, canonical} for a raw label."""
    lo = raw.lower()

    # Try compound rules first
    for pattern, mappings in COMPOUND_RULES:
        if re.search(pattern, lo):
            return [{"category": c, "canonical": canon} for c, canon in mappings]

    # Try single rules
    for pattern, category, canonical in RULES:
        if re.search(pattern, lo):
            return [{"category": category, "canonical": canonical}]

    return []


def build_rule_based_mapping(all_labels: list[str]) -> dict:
    """Apply rule-based matching to all unique labels."""
    mapping = {}
    unmatched = []

    for label in sorted(set(all_labels)):
        result = match_label(label)
        if result:
            mapping[label] = result
        else:
            unmatched.append(label)

    return mapping, unmatched


def batch_llm_classify(labels: list[str], client) -> dict:
    """Classify unmatched labels via Haiku in batches."""
    BATCH = 30
    mapping = {}

    categories_desc = (
        "mood (euphoric/hypnotic/dark/introspective/melancholic/dreamy/playful/uplifting/meditative/cerebral/atmospheric/warm/melodic), "
        "energy (peak-time/warm-up/slow-burn/high-energy/afterhours/sunrise/mid-tempo/low-energy), "
        "setting (club/festival/home-listening/warehouse/outdoor/radio), "
        "geography (specific city, region, or country), "
        "style (vinyl-focused/sample-heavy/vocal-driven/instrumental/live-recorded/genre-fluid/lo-fi/bass-heavy/dub-influenced/synth-driven/loop-driven/groove-focused), "
        "era (80s/90s/00s/2010s/contemporary/classic/futuristic/retro), "
        "vibe (underground/leftfield/eclectic/psychedelic/dancefloor/community-focused/soulful/minimal/groovy/trippy)"
    )

    system = "You are a music taxonomy expert. Classify DJ mix descriptive tags into structured categories."

    for i in range(0, len(labels), BATCH):
        batch = labels[i:i + BATCH]
        label_list = "\n".join(f"- {l}" for l in batch)

        prompt = f"""Classify each label below into ONE category and a canonical short form.
Categories: {categories_desc}

Rules:
- canonical: short, lowercase, normalized form (e.g. "peak-time", "introspective", "Berlin")
- If a label fits NO category well, use category "other" and canonical = simplified version
- Return ONLY valid JSON: a list of objects with keys: label, category, canonical

Labels:
{label_list}

Return JSON array only:"""

        try:
            resp = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1200,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
            text = resp.content[0].text.strip()
            # Extract JSON array
            m_json = re.search(r'\[.*\]', text, re.DOTALL)
            if m_json:
                results = json.loads(m_json.group())
                # Build lookup from LLM-returned label → classification
                llm_lookup = {}
                for item in results:
                    raw = item.get("label", "")
                    cat = item.get("category", "other")
                    canon = item.get("canonical", raw.lower())
                    if raw:
                        llm_lookup[raw.lower()] = {"category": cat, "canonical": canon}

                # Match back to original labels (case-insensitive)
                matched_count = 0
                for orig in batch:
                    key = orig.lower()
                    if key in llm_lookup:
                        entry = llm_lookup[key]
                        mapping[orig] = [entry]
                        matched_count += 1
                    else:
                        # Fuzzy: try stripping/trimming
                        found = False
                        for llm_key, entry in llm_lookup.items():
                            if llm_key in key or key in llm_key:
                                mapping[orig] = [entry]
                                matched_count += 1
                                found = True
                                break
                        if not found:
                            mapping[orig] = [{"category": "other", "canonical": orig.lower()}]
            print(f"  LLM batch {i//BATCH + 1}: classified {len(batch)} labels → mapping {len(mapping)}")
            if i + BATCH < len(labels):
                time.sleep(0.5)
        except Exception as e:
            print(f"  LLM batch error: {e}")
            # Fallback: mark as other
            for lbl in batch:
                mapping[lbl] = [{"category": "other", "canonical": lbl.lower()}]

    print(f"  batch_llm_classify returning {len(mapping)} entries")
    return mapping


def apply_mapping_to_cache(mapping: dict):
    """Generate llm_genre_cache_with_categories.jsonl with label_categories added."""
    written = 0
    skipped = 0

    with open(CACHE_IN, encoding="utf-8") as fin, \
         open(CACHE_OUT, "w", encoding="utf-8") as fout:

        for line in fin:
            if not line.strip():
                continue
            obj = json.loads(line)
            raw_labels = obj.get("labels", [])

            # Build label_categories from mapping
            label_categories: dict[str, list[str]] = defaultdict(list)
            for raw in raw_labels:
                entries = mapping.get(raw, [])
                for entry in entries:
                    cat = entry["category"]
                    canon = entry["canonical"]
                    if canon not in label_categories[cat]:
                        label_categories[cat].append(canon)

            # Write original fields + new label_categories
            out = dict(obj)
            out["label_categories"] = dict(label_categories)
            fout.write(json.dumps(out, ensure_ascii=False) + "\n")
            written += 1

    print(f"Written {written} episodes to {CACHE_OUT.name}")


def print_stats(mapping: dict):
    cat_counter: Counter = Counter()
    canon_counter: dict[str, Counter] = defaultdict(Counter)

    for raw, entries in mapping.items():
        for e in entries:
            cat_counter[e["category"]] += 1
            canon_counter[e["category"]][e["canonical"]] += 1

    print("\n── Mapping stats ──────────────────────────────")
    for cat in sorted(cat_counter):
        top = canon_counter[cat].most_common(5)
        print(f"  {cat:12s}  {cat_counter[cat]:4d} unique raw labels  →  {len(canon_counter[cat]):3d} canonical")
        print(f"             top: {', '.join(c for c, _ in top)}")


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--llm", action="store_true", help="Use LLM for unmatched labels (requires API key)")
    parser.add_argument("--no-llm", dest="llm", action="store_false")
    parser.set_defaults(llm=True)
    args = parser.parse_args()

    # Load all labels
    print(f"Loading labels from {CACHE_IN.name}...")
    all_labels = []
    with open(CACHE_IN, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                obj = json.loads(line)
                all_labels.extend(obj.get("labels", []))

    unique_labels = sorted(set(all_labels))
    print(f"Total instances: {len(all_labels)} | Unique: {len(unique_labels)}")

    # Rule-based pass
    print("\nApplying rule-based matching...")
    mapping, unmatched = build_rule_based_mapping(unique_labels)
    matched_pct = 100 * len(mapping) / len(unique_labels) if unique_labels else 0
    print(f"Matched: {len(mapping)} ({matched_pct:.1f}%)  |  Unmatched: {len(unmatched)}")

    # LLM pass for unmatched
    if unmatched and args.llm:
        print(f"\nSending {len(unmatched)} unmatched labels to Haiku...")
        try:
            import anthropic
            client = anthropic.Anthropic()
            llm_mapping = batch_llm_classify(unmatched, client)
            print(f"  LLM returned {len(llm_mapping)} entries")
            mapping.update(llm_mapping)
            print(f"After LLM: {len(mapping)} / {len(unique_labels)} labels mapped")
        except ImportError:
            print("anthropic package not found, skipping LLM pass")
        except Exception as e:
            print(f"LLM pass failed: {e}")
    elif unmatched:
        print(f"\nSkipping LLM pass. {len(unmatched)} labels left as unmatched.")
        for lbl in unmatched:
            mapping[lbl] = [{"category": "other", "canonical": lbl.lower()}]

    # Save normalization mapping
    with open(NORM_OUT, "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)
    print(f"\nSaved mapping → {NORM_OUT.name}")

    print_stats(mapping)

    # Generate enriched cache
    print(f"\nGenerating {CACHE_OUT.name}...")
    apply_mapping_to_cache(mapping)

    # Quick verification
    print("\n── Verification ───────────────────────────────")
    cat_label_counts: dict = defaultdict(Counter)
    with open(CACHE_OUT, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                obj = json.loads(line)
                for cat, labels in obj.get("label_categories", {}).items():
                    for lbl in labels:
                        cat_label_counts[cat][lbl] += 1

    for cat in sorted(cat_label_counts):
        counts = cat_label_counts[cat]
        top5 = counts.most_common(5)
        print(f"  {cat:12s}  {len(counts):3d} unique canonical  top: {', '.join(f'{c}({n})' for c,n in top5)}")


if __name__ == "__main__":
    main()
