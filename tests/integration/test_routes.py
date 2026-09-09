"""HTTP integration tests for POST /notifications.

These exercise the service through FastAPI rather than calling rule functions.
Each case asserts status, contract code, and actionable detail where section 5
requires it. Fixtures rebuild client and repository so the suite is order-independent.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from claims.api.routes import app
from claims.policy_client import LookupFailureReason, StubPolicyClient
from claims.repository import NotificationRepository


@pytest.fixture
def client() -> Iterator[TestClient]:
    app.state.policy_client = StubPolicyClient()
    app.state.repository = NotificationRepository(recording_year=2026)
    with TestClient(app) as test_client:
        yield test_client


def _post(client: TestClient, payload: dict[str, Any]) -> Any:
    return client.post("/notifications", json=payload)


def test_accepted_notification_returns_201_with_claim_reference(client: TestClient) -> None:
    response = _post(
        client,
        {
            "policy_number": "MOT-4471",
            "loss_date": "2026-04-02",
            "claim_type": "collision",
            "estimated_amount": "4200.00",
            "description": "Rear ended at a junction.",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "recorded"
    assert body["claim_reference"] == "CLM-2026-000001"


def test_missing_required_field_returns_400_malformed_request(client: TestClient) -> None:
    response = _post(
        client,
        {
            "policy_number": "MOT-4471",
            "loss_date": "2026-04-02",
            "claim_type": "collision",
            "description": "Amount omitted.",
        },
    )
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "MALFORMED_REQUEST"
    assert body["detail"] == {}
    assert set(body.keys()) == {"code", "message", "detail"}


def test_extra_field_returns_400_malformed_request(client: TestClient) -> None:
    response = _post(
        client,
        {
            "policy_number": "MOT-4471",
            "loss_date": "2026-04-02",
            "claim_type": "collision",
            "estimated_amount": "4200.00",
            "typo_field": "should-not-be-ignored",
        },
    )
    assert response.status_code == 400
    assert response.json()["code"] == "MALFORMED_REQUEST"


@pytest.mark.parametrize(
    ("payload", "status", "code"),
    [
        (
            {
                "policy_number": "MOT-9999",
                "loss_date": "2026-03-12",
                "claim_type": "collision",
                "estimated_amount": "3000.00",
            },
            422,
            "POLICY_NOT_FOUND",
        ),
        (
            {
                "policy_number": "MOT-4479",
                "loss_date": "2026-02-20",
                "claim_type": "collision",
                "estimated_amount": "5000.00",
            },
            422,
            "LOSS_BEFORE_INCEPTION",
        ),
        (
            {
                "policy_number": "MOT-4497",
                "loss_date": "2026-01-15",
                "claim_type": "glass",
                "estimated_amount": "480.00",
            },
            422,
            "POLICY_CANCELLED",
        ),
        (
            {
                "policy_number": "MOT-4489",
                "loss_date": "2026-03-20",
                "claim_type": "theft",
                "estimated_amount": "8000.00",
            },
            422,
            "LOSS_AFTER_EXPIRY",
        ),
        (
            {
                "policy_number": "MOT-4502",
                "loss_date": "2026-03-08",
                "claim_type": "collision",
                "estimated_amount": "14500.00",
            },
            422,
            "AMOUNT_EXCEEDS_LIMIT",
        ),
        (
            {
                "policy_number": "MOT-4486",
                "loss_date": "2026-03-14",
                "claim_type": "collision",
                "estimated_amount": "6200.00",
            },
            422,
            "TYPE_NOT_COVERED",
        ),
    ],
    ids=[
        "v1_policy_not_found",
        "v2_loss_before_inception",
        "v7_policy_cancelled",
        "v3_loss_after_expiry",
        "v4_amount_exceeds_limit",
        "v5_type_not_covered",
    ],
)
def test_each_policy_rule_refusal_returns_contract_status_and_code(
    client: TestClient,
    payload: dict[str, str],
    status: int,
    code: str,
) -> None:
    response = _post(client, payload)
    assert response.status_code == status
    body = response.json()
    assert body["code"] == code
    assert body["detail"] == {}
    assert set(body.keys()) == {"code", "message", "detail"}


def test_duplicate_notification_returns_409_with_existing_claim_reference(
    client: TestClient,
) -> None:
    payload = {
        "policy_number": "MOT-4471",
        "loss_date": "2026-04-02",
        "claim_type": "collision",
        "estimated_amount": "4200.00",
    }
    first = _post(client, payload)
    assert first.status_code == 201
    claim_reference = first.json()["claim_reference"]

    second = _post(client, {**payload, "description": "retry after timeout"})
    assert second.status_code == 409
    body = second.json()
    assert body["code"] == "DUPLICATE_NOTIFICATION"
    assert body["detail"] == {"claim_reference": claim_reference}


@pytest.mark.parametrize(
    ("reason", "status", "code"),
    [
        ("timeout", 503, "POLICY_MASTER_TIMEOUT"),
        ("unreachable", 503, "POLICY_MASTER_UNREACHABLE"),
        ("unparsable", 500, "POLICY_MASTER_UNPARSABLE"),
    ],
    ids=["timeout", "unreachable", "unparsable"],
)
def test_policy_lookup_failed_maps_each_reason_to_distinct_5xx(
    client: TestClient,
    reason: LookupFailureReason,
    status: int,
    code: str,
) -> None:
    app.state.policy_client = StubPolicyClient(fail_with=reason)
    response = _post(
        client,
        {
            "policy_number": "MOT-4471",
            "loss_date": "2026-04-02",
            "claim_type": "collision",
            "estimated_amount": "4200.00",
        },
    )
    assert response.status_code == status
    body = response.json()
    assert body["code"] == code
    assert body["detail"] == {}
    assert status >= 500


def test_policy_not_found_is_422_not_a_dependency_5xx(client: TestClient) -> None:
    response = _post(
        client,
        {
            "policy_number": "mot-4471",
            "loss_date": "2026-04-06",
            "claim_type": "collision",
            "estimated_amount": "3300.00",
        },
    )
    assert response.status_code == 422
    assert response.json()["code"] == "POLICY_NOT_FOUND"
