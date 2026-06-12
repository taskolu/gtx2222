import os
import sys
import time
import urllib.request


def wait_for_cdp_endpoint(endpoint, process=None, timeout=20, urlopen=urllib.request.urlopen, sleep=time.sleep):
    deadline = time.time() + timeout
    version_url = f"{endpoint}/json/version"
    while time.time() < deadline:
        try:
            with urlopen(version_url, timeout=1) as response:
                if response.status == 200:
                    return
        except Exception:
            sleep(0.25)
    raise TimeoutError("Timed out waiting for bundled Edge remote debugging")


def build_edge_cdp_args(executable_path, user_data_dir, port):
    return [
        executable_path,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={user_data_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-search-engine-choice-screen",
        "--disable-features=RendererCodeIntegrity",
        "about:blank",
    ]


def get_bundled_browser_executable(base_path=None):
    browser_root = base_path or os.path.join(os.path.dirname(__file__), "browsers")
    chromium_dirs = []
    if os.path.isdir(browser_root):
        chromium_dirs = sorted(
            name for name in os.listdir(browser_root)
            if name.startswith("chromium-")
        )
    chromium_dirs.extend(("chromium-1179", "chromium-1148"))

    for chromium_dir in chromium_dirs:
        for chrome_dir in ("chrome-win64", "chrome-win"):
            executable = os.path.join(browser_root, chromium_dir, chrome_dir, "chrome.exe")
            if os.path.exists(executable):
                return executable

    edge_executable = os.path.join(browser_root, "msedge", "Application", "msedge.exe")
    if os.path.exists(edge_executable):
        return edge_executable
    return None


def get_browser_launch_options():
    bundled_executable = get_bundled_browser_executable(
        os.path.join(sys._MEIPASS, "browsers") if getattr(sys, "frozen", False) else None
    )
    if bundled_executable:
        options = {"executable_path": bundled_executable, "headless": False}
        if os.path.basename(bundled_executable).lower() == "msedge.exe":
            options["use_cdp"] = True
        return options

    return {"channel": "msedge", "headless": False}
