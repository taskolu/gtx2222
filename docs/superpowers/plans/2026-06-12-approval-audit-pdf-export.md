# Approval Audit PDF Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an HTML-styled one-file PDF export for matched GTExchange payment copies.

**Architecture:** Build the GTExchange print-view HTML in `approval_audit.py` so it is unit-testable without PyQt. In `Main.py`, keep the current dry audit flow and add an `Export Matched Copies PDF` button that renders only matched audit results through Playwright/Chromium.

**Tech Stack:** Python, Playwright/Chromium PDF rendering, existing unittest suite.

---

### Task 1: Test And Build Audit HTML

**Files:**
- Modify: `approval_audit.py`
- Modify: `tests/test_approval_audit.py`

- [ ] Add a failing unit test for `build_approval_audit_html` that checks only matched rows are included and GTExchange print-view content is preserved.
- [ ] Implement `extract_gtexchange_print_view_html(...)` and `build_approval_audit_html(...)` using sanitized GTExchange print-view HTML and inline CSS.
- [ ] Run `python3 -m unittest tests.test_approval_audit.ApprovalAuditTests.test_build_approval_audit_html_creates_styled_report` and verify pass.

### Task 2: Wire PDF Export UI

**Files:**
- Modify: `Main.py`

- [ ] Add a small browser PDF export helper for Playwright launch/PDF options.
- [ ] Track `self.last_approval_results` after live/final audit updates.
- [ ] Capture `#container-body` HTML during each approval detail search.
- [ ] Add `Export Matched Copies PDF` next to the approval copy/view buttons.
- [ ] Implement `_export_approval_audit_pdf` using `QFileDialog.getSaveFileName` and Playwright `page.pdf`.
- [ ] Enable the export button only when matched results exist.

### Task 3: Verify And Commit

**Files:**
- All changed files

- [ ] Run `python3 -m unittest discover tests`.
- [ ] Run `python3 -m compileall Main.py approval_audit.py browser_launch.py payment_mapping.py`.
- [ ] Clean cache folders.
- [ ] Commit and push.
