# Approval Automation Safety Notes

These notes capture the required safety design for the future approval automation stage.

## Core Principle

Approval automation must never trust row order or "next item" assumptions. Each payment must be treated as a locked reference workflow:

1. Select one pasted GTX reference and its expected Excel values.
2. Store that as the active locked item.
3. Validate the GTExchange page against that locked item before any approval action.
4. Stop immediately if any required field is missing, mismatched, ambiguous, or unreadable.

## Required Checks Before Approval

For every payment, the automation must verify all required fields before entering confirmation values:

- GTX reference exactly matches the locked reference.
- Amount matches Excel.
- Currency matches Excel/template expectation.
- Value date matches Excel.
- Unit matches Excel/template expectation.
- To BIC matches expected mapping.
- Remittance/unstructured text matches expected reference and OTR content.
- Search result is unique and not ambiguous.
- Page status is eligible for approval.

## In-Between Safety Gates

Approval should use multiple gates, not one early check:

1. **Before opening verify**
   - Lock the current reference and expected values.
   - Do not continue based on list position.

2. **After opening verify page**
   - Read displayed reference.
   - Confirm it equals the locked reference.

3. **Before entering amount/date**
   - Parse page details again.
   - Compare reference, amount, currency, date, unit, To BIC, and remittance.

4. **After filling amount/date fields**
   - Read the input values back.
   - Confirm entered amount/date equal expected values.
   - Confirm page reference still equals locked reference.

5. **Before first OK**
   - Re-read visible reference/details if available.
   - Confirm the locked reference and expected amount again.

6. **Before final OK**
   - If a confirmation page appears, read reference, amount, and date again.
   - Click final OK only if they still match.

7. **After approval**
   - Search/check status.
   - Confirm status changed as expected.
   - Capture payment copy only after successful approval.

## Stop Conditions

Automation must not approve if any of these happen:

- Reference is missing or different.
- Amount parsing fails.
- Amount, currency, value date, unit, To BIC, or remittance mismatches.
- Date format is ambiguous.
- Multiple search results appear for one reference.
- GTExchange navigates unexpectedly.
- Confirmation fields cannot be read back.
- Status is not eligible for approval.
- Any timeout occurs at a safety-critical step.

## Rerun Behavior

Approval automation must be idempotent. Running the same reference list twice must not approve anything twice.

On every run, before attempting approval:

1. Search/open the pasted reference.
2. Read the current status.
3. If already approved, verified, completed, archived, or otherwise processed, mark it as skipped.
4. Do not enter amount/date or click approval buttons for skipped references.
5. Continue with the next reference.

Example rerun scenario:

- First run approves references 1-4.
- Reference 5 fails and automation stops.
- User manually fixes or approves reference 5.
- User reruns all references.
- References 1-5 should be detected as already processed and skipped.
- Remaining pending references can continue through the approval gates.

## Result Statuses To Show In UI

Future approval results should distinguish these states:

- Approved
- Already approved
- Skipped - already processed
- Failed before approval
- Needs manual review
- Search/read failed
- Status unknown

## Logging

Keep a local run log for troubleshooting and audit evidence:

- GTX reference
- Template
- Expected amount/date/unit/BIC/remittance
- Status before approval
- Each safety gate result
- Final status
- Error message if stopped
- Timestamp

GTExchange remains the source of truth. The local log is only supporting evidence.
