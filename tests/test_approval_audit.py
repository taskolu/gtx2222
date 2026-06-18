import unittest

from approval_audit import (
    approval_confirmation_values,
    approval_flow,
    approval_page_status,
    approval_status_is_already_processed,
    approval_status_is_eligible,
    approval_template_name,
    build_approval_precheck_decision,
    build_approval_audit_html,
    compare_payment_details,
    expected_to_bic,
    extract_gtexchange_print_view_html,
    format_payment_copy,
    normalize_date,
    parse_legacy_payment_details,
    parse_payment_details,
    parse_reference_lines,
    is_reportable_payment_copy_result,
    is_verify_no_search_item_warning,
    supports_automated_approval,
    supports_pacs_approval,
)


DETAILS_TEXT = """
Information
E008260612AOCYQL

Unit

CCT_CHUK

To : IRVTUS3NXXX
     THE BANK OF NEW YORK MELLON

pacs.008.001.08 : FITo FICustomer Credit Transfer V08
  Group Header

  Message Identification             E008260612AOCYQL
  Creation Date Time                 12.Jun,26 T 12h37m02 (UTC+03:00)

  Credit Transfer Transaction Information
    Payment Identification

    Instruction Identification         E008260612AOCYQL
    End To End Identification          E008260612AOCYQL
    UETR                               5b19b2a3-d2e5-4821-b7a4-b499aa2cb511

  Interbank Settlement Amount
             Ccy                     USD
             Value                   1,721,621.07
  Interbank Settlement Date          12.Jun,26
  Instructed Amount
             Ccy                     USD
             Value                   1,721,621.07
  Charge Bearer                      DEBT - Borne by Debtor

    Remittance Information

    Unstructured
     Funding CO5590
      OTR6591745,OTR6591747,OTR6591681,OTR6591279,OTR6591128,OTR6591131,OTR65882
     53,OTR6588442,OTR6590458,OTR6591675,OTR6591678,OTR6
"""

CZK_DETAILS_TEXT = """
Information
E101260612AOCYQW

Unit

CCT_CHUK

From : CHFXGB3LXXX
       CONVERA UK LIMITED

To : CEKOCZPPXXX
     CESKOSLOVENSKA OBCHODNI BANKA, A.S.

MT101 : Request for Transfer
________________________________________________________________________________
A - General Information

(20 ) Sender's Reference           E101260612AOCYQW
(30 ) Requested Execution Date     15.Jun,26
________________________________________________________________________________
B - Transaction Details

(21 ) Transaction Reference        E101260612AOCYQW
(32B) Currency Transaction Amount  CZK 366,972.95
(70 ) Remittance Information       Funding CO5590 OTR6591560,OTR659164
                                   0,OTR6591545
(71A) Details of Charges           OUR
"""

VERIFY_READY_DETAILS_TEXT = DETAILS_TEXT.replace(
    "Unit\n\nCCT_CHUK",
    "Unit\n\nCCT_CHUK\n\nStatus MESSAGE AWAITING VERIFICATION",
)

ARCHIVED_DETAILS_TEXT = DETAILS_TEXT.replace(
    "Unit\n\nCCT_CHUK",
    "Unit\n\nCCT_CHUK\n\nStatus MESSAGE ARCHIVED",
)

VERIFY_READY_CZK_DETAILS_TEXT = CZK_DETAILS_TEXT.replace(
    "Unit\n\nCCT_CHUK",
    "Unit\n\nCCT_CHUK\n\nStatus MESSAGE AWAITING VERIFICATION",
)


