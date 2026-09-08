"""Failing tests for the rule engine — written from the contract, not from service.py.

Authority: docs/api-contract.md sections 4.1 and 4.2, and docs/requirements-brief.md
(WI-0142, WI-0151, WI-0158). Every case names the guarantee that would break.

These tests are intentionally committed before the rule implementations exist.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from claims.models import (
    ClaimType,
    ErrorCode,
    NotificationRequest,
    Policy,
    RuleFailure,
    RuleId,
)
from claims.policy_client import PolicyLookupFailed, StubPolicyClient
from claims.repository import NotificationRepository
from claims.service import (
    evaluate_amount_within_limit,
    evaluate_claim_type_covered,
    evaluate_loss_after_inception,
    evaluate_loss_before_expiry,
    evaluate_notification,
    evaluate_policy_exists,
    evaluate_policy_not_cancelled,
    submit_notification,
)


def _notification(
    *,
    policy_number: str = "MOT-4471",
    loss_date: date = date(2026, 4, 2),
    claim_type: ClaimType = "collision",
    estimated_amount: str = "4200.00",
    description: str | None = "test notification",
) -> NotificationRequest:
    return NotificationRequest(
        policy_number=policy_number,
        loss_date=loss_date,
        claim_type=claim_type,
        estimated_amount=Decimal(estimated_amount),
        description=description,
    )


def _policy(policy_number: str, client: StubPolicyClient | None = None) -> Policy:
    return Policy.from_record((client or StubPolicyClient()).get_policy(policy_number))


def _failure(rule: str, code: str) -> RuleFailure:
    return RuleFailure(rule=RuleId(rule), code=ErrorCode(code))


def _assert_pass(result: RuleFailure | None) -> None:
    assert result is None


def _assert_fail(result: RuleFailure | None, rule: str, code: str) -> None:
    assert result == _failure(rule, code)


# ---------------------------------------------------------------------------
# V-1 — policy exists (case-sensitive). Contract §4.2, Day 1 EDGE-07 decision.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("policy_number", "should_pass"),
    [
        ("MOT-4471", True),
        ("MOT-9999", False),
        ("mot-4471", False),
    ],
    ids=[
        "policy_exists",
        "policy_missing",
        "policy_wrong_case_EDGE07",
    ],
)
def test_v1_policy_exists_is_case_sensitive(
    policy_client: StubPolicyClient,
    policy_number: str,
    should_pass: bool,
) -> None:
    notification = _notification(policy_number=policy_number)
    outcome = evaluate_policy_exists(notification, policy_client)
    if should_pass:
        assert outcome.passed is True
    else:
        assert outcome.passed is False
        assert outcome.rule == "V-1"
        assert outcome.code == "POLICY_NOT_FOUND"


# ---------------------------------------------------------------------------
# V-2 — loss_date >= effective_date. Inclusive on inception (WI-0142 AC-3).
# Policy MOT-4479 effective_date = 2026-03-15.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("loss_date", "should_pass"),
    [
        (date(2026, 3, 14), False),
        (date(2026, 3, 15), True),
        (date(2026, 3, 16), True),
    ],
    ids=[
        "before_inception",
        "on_inception_WI0142_AC3",
        "after_inception",
    ],
)
def test_v2_loss_against_inception_boundary(loss_date: date, should_pass: bool) -> None:
    policy = _policy("MOT-4479")
    notification = _notification(
        policy_number="MOT-4479",
        loss_date=loss_date,
        estimated_amount="5000.00",
    )
    result = evaluate_loss_after_inception(notification, policy)
    if should_pass:
        _assert_pass(result)
    else:
        _assert_fail(result, "V-2", "LOSS_BEFORE_INCEPTION")


# ---------------------------------------------------------------------------
# V-7 — cancellation_date is null OR loss_date < cancellation_date.
# Exclusive on the cancellation date (WI-0158 AC-2). Null means N/A (AC-3).
# Policy MOT-4497 cancellation_date = 2026-01-15.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("policy_number", "loss_date", "should_pass"),
    [
        ("MOT-4471", date(2026, 4, 2), True),
        ("MOT-4497", date(2026, 1, 14), True),
        ("MOT-4497", date(2026, 1, 15), False),
        ("MOT-4497", date(2026, 1, 16), False),
    ],
    ids=[
        "cancellation_absent_WI0158_AC3",
        "day_before_cancellation",
        "on_cancellation_date_WI0158_AC2",
        "after_cancellation",
    ],
)
def test_v7_cancellation_boundary_and_absence(
    policy_number: str,
    loss_date: date,
    should_pass: bool,
) -> None:
    policy = _policy(policy_number)
    notification = _notification(
        policy_number=policy_number,
        loss_date=loss_date,
        claim_type="glass" if policy_number == "MOT-4497" else "collision",
        estimated_amount="480.00" if policy_number == "MOT-4497" else "4200.00",
    )
    result = evaluate_policy_not_cancelled(notification, policy)
    if should_pass:
        _assert_pass(result)
    else:
        _assert_fail(result, "V-7", "POLICY_CANCELLED")


# ---------------------------------------------------------------------------
# V-3 — loss_date <= expiry_date. Inclusive on expiry. Contract §4.2.
# Policy MOT-4489 expiry_date = 2026-02-28.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("loss_date", "should_pass"),
    [
        (date(2026, 2, 27), True),
        (date(2026, 2, 28), True),
        (date(2026, 3, 1), False),
    ],
    ids=[
        "before_expiry",
        "on_expiry",
        "after_expiry",
    ],
)
def test_v3_loss_against_expiry_boundary(loss_date: date, should_pass: bool) -> None:
    policy = _policy("MOT-4489")
    notification = _notification(
        policy_number="MOT-4489",
        loss_date=loss_date,
        claim_type="theft",
        estimated_amount="9000.00",
    )
    result = evaluate_loss_before_expiry(notification, policy)
    if should_pass:
        _assert_pass(result)
    else:
        _assert_fail(result, "V-3", "LOSS_AFTER_EXPIRY")


# ---------------------------------------------------------------------------
# V-4 — estimated_amount <= limit. Inclusive at the limit. Contract §4.2.
# Policy MOT-4502 limit = 10000.00.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("estimated_amount", "should_pass"),
    [
        ("9999.99", True),
        ("10000.00", True),
        ("10000.01", False),
    ],
    ids=[
        "below_limit",
        "equal_to_limit",
        "above_limit",
    ],
)
def test_v4_amount_against_limit_boundary(
    estimated_amount: str,
    should_pass: bool,
) -> None:
    policy = _policy("MOT-4502")
    notification = _notification(
        policy_number="MOT-4502",
        loss_date=date(2026, 3, 11),
        estimated_amount=estimated_amount,
    )
    result = evaluate_amount_within_limit(notification, policy)
    if should_pass:
        _assert_pass(result)
    else:
        _assert_fail(result, "V-4", "AMOUNT_EXCEEDS_LIMIT")


# ---------------------------------------------------------------------------
# V-5 — claim_type in permitted_claim_types. Contract §4.2 / §2.3.
# MOT-4481 named perils: no collision. MOT-4486 liability only.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("policy_number", "claim_type", "should_pass"),
    [
        ("MOT-4481", "theft", True),
        ("MOT-4481", "collision", False),
        ("MOT-4486", "liability", True),
        ("MOT-4486", "collision", False),
    ],
    ids=[
        "type_permitted_named_perils",
        "type_not_covered_named_perils",
        "type_permitted_liability_only",
        "type_not_covered_liability_only",
    ],
)
def test_v5_claim_type_against_product_vocabulary(
    policy_number: str,
    claim_type: ClaimType,
    should_pass: bool,
) -> None:
    policy = _policy(policy_number)
    notification = _notification(
        policy_number=policy_number,
        loss_date=date(2026, 3, 14),
        claim_type=claim_type,
        estimated_amount="6200.00",
    )
    result = evaluate_claim_type_covered(notification, policy)
    if should_pass:
        _assert_pass(result)
    else:
        _assert_fail(result, "V-5", "TYPE_NOT_COVERED")


# ---------------------------------------------------------------------------
# evaluate_notification — pure (notification + policy only). Order §4.1:
# V-2, V-7, V-3, V-4, V-5. First failure wins. WI-0158 AC-4: V-7 before V-3.
# ---------------------------------------------------------------------------


def test_evaluate_notification_returns_none_when_all_policy_rules_pass() -> None:
    policy = _policy("MOT-4471")
    notification = _notification()
    assert evaluate_notification(notification, policy) is None


def test_evaluate_notification_reports_v7_before_v3_when_both_would_fail() -> None:
    # MOT-4500: cancelled 2025-10-01, original expiry 2025-12-31.
    # Loss 2026-01-08 is after cancellation AND after expiry.
    policy = _policy("MOT-4500")
    notification = _notification(
        policy_number="MOT-4500",
        loss_date=date(2026, 1, 8),
        estimated_amount="6000.00",
    )
    result = evaluate_notification(notification, policy)
    _assert_fail(result, "V-7", "POLICY_CANCELLED")


@pytest.mark.parametrize(
    ("policy_number", "loss_date", "claim_type", "estimated_amount", "rule", "code"),
    [
        (
            "MOT-4479",
            date(2026, 3, 14),
            "collision",
            "5000.00",
            "V-2",
            "LOSS_BEFORE_INCEPTION",
        ),
        (
            "MOT-4497",
            date(2026, 1, 15),
            "glass",
            "480.00",
            "V-7",
            "POLICY_CANCELLED",
        ),
        (
            "MOT-4489",
            date(2026, 3, 20),
            "theft",
            "8000.00",
            "V-3",
            "LOSS_AFTER_EXPIRY",
        ),
        (
            "MOT-4502",
            date(2026, 3, 8),
            "collision",
            "14500.00",
            "V-4",
            "AMOUNT_EXCEEDS_LIMIT",
        ),
        (
            "MOT-4486",
            date(2026, 3, 14),
            "collision",
            "6200.00",
            "V-5",
            "TYPE_NOT_COVERED",
        ),
    ],
    ids=[
        "stops_at_v2",
        "stops_at_v7",
        "stops_at_v3",
        "stops_at_v4",
        "stops_at_v5",
    ],
)
def test_evaluate_notification_stops_at_first_failing_policy_rule(
    policy_number: str,
    loss_date: date,
    claim_type: ClaimType,
    estimated_amount: str,
    rule: str,
    code: str,
) -> None:
    policy = _policy(policy_number)
    notification = _notification(
        policy_number=policy_number,
        loss_date=loss_date,
        claim_type=claim_type,
        estimated_amount=estimated_amount,
    )
    _assert_fail(evaluate_notification(notification, policy), rule, code)


# ---------------------------------------------------------------------------
# submit_notification — orchestration, V-1, V-6, recording, dependency boundary.
# ---------------------------------------------------------------------------


@pytest.fixture
def repository() -> NotificationRepository:
    return NotificationRepository(recording_year=2026)


def test_submit_notification_records_when_every_rule_passes(
    policy_client: StubPolicyClient,
    repository: NotificationRepository,
) -> None:
    notification = _notification()
    outcome = submit_notification(notification, policy_client, repository)
    assert outcome.accepted is True
    assert outcome.failure is None
    assert outcome.claim_reference == "CLM-2026-000001"


def test_submit_notification_maps_policy_not_found_to_v1(
    policy_client: StubPolicyClient,
    repository: NotificationRepository,
) -> None:
    notification = _notification(policy_number="MOT-9999")
    outcome = submit_notification(notification, policy_client, repository)
    assert outcome.accepted is False
    assert outcome.claim_reference is None
    assert outcome.failure == _failure("V-1", "POLICY_NOT_FOUND")
    assert repository.recorded_claims() == ()


@pytest.mark.parametrize(
    "reason",
    ["timeout", "unreachable", "unparsable"],
    ids=["timeout", "unreachable", "unparsable"],
)
def test_submit_notification_propagates_policy_lookup_failed_for_each_reason(
    repository: NotificationRepository,
    reason: str,
) -> None:
    client = StubPolicyClient(fail_with=reason)  # type: ignore[arg-type]
    notification = _notification()
    with pytest.raises(PolicyLookupFailed) as exc_info:
        submit_notification(notification, client, repository)
    assert exc_info.value.reason == reason
    assert repository.recorded_claims() == ()


def test_submit_notification_rejects_duplicate_on_three_field_match(
    policy_client: StubPolicyClient,
    repository: NotificationRepository,
) -> None:
    notification = _notification()
    first = submit_notification(notification, policy_client, repository)
    assert first.accepted is True

    duplicate = _notification(description="resubmission after portal timeout")
    second = submit_notification(duplicate, policy_client, repository)
    assert second.accepted is False
    assert second.failure == _failure("V-6", "DUPLICATE_NOTIFICATION")
    assert second.claim_reference is None
    assert len(repository.recorded_claims()) == 1


@pytest.mark.parametrize(
    ("policy_number", "loss_date", "claim_type"),
    [
        ("MOT-4472", date(2026, 4, 2), "collision"),
        ("MOT-4471", date(2026, 4, 3), "collision"),
        ("MOT-4471", date(2026, 4, 2), "theft"),
    ],
    ids=[
        "different_policy_number_only",
        "different_loss_date_only",
        "different_claim_type_only",
    ],
)
def test_submit_notification_two_of_three_fields_is_not_a_duplicate(
    policy_client: StubPolicyClient,
    repository: NotificationRepository,
    policy_number: str,
    loss_date: date,
    claim_type: ClaimType,
) -> None:
    original = _notification()
    assert submit_notification(original, policy_client, repository).accepted is True

    other = _notification(
        policy_number=policy_number,
        loss_date=loss_date,
        claim_type=claim_type,
        estimated_amount="12500.00" if claim_type == "theft" else "4200.00",
    )
    # MOT-4472 / theft paths must still be admissible on their own policy.
    outcome = submit_notification(other, policy_client, repository)
    assert outcome.accepted is True
    assert outcome.failure is None


def test_submit_notification_rejected_notification_is_not_a_duplicate_WI0151_AC3(
    policy_client: StubPolicyClient,
    repository: NotificationRepository,
) -> None:
    # Same policy_number, loss_date, and claim_type as the later success.
    # First submission fails V-4, so nothing is recorded (WI-0151 AC-3).
    refused = _notification(
        policy_number="MOT-4502",
        loss_date=date(2026, 3, 11),
        estimated_amount="14500.00",
    )
    refused_outcome = submit_notification(refused, policy_client, repository)
    assert refused_outcome.accepted is False
    assert refused_outcome.failure == _failure("V-4", "AMOUNT_EXCEEDS_LIMIT")
    assert repository.recorded_claims() == ()

    # Resubmit with an admissible amount. Matching keys must not be treated as
    # a duplicate because the refusal never created a claim record.
    admissible = _notification(
        policy_number="MOT-4502",
        loss_date=date(2026, 3, 11),
        estimated_amount="1250.00",
    )
    outcome = submit_notification(admissible, policy_client, repository)
    assert outcome.accepted is True
    assert outcome.claim_reference == "CLM-2026-000001"
    assert len(repository.recorded_claims()) == 1


def test_submit_notification_does_not_record_when_a_policy_rule_fails(
    policy_client: StubPolicyClient,
    repository: NotificationRepository,
) -> None:
    notification = _notification(
        policy_number="MOT-4502",
        loss_date=date(2026, 3, 8),
        estimated_amount="14500.00",
    )
    outcome = submit_notification(notification, policy_client, repository)
    assert outcome.accepted is False
    assert outcome.failure == _failure("V-4", "AMOUNT_EXCEEDS_LIMIT")
    assert repository.recorded_claims() == ()
