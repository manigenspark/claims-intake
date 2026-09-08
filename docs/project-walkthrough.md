# Claims Intake: What This Folder Is and What We Built

This is a personal walkthrough of the `claims-intake` repository: what the service is for, how the week is structured, what we changed in this workspace, and why each design and technical choice looks the way it does.

The authority for behavior is always `docs/api-contract.md`. If this note and the contract disagree, the contract wins.

---

## 1. What this folder is

`claims-intake` is a **first notice of loss (FNOL)** service. The claims portal posts a notification. This service either:

1. records it and issues a claim reference such as `CLM-2026-000001`, or
2. refuses it with a specific error code and HTTP status.

It does **not** decide whether the claim will be paid. It only decides whether the notification is well formed and admissible against the policy master and the rule table.

### How the week is split

| Day | Component | What you own |
| --- | --- | --- |
| Day 1 | C1 — the contract | `docs/api-contract.md` sections 4–6, `docs/payload-triage.md` |
| Day 2 | C2 — the boundary and the record | `models.py`, `repository.py`, unit tests, contract reconciliation |
| Day 3 | C3 — the rule engine | `service.py` (still a stub except V-1) |
| Day 4 | C4 — HTTP | `api/routes.py` (still a stub), finish `README.md` |

Day 2 is what we implemented in this workspace. Days 3 and 4 must not be filled in yet.

### How a request is supposed to move

```
JSON body
    → models.py          parse and reject shape problems (400)
    → service.py         evaluate rules V-1 … V-6 (422 / 409)     [Day 3]
    → repository.py      write a ClaimRecord, issue a reference
    → api/routes.py      map the outcome to HTTP                 [Day 4]
```

The important split is **well formed vs admissible** (contract section 2.4):

- The caller’s **code** is wrong → `400 MALFORMED_REQUEST` (missing field, extra field, wrong type, bad `claim_type`, bad money precision).
- The caller’s **data** is wrong → `422` (policy not found, loss before inception, cancelled, after expiry, over limit, type not covered).
- Same loss already recorded → `409 DUPLICATE_NOTIFICATION`.
- Policy master did not answer → `503` or `500`.

If a date string or a float amount reached the rules, a shape problem and a content problem would look the same to the portal. That is why Day 2 exists: make the objects Day 3 compares trustworthy.

### What was already here (starter, not ours)

| Path | Role |
| --- | --- |
| `docs/api-contract.md` | What the service accepts and refuses. Day 1 completed sections 4–6. |
| `docs/requirements-brief.md` | Work items WI-0142, WI-0151, WI-0158 and their acceptance criteria. |
| `docs/payload-triage.md` | Day 1 classification of every `EDGE-*` payload. |
| `docs/day2-guide.md` | Official Day 2 lab instructions. |
| `data/policies.json` | Synthetic policy master. |
| `data/fnol_valid.json` | Notifications that should parse and later pass rules. |
| `data/fnol_invalid.json` | Notifications that parse but fail a rule (Day 3). |
| `data/fnol_edge.json` | Boundary cases. EDGE-08, 11, 12 fail at the model; the rest survive to rules. |
| `src/claims/policy_client.py` | Complete. `PolicyClient`, `PolicyNotFound`, `PolicyLookupFailed`, `StubPolicyClient`. Do not rewrite it. |
| `src/claims/service.py` | Day 3. Only `evaluate_policy_exists` (V-1) is written. |
| `src/claims/api/routes.py` | Day 4 stub. |

---

## 2. What we did, in order

### Step 0 — Clean the tree

macOS AppleDouble sidecar files (`._README.md`, `._src`, and so on) were sitting next to every real file, so the tree looked doubled. Those are resource-fork leftovers, not source. We deleted them and added `._*` to `.gitignore`.

### Step 1 — Implement the request boundary (`NotificationRequest`)

`NotificationRequest` is the only production type that may parse a raw request dictionary. After this, Day 3 and Day 4 work with a typed object.

Fields come from contract section 2.2, not from the example payloads:

| Field | Type after parse | Why |
| --- | --- | --- |
| `policy_number` | non-empty `str` | Identifier as held in the master. Empty is a shape error. |
| `loss_date` | `date` | V-2, V-3, V-7 compare dates. A string comparison is not a date comparison. |
| `claim_type` | `Literal` of the five values in 2.3 | `"flood"` is not a type the rules know. EDGE-11 is 400, not V-5. |
| `estimated_amount` | `Decimal` with exactly two places, `> 0` | V-4 compares to `policy.limit`. A `float` is binary and inexact. |
| `description` | `str \| None` | Optional. Absent and `null` both become `None`. The only field with a default, and the default does not invent caller data. |

