import re
import unittest
from pathlib import Path


class MainSourceTests(unittest.TestCase):
    def test_waits_before_clicking_create_message(self):
        source = Path("Main.py").read_text(encoding="utf-8")

        pacs_click = re.search(
            r"def _click_create_message\(self, page\):"
            r".*?page\.wait_for_timeout\(1000\)"
            r".*?page\.get_by_role\(\"button\", name=\"Create Message\"\)\.click\(\)",
            source,
            re.DOTALL,
        )
        legacy_click = re.search(
            r"# Create message"
            r".*?page\.wait_for_timeout\(1000\)"
            r".*?page\.get_by_role\(\"button\", name=\"Create Message\"\)\.click\(\)",
            source,
            re.DOTALL,
        )

        self.assertIsNotNone(pacs_click)
        self.assertIsNotNone(legacy_click)


if __name__ == "__main__":
    unittest.main()
