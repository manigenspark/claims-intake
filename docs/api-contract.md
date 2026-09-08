# Claims Intake Service: API Contract

Version 0.4. Owned by the claims intake team. Consumed by the claims portal team.

This document is the authority on what the service accepts, what it returns, and under what conditions it refuses. Where the code and this document disagree, the document is correct and the code is a defect.

Sections 1 through 3 are fixed. Do not edit them.

## 1. Purpose and scope

The claims intake service accepts a first notice of loss from the claims portal, validates it against the policy master and a table of business rules, and either records a notification and issues a claim reference or refuses the submission with a specific reason.

**In scope.** Accepting a notification, validating it, and recording it. Issuing a claim reference. Reporting the reason a notification was refused.

**Out of scope.** Adjusting, reserving, payment, and any decision about coverage beyond the rules in section 4. The service decides whether a notification is well formed and admissible. It does not decide whether the claim will be paid.

**The policy master is a dependency, not part of this service.** The service reads policy records from it and does not write to it. A policy that cannot be read is a condition this contract specifies, and it is specified separately from a policy that does not exist, because the two require different action from the caller.

**Compatibility.** Adding a field to a response is a compatible change and callers must ignore fields they do not recognize. Adding a new error code is a compatible change and callers must fall through to default handling for a code they do not recognize. Changing the meaning of an existing code, removing a field, or changing a status code for an existing condition is not compatible and does not happen without a version increment agreed with the portal team.

## 2. Request

### 2.1 Endpoint

```
POST /notifications
Content-Type: application/json
```

### 2.2 Body

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `policy_number` | string | yes | Identifier as held in the policy master. Not empty. |
| `loss_date` | string | yes | Calendar date, `YYYY-MM-DD`. |
| `claim_type` | string | yes | One of the values in 2.3. Not empty. |
| `estimated_amount` | decimal | yes | United States dollars, two decimal places. Greater than zero. |
| `description` | string | no | Free text. Absent and `null` are equivalent. |

The service rejects a body carrying a field not listed above. A misspelled field name is a defect in the caller's code, and accepting the payload with the field ignored would record a notification built from data the caller did not send.

### 2.3 Claim type vocabulary

`collision`, `theft`, `glass`, `liability`, `weather`.

Which of these are admissible on a given notification depends on the product the policy is written on. The vocabulary is fixed by this contract. The permitted subset is a property of the policy record and is evaluated by rule `V-5`.

### 2.4 Well formed against acceptable

A request that cannot be interpreted is refused with status `400`. This means the body was not valid JSON, a required field was absent, a field carried a value of the wrong type, or a field was present that this contract does not define. The caller's code is wrong.

A request that was interpreted and whose content is not admissible is refused with status `422`. The caller's data is wrong, and a person needs to see the reason.

This split is stated here once and holds without exception everywhere else in this document.

## 3. Success response

A notification that passes every rule in section 4 is recorded and the service responds:

```
201 Created
Content-Type: application/json

{
  "claim_reference": "CLM-2026-000317",
  "status": "recorded"
}
```

**`claim_reference`** matches the pattern `CLM-YYYY-NNNNNN`, where `YYYY` is the calendar year in which the notification was recorded and `NNNNNN` is a zero padded sequence. A claim reference is unique across all recorded notifications and is never reissued. It is the value the claims handler quotes and the value every downstream system keys on.

**`status`** is `recorded` on every success response this contract defines. It exists because the portal displays it and because a future state that is not `recorded` is foreseeable. Callers must not treat it as constant.

A refused notification is never recorded and no claim reference is issued. There is no partial outcome: either a notification exists with a reference, or nothing was written.

## 4. Validation

### 4.1 Evaluation order

Rules are evaluated in the sequence listed below, not in ascending
identifier order. Identifiers name rules for reference; this sequence is
the only authority on which rule runs when. Evaluation stops at the
first failure and that rule's code is returned. V-1 short circuits: if
it fails, no rule that reads a policy field is evaluated.

`V-7` is evaluated before `V-3` because a loss that falls both after
cancellation and outside the original term must be refused with
`POLICY_CANCELLED`, not `LOSS_AFTER_EXPIRY`. Reporting expiry alone
sends the handler to the wrong system to investigate (WI-0158, AC-4).

Evaluation sequence: `V-1`, `V-2`, `V-7`, `V-3`, `V-4`, `V-5`, `V-6`.

### 4.2 Rule table

| ID  | Condition                                      | Code                    | Status |
| --- | ---------------------------------------------- | ----------------------- | ------ |
| V-1 | `policy_number` exists in the policy master    | `POLICY_NOT_FOUND`      | 422    |
| V-2 | `loss_date` >= policy `effective_date`         | `LOSS_BEFORE_INCEPTION` | 422    |
| V-3 | `loss_date` <= policy `expiry_date`            | `LOSS_AFTER_EXPIRY`     | 422    |
| V-4 | `estimated_amount` <= policy `limit`           | `AMOUNT_EXCEEDS_LIMIT`  | 422    |
| V-5 | `claim_type` permitted on the policy's product | `TYPE_NOT_COVERED`      | 422    |
| V-6 | `policy_number`, `loss_date`, and `claim_type` match no recorded notification | `DUPLICATE_NOTIFICATION` | 409    |
| V-7 | policy `cancellation_date` is null or `loss_date` < policy `cancellation_date` | `POLICY_CANCELLED` | 422    |

Boundaries are inclusive as stated, with exceptions:

