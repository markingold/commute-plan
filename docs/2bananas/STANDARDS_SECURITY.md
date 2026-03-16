<!--
id: STD-SECURITY
version: 1.2
last_updated: 2026-03-01
title: Standards: Security
purpose:
  Safe defaults for secrets, input handling, and operational safety.
-->
# Standards: Security

- Never commit secrets. Real env belongs in `secrets/.env` (chmod 600).
- Validate input at boundaries (web/API/CLI).
- Avoid writing files into web-served locations.
- Don’t log secrets/tokens/keys.
