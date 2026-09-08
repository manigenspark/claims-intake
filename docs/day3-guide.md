# Day 3 Guide: Build the Rule Engine Test-First and Gate It

This guide is written for *this* repository as it stands after Day 2.
Read it top to bottom before writing code. The **order is graded**.

---

## Where you are right now

| Piece | Status |
| --- | --- |
| Day 1 contract sections 4–6 + payload triage | Done |
| Day 2 models + repository + unit tests | Done |
| `src/claims/service.py` | Starter only: V-1 pattern written; V-2–V-7 / orchestration still `NotImplementedError` |
| `tests/unit/test_validation.py` | **Missing** |
| `.github/workflows/checks.yaml` | **Missing** |
| `docs/agent-log.md` | **Missing** |
| Git history with “tests before implementation” | **Missing** — this folder has no `.git` yet |

Without git commits in the right order, the 20-point **test-first evidence** rubric cannot be scored. Fix that first.

---

## What Day 3 is really about

Three strands meet:

1. **Contract (Day 1)** — what each rule means, boundaries, evaluation order, codes.
2. **Models (Day 2)** — rules operate on `NotificationRequest` and `Policy`, never on raw dicts.
3. **Today** — write tests from the contract *first*, implement against those tests, then put a CI gate in front so the suite keeps refusing bad changes.

Out of scope (Day 4): `api/routes.py`, Dockerfile, integration tests.

---

## The mental model

```
submit_notification(notification, client, repository)
    │
    ├─ client.get_policy(...)
    │     ├─ PolicyNotFound      → V-1 RuleFailure (POLICY_NOT_FOUND)   ← catch this
    │     └─ PolicyLookupFailed  → propagate unchanged                  ← do NOT catch
    │
    ├─ evaluate_notification(notification, policy)   ← pure: no I/O, no repo
    │     runs POLICY_RULES in contract order: V-2, V-7, V-3, V-4, V-5
    │     returns RuleFailure | None
    │
    ├─ V-6 duplicate check via repository.find_matching(...)
    │     (NOT inside POLICY_RULES — see decision below)
    │
    └─ if all passed → repository.record(...) → success with claim_reference
```

### Why V-6 is not inside `POLICY_RULES`

`POLICY_RULES` should be pure functions of `(notification, policy)`.
V-6 needs the **repository** (what was already recorded). Putting a repo lookup inside `POLICY_RULES` entangles *deciding* with *doing*.

**Decision (record this in a comment in `service.py`):**

- V-1 runs in `submit_notification` when resolving the policy (needs the client).
- V-2, V-7, V-3, V-4, V-5 run inside `evaluate_notification` via `POLICY_RULES`.
- V-6 runs in `submit_notification` after `evaluate_notification` returns `None`, using `repository.find_matching`.

That preserves contract section 4.1 order:

`V-1 → V-2 → V-7 → V-3 → V-4 → V-5 → V-6`

without a repository inside `POLICY_RULES`.

### Dependency boundary (20 rubric points)

| Exception | Meaning | Service behavior |
| --- | --- | --- |
| `PolicyNotFound` | Master answered: no such policy | Become V-1 / `POLICY_NOT_FOUND` |
| `PolicyLookupFailed` | Master did not produce an answer (`timeout` / `unreachable` / `unparsable`) | **Do not catch.** Day 4 maps `reason` to 503/500 |

Catching `Exception` or catching `PolicyLookupFailed` and turning it into “policy not found” is an **Inadequate** score: the service would lie that a policy does not exist when it simply does not know.

### Interface to fix (C3)

The starter signatures do not match the graded interface. Align them:

| Function | Graded shape |
| --- | --- |
| `evaluate_notification` | `(notification, policy) -> RuleFailure \| None` — no client, no repo, no writes |
| `submit_notification` | `(notification, client, repository) -> ValidationOutcome` — accepted + claim ref, or rule failure |
| Individual rules | Prefer returning `RuleFailure \| None` (or keep `ValidationOutcome` consistently — but Day 3 brief wants `RuleFailure`) |

`RuleFailure` already exists in `models.py` (`rule: RuleId`, `code: ErrorCode`).

`ValidationOutcome` for **submit** should carry:

- whether accepted
- `claim_reference` if accepted
- the `RuleFailure` if refused

(You can reshape the existing starter dataclass; Day 4 will call `submit_notification`.)

---

## Rule cheat sheet (write tests from this — not from `service.py`)

