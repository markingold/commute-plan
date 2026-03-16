<!--
id: OPS-GLOBAL-ENV
version: 1.2
last_updated: 2026-03-01
title: Global env keys (2bananas)
purpose:
  Document the shared keys that live in /srv/2bananas/secrets/global.env so projects stay consistent.
notes:
  - Do NOT paste secrets into repos; list keys + intent only.
  - Prefer reusing these keys across projects instead of inventing new names.
-->
# Global env keys (2bananas)

## Location
- `/srv/2bananas/secrets/global.env`

## Usage rule
- Projects may read these keys, but should still keep project-specific config in `secrets/.env`.
- Do not commit global.env or any real secrets.

## Key groups (names only; keep values in global.env)

### Local LLM endpoints
- `LOCAL_LLM_BASE_URL`
- `LOCAL_LLM_CHAT_COMPLETIONS_URL`
- `LOCAL_LLM_INTENT_BASE_URL`
- `LOCAL_LLM_SMALL_BASE_URL`

### Core services
- `SMART_ASSISTANT_URL`
- `BANANA_MONITOR_BASE_URL`

### Image / creative tools
- `SD_WEBUI_URL`
- `COMFYUI_URL`

### Ports (shared conventions)
- `SMART_ASSISTANT_PORT`
- `BANANA_MONITOR_PORT`
- `LOCAL_LLM_PORT`
- `LOCAL_LLM_INTENT_PORT`
- `LOCAL_LLM_SMALL_PORT`
- `VOICE_PORT`
- `VOICE_WS_PORT`
- `WEB_BACKEND_PORT`
- `WEB_FRONTEND_PORT`
- `VITE_DEV_PORT`
- `VACATION_PLANNER_API_PORT`
- `NOVA_API_PORT`

### Notifications
- `PUSHOVER_USER_KEY`
- `PUSHOVER_APP_TOKEN`
- `DISCORD_BOT_TOKEN`
- `DISCORD_APP_ID`
- `DISCORD_PUBLIC_KEY`
- `DISCORD_CHANNEL_ID`
- `DISCORD_USER_ID_MARK`
- `DISCORD_LOW_WEBHOOK`
- `DISCORD_HIGH_WEBHOOK`
- `DISCORD_WEBHOOK_URL`

### Media
- `PLEX_URL`
- `PLEX_TOKEN`
- `PLEX_SERVER_ID`
- `SPOTIFY_CLIENT_ID`
- `SPOTIFY_CLIENT_SECRET`
- `SPOTIFY_REDIRECT_URI`
- `TMDB_API_KEY`
- `TMDB_API_READ_ACCESS_TOKEN`

### LLM providers / search
- `OPENROUTER_BASE_URL`
- `OPENROUTER_API_KEY`
- `OPENAI_BASE_URL`
- `OPENAI_API_KEY`
- `OPENAI_API_KEY_2`
- `OPENAI_PI5_API_KEY`
- `OPENAI_PI3_API_KEY`
- `CLAUDE_API_KEY`
- `HUGGINGFACE_API_KEY`
- `TAVILY_API_KEY`
- `EXA_API_KEY`
- `SERPER_API_KEY`

### Infra / vendor keys (as needed)
- `NVIDIA_NIM_API_KEY`
- `NVIDIA_API_KEY_1`
- `NVIDIA_API_KEY_2`
- `NGC_API_KEY`
- `APIFY_TOKEN`
- `RAPIDAPI_KEY`
- `ZENROWS_API_KEY`
- `GITHUB_TOKEN`
- `NETLIFY_API_KEY`
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `PINECONE_API_KEY`
- `PINECONE_ENVIRONMENT`
- `BING_API_KEY_1`
- `BING_API_KEY_2`

### Travel + mapping + weather
- `VIATOR_API_KEY`
- `VIATOR_PROD_API_KEY`
- `AMADEUS_API_KEY`
- `AMADEUS_API_SECRET`
- `OPENROUTESERVICE_API_KEY`
- `OPENTRIPMAP_API_KEY`
- `GOOGLE_MAPS_API_KEY`
- `GOOGLE_PLACES_API_KEY`
- `OPENWEATHER_API_KEY`
- `WEATHER_UNDERGROUND_API_KEY`
- `WEATHER_UNDERGROUND_PWS`
- `WEATHER_UNDERGROUND_STATION_KEY`

### Smart home / misc
- `TUYA_API_ENDPOINT`
- `TUYA_ACCESS_ID`
- `TUYA_ACCESS_SECRET`
- `TUYA_UID`
- `TUYA_DRIVEWAY_PLUG_DEVICE_ID`
- `EXCHANGERATE_HOST_BASE`
- `DOWNLOAD_URL`

### Internal auth
- `BANANA_MONITOR_API_KEY`
- `SYSOP_API_TOKEN`
