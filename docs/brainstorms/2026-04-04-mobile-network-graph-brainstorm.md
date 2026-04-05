---
name: Mobile Interactive Network Graph
description: Transform Genre Map from decorative to interactive D3 visualization on mobile with touch gestures and fullscreen viewport
type: project
---

# Mobile Interactive Network Graph

**Date:** 2026-04-04  
**Context:** Genre Map tab on mobile is currently decorative (opacity 0.4, non-interactive). Exploring how to make it a functional, touch-enabled visualization.

## What We're Building

A **touch-optimized D3 force graph** for mobile that:
- Occupies fullscreen-ish viewport (primary focus)
- Responds to touch gestures: pinch-zoom, tap-to-select, drag-to-pan
- Maintains force simulation behavior (organic node movement)
- Opens detail panel via bottom-sheet when tapping a genre node
- Works seamlessly with existing mobile navigation (bottom tab bar)

## Why This Approach

**Prístup 1: Touch-Optimized Force Graph** was selected because:
- Minimal departure from current D3 codebase
- Intuitive on mobile (gesture vocabulary is familiar)
- Preserves "big picture" genre relationships
- Easier to iterate on than radical redesigns (Hierarchical browser, Radial hub)

## Key Decisions

### Viewport & Layout
- **Size**: Fullscreen-ish (e.g., full mobile screen height minus tab bar)
- **Position**: Genre Map tab → replaces decorative static version
- **Detail panel integration**: Bottom-sheet pattern (tap node → panel slides up)
- **Search box**: Keep accessible (search still visible or move to top-right corner)

### Touch Gestures
- **Tap on node**: Select genre → highlight node + neighbors → open detail panel
- **Pinch gesture**: Zoom in/out on graph
- **Drag on background**: Pan the camera/scene (optional, test with users)
- **Double-tap** (stretch): Center & zoom on selected node (optional, lower priority)
- **Node dragging**: NOT implemented (force simulation handles layout)

### Force Simulation
- Reuse existing force simulation (no changes to physics)
- Continuous movement acceptable on mobile (visual interest, organic feel)
- Performance tuning may be needed (reduce node count for mobile? → defer to testing)

### Visual & Interaction States
- **Node selection**: Glow intensity increases, neighbors highlighted
- **Detail panel open**: Graph dims slightly OR stays bright (test which feels better)
- **Safe area**: Respect `env(safe-area-inset-top)` for notch devices
- **Touch targets**: Nodes must be ≥44px diameter or have larger tap zone (currently OK for large nodes, may need padding for small ones)

## Implementation Scope

### Core Changes (Phase 1)
1. Enable interactivity on mobile (remove `pointer-events: none`, increase opacity from 0.4 → 1.0)
2. Add touch gesture handlers (pinch-zoom, drag-pan via D3)
3. Tap handler: select node → highlight + open detail panel
4. Test viewport sizing (fullscreen-ish) and responsiveness

### Polish (Phase 2, optional)
- Gesture animations (smooth zoom easing)
- Double-tap-to-center
- Performance optimization (if needed)
- UX refinement based on testing

## Open Questions

1. **Search box placement on mobile graph view**: Keep bottom-right corner (might overlap graph at small zoom)? Move to top-right? Hide until toggled?
2. **Graph panning**: Is drag-to-pan necessary, or should users only pinch-zoom? Test with users.
3. **Detail panel interaction**: When detail panel opens, should the graph dim/blur, or stay bright? Affects visual hierarchy.
4. **Performance**: Will fullscreen force graph drain battery on older mobile devices? May need to reduce node count or throttle simulation on mobile.
5. **Tap zone size for small nodes**: Some genres are small nodes. Do we need 44px tap zone padding, or accept smaller targets?

## Success Criteria

- [ ] D3 graph is fully interactive on mobile (no longer decorative)
- [ ] Touch gestures work smoothly (pinch-zoom, tap, drag)
- [ ] Detail panel integrates seamlessly (no accidental overlaps)
- [ ] Performance is acceptable (graph doesn't stutter on mid-range devices)
- [ ] Accessible touch targets (≥44px per iOS HIG, or tested equivalents)
