"""Rule evaluation and notification submission.

This module owns the decision. It does not know it was reached over HTTP, which
is why it can be tested by calling a function with a typed object and asserting on
the result with no server running. Status codes live at the HTTP boundary
(contract section 6).

V-6 placement (contract section 4.1): ``POLICY_RULES`` holds only pure functions of
a notification and a policy (V-2, V-7, V-3, V-4, V-5). V-1 needs the policy client
and V-6 needs the repository, so both run in ``submit_notification``. That keeps
evaluation order ``V-1 → V-2 → V-7 → V-3 → V-4 → V-5 → V-6`` without a repository
lookup inside ``POLICY_RULES``, preserving the separation between deciding and
doing.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from claims.models import ErrorCode, NotificationRequest, Policy, RuleFailure, RuleId
from claims.policy_client import PolicyClient, PolicyNotFound
from claims.repository import NotificationRepository

PolicyRule = Callable[[NotificationRequest, Policy], RuleFailure | None]


def _fail(rule: str, code: str) -> RuleFailure:
    return RuleFailure(rule=RuleId(rule), code=ErrorCode(code))


@dataclass(frozen=True)
class ValidationOutcome:
    """Result of submitting a notification (and of the V-1 existence check).

    ``accepted`` is the branch the HTTP layer needs. On success,
    ``claim_reference`` is set. On refusal, ``failure`` carries the rule id and
    contract code, and ``detail`` carries the values section 5 documents for
    that code. ``passed`` / ``rule`` / ``code`` mirror those fields so the
    existing V-1 helper stays readable.
    """

    accepted: bool
    claim_reference: str | None = None
    failure: RuleFailure | None = None
    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.accepted

    @property
    def rule(self) -> str | None:
        if self.failure is None:
            return None
        return str(self.failure.rule)

    @property
    def code(self) -> str | None:
        if self.failure is None:
            return None
        return str(self.failure.code)

    @classmethod
    def ok(cls, claim_reference: str | None = None) -> ValidationOutcome:
        return cls(accepted=True, claim_reference=claim_reference)

    @classmethod
    def rejected(
        cls,
        failure: RuleFailure,
        *,
        detail: dict[str, Any] | None = None,
    ) -> ValidationOutcome:
        return cls(accepted=False, failure=failure, detail=detail or {})


def evaluate_policy_exists(
    notification: NotificationRequest,
    policy_client: PolicyClient,
) -> ValidationOutcome:
    """V-1. The policy must exist in the policy master.

    ``PolicyNotFound`` is a fact about the caller's data and becomes a refusal.
    ``PolicyLookupFailed`` is deliberately not caught: the caller did nothing
    wrong and Day 4 maps ``reason`` to the correct 5xx status.
    """
    try:
        policy_client.get_policy(notification.policy_number)
    except PolicyNotFound:
        return ValidationOutcome.rejected(_fail("V-1", "POLICY_NOT_FOUND"))
    return ValidationOutcome.ok()


def evaluate_loss_after_inception(
    notification: NotificationRequest,
    policy: Policy,
) -> RuleFailure | None:
    """V-2. loss_date >= effective_date (inclusive on inception, WI-0142 AC-3)."""
    if notification.loss_date >= policy.effective_date:
        return None
    return _fail("V-2", "LOSS_BEFORE_INCEPTION")


def evaluate_policy_not_cancelled(
    notification: NotificationRequest,
    policy: Policy,
) -> RuleFailure | None:
    """V-7. cancellation_date is null, or loss_date < cancellation_date.

    Null means the policy was not cancelled (WI-0158 AC-3). A loss on the
    cancellation date itself is not covered (AC-2): comparison is strict ``<``.
    """
    if policy.cancellation_date is None:
        return None
    if notification.loss_date < policy.cancellation_date:
        return None
    return _fail("V-7", "POLICY_CANCELLED")


def evaluate_loss_before_expiry(
    notification: NotificationRequest,
    policy: Policy,
) -> RuleFailure | None:
    """V-3. loss_date <= expiry_date (inclusive on expiry)."""
    if notification.loss_date <= policy.expiry_date:
        return None
    return _fail("V-3", "LOSS_AFTER_EXPIRY")


def evaluate_amount_within_limit(
    notification: NotificationRequest,
    policy: Policy,
) -> RuleFailure | None:
    """V-4. estimated_amount <= limit (inclusive at the limit)."""
    if notification.estimated_amount <= policy.limit:
        return None
    return _fail("V-4", "AMOUNT_EXCEEDS_LIMIT")


def evaluate_claim_type_covered(
    notification: NotificationRequest,
    policy: Policy,
) -> RuleFailure | None:
    """V-5. claim_type must be permitted on the policy's product."""
    if notification.claim_type in policy.permitted_claim_types:
        return None
    return _fail("V-5", "TYPE_NOT_COVERED")


# Contract section 4.1 order for rules that only need notification + policy.
# V-7 before V-3 so cancelled-and-expired reports POLICY_CANCELLED (WI-0158 AC-4).
POLICY_RULES: Sequence[PolicyRule] = (
    evaluate_loss_after_inception,
    evaluate_policy_not_cancelled,
    evaluate_loss_before_expiry,
    evaluate_amount_within_limit,
    evaluate_claim_type_covered,
)


def evaluate_notification(
    notification: NotificationRequest,
    policy: Policy,
) -> RuleFailure | None:
    """Run pure policy-field rules in contract order. No I/O, no writes."""
    for rule in POLICY_RULES:
        failure = rule(notification, policy)
        if failure is not None:
            return failure
    return None


def submit_notification(
    notification: NotificationRequest,
    policy_client: PolicyClient,
    repository: NotificationRepository,
) -> ValidationOutcome:
    """Resolve the policy, evaluate, and record only if every rule passed.

    Order: V-1 (lookup), then ``evaluate_notification`` (V-2…V-5), then V-6
    (repository). ``PolicyLookupFailed`` propagates uncaught.
    """
    try:
        record = policy_client.get_policy(notification.policy_number)
    except PolicyNotFound:
        return ValidationOutcome.rejected(_fail("V-1", "POLICY_NOT_FOUND"))

    policy = Policy.from_record(record)
    failure = evaluate_notification(notification, policy)
    if failure is not None:
        return ValidationOutcome.rejected(failure)

    # V-6: duplicate detection against recorded claims only (WI-0151 AC-1, AC-3).
    existing = repository.find_matching(
        notification.policy_number,
        notification.loss_date,
        notification.claim_type,
    )
    if existing is not None:
        return ValidationOutcome.rejected(
            _fail("V-6", "DUPLICATE_NOTIFICATION"),
            detail={"claim_reference": existing.claim_reference},
        )

    recorded = repository.record(notification)
    return ValidationOutcome.ok(claim_reference=recorded.claim_reference)
