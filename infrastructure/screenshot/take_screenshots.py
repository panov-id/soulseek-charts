"""Screenshot the dashboard in both themes and both layouts.

Rendering it and looking at it is the only way to catch label collisions,
overflow and broken geometry — a palette validator checks colour, not layout.
Console errors are reported too: a silent JavaScript failure looks like an
empty page.
"""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
OUTPUT_DIRECTORY = Path("/output")

DESKTOP_VIEWPORT = {"width": 1200, "height": 1000}
MOBILE_VIEWPORT = {"width": 390, "height": 900}

PAGES = [
    ("charts", "/"),
    ("artist", "/#/artist/aphex%20twin"),
    ("about", "/about.html"),
]


def main() -> int:
    console_errors: list[str] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()

        for color_scheme in ("light", "dark"):
            for viewport_name, viewport in (
                ("desktop", DESKTOP_VIEWPORT),
                ("mobile", MOBILE_VIEWPORT),
            ):
                context = browser.new_context(
                    viewport=viewport,
                    color_scheme=color_scheme,
                    device_scale_factor=2,
                )
                page = context.new_page()
                page.on(
                    "console",
                    lambda message: console_errors.append(message.text)
                    if message.type == "error"
                    else None,
                )
                page.on("pageerror", lambda error: console_errors.append(str(error)))

                for page_name, path in PAGES:
                    page.goto(f"{BASE_URL}{path}", wait_until="networkidle")
                    # The hash router renders after load; give it a beat.
                    page.wait_for_timeout(600)
                    file_name = f"{page_name}-{color_scheme}-{viewport_name}.png"
                    page.screenshot(
                        path=str(OUTPUT_DIRECTORY / file_name),
                        full_page=(viewport_name == "desktop"),
                    )
                    print(f"saved {file_name}")

                context.close()

        browser.close()

    if console_errors:
        print("\nCONSOLE ERRORS:")
        for message in dict.fromkeys(console_errors):
            print(f"  {message}")
        return 1

    print("\nNo console errors.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
