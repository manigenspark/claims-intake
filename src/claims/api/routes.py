"""HTTP surface for the claims intake service.

This layer does three things and no more: it parses the request, it calls the
service, and it maps the outcome to a status code. It holds no rule logic. A rule
that appears here is a rule the service layer cannot be tested for.

Mapping authority: docs/api-contract.md sections 5 and 6.
"""

from __future__ import annotations

from json import JSONDecodeError
from typing import Any, cast

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from claims.models import NotificationRequest
from claims.policy_client import PolicyClient, PolicyLookupFailed, StubPolicyClient
from claims.repository import NotificationRepository
from claims.service import ValidationOutcome, submit_notification

app = FastAPI(title="Claims Intake Service")

_STATUS_BY_CODE: dict[str, int] = {
    "MALFORMED_REQUEST": 400,
    "DUPLICATE_NOTIFICATION": 409,
    "POLICY_NOT_FOUND": 422,
    "LOSS_BEFORE_INCEPTION": 422,
    "POLICY_CANCELLED": 422,
    "LOSS_AFTER_EXPIRY": 422,
    "AMOUNT_EXCEEDS_LIMIT": 422,
    "TYPE_NOT_COVERED": 422,
    "POLICY_MASTER_TIMEOUT": 503,
    "POLICY_MASTER_UNREACHABLE": 503,
    "POLICY_MASTER_UNPARSABLE": 500,
}

_CODE_BY_LOOKUP_REASON: dict[str, str] = {
    "timeout": "POLICY_MASTER_TIMEOUT",
    "unreachable": "POLICY_MASTER_UNREACHABLE",
    "unparsable": "POLICY_MASTER_UNPARSABLE",
}

_MESSAGE_BY_CODE: dict[str, str] = {
    "MALFORMED_REQUEST": "The request could not be interpreted.",
    "DUPLICATE_NOTIFICATION": "A matching notification has already been recorded.",
    "POLICY_NOT_FOUND": "No policy was found for the given policy number.",
    "LOSS_BEFORE_INCEPTION": "The loss date is before the policy effective date.",
    "POLICY_CANCELLED": "The policy was cancelled before the loss date.",
    "LOSS_AFTER_EXPIRY": "The loss date is after the policy expiry date.",
    "AMOUNT_EXCEEDS_LIMIT": "The estimated amount exceeds the policy limit.",
    "TYPE_NOT_COVERED": "The claim type is not permitted on this policy.",
    "POLICY_MASTER_TIMEOUT": "The policy master did not respond within the allowed time.",
    "POLICY_MASTER_UNREACHABLE": "The policy master could not be reached.",
    "POLICY_MASTER_UNPARSABLE": "The policy master returned a response that could not be parsed.",
}


def _error_envelope(code: str, detail: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "code": code,
        "message": _MESSAGE_BY_CODE.get(code, "The request was refused."),
        "detail": detail if detail is not None else {},
    }


def _error_response(
    code: str,
    *,
    detail: dict[str, Any] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=_STATUS_BY_CODE[code],
        content=_error_envelope(code, detail),
    )


def get_policy_client() -> PolicyClient:
    client = getattr(app.state, "policy_client", None)
    if client is None:
        client = StubPolicyClient()
        app.state.policy_client = client
    return cast(PolicyClient, client)


def get_repository() -> NotificationRepository:
    repository = getattr(app.state, "repository", None)
    if repository is None:
        repository = NotificationRepository()
        app.state.repository = repository
    return cast(NotificationRepository, repository)


def _refusal_from_outcome(outcome: ValidationOutcome) -> JSONResponse:
    assert outcome.failure is not None
    code = str(outcome.failure.code)
    return _error_response(code, detail=outcome.detail)


@app.post("/notifications")
async def create_notification(request: Request) -> JSONResponse:
    """Accept a first notice of loss and record it or refuse with a contract code."""
    try:
        payload = await request.json()
    except JSONDecodeError:
        return _error_response("MALFORMED_REQUEST")

    if not isinstance(payload, dict):
        return _error_response("MALFORMED_REQUEST")

    try:
        notification = NotificationRequest.model_validate(payload)
    except ValidationError:
        return _error_response("MALFORMED_REQUEST")

    try:
        outcome = submit_notification(
            notification,
            get_policy_client(),
            get_repository(),
        )
    except PolicyLookupFailed as exc:
        code = _CODE_BY_LOOKUP_REASON[exc.reason]
        return _error_response(code)

    if outcome.accepted:
        assert outcome.claim_reference is not None
        return JSONResponse(
            status_code=201,
            content={
                "claim_reference": outcome.claim_reference,
                "status": "recorded",
            },
        )

    return _refusal_from_outcome(outcome)
