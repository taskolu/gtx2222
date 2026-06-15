import os
import ntpath

from browser_launch import get_browser_launch_options


def prepare_pdf_launch_options(launch_options):
    options = dict(launch_options or {})
    options.pop("use_cdp", None)
    options.pop("use_persistent_context", None)
    options["headless"] = True

    executable_path = str(options.get("executable_path") or "")
    executable_name = ntpath.basename(executable_path) or os.path.basename(executable_path)
    if executable_name.lower() == "msedge.exe":
        args = list(options.get("args") or [])
        renderer_flag = "--disable-features=RendererCodeIntegrity"
        if renderer_flag not in args:
            args.append(renderer_flag)
        options["args"] = args

    return options


def render_html_pdf_with_playwright(html, file_path, sync_playwright, launch_options_provider=get_browser_launch_options):
    launch_options = prepare_pdf_launch_options(launch_options_provider())

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(**launch_options)
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 1600})
            page.set_content(html, wait_until="load")
            page.emulate_media(media="print")
            page.pdf(
                path=file_path,
                format="A4",
                print_background=True,
                margin={
                    "top": "8mm",
                    "right": "8mm",
                    "bottom": "8mm",
                    "left": "8mm",
                },
            )
        finally:
            browser.close()
