"""Playwright Visual QC script for Wave 3 verification.

Viewport: 1366x768.
Verifies geometry of #smart-paste-box, #access_token, #client_id, #csrftoken, and #login-btn-cookie
on /login and / (connect section).
"""

import glob
import os
import socket
import tempfile
import threading
import time
import pytest
import uvicorn
from playwright.sync_api import sync_playwright

_uid = getattr(os, "getuid", lambda: "local")()
DEFAULT_SCREENSHOT_DIR = os.getenv(
    "SCREENSHOT_DIR",
    os.path.join(tempfile.gettempdir(), f"udemy_enroller_visual_qc_{_uid}"),
)
SCREENSHOT_DIR = DEFAULT_SCREENSHOT_DIR


def _is_ci_environment() -> bool:
    return (
        os.getenv("CI", "").strip().lower() in ("true", "1")
        or os.getenv("GITHUB_ACTIONS", "").strip().lower() in ("true", "1")
    )


def get_chromium_executable():
    base_dirs = []
    env_path = os.getenv("PLAYWRIGHT_BROWSERS_PATH")
    if env_path:
        base_dirs.append(env_path)

    # Linux
    base_dirs.append(os.path.expanduser("~/.cache/ms-playwright"))
    # macOS
    base_dirs.append(os.path.expanduser("~/Library/Caches/ms-playwright"))
    # Windows
    local_app_data = os.getenv("LOCALAPPDATA")
    if local_app_data:
        base_dirs.append(os.path.join(local_app_data, "ms-playwright"))
    base_dirs.append(os.path.expanduser("~/AppData/Local/ms-playwright"))

    patterns = [
        # Linux
        "chromium-*/chrome-linux*/chrome",
        "chromium_headless_shell-*/chrome-headless-shell-linux*/chrome-headless-shell",
        # macOS
        "chromium-*/chrome-mac*/Chromium.app/Contents/MacOS/Chromium",
        "chromium_headless_shell-*/chrome-headless-shell-mac*/chrome-headless-shell",
        # Windows
        "chromium-*/chrome-win*/chrome.exe",
        "chromium_headless_shell-*/chrome-headless-shell-win*/chrome-headless-shell.exe",
    ]

    for base in base_dirs:
        if not os.path.isdir(base):
            continue
        for pat in patterns:
            for match in glob.glob(os.path.join(base, pat)):
                if os.path.isfile(match) and (os.access(match, os.X_OK) or os.name == "nt"):
                    return match
    return None


CHROMIUM_PATH = get_chromium_executable()
SKIP_REASON = None
if _is_ci_environment():
    SKIP_REASON = "Playwright visual QC requires local browser environment (skipped in CI unit test step)"
elif not CHROMIUM_PATH:
    SKIP_REASON = "No local Playwright Chromium executable found"

pytestmark = pytest.mark.skipif(SKIP_REASON is not None, reason=SKIP_REASON or "")


def is_server_listening(host="127.0.0.1", port=8888):
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


@pytest.fixture(scope="session", autouse=True)
def ensure_server():
    if SKIP_REASON:
        yield
        return

    server_started = False
    server = None
    if not is_server_listening("127.0.0.1", 8888):
        from main import app
        config = uvicorn.Config(app, host="127.0.0.1", port=8888, log_level="warning")
        server = uvicorn.Server(config)
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        for _ in range(60):
            if is_server_listening("127.0.0.1", 8888):
                break
            time.sleep(0.1)
        server_started = True

    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    yield
    if server_started and server:
        server.should_exit = True


