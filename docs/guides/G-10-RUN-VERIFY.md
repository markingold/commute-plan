<!--
id: G-10-RUN-VERIFY
version: 1.0
last_updated: 2026-03-16
title: Run and Verify
purpose:
  Repeatable local verification for commute-plan runtime, contract tests, and smoke checks.
related:
  - docs/guides/G-00-INDEX.md
  - tests/contract/test_health.py
  - scripts/smoke.sh
-->
# Run and Verify

## When to use

- After pulling changes.
- Before opening a PR.
- After changing API, logging, scripts, or env handling.

## Steps

1. Install dependencies:

```bash
cd /srv/2bananas/projects/commute-plan
venv/bin/pip install -r requirements.txt -r requirements-dev.txt
```

2. Compile-check Python modules:

```bash
venv/bin/python -m compileall app/src
```

3. Run contract tests:

```bash
venv/bin/python -m pytest -q tests/contract/test_health.py
```

4. Run smoke check:

```bash
scripts/smoke.sh
```

## Pitfalls

- If smoke fails immediately, verify `structlog` is installed in the same venv used by scripts.
- If `/health` or `/version` tests fail, verify no stale API process is already bound to the port.
