# Payment Entry and Final Status Safety Design

## Scope

This change strengthens existing payment entry and approval behavior without changing the Excel format, reference order, credential storage, or normal user workflow.

## Payment Value Dates

Payment entry will use the active payment row's `value_date` directly. It will not look up a date by template name. This preserves the current behavior when duplicate templates share a date and correctly handles the uncommon case where duplicate templates have different dates.

## Unit and BIC Validation

### Creating Unit

Creating Unit is selected on the template-search page. The automation will:

1. Select the expected unit when necessary.
2. Wait 500 milliseconds.
3. Read the dropdown value back.
4. Retry up to three times if it does not match.
5. Stop the current payment before creating a message if the value still differs.

An already selected value, such as TGBP, still must be read and confirmed.

### Owning Unit and Correspondent BIC

On the payment-creation page, the automation will treat Owning Unit and Correspondent BIC as one validation pair:

1. Select the expected Owning Unit when necessary.
2. Enter and apply the Correspondent BIC captured from the selected template.
3. Wait 500 milliseconds.
4. Read back both values.
5. Retry the pair up to three times if either value differs.
6. Stop the current payment before entering payment details if the pair still does not match.

No unit-selection failure may be logged and ignored.

## Final Approval Status

After all approval actions finish, the Search flow will check each approved reference for up to 30 seconds.

Successful final statuses are:

- `MESSAGE AWAITING ARCHIVING`
- `MESSAGE ARCHIVED`
- `MESSAGE VERIFIED`
- `MESSAGE PROCESSED`

`MESSAGE REJECTED` or `REJECTED` produces a `Rejected` result. Rejected results are styled red and excluded from PDF/payment-copy output.

Any other status or timeout produces `Status unknown` and is also excluded from PDF/payment-copy output. A result remains `Approved` only after both the final status and payment details match.

## Browser Profile Cleanup

Temporary browser profile directories remain useful for isolation while a run is active. Every profile created by the app will be deleted after browser shutdown. A launch failure will also terminate the browser process and remove its profile.

## Settings

Remove the unused `Stop approval on first failure` setting from the Settings dialog and persisted defaults. Approval continues to stop on the first unsafe or failed item.

## Explicitly Unchanged

- Duplicate-template references continue to pair with Excel rows in pasted order.
- Credential storage behavior is unchanged.
- Worker signal architecture is unchanged.
- Confirmation-reference capture behavior is unchanged.
- Approval rule Flow remains visible in Settings.

## Tests

- Active payment rows retain their own value dates when templates repeat.
- Creating Unit retries and fails closed after three mismatches.
- Owning Unit and Correspondent BIC are validated together and fail closed.
- Final success, rejected, unknown, and delayed status transitions are covered.
- Rejected and unknown results are excluded from reportable payment copies.
- Temporary profiles are removed after success and launch failure.
- Settings no longer include the stop-on-first-failure option.
- Existing parser, mapping, PDF, browser, and configuration tests continue to pass.