Required fields have **no defaults**. A default would invent data the portal did not send.

### Step 2 — Implement `Policy`

`StubPolicyClient` returns a plain `PolicyRecord`. Day 2 defines `Policy`, the object the service will compare against.

`cancellation_date` is `date | None`. That is WI-0158 AC-3: if the policy was never cancelled, the date is absent. Writing `loss_date < policy.cancellation_date` without a `None` check fails mypy. The type checker enforces the work item.

`Policy.from_record` is the only conversion from the policy master type into our type.

### Step 3 — Implement `RuleFailure` and `ClaimRecord`

`RuleFailure` is a frozen dataclass with two **different** NewTypes: `RuleId` (`"V-2"`) and `ErrorCode` (`"LOSS_BEFORE_INCEPTION"`). A rule identifier must not be passable where a contract code is expected.

`ClaimRecord` is a recorded notification plus `claim_reference` matching `CLM-YYYY-NNNNNN`. The assignment name is `ClaimRecord`. The starter comments said `RecordedNotification`; we use `ClaimRecord` because that is what the brief requires.

### Step 4 — Implement `NotificationRepository`

In-memory list of `ClaimRecord`. Three jobs only:

1. `record` — write an accepted notification, issue a unique reference.
2. `find_matching` — query by `policy_number` + `loss_date` + `claim_type` (WI-0151 AC-1).
3. `recorded_claims` — read-only view of what was written.

No rule logic lives here. The repository does not know about inception, limits, or cancellation.

### Step 5 — Write unit tests

`tests/unit/test_models.py` and `tests/unit/test_repository.py`. Multiple inputs use `@pytest.mark.parametrize` with named ids. Fixtures return a new object every time. No test depends on another test having run.

### Step 6 — Reconcile the contract

Every refusal the model can produce was listed against section 6. All of them are `MALFORMED_REQUEST` / 400. Three structural constraints from section 2.2 were named in the 400 row because the parenthetical had omitted them. The method and result are in `docs/payload-triage.md` under **Contract reconciliation (Day 2)**.

### Step 7 — Instructor feedback (second pass)

The request model and its tests were accepted. Feedback on the rest:

| Feedback | What we changed |
| --- | --- |
| `Policy` did not forbid extras or constrain `policy_number` / `limit` | `extra="forbid"`, `NonEmptyString`, `UsdAmount` on `limit` |
| `RecordedNotification` did not keep the request’s money constraints | Replaced by `ClaimRecord` using the same `UsdAmount` |
| Required `ClaimRecord` type was missing | `ClaimRecord` is the persistable type |
| Rejected notifications were safe only because tests skipped `record()` | Store is `ClaimRecord` only; no reject API; `find_matching` reads that store |
| Reconciliation note “not included” | Note was already at the end of `payload-triage.md`; a pointer was added at the top |

---

## 3. Design decisions

### The contract is the specification

Where the contract is silent or incomplete, we amend the contract. We do not invent behavior in code and leave the portal team to guess. That is why empty `policy_number`, invalid `loss_date`, and `estimated_amount <= 0` were added to section 6’s 400 row: the model already refused them, and the table claims to be exhaustive.

### Shape vs content is a type boundary, not an if-statement later

`NotificationRequest` is the shape boundary. `service.py` is the content boundary. A payload that reaches a rule has already been proven well formed. Day 3 will not touch raw dictionaries.

### Extra fields are forbidden

Contract section 2.2: a misspelled field is a defect in the caller’s code. If extras were ignored, we would record a notification built from data the caller did not intend (`policy_nubmer` dropped, `policy_number` missing or invented). `extra="forbid"` makes that a validation error.

The same rule applies to `Policy` and `ClaimRecord`. A typo on those objects must not be silently dropped.

### No defaults on required fields

A default is invented data. `description` may default to `None` because the contract says absent and `null` are equivalent. `estimated_amount` must not default to `0` or anything else.

### `claim_type` vocabulary is a type, not rule V-5

Section 2.3 fixes five strings. `"flood"` is not in the vocabulary, so it is a type error (EDGE-11 → 400). V-5 (`TYPE_NOT_COVERED`) is for a **valid** type that this **product** does not cover (collision on a named-perils policy). Those are different statements to the handler.

### Dates are `date`, money is `Decimal`

