// ── Embedded Data (injected by build_network_html.py) ───────────────────────
const GRAPH_NODES = window.__RA_DATA__.nodes;
const GRAPH_EDGES = window.__RA_DATA__.edges;
const MIXES = window.__RA_DATA__.mixes;

// ── Lookups ─────────────────────────────────────────────────────────────────
const nodeMap = new Map(GRAPH_NODES.map(n => [n.id, n]));
const mixMap = new Map(MIXES.map(m => [m.id, m]));

// Adjacency: genre → set of neighbor genres
const adjacency = new Map();
GRAPH_EDGES.forEach(e => {
  if (!adjacency.has(e.source)) adjacency.set(e.source, new Set());
  if (!adjacency.has(e.target)) adjacency.set(e.target, new Set());
  adjacency.get(e.source).add(e.target);
  adjacency.get(e.target).add(e.source);
});

const maxWeight = Math.max(...GRAPH_EDGES.map(e => e.weight));
const maxCount = Math.max(...GRAPH_NODES.map(n => n.count));
function nodeRadius(count) { return 4 + 18 * Math.sqrt(count / maxCount); }


// ── Episode List ────────────────────────────────────────────────────────────
const episodeList = document.getElementById('episodeList');
const searchInput = document.getElementById('search');
const detailPanel = document.getElementById('detailPanel');
const detailContent = document.getElementById('detailContent');

function renderEpisodeList(filter = '') {
  const lower = filter.toLowerCase();
  episodeList.innerHTML = '';
  MIXES.forEach(m => {
    if (filter && !m.artist.toLowerCase().includes(lower) &&
        !m.id.includes(filter)) return;
    const div = document.createElement('div');
    div.className = 'ep-item';
    div.dataset.id = m.id;
    div.innerHTML = `<span class="ep-num">RA.${m.mix_number.padStart(3,'0')}</span>${m.artist}`;
    div.addEventListener('click', () => selectEpisode(m));
    episodeList.appendChild(div);
  });
}

function renderEpisodeListByGenres(genreSet) {
  episodeList.innerHTML = '';
  MIXES.forEach(m => {
    if (!m.genres.some(g => genreSet.has(g))) return;
    const div = document.createElement('div');
    div.className = 'ep-item';
    div.dataset.id = m.id;
    div.innerHTML = `<span class="ep-num">RA.${m.mix_number.padStart(3,'0')}</span>${m.artist}`;
    div.addEventListener('click', () => selectEpisode(m));
    episodeList.appendChild(div);
  });
}

const searchClear = document.getElementById('searchClear');
searchInput.addEventListener('input', e => {
  searchClear.style.display = e.target.value ? 'block' : 'none';
  renderEpisodeList(e.target.value);
});
if (searchClear) {
  searchClear.addEventListener('click', () => {
    searchInput.value = '';
    searchClear.style.display = 'none';
    renderEpisodeList('');
    searchInput.focus();
  });
}
renderEpisodeList();

// ── Label & Genre Filter Panel ─────────────────────────────────────────────
const CAT_ORDER = ['mood','setting','era','energy','geography','vibe','style'];
const CAT_ORDER_MOBILE = ['mood','setting','energy','geography','vibe','era'];
const CAT_NAMES = { mood:'Mood', energy:'Energy', vibe:'Vibe', style:'Style', geography:'Geography', setting:'Setting', era:'Era' };
const CAT_GROUPS = [
  ['mood', 'energy', 'vibe'],
  ['geography', 'setting', 'style'],
  ['era'],
];
const DEFAULT_SHOW = 80;

// Precompute label counts per category
const LABEL_COUNTS = {};
CAT_ORDER.forEach(cat => { LABEL_COUNTS[cat] = {}; });
MIXES.forEach(m => {
  if (!m.label_categories) return;
  CAT_ORDER.forEach(cat => {
    (m.label_categories[cat] || []).forEach(l => {
      LABEL_COUNTS[cat][l] = (LABEL_COUNTS[cat][l] || 0) + 1;
    });
  });
});

// Precompute RA keyword counts
const KW_COUNTS = {};
MIXES.forEach(m => {
  if (!m.keywords) return;
  m.keywords.split(',').map(k => k.trim()).filter(Boolean).forEach(k => {
    KW_COUNTS[k] = (KW_COUNTS[k] || 0) + 1;
  });
});

// Precompute genre counts
const GENRE_COUNTS = {};
MIXES.forEach(m => {
  (m.genres || []).forEach(g => {
    GENRE_COUNTS[g] = (GENRE_COUNTS[g] || 0) + 1;
  });
});
const SORTED_GENRES = Object.entries(GENRE_COUNTS).sort((a, b) => b[1] - a[1]);

let activeFilters = [];  // [{category, label}]  category='genre' for genres
let expandedCats = new Set();

function getFilteredMixes() {
  if (activeFilters.length === 0) return MIXES;
  return MIXES.filter(m => {
    const cats = m.label_categories || {};
    return activeFilters.every(f => {
      if (f.category === 'genre') return (m.genres || []).includes(f.label);
      if (f.category === '__kw__') return m.keywords ? m.keywords.split(',').map(k => k.trim()).includes(f.label) : false;
      return (cats[f.category] || []).includes(f.label);
    });
  });
}

function computeFilteredCounts(filteredMixes) {
  const labelCounts = {};
  CAT_ORDER.forEach(cat => { labelCounts[cat] = {}; });
  const genreCounts = {};
  const kwCounts = {};
  filteredMixes.forEach(m => {
    if (m.label_categories) {
      CAT_ORDER.forEach(cat => {
        (m.label_categories[cat] || []).forEach(l => {
          labelCounts[cat][l] = (labelCounts[cat][l] || 0) + 1;
        });
      });
    }
    (m.genres || []).forEach(g => {
      genreCounts[g] = (genreCounts[g] || 0) + 1;
    });
    if (m.keywords) {
      m.keywords.split(',').map(k => k.trim()).filter(Boolean).forEach(k => {
        kwCounts[k] = (kwCounts[k] || 0) + 1;
      });
    }
  });
  return { labelCounts, genreCounts, kwCounts };
}

function chipFontSize(count) {
  return Math.round(9 + Math.log2(Math.max(count, 1)) * 1.1);
}

function renderGenreFilterSection() {
  const container = document.getElementById('genreFilterSection');
  container.innerHTML = '';

  const filteredMixes = getFilteredMixes();
  const displayCounts = activeFilters.length > 0
    ? computeFilteredCounts(filteredMixes).genreCounts
    : GENRE_COUNTS;

  let entries = Object.entries(displayCounts).sort((a, b) => b[1] - a[1]);
  if (labelSearchQuery) entries = entries.filter(([g]) => g.toLowerCase().includes(labelSearchQuery));
  if (!entries.length) return;

  const expanded = expandedCats.has('genre');
  const visible = expanded ? entries : entries.slice(0, 30);
  const hasMore = entries.length > 30;

  const title = document.createElement('div');
  title.className = 'genre-filter-title';
  title.textContent = `Genres (${entries.length})`;
  container.appendChild(title);

  const items = document.createElement('div');
  items.className = 'genre-filter-items';

  visible.forEach(([genre, count]) => {
    const chip = document.createElement('span');
    chip.className = 'genre-filter-chip';
    const node = nodeMap.get(genre);
    const color = node ? node.color : '#666';
    chip.style.background = color;
    chip.style.fontSize = chipFontSize(count) + 'px';
    chip.innerHTML = `${genre}<span class="chip-count">${count}</span>`;
    if (activeFilters.some(f => f.category === 'genre' && f.label === genre)) {
      chip.classList.add('selected');
    }
    chip.addEventListener('click', () => toggleLabelFilter('genre', genre));
    const desc = node && node.description ? node.description : '';
    if (desc) {
      chip.addEventListener('mouseenter', (e) => {
        const tt = document.getElementById('tooltip');
        tt.innerHTML = `<div class="tt-title">${genre}</div><div class="tt-desc">${desc}</div>`;
        tt.classList.add('has-desc');
        tt.style.display = 'block';
        requestAnimationFrame(() => positionTooltip(e));
      });
      chip.addEventListener('mousemove', (e) => positionTooltip(e));
      chip.addEventListener('mouseleave', () => {
        const tt = document.getElementById('tooltip');
        tt.style.display = 'none';
        tt.classList.remove('has-desc');
      });
    }
    items.appendChild(chip);
  });

  container.appendChild(items);

  if (hasMore) {
    const btn = document.createElement('button');
    btn.className = 'show-more-btn';
    btn.textContent = expanded ? 'Show less' : `Show all ${entries.length}`;
    btn.addEventListener('click', () => {
      if (expanded) expandedCats.delete('genre');
      else expandedCats.add('genre');
      renderFilterPanel();
    });
    container.appendChild(btn);
  }
}

