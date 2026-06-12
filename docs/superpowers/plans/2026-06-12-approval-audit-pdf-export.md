# Approval Audit PDF Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an HTML-styled one-file PDF export for approval dry audit evidence.

**Architecture:** Build the audit report HTML in `approval_audit.py` so it is unit-testable without PyQt. In `Main.py`, keep the current dry audit flow and add an `Export Audit PDF` button that renders the stored audit results through `QTextDocument` and `QPrinter`.

**Tech Stack:** Python, PyQt6 `QTextDocument`, PyQt6 `QPrinter`, existing unittest suite.

---

### Task 1: Test And Build Audit HTML

**Files:**
- Modify: `approval_audit.py`
- Modify: `tests/test_approval_audit.py`

- [ ] Add a failing unit test for `build_approval_audit_html` that checks title, summary counts, escaped text, and payment copy content.
- [ ] Implement `build_approval_audit_html(results, excel_file="", run_date="")` using `html.escape` and inline CSS.
- [ ] Run `python3 -m unittest tests.test_approval_audit.ApprovalAuditTests.test_build_approval_audit_html_creates_styled_report` and verify pass.

### Task 2: Wire PDF Export UI

**Files:**
- Modify: `Main.py`

- [ ] Add imports for `QTextDocument` and `QPrinter`.
- [ ] Track `self.last_approval_results` after live/final audit updates.
- [ ] Add `Export Audit PDF` next to the approval copy/view buttons.
- [ ] Implement `_export_approval_audit_pdf` using `QFileDialog.getSaveFileName`, `QPrinter.PdfFormat`, and `QTextDocument.print`.
- [ ] Enable the export button only when results exist.

### Task 3: Verify And Commit

**Files:**
- All changed files

- [ ] Run `python3 -m unittest discover tests`.
- [ ] Run `python3 -m compileall Main.py approval_audit.py browser_launch.py payment_mapping.py`.
- [ ] Clean cache folders.
- [ ] Commit and push.
