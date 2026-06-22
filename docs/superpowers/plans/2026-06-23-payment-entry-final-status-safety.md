# Payment Entry and Final Status Safety Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make payment entry fail closed on incorrect units/BIC, preserve row-specific dates, confirm terminal approval status, clean temporary browser profiles, and remove an unused setting.

**Architecture:** Add small reusable retry/resource helpers outside the PyQt window so critical behavior is unit-testable without a browser. Keep GTExchange selectors and orchestration in the existing workers, while moving final-status classification into `approval_audit.py`.

**Tech Stack:** Python 3.11+, unittest, PyQt6, Playwright sync API, PyInstaller.

## Global Constraints

- Unit/BIC validation delays are exactly 500 ms, 1000 ms, and 1500 ms.
- A payment stops before detail entry when Creating Unit or the Owning Unit/BIC pair cannot be confirmed.
- Final status is checked for up to 30 seconds after approval actions complete.
- Rejected and unknown results are excluded from payment-copy PDF output.
- Duplicate-template pairing, credentials, worker signals, and reference capture are unchanged.

---

### Task 1: Retry and Browser Resource Helpers

**Files:**
- Modify: `browser_launch.py`
- Test: `tests/test_browser_launch.py`

**Interfaces:**
- Produces: `VERIFICATION_DELAYS_MS`, `run_verified_action(action, verify, wait)`, and `BrowserSessionResources`.

- [ ] Write failing tests proving the retry helper uses 500/1000/1500 ms, succeeds on a later read-back, and raises after three failures.
- [ ] Write failing tests proving browser resources terminate tracked processes and remove tracked profile directories.
- [ ] Run `python3 -m unittest tests.test_browser_launch` and confirm the new tests fail for missing interfaces.
- [ ] Implement the minimal retry helper and resource registry.
- [ ] Re-run `python3 -m unittest tests.test_browser_launch` and confirm it passes.

### Task 2: Row-Specific Dates and Unit/BIC Gates

**Files:**
- Modify: `Main.py`
- Modify: `payment_mapping.py`
- Test: `tests/test_payment_mapping.py`

**Interfaces:**
- Produces: `payment_value_date(payment, fallback_date)`.
- Consumes: `run_verified_action` and `BrowserSessionResources` from Task 1.

- [ ] Write a failing test proving duplicate templates retain different row-specific dates.
- [ ] Implement `payment_value_date` and update all entry paths to pass the active payment rather than searching by template.
- [ ] Add Creating Unit read-back using the progressive retry helper.
- [ ] Replace the PACS Owning Unit/BIC sequence with one paired action/read-back gate using the progressive retry helper.
- [ ] Register every temporary profile and CDP process with `BrowserSessionResources`; clean them in worker `finally` blocks and on launch failure.
- [ ] Run payment-mapping and browser tests.

### Task 3: Final Approval Status Gate

**Files:**
- Modify: `approval_audit.py`
- Modify: `Main.py`
- Test: `tests/test_approval_audit.py`

**Interfaces:**
- Produces: `FINAL_APPROVAL_SUCCESS_STATUSES`, `FINAL_APPROVAL_REJECTED_STATUSES`, and `classify_final_approval_status(details_text)` returning `approved`, `rejected`, or `unknown` plus the parsed status.

- [ ] Write failing tests for awaiting archiving, archived, verified, processed, rejected, bare rejected, and unknown statuses.
- [ ] Write a failing reportability test proving Rejected and Status unknown are excluded.
- [ ] Implement final-status classification.
- [ ] Change post-OK state to `Approval submitted` until final Search confirmation.
- [ ] Poll final Search status for up to 30 seconds; set Approved only after terminal success and matching details, Rejected on rejection, otherwise Status unknown.
- [ ] Update Approval Checks display so submitted approvals show the final-status gate as active.
- [ ] Run approval-audit tests.

### Task 4: Remove Unused Stop Setting

**Files:**
- Modify: `app_config.py`
- Modify: `Main.py`
- Test: `tests/test_app_config.py`

**Interfaces:**
- Removes: `stop_approval_on_first_failure` from defaults, normalization, persistence, and Settings UI.

- [ ] Update the config test to require that the unused key is absent.
- [ ] Run the targeted test and confirm it fails.
- [ ] Remove the key and Settings checkbox while retaining fail-closed approval behavior.
- [ ] Re-run app-config tests.

### Task 5: Full Verification and Delivery

**Files:**
- Verify all modified files.

- [ ] Run `python3 -m unittest discover tests`.
- [ ] Run `python3 -m compileall Main.py app_config.py approval_audit.py browser_launch.py payment_mapping.py pdf_export.py tests`.
- [ ] Run `git diff --check` and inspect the full diff for unrelated changes.
- [ ] Remove generated `__pycache__` directories.
- [ ] Commit implementation and push `main` for Windows testing.
