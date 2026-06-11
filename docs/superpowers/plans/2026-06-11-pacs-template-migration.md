# PACS Template Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Update the existing PyQt/Playwright GTExchange automation to use the ISO 20022 PACS templates and fields.

**Architecture:** Extract payment mapping and text formatting into a small pure Python module, cover it with tests, then wire `Main.py` to the new mapping and PACS browser flow. Keep the CZK special flow unchanged.

**Tech Stack:** Python, pandas, PyQt6, Playwright sync API, stdlib `unittest`.

---

### Task 1: Mapping And Helper Tests

**Files:**
- Create: `payment_mapping.py`
- Create: `tests/test_payment_mapping.py`
- Modify: `Main.py`

- [ ] Write failing tests for old code to PACS template mapping, skipped EURMALAP, unchanged CZK, valid code detection, and narrative chunking.
- [ ] Run `python3 -m unittest tests.test_payment_mapping -v` and verify it fails because `payment_mapping` is missing.
- [ ] Implement `payment_mapping.py` with `resolve_payment_template`, `is_valid_payment_code`, `format_amount`, and `build_narrative`.
- [ ] Run the unittest command again and verify it passes.

### Task 2: Excel Parsing Integration

**Files:**
- Modify: `Main.py`

- [ ] Replace duplicated local valid-template lists with `is_valid_payment_code`.
- [ ] Store both the source Excel code and resolved template in each payment row.
- [ ] Keep `EURMALAP` skipped and `CZKCUKKOM` routed to `APFUNDINGCZK`.
- [ ] Run the mapping tests after integration.

### Task 3: PACS Browser Flow

**Files:**
- Modify: `Main.py`

- [ ] Add helper methods on `BrowserWorker` to capture correspondent id, fill envelope correspondent id, open PACS text, fill message ids, fill PACS amount/date/narrative, and confirm the message.
- [ ] Route all non-CZK payments through the PACS helper flow.
- [ ] Keep the existing CZK special handling unchanged.
- [ ] Run `python3 -m py_compile Main.py payment_mapping.py` and the unittest command.
