# Payload Triage

Every payload in `data/fnol_edge.json` classified against `docs/api-contract.md` as you have completed it. The classification records what the contract says the service does, which is not always what the payload obviously violates.

**Day 2 contract reconciliation** is in the section [Contract reconciliation (Day 2)](#contract-reconciliation-day-2) at the end of this document. It lists every refusal `NotificationRequest` can produce, how each was checked against section 6, and the amendment made to the 400 row.

Fill one row per payload. Where a payload is accepted, leave the rule, code, and status columns as `-`.

## Classification

| Payload | Outcome | Rule | Code | Status |
| --- | --- | --- | --- | --- |
| EDGE-01 | Accepted | - | - | - |
| EDGE-02 | Accepted | - | - | - |
| EDGE-03 | Accepted | - | - | - |
| EDGE-04 | Rejected | V-7 | POLICY_CANCELLED | 422 |
| EDGE-05 | Rejected | V-2 | LOSS_BEFORE_INCEPTION | 422 |
| EDGE-06 | Rejected | V-4 | AMOUNT_EXCEEDS_LIMIT | 422 |
| EDGE-07 | Rejected | V-1 | POLICY_NOT_FOUND | 422 |
| EDGE-08 | Rejected | — | MALFORMED_REQUEST | 400 |
| EDGE-09 | Rejected | V-5 | TYPE_NOT_COVERED | 422 |
| EDGE-10 | Rejected | V-7 | POLICY_CANCELLED | 422 |
| EDGE-11 | Rejected | — | MALFORMED_REQUEST | 400 |
| EDGE-12 | Rejected | — | MALFORMED_REQUEST | 400 |

## Decision log

Three payloads cannot be classified against the contract as it shipped, because the contract left a decision unmade. For each one, record the ambiguity, the decision, its authority, and the alternative you rejected.

A decision recorded here and nowhere else has not been made. Amend `docs/api-contract.md` so that a reader of the contract alone could not arrive at the other reading.

### Decision 1

**Payload.** EDGE-07: `policy_number` "mot-4471" (lowercase) against policy "MOT-4471" (uppercase).

**The ambiguity.** The contract says `policy_number` is an "Identifier as held in the policy master" but does not explicitly state whether the lookup against the policy master is case-sensitive. A reader could interpret this as either (a) exact matching including case, or (b) case-insensitive lookup as is common in many business systems.

**Decision.** Policy number lookups are case-sensitive. A `policy_number` value must match the policy master record exactly, character for character. "mot-4471" does not match "MOT-4471" and results in V-1 failure: POLICY_NOT_FOUND, 422.

**Authority.** The phrase "Identifier as held in the policy master" implies the value must match precisely as stored. This is the standard behavior for exact identifier matching in master systems, and the policy master is the system of record for the exact format. Field 2.2 also specifies that policy_number is "Not empty", treating it as a precise value to be looked up, not as data to be normalized.

**Rejected alternative.** Case-insensitive matching might be more forgiving of user input errors (typos), but the contract's language treats policy_number as a precise identifier, not a search term. Additionally, requiring exact matching ensures the service behavior is predictable and aligns with how most database systems handle primary key lookups. Making policy lookups case-insensitive would require the contract to explicitly state this normalization.

**Contract amended.** Section 4.2, V-1 boundary note: "Lookup is case-sensitive. `policy_number` must match the policy master record exactly, including case."

### Decision 2

**Payload.** EDGE-11: `claim_type` value "flood" against the defined vocabulary.

**The ambiguity.** The contract defines the claim type vocabulary in section 2.3 as exactly `collision`, `theft`, `glass`, `liability`, `weather`. Section 2.4 states that "a field carried a value of the wrong type" is rejected with 400. However, the contract does not explicitly state whether a claim_type value outside the defined vocabulary (a) is rejected as a malformed request at the parsing stage (400), or (b) is accepted syntactically and then evaluated by rule V-5 as not covered (422).

**Decision.** An unknown claim_type value is rejected as a malformed request with status 400 and error code MALFORMED_REQUEST. The claim_type field has a constrained vocabulary defined in 2.3; a value outside that vocabulary violates the field's type definition and is structurally invalid, not merely business-invalid.

**Authority.** Section 2.4: "a field carried a value of the wrong type... The caller's code is wrong." An enumeration constraint is part of a field's type definition. Section 2.3 fixes the vocabulary by contract: "The vocabulary is fixed by this contract." Accepting "flood" and checking it against V-5 (TYPE_NOT_COVERED) would blur the distinction between schema validation (field type) and business validation (rule evaluation), and would allow unknown types to reach the policy master check, consuming resources unnecessarily.

**Rejected alternative.** A lenient interpretation might accept "flood" syntactically and fail it at V-5 (TYPE_NOT_COVERED, 422). This would be simpler to implement but violates section 2.4's clear statement that wrong types cause 400 errors. It would also allow the service to report TYPE_NOT_COVERED for claim types that do not exist in the product definition, conflating "not covered" (meaning "covered by another peril") with "not defined" (meaning "not part of the claim type vocabulary"). Strict enum validation at the parsing stage ensures the service only reasons about valid types.

**Contract amended.** Section 5, detail table: Added entry for `MALFORMED_REQUEST`. Section 6, status 400 definition: now includes structural constraints for `claim_type` and `estimated_amount`.

### Decision 3

**Payload.** EDGE-12: `estimated_amount` value "3499.999" with three decimal places instead of the specified two.

**The ambiguity.** Section 2.2 specifies that estimated_amount is "United States dollars, two decimal places". The contract does not explicitly state what happens if a number is provided with a different precision: rejected as malformed (400), accepted and parsed, or rounded/truncated.

**Decision.** A number with decimal precision other than exactly two decimal places is rejected as a malformed request with status 400 and error code MALFORMED_REQUEST. The field's format includes the decimal place constraint; a value that does not conform to "two decimal places" has the wrong format and is structurally invalid.

**Authority.** Section 2.4: "a field carried a value of the wrong type". Precision is part of the numeric type definition. USD amounts are conventionally specified as exactly two decimal places (cents), and the contract makes this explicit in 2.2. Accepting "3499.999" would require the implementation to define lossy conversion behavior (truncate? round? error?), creating ambiguity about what was actually claimed. Strict enforcement at the parsing stage ensures a single clear path: well-formed requests proceed to validation rules, malformed requests are rejected before rule evaluation.

**Rejected alternative.** The implementation might accept "3499.999" and round it to "3499.99" or truncate to "3500.00", allowing the service to normalize numeric input. However, this would mask a potential error in the caller's code. A handler who sends three decimal places may have made a mistake (e.g., incorrect JSON parsing in their system). Silently correcting it and recording a notification with a different amount than what was submitted would violate the contract's principle in section 3: "either a notification exists with a reference, or nothing was written." Recording with an adjusted value is a form of partial outcome. The contract requires the caller to submit well-formed data; if the precision is wrong, the caller's code is wrong and must be fixed.

**Contract amended.** Section 6, status 400 definition: now includes "`estimated_amount` does not have exactly two decimal places" as a structural constraint.

## Contract reconciliation (Day 2)

**Method.** Listed every refusal `NotificationRequest` can produce by walking the model field by field against section 2.2, then checking each refusal against section 6. The list:

| Model refusal | Section 6 before this note |
| --- | --- |
| Extra field (`extra="forbid"`) | Named: "a field is present that this contract does not define" |
| Missing required field | Named: "a required field is absent" |
| Wrong type (`policy_number`, `loss_date`, `claim_type`, `estimated_amount`, `description`) | Named: "a field has the wrong type" |
| `claim_type` outside section 2.3 (EDGE-11) | Named in the 400 parenthetical |
| `estimated_amount` not exactly two decimal places (EDGE-12) | Named in the 400 parenthetical |
| `policy_number` empty | Covered only by the general "structural constraint" phrase; not named |
| `loss_date` not `YYYY-MM-DD` / not a real calendar date | Covered only by the general phrase; not named |
| `estimated_amount` not greater than zero | Covered only by the general phrase; not named |
| Body not valid JSON | Named; produced at the HTTP boundary on Day 4, not by this model |

`fnol_valid.json` (VALID-01–08) and `fnol_invalid.json` (INVALID-01–07) all parse. EDGE-01–07, EDGE-09, and EDGE-10 parse and survive to the rules. EDGE-08 (missing `estimated_amount`), EDGE-11 (`claim_type` `"flood"`), and EDGE-12 (`estimated_amount` `"3499.999"`) fail at the model with `MALFORMED_REQUEST` / 400.

Every model refusal uses the existing code `MALFORMED_REQUEST`. No new code or status was required.

**Result.** Amended section 6, status 400, to name the three structural constraints that section 2.2 already imposed but the 400 parenthetical omitted: empty `policy_number`, `loss_date` not a calendar date in `YYYY-MM-DD`, and `estimated_amount` not greater than zero. Left the code and status unchanged. A reader of section 6 alone can now enumerate every refusal the model produces.

**Payload boundary check.** Model vs rules split matches the Day 2 guide table and the Day 1 classification: only EDGE-08, EDGE-11, and EDGE-12 stop at the model; every other fixture payload is well formed and is decided by the rule table.
