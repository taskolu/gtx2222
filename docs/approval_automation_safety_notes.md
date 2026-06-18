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

## Observed GTExchange Verify Flow

The real approval path captured from Playwright codegen uses the `Messages` > `Verify Messages` screen:

1. Open `Messages`.
2. Open `Verify Messages`.
3. Search by exact `GTX Reference`.
4. Open the matching reference link.
5. Read the payment detail page before clicking `Verify`.
6. Confirm status is `MESSAGE AWAITING VERIFICATION`.
7. Click `Verify`.
8. On the verify/edit page, re-check the same reference and key fields.
9. Enter the confirmation currency, amount, and date/amount fields required by the page.
10. Re-read the fields that were entered.
11. Click `Ok` only if all gates pass.
12. Confirm the success message.
13. Continue to the next reference.
14. After all approvals are complete, go to the search flow and capture matched payment copies/PDF.

The automation should not rely on the codegen's click sequence as proof. Codegen clicks are only locator clues. The implementation must read and compare values programmatically before acting.

## PACS Verify Page Fields

For PACS payments, codegen shows these useful fields on the verify/edit page:

- Header/reference heading.
- `From`.
- `To`.
- `(BizMsgIdr) Business Message Identifier`.
- `(MsgId) Message Identification`.
- `(InstrId) Instruction Identification`.
- `(EndToEndId) End To End Identification`.
- `(UETR) UETR`.
- `(IntrBkSttlmAmt) Interbank Settlement Amount`.
- Currency input with title `You can enter currency ISO`.
- Amount input with title beginning `Enter amount with a dot as`.
- Date input with title beginning `You can enter date in format`.
- `(IntrBkSttlmDt) Interbank Settlement Date`.
- Instructed amount currency/value.
- `(Ustrd) Unstructured`.
- `Ok` button.
- Success message containing `Message is successfully`.

For PACS, confirmation fields must be filled from the locked Excel/reference item, then read back from the page before `Ok`.

## CZK / MT101 Verify Page Fields

CZK/MT101 uses a different structure from PACS. Codegen shows these useful fields:

- Header/reference heading.
- `From`.
- `To`.
- `(20) Sender's Reference`.
- `(30) Requested Execution Date`.
- `(21) Transaction Reference`.
- `Currency`.
- `Amount`.
- Currency input with title `You can enter currency ISO`.
- Amount input with title beginning `Enter amount with a dot as`.
- `(70) Remittance Information`.

CZK approval must use a separate parser/check path. It must not reuse PACS-only field assumptions.

## In-Between Safety Gates

Approval should use multiple gates, not one early check:

1. **Before opening verify**
   - Lock the current reference and expected values.
   - Do not continue based on list position.

2. **After opening the pre-Verify detail page**
   - Read displayed reference.
   - Confirm it equals the locked reference.
   - Read status.
   - Confirm status is eligible, for example `MESSAGE AWAITING VERIFICATION`.
   - Parse page details and compare reference, amount, currency, date, unit, To BIC, and remittance.

3. **After clicking Verify**
   - Read displayed reference again on the verify/edit page.
   - Confirm it equals the locked reference.
   - Use the PACS or CZK/MT101 field path based on the locked payment/template.

4. **Before entering amount/date**
   - Parse verify/edit page details again.
   - Compare reference, amount, currency, date, unit, To BIC, and remittance.

5. **After filling amount/date fields**
   - Read the input values back.
   - Confirm entered amount/date equal expected values.
   - Confirm page reference still equals locked reference.

6. **Before OK**
   - Re-read visible reference/details if available.
   - Confirm the locked reference and expected amount again.
   - Click `Ok` only if all checks pass.

7. **After OK**
   - Confirm success message appears.
   - Search/check status if available.
   - Confirm status changed as expected.
   - Do not capture final payment copies until the full approval run is complete.

8. **After all references**
   - Open search flow.
   - Search each approved/matched reference.
   - Capture matched payment copies and export PDF.

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
- PACS/CZK page type does not match the expected template path.
- Success message does not appear after `Ok`.

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
- Failed after verify click before OK
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
