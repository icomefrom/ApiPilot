# Bug Shoot

[English](README.md) | [简体中文](README.zh-CN.md)

Bug Shoot is a self-hosted API debugging, interface testing, and visual workflow testing platform for individuals and small teams. It combines Postman-like API debugging, lightweight chain testing, and an Agent that can draft API workflows from natural language.

> Status: early open-source release. Good for local/self-hosted team usage; production deployments should review the security checklist first.

## Highlights

- API debugging for HTTP, WebSocket, and RPC-style requests
- Interface management with groups, environments, cURL import, and Postman Collection import
- Environment variables with runtime replacement via `{{env.key}}`
- JSONPath assertions and script assertions
- Visual chain testing with interface, script, timer, and condition nodes
- Chain execution history and step-level response details
- Agent workflow drafting from natural language goals
- Model-driven interface matching, response sampling, and dependency planning
- Project spaces and basic team membership
- Docker Compose one-command deployment

## Screenshots

Screenshots are not committed yet. Suggested files:

- `docs/images/api-debug.png`
- `docs/images/chain-test.png`
- `docs/images/agent-planner.png`
- `docs/images/run-report.png`

## Tech Stack

| Layer | Stack |
| --- | --- |
| Frontend | Vue 3, Vite, Pinia, Vue Router, Ant Design Vue, Vue Flow |
| Backend | Django, Django REST Framework, SimpleJWT, Gunicorn |
| Database | PostgreSQL |
| Agent LLM | OpenAI-compatible API or local Ollama |
| Deployment | Docker Compose, Nginx |

## Quick Start

Requirements:

- Docker
- Docker Compose v2

Start:

```bash
git clone <your-repo-url> bug-shoot
cd bug-shoot
cp .env.example .env
docker compose up --build -d
```

Open:

- Frontend: http://localhost
- Backend API: http://localhost:8000/api/

Default local account:

| Username | Password |
| --- | --- |
| `admin` | `admin123` |

The first startup runs migrations and creates demo data: a default project, local environment, sample interface, and sample chain.

English Agent demo:

- [Agent order chain demo: Create order -> Query order -> Assert status](docs/AGENT_ORDER_DEMO.md)

## Self Check

After startup, run:

```bash
sh scripts/self_check.sh
```

The script checks the frontend, backend login, and authenticated project list.

## Agent Setup

Bug Shoot supports two Agent provider modes:

1. OpenAI-compatible API
2. Bundled Ollama fallback

To use OpenAI or another OpenAI-compatible model, edit the root `.env` file. You do not need to change `Dockerfile`, `docker-compose.yml`, or backend code.

```bash
cp .env.example .env
```

Then set these values in `.env`:

```env
AGENT_OPENAI_BASE_URL=https://api.openai.com/v1
AGENT_OPENAI_API_KEY=sk-your-key
AGENT_OPENAI_MODEL=gpt-4.1-mini
```

For other OpenAI-compatible providers, keep the same three variables and replace the base URL/model with your provider's values.

Apply the change:

```bash
docker compose up -d backend
```

OpenAI-compatible mode is used when all values below are set:

```env
AGENT_OPENAI_BASE_URL=https://your-provider.example/v1
AGENT_OPENAI_API_KEY=your-key
AGENT_OPENAI_MODEL=your-model
```

If those values are empty, Docker Compose starts Ollama and pulls:

```env
AGENT_OLLAMA_MODEL=qwen2.5:7b
```

Agent pipeline:

```text
Natural language goal
→ Step planning
→ Interface candidate retrieval
→ Interface matching
→ Response sampling
→ Dependency planning
→ Chain draft generation
```

Agent results are explainable in the UI: each model stage shows status, provider/model, summary, and JSON details.

## Common Commands

```bash
# Service status
docker compose ps

# Logs
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f ollama

# Rebuild one service
docker compose up --build -d backend
docker compose up --build -d frontend

# Stop
docker compose down

# Reset local data
docker compose down -v
```

## Configuration

