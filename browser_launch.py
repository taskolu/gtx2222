import os
import sys


def get_bundled_browser_executable(base_path=None):
    browser_root = base_path or os.path.join(os.path.dirname(__file__), "browsers")
    edge_executable = os.path.join(browser_root, "msedge", "Application", "msedge.exe")
    if os.path.exists(edge_executable):
        return edge_executable

    chromium_dirs = []
    if os.path.isdir(browser_root):
        chromium_dirs = sorted(
            name for name in os.listdir(browser_root)
            if name.startswith("chromium-")
        )
    chromium_dirs.extend(("chromium-1179", "chromium-1148"))

    for chromium_dir in chromium_dirs:
        executable = os.path.join(browser_root, chromium_dir, "chrome-win", "chrome.exe")
        if os.path.exists(executable):
            return executable
    return None


def get_browser_launch_options():
    bundled_executable = get_bundled_browser_executable(
        os.path.join(sys._MEIPASS, "browsers") if getattr(sys, "frozen", False) else None
    )
    if bundled_executable:
        options = {"executable_path": bundled_executable, "headless": False}
        if os.path.basename(bundled_executable).lower() == "msedge.exe":
            options["use_persistent_context"] = True
        return options

    return {"channel": "msedge", "headless": False}
