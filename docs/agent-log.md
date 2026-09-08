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

**PR.** https://github.com/manigenspark/claims-intake/pull/1  
**Deliberate failure.** Commit `a01ecf1` introduced invalid Python syntax in `src/claims/service.py`.  
**Checks.** Job `checks / ruff, mypy, pytest` failed after ~12s.  
**Merge.** Not blocked. GitHub still showed “Merging can be performed automatically” while the check was red.

**Detail.** The workflow correctly refused the bad commit (the check failed). Merge into `main` was still allowed because no branch protection / ruleset requires that status check. Per the assignment, that is a finding about repository configuration, not a defect in `checks.yaml`.
