# PACS Template Migration Design

## Goal

Update the GTExchange payment automation for the ISO 20022/PACS website flow while preserving the existing weekly Excel import workflow.

## Current Behavior

The app reads the Excel funding workbook, maps old funding codes to MT-style template names, creates a message from the template, fills MT amount/date/remittance fields, and captures the generated payment reference.

## New Behavior

For all migrated templates except CZK, the app maps the old Excel code to the new PACS template name:

- `AUDCUKBOA` -> `APAUDPACS`
- `CHFCUKCSB` -> `APCHFPACS`
- `EURCHKING` -> `EURPMTAP2PACS`
- `HKDCUKBOA` -> `APHKDPACS`
- `JPYCUKCIT` -> `APJPYPACS`
- `GBPCHBARX` -> `APGBPPACS`
- `GBPCVBAROPS` -> `APGBPPACS2`
- `USDBNYCHKINC` -> `APUSDPACS`
- `CADCHKRBC` and `CADBMOIN` -> `APCADPACS`
- `NZDCUKCIT` -> `APNZDPACS`
- `SGDCHKBNY` -> `APSGDPACS`
- `PLNCUKING` -> `APPLNPACS`

`EURMALAP` remains skipped. `CZKCUKKOM` keeps the old `APFUNDINGCZK` special flow.

## Browser Flow

The PACS flow selects the creating unit, searches the PACS template, captures the correspondent identifier from the `FinInstnId-36` table, creates the message, selects the owning unit, pastes the captured correspondent identifier, opens `Empty message Text`, copies/reads the generated message id, fills `InstrId` and `EndToEndId`, generates the message, then fills PACS amount/date/narrative fields.

Amount selectors must avoid fixed `Value-327` and `Value-348` ids because those vary by template. The code should use role/label-based locators where possible and fall back to value-like fields only if needed.

## Error Handling

The existing licence popup handler stays in place and is called around login/navigation and the new PACS steps. If correspondent id or PACS fields cannot be found, that payment is marked as an error and processing continues with the next row.

## Tests

Add pure Python tests for the new mapping and text helpers so the template migration can be verified without logging into GTExchange.