function renderLabelMasonry() {
  const container = document.getElementById('labelMasonry');
  container.innerHTML = '';

  // Create 3 columns
  const col1 = document.createElement('div');
  col1.className = 'label-column';
  const col2 = document.createElement('div');
  col2.className = 'label-column';
  const col3 = document.createElement('div');
  col3.className = 'label-column';

  // On mobile: single column with CAT_ORDER_MOBILE; on desktop: 3 columns with CAT_ORDER
  const isMobile = window.innerWidth <= 768;
  const effectiveCatOrder = isMobile ? CAT_ORDER_MOBILE : CAT_ORDER;

  let columnMap;
  if (isMobile) {
    // Single column on mobile
    columnMap = {};
    CAT_ORDER_MOBILE.forEach(cat => { columnMap[cat] = col1; });
  } else {
    // 3 columns on desktop
    columnMap = {
      mood: col1, setting: col1, era: col1,
      energy: col2, geography: col2,
      vibe: col3, style: col3
    };
  }

  const filteredMixes = getFilteredMixes();
  const displayCounts = activeFilters.length > 0
    ? computeFilteredCounts(filteredMixes).labelCounts
    : LABEL_COUNTS;

  // Render categories into their assigned columns
  effectiveCatOrder.forEach(cat => {
      let entries = Object.entries(displayCounts[cat] || {})
        .sort((a, b) => b[1] - a[1]);
      if (labelSearchQuery) entries = entries.filter(([l]) => l.toLowerCase().includes(labelSearchQuery));
      if (!entries.length) return;

      const expanded = expandedCats.has(cat);
      const visible = expanded ? entries : entries.slice(0, DEFAULT_SHOW);
      const hasMore = entries.length > DEFAULT_SHOW;

      const section = document.createElement('div');
      section.className = 'label-cat-section';
      section.setAttribute('data-cat', cat);

      const title = document.createElement('div');
      title.className = 'label-cat-title';
      title.textContent = `${CAT_NAMES[cat]} (${entries.length})`;
      section.appendChild(title);

      const items = document.createElement('div');
      items.className = 'label-cat-items';

      visible.forEach(([label, count]) => {
        const chip = document.createElement('span');
        chip.className = 'filter-label-chip label-chip';
        chip.setAttribute('data-cat', cat);
        chip.style.fontSize = chipFontSize(count) + 'px';
        chip.innerHTML = `${label}<span class="chip-count">${count}</span>`;
        if (activeFilters.some(f => f.category === cat && f.label === label)) {
          chip.classList.add('selected');
        }
        chip.addEventListener('click', () => toggleLabelFilter(cat, label));
        items.appendChild(chip);
      });

      section.appendChild(items);

      if (hasMore) {
        const btn = document.createElement('button');
        btn.className = 'show-more-btn';
        btn.textContent = expanded ? 'Show less' : `Show all ${entries.length}`;
        btn.addEventListener('click', () => {
          if (expanded) expandedCats.delete(cat);
          else expandedCats.add(cat);
          renderFilterPanel();
        });
        section.appendChild(btn);
      }

      columnMap[cat].appendChild(section);
  });

  // RA Tags section → col1
  const displayKwCounts = activeFilters.length > 0
    ? computeFilteredCounts(filteredMixes).kwCounts
    : KW_COUNTS;
  let kwEntries = Object.entries(displayKwCounts).sort((a, b) => b[1] - a[1]);
  if (labelSearchQuery) kwEntries = kwEntries.filter(([k]) => k.toLowerCase().includes(labelSearchQuery));
  if (kwEntries.length > 0) {
    const expanded = expandedCats.has('__kw__');
    const visible = expanded ? kwEntries : kwEntries.slice(0, DEFAULT_SHOW);
    const hasMore = kwEntries.length > DEFAULT_SHOW;

    const section = document.createElement('div');
    section.className = 'label-cat-section';
    section.setAttribute('data-cat', '__kw__');

    const title = document.createElement('div');
    title.className = 'label-cat-title';
    title.textContent = `RA Tags (${kwEntries.length})`;
    section.appendChild(title);

    const items = document.createElement('div');
    items.className = 'label-cat-items';

    visible.forEach(([kw, count]) => {
      const chip = document.createElement('span');
      chip.className = 'filter-label-chip label-chip';
      chip.setAttribute('data-cat', '__kw__');
      chip.style.fontSize = chipFontSize(count) + 'px';
      chip.innerHTML = `${kw}<span class="chip-count">${count}</span>`;
      if (activeFilters.some(f => f.category === '__kw__' && f.label === kw)) {
        chip.classList.add('selected');
      }
      chip.addEventListener('click', () => toggleLabelFilter('__kw__', kw));
      items.appendChild(chip);
    });

    section.appendChild(items);

    if (hasMore) {
      const btn = document.createElement('button');
      btn.className = 'show-more-btn';
      btn.textContent = expanded ? 'Show less' : `Show all ${kwEntries.length}`;
      btn.addEventListener('click', () => {
        if (expanded) expandedCats.delete('__kw__');
        else expandedCats.add('__kw__');
        renderFilterPanel();
      });
      section.appendChild(btn);
    }

    col1.appendChild(section);
  }

  container.appendChild(col1);
  container.appendChild(col2);
  container.appendChild(col3);
}

let labelSearchQuery = '';

function renderFilterPanel() {
  renderGenreFilterSection();
  renderLabelMasonry();
}

// Label search input
const labelSearchInput = document.getElementById('labelSearch');
const labelSearchClear = document.getElementById('labelSearchClear');
if (labelSearchInput) {
  labelSearchInput.addEventListener('input', (e) => {
    labelSearchQuery = e.target.value.toLowerCase();
    labelSearchClear.style.display = labelSearchQuery ? 'block' : 'none';
    renderFilterPanel();
  });
}
if (labelSearchClear) {
  labelSearchClear.addEventListener('click', () => {
    labelSearchInput.value = '';
    labelSearchQuery = '';
    labelSearchClear.style.display = 'none';
    renderFilterPanel();
    labelSearchInput.focus();
  });
}

