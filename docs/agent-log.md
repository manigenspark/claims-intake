# Agent decision log (Day 3)

Record of engineering judgment during the rule-engine work. Each entry names a
real change, the decision, and a reason tied to the contract, a work item, or a
concrete failure — not preference.

---

## Accepted: keep V-6 outside `POLICY_RULES`

**What was produced.** A draft that registered every rule, including duplicate
detection, in one `POLICY_RULES` list so a single loop ran V-1 through V-6.

**Decision.** Accepted the pure list for V-2, V-7, V-3, V-4, and V-5 only.
Run V-1 in `submit_notification` when resolving the policy through the client,
and run V-6 there after `evaluate_notification` returns, using
`repository.find_matching`.

**Reason.** Contract section 4.1 requires order
`V-1 → V-2 → V-7 → V-3 → V-4 → V-5 → V-6`, and the Day 3 brief requires
`evaluate_notification(notification, policy)` to perform no I/O. Putting a
repository lookup inside `POLICY_RULES` would either break that signature or
entangle deciding with doing. Leaving V-6 in `submit_notification` preserves
both the order and the boundary: a refused notification is never passed to
`record`, which is what WI-0151 AC-3 depends on.

---

## Rejected: treat `PolicyLookupFailed` like a missing policy

**What was produced.** A handler that caught a broad failure around
`get_policy` and returned `POLICY_NOT_FOUND` whenever the lookup did not
succeed, so the HTTP layer would only ever see one dependency outcome.

**Decision.** Rejected. Catch only `PolicyNotFound`. Let `PolicyLookupFailed`
propagate from `submit_notification` with its `reason` intact
(`timeout`, `unreachable`, `unparsable`).

**Reason.** Contract section 6 maps those reasons to different statuses (503 vs
500). Collapsing them into V-1 would report that a policy does not exist when
the service does not know — a false statement about the caller's data, and the
failure mode the dependency-boundary rubric calls out. The three-reason
propagation tests in `tests/unit/test_validation.py` exist specifically to
catch that regression.

---

## Gate observation (Step 8)

**Status.** Not yet verified on GitHub.

**What is ready locally.** `.github/workflows/checks.yaml` triggers on
`pull_request`, installs with `uv sync --frozen`, and runs ruff, mypy over
`src` and `tests`, and pytest. No step sets `continue-on-error`. Third-party
actions are pinned to commit SHAs.

**What still has to happen.** Push this branch to a GitHub remote, open a pull
request, push a commit that deliberately fails one check, and observe whether
required status checks **block merge** or only mark the PR. Record the outcome
here. If merge is not blocked, that is a finding about branch protection
configuration, not something to work around in the workflow file.
