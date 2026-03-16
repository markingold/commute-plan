<!--
id: STD-LOGGING
version: 1.2
last_updated: 2026-03-01
title: Standards: Logging
purpose:
  Consistent logging conventions across 2bananas projects.
-->
# Standards: Logging

## Goals
- Logs should help you debug quickly.
- Logs should be consistent across projects.
- Never leak secrets.

## Minimum fields
- `ts` (ISO)
- `level`
- `msg` (event name)
- `project` (or `project_id`)
- `component` (api/web/cli/etc.)

## Output
- Prefer stdout for long-running services (journald capture).
- File logs are allowed under `logs/` when useful (JSONL preferred for tailing/parsing).

## HTTP logging (when applicable)
- include: `request_id`, `method`, `path`, `status`, `duration_ms`
- accept `X-Request-Id` header if present; otherwise generate one; echo it in response

## Non-negotiables
- Never log secrets/tokens/keys.
- Log errors with enough context to fix them (but not sensitive data).
