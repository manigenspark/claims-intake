# Day 4 Guide: Ship the Claims Intake Service

Day 4 wires C1–C3 into HTTP, proves it end-to-end, containers it, and merges through review.

## Already done (C1–C3)

- Contract, models, repository, rule engine, `checks.yaml`, agent-log + gate observation
- Repo: https://github.com/manigenspark/claims-intake

## Day 4 technical work (this branch)

| Piece | File |
| --- | --- |
| HTTP | `src/claims/api/routes.py` |
| Integration tests | `tests/integration/test_routes.py` |
| Image | `Dockerfile` |
| Runbook | `README.md` |
| Tool note | `docs/tool-comparison.md` (you finish after one Cursor task) |

## Mapping (contract §5–§6)

| Outcome | Status | Code |
| --- | --- | --- |
| Accepted | 201 | body: `claim_reference`, `status: recorded` |
| Parse / extra field / bad shape | 400 | `MALFORMED_REQUEST` |
| V-6 duplicate | 409 | `DUPLICATE_NOTIFICATION` + detail.claim_reference |
| V-1…V-5, V-7 | 422 | matching rule code |
| lookup `timeout` / `unreachable` | 503 | `POLICY_MASTER_TIMEOUT` / `_UNREACHABLE` |
| lookup `unparsable` | 500 | `POLICY_MASTER_UNPARSABLE` |

Envelope always: `{ "code", "message", "detail" }`.

## You still do manually

1. One small task **in Cursor** (not only the agent) → write `docs/tool-comparison.md`
2. Open PR with what / why / look hardest at / verified
3. Review partner’s PR (blocking | question | suggestion + contract cites)
4. Answer blocking comments; merge when green

## Platform note (for README)

Dev container is often `linux/aarch64` (Apple Silicon). Deployment targets `linux/amd64`.  
`docker buildx build --platform linux/amd64` builds for the **deployment** CPU, not necessarily the laptop’s.
