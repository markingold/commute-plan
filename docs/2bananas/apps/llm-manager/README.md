<!--
id: APP-LLM-MANAGER
version: 1.2
last_updated: 2026-03-01
title: llm-manager Handbook
purpose:
  Shared guidance for local LLM endpoints and how projects should interact with them.
-->

# llm-manager Handbook

## What it provides
- Local model endpoints (chat / intent / small)
- Centralized switching + symlink management
- Training + LoRA pipeline orchestration
- GPU inspection + job management

## Relevant env keys
See: `docs/2bananas/OPS_GLOBAL_ENV.md`

- `LOCAL_LLM_BASE_URL`
- `LOCAL_LLM_CHAT_COMPLETIONS_URL`
- `LOCAL_LLM_INTENT_BASE_URL`
- `LOCAL_LLM_SMALL_BASE_URL`

## Documentation

- [API Reference](./API.md)
- [CLI Sysop Guide](./CLI_SYSOP_GUIDE.md)

## Integration expectations

- Prefer calling the API rather than editing symlinks directly.
- Log model switches.
- Use health endpoints before and after major changes.
