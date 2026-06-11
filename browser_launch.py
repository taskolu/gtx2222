import os
import sys


def get_bundled_browser_executable(base_path=None):
    browser_root = base_path or os.path.join(os.path.dirname(__file__), "browsers")
    for chromium_dir in ("chromium-1179", "chromium-1148"):
        executable = os.path.join(browser_root, chromium_dir, "chrome-win", "chrome.exe")
        if os.path.exists(executable):
            return executable
    return None


def get_browser_launch_options():
    bundled_executable = get_bundled_browser_executable(
        os.path.join(sys._MEIPASS, "browsers") if getattr(sys, "frozen", False) else None
    )
    if bundled_executable:
        return {"executable_path": bundled_executable, "headless": False}

    return {"channel": "msedge", "headless": False}