function renderActiveFilters() {
  const container = document.getElementById('activeFilters');
  container.innerHTML = '';
  if (activeFilters.length === 0) return;

  activeFilters.forEach((f, idx) => {
    const chip = document.createElement('span');
    if (f.category === 'genre') {
      chip.className = 'active-filter-chip genre-chip';
      const node = nodeMap.get(f.label);
      chip.style.background = node ? node.color : '#666';
    } else {
      chip.className = 'active-filter-chip label-chip';
      chip.setAttribute('data-cat', f.category);
    }
    chip.innerHTML = `${f.label} <span class="remove" data-idx="${idx}">&times;</span>`;
    chip.querySelector('.remove').addEventListener('click', (e) => {
      e.stopPropagation();
      activeFilters.splice(idx, 1);
      onFiltersChanged();
    });
    container.appendChild(chip);
  });

  // Match count
  const count = document.createElement('span');
  count.className = 'filter-match-count';
  const matchCount = getFilteredMixes().length;
  count.textContent = `${matchCount} mix${matchCount !== 1 ? 'es' : ''}`;
  container.appendChild(count);

  // Clear all
  const clear = document.createElement('button');
  clear.className = 'clear-filters-btn';
  clear.textContent = 'Clear all';
  clear.addEventListener('click', clearAllFilters);
  container.appendChild(clear);
}

function toggleLabelFilter(cat, label) {
  const idx = activeFilters.findIndex(f => f.category === cat && f.label === label);
  if (idx >= 0) {
    activeFilters.splice(idx, 1);
  } else {
    activeFilters.push({ category: cat, label: label });
  }
  onFiltersChanged();
}

function onFiltersChanged() {
  renderActiveFilters();
  renderFilterPanel();
  applyLabelFilters();
}

function applyLabelFilters() {
  if (activeFilters.length === 0) {
    // Collapse detail panel when no filters
    detailPanel.classList.add('collapsed');
    return;
  }

  const filtered = getFilteredMixes();
  detailHistory = [{ type: 'filters' }];

  // Show filtered mixes in right detail panel (like genre detail)
  detailPanel.classList.remove('collapsed');
  document.getElementById('graphSearch')?.classList.add('hidden-by-panel');

  const filterDesc = activeFilters.map(f => f.label).join(' + ');
  const epList = filtered.slice(0, 50).map(m =>
    `<div class="track-item" style="cursor:pointer" onclick="selectEpisode(mixMap.get('${m.id}'))">` +
    `<span class="track-num">${m.mix_number}</span>` +
    `<span class="track-artist">${m.artist}</span></div>`
  ).join('');

  detailContent.innerHTML = `
    <div style="position:relative">
      <button class="detail-close" onclick="clearAllFilters()">Close</button>
      <div class="detail-header">
        <div class="ep-title">Label Filter</div>
        <div class="ep-artist">${filterDesc}</div>
        <div class="detail-meta">
          <div class="meta-item"><span class="meta-val">${filtered.length} episodes</span></div>
        </div>
      </div>
    </div>
    <div class="tracklist-section">
      <div class="tracklist-header">Episodes (${filtered.length})</div>
      ${epList}
      ${filtered.length > 50 ? '<div class="no-tracklist">...and ' + (filtered.length - 50) + ' more</div>' : ''}
    </div>
  `;

  detailPanel.scrollTop = 0;
}

function clearAllFilters() {
  activeFilters = [];
  expandedCats.clear();
  labelSearchQuery = '';
  if (labelSearchInput) labelSearchInput.value = '';
  onFiltersChanged();
}

function showLabelMixes(cat, label) {
  detailHistory = [{ type: 'label', cat: cat, label: label }];
  // Find all mixes with this label in this category
  const matches = MIXES.filter(m => {
    const cats = m.label_categories || {};
    return (cats[cat] || []).includes(label);
  });

  detailPanel.classList.remove('collapsed');
  document.getElementById('graphSearch')?.classList.add('hidden-by-panel');

  const epList = matches.slice(0, 50).map(m =>
    `<div class="track-item" style="cursor:pointer" onclick="selectEpisode(mixMap.get('${m.id}'))">` +
    `<span class="track-num">${m.mix_number}</span>` +
    `<span class="track-artist">${m.artist}</span></div>`
  ).join('');

  detailContent.innerHTML = `
    <div style="position:relative">
      <button class="detail-close" onclick="clearSelection()">Close</button>
      <div class="detail-header">
        <div class="ep-title"><span class="label-chip" data-cat="${cat}">${label}</span></div>
        <div class="detail-meta">
          <div class="meta-item"><span class="meta-val">${matches.length} episodes</span></div>
        </div>
      </div>
    </div>
    <div class="tracklist-section">
      <div class="tracklist-header">Episodes (${matches.length})</div>
      ${epList}
      ${matches.length > 50 ? '<div class="no-tracklist">...and ' + (matches.length - 50) + ' more</div>' : ''}
    </div>
  `;

  detailPanel.scrollTop = 0;
}

// Tab switching (unified for desktop + mobile)
function switchTab(view) {
  document.querySelectorAll('.center-tab').forEach(t => t.classList.toggle('active', t.dataset.view === view));
  document.querySelectorAll('.mobile-tab').forEach(t => t.classList.toggle('active', t.dataset.view === view));
  document.getElementById('graphArea').style.display = view === 'graph' ? '' : 'none';
  document.getElementById('labelFilterArea').style.display = view === 'labels' ? '' : 'none';
  const mixesArea = document.getElementById('mixesArea');
  if (mixesArea) mixesArea.classList.toggle('active-view', view === 'mixes');
  if (view === 'labels') renderFilterPanel();
  if (view === 'graph') setTimeout(resizeGraph, 100);
  if (view === 'mixes') renderMixesList();
}

document.querySelectorAll('.center-tab').forEach(tab => {
  tab.addEventListener('click', () => switchTab(tab.dataset.view));
});

// Mobile tab bar switching
document.querySelectorAll('.mobile-tab').forEach(tab => {
  tab.addEventListener('click', () => switchTab(tab.dataset.view));
});

// ── Selection State ─────────────────────────────────────────────────────────
let highlightedNodes = new Set();
let directGenres = new Set();
let highlightedEdges = new Set();
let activeFilter = 'all';
let selectedMixId = null;
let detailHistory = [];  // navigation stack for detail panel

function selectEpisode(mix) {
  // Toggle: if already selected, clear
  if (selectedMixId === mix.id) {
    clearSelection();
    return;
  }
  selectedMixId = mix.id;

  // Active state in list
  episodeList.querySelectorAll('.ep-item').forEach(el => {
    el.classList.toggle('active', el.dataset.id === mix.id);
  });

  // Highlight direct genres + their neighbors
  directGenres = new Set(mix.genres);
  highlightedNodes = new Set(mix.genres);
  // Add neighbors of direct genres
  mix.genres.forEach(g => {
    const neighbors = adjacency.get(g);
    if (neighbors) neighbors.forEach(n => highlightedNodes.add(n));
  });

  highlightedEdges = new Set();
  GRAPH_EDGES.forEach((e, i) => {
    if (highlightedNodes.has(e.source) && highlightedNodes.has(e.target)) {
      highlightedEdges.add(i);
    }
  });

  // Build detail panel
  showEpisodeDetail(mix);
  updateVisuals();
}

