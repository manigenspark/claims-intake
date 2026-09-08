"""Boundary models for the claims intake service.

Everything that enters the service is parsed into one of these before any rule
runs. A payload that reaches the rule layer has already been proven well formed,
which is what keeps a shape problem and a content problem from arriving at the
caller as the same status code.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Annotated, Literal, NewType, cast

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator

from claims.policy_client import PolicyRecord

ClaimType = Literal["collision", "theft", "glass", "liability", "weather"]

RuleId = NewType("RuleId", str)
ErrorCode = NewType("ErrorCode", str)

CLAIM_REFERENCE_PATTERN = r"^CLM-\d{4}-\d{6}$"
CLAIM_TYPE_VOCABULARY: frozenset[str] = frozenset(
    ("collision", "theft", "glass", "liability", "weather")
)
_CALENDAR_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _exactly_two_decimal_places(value: Decimal) -> Decimal:
    if value.as_tuple().exponent != -2:
        raise ValueError("amount must have exactly two decimal places")
    return value


# Shared money type so a recorded claim and a policy limit use the same
# comparison unit the request was parsed into (section 2.2).
UsdAmount = Annotated[Decimal, Field(gt=0), AfterValidator(_exactly_two_decimal_places)]
NonEmptyString = Annotated[str, Field(min_length=1)]


@dataclass(frozen=True)
class RuleFailure:
    """A refused rule outcome with its identifier and code kept distinct.

    Two fields exist so a rule identifier can never be passed where an error
    code is expected. Both are NewTypes for the same reason.
    """

    rule: RuleId
    code: ErrorCode


class NotificationRequest(BaseModel):
    """A first notice of loss as submitted by the claims portal.

    Fields and constraints follow contract section 2.2 and the structural
    refusals in section 6. Shape validation stops here; admissibility is
    decided in ``service.py``.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    policy_number: NonEmptyString
    loss_date: date
    claim_type: ClaimType
    estimated_amount: UsdAmount
    description: str | None = None

    @field_validator("loss_date", mode="before")
    @classmethod
    def parse_loss_date(cls, value: object) -> object:
        # JSON carries a YYYY-MM-DD string. Every other type is left for
        # strict checking so a ``datetime`` cannot silently become a ``date``.
        if not isinstance(value, str):
            return value
        if _CALENDAR_DATE_PATTERN.fullmatch(value) is None:
            raise ValueError("loss_date must be a calendar date in YYYY-MM-DD")
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("loss_date must be a real calendar date") from exc

    @field_validator("estimated_amount", mode="before")
    @classmethod
    def parse_estimated_amount(cls, value: object) -> object:
        # JSON fixtures and the portal send a decimal as a string. A JSON
        # number would already be a float; strict mode refuses it so V-4
        # never compares against a binary approximation.
        if not isinstance(value, str):
            return value
        try:
            return Decimal(value)
        except InvalidOperation as exc:
            raise ValueError("estimated_amount must be a decimal amount") from exc


class Policy(BaseModel):
    """A policy as this service works with it.

    Built from the ``PolicyRecord`` the policy client returns.
    ``cancellation_date`` is ``date | None`` so a comparison without handling
    absence fails type checking (WI-0158, AC-3). Extra fields are forbidden
    for the same reason they are on the request: a misspelled field must not
    be ignored.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_number: NonEmptyString
    product: NonEmptyString
    effective_date: date
    expiry_date: date
    cancellation_date: date | None
    limit: UsdAmount
    permitted_claim_types: frozenset[ClaimType]

    @classmethod
    def from_record(cls, record: PolicyRecord) -> Policy:
        return cls(
            policy_number=record.policy_number,
            product=record.product,
            effective_date=record.effective_date,
            expiry_date=record.expiry_date,
            cancellation_date=record.cancellation_date,
            limit=record.limit,
            permitted_claim_types=frozenset(
                _as_claim_type(claim_type) for claim_type in record.permitted_claim_types
            ),
        )


class ClaimRecord(BaseModel):
    """A notification that passed every rule and was written.

    Carries the claim reference issued at the time it was recorded. Contract
    section 3 fixes the reference format. Money and identifier constraints
    match ``NotificationRequest`` so a recorded claim cannot drift from the
    request that produced it.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    claim_reference: Annotated[str, Field(pattern=CLAIM_REFERENCE_PATTERN)]
    policy_number: NonEmptyString
    loss_date: date
    claim_type: ClaimType
    estimated_amount: UsdAmount
    description: str | None


def _as_claim_type(value: str) -> ClaimType:
    if value not in CLAIM_TYPE_VOCABULARY:
        raise ValueError(f"{value!r} is not in the claim type vocabulary")
    return cast(ClaimType, value)
