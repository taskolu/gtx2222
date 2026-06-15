import unittest

from pdf_export import prepare_pdf_launch_options, render_html_pdf_with_playwright


class PdfExportTests(unittest.TestCase):
    def test_pdf_launch_options_force_headless_browser_rendering(self):
        options = prepare_pdf_launch_options({"channel": "msedge", "headless": False})

        self.assertEqual(options["channel"], "msedge")
        self.assertTrue(options["headless"])

    def test_pdf_launch_options_remove_cdp_flags(self):
        options = prepare_pdf_launch_options({
            "executable_path": r"C:\browsers\msedge\Application\msedge.exe",
            "headless": False,
            "use_cdp": True,
            "use_persistent_context": True,
        })

        self.assertNotIn("use_cdp", options)
        self.assertNotIn("use_persistent_context", options)
        self.assertTrue(options["headless"])

    def test_pdf_launch_options_disable_edge_renderer_code_integrity(self):
        options = prepare_pdf_launch_options({
            "executable_path": r"C:\browsers\msedge\Application\msedge.exe",
            "headless": False,
        })

        self.assertIn("--disable-features=RendererCodeIntegrity", options["args"])

    def test_render_html_pdf_uses_playwright_pdf_with_backgrounds(self):
        class FakePage:
            def __init__(self):
                self.content = None
                self.media = None
                self.pdf_options = None

            def set_content(self, html, wait_until):
                self.content = (html, wait_until)

            def emulate_media(self, media):
                self.media = media

            def pdf(self, **kwargs):
                self.pdf_options = kwargs

        class FakeBrowser:
            def __init__(self):
                self.page = FakePage()
                self.closed = False

            def new_page(self, viewport):
                self.viewport = viewport
                return self.page

            def close(self):
                self.closed = True

        class FakeChromium:
            def __init__(self):
                self.launch_options = None
                self.browser = FakeBrowser()

            def launch(self, **kwargs):
                self.launch_options = kwargs
                return self.browser

        class FakePlaywright:
            def __init__(self):
                self.chromium = FakeChromium()

        class FakeSyncPlaywright:
            def __init__(self):
                self.playwright = FakePlaywright()

            def __call__(self):
                return self

            def __enter__(self):
                return self.playwright

            def __exit__(self, exc_type, exc_value, traceback):
                return False

        fake_sync = FakeSyncPlaywright()

        render_html_pdf_with_playwright(
            "<html><body>copy</body></html>",
            "output.pdf",
            fake_sync,
            launch_options_provider=lambda: {"channel": "msedge", "headless": False},
        )

        browser = fake_sync.playwright.chromium.browser
        self.assertTrue(fake_sync.playwright.chromium.launch_options["headless"])
        self.assertEqual(browser.page.content, ("<html><body>copy</body></html>", "load"))
        self.assertEqual(browser.page.media, "print")
        self.assertEqual(browser.page.pdf_options["path"], "output.pdf")
        self.assertTrue(browser.page.pdf_options["print_background"])
        self.assertEqual(browser.page.pdf_options["format"], "A4")
        self.assertTrue(browser.closed)


if __name__ == "__main__":
    unittest.main()