function showEpisodeDetail(mix) {
  if (detailHistory.length > 0) {
    detailHistory.push({ type: 'episode', id: mix.id });
  }
  detailPanel.classList.remove('collapsed');
  document.getElementById('graphSearch')?.classList.add('hidden-by-panel');

  const dur = mix.duration || '';
  const chips = mix.genres.map(g => {
    const node = nodeMap.get(g);
    const color = node ? node.color : '#666';
    return `<span class="genre-chip" style="background:${color}" onclick="selectGenreNode('${g}')">${g}</span>`;
  }).join('');

  // Keywords chips
  const kwHtml = mix.keywords ? mix.keywords.split(',').map(k => k.trim()).filter(Boolean)
    .map(k => `<span class="kw-chip">${k}</span>`).join('') : '';

  // Labels chips — use label_categories if available, else fall back to flat labels
  let labelsHtml = '';
  if (mix.label_categories && Object.keys(mix.label_categories).length > 0) {
    const chips = [];
    // Render in category order, skip 'other'
    CAT_ORDER.forEach(cat => {
      const items = mix.label_categories[cat];
      if (items && items.length) {
        items.forEach(l => chips.push(`<span class="label-chip" data-cat="${cat}" style="cursor:pointer" onclick="showLabelMixes('${cat}','${l.replace(/'/g, "\\\\'")}')">${l}</span>`));
      }
    });
    labelsHtml = chips.join('');
  } else if (mix.labels && mix.labels.length) {
    labelsHtml = mix.labels.map(l => `<span class="label-chip">${l}</span>`).join('');
  }

  // Links
  const links = [];
  if (mix.streamingUrl) links.push(`<a href="#" onclick="event.preventDefault(); playMix(mixMap.get('${mix.id}'))" class="detail-link">Listen</a>`);
  if (mix.url) links.push(`<a href="${mix.url}" target="_blank" rel="noopener noreferrer" class="detail-link">RA page</a>`);
  if (mix.artist_id) links.push(`<a href="https://ra.co/dj/${mix.artist_id}" target="_blank" rel="noopener noreferrer" class="detail-link">Artist</a>`);
  const linksHtml = links.length ? `<div class="detail-links">${links.join('')}</div>` : '';

  // Tracklist
  let tracklistHtml = '';
  if (mix.tracks && mix.tracks.length > 0) {
    const tracks = mix.tracks.map((t, i) => {
      const num = `<span class="track-num">${i + 1}</span>`;
      const artist = t.artist ? `<span class="track-artist">${t.artist}</span> ` : '';
      const title = t.title ? `<span class="track-title">${artist ? '- ' : ''}${t.title}</span>` : '';
      const label = t.label ? ` <span class="track-label">[${t.label}]</span>` : '';
      return `<div class="track-item">${num}${artist}${title}${label}</div>`;
    }).join('');
    tracklistHtml = `
      <div class="tracklist-header">Tracklist (${mix.tracks.length})</div>
      ${tracks}`;
  } else {
    tracklistHtml = '<div class="no-tracklist">No tracklist available</div>';
  }

  const hasHistory = detailHistory.length > 1;
  detailContent.innerHTML = `
    ${mix.imageUrl ? `<div class="detail-cover"><img src="${mix.imageUrl}" alt="${mix.artist}"></div>` : ''}
    <div style="position:relative">
      <button class="detail-close" onclick="${hasHistory ? 'goBack()' : 'clearSelection()'}">${hasHistory ? '\u2190 Back' : 'Close'}</button>
      <div class="detail-header">
        <div class="ep-title">RA.${mix.mix_number.padStart(3,'0')}</div>
        <div class="ep-artist">${mix.artist}</div>
        <div class="detail-meta">
          ${mix.date ? `<div class="meta-item"><span class="meta-val">${mix.date}</span></div>` : ''}
          ${dur ? `<div class="meta-item"><span class="meta-val">${dur}</span></div>` : ''}
          <div class="meta-item"><span class="meta-val">${mix.tracks ? mix.tracks.length : 0} tracks</span></div>
        </div>
        ${linksHtml}
        <div class="genre-chips">${chips}</div>
        ${labelsHtml ? `<div class="label-chips">${labelsHtml}</div>` : ''}
        ${kwHtml ? `<div class="kw-chips">${kwHtml}</div>` : ''}
      </div>
    </div>
    ${mix.blurb ? `<div class="detail-blurb">${mix.blurb}</div>` : ''}
    ${mix.article ? `<div class="detail-section-header">About</div><div class="detail-article">${mix.article}</div>` : ''}
    ${mix.qa ? `<div class="detail-section-header">Q&A</div><div class="detail-article detail-qa">${mix.qa}</div>` : ''}
    ${tracklistHtml}
  `;

  // Scroll to top + resize graph after panel opens
  detailPanel.scrollTop = 0;
  setTimeout(resizeGraph, 250);
}

function showGenreDetail(nodeId, pushHistory = true) {
  if (pushHistory) detailHistory = [{ type: 'genre', id: nodeId }];
  detailPanel.classList.remove('collapsed');
  document.getElementById('graphSearch')?.classList.add('hidden-by-panel');

  const n = nodeMap.get(nodeId);
  const count = n ? (n.count || 0) : 0;
  const family = n ? n.family : '';
  const color = n ? n.color : '#666';
  const desc = n && n.description ? n.description : '';

  // Find episodes with this genre
  const eps = MIXES.filter(m => m.genres.includes(nodeId));

  const epList = eps.slice(0, 50).map(m =>
    `<div class="track-item" style="cursor:pointer" onclick="selectEpisode(mixMap.get('${m.id}'))">` +
    `<span class="track-num">${m.mix_number}</span>` +
    `<span class="track-artist">${m.artist}</span></div>`
  ).join('');

  detailContent.innerHTML = `
    <div style="position:relative">
      <button class="detail-close" onclick="clearSelection()">Close</button>
      <div class="detail-header">
        <div class="ep-title" style="color:${color}">${nodeId}</div>
        <div class="ep-artist">${family}</div>
        <div class="detail-meta">
          <div class="meta-item"><span class="meta-val">${count} episodes</span></div>
        </div>
      </div>
      ${desc ? `<div class="detail-blurb">${desc}</div>` : ''}
    </div>
    <div class="tracklist-section">
      <div class="tracklist-header">Episodes (${eps.length})</div>
      ${epList}
      ${eps.length > 50 ? '<div class="no-tracklist">...and ' + (eps.length - 50) + ' more</div>' : ''}
    </div>
  `;

  setTimeout(resizeGraph, 250);
}

function selectGenreNode(nodeId) {
  directGenres = new Set([nodeId]);
  highlightedNodes = new Set([nodeId]);
  const neighbors = adjacency.get(nodeId);
  if (neighbors) neighbors.forEach(n => highlightedNodes.add(n));

  highlightedEdges = new Set();
  GRAPH_EDGES.forEach((e, i) => {
    if (highlightedNodes.has(e.source) && highlightedNodes.has(e.target)) {
      highlightedEdges.add(i);
    }
  });

  selectedMixId = null;

  // Show genre detail in right panel (don't filter left sidebar)

  showGenreDetail(nodeId);
  updateVisuals();
}

function goBack() {
  detailHistory.pop();  // remove current
  const prev = detailHistory[detailHistory.length - 1];
  if (!prev) { clearSelection(); return; }
  selectedMixId = null;
  if (prev.type === 'genre') {
    showGenreDetail(prev.id, false);
  } else if (prev.type === 'label') {
    showLabelMixes(prev.cat, prev.label);
  } else if (prev.type === 'filters') {
    applyLabelFilters();
  } else {
    clearSelection();
  }
}

function clearSelection() {
  selectedMixId = null;
  detailHistory = [];
  highlightedNodes = new Set();
  directGenres = new Set();
  highlightedEdges = new Set();
  renderEpisodeList(searchInput.value);
  detailPanel.classList.add('collapsed');
  document.getElementById('graphSearch')?.classList.remove('hidden-by-panel');
  detailContent.innerHTML = '<div class="detail-placeholder">Select an episode to see details</div>';
  setTimeout(resizeGraph, 250);
  updateVisuals();
}

