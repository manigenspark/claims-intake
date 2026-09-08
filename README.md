# Claims Intake Service

A service that accepts a first notice of loss from the claims portal, validates
it against the policy master and the rule table in `docs/api-contract.md`, and
either records a notification and issues a claim reference or refuses the
submission with a specific contract error code.

This README is written for someone inside the lab container who has never opened
the repository before. Dependencies are already installed in that environment.
There is no install step.

## Confirm you are in the right place

```
uname -sm     # often Linux aarch64 in this Codespace
pwd           # /workspaces/claims-intake
```

## What the service does

```
POST /notifications
Content-Type: application/json
```

Body fields are defined in `docs/api-contract.md` section 2. A valid, admissible
notification returns `201` with `claim_reference` and `status: recorded`. A
refusal returns the standard envelope `{code, message, detail}` with the HTTP
status from section 6.

## Run the service locally (in this container)

```
uv run uvicorn claims.api.routes:app --host 0.0.0.0 --port 8000
```

In another terminal:

```
curl -s -X POST http://127.0.0.1:8000/notifications \
  -H 'Content-Type: application/json' \
  -d '{
    "policy_number": "MOT-4471",
    "loss_date": "2026-04-02",
    "claim_type": "collision",
    "estimated_amount": "4200.00",
    "description": "Rear ended at a junction."
  }'
```

## Run the tests

```
uv run pytest
uv run ruff check .
uv run mypy
```

Unit tests cover models, repository, and rules. Integration tests under
`tests/integration/` call the HTTP surface with `TestClient`.

## Build and run the container image

Build for the **deployment** CPU architecture explicitly:

```
docker buildx build --platform linux/amd64 -t claims-intake:local --load .
```

Run it:

```
docker run --rm -p 8000:8000 claims-intake:local
```

Then use the same `curl` as above against `http://127.0.0.1:8000/notifications`.

### Why `--platform linux/amd64`

This Codespace often runs on ARM (`linux/aarch64`), for example on Apple Silicon.
The place that runs the service in deployment is typically an `amd64` (x86_64)
machine or cluster node. If you build with no platform flag, Docker may produce
an ARM image that runs here but fails or is rejected where the service is
actually hosted. `--platform linux/amd64` forces the image to match that
deployment architecture even when your laptop or Codespace CPU is different.

## Where things are

| Path | What it holds |
| --- | --- |
| `docs/api-contract.md` | What the service accepts, returns, and refuses |
| `docs/requirements-brief.md` | Work items and acceptance criteria |
| `docs/payload-triage.md` | Day 1 edge payload classifications |
| `data/` | Synthetic policies and FNOL payloads |
| `src/claims/` | Models, repository, rules, HTTP routes |
| `tests/` | Unit and HTTP integration tests |
| `Dockerfile` | Image definition for the running API |
| `.github/workflows/checks.yaml` | PR checks: ruff, mypy, pytest |

## Data

Everything in `data/` is synthetic. It contains no real client data and no named
clients.
