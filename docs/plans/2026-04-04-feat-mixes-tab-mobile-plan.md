---
title: "feat: Mixes Tab — Mobile Bottom Navigation"
type: feat
status: completed
date: 2026-04-04
origin: docs/brainstorms/2026-04-04-mixes-tab-mobile-brainstorm.md
---

# feat: Mixes Tab — Mobile Bottom Navigation

## Overview

Pridať tretiu záložku **"Mixes"** do mobile bottom tab baru. Tab zobrazí kompaktný zoznam mixov (najnovší → najstarší). Po kliknutí na riadok sa zobrazí detail mixu s tlačidlom "← Back". Desktop sa nemení.

## Problem Statement

Na mobile je sidebar skrytý — používateľ nemá žiadny priamy prístup k zoznamu podcastov. Jediný spôsob ako nájsť mix je cez Explore filtre. Mixes tab doplní prirodzenú list→detail navigáciu typickú pre mobilné aplikácie.

(see brainstorm: docs/brainstorms/2026-04-04-mixes-tab-mobile-brainstorm.md)

---

## Acceptance Criteria

- [x] Bottom tab bar má 3 záložky: Mixes | Genre Map | Explore
- [x] Záložka Mixes zobrazuje scrollovateľný zoznam mixov od najnovšieho po najstarší
- [x] Každý riadok: `RA.1032 · Fcukers · 29 Mar` (číslo + artist + dátum)
- [x] Klik na riadok → zobrazia sa detaily mixu (reuse `showEpisodeDetail()`)
- [x] Detail obsahuje tlačidlo "← Back" → vráti na zoznam (NIE do bottom sheet)
- [x] Mixes tab je viditeľná len na mobile (`@media max-width: 768px`)
- [x] Desktop zostáva nezmenený
- [x] `switchTab('mixes')` skryje `graphArea` a `labelFilterArea`, zobrazí `mixesArea`

---

## Implementation Plan

### 1. HTML — `#mobileTabBar` (pridať 1 button)

Súbor: `ra_genre_network.html`, riadok ~1285

Pridať **pred** existujúci `<button data-view="graph">` (Mixes má byť prvá záložka):

```html
<button class="mobile-tab" data-view="mixes">
  <svg viewBox="0 0 24 24">
    <!-- list icon: 3 horizontálne čiary -->
    <line x1="4" y1="6" x2="20" y2="6"/>
    <line x1="4" y1="12" x2="20" y2="12"/>
    <line x1="4" y1="18" x2="20" y2="18"/>
  </svg>
  <span>Mixes</span>
</button>
```

Výsledok tab baru:
```
│ 🎵 Mixes │ 🗺 Genre Map │ 🔍 Explore │
```

### 2. HTML — `#mixesArea` (nový div v `.center-panel`)

Súbor: `ra_genre_network.html`, riadok ~1264 (za `#labelFilterArea`)

```html
<div id="mixesArea" style="display:none">
  <div id="mixesList"></div>
  <div id="mixesDetail" style="display:none"></div>
</div>
```

### 3. CSS — nové štýly (pridať do `@media (max-width: 768px)` bloku)

```css
/* Mixes area — full height scrollable */
#mixesArea {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

#mixesList {
  flex: 1;
  overflow-y: auto;
  padding: 8px 0;
}

/* Kompaktný riadok mixu */
.mix-row {
  display: flex;
  align-items: center;
  padding: 12px 18px;
  cursor: pointer;
  border-bottom: 1px solid var(--glass-border);
  transition: background 0.15s;
}
.mix-row:active {
  background: rgba(255, 45, 120, 0.08);
}
.mix-row-num {
  font-family: var(--font-data);
  font-size: 10px;
  color: var(--neon-pink);
  min-width: 52px;
  flex-shrink: 0;
}
.mix-row-artist {
  flex: 1;
  font-size: 13px;
  color: var(--text-bright);
  font-weight: 400;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-right: 8px;
}
.mix-row-date {
  font-family: var(--font-data);
  font-size: 10px;
  color: var(--text-dim);
  white-space: nowrap;
  flex-shrink: 0;
}

/* Detail view s Back headerom */
#mixesDetail {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.mixes-detail-header {
  display: flex;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--glass-border);
  background: var(--glass);
  flex-shrink: 0;
}
.mixes-back-btn {
  background: none;
  border: none;
  color: var(--neon-pink);
  font-family: var(--font-display);
  font-size: 13px;
  cursor: pointer;
  padding: 4px 0;
  display: flex;
  align-items: center;
  gap: 6px;
}
.mixes-detail-content {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
}
```

### 4. JavaScript — `switchTab()` rozšíriť

Súbor: `ra_genre_network.html`, riadok ~1839

```javascript
function switchTab(view) {
  document.querySelectorAll('.center-tab').forEach(t => t.classList.toggle('active', t.dataset.view === view));
  document.querySelectorAll('.mobile-tab').forEach(t => t.classList.toggle('active', t.dataset.view === view));
  document.getElementById('graphArea').style.display = view === 'graph' ? '' : 'none';
  document.getElementById('labelFilterArea').style.display = view === 'labels' ? '' : 'none';
  document.getElementById('mixesArea').style.display = view === 'mixes' ? '' : 'none';  // NEW
  if (view === 'labels') renderFilterPanel();
  if (view === 'graph') setTimeout(resizeGraph, 100);
  if (view === 'mixes') renderMixesList();  // NEW
}
```

