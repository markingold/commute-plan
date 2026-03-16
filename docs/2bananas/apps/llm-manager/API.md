<!--
id: APP-LLM-MANAGER-API
version: 1.2
last_updated: 2026-03-01
title: llm-manager API Reference
purpose:
  Public HTTP surface for llm-manager API server.
  Canonical routes live in api/server.py.
-->

# llm-manager API Reference

## Base URL

- Local: `http://127.0.0.1:8101/`
- Prefer using `LOCAL_LLM_BASE_URL` when available.

## Core Endpoints

### Health
- `GET /health`

### Model Switching
- `POST /switch`
  - `{ mode, model_dir, bounce }`

### Model Inspection
- `GET /inspect`
- `GET /inspect/<model_dir>`
- `GET /vram`

### Engine Status
- `GET /engines/status`
- `GET /engines/chat/logs?lines=50`

### Models
- `GET /models`

### Knobs (.env-backed settings)
- `GET /knobs`
- `POST /knobs`

### Jobs
- `POST /jobs`
- `GET /jobs`
- `GET /jobs/<id>`
- `POST /jobs/<id>/cancel`

### Test Endpoints
- `GET /test-chat?q=...`
- `GET /test-intent?q=...`

## Notes

- If routes change, update this file in the same PR.
- Prefer switching models via API rather than manual symlink edits.