Contract section 4.2 + boundary notes. Use `date(...)` and `Decimal("...")` in tests.

| Rule | Pass when | Fail code | Boundary cases you must test |
| --- | --- | --- | --- |
| **V-1** | Policy exists (exact case) | `POLICY_NOT_FOUND` | exists; missing; lowercase vs uppercase (EDGE-07 style) |
| **V-2** | `loss_date >= effective_date` | `LOSS_BEFORE_INCEPTION` | day before (fail); **on inception (pass, WI-0142 AC-3)**; day after (pass) |
| **V-7** | `cancellation_date is None` **or** `loss_date < cancellation_date` | `POLICY_CANCELLED` | null cancellation (pass, WI-0158 AC-3); day before cancel (pass); **on cancel day (fail, AC-2)**; after cancel (fail) |
| **V-3** | `loss_date <= expiry_date` | `LOSS_AFTER_EXPIRY` | day before expiry (pass); **on expiry (pass)**; day after (fail) |
| **V-4** | `estimated_amount <= limit` | `AMOUNT_EXCEEDS_LIMIT` | below (pass); **equal (pass)**; above (fail) |
| **V-5** | `claim_type in permitted_claim_types` | `TYPE_NOT_COVERED` | permitted (pass); not permitted (fail) |
| **V-6** | no recorded match on all three fields | `DUPLICATE_NOTIFICATION` | exact three-field match (fail); two-of-three (pass); **prior refusal never recorded → not duplicate (WI-0151 AC-3)** |

Also test:

- **Evaluation order**: a case that would fail several rules returns the *first* in section 4.1 order (e.g. cancelled *and* after expiry → `POLICY_CANCELLED`, not `LOSS_AFTER_EXPIRY` — WI-0158 AC-4).
- **`PolicyLookupFailed`**: for each of `timeout`, `unreachable`, `unparsable`, `submit_notification` re-raises with `reason` intact.

Use real policies from `data/policies.json` via `StubPolicyClient` / `Policy.from_record` where helpful. Build notifications with `NotificationRequest(...)` using `date` and `Decimal` — never floats or date strings in assertions.

---

## Step-by-step plan (do not skip steps)

### Step 0 — Make git history possible (blocker)

```bash
cd /workspaces/claims-intake
git init
git add -A
git commit -m "Baseline: Day 1 contract and Day 2 boundary models"
```

You need a branch you can push later for Step 8 (PR + deliberate failing check).

### Step 1 — Write failing tests only

Create `tests/unit/test_validation.py`.

Rules while writing:

- Open `docs/api-contract.md` and `docs/requirements-brief.md`.
- **Do not open `service.py`** to invent expected behavior.
- One parametrized test (or clear group) per rule, with **named ids**.
- Every comparison: below / on / above (or absent where AC requires it).
- Import the functions you *expect* to exist (`evaluate_loss_after_inception`, etc.). If names differ from the stub, match the stub names so imports resolve after stubs exist — but assert from the contract.

Structure sketch:

```python
@pytest.mark.parametrize(
    ("case_id", "loss_date", "should_pass"),
    [
        ("before_inception", date(2026, 3, 14), False),
        ("on_inception_WI0142_AC3", date(2026, 3, 15), True),
        ("after_inception", date(2026, 3, 16), True),
    ],
    ids=["before_inception", "on_inception_WI0142_AC3", "after_inception"],
)
def test_v2_loss_against_inception(...):
    ...
```

Also cover `submit_notification` for:

- happy path → recorded + claim reference
- V-1 via `PolicyNotFound`
- V-6 duplicate + WI-0151 AC-3
- `PolicyLookupFailed` × 3 reasons propagates

### Step 2 — Make failures meaningful

Run:

```bash
uv run pytest tests/unit/test_validation.py -q
```

If you get `ImportError` / missing symbol, that failure is **not** useful. Add or keep stubs in `service.py` that raise `NotImplementedError` (or return a wrong fixed value) so tests fail on **assertions**.

Confirm one failure message shows the expected code / outcome.

### Step 3 — Commit the failing tests (evidence)

```bash
git add tests/unit/test_validation.py
# only stubs if you had to touch service.py for imports — no real rule logic yet
git commit -m "Add failing validation tests for rules V-1 through V-7"
```

`git log` must show this commit **before** any commit that implements the rules.
Do **not** edit these tests later without a contract line justifying it.

### Step 4 — Decide V-6 placement (already decided above)