Copy `.env.example` to `.env` and adjust values.

| Variable | Description | Local default |
| --- | --- | --- |
| `FRONTEND_PORT` | Frontend published port | `80` |
| `BACKEND_PORT` | Backend API published port | `8000` |
| `DB_NAME` | PostgreSQL database | `bugshoot` |
| `DB_USER` | PostgreSQL user | `postgres` |
| `DB_PASSWORD` | PostgreSQL password | `postgres` |
| `SECRET_KEY` | Django secret key | local demo value |
| `DEBUG` | Django debug mode | `True` |
| `ALLOWED_HOSTS` | Django allowed hosts | `*` |
| `CORS_ALLOW_ALL_ORIGINS` | CORS wildcard | `True` |
| `DJANGO_SUPERUSER_USERNAME` | Initial admin username | `admin` |
| `DJANGO_SUPERUSER_PASSWORD` | Initial admin password | `admin123` |
| `LOAD_SAMPLE_DATA` | Seed demo data | `True` |
| `AGENT_OPENAI_BASE_URL` | OpenAI-compatible base URL | empty |
| `AGENT_OPENAI_API_KEY` | OpenAI-compatible API key | empty |
| `AGENT_OPENAI_MODEL` | OpenAI-compatible model | empty |
| `AGENT_OLLAMA_MODEL` | Ollama fallback model | `qwen2.5:7b` |

## Troubleshooting

Agent unavailable:

- Check `docker compose logs -f ollama`.
- The first Ollama startup may take time because it pulls the model.
- If using OpenAI-compatible mode, verify `AGENT_OPENAI_BASE_URL`, `AGENT_OPENAI_API_KEY`, and `AGENT_OPENAI_MODEL`.

Backend cannot start:

- Check `docker compose logs -f backend`.
- Ensure the database is healthy: `docker compose ps db`.
- If local data is disposable, run `docker compose down -v` and restart.

Port already used:

- Change `FRONTEND_PORT`, `BACKEND_PORT`, `DB_PORT`, or `OLLAMA_PORT` in `.env`.

Default login fails:

- Confirm `LOAD_SAMPLE_DATA=True`.
- Check backend logs for superuser initialization.
- If you changed `.env` after first startup, existing database data remains until `docker compose down -v`.

## Security Notes

Local defaults are not production-safe. Before exposing Bug Shoot beyond localhost:

- Change `SECRET_KEY`, `DB_PASSWORD`, and `DJANGO_SUPERUSER_PASSWORD`.
- Set `DEBUG=False`.
- Set explicit `ALLOWED_HOSTS`.
- Set `CORS_ALLOW_ALL_ORIGINS=False`.
- Use HTTPS.
- Do not expose PostgreSQL or Ollama ports publicly.
- Back up the PostgreSQL volume.

See [SECURITY.md](SECURITY.md).

Sensitive authentication fields and sensitive environment-variable keys are masked in API responses. Still, avoid importing or exporting production secrets unless your deployment is trusted.

## Local Development

Backend:

```bash
cd backend
pip install -r requirements.txt
python manage.py migrate
python scripts/init_data.py
python manage.py runserver 0.0.0.0:8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Frontend dev server: http://localhost:3000

## Tests

```bash
# Backend tests
docker compose exec backend python manage.py test

# Frontend tests/build
docker compose exec frontend npm test
docker compose exec frontend npm run build
```

## Roadmap

Near term:

- OpenAPI / Swagger import
- Editable Agent confirmation step
- Exportable chain execution reports
- Better demo templates for e-commerce, ERP, finance, CRM, and ticketing
- CI workflow for backend tests and frontend build

Later:

- Mock server
- Scheduled chain runs and notifications
- CLI runner for CI
- Audit logs
- Version history and rollback
- More granular project permissions

## Contributing

Issues and pull requests are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

Before opening a PR, please include:

- what changed
- why it changed
- how you verified it
- screenshots for UI changes

## License

MIT License. See [LICENSE](LICENSE).
