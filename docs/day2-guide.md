# Day 2 Guide: Build the Boundary and the Record

Step-by-step instructions for completing **Component C2** — `models.py`, `repository.py`, unit tests, and contract reconciliation.

**Prerequisites (already done in this repo):**

- `docs/api-contract.md` sections 4–6 are complete
- `docs/payload-triage.md` classification and three ambiguity decisions are recorded
- `src/claims/policy_client.py` is complete — read it before you start
- `src/claims/service.py` and `src/claims/api/routes.py` remain stubs — do not implement them today

**Deliverables when finished:**

| File | Action |
| --- | --- |
| `src/claims/models.py` | Implement |
| `src/claims/repository.py` | Implement |
| `tests/unit/test_models.py` | Create |
| `tests/unit/test_repository.py` | Create |
| `docs/payload-triage.md` | Add reconciliation note at the end |
| `docs/api-contract.md` | Amend section 6 only if a model rejection is missing |

Commit all of the above to your branch.

---

## Step 0 — Confirm your starting point

From the project root (`claims-intake/`):

```bash
uname -sm     # expect Linux aarch64 in the container
pwd           # expect /workspaces/claims-intake
uv run pytest # expect 0 tests or only conftest-level fixtures
```

Open and read:

1. `docs/api-contract.md` — especially sections 2.2, 2.3, 2.4, 3, and 6
2. `docs/payload-triage.md` — your Day 1 classification table
3. `src/claims/policy_client.py` — `PolicyRecord`, `StubPolicyClient`, exceptions
4. `data/fnol_valid.json`, `data/fnol_invalid.json`, `data/fnol_edge.json`

Confirm stubs raise `NotImplementedError`:

```bash
uv run python -c "from claims.repository import NotificationRepository; NotificationRepository()"
# should raise NotImplementedError
```

---

## Step 1 — Implement `NotificationRequest`

**Authority:** contract section 2.2, 2.3, 2.4, and section 6 (400 structural constraints).

### Fields (all from the contract, not from memory)

| Field | Python type | Constraints |
| --- | --- | --- |
| `policy_number` | `str` | Required, non-empty, **no default** |
| `loss_date` | `date` | Required; parse `YYYY-MM-DD` strings from JSON |
| `claim_type` | `Literal[...]` | Required; exactly the five values in section 2.3 |
| `estimated_amount` | `Decimal` | Required; exactly two decimal places; greater than zero |
| `description` | `str \| None` | Optional; absent and `null` both become `None` |

### Design rules

- Set `model_config = ConfigDict(extra="forbid")` — unknown fields → validation error (400 later).
- **No defaults on required fields** — the service never invents caller data.
- Reject `float` for `estimated_amount` — use `Decimal` everywhere in source and tests.
- Reject bare `int` for amounts — JSON strings like `"4300.00"` should parse to `Decimal`.

### Payload boundary decisions (from your triage)

These must fail at the **model**, never reaching rules:

| Payload | Why |
| --- | --- |
| EDGE-08 | Missing required field |
| EDGE-11 | `claim_type` `"flood"` outside section 2.3 vocabulary |
| EDGE-12 | `estimated_amount` `"3499.999"` — wrong precision |

All payloads in `fnol_valid.json` and `fnol_invalid.json` should **pass** the model (invalid ones fail later at rules).

### Check yourself

```python
NotificationRequest.model_validate({"policy_number": "MOT-4471", ...})
```

Never accept a raw `dict` outside `models.py` in production code.

---

## Step 2 — Implement `Policy`

**Authority:** `PolicyRecord` in `policy_client.py`, WI-0158 AC-3.

Build a Pydantic model (or frozen dataclass) your service works with:

| Field | Type | Notes |
| --- | --- | --- |
| `policy_number` | `str` | |
| `product` | `str` | |
| `effective_date` | `date` | |
| `expiry_date` | `date` | |
| `cancellation_date` | **`date \| None`** | Critical: AC-3 requires handling absence at the type level |
| `limit` | `Decimal` | |
| `permitted_claim_types` | `frozenset[ClaimType]` or similar | From policy record |

Add `Policy.from_record(record: PolicyRecord) -> Policy`.

**Why `date | None` matters:** comparing `loss_date < policy.cancellation_date` without a `None` check must fail mypy strict mode. That makes WI-0158 AC-3 hard to violate accidentally.

---

## Step 3 — Implement supporting value types

### `RuleFailure`

