"""Unit tests for notification recording and duplicate detection.

Fixtures return a new repository and new request objects on every use so the
suite is order-independent. Duplicate matching is the three-field composite
from WI-0151 AC-1. The store holds ``ClaimRecord`` values only, which is why a
refused notification cannot be a duplicate (WI-0151 AC-3).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from claims.models import ClaimRecord, NotificationRequest
from claims.repository import NotificationRepository


@pytest.fixture
def repository() -> NotificationRepository:
    return NotificationRepository(recording_year=2026)


@pytest.fixture
def sample_notification() -> NotificationRequest:
    return NotificationRequest(
        policy_number="MOT-4471",
        loss_date=date(2026, 4, 2),
        claim_type="collision",
        estimated_amount=Decimal("4200.00"),
        description="Rear ended at a junction.",
    )


@pytest.fixture
def other_notification() -> NotificationRequest:
    return NotificationRequest(
        policy_number="MOT-4472",
        loss_date=date(2026, 3, 18),
        claim_type="theft",
        estimated_amount=Decimal("12500.00"),
        description="Vehicle taken overnight from a driveway.",
    )


def test_record_issues_claim_reference_matching_contract_pattern(
    repository: NotificationRepository,
    sample_notification: NotificationRequest,
) -> None:
    recorded = repository.record(sample_notification)
    assert isinstance(recorded, ClaimRecord)
    assert recorded.claim_reference == "CLM-2026-000001"
    assert recorded.policy_number == sample_notification.policy_number
    assert recorded.loss_date == date(2026, 4, 2)
    assert recorded.claim_type == sample_notification.claim_type
    assert recorded.estimated_amount == Decimal("4200.00")
    assert recorded.description == sample_notification.description


def test_record_issues_unique_claim_references(
    repository: NotificationRepository,
    sample_notification: NotificationRequest,
    other_notification: NotificationRequest,
) -> None:
    first = repository.record(sample_notification)
    second = repository.record(other_notification)
    assert first.claim_reference == "CLM-2026-000001"
    assert second.claim_reference == "CLM-2026-000002"
    assert first.claim_reference != second.claim_reference


def test_find_matching_returns_claim_record_on_three_field_match(
    repository: NotificationRepository,
    sample_notification: NotificationRequest,
) -> None:
    recorded = repository.record(sample_notification)
    match = repository.find_matching(
        sample_notification.policy_number,
        sample_notification.loss_date,
        sample_notification.claim_type,
    )
    assert match is not None
    assert isinstance(match, ClaimRecord)
    assert match.claim_reference == recorded.claim_reference
    assert match.loss_date == date(2026, 4, 2)
    assert match.estimated_amount == Decimal("4200.00")


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
def test_find_matching_does_not_treat_two_of_three_fields_as_duplicate(
    repository: NotificationRepository,
    sample_notification: NotificationRequest,
    policy_number: str,
    loss_date: date,
    claim_type: str,
) -> None:
    repository.record(sample_notification)
    assert repository.find_matching(policy_number, loss_date, claim_type) is None


def test_repository_has_no_write_path_for_a_refused_notification() -> None:
    # WI-0151 AC-3 is structural: the only persistable type is ClaimRecord,
    # and the only write method is record().
    assert not hasattr(NotificationRepository, "reject")
    assert not hasattr(NotificationRepository, "record_rejection")
    assert not hasattr(NotificationRepository, "record_failure")


def test_find_matching_searches_only_recorded_claim_records(
    repository: NotificationRepository,
    sample_notification: NotificationRequest,
    other_notification: NotificationRequest,
) -> None:
    # A well-formed request that rules would refuse is still only a
    # NotificationRequest. It cannot appear in find_matching because that
    # method reads recorded_claims(), which starts empty (WI-0151 AC-3).
    assert repository.recorded_claims() == ()
    assert (
        repository.find_matching(
            sample_notification.policy_number,
            sample_notification.loss_date,
            sample_notification.claim_type,
        )
        is None
    )

    accepted = repository.record(other_notification)
    stored = repository.recorded_claims()
    assert stored == (accepted,)
    assert stored[0].policy_number == other_notification.policy_number
    assert (
        repository.find_matching(
            sample_notification.policy_number,
            sample_notification.loss_date,
            sample_notification.claim_type,
        )
        is None
    )

    recorded = repository.record(sample_notification)
    assert recorded.claim_reference == "CLM-2026-000002"
    match = repository.find_matching(
        sample_notification.policy_number,
        sample_notification.loss_date,
        sample_notification.claim_type,
    )
    assert match is not None
    assert match.claim_reference == recorded.claim_reference
