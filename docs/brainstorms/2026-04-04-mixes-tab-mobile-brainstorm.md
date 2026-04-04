# Brainstorm: Mixes Tab — Mobile Bottom Navigation

**Date:** 2026-04-04
**Status:** Ready for planning

---

## What We're Building

Nová záložka **"Mixes"** v mobile bottom tab bare. Celková navigácia na mobile bude mať 3 záložky:

```
┌─────────────────────────────┐
│   [content area]            │
├─────────────────────────────┤
│ 🎵 Mixes │ 🗺 Map │ 🔍 Explore │
└─────────────────────────────┘
```

**Záložka Mixes:**
- Zoznam všetkých mixov, zoradenych od najnovšieho po najstarší
- Kompaktný riadok: číslo (RA.1032) + Artist + dátum
- Po kliknutí → detail mixu (full-screen v rámci Mixes tab)
- Detail má tlačidlo "← Back" na návrat do zoznamu

---

## Why This Approach

Desktop má sidebar so zoznamom mixov stále viditeľný. Na mobile je sidebar skrytý — používateľ nemá prístup k zoznamu. Mixes tab túto medzeru vypĺňa prirodzeným mobile-native spôsobom (list → detail navigácia).

---

## Key Decisions

| Rozhodnutie | Voľba | Dôvod |
|---|---|---|
| Row design | Kompaktný (číslo + artist + dátum) | Viac mixov naraz viditeľných |
| Detail navigácia | In-tab (Back button) | Nestratiť kontext záložky |
| Zoradenie | Najnovší → najstarší | Prirodzené pre obsah feed |
| Desktop | Záložka skrytá | Sidebar existuje, zbytočná duplicita |
| Search v Mixes tab | Nie (v1) | YAGNI — Explore tab má filtre |

---

## Resolved Questions

- **Row design:** Kompaktný riadok (RA.1032 + Artist + dátum) ✅
- **Detail zobrazenie:** Nový in-tab view s Back tlačidlom (nie bottom sheet) ✅
- **Desktop:** Mixes tab sa zobrazuje len na mobile ✅

---

## Implementation Scope

**HTML changes:**
- Pridať `<button class="mobile-tab" data-view="mixes">` do `#mobileTabBar`
- Pridať `<div id="mixesArea">` do `.center-panel`

**CSS changes:**
- `.mixes-list` — scrollovateľný zoznam, full height
- `.mixes-row` — kompaktný riadok (číslo, artist, dátum)
- `.mixes-detail` — detail view s Back headerom
- Zobraziť/skryť len na `@media (max-width: 768px)`

**JS changes:**
- `switchTab('mixes')` — rozšíriť existujúcu funkciu
- `renderMixesList()` — vyrenderovať zoznam z `MIXES` array, zoradený podľa dátumu
- `showMixDetail(mix)` / `backToMixesList()` — navigácia v rámci tab
