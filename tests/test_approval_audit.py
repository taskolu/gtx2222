import unittest

from approval_audit import (
    compare_payment_details,
    expected_to_bic,
    normalize_date,
    parse_payment_details,
    parse_reference_lines,
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


if __name__ == "__main__":
    unittest.main()
