# 3-Part Plan: Commute-Plan Standardization

<!--
id: COMMUTE-PLAN-3-PART-PLAN
version: 1.0
last_updated: 2026-03-16
title: Commute-Plan Standardization 3-Part Plan
purpose:
	Compare existing implementation vs project notes/2bananas standards, define
	remaining work, and propose branch strategy for safe execution.
-->

## Scope and Inputs Reviewed

This report is based on the following artifacts:

- `.github/copilot-instructions.md`
- `docs/web-ui-standardization.md`
- `docs/STANDARDIZATION.md`
- `docs/logging-audit.md`
- `docs/2bananas/STANDARDS_PROJECT_LAYOUT.md`
- `docs/2bananas/STANDARDS_LOGGING.md`
- `docs/2bananas/STANDARDS_DOCS.md`
- `docs/2bananas/GUIDE_SYSTEM.md`
- `docs/2bananas/OPS_GLOBAL_ENV.md`
- `docs/2bananas/OPS_SERVICES.md`
- `docs/2bananas/OPS_PORTS.md`

Code and ops surface sampled:

- `app/src/*` (API, CLI, bot, notifier, config, weather, comfort modules)
- `web/index.php`, `web/styles.css`
- `scripts/commute_morning.sh`, `scripts/commute_evening.sh`, `scripts/discord_feedback_bot.sh`
- `config/settings.example.env`
- `requirements.txt`

---

## Part 1: What Is Already Done vs. What Is Not

### A. Already Done (or mostly done)

#### 1) Project layout is mostly aligned with 2bananas structure

Present and correctly separated:

- `app/`, `config/`, `data/`, `docs/`, `logs/`, `scripts/`, `secrets/`, `web/`
- Secrets are outside `web/`
- DB/data are outside `web/`
- Env template exists in `config/settings.example.env`

Assessment: strong baseline alignment with `STANDARDS_PROJECT_LAYOUT.md`.

#### 2) Basic health endpoint exists

`app/src/comfort_api_server.py` currently implements:

- `GET /health`
- `POST /comfort-log`

Assessment: health endpoint exists, but contract is only partial (see gaps).

#### 3) Web UI already externalized CSS and is polished

Current web state:

- Main styling in `web/styles.css` (not all inline)
- Responsive breakpoint present
- Organized card/tab architecture
- UX polish already above typical MVP dashboards

Assessment: design quality is strong; migration can preserve visual identity while standardizing tokens/components.

#### 4) Runtime wrapper scripts exist for cron/service-style runs

Present wrappers:

- `scripts/commute_morning.sh`
- `scripts/commute_evening.sh`
- `scripts/discord_feedback_bot.sh`

Assessment: good operational starting point.

#### 5) Some standard env keys already present in template

In `config/settings.example.env`:

- `APP_NAME`, `APP_ENV`, `APP_VERSION`
- `LOG_LEVEL`, `LOG_DEST`
- `OPENWEATHER_API_KEY`, `DISCORD_*`

Assessment: partially aligned; missing/renaming items remain.

---

### B. Not Done Yet / Needs Rework

#### 1) Logging standardization is not implemented yet

Current code still uses many `print()` statements across core modules:

- API, CLI, bot, notifier, weather, config loader, helpers

Missing per `STANDARDS_LOGGING.md` + `logging-audit.md`:

- Structured JSON logs
- Shared logging setup module
- Required fields (`ts`, `level`, `msg`, `project/project_id`, `component`)
- HTTP fields (`request_id`, `method`, `path`, `status`, `duration_ms`)
- `X-Request-Id` accept/generate/echo behavior

Also missing dependency:

- `structlog` not in `requirements.txt`

Status: major gap.

#### 2) Health contract is incomplete

Current `/health` payload in `comfort_api_server.py` returns only:

- `ok`
- `service`

Still missing from standardization notes:

- `version`
- `time` (ISO)
- `uptime_s` (or agreed equivalent)
- `GET /version`

Status: medium gap.

#### 3) Testing foundation is missing

No `tests/` directory and no CI workflow files detected.

Still needed:

- contract test(s) for health endpoint
- smoke script for local/system-level verification

Status: major reliability gap.

#### 4) Web standard token/component migration is not started

Current CSS uses custom tokens (`--bg`, `--accent`, etc.) and no `--2b-*` naming.

Still needed from `web-ui-standardization.md`:

- map/replace to `--2b-*`
- add standardized component class layer (`2b-card`, `2b-chip`, tabs/header conventions)
- add `web/lab.meta.json`

Also noted:

- inline JS block still exists in `web/index.php` (tab switch function)

Status: medium gap (design is good, standard naming/framework not yet applied).

#### 5) Env naming consistency is incomplete

Current vs target highlights:

- `TIMEZONE` used; standardization plan suggests migration to `TZ`
- `LOG_FORMAT` not present in template
- `WEATHER_JSON` in example points to smart_assistant path, while project appears self-contained under `data/`

Status: medium gap + potential confusion risk.

#### 6) Existing standardization docs contain stale assumptions

Observed mismatch examples:

- `docs/STANDARDIZATION.md` references route set (`/api/commute`, etc.) not matching current API surface (`/health`, `/comfort-log`)
- logging and CLI task lists partially reflect older architecture assumptions

Status: documentation alignment gap (needs reconciliation before execution).

#### 7) Git branch state cannot currently be audited from this workspace

From project path, git commands report: not a git repository.

Implication:

- cannot verify existing local/remote branches from current working copy
- branch merge plan must include an initial git-recovery/validation gate

Status: blocker for branch-level execution, not blocker for planning.

---

### C. Net Assessment

The project has strong functional and UI foundations, but ecosystem consistency is blocked by three core deficits:

