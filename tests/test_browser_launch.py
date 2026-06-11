import unittest
from unittest.mock import patch

import browser_launch


class BrowserLaunchTests(unittest.TestCase):
    def test_uses_bundled_edge_application_when_available(self):
        def fake_exists(path):
            return path == "browsers/msedge/Application/msedge.exe"

        with patch("browser_launch.os.path.exists", side_effect=fake_exists):
            executable = browser_launch.get_bundled_browser_executable("browsers")

        self.assertEqual(executable, "browsers/msedge/Application/msedge.exe")

    def test_bundled_edge_uses_persistent_context(self):
        def fake_exists(path):
            return path.replace("./", "") == "browsers/msedge/Application/msedge.exe"

        with patch("browser_launch.os.path.exists", side_effect=fake_exists), \
                patch.object(browser_launch.sys, "frozen", True, create=True), \
                patch.object(browser_launch.sys, "_MEIPASS", ".", create=True):
            options = browser_launch.get_browser_launch_options()

        self.assertTrue(options["use_persistent_context"])

    def test_source_run_uses_installed_edge_when_no_bundled_browser_exists(self):
        with patch.object(browser_launch.sys, "frozen", False, create=True), \
                patch("browser_launch.os.path.exists", return_value=False):
            self.assertEqual(
                browser_launch.get_browser_launch_options(),
                {"channel": "msedge", "headless": False},
            )

    def test_uses_bundled_browser_when_executable_exists(self):
        def fake_exists(path):
            return path.endswith("chromium-1179/chrome-win/chrome.exe")

        with patch("browser_launch.os.path.exists", side_effect=fake_exists):
            options = browser_launch.get_browser_launch_options()

        self.assertEqual(options["headless"], False)
        self.assertTrue(options["executable_path"].endswith("chromium-1179/chrome-win/chrome.exe"))

    def test_finds_any_bundled_chromium_version(self):
        def fake_exists(path):
            return path == "browsers/chromium-9999/chrome-win/chrome.exe"

        with patch("browser_launch.os.path.isdir", return_value=True), \
                patch("browser_launch.os.listdir", return_value=["chromium-9999"]), \
                patch("browser_launch.os.path.exists", side_effect=fake_exists):
            executable = browser_launch.get_bundled_browser_executable("browsers")

        self.assertEqual(
            executable,
            "browsers/chromium-9999/chrome-win/chrome.exe",
        )


if __name__ == "__main__":
    unittest.main()
