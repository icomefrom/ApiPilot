# Bug Shoot v0.1 Release Notes Draft

Initial open-source release focused on self-hosted API debugging and lightweight workflow testing for individuals and small teams.

## Included

- User authentication with JWT
- Project spaces and basic membership
- API interface management
- Environment management with masked sensitive values
- HTTP / WebSocket / RPC debugging
- cURL and Postman Collection import
- JSONPath and script assertions
- Visual chain testing
- Chain execution history
- Agent planner with:
  - step planning
  - interface candidate retrieval
  - interface matching
  - response sampling
  - dependency planning
  - draft chain generation
- Docker Compose deployment
- Demo data initialization

## Known Limitations

- OpenAPI / Swagger import is not implemented yet.
- Mock server is not implemented yet.
- Scheduled chain runs are not implemented yet.
- CLI runner is not implemented yet.
- Audit logs and version rollback are planned.
- Agent quality depends on the configured model and local interface naming.

## Upgrade Notes

This is the first public release. For local resets, run:

```bash
docker compose down -v
docker compose up --build -d
```
