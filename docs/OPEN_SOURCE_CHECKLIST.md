# Open Source Release Checklist

Use this before tagging the first public release.

## Required

- [ ] `README.md` includes positioning, features, quick start, default account, Agent setup, troubleshooting, roadmap, and license.
- [ ] `.env.example` contains all supported environment variables and safe local defaults.
- [ ] `.env` is not committed.
- [ ] `docker compose up --build -d` succeeds on a clean machine.
- [ ] Default demo data is created on first start.
- [ ] Default account can log in.
- [ ] Example interface can be executed.
- [ ] Example chain can be executed.
- [ ] Agent shows a useful error when the model provider is unavailable.
- [ ] Sensitive environment values are masked in API responses.
- [ ] `LICENSE` is present and referenced from README.
- [ ] `SECURITY.md` explains production hardening and vulnerability reporting.
- [ ] Issue and pull request templates exist.

## Recommended

- [ ] Add screenshots or GIFs under `docs/images/`.
- [ ] Add a tagged `v0.1.0` release.
- [ ] Add a short demo video.
- [ ] Add CI for backend tests and frontend build.
- [ ] Add OpenAPI import, mock server, scheduled runs, and CLI runner to roadmap.
