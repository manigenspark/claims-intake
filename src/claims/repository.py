"""Persistence for recorded notifications.

An in-memory store is sufficient for Week 1 and is deliberate rather than a
shortcut. The rules do not know where a notification is stored, so replacing this
with a database in a later week is a change to one module.

The store holds ``ClaimRecord`` values only. There is no collection of refused
notifications and no write method except ``record``. ``find_matching`` therefore
cannot see a refusal: WI-0151 AC-3 is a property of what this module can store,
not a convention the caller has to remember.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from claims.models import ClaimRecord, NotificationRequest


class NotificationRepository:
    """Stores recorded notifications and issues claim references."""

    def __init__(self, *, recording_year: int | None = None) -> None:
        self._recording_year = recording_year
        self._claims: list[ClaimRecord] = []
        self._next_sequence_by_year: dict[int, int] = {}

    def record(self, notification: NotificationRequest) -> ClaimRecord:
        """Write an accepted notification and return it as a ``ClaimRecord``.

        This is the only write path. The reference format is fixed by contract
        section 3. References are unique and are never reissued.
        """
        year = self._year()
        sequence = self._next_sequence_by_year.get(year, 1)
        self._next_sequence_by_year[year] = sequence + 1
        recorded = ClaimRecord(
            claim_reference=f"CLM-{year}-{sequence:06d}",
            policy_number=notification.policy_number,
            loss_date=notification.loss_date,
            claim_type=notification.claim_type,
            estimated_amount=notification.estimated_amount,
            description=notification.description,
        )
        self._claims.append(recorded)
        return recorded

    def find_matching(
        self,
        policy_number: str,
        loss_date: date,
        claim_type: str,
    ) -> ClaimRecord | None:
        """Return an existing claim matching all three values.

        ``WI-0151`` AC-1 fixes which fields constitute a match. The search is
        over ``ClaimRecord`` values only, which is why a refused notification
        cannot be a duplicate (WI-0151, AC-3).
        """
        for recorded in self._claims:
            if (
                recorded.policy_number == policy_number
                and recorded.loss_date == loss_date
                and recorded.claim_type == claim_type
            ):
                return recorded
        return None

    def recorded_claims(self) -> tuple[ClaimRecord, ...]:
        """The claims this repository has written, in write order."""
        return tuple(self._claims)

    def _year(self) -> int:
        if self._recording_year is not None:
            return self._recording_year
        return datetime.now(tz=UTC).date().year
