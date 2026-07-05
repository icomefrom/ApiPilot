# Security Policy

Bug Shoot is intended for self-hosted API debugging and lightweight team collaboration. Before exposing it outside a trusted local network, review the checklist below.

## Supported Versions

Security fixes target the latest `main` branch until formal releases are published.

## Reporting a Vulnerability

Please do not open a public issue for sensitive reports. Email the maintainer or use a private advisory if the repository host supports it. Include:

- affected version or commit
- deployment mode
- reproduction steps
- impact
- relevant logs or screenshots with secrets removed

## Production Hardening

- Change `SECRET_KEY`, `DB_PASSWORD`, and the default admin password.
- Set `DEBUG=False`.
- Set explicit `ALLOWED_HOSTS`.
- Disable `CORS_ALLOW_ALL_ORIGINS` and configure `CORS_ALLOWED_ORIGINS`.
- Put the frontend behind HTTPS.
- Restrict database and Ollama ports from the public internet.
- Back up the PostgreSQL volume regularly.
- Treat imported API collections and environment variables as sensitive.

## Secret Handling

Authentication token/password fields are returned masked by the API. Environment variables with sensitive keys such as `token`, `secret`, `password`, `apikey`, `api_key`, `authorization`, and `cookie` are masked in list/detail responses.

Never commit `.env`, database dumps, screenshots containing tokens, or exported collections containing production secrets.