- **V-1:** Lookup is case-sensitive. `policy_number` must match the policy master record exactly, including case.
- **V-2:** Inclusive. A loss on the inception date is covered (WI-0142, AC-3).
- **V-3:** Inclusive on expiry as written (`<=`). Evaluated after `V-7`; see section 4.1.
- **V-4:** Inclusive. An amount equal to the limit is within cover (implicit in "<=").
- **V-5:** Per the policy's product definition; see 2.3.
- **V-6 scope:** A match is determined against recorded notifications only. A resubmission after a prior refusal is not treated as a duplicate (WI-0151, AC-3).
- **V-7:** Exclusive on cancellation. A loss on the cancellation date is not covered (WI-0158, AC-2). Uses strict `<` to enforce this boundary. When `cancellation_date` is null, the rule passes without evaluating the date comparison (WI-0158, AC-3).

## 5. Error envelope

When the service refuses a notification, the response body is a JSON object with a fixed top-level structure and a variable `detail` field.

**Response structure:**

```json
{
  "code": "ERROR_CODE_HERE",
  "message": "Human readable explanation.",
  "detail": {}
}
```

**Stable parts of the envelope:**
- The response is always valid JSON
- `code` is always present and is one of the error codes defined in this contract (section 6)
- The envelope always carries exactly these three keys: `code`, `message`, and `detail`
- Callers must not rely on the value of `message`. It is an implementation detail and may change between service versions, may vary by deployment, and is not stable within this contract. It exists for human readers, not for programmatic logic.

**Variable parts of the envelope:**
- The shape and contents of `detail` vary by `code`
- `detail` is always an object, but its keys and value types depend on the error code
- Callers may rely on `code` to dispatch behavior but must not make assumptions about `detail` except where explicitly documented below
- Callers must ignore keys in `detail` they do not recognize, as the contract permits adding new keys in future versions

**Detail object by error code:**

| Code | Detail shape | Notes |
| --- | --- | --- |
| `POLICY_NOT_FOUND` | `{}` | Empty object. The policy could not be found in the policy master. |
| `LOSS_BEFORE_INCEPTION` | `{}` | Empty object. The loss date is before cover attached. |
| `POLICY_CANCELLED` | `{}` | Empty object. Cover has ended due to cancellation. |
| `LOSS_AFTER_EXPIRY` | `{}` | Empty object. The loss date is after cover expired. |
| `AMOUNT_EXCEEDS_LIMIT` | `{}` | Empty object. The claimed amount is above the policy limit. |
| `TYPE_NOT_COVERED` | `{}` | Empty object. The claim type is not permitted on this policy. |
| `DUPLICATE_NOTIFICATION` | `{"claim_reference": "CLM-2026-000317"}` | The claim reference of the existing recorded notification. |
| `MALFORMED_REQUEST` | `{}` | Empty object. A required field is missing, a field has the wrong type, the request body is not valid JSON, or a field value violates a structural constraint defined in section 6. |
| `POLICY_MASTER_TIMEOUT` | `{}` | Empty object. The policy master did not respond within the allowed time. |
| `POLICY_MASTER_UNREACHABLE` | `{}` | Empty object. The policy master could not be reached. |
| `POLICY_MASTER_UNPARSABLE` | `{}` | Empty object. The policy master returned a response the service cannot parse. |

**Worked examples:**

Example 1: A rule failure (V-5, type not covered)
```json
{
  "code": "TYPE_NOT_COVERED",
  "message": "Collision is not covered under this policy's product.",
  "detail": {}
}
```

Example 2: A request the service could not interpret (missing required field)
```json
{
  "code": "MALFORMED_REQUEST",
  "message": "The field 'estimated_amount' is required and was not provided.",
  "detail": {}
}
```

Example 3: A policy master dependency failure (lookup timed out)

```
503 Service Unavailable
```

```json
{
  "code": "POLICY_MASTER_TIMEOUT",
  "message": "The policy master did not respond within the allowed time.",
  "detail": {}
}
```

## 6. Status code mapping

This table is exhaustive. Every condition that causes the service to refuse a notification appears here, mapped to exactly one HTTP status code. There is no refusal not covered by this table.

| Status | Codes | Condition |
| --- | --- | --- |
| 400 | `MALFORMED_REQUEST` | Request body is not valid JSON; a required field is absent; a field has the wrong type; a field is present that this contract does not define; a field value violates a structural constraint in section 2.2 (`policy_number` is empty; `loss_date` is not a calendar date in `YYYY-MM-DD`; `claim_type` is not one of the values in section 2.3; `estimated_amount` is not greater than zero or does not have exactly two decimal places). The fault is in the caller's code. |
| 409 | `DUPLICATE_NOTIFICATION` | A notification with identical `policy_number`, `loss_date`, and `claim_type` has already been recorded (rule V-6). The caller may retry the same notification and receive the claim reference of the existing record, or may cancel and resubmit with modified data. |
| 422 | `POLICY_NOT_FOUND`, `LOSS_BEFORE_INCEPTION`, `POLICY_CANCELLED`, `LOSS_AFTER_EXPIRY`, `AMOUNT_EXCEEDS_LIMIT`, `TYPE_NOT_COVERED` | The request is well formed and the caller's code is correct, but the notification data is not admissible: the policy does not exist (V-1), the loss is outside the policy term (V-2, V-3, V-7), the amount exceeds the policy limit (V-4), or the claim type is not permitted on this policy (V-5). A person needs to investigate and correct the data. |
| 503 | `POLICY_MASTER_TIMEOUT`, `POLICY_MASTER_UNREACHABLE` | The policy master did not produce a usable answer because the lookup timed out (`timeout`) or the policy master was unreachable (`unreachable`). The service cannot determine whether to accept or refuse the notification. The caller may retry immediately. |
| 500 | `POLICY_MASTER_UNPARSABLE` | The policy master returned a response the service cannot parse (`unparsable`), or an internal error occurred in the service. The caller may retry after a delay; an `unparsable` response indicates a configuration error or a defect in the policy master integration. |
