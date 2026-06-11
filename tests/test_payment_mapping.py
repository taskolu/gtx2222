import unittest

from payment_mapping import (
    build_narrative,
    format_amount,
    get_pacs_amount_field_ids,
    is_valid_payment_code,
    resolve_payment_template,
)


class PaymentMappingTests(unittest.TestCase):
    def test_resolves_old_excel_codes_to_new_pacs_templates(self):
        cases = {
            "AUDCUKBOA": ("APAUDPACS", "TGBP"),
            "CHFCUKCSB": ("APCHFPACS", "TGBP"),
            "EURCHKING": ("EURPMTAP2PACS", "CCT_CHUK"),
            "HKDCUKBOA": ("APHKDPACS", "TGBP"),
            "JPYCUKCIT": ("APJPYPACS", "CCT_CHUK"),
            "GBPCHBARX": ("APGBPPACS", "CCT_CHUK"),
            "GBPCVBAROPS": ("APGBPPACS2", "CCT_CHUK"),
            "USDBNYCHKINC": ("APUSDPACS", "CCT_CHUK"),
            "CADCHKRBC": ("APCADPACS", "CCT_CHUK"),
            "CADBMOIN": ("APCADPACS", "CCT_CHUK"),
            "NZDCUKCIT": ("APNZDPACS", "CCT_CHUK"),
            "SGDCHKBNY": ("APSGDPACS", "CCT_CHUK"),
            "PLNCUKING": ("APPLNPACS", "CCT_CHUK"),
        }

        for code, expected in cases.items():
            with self.subTest(code=code):
                resolved = resolve_payment_template(code)
                self.assertIsNotNone(resolved)
                self.assertEqual((resolved.template, resolved.unit), expected)
                self.assertTrue(resolved.uses_pacs_flow)

    def test_keeps_czk_on_existing_special_flow(self):
        resolved = resolve_payment_template("CZKCUKKOM")

        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.template, "APFUNDINGCZK")
        self.assertEqual(resolved.unit, "CCT_CHUK")
        self.assertFalse(resolved.uses_pacs_flow)

    def test_skips_bov_eur_platform(self):
        self.assertIsNone(resolve_payment_template("EURMALAP"))
        self.assertFalse(is_valid_payment_code("EURMALAP"))

    def test_accepts_new_template_names_as_valid_input(self):
        self.assertTrue(is_valid_payment_code("APAUDPACS"))
        resolved = resolve_payment_template("APGBPPACS2")

        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.template, "APGBPPACS2")
        self.assertEqual(resolved.unit, "CCT_CHUK")

    def test_formats_amount_with_two_decimals_without_commas(self):
        self.assertEqual(format_amount("1,936.457"), "1936.46")
        self.assertEqual(format_amount(43622.72), "43622.72")

    def test_formats_jpy_amount_without_decimals(self):
        self.assertEqual(format_amount(660436.0, "JPYCUKCIT"), "660436")
        self.assertEqual(format_amount("660,436.49", "APJPYPACS"), "660436")

    def test_returns_pacs_amount_field_ids(self):
        self.assertEqual(
            get_pacs_amount_field_ids(),
            ("rightTreeForm:Value-327", "rightTreeForm:Value-348"),
        )

    def test_builds_pacs_narrative_as_single_restricted_line(self):
        narrative = build_narrative(
            "CO5590",
            "OTR6591556,OTR6591649,OTR6591638,OTR6591541,OTR6591573",
        )

        self.assertNotIn("\n", narrative)
        self.assertLessEqual(len(narrative), 140)
        self.assertIn("OTR6591649", narrative)


if __name__ == "__main__":
    unittest.main()
