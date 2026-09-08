"""FNOL fixture payloads loaded from ``data/``.

JSON strings stay strings here. Tests parse them through ``NotificationRequest``
and assert on ``date`` and ``Decimal`` values, which is the same boundary the
service uses.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def load_named_payloads(filename: str) -> dict[str, dict[str, Any]]:
    records = json.loads((DATA_DIR / filename).read_text())
    return {record["id"]: record["payload"] for record in records}


def well_formed_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "policy_number": "MOT-4471",
        "loss_date": "2026-04-02",
        "claim_type": "collision",
        "estimated_amount": "4200.00",
        "description": "Rear ended at a junction.",
    }
    payload.update(overrides)
    return payload


def payload_omitting(*field_names: str) -> dict[str, object]:
    payload = well_formed_payload()
    for field_name in field_names:
        del payload[field_name]
    return payload


VALID_PAYLOADS = load_named_payloads("fnol_valid.json")
INVALID_PAYLOADS = load_named_payloads("fnol_invalid.json")
EDGE_PAYLOADS = load_named_payloads("fnol_edge.json")

EDGE_CASES_THAT_SURVIVE_THE_MODEL = (
    "EDGE-01",
    "EDGE-02",
    "EDGE-03",
    "EDGE-04",
    "EDGE-05",
    "EDGE-06",
    "EDGE-07",
    "EDGE-09",
    "EDGE-10",
)
