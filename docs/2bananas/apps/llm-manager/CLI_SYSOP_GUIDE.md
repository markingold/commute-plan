<!--
id: APP-LLM-MANAGER-CLI
version: 1.2
last_updated: 2026-03-01
title: CLI Sysop Guide — LLM Manager
purpose:
  Quick-reference for command-line operations against llm-manager.
  Assumes project root + venv activated.
-->

# CLI Sysop Guide — LLM Manager

All commands assume:

    cd /srv/2bananas/projects/llm-manager
    source venv/bin/activate

---

## 1. Engine Control (systemd)

- Check engines:
  - `sudo systemctl status llm-a llm-b llm-c llm-manager-api`

- Restart chat:
  - `sudo systemctl restart llm-a`

- Stop all:
  - `sudo systemctl stop llm-a llm-b llm-c`

- Solo chat:
  - `sudo systemctl stop llm-b llm-c && sudo systemctl start llm-a`

- Logs:
  - `sudo journalctl -u llm-a -n 100 --no-pager`
  - `sudo journalctl -u llm-manager-api -f`

---

## 2. Model Switching

Preferred via API:

- POST `/switch`
  - Body: `{ "mode": "chat|intent|small", "model_dir": "...", "bounce": true }`

CLI options:

- `python switch_model.py --chat <dir>`
- `python switch_model.py --intent <dir>`

---

## 3. Model Inspection

- `GET /inspect`
- `GET /inspect/<model>`
- `GET /vram`
- `nvidia-smi`

---

## 4. Model Download

Located under:
- `app/src/llm_manager/`

Common scripts:
- `download_models.py`
- `download_convert_chat_model.py`

---

## 5. LoRA Training Pipeline

Primary entry:
- `python main.py --pipeline`

Individual steps:
- `train_lora.py`
- `merge_lora.py`
- `convert_lora.py`

Dual GPU uses `accelerate`.

---

## 6. Training Jobs via API

- `POST /jobs`
- `GET /jobs`
- `POST /jobs/<id>/cancel`

---

## 7. Health & Diagnostics

- `GET /health`
- `GET /system`
- `GET /engines/status`
- `GET /models`
- `GET /knobs`

---

## 8. File Locations

| What | Path |
|------|------|
| API server | `api/server.py` |
| CLI tools | `app/src/llm_manager/` |
| Config | `secrets/.env` |
| Model configs | `model_configs.json` |
| Training data | `data/*_prompts.jsonl` |
| Models dir | `/srv/2bananas/engines/models/` |
| Systemd units | `/etc/systemd/system/llm-{a,b,c}.service` |
| API unit | `/etc/systemd/system/llm-manager-api.service` |