1. Logging not standardized
2. Test contract/smoke coverage absent
3. Documentation and branch hygiene drifted from current reality

---

## Part 2: Execution Plan (Logical Order to "Kick It Up a Notch")

This order is intentionally dependency-safe: each phase reduces risk for the next.

### Phase 0: Preconditions and Truth Baseline (No behavior changes)

Goals:

- restore/confirm git metadata and branch visibility
- reconcile stale docs to current architecture before coding
- define acceptance checklist for each phase

Deliverables:

- confirmed branch inventory (or documented recovery path)
- updated baseline section in this plan if assumptions change
- implementation checklist approved by owner

### Phase 1: Logging Foundation (Highest leverage first)

Goals:

- add shared logging setup (`app/src/logging_setup.py`)
- introduce structured logs with required baseline fields
- remove ad-hoc `print()` from high-impact runtime paths first

Suggested sequence:

1. API server (`comfort_api_server.py`)
2. notifier + CLI (`notifier.py`, `cli.py`)
3. Discord bot/client (`discord_feedback_bot.py`, `discord_client.py`)
4. remaining helpers/modules

Acceptance criteria:

- each component logs JSON to stdout
- no secret/token values logged
- API request logs include method/path/status/duration and request ID behavior

### Phase 2: Health + Contract Testing

Goals:

- finalize `/health` payload contract
- add `/version` endpoint (or documented equivalent)
- add minimum contract test and smoke test script

Acceptance criteria:

- deterministic health/version responses
- tests runnable locally in one command
- smoke script validates service start + health response

### Phase 3: Env and Config Standardization

Goals:

- normalize env names to ecosystem conventions
- preserve backward compatibility where needed during migration window
- clean up template/examples to avoid cross-project path confusion

High-priority env items:

- add `LOG_FORMAT`
- implement `TZ` support (with temporary fallback from `TIMEZONE`)
- align path defaults to this project (`data/...`)

Acceptance criteria:

- settings template matches actual runtime behavior
- migration notes documented for any renamed keys

### Phase 4: Web UI Standardization (Preserve look, align tokens/components)

Goals:

- map existing design to `--2b-*` token names
- migrate shared component naming while preserving current visual quality
- externalize remaining inline JS into a dedicated web asset
- add `web/lab.meta.json`

Acceptance criteria:

- visual parity (or intentional improvement) on desktop + mobile
- token/component naming aligned with ecosystem standards
- dashboard metadata present for ecosystem indexing/ops

### Phase 5: Documentation and Guides Finalization

Goals:

- align docs with actual implementation state
- ensure behavior-change docs are updated as each phase lands
- add project guide artifacts under docs/guides as needed

Suggested docs outputs:

- `docs/README.md` updates for run/log/test conventions
- `docs/guides/G-00-INDEX.md`
- short operational guides for cron/service validation and troubleshooting

Acceptance criteria:

- no stale route/feature docs
- clear "how to run / how to verify" instructions

---

## Part 3: Branch and Merge Strategy

## Current State Constraint

This workspace copy does not currently expose `.git` metadata, so branch inventory/merge cannot be executed from here yet.

Therefore, branch handling starts with a mandatory gate.

### Gate A: Restore Branch Visibility

Actions:

1. Confirm canonical repo location for commute-plan.
2. Ensure working directory has valid `.git` metadata.
3. Fetch all remotes and list active branches.
4. Produce a one-time branch triage sheet:
	 - merge now
	 - cherry-pick selectively
	 - archive/close

Output:

- "Branch Triage Note" appended to this file after git visibility is restored.

Branch Triage Note (2026-03-16):

- Repository was initialized as a new git repo in this workspace.
- Remote configured: https://github.com/markingold/commute-plan.git
- Baseline branch renamed to `main`.
- Active implementation branch created per approved naming: `chore/standardize-logging-foundation`.
- No legacy local branches existed in this workspace at triage time (new repo baseline).

### Gate B: Merge Existing Work into Main (Stabilize baseline)

Principles:

- merge only branches that are coherent, tested, and non-conflicting with this plan
- prefer small merges in priority order (docs/infra before behavior-heavy changes)

Recommended order:

1. docs-only branches
2. low-risk infra/config branches
3. runtime behavior branches

If large divergence exists:

- use one short-lived integration branch from `main` to reconcile and test before final merge

### Gate C: Future Branches for This Standardization Program

Use one branch per phase/concern (keeps PRs reviewable and reversible):

1. `chore/standardize-logging-foundation`
2. `feat/health-contract-and-tests`
3. `chore/env-key-alignment`
4. `feat/web-ui-2b-standardization`
5. `docs/standardization-closeout`

Integration policy:

- each branch rebased/merged from latest `main` before PR
- each PR includes:
	- scope statement
	- validation steps run
	- docs updated list

### PR/merge quality gates (required)

- smoke checks pass
- new/updated tests pass (where phase includes tests)
- no secret exposure in logs
- docs updated for any behavior changes

---

## Proposed Work Cadence

If approved, execution cadence should be:

1. Phase 0 + Gate A/B (repo truth + branch cleanup)
2. Phases 1-2 (logging + health/test contracts)
3. Phase 3 (env migration)
4. Phase 4 (web token/component migration)
5. Phase 5 (docs and closeout)

This sequence minimizes rework and prevents styling/documentation work from being invalidated by later backend changes.

---

## Approval Checklist

Please confirm:

1. Proceed with this phase order as written.
2. Proceed with Gate A git recovery/branch triage before implementation.
3. Approve per-phase branch naming strategy.
4. Approve documentation-first reconciliation where existing docs are stale.

Once approved, implementation can begin phase-by-phase with PR-sized changes.