function resetApp() {
  // Clear all filters
  activeFilters = [];
  expandedCats.clear();
  labelSearchQuery = '';
  if (labelSearchInput) labelSearchInput.value = '';
  renderActiveFilters();
  renderFilterPanel();

  // Clear selection
  selectedMixId = null;
  highlightedNodes = new Set();
  directGenres = new Set();
  highlightedEdges = new Set();
  updateVisuals();

  // Reset episode list and search
  searchInput.value = '';
  renderEpisodeList();

  // Collapse detail panel
  detailPanel.classList.add('collapsed');
  document.getElementById('graphSearch')?.classList.remove('hidden-by-panel');
  detailContent.innerHTML = '<div class="detail-placeholder">Select an episode to see details</div>';

  // Switch to Network Graph tab
  switchTab('graph');

  setTimeout(resizeGraph, 250);
}

// ── D3 Graph (co-occurrence) ─────────────────────────────────────────────
const svg = d3.select('#graph');
const graphArea = document.getElementById('graphArea');
let width = graphArea.clientWidth;
let height = graphArea.clientHeight;

svg.attr('viewBox', [0, 0, width, height]);

const defs = svg.append('defs');

// Helper: blend two hex colors
function blendColors(c1, c2) {
  const r1 = parseInt(c1.slice(1,3),16), g1 = parseInt(c1.slice(3,5),16), b1 = parseInt(c1.slice(5,7),16);
  const r2 = parseInt(c2.slice(1,3),16), g2 = parseInt(c2.slice(3,5),16), b2 = parseInt(c2.slice(5,7),16);
  const r = Math.round((r1+r2)/2), g = Math.round((g1+g2)/2), b = Math.round((b1+b2)/2);
  return `rgb(${r},${g},${b})`;
}

const gRoot = svg.append('g');

let currentZoomK = 0.9;
const zoom = d3.zoom()
  .scaleExtent([0.2, 5])
  .on('zoom', (event) => {
    gRoot.attr('transform', event.transform);
    currentZoomK = event.transform.k;
    updateSemanticZoom();
  });
svg.call(zoom);

// Family gravity centers — arranged in a ring (hoisted for resizeGraph)
const families = [...new Set(GRAPH_NODES.map(n => n.family))];
const familyColor = {};
families.forEach(f => { familyColor[f] = GRAPH_NODES.find(n => n.family === f)?.color || '#666'; });

const familyCenter = {};

function resizeGraph() {
  width = graphArea.clientWidth;
  height = graphArea.clientHeight;
  svg.attr('viewBox', [0, 0, width, height]);

  // Recenter simulation forces
  const newCx = width / 2, newCy = height / 2;
  simulation.force('center', d3.forceCenter(newCx, newCy).strength(0.03));
  const newRingR = Math.min(width, height) * 0.25;
  families.forEach((f, i) => {
    const angle = (2 * Math.PI * i / families.length) - Math.PI / 2;
    familyCenter[f] = { x: newCx + newRingR * Math.cos(angle), y: newCy + newRingR * Math.sin(angle) };
  });
  simulation.alpha(0.15).restart();
  // Update family district label positions
  if (typeof familyLabels !== 'undefined') {
    familyLabels
      .attr('x', f => familyLabelPos(f).x)
      .attr('y', f => familyLabelPos(f).y);
  }
}

// Prepare simulation data
const simNodes = GRAPH_NODES.map(n => ({ ...n }));
const simEdges = GRAPH_EDGES.map((e, i) => ({ ...e, index: i }));
const cx = width / 2, cy = height / 2;

// Initialize family gravity centers
const ringR = Math.min(width, height) * 0.25;
families.forEach((f, i) => {
  const angle = (2 * Math.PI * i / families.length) - Math.PI / 2;
  familyCenter[f] = { x: cx + ringR * Math.cos(angle), y: cy + ringR * Math.sin(angle) };
});

// Simulation — musicological links + soft family gravity
const simulation = d3.forceSimulation(simNodes)
  .force('link', d3.forceLink(simEdges)
    .id(d => d.id)
    .distance(d => 40 + 100 * (1 - d.weight / maxWeight))
    .strength(d => 0.15 + 0.5 * (d.weight / maxWeight))
  )
  .force('charge', d3.forceManyBody()
    .strength(d => -30 - 100 * Math.sqrt(d.count / maxCount))
  )
  .force('center', d3.forceCenter(cx, cy).strength(0.03))
  .force('familyX', d3.forceX(d => {
    const fc = familyCenter[d.family];
    return fc ? fc.x : cx;
  }).strength(0.08))
  .force('familyY', d3.forceY(d => {
    const fc = familyCenter[d.family];
    return fc ? fc.y : cy;
  }).strength(0.08))
  .force('collide', d3.forceCollide().radius(d => nodeRadius(d.count) + 4))
  .alphaDecay(0.03);

// Family district labels — positioned at familyCenter, behind everything
// Family district labels — pushed outward past the node clusters
const familyLabelG = gRoot.append('g').attr('class', 'family-labels-layer');
function familyLabelPos(f) {
  const fc = familyCenter[f];
  if (!fc) return { x: cx, y: cy };
  // Push 60% further from center
  const dx = fc.x - cx, dy = fc.y - cy;
  return { x: fc.x + dx * 0.6, y: fc.y + dy * 0.6 };
}
const familyLabels = familyLabelG.selectAll('text')
  .data(families)
  .join('text')
  .attr('class', 'family-label')
  .attr('x', f => familyLabelPos(f).x)
  .attr('y', f => familyLabelPos(f).y)
  .attr('fill', f => familyColor[f])
  .attr('opacity', 0.2)
  .attr('font-size', 26)
  .text(f => f);

// Draw edges — color blended from source/target family, brightness scales with strength
const linkG = gRoot.append('g');
const links = linkG.selectAll('line')
  .data(simEdges)
  .join('line')
  .attr('stroke', d => {
    const sc = (nodeMap.get(d.source.id || d.source) || {}).color || '#00e5ff';
    const tc = (nodeMap.get(d.target.id || d.target) || {}).color || '#00e5ff';
    return sc === tc ? sc : blendColors(sc, tc);
  })
  .attr('stroke-width', d => 0.5 + 3.5 * (d.weight / maxWeight))
  .attr('stroke-opacity', d => 0.08 + 0.3 * (d.weight / maxWeight));

