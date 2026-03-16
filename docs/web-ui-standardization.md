# Commute Plan — Web UI Standardization

## Status Update (2026-03-16)

Implemented from this plan so far:

- Added 2bananas token layer aliases (`--2b-*`) in `web/styles.css` while preserving current visual style.
- Added initial 2b component compatibility classes (`2b-card`, `2b-chip`, `2b-badge`, `2b-tab`).
- Extracted inline tab-switching JavaScript from `web/index.php` into `web/app.js`.
- Added `web/lab.meta.json` metadata file.
- Added a header lab navigation affordance (`← Lab`) in `web/index.php`.

Remaining UI standardization can proceed incrementally without disrupting existing UX polish.

> Part of the [2bananas Web UI Standardization Plan](../../docs/web-ui-standardization-plan.md).
> This document started as a plan and now includes implementation status updates.

---

## Current State Audit

- **Stack:** PHP (single monolithic `index.php` — 1,644 lines) + external CSS
- **CSS approach:** External `styles.css` with extensive CSS custom properties
- **Theme:** Dark only
- **Accent color:** `#38bdf8` (sky blue)
- **Layout:** Centered single-column max `1120px`. Outer shell with gradient border + inner panel. CSS Grid 2-column for cards. Tab nav for sections.
- **Navigation:** Tab buttons (Planner, Config GUI, Config Raw, Feedback) with pill-shaped tabs, animated transitions
- **Components:** Cards with `radial-gradient` `::before` overlay, status pills with animated dots, chip badges, tab panels, comfort emoji displays, SQLite data viewing
- **Typography:** `system-ui, -apple-system, BlinkMacSystemFont, "SF Pro Text", sans-serif`
- **Responsive:** `@media (max-width: 960px)` collapses grid to single column
- **Notable:** Highly polished design with `backdrop-filter`, `radial-gradient` overlays, animated status dots with `box-shadow` glow, pill-shaped UI elements throughout. Comfort feedback system with emoji mapping. 405-line CSS file.

### Current Color Palette

| Token | Value |
|---|---|
| `--bg` | `#050712` |
| `--bg-elevated` | `#0f172a` |
| `--accent` | `#38bdf8` |
| `--accent2` | `#22c55e` |
| `--text-main` | `#e5e7eb` |
| `--text-muted` | `#9ca3af` |
| `--error` | `#fca5a5` |
| `--success` | `#bbf7d0` |

---

## Token Mapping

| Current Variable | Standard Variable |
|---|---|
| `--bg` | `--2b-bg` |
| `--bg-elevated` | `--2b-bg-elevated` |
| `--accent` | `--2b-accent` |
| `--accent2` | `--2b-ok` (or keep as project-specific) |
| `--text-main` | `--2b-text` |
| `--text-muted` | `--2b-text-muted` |
| `--error` | `--2b-error` |
| `--success` | `--2b-ok` |

---

## Migration Steps

1. **CSS tokens**: Replace `--bg`, `--bg-elevated`, `--accent`, `--accent2`, `--text-main`, `--text-muted`, `--error`, `--success` with `--2b-*` equivalents.

2. **Accent**: `--2b-accent: #38bdf8;` (default sky-blue, no override needed).

3. **Header**: Already has a polished top area. Restructure to use the standard `2b-header` pattern. Add "← Lab" link.

4. **Tabs**: Replace custom tab CSS with `2b-tab` classes. Preserve the pill-tab aesthetic:
   ```css
   .2b-tab {
     border-radius: var(--2b-radius-pill);
     /* rest from standard */
   }
   ```

5. **Cards**: Replace gradient-overlay cards with `2b-card` + optional `radial-gradient` overlay as a project-specific enhancement on top.

6. **Status pills**: Replace animated dots with `2b-badge` + `2b-status-dot`:
   ```css
   .2b-status-dot {
     width: 8px; height: 8px;
     border-radius: 50%;
     background: var(--2b-ok);
     animation: 2b-pulse 2s infinite;
   }
   ```

7. **Chips**: Replace custom chips with `2b-chip` class.

8. **Breakpoint**: Already at 960px — keep as-is. Already compliant.

9. **`lab.meta.json`**: Create `web/lab.meta.json`:
   ```json
   {
     "title": "Commute Plan",
     "description": "Transit commute planner with comfort tracking and feedback.",
     "category": "app",
     "tags": ["php", "sqlite", "transit"],
     "healthPath": "/health",
     "accent": "#38bdf8"
   }
   ```

---

## Estimated Effort

**Small-Medium** — already well-organized with variables. Mostly renaming. The polished animations and gradient overlays can be kept as project-specific enhancements on top of the standard base.

## Phase

**Phase 4** (Week 4-5) — Variable-based projects.

---

## Design System Reference

See the full [2b-tokens.css reference](../../docs/web-ui-standardization-plan.md#1-design-system-shared-tokens--variables) for the complete token set, and the [component library](../../docs/web-ui-standardization-plan.md#5-component-library-cards-badges-buttons-tables) for standard CSS classes.