- Immutable (`@dataclass(frozen=True)` or equivalent)
- Two **separate** fields: rule identifier and error code
- Use `NewType("RuleId", str)` and `NewType("ErrorCode", str)` so they cannot be swapped at call sites

### `RecordedNotification` (starter name; assignment text says `ClaimRecord`)

**Authority:** contract section 3 — success response.

| Field | Notes |
| --- | --- |
| `claim_reference` | Pattern `CLM-YYYY-NNNNNN` |
| Copy of notification fields | `policy_number`, `loss_date`, `claim_type`, `estimated_amount`, `description` |

Validate the reference format in the model or via a shared regex constant.

---

## Step 4 — Implement `NotificationRepository`

**Authority:** contract section 3 (reference format), WI-0151 AC-1 and AC-3.

### `record(notification: NotificationRequest) -> RecordedNotification`

- Issue a unique claim reference: `CLM-{year}-{sequence:06d}`
- `YYYY` = calendar year when recorded (use `datetime.now(tz=UTC).date().year`)
- Sequence zero-padded to six digits, unique per year
- Append to in-memory store; return the recorded object
- **Optional test hook:** accept `recording_year: int | None` in `__init__` so tests are deterministic

### `find_matching(policy_number, loss_date, claim_type) -> RecordedNotification | None`

- Match on **all three** fields together (WI-0151 AC-1)
- Return the first match or `None`
- **No rule logic here** — only query what was stored

### What does NOT belong in the repository

- No validation of policy dates, limits, or cancellation
- No recording of rejected notifications — if it was refused, it was never written (AC-3)

---

## Step 5 — Write `tests/unit/test_models.py`

### Structure

```python
@pytest.mark.parametrize(
    ("case_id", "payload"),
    [...],
    ids=[...],
)
def test_notification_request_accepts_valid_payloads(case_id, payload): ...

@pytest.mark.parametrize(
    ("case_id", "payload", "expected_loc"),
    [...],
    ids=[...],
)
def test_notification_request_rejects_invalid_payloads(case_id, payload, expected_loc): ...
```

**Rules for tests:**

- Parametrize with **named cases** — no loops inside test bodies
- Every field constraint gets at least one violating case
- Use `date(...)` and `Decimal("...")` in assertions — never `float` or date strings in test logic
- Load realistic payloads from `data/fnol_*.json` via a small helper (e.g. `tests/unit/payload_data.py`)

### Minimum test coverage

| Category | Examples |
| --- | --- |
| Accept | All `fnol_valid.json` cases; EDGE-01–07, 09–10 |
| Reject extra field | `{"policy_number": "...", "typo_field": 1, ...}` |
| Reject each missing required field | One case per field |
| Reject empty `policy_number` | `""` |
| Reject bad `loss_date` | Wrong type, bad format |
| Reject unknown `claim_type` | EDGE-11 |
| Reject bad `estimated_amount` | Zero, negative, float, int, wrong precision (EDGE-12) |
| `RuleFailure` immutability | Assigning to a field raises |
| `Policy.from_record` | Builds from `StubPolicyClient` data |
| `Policy.cancellation_date` typing | mypy enforces `None` check (no test needed if types are correct) |

---

## Step 6 — Write `tests/unit/test_repository.py`

### Fixtures (fresh objects every time)

```python
@pytest.fixture
def repository() -> NotificationRepository:
    return NotificationRepository(recording_year=2026)

@pytest.fixture
def sample_notification() -> NotificationRequest:
    return NotificationRequest.model_validate({...})
```

### Required test cases

| Test | What it proves |
| --- | --- |
| Reference format | Matches `CLM-2026-000001` pattern |
| Reference uniqueness | Two `record()` calls → different references |
| Duplicate detection | Same three fields → `find_matching` returns existing record |
| Partial match is not duplicate | Only two of three fields agree → `None` |
| WI-0151 AC-3 | Never call `record()` for a "rejected" notification; resubmitting identical data is **not** a duplicate |

For AC-3, demonstrate explicitly:

1. Build a notification but **do not** record it
2. Call `find_matching` — expect `None`
3. Record a *different* notification with the same three key fields — now it is a duplicate

Each test must run independently — no shared mutable state between tests.

---

## Step 7 — Configure tooling

Add to `pyproject.toml` if not present:

```toml
[tool.mypy]
python_version = "3.12"

[tool.pytest.ini_options]
pythonpath = ["src"]
```

Run until clean:

```bash
uv run ruff check .
uv run mypy
uv run pytest
```

### Common lint/type issues

| Issue | Resolution |
| --- | --- |
| Pydantic validators raise `ValueError` | Ruff TRY004 prefers `TypeError` — if unavoidable, discuss with instructor before adding a per-file ignore |
| `UTC` vs `timezone.utc` | Use what matches your Python version and project convention |
| Import paths | `pythonpath = ["src"]` in pytest config |

**Do not add suppression comments** unless you have documented why the rule cannot be satisfied.

---

## Step 8 — Reconcile the contract

List every rejection your `NotificationRequest` can produce:

- Extra field
- Missing required field
- Wrong type per field
- Empty `policy_number`
- Unknown `claim_type`
- Wrong `estimated_amount` precision or sign
- Invalid JSON shape (handled at HTTP layer Day 4, but model covers typed parsing)

Compare against **section 6** of `docs/api-contract.md`.

| If… | Then… |
| --- | --- |
| Every rejection maps to an existing code | Add a reconciliation note saying so and how you checked |
| Something is missing | Amend section 6 (code + status), then note what changed and why |

Add the note at the **end** of `docs/payload-triage.md`:

```markdown
## Contract reconciliation (Day 2)

**Method.** [what you listed and checked]
**Result.** [no amendment needed / amended section 6 because …]
**Payload boundary check.** [fnol_valid/invalid/edge model vs rules split]
```

Expected outcome in this repo: all model rejections already map to `MALFORMED_REQUEST` (400) in section 6 from your Day 1 EDGE-11/EDGE-12 decisions — no amendment needed, but you must still document how you verified.

---

## Step 9 — Acceptance criteria checklist

Before committing, confirm each criterion is fully met:

- [ ] `NotificationRequest` rejects extra fields (`extra="forbid"`)
- [ ] `NotificationRequest` rejects missing required fields; no required field has a default
- [ ] `loss_date` is `date`; `estimated_amount` is `Decimal` everywhere in source and tests
- [ ] No date or money value in source or tests is a `str` or `float` (JSON input strings are fine; parse them)
- [ ] `cancellation_date` is `date | None` — comparison without `None` handling fails mypy
- [ ] `RuleFailure` is immutable with separate rule id and error code fields
- [ ] Repository returns references matching `CLM-YYYY-NNNNNN`; all references unique
- [ ] Duplicate match requires all three: `policy_number`, `loss_date`, `claim_type`
- [ ] Two-of-three match is **not** a duplicate
- [ ] Rejected notifications are never recorded; test proves resubmit is not duplicate
- [ ] Every declared field constraint has a violating test case
- [ ] All multi-input tests use parametrization with named cases — no loops in test bodies
- [ ] Every fixture returns a fresh object; suite passes in any order
- [ ] `ruff check` and `mypy` exit zero without unjustified suppressions
- [ ] No module outside `models.py` accepts a raw request `dict`
- [ ] Reconciliation note exists; every model-produced code appears in contract section 6

---

## Step 10 — Commit

```bash
git status
git add src/claims/models.py src/claims/repository.py \
        tests/unit/test_models.py tests/unit/test_repository.py \
        docs/payload-triage.md
# add docs/api-contract.md only if you amended section 6
git commit -m "$(cat <<'EOF'
Implement boundary models and notification repository (Day 2).

Adds request parsing, policy/record types, duplicate detection, and unit tests
pinned to the API contract.
EOF
)"
```

---

## What comes next (out of scope today)

| Day | Work |
| --- | --- |
| **Day 3** | Implement `service.py` — rules V-1 through V-7 in section 4.1 order; test-first against `fnol_invalid.json` and edge payloads |
| **Day 4** | Implement `api/routes.py` — `POST /notifications`, map outcomes to status codes from section 6; finish `README.md` |

Day 3 will import your `NotificationRequest`, `Policy`, and `NotificationRepository` exactly as you define them today. Keep names and types stable.

---

## Quick reference — where each payload stops

| Source | Model (Day 2) | Rules (Day 3) |
| --- | --- | --- |
| `fnol_valid.json` (all) | Pass | Pass (if rules allow) |
| `fnol_invalid.json` (all) | Pass | Fail (various V-* codes) |
| EDGE-01 – 07, 09 – 10 | Pass | Per triage table |
| EDGE-08, 11, 12 | **Fail → 400** | Never reached |

Use this table when writing both model tests and (later) service tests.