V-2 compares `loss_date >= effective_date`. V-4 compares `estimated_amount <= limit`. Those comparisons are exact only if both sides are `date` and `Decimal`.

A JSON number `4200.00` becomes a Python `float`. Floats are binary. We refuse floats so V-4 never compares against an approximation. Portal fixtures send amounts as strings (`"4200.00"`); the before-validator turns that string into `Decimal`.

Exactly two decimal places is part of the USD type (cents). `"3499.999"` (EDGE-12) is malformed, not “round it and continue”. Recording a different amount than the caller sent would be a partial outcome, which section 3 forbids.

We check `Decimal.as_tuple().exponent == -2`. That is the value’s scale, not a display format:

- `Decimal("4200.00")` → exponent `-2` → accept
- `Decimal("4200.0")` → `-1` → reject
- `Decimal("4200")` → `0` → reject
- `Decimal("3499.999")` → `-3` → reject

`UsdAmount` is one annotated type (`> 0` and two places) used on the request, the policy limit, and the claim record. A recorded claim cannot drift from the request that produced it. A limit uses the same unit V-4 will compare against.

### `strict=True` on the request

Pydantic will otherwise coerce `datetime` to `date` (because `datetime` is a subclass of `date`) and coerce `int`/`float` toward `Decimal`. Strict mode lets the before-validators convert **only** well-formed JSON strings. Every other type is left for pydantic to reject.

That is how we satisfied both:

- pydantic, which wraps `ValueError` into `ValidationError` (a bare `TypeError` from a validator was escaping), and
- ruff TRY004, which complained if we `raise ValueError` after `isinstance(value, float)`.

Validators convert strings. Types reject everything else.

### `cancellation_date: date | None`

WI-0158 AC-3: a null cancellation means the policy was not cancelled; do not evaluate the date comparison. Typing it as `date` would force a dummy date. Typing it as `str` would make absence a magic string. `date | None` makes the missing case visible to mypy.

V-7 itself (loss on or after cancellation) is Day 3. Day 2 only makes that rule hard to write incorrectly.

### `RuleFailure` keeps two names

The contract has rule ids (`V-6`) and error codes (`DUPLICATE_NOTIFICATION`). They travel together in a refusal but they are not interchangeable. `NewType` plus two fields means a call site cannot pass `"V-6"` where a code is expected without the type checker noticing.

Frozen so a later layer cannot mutate the decision.

### The repository stores decisions, it does not make them

WI-0151 AC-1: a duplicate is the same `policy_number`, `loss_date`, and `claim_type` **already recorded**. Two of three is not a duplicate.

WI-0151 AC-3: a previous **refusal** is not a duplicate, because nothing was written.

The first version of the test showed AC-3 by not calling `record()`. Instructor feedback: that is caller discipline, not design. The design is:

- the only persistable type is `ClaimRecord`
- the only write method is `record`
- there is no `reject` / `record_rejection` / `record_failure`
- `find_matching` iterates `_claims`, which contains only `ClaimRecord`

A `NotificationRequest` that exists in memory after a refusal is invisible to the store. The caller does not have to remember “don’t record this.” There is no API that could record a refusal.

`record` will still write if Day 3 calls it after a failed rule. That is Day 3’s job (`submit_notification` records only if every rule passed). Putting “refuse if duplicate” inside `record` would move V-6 into the repository and collapse deciding and doing.

### Claim references

Contract section 3: `CLM-YYYY-NNNNNN`. `YYYY` is the calendar year **when recorded**, not the loss year. Sequence is zero-padded to six digits, unique, never reissued.

`recording_year` on `__init__` is a test hook so tests can assert `CLM-2026-000001` without depending on the clock. Production uses `datetime.now(tz=UTC).date().year`. Sequences are per year so `CLM-2026-000001` and `CLM-2027-000001` can both exist.

### In-memory store is deliberate

Week 1 does not need a database. Rules do not know where claims live. Replacing the list with a database later is a change to one module.

### Tests name the guarantee that would break

Ids such as `missing_estimated_amount_EDGE-08` and `claim_type_outside_vocabulary_flood_EDGE-11` identify the failure without opening the file. Parametrization means one failing case does not hide the others (a loop inside one test would).

Fixtures are fresh. Shared mutable fixtures make the suite order-dependent; an order-dependent suite fails in CI on a day nothing changed.

JSON fixture strings are input, not assertion types. After parse we assert `date(...)` and `Decimal("...")`.

### Tools

