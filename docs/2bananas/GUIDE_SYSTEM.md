<!--
id: GUIDE-SYSTEM
version: 1.2
last_updated: 2026-03-01
title: Guides system (2bananas)
purpose:
  A predictable format for small, composable guides that work across projects and are easy for an LLM to read.
-->
# Guides system (2bananas)

## Where guides live
- Ecosystem-wide guides: `docs/2bananas/guides/`
- Project-specific guides: `<project>/docs/guides/`

## File naming
- `G-00-INDEX.md` for an index
- `G-##-SLUG.md` for guides (e.g. `G-10-PORTS.md`, `G-20-DB-SCHEMA.md`)

## Guide header (machine-friendly)
Each guide begins with a short header block:

- `id` (stable)
- `version`
- `last_updated` (YYYY-MM-DD)
- `title`
- `purpose`
- optional: `applies_to` (paths, language, project types)
- optional: `related` (links to other guides/docs)

## Content pattern (keep it short)
- Purpose
- When to use
- Steps (commands/examples)
- Pitfalls / gotchas
- Links

## Linking rule
- Every guide should link back to `G-00-INDEX`.
- Index should link out to standards/ops docs where relevant.