Write the comment in `service.py` next to `POLICY_RULES` / `submit_notification`.

### Step 5 — Implement rules against the tests

Implement only what the tests demand:

- V-2: `loss_date >= effective_date`
- V-7: null → pass; else `loss_date < cancellation_date`
- V-3: `loss_date <= expiry_date`
- V-4: `estimated_amount <= limit`
- V-5: membership in `permitted_claim_types`
- Wire `POLICY_RULES` in order `V-2, V-7, V-3, V-4, V-5`
- `evaluate_notification(notification, policy)` loops until first `RuleFailure`

**Do not modify the tests.** Review with the contract open: check boundaries and what is *absent* (e.g. did someone catch `PolicyLookupFailed`?).

### Step 6 — Implement `submit_notification`

1. `get_policy` — catch only `PolicyNotFound` → V-1 failure outcome.
2. `evaluate_notification` — if failure, return it (do not record).
3. `find_matching` — if match, V-6 failure with existing claim reference available for Day 4 detail.
4. Else `record` and return success with the new claim reference.

No broad `except Exception`.

### Step 7 — Author the pipeline

Create `.github/workflows/checks.yaml`:

- Trigger: `pull_request`
- Install from lockfile **without re-resolving** (e.g. `uv sync --frozen`)
- Steps: `ruff check`, `mypy` (source **and** tests), `pytest`
- Every step must be allowed to fail the job (no `continue-on-error: true`)
- Pin third-party actions to full commit SHAs (or at least version tags; SHA is stronger)

### Step 8 — Confirm the gate

1. Push branch, open a PR.
2. Push a commit that deliberately fails (e.g. `assert False` or a lint error).
3. Observe: does GitHub **block merge**, or only show a red check?
4. Record the observation in `docs/agent-log.md` or a short note in the PR / agent log.
5. If merge is not blocked, that is a **finding about branch protection** — report it; do not silently work around it.
6. Revert the deliberate failure.

If you cannot open a real PR from this environment, record that limitation and what you would verify.

### Step 9 — Agent decision log

Create `docs/agent-log.md` with **two** entries:

1. One change you **accepted** (cite contract section / AC / concrete failure prevented).
2. One change you **rejected or corrected** (same — preference does not count).

Example shape:

```markdown
## Accepted: V-7 before V-3 in evaluation order

**Produced.** Agent ordered rules V-1…V-7 numerically.
**Decision.** Rejected; use section 4.1 order with V-7 before V-3.
**Reason.** WI-0158 AC-4 / contract §4.1: cancelled-and-expired must return POLICY_CANCELLED, not LOSS_AFTER_EXPIRY.
```

---

## Acceptance checklist (binary)

- [ ] `git log` shows validation tests committed before rule implementation
- [ ] Parametrized tests with named ids for V-1 … V-7
- [ ] Each comparison: both sides + boundary
- [ ] V-2 on inception = pass; V-7 on cancellation = fail
- [ ] WI-0158 AC-3: absent `cancellation_date`
- [ ] WI-0151 AC-3: rejected notification not a duplicate
- [ ] No post-implementation edits to `test_validation.py` without contract justification
- [ ] `evaluate_notification` is pure (notification + policy only)
- [ ] `PolicyNotFound` → V-1; `PolicyLookupFailed` propagates for all three reasons
- [ ] No overly broad exception handlers
- [ ] Order matches §4.1; V-6 outside `POLICY_RULES` with a recorded reason
- [ ] `checks.yaml` on PRs, frozen install, ruff + mypy(src+tests) + pytest, pinned actions
- [ ] Gate observation recorded
- [ ] `agent-log.md` two judgment entries with references
- [ ] `ruff` / `mypy` / full suite green

---

## Suggested commit sequence (for the rubric)

1. Baseline Day 1–2 (if repo is new)
2. **Failing** `test_validation.py` (+ stubs only if required)
3. Rule implementations + `evaluate_notification` + `submit_notification`
4. `.github/workflows/checks.yaml`
5. `docs/agent-log.md` (+ gate observation)
6. Deliberate failing commit on a PR branch, then fix commit (optional but needed for Step 8 evidence)

---

## How we will work next

Next executable actions in this workspace:

1. Initialize git and commit the Day 2 baseline.
2. Write `tests/unit/test_validation.py` from the contract (failing).
3. Commit those tests.
4. Implement `service.py` until tests pass — **without changing the tests**.
5. Add the workflow and agent log.

Say when to start Step 0, and we proceed in that order.
