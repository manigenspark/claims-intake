"""Unit tests for the request, policy, and record models.

Every constraint declared on ``NotificationRequest`` has a case that violates it.
Payloads from ``data/fnol_*.json`` are classified as failing at this boundary or
surviving to the rules. Dates and amounts are asserted as ``date`` and
``Decimal``, never as strings or floats.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from claims.models import (
    ClaimRecord,
    ErrorCode,
    NotificationRequest,
    Policy,
    RuleFailure,
    RuleId,
)
from claims.policy_client import StubPolicyClient
from tests.unit.payload_data import (
    EDGE_CASES_THAT_SURVIVE_THE_MODEL,
    EDGE_PAYLOADS,
    INVALID_PAYLOADS,
    VALID_PAYLOADS,
    payload_omitting,
    well_formed_payload,
)


def _error_locations(exc_info: pytest.ExceptionInfo[ValidationError]) -> list[object]:
    return [error["loc"][0] for error in exc_info.value.errors()]


@pytest.mark.parametrize(
    "case_id",
    list(VALID_PAYLOADS),
    ids=[f"accepts_{case_id}" for case_id in VALID_PAYLOADS],
)
def test_notification_request_accepts_fnol_valid_payloads(case_id: str) -> None:
    payload = VALID_PAYLOADS[case_id]
    parsed = NotificationRequest.model_validate(payload)

    policy_number = payload["policy_number"]
    loss_date_raw = payload["loss_date"]
    amount_raw = payload["estimated_amount"]
    assert isinstance(policy_number, str)
    assert isinstance(loss_date_raw, str)
    assert isinstance(amount_raw, str)

    assert parsed.policy_number == policy_number
    assert type(parsed.loss_date) is date
    assert parsed.loss_date == date.fromisoformat(loss_date_raw)
    assert type(parsed.estimated_amount) is Decimal
    assert parsed.estimated_amount == Decimal(amount_raw)
    if "description" not in payload:
        assert parsed.description is None
    else:
        assert parsed.description == payload["description"]


@pytest.mark.parametrize(
    "case_id",
    list(INVALID_PAYLOADS),
    ids=[f"survives_to_rules_{case_id}" for case_id in INVALID_PAYLOADS],
)
def test_notification_request_accepts_fnol_invalid_payloads(case_id: str) -> None:
    NotificationRequest.model_validate(INVALID_PAYLOADS[case_id])


@pytest.mark.parametrize(
    "case_id",
    EDGE_CASES_THAT_SURVIVE_THE_MODEL,
    ids=[f"survives_to_rules_{case_id}" for case_id in EDGE_CASES_THAT_SURVIVE_THE_MODEL],
)
def test_notification_request_accepts_edge_payloads_that_reach_the_rules(
    case_id: str,
) -> None:
    NotificationRequest.model_validate(EDGE_PAYLOADS[case_id])


@pytest.mark.parametrize(
    "claim_type",
    ["collision", "theft", "glass", "liability", "weather"],
    ids=[
        "vocabulary_collision",
        "vocabulary_theft",
        "vocabulary_glass",
        "vocabulary_liability",
        "vocabulary_weather",
    ],
)
def test_notification_request_accepts_each_section_2_3_claim_type(claim_type: str) -> None:
    parsed = NotificationRequest.model_validate(well_formed_payload(claim_type=claim_type))
    assert parsed.claim_type == claim_type


@pytest.mark.parametrize(
    ("case_id", "payload"),
    [
        ("description_omitted_is_none", payload_omitting("description")),
        ("description_null_is_none", well_formed_payload(description=None)),
    ],
    ids=["description_omitted_is_none", "description_null_is_none"],
)
def test_notification_request_treats_absent_and_null_description_as_none(
    case_id: str,
    payload: dict[str, object],
) -> None:
    parsed = NotificationRequest.model_validate(payload)
    assert parsed.description is None


@pytest.mark.parametrize(
    ("case_id", "payload", "expected_loc"),
    [
        (
            "extra_field_typo_field",
            well_formed_payload(typo_field="ignored-if-accepted"),
            "typo_field",
        ),
        (
            "missing_policy_number",
            payload_omitting("policy_number"),
            "policy_number",
        ),
        (
            "missing_loss_date",
            payload_omitting("loss_date"),
            "loss_date",
        ),
        (
            "missing_claim_type",
            payload_omitting("claim_type"),
            "claim_type",
        ),
        (
            "missing_estimated_amount_EDGE-08",
            EDGE_PAYLOADS["EDGE-08"],
            "estimated_amount",
        ),
        (
            "empty_policy_number",
            well_formed_payload(policy_number=""),
            "policy_number",
        ),
        (
            "policy_number_wrong_type",
            well_formed_payload(policy_number=4471),
            "policy_number",
        ),
        (
            "loss_date_wrong_format",
            well_formed_payload(loss_date="02-04-2026"),
            "loss_date",
        ),
        (
            "loss_date_with_time_component",
            well_formed_payload(loss_date="2026-04-02T00:00:00"),
            "loss_date",
        ),
        (
            "loss_date_impossible_calendar_day",
            well_formed_payload(loss_date="2026-02-31"),
            "loss_date",
        ),
        (
            "loss_date_datetime_instance",
            well_formed_payload(loss_date=datetime(2026, 4, 2, 12, 0, 0, tzinfo=UTC)),
            "loss_date",
        ),
        (
            "loss_date_wrong_type_int",
            well_formed_payload(loss_date=20260402),
            "loss_date",
        ),
        (
            "claim_type_outside_vocabulary_flood_EDGE-11",
            EDGE_PAYLOADS["EDGE-11"],
            "claim_type",
        ),
        (
            "claim_type_empty_string",
            well_formed_payload(claim_type=""),
            "claim_type",
        ),
        (
            "claim_type_wrong_type",
            well_formed_payload(claim_type=["collision"]),
            "claim_type",
        ),
        (
            "estimated_amount_zero",
            well_formed_payload(estimated_amount="0.00"),
            "estimated_amount",
        ),
        (
            "estimated_amount_negative",
            well_formed_payload(estimated_amount="-1.00"),
            "estimated_amount",
        ),
        (
            "estimated_amount_float",
            well_formed_payload(estimated_amount=4200.0),
            "estimated_amount",
        ),
        (
            "estimated_amount_integer",
            well_formed_payload(estimated_amount=4200),
            "estimated_amount",
        ),
        (
            "estimated_amount_boolean",
            well_formed_payload(estimated_amount=True),
            "estimated_amount",
        ),
        (
            "estimated_amount_three_decimal_places_EDGE-12",
            EDGE_PAYLOADS["EDGE-12"],
            "estimated_amount",
        ),
        (
            "estimated_amount_one_decimal_place",
            well_formed_payload(estimated_amount="4200.0"),
            "estimated_amount",
        ),
        (
            "estimated_amount_no_decimal_places",
            well_formed_payload(estimated_amount="4200"),
            "estimated_amount",
        ),
        (
            "estimated_amount_not_a_number",
            well_formed_payload(estimated_amount="four-thousand"),
            "estimated_amount",
        ),
        (
            "description_wrong_type",
            well_formed_payload(description=123),
            "description",
        ),
    ],
    ids=[
        "extra_field_typo_field",
        "missing_policy_number",
        "missing_loss_date",
        "missing_claim_type",
        "missing_estimated_amount_EDGE-08",
        "empty_policy_number",
        "policy_number_wrong_type",
        "loss_date_wrong_format",
        "loss_date_with_time_component",
        "loss_date_impossible_calendar_day",
        "loss_date_datetime_instance",
        "loss_date_wrong_type_int",
        "claim_type_outside_vocabulary_flood_EDGE-11",
        "claim_type_empty_string",
        "claim_type_wrong_type",
        "estimated_amount_zero",
        "estimated_amount_negative",
        "estimated_amount_float",
        "estimated_amount_integer",
        "estimated_amount_boolean",
        "estimated_amount_three_decimal_places_EDGE-12",
        "estimated_amount_one_decimal_place",
        "estimated_amount_no_decimal_places",
        "estimated_amount_not_a_number",
        "description_wrong_type",
    ],
)
def test_notification_request_rejects_structurally_invalid_payloads(
    case_id: str,
    payload: dict[str, object],
    expected_loc: str,
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        NotificationRequest.model_validate(payload)
    assert expected_loc in _error_locations(exc_info)


@pytest.mark.parametrize(
    ("policy_number", "cancellation_date"),
    [
        ("MOT-4471", None),
        ("MOT-4496", date(2026, 2, 1)),
        ("MOT-4497", date(2026, 1, 15)),
    ],
    ids=[
        "uncancelled_policy_cancellation_date_is_none",
        "cancelled_mid_term_MOT-4496",
        "cancelled_on_cancellation_date_MOT-4497",
    ],
)
def test_policy_from_record_types_cancellation_date_so_absence_is_visible(
    policy_client: StubPolicyClient,
    policy_number: str,
    cancellation_date: date | None,
) -> None:
    policy = Policy.from_record(policy_client.get_policy(policy_number))
    assert policy.policy_number == policy_number
    assert type(policy.effective_date) is date
    assert type(policy.expiry_date) is date
    assert type(policy.limit) is Decimal
    assert policy.cancellation_date == cancellation_date


def _valid_policy(**overrides: object) -> Policy:
    fields: dict[str, object] = {
        "policy_number": "MOT-4471",
        "product": "personal_auto_standard",
        "effective_date": date(2026, 3, 1),
        "expiry_date": date(2027, 2, 28),
        "cancellation_date": None,
        "limit": Decimal("50000.00"),
        "permitted_claim_types": frozenset({"collision", "theft"}),
    }
    fields.update(overrides)
    return Policy.model_validate(fields)


@pytest.mark.parametrize(
    ("case_id", "overrides", "expected_loc"),
    [
        ("extra_field_forbidden", {"unknown_field": "x"}, "unknown_field"),
        ("empty_policy_number", {"policy_number": ""}, "policy_number"),
        ("empty_product", {"product": ""}, "product"),
        ("limit_zero", {"limit": Decimal("0.00")}, "limit"),
        ("limit_negative", {"limit": Decimal("-1.00")}, "limit"),
        ("limit_one_decimal_place", {"limit": Decimal("50000.0")}, "limit"),
        ("limit_no_decimal_places", {"limit": Decimal(50000)}, "limit"),
    ],
    ids=[
        "extra_field_forbidden",
        "empty_policy_number",
        "empty_product",
        "limit_zero",
        "limit_negative",
        "limit_one_decimal_place",
        "limit_no_decimal_places",
    ],
)
def test_policy_rejects_unconstrained_or_extra_fields(
    case_id: str,
    overrides: dict[str, object],
    expected_loc: str,
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        _valid_policy(**overrides)
    assert expected_loc in _error_locations(exc_info)


def test_rule_failure_keeps_rule_identifier_and_error_code_as_separate_fields() -> None:
    failure = RuleFailure(rule=RuleId("V-6"), code=ErrorCode("DUPLICATE_NOTIFICATION"))
    assert failure.rule == "V-6"
    assert failure.code == "DUPLICATE_NOTIFICATION"


def test_rule_failure_is_immutable() -> None:
    failure = RuleFailure(rule=RuleId("V-2"), code=ErrorCode("LOSS_BEFORE_INCEPTION"))
    with pytest.raises(FrozenInstanceError):
        failure.__setattr__("code", ErrorCode("POLICY_NOT_FOUND"))


@pytest.mark.parametrize(
    ("case_id", "claim_reference"),
    [
        ("valid_first_of_year", "CLM-2026-000001"),
        ("valid_padded_sequence", "CLM-2026-000317"),
    ],
    ids=["valid_first_of_year", "valid_padded_sequence"],
)
def test_claim_record_accepts_contract_claim_reference(
    case_id: str,
    claim_reference: str,
) -> None:
    recorded = ClaimRecord(
        claim_reference=claim_reference,
        policy_number="MOT-4471",
        loss_date=date(2026, 4, 2),
        claim_type="collision",
        estimated_amount=Decimal("4200.00"),
        description="Rear ended at a junction.",
    )
    assert recorded.claim_reference == claim_reference
    assert type(recorded.loss_date) is date
    assert type(recorded.estimated_amount) is Decimal
    assert recorded.estimated_amount == Decimal("4200.00")


@pytest.mark.parametrize(
    ("case_id", "claim_reference"),
    [
        ("year_not_four_digits", "CLM-26-000001"),
        ("sequence_not_six_digits", "CLM-2026-1"),
        ("lowercase_prefix", "clm-2026-000001"),
        ("trailing_suffix", "CLM-2026-000001-X"),
        ("missing_prefix", "2026-000001"),
    ],
    ids=[
        "year_not_four_digits",
        "sequence_not_six_digits",
        "lowercase_prefix",
        "trailing_suffix",
        "missing_prefix",
    ],
)
def test_claim_record_rejects_claim_reference_outside_contract_pattern(
    case_id: str,
    claim_reference: str,
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        ClaimRecord(
            claim_reference=claim_reference,
            policy_number="MOT-4471",
            loss_date=date(2026, 4, 2),
            claim_type="collision",
            estimated_amount=Decimal("4200.00"),
            description=None,
        )
    assert "claim_reference" in _error_locations(exc_info)


def _valid_claim_record(**overrides: object) -> ClaimRecord:
    fields: dict[str, object] = {
        "claim_reference": "CLM-2026-000001",
        "policy_number": "MOT-4471",
        "loss_date": date(2026, 4, 2),
        "claim_type": "collision",
        "estimated_amount": Decimal("4200.00"),
        "description": "Rear ended at a junction.",
    }
    fields.update(overrides)
    return ClaimRecord.model_validate(fields)


@pytest.mark.parametrize(
    ("case_id", "overrides", "expected_loc"),
    [
        ("extra_field_forbidden", {"unknown_field": "x"}, "unknown_field"),
        ("empty_policy_number", {"policy_number": ""}, "policy_number"),
        ("estimated_amount_zero", {"estimated_amount": Decimal("0.00")}, "estimated_amount"),
        (
            "estimated_amount_negative",
            {"estimated_amount": Decimal("-1.00")},
            "estimated_amount",
        ),
        (
            "estimated_amount_one_decimal_place",
            {"estimated_amount": Decimal("4200.0")},
            "estimated_amount",
        ),
        (
            "estimated_amount_no_decimal_places",
            {"estimated_amount": Decimal(4200)},
            "estimated_amount",
        ),
    ],
    ids=[
        "extra_field_forbidden",
        "empty_policy_number",
        "estimated_amount_zero",
        "estimated_amount_negative",
        "estimated_amount_one_decimal_place",
        "estimated_amount_no_decimal_places",
    ],
)
def test_claim_record_preserves_request_money_and_identifier_constraints(
    case_id: str,
    overrides: dict[str, object],
    expected_loc: str,
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        _valid_claim_record(**overrides)
    assert expected_loc in _error_locations(exc_info)
