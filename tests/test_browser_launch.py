import unittest
from unittest.mock import patch

import browser_launch


class BrowserLaunchTests(unittest.TestCase):
    def test_verify_response_allows_server_fifteen_seconds(self):
        self.assertEqual(browser_launch.VERIFY_SEARCH_TIMEOUT_MS, 15000)

    def test_verify_warning_ok_wait_is_three_seconds(self):
        self.assertEqual(browser_launch.VERIFY_WARNING_OK_TIMEOUT_MS, 3000)

    def test_verify_warning_requires_a_visible_ok_button(self):
        class FakeWarning:
            first = None

            def __init__(self):
                self.first = self

            def is_visible(self, timeout):
                return True

            def inner_text(self, timeout):
                return "No search item found"

        class EmptyButtons:
            def count(self):
                return 0

        class FakePage:
            def get_by_text(self, text):
                return FakeWarning()

            def get_by_role(self, role, name, exact):
                return EmptyButtons()

            def locator(self, selector):
                return EmptyButtons()

            def wait_for_timeout(self, milliseconds):
                pass

        with self.assertRaisesRegex(RuntimeError, "OK button is not available"):
            browser_launch.dismiss_verify_no_search_warning(FakePage(), timeout_ms=0)

    def test_verify_warning_clicks_visible_ok_and_confirms_it_closed(self):
        class FakeWarning:
            first = None

            def __init__(self):
                self.first = self
                self.hidden_waited = False

            def is_visible(self, timeout):
                return True

            def inner_text(self, timeout):
                return "No search item found"

            def wait_for(self, state, timeout):
                self.hidden_waited = state == "hidden"

        class FakeButton:
            def __init__(self):
                self.clicked = False

            def is_visible(self, timeout):
                return True

            def click(self, timeout):
                self.clicked = True

        class ButtonList:
            def __init__(self, button):
                self.button = button

            def count(self):
                return 1

            def nth(self, index):
                return self.button

        warning = FakeWarning()
        button = FakeButton()

        class FakePage:
            def get_by_text(self, text):
                return warning

            def get_by_role(self, role, name, exact):
                return ButtonList(button)

            def locator(self, selector):
                return ButtonList(button)

            def wait_for_timeout(self, milliseconds):
                pass

        dismissed = browser_launch.dismiss_verify_no_search_warning(FakePage())

        self.assertTrue(dismissed)
        self.assertTrue(button.clicked)
        self.assertTrue(warning.hidden_waited)

    def test_verify_warning_clicks_ok_exposed_as_table_cell(self):
        class FakeWarning:
            first = None

            def __init__(self):
                self.first = self
                self.hidden_waited = False

            def is_visible(self, timeout):
                return True

            def inner_text(self, timeout):
                return "No search item found"

            def wait_for(self, state, timeout):
                self.hidden_waited = state == "hidden"

        class FakeCell:
            def __init__(self):
                self.clicked = False

            def is_visible(self, timeout):
                return True

            def click(self, timeout):
                self.clicked = True

        class LocatorList:
            def __init__(self, items=()):
                self.items = items

            def count(self):
                return len(self.items)

            def nth(self, index):
                return self.items[index]

        warning = FakeWarning()
        ok_cell = FakeCell()

        class FakePage:
            def get_by_text(self, text):
                return warning

            def get_by_role(self, role, name, exact):
                if role == "cell" and name == "OK":
                    return LocatorList((ok_cell,))
                return LocatorList()

            def locator(self, selector):
                return LocatorList()

            def wait_for_timeout(self, milliseconds):
                pass

        dismissed = browser_launch.dismiss_verify_no_search_warning(
            FakePage(),
            timeout_ms=0,
        )

        self.assertTrue(dismissed)
        self.assertTrue(ok_cell.clicked)
        self.assertTrue(warning.hidden_waited)

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

    def test_prefers_bundled_chromium_over_copied_edge(self):
        def fake_exists(path):
            return path in {
                "browsers/msedge/Application/msedge.exe",
                "browsers/chromium-9999/chrome-win/chrome.exe",
            }

        with patch("browser_launch.os.path.isdir", return_value=True), \
                patch("browser_launch.os.listdir", return_value=["chromium-9999"]), \
                patch("browser_launch.os.path.exists", side_effect=fake_exists):
            executable = browser_launch.get_bundled_browser_executable("browsers")

        self.assertEqual(executable, "browsers/chromium-9999/chrome-win/chrome.exe")

    def test_finds_chrome_for_testing_win64_layout(self):
        def fake_exists(path):
            return path == "browsers/chromium-1223/chrome-win64/chrome.exe"

        with patch("browser_launch.os.path.isdir", return_value=True), \
                patch("browser_launch.os.listdir", return_value=["chromium-1223"]), \
                patch("browser_launch.os.path.exists", side_effect=fake_exists):
            executable = browser_launch.get_bundled_browser_executable("browsers")

        self.assertEqual(executable, "browsers/chromium-1223/chrome-win64/chrome.exe")

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

    def test_configured_browser_path_takes_precedence(self):
        with patch.dict("browser_launch.os.environ", {"GTX_BROWSER_PATH": "C:/Tools/msedge.exe"}), \
                patch("browser_launch.os.path.exists", return_value=True):
            options = browser_launch.get_browser_launch_options()

        self.assertEqual(options["executable_path"], "C:/Tools/msedge.exe")
        self.assertFalse(options["headless"])
        self.assertTrue(options["use_cdp"])

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
