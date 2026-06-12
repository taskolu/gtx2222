import unittest
from unittest.mock import patch

import browser_launch


class BrowserLaunchTests(unittest.TestCase):
    def test_bundled_edge_cdp_args_disable_renderer_code_integrity(self):
        args = browser_launch.build_edge_cdp_args(
            "msedge.exe",
            "profile-dir",
            9222,
        )

        self.assertIn("--disable-features=RendererCodeIntegrity", args)

    def test_wait_for_cdp_allows_parent_process_to_exit(self):
        class FakeProcess:
            def poll(self):
                return 0

        class FakeResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

        browser_launch.wait_for_cdp_endpoint(
            "http://127.0.0.1:9222",
            FakeProcess(),
            timeout=1,
            urlopen=lambda url, timeout: FakeResponse(),
            sleep=lambda seconds: None,
        )

    def test_uses_bundled_edge_application_when_available(self):
        def fake_exists(path):
            return path == "browsers/msedge/Application/msedge.exe"

        with patch("browser_launch.os.path.exists", side_effect=fake_exists):
            executable = browser_launch.get_bundled_browser_executable("browsers")

        self.assertEqual(executable, "browsers/msedge/Application/msedge.exe")

    def test_bundled_edge_uses_cdp_launch(self):
        def fake_exists(path):
            return path.replace("./", "") == "browsers/msedge/Application/msedge.exe"

        with patch("browser_launch.os.path.exists", side_effect=fake_exists), \
                patch.object(browser_launch.sys, "frozen", True, create=True), \
                patch.object(browser_launch.sys, "_MEIPASS", ".", create=True):
            options = browser_launch.get_browser_launch_options()

        self.assertTrue(options["use_cdp"])

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