class ApprovalAuditTests(unittest.TestCase):
    def test_parse_reference_lines(self):
        refs = parse_reference_lines(
            "APAUDPACS: E008260612AOCYOF\n"
            "APUSDPACS: E008260612AOCYQL\n"
            "bad line\n"
        )

        self.assertEqual(len(refs), 2)
        self.assertEqual(refs[1].template, "APUSDPACS")
        self.assertEqual(refs[1].reference, "E008260612AOCYQL")

    def test_parse_payment_details_text(self):
        details = parse_payment_details(DETAILS_TEXT)

        self.assertEqual(details.unit, "CCT_CHUK")
        self.assertEqual(details.to_bic, "IRVTUS3NXXX")
        self.assertEqual(details.message_id, "E008260612AOCYQL")
        self.assertEqual(details.instruction_id, "E008260612AOCYQL")
        self.assertEqual(details.end_to_end_id, "E008260612AOCYQL")
        self.assertEqual(details.interbank_ccy, "USD")
        self.assertEqual(details.interbank_amount, "1,721,621.07")
        self.assertEqual(details.settlement_date, "12.Jun,26")
        self.assertEqual(details.instructed_ccy, "USD")
        self.assertEqual(details.instructed_amount, "1,721,621.07")
        self.assertIn("Funding CO5590", details.unstructured)

    def test_normalizes_gtx_date(self):
        self.assertEqual(normalize_date("12.Jun,26"), "12.06.2026")

    def test_compare_payment_details_matches_expected_payment(self):
        payment = {
            "amount": 1721621.07,
            "source_code": "USDBNYCHKINC",
            "unit": "CCT_CHUK",
            "reference": "CO5590",
            "otr_number": (
                "OTR6591745,OTR6591747,OTR6591681,OTR6591279,OTR6591128,"
                "OTR6591131,OTR6588253,OTR6588442,OTR6590458,OTR6591675,"
                "OTR6591678,OTR6"
            ),
            "value_date": "12.06.2026",
        }

        result = compare_payment_details(payment, "E008260612AOCYQL", DETAILS_TEXT)

        self.assertEqual(result.status, "Match")
        self.assertEqual(result.issues, [])

    def test_compare_payment_details_flags_wrong_amount(self):
        payment = {
            "amount": 1721622.07,
            "source_code": "USDBNYCHKINC",
            "unit": "CCT_CHUK",
            "reference": "CO5590",
            "otr_number": "OTR6591745",
            "value_date": "12.06.2026",
        }

        result = compare_payment_details(payment, "E008260612AOCYQL", DETAILS_TEXT)

        self.assertEqual(result.status, "Needs manual review")
        self.assertTrue(any("amount mismatch" in issue.lower() for issue in result.issues))

    def test_compare_payment_details_flags_wrong_to_bic(self):
        payment = {
            "amount": 1721621.07,
            "source_code": "USDBNYCHKINC",
            "unit": "CCT_CHUK",
            "reference": "CO5590",
            "otr_number": (
                "OTR6591745,OTR6591747,OTR6591681,OTR6591279,OTR6591128,"
                "OTR6591131,OTR6588253,OTR6588442,OTR6590458,OTR6591675,"
                "OTR6591678,OTR6"
            ),
            "value_date": "12.06.2026",
        }

        result = compare_payment_details(
            payment,
            "E008260612AOCYQL",
            DETAILS_TEXT.replace("IRVTUS3NXXX", "WRONGBICXXX"),
        )

        self.assertEqual(result.status, "Needs manual review")
        self.assertTrue(any("to bic mismatch" in issue.lower() for issue in result.issues))

    def test_compare_payment_details_requires_confirmed_to_bic_mapping(self):
        payment = {
            "amount": 1721621.07,
            "source_code": "UNKNOWN",
            "template": "UNKNOWNPACS",
            "unit": "CCT_CHUK",
            "reference": "CO5590",
            "otr_number": (
                "OTR6591745,OTR6591747,OTR6591681,OTR6591279,OTR6591128,"
                "OTR6591131,OTR6588253,OTR6588442,OTR6590458,OTR6591675,"
                "OTR6591678,OTR6"
            ),
            "value_date": "12.06.2026",
        }

        result = compare_payment_details(payment, "E008260612AOCYQL", DETAILS_TEXT)

        self.assertEqual(result.status, "Needs manual review")
        self.assertTrue(any("no expected to bic mapping" in issue.lower() for issue in result.issues))

    def test_expected_to_bic_uses_approval_template_mapping(self):
        self.assertEqual(
            expected_to_bic({"source_code": "AUDCUKBOA", "template": "APAUDPACS"}),
            "NATAAU3302S",
        )
        self.assertEqual(
            expected_to_bic({"source_code": "CADBMOIN", "template": "APCADPACS"}),
            "BOFMCAM2XXX",
        )

    def test_expected_to_bic_resolves_excel_account_code_to_template(self):
        payment = {"source_code": "CHFCUKCSB", "template": "CHFCUKCSB"}

        self.assertEqual(approval_template_name(payment), "APCHFPACS")
        self.assertEqual(expected_to_bic(payment), "BOFACH2XXXX")

    def test_pacs_approval_confirmation_values_are_safe_to_type(self):
        values = approval_confirmation_values(
            {
                "amount": 1721621.07,
                "source_code": "USDBNYCHKINC",
                "template": "APUSDPACS",
                "value_date": "12.06.2026",
            }
        )

        self.assertEqual(values.currency, "USD")
        self.assertEqual(values.amount, "1721621.07")
        self.assertEqual(values.value_date, "12.06.2026")

    def test_pacs_approval_confirmation_uses_zero_decimal_currency_rules(self):
        values = approval_confirmation_values(
            {
                "amount": 660436,
                "source_code": "JPYCUKCIT",
                "template": "APJPYPACS",
                "value_date": "15.Jun,26",
            }
        )

        self.assertEqual(values.currency, "JPY")
        self.assertEqual(values.amount, "660436")
        self.assertEqual(values.value_date, "15.06.2026")

    def test_approval_flow_distinguishes_pacs_and_czk_mt101(self):
        self.assertTrue(
            supports_pacs_approval({"source_code": "USDBNYCHKINC", "template": "APUSDPACS"})
        )
        self.assertFalse(
            supports_pacs_approval(
                {"source_code": "CZKCUKKOM", "template": "APFUNDINGCZK", "uses_pacs_flow": False}
            )
        )
        self.assertTrue(
            supports_automated_approval(
                {"source_code": "CZKCUKKOM", "template": "APFUNDINGCZK", "uses_pacs_flow": False}
            )
        )
        self.assertEqual(
            approval_flow({"source_code": "CZKCUKKOM", "template": "APFUNDINGCZK", "uses_pacs_flow": False}),
            "mt101",
        )

    def test_approval_page_status_normalizes_eligible_status(self):
        status = approval_page_status(
            """
            Unit CCT_CHUK
            Priority N
            Status MESSAGE AWAITING VERIFICATION
            """
        )

        self.assertEqual(status, "MESSAGE AWAITING VERIFICATION")

    def test_approval_page_status_stops_on_archived_status(self):
        status = approval_page_status(
            """
            Unit TGBP
            Status MESSAGE ARCHIVED
            """
        )

        self.assertEqual(status, "MESSAGE ARCHIVED")
        self.assertTrue(approval_status_is_already_processed(status))
        self.assertFalse(approval_status_is_eligible(status))

    def test_approval_page_status_recognizes_awaiting_archiving_as_processed(self):
        status = approval_page_status(
            """
            Unit TGBP
            Status MESSAGE AWAITING ARCHIVING
            """
        )

        self.assertEqual(status, "MESSAGE AWAITING ARCHIVING")
        self.assertTrue(approval_status_is_already_processed(status))

    def test_identifies_verify_no_search_item_warning_text(self):
        self.assertTrue(is_verify_no_search_item_warning("Warning Warning\nNo search item found"))
        self.assertTrue(is_verify_no_search_item_warning("No search item found"))
        self.assertFalse(is_verify_no_search_item_warning("MESSAGE AWAITING VERIFICATION"))

    def test_approval_precheck_allows_matching_pacs_waiting_for_verification(self):
        payment = {
            "amount": 1721621.07,
            "source_code": "USDBNYCHKINC",
            "unit": "CCT_CHUK",
            "reference": "CO5590",
            "otr_number": (
                "OTR6591745,OTR6591747,OTR6591681,OTR6591279,OTR6591128,"
                "OTR6591131,OTR6588253,OTR6588442,OTR6590458,OTR6591675,"
                "OTR6591678,OTR6"
            ),
            "value_date": "12.06.2026",
        }

        decision = build_approval_precheck_decision(payment, "E008260612AOCYQL", VERIFY_READY_DETAILS_TEXT)

        self.assertTrue(decision.can_approve)
        self.assertEqual(decision.status, "Ready for approval")
        self.assertEqual(decision.details, "All checked fields match")

    def test_approval_precheck_skips_already_processed_payment(self):
        payment = {
            "amount": 1721621.07,
            "source_code": "USDBNYCHKINC",
            "unit": "CCT_CHUK",
            "reference": "CO5590",
            "otr_number": "OTR6591745",
            "value_date": "12.06.2026",
        }

        decision = build_approval_precheck_decision(payment, "E008260612AOCYQL", ARCHIVED_DETAILS_TEXT)

        self.assertFalse(decision.can_approve)
        self.assertEqual(decision.status, "Skipped - already processed")
        self.assertIn("MESSAGE ARCHIVED", decision.details)

    def test_approval_precheck_blocks_already_processed_payment_with_mismatch(self):
        payment = {
            "amount": 1721622.07,
            "source_code": "USDBNYCHKINC",
            "unit": "CCT_CHUK",
            "reference": "CO5590",
            "otr_number": "OTR6591745",
            "value_date": "12.06.2026",
        }

        decision = build_approval_precheck_decision(payment, "E008260612AOCYQL", ARCHIVED_DETAILS_TEXT)

        self.assertFalse(decision.can_approve)
        self.assertEqual(decision.status, "Needs manual review")
        self.assertIn("already processed, but details do not match", decision.details.lower())
        self.assertIn("amount mismatch", decision.details.lower())

    def test_approval_precheck_allows_matching_czk_mt101_waiting_for_verification(self):
        payment = {
            "amount": 366972.95,
            "source_code": "CZKCUKKOM",
            "template": "APFUNDINGCZK",
            "uses_pacs_flow": False,
            "unit": "CCT_CHUK",
            "reference": "CO5590",
            "otr_number": "OTR6591560,OTR6591640,OTR6591545",
            "value_date": "15.06.2026",
        }

        decision = build_approval_precheck_decision(payment, "E101260612AOCYQW", VERIFY_READY_CZK_DETAILS_TEXT)

        self.assertTrue(decision.can_approve)
        self.assertEqual(decision.status, "Ready for approval")
        self.assertEqual(decision.details, "All checked fields match")

    def test_approval_precheck_blocks_mismatched_details(self):
        payment = {
            "amount": 1721622.07,
            "source_code": "USDBNYCHKINC",
            "unit": "CCT_CHUK",
            "reference": "CO5590",
            "otr_number": "OTR6591745",
            "value_date": "12.06.2026",
        }

        decision = build_approval_precheck_decision(payment, "E008260612AOCYQL", VERIFY_READY_DETAILS_TEXT)

        self.assertFalse(decision.can_approve)
        self.assertEqual(decision.status, "Failed before approval")
        self.assertIn("amount mismatch", decision.details.lower())

    def test_parse_legacy_czk_payment_details(self):
        details = parse_legacy_payment_details(CZK_DETAILS_TEXT)

        self.assertEqual(details.unit, "CCT_CHUK")
        self.assertEqual(details.to_bic, "CEKOCZPPXXX")
        self.assertEqual(details.message_id, "E101260612AOCYQW")
        self.assertEqual(details.instruction_id, "E101260612AOCYQW")
        self.assertEqual(details.interbank_ccy, "CZK")
        self.assertEqual(details.interbank_amount, "366,972.95")
        self.assertEqual(details.settlement_date, "15.Jun,26")
        self.assertIn("Funding CO5590", details.unstructured)

    def test_legacy_czk_payment_details_match_expected_payment(self):
        payment = {
            "amount": 366972.95,
            "source_code": "CZKCUKKOM",
            "template": "APFUNDINGCZK",
            "uses_pacs_flow": False,
            "unit": "CCT_CHUK",
            "reference": "CO5590",
            "otr_number": "OTR6591560,OTR6591640,OTR6591545",
            "value_date": "15.06.2026",
        }

        result = compare_payment_details(payment, "E101260612AOCYQW", CZK_DETAILS_TEXT)

        self.assertEqual(result.status, "Match")
        self.assertEqual(result.issues, [])

    def test_format_payment_copy_keeps_details_ready_for_email(self):
        text = format_payment_copy("APUSDPACS", "E008260612AOCYQL", DETAILS_TEXT)

        self.assertTrue(text.startswith("APUSDPACS - E008260612AOCYQL"))
        self.assertIn("Payment copy", text)
        self.assertIn("To : IRVTUS3NXXX", text)
        self.assertIn("Interbank Settlement Amount", text)
        self.assertTrue(text.endswith("\n"))

    def test_build_approval_audit_html_creates_styled_report(self):
        html = build_approval_audit_html(
            [
                {
                    "template": "APUSDPACS",
                    "reference": "E008260612AOCYQL",
                    "expected_amount": "1,721,621.07",
                    "expected_date": "12.06.2026",
                    "status": "Match",
                    "details": "All checked fields match",
                    "payment_copy": "APUSDPACS - E008260612AOCYQL\nPayment copy\nTo : IRVTUS3NXXX",
                    "payment_copy_html": (
                        '<div class="headerPrintView"><table><tr><td><pre><span style="FONT-WEIGHT: bold;">MUR'
                        '</span></pre></td><td><pre>E008260612AOCYQL</pre></td></tr></table></div>'
                        '<pre><span class="bodyStdLabelTrueType completeDataDisplay">From : CHFXGB3LXXX\n'
                        'To : IRVTUS3NXXX</span></pre>'
                    ),
                },
                {
                    "template": "APAUDPACS",
                    "reference": "E008260612AOCYOF",
                    "expected_amount": "12,365.33",
                    "expected_date": "15.06.2026",
                    "status": "Needs manual review",
                    "details": "Amount mismatch <check>",
                    "payment_copy": "",
                },
                {
                    "template": "APCHFPACS",
                    "reference": "E008260612AOCYOI",
                    "expected_amount": "5,684.15",
                    "expected_date": "15.06.2026",
                    "status": "Match",
                    "details": "All checked fields match",
                    "payment_copy": "APCHFPACS - E008260612AOCYOI\nPayment copy\nTo : BOFACH2XXXX",
                    "payment_copy_html": (
                        '<div class="headerPrintView"><table><tr><td><pre><span style="FONT-WEIGHT: bold;">Unit'
                        '</span></pre></td><td><pre>TGBP</pre></td></tr></table></div>'
                        '<pre><span class="bodyStdLabelTrueType completeDataDisplay">From : TGBPUS3WXXX\n'
                        'To : BOFACH2XXXX</span></pre>'
                    ),
                },
            ],
            excel_file="Convera & CCT.xlsx",
            run_date="12-Jun-2026 13:00",
        )

        self.assertIn("E008260612AOCYQL", html)
        self.assertIn("E008260612AOCYOI", html)
        self.assertIn("To : IRVTUS3NXXX", html)
        self.assertIn("headerPrintView", html)
        self.assertIn("gtexchange-title", html)
        self.assertIn("border: 2px solid #4d4d4d", html)
        self.assertIn("background-color: #4f4f4f", html)
        self.assertIn(".messageBody pre", html)
        self.assertIn("border-left: 1px solid #d6d6d6", html)
        self.assertIn("border-right: 1px solid #d6d6d6", html)
        self.assertIn("box-sizing: border-box", html)
        self.assertIn("payment-separator", html)
        self.assertNotIn("page-break-before: always", html)
        self.assertNotIn("Approval Audit Pack", html)
        self.assertNotIn("Amount mismatch", html)
        self.assertNotIn("E008260612AOCYOF", html)

    def test_build_approval_audit_html_includes_approved_payment_copies(self):
        html = build_approval_audit_html(
            [
                {
                    "template": "APUSDPACS",
                    "reference": "E008260612AOCYQL",
                    "status": "Approved",
                    "payment_copy_html": (
                        '<div class="headerPrintView"><table><tr><td><pre>Unit</pre></td></tr></table></div>'
                        '<pre><span class="bodyStdLabelTrueType completeDataDisplay">To : IRVTUS3NXXX</span></pre>'
                    ),
                }
            ]
        )

        self.assertIn("E008260612AOCYQL", html)
        self.assertIn("To : IRVTUS3NXXX", html)

    def test_reportable_payment_copy_statuses_exclude_manual_review(self):
        self.assertTrue(is_reportable_payment_copy_result({"status": "Match", "payment_copy": "copy"}))
        self.assertTrue(is_reportable_payment_copy_result({"status": "Approved", "payment_copy": "copy"}))
        self.assertTrue(
            is_reportable_payment_copy_result({"status": "Skipped - already processed", "payment_copy": "copy"})
        )
        self.assertFalse(is_reportable_payment_copy_result({"status": "Needs manual review", "payment_copy": "copy"}))
        self.assertFalse(is_reportable_payment_copy_result({"status": "Approved", "payment_copy": ""}))

    def test_extract_gtexchange_print_view_html_keeps_print_header_and_body(self):
        raw_html = """
        <script>bad()</script>
        <div class="nav-tab">Navigation</div>
        <div class="headerPrintView"><table><tr><td><pre><b>MUR</b></pre></td></tr></table></div>
        <div><pre><span class="bodyStdLabelTrueType completeDataDisplay">From : CHFXGB3LXXX
To : IRVTUS3NXXX</span></pre></div>
        """

        html = extract_gtexchange_print_view_html(raw_html, "E008260612AOCYQL")

        self.assertIn("headerPrintView", html)
        self.assertIn("From : CHFXGB3LXXX", html)
        self.assertIn("To : IRVTUS3NXXX", html)
        self.assertNotIn("<script", html)
        self.assertNotIn("Navigation", html)


if __name__ == "__main__":
    unittest.main()