def test_visual_qc_login_page():
    """Visual QC for /login on 1366x768 with simulated cookie banner."""
    exec_path = CHROMIUM_PATH
    launch_kwargs = {"headless": True}
    if exec_path:
        launch_kwargs["executable_path"] = exec_path

    with sync_playwright() as p:
        browser = p.chromium.launch(**launch_kwargs)
        context = browser.new_context(viewport={"width": 1366, "height": 768})
        page = context.new_page()

        page.goto("http://127.0.0.1:8888/login", wait_until="networkidle")

        # Switch to cookie tab to display cookie form
        page.click("#tab-cookie")
        page.wait_for_selector("#cookie-form:not(.hidden)", state="visible")

        # Inject simulated 56px cookie banner fixed at bottom (Y = 712 to 768)
        page.evaluate("""() => {
            const banner = document.createElement('div');
            banner.id = 'dummy-cookie-banner';
            banner.style.position = 'fixed';
            banner.style.bottom = '0';
            banner.style.left = '0';
            banner.style.right = '0';
            banner.style.height = '56px';
            banner.style.backgroundColor = 'rgba(17, 24, 39, 0.95)';
            banner.style.color = 'white';
            banner.style.zIndex = '9999';
            banner.style.display = 'flex';
            banner.style.alignItems = 'center';
            banner.style.justifyContent = 'center';
            banner.style.fontSize = '12px';
            banner.innerText = 'Simulated Cookie Banner (56px fixed bottom, Y=712px to 768px)';
            document.body.appendChild(banner);
        }""")

        element_ids = [
            "smart-paste-box",
            "access_token",
            "client_id",
            "csrftoken",
            "login-btn-cookie",
        ]

        metrics = {}
        for el_id in element_ids:
            rect = page.evaluate(f"document.getElementById('{el_id}').getBoundingClientRect().toJSON()")
            metrics[el_id] = rect

        print("\n--- Visual QC Metrics for /login ---")
        for el_id, rect in metrics.items():
            print(f"#{el_id}: y={rect['y']:.1f}, height={rect['height']:.1f}, bottom={rect['bottom']:.1f}")

        # Check button clearance from cookie banner (Y = 712)
        button_bottom = metrics["login-btn-cookie"]["bottom"]
        clearance = 712 - button_bottom
        print(f"Clearance (712 - button_bottom={button_bottom:.1f}): {clearance:.1f}px")

        # Check 3 inputs completely above the fold and banner (y + height < 712)
        for input_id in ["access_token", "client_id", "csrftoken"]:
            bottom = metrics[input_id]["y"] + metrics[input_id]["height"]
            assert bottom < 712, f"Input #{input_id} bottom ({bottom:.1f}px) is not < 712px"

        # Save screenshot
        screenshot_path = os.path.join(SCREENSHOT_DIR, "after_login_page_compact.png")
        page.screenshot(path=screenshot_path)
        print(f"Saved screenshot to {screenshot_path}")

        # Assert clearance >= 100px
        assert clearance >= 100, f"Button clearance {clearance:.1f}px is less than 100px"

        browser.close()


def test_visual_qc_home_connect():
    """Visual QC for / (homepage connect section) on 1366x768 with simulated cookie banner."""
    exec_path = CHROMIUM_PATH
    launch_kwargs = {"headless": True}
    if exec_path:
        launch_kwargs["executable_path"] = exec_path

    with sync_playwright() as p:
        browser = p.chromium.launch(**launch_kwargs)
        context = browser.new_context(viewport={"width": 1366, "height": 768})
        page = context.new_page()

        page.goto("http://127.0.0.1:8888/#connect", wait_until="networkidle")

        # Scroll connect section into view
        page.evaluate("document.getElementById('connect').scrollIntoView(true)")
        time.sleep(0.5)

        # Switch to cookie tab
        page.click("#tab-cookie")
        page.wait_for_selector("#cookie-form:not(.hidden)", state="visible")

        # Inject simulated 56px cookie banner fixed at bottom (Y = 712 to 768)
        page.evaluate("""() => {
            const banner = document.createElement('div');
            banner.id = 'dummy-cookie-banner';
            banner.style.position = 'fixed';
            banner.style.bottom = '0';
            banner.style.left = '0';
            banner.style.right = '0';
            banner.style.height = '56px';
            banner.style.backgroundColor = 'rgba(17, 24, 39, 0.95)';
            banner.style.color = 'white';
            banner.style.zIndex = '9999';
            banner.style.display = 'flex';
            banner.style.alignItems = 'center';
            banner.style.justifyContent = 'center';
            banner.style.fontSize = '12px';
            banner.innerText = 'Simulated Cookie Banner (56px fixed bottom, Y=712px to 768px)';
            document.body.appendChild(banner);
        }""")

        element_ids = [
            "smart-paste-box",
            "access_token",
            "client_id",
            "csrftoken",
            "login-btn-cookie",
        ]

        metrics = {}
        for el_id in element_ids:
            rect = page.evaluate(f"document.getElementById('{el_id}').getBoundingClientRect().toJSON()")
            metrics[el_id] = rect

        print("\n--- Visual QC Metrics for / (Connect section) ---")
        for el_id, rect in metrics.items():
            print(f"#{el_id}: y={rect['y']:.1f}, height={rect['height']:.1f}, bottom={rect['bottom']:.1f}")

        # Check button clearance from cookie banner (Y = 712)
        button_bottom = metrics["login-btn-cookie"]["bottom"]
        clearance = 712 - button_bottom
        print(f"Clearance (712 - button_bottom={button_bottom:.1f}): {clearance:.1f}px")

        # Check 3 inputs completely above the fold and banner (y + height < 712)
        for input_id in ["access_token", "client_id", "csrftoken"]:
            bottom = metrics[input_id]["y"] + metrics[input_id]["height"]
            assert bottom < 712, f"Input #{input_id} bottom ({bottom:.1f}px) is not < 712px"

        # Save screenshot
        screenshot_path = os.path.join(SCREENSHOT_DIR, "after_home_connect_compact.png")
        page.screenshot(path=screenshot_path)
        print(f"Saved screenshot to {screenshot_path}")

        browser.close()

        # Assert clearance >= 100px
        assert clearance >= 100, f"Button clearance {clearance:.1f}px is less than 100px"