`ruff check` and `mypy --strict` must exit zero with no suppression comments. A rule you cannot satisfy is a conversation, not `# noqa`.

---

## 4. Technical decisions (implementation detail)

### Pydantic models at the boundary, dataclass for `RuleFailure`

The request, policy, and claim record parse and constrain fields. Pydantic is the right tool. `RuleFailure` is not parsed from JSON; it is constructed in process. A frozen dataclass plus NewTypes is enough and stays immutable without a model.

### `from __future__ import annotations`

Keeps annotations as strings so `date | None` and forward references stay clean on 3.12.

### `Policy.from_record` and `cast`

`PolicyRecord.permitted_claim_types` is `tuple[str, ...]`. We map each string through `_as_claim_type`, which checks the vocabulary and `cast`s to `ClaimType`. The policy master is trusted data, but a bad file still fails loudly instead of carrying `"flood"` into V-5.

### Before-validators return `object`

They either return a converted `date` / `Decimal`, or they return the original value for strict pydantic to reject. They do not raise `TypeError` for wrong types (that escaped as an uncaught exception in this pydantic version).

### `InvalidOperation` from `Decimal("four-thousand")`

That exception is not a `ValueError`. We catch it and raise `ValueError` so pydantic turns it into `ValidationError` with loc `estimated_amount`.

### UTC for the recording year

`datetime.now(tz=UTC)` avoids naive datetimes (ruff DTZ001) and does not depend on the container’s local timezone.

### `recorded_claims()` returns a tuple

Callers cannot append to the internal list. The test for AC-3 can assert `recorded_claims() == ()` without reaching into `_claims`.

### Test helper `tests/unit/payload_data.py`

Loads `data/fnol_*.json` once. Tests do not open files themselves. `well_formed_payload` / `payload_omitting` build mutation cases from one valid shape so missing-field tests do not share a mutated dict.

### What we did **not** do

- Did not implement `service.py` rules V-2 through V-6 or `submit_notification`.
- Did not implement `POST /notifications` in `routes.py`.
- Did not put V-6 (duplicate refusal) inside `record`.
- Did not commit: this workspace has no `.git` directory. The lab asks for a commit on your branch when git is available.

---

## 5. Where each fixture payload stops

| Source | Stops at the model (Day 2) | Survives to rules (Day 3) |
| --- | --- | --- |
| `fnol_valid.json` VALID-01–08 | No | Yes |
| `fnol_invalid.json` INVALID-01–07 | No | Yes (various V-* codes) |
| EDGE-01 inception day | No | Accept (V-2 inclusive) |
| EDGE-02 amount equals limit | No | Accept (V-4 inclusive) |
| EDGE-03 loss on expiry day | No | Accept (V-3 inclusive) |
| EDGE-04 loss on cancellation day | No | V-7 `POLICY_CANCELLED` |
| EDGE-05 before inception and over limit | No | V-2 (evaluation order; V-1 first) |
| EDGE-06 over limit, type covered | No | V-4 |
| EDGE-07 lowercase policy number | No | V-1 `POLICY_NOT_FOUND` (case-sensitive) |
| EDGE-08 missing `estimated_amount` | **Yes → 400** | Never |
| EDGE-09 collision on named perils | No | V-5 |
| EDGE-10 cancelled and after expiry | No | V-7 before V-3 (WI-0158 AC-4) |
| EDGE-11 `claim_type` `"flood"` | **Yes → 400** | Never |
| EDGE-12 amount `"3499.999"` | **Yes → 400** | Never |

Day 1 decisions that made EDGE-07 / 11 / 12 classifiable are in `docs/payload-triage.md`.

---

## 6. How to run what we have

From `/workspaces/claims-intake`:

```bash
uv run pytest
uv run ruff check .
uv run mypy
```

Expect 89 unit tests, ruff clean, mypy clean.

---

## 7. What Day 3 will consume

Day 3 should import these names and not invent new payload parsing:

- `NotificationRequest` — already parsed
- `Policy` / `Policy.from_record`
- `RuleFailure` / `RuleId` / `ErrorCode`
- `ClaimRecord`
- `NotificationRepository.record` and `find_matching`

Evaluation order from the contract: `V-1`, `V-2`, `V-7`, `V-3`, `V-4`, `V-5`, `V-6`. V-1 short-circuits if the policy does not exist. V-7 runs before V-3 so a cancelled-and-expired policy is reported as cancelled.

`submit_notification` is the only place that should call `record`, and only after every rule passed.
