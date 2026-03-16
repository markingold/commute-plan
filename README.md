# commute-plan

Local-first commute planning app for weather-aware walk/drive decisions, comfort feedback logging, and a local web dashboard.

## What it is

- Python backend for forecast fetch, planning, notifier, and comfort API.
- Discord DM integrations for outbound plans and feedback logging.
- Local PHP dashboard for planner runs, config edits, and comfort history.

## Quick start

```bash
cd /srv/2bananas/projects/commute-plan
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
```

Create secrets file at `secrets/.env` and config at `secrets/commute_config.toml` (copy from `config/commute_config.example.toml`).

Run quick verification:

```bash
venv/bin/python -m pytest -q tests/contract/test_health.py
scripts/smoke.sh
```

## Logs

- Service logs: stdout JSON (journald/systemd-friendly).
- Script logs: `logs/` directory (cron wrappers append there).
- Logging standard guide: `docs/guides/G-20-LOGGING-CHECKS.md`

## Documentation

- Full project handbook: `docs/README.md`
- Standardization plan/status: `docs/3-part-plan.md`
- Project guides index: `docs/guides/G-00-INDEX.md`