### 5. JavaScript — `renderMixesList()`

```javascript
function renderMixesList() {
  const list = document.getElementById('mixesList');
  if (!list) return;

  // Zoradiť MIXES od najnovšieho po najstarší
  const sorted = [...MIXES].sort((a, b) => {
    if (!a.date) return 1;
    if (!b.date) return -1;
    return b.date.localeCompare(a.date);
  });

  list.innerHTML = sorted.map(m => {
    const num = `RA.${m.mix_number.padStart(3, '0')}`;
    const date = m.date ? formatMixDate(m.date) : '';
    return `<div class="mix-row" data-id="${m.id}">
      <span class="mix-row-num">${num}</span>
      <span class="mix-row-artist">${m.artist}</span>
      <span class="mix-row-date">${date}</span>
    </div>`;
  }).join('');

  list.querySelectorAll('.mix-row').forEach(row => {
    row.addEventListener('click', () => {
      const mix = mixMap.get(row.dataset.id);
      if (mix) showMixesDetail(mix);
    });
  });
}

function formatMixDate(dateStr) {
  // dateStr je vo formáte "YYYY-MM-DD"
  const d = new Date(dateStr);
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
}
```

### 6. JavaScript — `showMixesDetail()` a `backToMixesList()`

```javascript
function showMixesDetail(mix) {
  const mixesList = document.getElementById('mixesList');
  const mixesDetail = document.getElementById('mixesDetail');

  mixesList.style.display = 'none';
  mixesDetail.style.display = 'flex';

  mixesDetail.innerHTML = `
    <div class="mixes-detail-header">
      <button class="mixes-back-btn" onclick="backToMixesList()">
        ← Back
      </button>
    </div>
    <div class="mixes-detail-content" id="mixesDetailContent"></div>
  `;

  // Reuse existujúceho showEpisodeDetail — ale zobraziť content do mixesDetailContent
  // Priamo naplníme content rovnako ako showEpisodeDetail, bez bottom sheet
  const container = document.getElementById('mixesDetailContent');
  // Zavolaj selectEpisode ktorý naplní detailContent — potom skopíruj html
  selectEpisode(mix);
  // Počkaj kým sa naplní detailContent, potom skopíruj do mixesDetailContent
  requestAnimationFrame(() => {
    container.innerHTML = document.getElementById('detailContent').innerHTML;
    // Zatvoriť bottom sheet detail panel (nechceme ho na mobile keď sme v Mixes)
    detailPanel.classList.add('collapsed');
    document.getElementById('graphSearch')?.classList.remove('hidden-by-panel');
  });
}

function backToMixesList() {
  const mixesList = document.getElementById('mixesList');
  const mixesDetail = document.getElementById('mixesDetail');
  mixesDetail.style.display = 'none';
  mixesList.style.display = '';
}
```

**Poznámka k implementácii detailu:** `selectEpisode()` aj `showEpisodeDetail()` sú existujúce funkcie, ktoré plnia `#detailContent` a otvárajú bottom sheet panel. Na Mixes tab nechceme bottom sheet — preto po `selectEpisode()` skryjeme `detailPanel` a skopírujeme vyrenderovaný HTML do `#mixesDetailContent`. Alternatíva: priamo zavolať `showEpisodeDetail()` a obsah skopírovať.

---

## Key Files

| Súbor | Čo sa mení |
|---|---|
| `ra_genre_network.html` | HTML + CSS + JS — jeden súbor, všetky zmeny tu |

Konkrétne miesta:
- `ra_genre_network.html:1285` — `#mobileTabBar` → pridať Mixes button
- `ra_genre_network.html:1272` → pridať `#mixesArea` div
- `ra_genre_network.html:1073` (koniec `<style>`) → pridať nové CSS štýly
- `ra_genre_network.html:1839` — `switchTab()` → pridať `mixesArea` toggle
- `ra_genre_network.html:1859` (po mobile tab listeneroch) → pridať `renderMixesList()`, `showMixesDetail()`, `backToMixesList()`

---

## Edge Cases

- **Prázdny dátum:** `formatMixDate()` vracia `''` ak `m.date` chýba — riadok funguje aj bez dátumu
- **Back button + bottom sheet:** `showMixesDetail()` zatvorí `detailPanel` aby sa neprekrýval
- **Tab switch počas detail view:** Ak user prepne tab kým je otvorený mix detail, `renderMixesList()` sa znova zavolá a zoznam sa zobrazí (nie detail)

---

## Sources

- **Origin brainstorm:** [docs/brainstorms/2026-04-04-mixes-tab-mobile-brainstorm.md](docs/brainstorms/2026-04-04-mixes-tab-mobile-brainstorm.md)
  - Kľúčové rozhodnutia: kompaktný riadok, in-tab navigácia, len mobile
- Existujúce vzory: `ra_genre_network.html:1839` (`switchTab`), `ra_genre_network.html:166` (`.ep-item` štýl), `ra_genre_network.html:1869` (`selectEpisode`)
