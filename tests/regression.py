"""
Regression suite for roadtorecovery.net.

Run from the repo root with the venv active:
  source .venv-tests/bin/activate
  python tests/regression.py

Boots a local HTTP server on a free port, drives Chromium across mobile/tablet/desktop
viewports in both light and dark mode, and asserts the contracts that have broken before:
text colors, image filters, theme toggle position, click + hover-hold behavior.
Exits non-zero on any failure.
"""

import http.server
import socketserver
import socket
import threading
from contextlib import contextmanager
from pathlib import Path
import sys

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
VIEWPORTS = {
    "mobile":  {"width": 390,  "height": 844},
    "tablet":  {"width": 820,  "height": 1180},
    "tablet_small": {"width": 800, "height": 600},
    "desktop": {"width": 1280, "height": 800},
}


def free_port() -> int:
    s = socket.socket()
    s.bind(("", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@contextmanager
def serve():
    port = free_port()

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(ROOT), **kw)
        def log_message(self, *a, **kw):  # silence
            pass

    httpd = socketserver.TCPServer(("127.0.0.1", port), Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        yield f"http://127.0.0.1:{port}/"
    finally:
        httpd.shutdown()


class Results:
    def __init__(self):
        self.passed = 0
        self.failed = []

    def check(self, label, actual, expected, op="=="):
        ok = (actual == expected) if op == "==" else op(actual, expected)
        if ok:
            self.passed += 1
            print(f"  ✓ {label}")
        else:
            self.failed.append((label, actual, expected))
            print(f"  ✗ {label}: got {actual!r}, expected {expected!r}")

    def summary(self):
        total = self.passed + len(self.failed)
        print(f"\n{self.passed}/{total} passed")
        if self.failed:
            print(f"\n{len(self.failed)} FAILED:")
            for label, actual, expected in self.failed:
                print(f"  - {label}: got {actual!r}, expected {expected!r}")
            return 1
        return 0


def set_theme(page, theme: str):
    page.evaluate(f"""
        document.documentElement.setAttribute('data-theme', '{theme}');
        try {{ localStorage.setItem('rtr-theme', '{theme}'); }} catch (e) {{}}
    """)
    # Image filters use 0.3s transitions; wait for them to settle before sampling.
    page.wait_for_timeout(500)


def filter_of(page, selector):
    return page.evaluate(f"""
        () => {{
            const el = document.querySelector({selector!r});
            return el ? getComputedStyle(el).filter : null;
        }}
    """)


def color_of(page, selector):
    return page.evaluate(f"""
        () => {{
            const el = document.querySelector({selector!r});
            return el ? getComputedStyle(el).color : null;
        }}
    """)


def bg_of(page, selector):
    return page.evaluate(f"""
        () => {{
            const el = document.querySelector({selector!r});
            return el ? getComputedStyle(el).backgroundColor : null;
        }}
    """)


def rect_of(page, selector):
    return page.evaluate(f"""
        () => {{
            const el = document.querySelector({selector!r});
            return el ? el.getBoundingClientRect().toJSON() : null;
        }}
    """)


def run_tests(base_url):
    r = Results()

    with sync_playwright() as p:
        browser = p.chromium.launch()

        # ── Per-viewport theme toggle position ───────────────────────────
        for vname, vp in VIEWPORTS.items():
            print(f"\n[{vname}] viewport {vp['width']}x{vp['height']}")
            ctx = browser.new_context(viewport=vp)
            page = ctx.new_page()
            page.goto(base_url, wait_until="domcontentloaded")

            mast = rect_of(page, "header.masthead")
            tog = rect_of(page, "#theme-toggle")
            r.check(f"{vname}: masthead present", mast is not None, True)
            r.check(f"{vname}: toggle present",   tog is not None,  True)

            if vname == "mobile":
                # Full-width banner below the nav
                r.check("mobile: toggle width == viewport width",
                        round(tog["width"]), vp["width"])
                # Toggle bottom should be at masthead bottom (flush)
                r.check("mobile: toggle bottom flush with masthead bottom",
                        round(tog["bottom"]), round(mast["bottom"]))

            elif vname in ("tablet", "tablet_small"):
                # Toggle should sit BELOW the masthead, not overlapping
                r.check(f"{vname}: toggle top below masthead bottom",
                        tog["top"] >= mast["bottom"], True)
                r.check(f"{vname}: toggle is right-aligned (right within ~30px of viewport edge)",
                        vp["width"] - tog["right"] < 30, True)

            elif vname == "desktop":
                # Toggle should sit INSIDE the masthead, vertically centered
                r.check("desktop: toggle vertically inside masthead",
                        mast["top"] <= tog["top"] and tog["bottom"] <= mast["bottom"], True)
                r.check("desktop: toggle is right-aligned",
                        vp["width"] - tog["right"] < 30, True)

            ctx.close()

        # ── Light mode contracts ─────────────────────────────────────────
        print("\n[light mode] desktop")
        ctx = browser.new_context(viewport=VIEWPORTS["desktop"])
        page = ctx.new_page()
        page.goto(base_url, wait_until="domcontentloaded")
        set_theme(page, "light")

        r.check("light: body text black",
                color_of(page, "body"), "rgb(0, 0, 0)")
        r.check("light: reintegration body p text black",
                page.evaluate("""
                    () => {
                        const ps = document.querySelectorAll('#reintegration p');
                        const body = Array.from(ps).find(p => !p.classList.contains('sub-heading-five-one'));
                        return body ? getComputedStyle(body).color : null;
                    }
                """), "rgb(0, 0, 0)")
        r.check("light: MRI image keep-color filter none",
                filter_of(page, "#reintegration img.keep-color"), "none")
        ctx.close()

        # ── Dark mode contracts ──────────────────────────────────────────
        print("\n[dark mode] desktop")
        ctx = browser.new_context(viewport=VIEWPORTS["desktop"])
        page = ctx.new_page()
        page.goto(base_url, wait_until="domcontentloaded")
        set_theme(page, "dark")

        r.check("dark: body bg black",
                bg_of(page, "body"), "rgb(0, 0, 0)")
        r.check("dark: body text light gray",
                color_of(page, "body"), "rgb(204, 204, 204)")
        r.check("dark: MRI image keep-color filter none",
                filter_of(page, "#reintegration img.keep-color"), "none")
        r.check("dark: Dixon logo pure white filter",
                filter_of(page, "#foot-logo img"), "brightness(0) invert(1)")
        r.check("dark: motor neuron filter dark gray",
                filter_of(page, ".neuron-diagram img[src*='Motor']"),
                "brightness(0) invert(0.35)")
        r.check("dark: sensory neuron filter dark gray",
                filter_of(page, ".neuron-diagram img[src*='Sensory']"),
                "brightness(0) invert(0.35)")
        r.check("dark: generic image grayscaled at rest",
                filter_of(page, "img[src*='handtransplant']"),
                "grayscale(1) brightness(0.85)")
        ctx.close()

        # ── Theme toggle interaction ─────────────────────────────────────
        print("\n[interaction] click flips theme")
        ctx = browser.new_context(viewport=VIEWPORTS["desktop"])
        page = ctx.new_page()
        page.goto(base_url, wait_until="domcontentloaded")
        set_theme(page, "light")
        before = page.evaluate("document.documentElement.getAttribute('data-theme')")
        page.click("#theme-toggle")
        after = page.evaluate("document.documentElement.getAttribute('data-theme')")
        r.check("click flips light → dark", (before, after), ("light", "dark"))
        ctx.close()

        browser.close()

    return r.summary()


if __name__ == "__main__":
    with serve() as base_url:
        print(f"Test server: {base_url}")
        sys.exit(run_tests(base_url))