// Draw nodes
const nodeG = gRoot.append('g');
const nodeGroups = nodeG.selectAll('g')
  .data(simNodes)
  .join('g')
  .attr('cursor', 'pointer')
  .call(d3.drag()
    .filter(event => event.pointerType === 'mouse')
    .on('start', (event, d) => { if (!event.active) simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
    .on('drag', (event, d) => { d.fx = event.x; d.fy = event.y; })
    .on('end', (event, d) => { if (!event.active) simulation.alphaTarget(0); d.fx = null; d.fy = null; })
  );

// Invisible touch hit area — ensures min 22px radius (44px target) on mobile
nodeGroups.append('circle').attr('class', 'node-hit')
  .attr('r', d => Math.max(22, nodeRadius(d.count) + 6))
  .attr('fill', 'transparent')
  .attr('stroke', 'none');

// Glow circle — intensity scales with node importance
nodeGroups.append('circle').attr('class', 'node-glow')
  .attr('r', d => nodeRadius(d.count) + 6 + 8 * Math.sqrt(d.count / maxCount))
  .attr('fill', d => d.color || '#666')
  .attr('opacity', d => 0.08 + 0.2 * Math.sqrt(d.count / maxCount));

// Idle pulse on top nodes
const idleThreshold = [...simNodes].sort((a,b) => b.count - a.count)[4]?.count || 50;
nodeGroups.each(function(d) {
  if (d.count >= idleThreshold) d3.select(this).select('.node-glow').classed('idle-pulse', true);
});

// Pulse ring
nodeGroups.append('circle').attr('class', 'pulse-ring')
  .attr('r', d => nodeRadius(d.count) + 4)
  .attr('fill', 'none').attr('stroke', '#00e5ff')
  .attr('stroke-opacity', 0).attr('stroke-width', 0);

// Main circle
nodeGroups.append('circle').attr('class', 'node-circle')
  .attr('r', d => nodeRadius(d.count))
  .attr('fill', d => d.color || '#666')
  .attr('opacity', 0.9);

// Labels
nodeGroups.append('text').attr('class', 'node-label')
  .attr('dy', d => nodeRadius(d.count) + 14)
  .attr('font-size', d => d.count > 50 ? 12 : d.count > 10 ? 10 : 8)
  .attr('font-weight', d => d.count > 50 ? 600 : 400)
  .attr('opacity', d => d.count >= 10 ? 0.8 : 0)
  .text(d => d.id);

// Tooltip
const tooltip = document.getElementById('tooltip');
function positionTooltip(event) {
  const tip = document.getElementById('tooltip');
  const tt = tip.getBoundingClientRect();
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  let x = event.clientX + 12;
  let y = event.clientY - 10;
  if (x + tt.width > vw - 8) x = event.clientX - tt.width - 12;
  if (x < 8) x = 8;
  if (y + tt.height > vh - 8) y = event.clientY - tt.height - 10;
  if (y < 8) y = 8;
  tip.style.left = x + 'px';
  tip.style.top = y + 'px';
}
nodeGroups.on('mouseover', function(event, d) {
  d3.select(this).select('.node-label').attr('opacity', 1);
  d3.select(this).select('.node-glow').attr('opacity', 0.4);
  // Brighten family district label
  familyLabels.attr('opacity', f => f === d.family ? 0.45 : 0.08);
  // Build tooltip with top connections
  const neighbors = adjacency.get(d.id);
  let conns = '';
  if (neighbors) {
    const top = GRAPH_EDGES
      .filter(e => e.source.id === d.id || e.target.id === d.id)
      .sort((a, b) => b.weight - a.weight)
      .slice(0, 5)
      .map(e => {
        const other = e.source.id === d.id ? e.target.id : e.source.id;
        return other;
      });
    if (top.length) conns = ' → ' + top.join(', ');
  }
  tooltip.classList.remove('has-desc');
  tooltip.textContent = `${d.id} — ${d.count} mixes${conns}`;
  tooltip.style.display = 'block';
  const ev = event;
  requestAnimationFrame(() => positionTooltip(ev));
})
.on('mousemove', function(event) {
  positionTooltip(event);
})
.on('mouseout', function(event, d) {
  if (!highlightedNodes.has(d.id) && d.count < 10) {
    d3.select(this).select('.node-label').attr('opacity', 0);
  }
  d3.select(this).select('.node-glow').attr('opacity', 0.08 + 0.2 * Math.sqrt(d.count / maxCount));
  familyLabels.attr('opacity', 0.2);
  tooltip.style.display = 'none';
})
.on('click', function(event, d) {
  event.stopPropagation();
  selectGenreNode(d.id);
});

// Clear selection on background click — but NOT after pan/drag
let svgPointerDown = null;
svg.on('pointerdown', (event) => {
  svgPointerDown = { x: event.clientX, y: event.clientY };
});
svg.on('click', (event) => {
  if (svgPointerDown) {
    const dx = Math.abs(event.clientX - svgPointerDown.x);
    const dy = Math.abs(event.clientY - svgPointerDown.y);
    if (dx > 5 || dy > 5) return; // was a drag, not a tap
  }
  clearSelection();
});

// ── Graph Search ──────────────────────────────────────────────
(function() {
  const gsInput = document.getElementById('graphSearchInput');
  const gsClear = document.getElementById('graphSearchClear');
  const gsDropdown = document.getElementById('graphSearchDropdown');
  let gsActiveIdx = -1;

  function gsFilter(q) {
    if (!q) return [];
    const lower = q.toLowerCase();
    return simNodes
      .filter(n => n.id.toLowerCase().includes(lower))
      .sort((a, b) => {
        const aStarts = a.id.toLowerCase().startsWith(lower) ? 0 : 1;
        const bStarts = b.id.toLowerCase().startsWith(lower) ? 0 : 1;
        if (aStarts !== bStarts) return aStarts - bStarts;
        return b.count - a.count;
      })
      .slice(0, 12);
  }

  function gsRender(results) {
    if (!results.length) { gsDropdown.style.display = 'none'; return; }
    gsDropdown.innerHTML = results.map((n, i) =>
      `<div class="graph-search-item${i === gsActiveIdx ? ' active' : ''}" data-id="${n.id}">` +
      `<span class="gs-dot" style="background:${n.color}"></span>` +
      `<span>${n.id}</span>` +
      `<span class="gs-family">${n.family}</span>` +
      `<span class="gs-count">${n.count}</span>` +
      `</div>`
    ).join('');
    gsDropdown.style.display = 'block';
    gsDropdown.querySelectorAll('.graph-search-item').forEach(item => {
      item.addEventListener('click', () => gsSelect(item.dataset.id));
    });
  }

  function gsSelect(nodeId) {
    gsInput.value = '';
    gsClear.style.display = 'none';
    gsDropdown.style.display = 'none';
    gsActiveIdx = -1;
    gsInput.blur();

    // Zoom to node + select
    const node = simNodes.find(n => n.id === nodeId);
    if (node) {
      const svgEl = document.getElementById('graph');
      const w = svgEl.clientWidth;
      const h = svgEl.clientHeight;
      const scale = 2.5;
      const tx = w / 2 - node.x * scale;
      const ty = h / 2 - node.y * scale;
      svg.transition().duration(600).call(
        zoom.transform,
        d3.zoomIdentity.translate(tx, ty).scale(scale)
      );
    }
    setTimeout(() => selectGenreNode(nodeId), 150);
  }

  gsInput.addEventListener('input', () => {
    const q = gsInput.value.trim();
    gsClear.style.display = q ? 'block' : 'none';
    gsActiveIdx = -1;
    gsRender(gsFilter(q));
  });

  gsInput.addEventListener('keydown', (e) => {
    const items = gsDropdown.querySelectorAll('.graph-search-item');
    if (!items.length) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      gsActiveIdx = Math.min(gsActiveIdx + 1, items.length - 1);
      gsRender(gsFilter(gsInput.value.trim()));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      gsActiveIdx = Math.max(gsActiveIdx - 1, 0);
      gsRender(gsFilter(gsInput.value.trim()));
    } else if (e.key === 'Enter' && gsActiveIdx >= 0) {
      e.preventDefault();
      gsSelect(items[gsActiveIdx].dataset.id);
    } else if (e.key === 'Escape') {
      gsDropdown.style.display = 'none';
      gsInput.blur();
    }
  });

  gsClear.addEventListener('click', () => {
    gsInput.value = '';
    gsClear.style.display = 'none';
    gsDropdown.style.display = 'none';
    gsActiveIdx = -1;
    gsInput.focus();
  });

  document.addEventListener('click', (e) => {
    if (!e.target.closest('.graph-search')) gsDropdown.style.display = 'none';
  });
})();

simulation.on('tick', () => {
  links.attr('x1', d => d.source.x).attr('y1', d => d.source.y)
    .attr('x2', d => d.target.x).attr('y2', d => d.target.y);
  nodeGroups.attr('transform', d => `translate(${d.x},${d.y})`);
});

// ── Visual Update ───────────────────────────────────────────────────────────
function updateVisuals() {
  const has = highlightedNodes.size > 0;

  nodeGroups.each(function(d) {
    const el = d3.select(this);
    const isDirect = directGenres.has(d.id);
    const isNeighbor = highlightedNodes.has(d.id);

    const nodeOpacity = !has ? 0.9
      : isDirect ? 1
      : isNeighbor ? 0.4
      : 0.06;
    el.select('.node-circle').attr('opacity', nodeOpacity);
    const defaultGlow = 0.08 + 0.2 * Math.sqrt(d.count / maxCount);
    el.select('.node-glow')
      .attr('opacity', isDirect && has ? 0.5 : has ? 0.03 : defaultGlow);

    el.select('.pulse-ring')
      .classed('pulse', isDirect && has)
      .attr('stroke-opacity', isDirect && has ? 0.8 : 0);
    // Pause idle pulse during highlight
    el.select('.node-glow').classed('idle-pulse', !has && d.count >= idleThreshold);

    const labelOpacity = !has ? (d.count >= 10 ? 1 : 0)
      : isDirect ? 1
      : isNeighbor ? 0.4
      : 0;
    el.select('.node-label').attr('opacity', labelOpacity);
  });

  // Family district labels
  const directFamily = has ? [...directGenres].map(id => nodeMap.get(id)?.family).filter(Boolean) : [];
  familyLabels.attr('opacity', f => {
    if (!has) return 0.2;
    return directFamily.includes(f) ? 0.45 : 0.06;
  });

  if (!has) {
    updateSemanticZoom();
  } else {
    links.attr('stroke-opacity', (d, i) => {
      return highlightedEdges.has(i) ? 0.3 + 0.5 * (d.weight / maxWeight) : 0.02;
    });
  }
}

// ── Semantic Zoom ────────────────────────────────────────────────────────
function updateSemanticZoom() {
  if (highlightedNodes.size > 0) return;

  const k = currentZoomK;
  const isMobile = window.innerWidth <= 768;

  // Labels: threshold drops as you zoom in (mobile-aware thresholds)
  let countThreshold;
  if (isMobile) {
    countThreshold = k < 0.3 ? 999
      : k < 0.5 ? 100
      : k < 0.8 ? 30
      : k < 1.2 ? 8
      : k < 2 ? 3
      : 0;
  } else {
    countThreshold = k < 0.5 ? 999
      : k < 0.8 ? 50
      : k < 1.2 ? 10
      : k < 2 ? 3
      : 0;
  }

  nodeGroups.each(function(d) {
    const show = d.count >= countThreshold;
    d3.select(this).select('.node-label').attr('opacity', show ? 0.8 : 0);
  });

  // Links: opacity grows with zoom
  const linkBoost = Math.max(0.3, Math.min(1.5, k / 1.5));
  links.attr('stroke-opacity', d => (0.08 + 0.25 * (d.weight / maxWeight)) * linkBoost);
}

// ── Player (in detail panel) ─────────────────────────────────────────────
function getEmbedInfo(streamingUrl) {
  if (!streamingUrl) return null;
  if (streamingUrl.includes('soundcloud.com')) {
    const encoded = encodeURIComponent(streamingUrl);
    return {
      type: 'sc',
      url: `https://w.soundcloud.com/player/?url=${encoded}&color=%23e63946&auto_play=true&hide_related=true&show_comments=false&show_user=false&show_reposts=false&show_teaser=false&visual=false`
    };
  }
  if (streamingUrl.includes('mixcloud.com')) {
    const path = new URL(streamingUrl).pathname;
    return {
      type: 'mc',
      url: `https://www.mixcloud.com/widget/iframe/?feed=${encodeURIComponent(path)}&autoplay=1&mini=0&hide_cover=1&light=1`
    };
  }
  return null;
}

let currentlyPlayingMix = null;
function playMix(mix) {
  currentlyPlayingMix = mix;
  window.currentlyPlayingMix = mix;
  const info = getEmbedInfo(mix.streamingUrl);
  const el = document.getElementById('sidebarPlayer');
  if (!info || !el) {
    if (mix.streamingUrl) window.open(mix.streamingUrl, '_blank');
    return;
  }
  el.className = `sidebar-player ${info.type}`;
  el.innerHTML = `<div class="player-info" style="cursor:pointer" onclick="if(currentlyPlayingMix) selectEpisode(currentlyPlayingMix)"><span class="player-ep">RA.${mix.mix_number.padStart(3,'0')}</span> <span class="player-artist">${mix.artist}</span></div>` +
    `<iframe src="${info.url}" allow="autoplay"></iframe>`;
}

// ── Keyboard navigation ──────────────────────────────────────────────────
document.addEventListener('keydown', (e) => {
  if (e.target.tagName === 'INPUT') return; // don't hijack search
  if (e.key !== 'ArrowUp' && e.key !== 'ArrowDown') return;
  if (!selectedMixId) return;

  e.preventDefault();
  const items = Array.from(episodeList.querySelectorAll('.ep-item'));
  if (!items.length) return;

  const currentIdx = items.findIndex(el => el.dataset.id === selectedMixId);
  let nextIdx;
  if (e.key === 'ArrowDown') {
    nextIdx = currentIdx < items.length - 1 ? currentIdx + 1 : currentIdx;
  } else {
    nextIdx = currentIdx > 0 ? currentIdx - 1 : currentIdx;
  }

  if (nextIdx !== currentIdx) {
    const nextId = items[nextIdx].dataset.id;
    const nextMix = mixMap.get(nextId);
    if (nextMix) {
      selectEpisode(nextMix);
      items[nextIdx].scrollIntoView({ block: 'nearest' });
    }
  }
});


// ── Mobile: Mixes Tab ──────────────────────────────────────────────────────
function formatMixDate(dateStr) {
  const d = new Date(dateStr);
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
}

function renderMixesList() {
  const list = document.getElementById('mixesList');
  const detail = document.getElementById('mixesDetail');
  if (!list) return;
  if (detail) detail.style.display = 'none';
  list.style.display = '';

  const sorted = [...MIXES].sort((a, b) => {
    if (!a.date) return 1;
    if (!b.date) return -1;
    return b.date.localeCompare(a.date);
  });

  // Build search box + list
  const searchBoxHtml = `
    <div class="mixes-search-box">
      <input type="text" id="mixesSearchInput" placeholder="Search artist or RA.number..." class="mixes-search-input" />
      <svg class="search-icon" viewBox="0 0 24 24"><circle cx="10" cy="10" r="6"/><line x1="14" y1="14" x2="20" y2="20"/></svg>
    </div>
  `;

  const listHtml = sorted.map(m => {
    const num = `RA.${m.mix_number.padStart(3, '0')}`;
    const date = m.date ? formatMixDate(m.date) : '';
    return `<div class="mix-row" data-id="${m.id}">
      <span class="mix-row-num">${num}</span>
      <span class="mix-row-artist">${m.artist}</span>
      <span class="mix-row-date">${date}</span>
    </div>`;
  }).join('');

  // Set HTML with search box + list
  list.innerHTML = searchBoxHtml + listHtml;

  // Setup search filtering
  const searchInput = document.getElementById('mixesSearchInput');
  if (searchInput) {
    searchInput.addEventListener('input', (e) => {
      const query = e.target.value.toLowerCase();
      list.querySelectorAll('.mix-row').forEach(row => {
        const artist = row.querySelector('.mix-row-artist').textContent.toLowerCase();
        const num = row.querySelector('.mix-row-num').textContent.toLowerCase();
        const matches = artist.includes(query) || num.includes(query);
        row.style.display = matches ? '' : 'none';
      });
    });
  }

  // Setup click handlers
  list.querySelectorAll('.mix-row').forEach(row => {
    row.addEventListener('click', () => {
      const mix = mixMap.get(row.dataset.id);
      if (mix) {
        // On mobile, use detailPanel; on desktop, use mixesDetail
        if (window.innerWidth < 768) {
          selectEpisode(mix);
        } else {
          showMixesDetail(mix);
        }
      }
    });
  });
}

function showMixesDetail(mix) {
  const mixesList = document.getElementById('mixesList');
  let mixesDetail = document.getElementById('mixesDetail');
  const mixesArea = document.getElementById('mixesArea');
  if (!mixesList || !mixesDetail || !mixesArea) return;

  mixesList.style.display = 'none';
  mixesDetail.style.display = '';

  // Reset scroll on parent container
  mixesDetail.scrollTop = 0;

  // Create detail header + content
  const newHTML = `
    <div class="mixes-detail-header">
      <button class="mixes-back-btn" onclick="backToMixesList()">\u2190 Back</button>
    </div>
    <div class="mixes-detail-content"></div>
  `;

  mixesDetail.innerHTML = newHTML;

  // Get the content div
  const container = mixesDetail.querySelector('.mixes-detail-content');

  // Reset scroll again
  mixesDetail.scrollTop = 0;
  // Build the same detail content as showEpisodeDetail
  const dur = mix.duration || '';
  const chips = mix.genres.map(g => {
    const node = nodeMap.get(g);
    const color = node ? node.color : '#666';
    return `<span class="genre-chip" style="background:${color}" onclick="selectGenreNode('${g}')">${g}</span>`;
  }).join('');

  const kwHtml = mix.keywords ? mix.keywords.split(',').map(k => k.trim()).filter(Boolean)
    .map(k => `<span class="kw-chip">${k}</span>`).join('') : '';

  let labelsHtml = '';
  if (mix.label_categories && Object.keys(mix.label_categories).length > 0) {
    const lchips = [];
    CAT_ORDER.forEach(cat => {
      const items = mix.label_categories[cat];
      if (items && items.length) {
        items.forEach(l => lchips.push(`<span class="label-chip" data-cat="${cat}" style="cursor:pointer" onclick="showLabelMixes('${cat}','${l.replace(/'/g, "\\\\'")}' )">${l}</span>`));
      }
    });
    labelsHtml = lchips.join('');
  }

  const links = [];
  if (mix.streamingUrl) links.push(`<a href="${mix.streamingUrl}" target="_blank" rel="noopener" class="detail-link">Listen</a>`);
  if (mix.url) links.push(`<a href="${mix.url}" target="_blank" rel="noopener noreferrer" class="detail-link">RA page</a>`);
  if (mix.artist_id) links.push(`<a href="https://ra.co/dj/${mix.artist_id}" target="_blank" rel="noopener noreferrer" class="detail-link">Artist</a>`);
  const linksHtml = links.length ? `<div class="detail-links">${links.join('')}</div>` : '';

  let tracklistHtml = '';
  if (mix.tracks && mix.tracks.length > 0) {
    const tracks = mix.tracks.map((t, i) => {
      const num = `<span class="track-num">${i + 1}</span>`;
      const artist = t.artist ? `<span class="track-artist">${t.artist}</span> ` : '';
      const title = t.title ? `<span class="track-title">${artist ? '- ' : ''}${t.title}</span>` : '';
      const label = t.label ? ` <span class="track-label">[${t.label}]</span>` : '';
      return `<div class="track-item">${num}${artist}${title}${label}</div>`;
    }).join('');
    tracklistHtml = `<div class="tracklist-header">Tracklist (${mix.tracks.length})</div>${tracks}`;
  } else {
    tracklistHtml = '<div class="no-tracklist">No tracklist available</div>';
  }

  container.innerHTML = `
    ${mix.imageUrl ? `<div class="detail-cover"><img src="${mix.imageUrl}" alt="${mix.artist}"></div>` : ''}
    <div class="detail-header" style="padding: 16px">
      <div class="ep-title">RA.${mix.mix_number.padStart(3,'0')}</div>
      <div class="ep-artist">${mix.artist}</div>
      <div class="detail-meta">
        ${mix.date ? `<div class="meta-item"><span class="meta-val">${mix.date}</span></div>` : ''}
        ${dur ? `<div class="meta-item"><span class="meta-val">${dur}</span></div>` : ''}
        <div class="meta-item"><span class="meta-val">${mix.tracks ? mix.tracks.length : 0} tracks</span></div>
      </div>
      ${linksHtml}
      <div class="genre-chips">${chips}</div>
      ${labelsHtml ? `<div class="label-chips">${labelsHtml}</div>` : ''}
      ${kwHtml ? `<div class="kw-chips">${kwHtml}</div>` : ''}
    </div>
    ${mix.blurb ? `<div class="detail-blurb">${mix.blurb}</div>` : ''}
    ${mix.article ? `<div class="detail-section-header">About</div><div class="detail-article">${mix.article}</div>` : ''}
    ${mix.qa ? `<div class="detail-section-header">Q&A</div><div class="detail-article detail-qa">${mix.qa}</div>` : ''}
    ${tracklistHtml}
  `;

}

function backToMixesList() {
  const mixesList = document.getElementById('mixesList');
  const mixesDetail = document.getElementById('mixesDetail');
  if (mixesList) mixesList.style.display = '';
  if (mixesDetail) mixesDetail.style.display = 'none';
}

// ── Mobile: Sheet handle swipe to expand/collapse ──────────────────────────
(function() {
  const handle = detailPanel.querySelector('.sheet-handle');
  if (!handle) return;
  let startY = 0;
  handle.addEventListener('touchstart', (e) => {
    startY = e.touches[0].clientY;
  });
  handle.addEventListener('touchmove', (e) => {
    e.preventDefault();
  });
  handle.addEventListener('touchend', (e) => {
    const endY = e.changedTouches[0].clientY;
    const dy = startY - endY;
    if (dy > 40) {
      // Swipe up → expand
      detailPanel.classList.add('expanded');
    } else if (dy < -40) {
      // Swipe down → collapse or close
      if (detailPanel.classList.contains('expanded')) {
        detailPanel.classList.remove('expanded');
      } else {
        clearSelection();
      }
    }
  });
})();

// ── Mobile: open streaming URL directly instead of embed ───────────────────
(function() {
  const origPlayMix = playMix;
  playMix = function(mix) {
    if (window.innerWidth <= 768) {
      if (mix.streamingUrl) window.open(mix.streamingUrl, '_blank');
      return;
    }
    origPlayMix(mix);
  };
})();

// Expose functions needed by inline onclick handlers (Parcel bundles in module scope)
window.goBack = goBack;
window.clearSelection = clearSelection;
window.clearAllFilters = clearAllFilters;
window.selectGenreNode = selectGenreNode;
window.showLabelMixes = showLabelMixes;
window.selectEpisode = selectEpisode;
window.playMix = playMix;
window.backToMixesList = backToMixesList;
window.resetApp = resetApp;
window.mixMap = mixMap;
