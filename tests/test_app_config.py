import os
import tempfile
import unittest

from app_config import (
    DEFAULT_FUNDING_REFERENCE,
    default_settings,
    display_funding_reference,
    load_settings,
    normalize_settings,
    parse_funding_reference,
    save_settings,
)


class AppConfigTests(unittest.TestCase):
    def test_default_settings_include_operational_defaults(self):
        settings = default_settings(home_dir="/Users/example")

        self.assertEqual(settings["funding_reference"], DEFAULT_FUNDING_REFERENCE)
        self.assertEqual(settings["output_folder"], os.path.join("/Users/example", "Downloads"))
        self.assertTrue(settings["stop_approval_on_first_failure"])
        self.assertTrue(any(rule["template"] == "APUSDPACS" for rule in settings["approval_rules"]))
        usd_rule = next(rule for rule in settings["approval_rules"] if rule["template"] == "APUSDPACS")
        aud_rule = next(rule for rule in settings["approval_rules"] if rule["template"] == "APAUDPACS")
        self.assertEqual(usd_rule["owning_unit"], "CCT_CHUK")
        self.assertEqual(aud_rule["owning_unit"], "TGBP")

    def test_normalize_settings_preserves_known_values_and_repairs_missing_values(self):
        settings = normalize_settings(
            {
                "browser_path": "C:/Tools/msedge.exe",
                "output_folder": "C:/Reports",
                "funding_reference": "CO6000",
                "stop_approval_on_first_failure": False,
                "approval_rules": [{
                    "template": "APUSDPACS",
                    "to_bic": "CUSTOMBICXXX",
                    "flow": "PACS",
                    "owning_unit": "CUSTOM_UNIT",
                }],
            },
            home_dir="/Users/example",
        )

        self.assertEqual(settings["browser_path"], "C:/Tools/msedge.exe")
        self.assertEqual(settings["output_folder"], "C:/Reports")
        self.assertEqual(settings["funding_reference"], "CO6000")
        self.assertFalse(settings["stop_approval_on_first_failure"])
        self.assertEqual(settings["approval_rules"][0]["to_bic"], "CUSTOMBICXXX")
        self.assertEqual(settings["approval_rules"][0]["owning_unit"], "CUSTOM_UNIT")

    def test_load_settings_returns_defaults_for_missing_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = load_settings(os.path.join(temp_dir, "missing.json"), home_dir=temp_dir)

        self.assertEqual(settings["funding_reference"], DEFAULT_FUNDING_REFERENCE)

    def test_existing_rule_without_owning_unit_inherits_template_default(self):
        settings = normalize_settings({
            "approval_rules": [{"template": "APAUDPACS", "to_bic": "NATAAU3302S", "flow": "PACS"}],
        })

        aud_rule = next(rule for rule in settings["approval_rules"] if rule["template"] == "APAUDPACS")
        self.assertEqual(aud_rule["owning_unit"], "TGBP")

    def test_save_and_load_settings_round_trip(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "settings.json")
            save_settings({"funding_reference": "CO7000"}, path=path, home_dir=temp_dir)
            loaded = load_settings(path, home_dir=temp_dir)

        self.assertEqual(loaded["funding_reference"], "CO7000")

    def test_funding_reference_display_round_trip(self):
        self.assertEqual(display_funding_reference("CO5590"), "Funding CO5590")
        self.assertEqual(parse_funding_reference("Funding CO5590"), "CO5590")
        self.assertEqual(parse_funding_reference("CO5590"), "CO5590")


if __name__ == "__main__":
    unittest.main()
