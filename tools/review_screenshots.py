"""tools/review_screenshots.py: every v2 page and device tab, shot in a real Firefox at 1920x1080
and 1366x768, for the GUI usability review (the week plan of 2026-11-23, Stage 3).

    ~/.local/share/nmas-py312/bin/python tools/review_screenshots.py [--out DIR]

The shots go to ``design/review/shots/<width>x<height>/<page>.png`` (gitignored), the viewport
as a person first sees it and the whole page beside it (``<page>.full.png``), with
``design/review/shots/index.md`` naming each page, its file and anything that could not be shot.

**What it serves.** Not the host and not a live store: the suite's own fixture world, the one
tests/test_v2_layout_in_a_browser.py draws its pages in (its ``served`` fixture: the app on
loopback, two example routers, a timeline and an update at their widest), run under
tests/conftest.py (loaded as a plugin), which gives the run a temporary ``NMAS_DATA_DIR`` and
refuses non-loopback connects. The person is the suite's verified test person, so no account
or password is made anywhere. The browser is the suite's own driver (tests/browser.py,
geckodriver), not a second one.

**Which pages.** Every GET rule of the app under ``/v2`` whose page draws the v2 frame
(``body.v2``): a rule's ``<device>``-like argument is filled with the fixture's router, and a
rule needing another argument is listed as skipped, by name. Then every device tab
tests/signed_off_screens.py names (``tab:<key>``). The list is measured from the app at run
time, so a new page is shot without this file changing.
"""
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIZES = ((1920, 1080), (1366, 768))
DEVICE = "r2"
#: Arguments a page rule may take that the fixture world can fill.
FILL = {"device": DEVICE, "name": DEVICE, "hostname": DEVICE, "host": DEVICE,
        "list_name": "Lab", "network": "Lab", "slug": "getting-started"}
OUT_ENV = "NMAS_REVIEW_SHOTS_OUT"


def main(argv=None) -> int:
    import argparse

    import pytest

    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", default=os.path.join(ROOT, "design", "review", "shots"))
    ap.add_argument("--static", metavar="DIR",
                    help="shoot every .html file under DIR (static mockups, no app) into "
                         "DIR/<folder>/shots/<size>/<name>.png instead")
    a = ap.parse_args(argv)
    if a.static:
        return shoot_static(os.path.abspath(a.static))
    os.environ[OUT_ENV] = os.path.abspath(a.out)
    os.chdir(ROOT)
    return pytest.main([os.path.abspath(__file__), "-p", "tests.conftest", "-p", "no:randomly",
                        "-p", "no:cacheprovider", "-q", "-s", "-o", "python_files=*.py"])


def shoot_static(top: str) -> int:
    """Every ``.html`` under *top* (a proposal's static mockups), shot at each of `SIZES`, the
    viewport and the whole page, beside it in ``shots/<size>/``. Folders named ``shots`` or
    starting with ``_`` are left out. No app is served: each file opens as ``file://``."""
    import base64

    sys.path.insert(0, ROOT)
    from tests.browser import Browser

    files = sorted(os.path.join(d, f) for d, subs, fs in os.walk(top)
                   for f in fs if f.endswith(".html")
                   and not any(p == "shots" or p.startswith("_")
                               for p in os.path.relpath(d, top).split(os.sep)))
    with Browser() as b:
        for path in files:
            for w, h in SIZES:
                folder = os.path.join(os.path.dirname(path), "shots", f"{w}x{h}")
                os.makedirs(folder, exist_ok=True)
                b.go("about:blank")
                b._call("POST", f"/session/{b.session}/window/rect", {"width": w, "height": h})
                iw, ih = b.js("return [window.innerWidth, window.innerHeight]")
                b._call("POST", f"/session/{b.session}/window/rect",
                        {"width": w + (w - iw), "height": h + (h - ih)})
                b.go("file://" + path)
                time.sleep(0.3)
                name = os.path.splitext(os.path.basename(path))[0]
                b.screenshot(os.path.join(folder, f"{name}.png"))
                png = b._call("GET", f"/session/{b.session}/moz/screenshot/full")
                with open(os.path.join(folder, f"{name}.full.png"), "wb") as fh:
                    fh.write(base64.b64decode(png))
    print(f"review shots: {len(files)} mockups at {len(SIZES)} sizes under {top}")
    return 0


# --------------------------------------------------------------------------- under pytest

if os.environ.get(OUT_ENV):
    import pytest

    from tests.test_v2_layout_in_a_browser import lab, served  # noqa: F401 (the fixtures)

    def _slug(path: str) -> str:
        s = re.sub(r"[^A-Za-z0-9]+", "-", path.strip("/")).strip("-")
        return s or "v2"

    def _pages(app) -> tuple:
        """``(paths, skipped)``: every GET rule under /v2 filled from `FILL`, and each rule
        needing an argument the fixture cannot fill, with the argument."""
        paths, skipped = [], []
        for rule in sorted(app.url_map.iter_rules(), key=lambda r: r.rule):
            if "GET" not in (rule.methods or ()) or not rule.rule.startswith("/v2"):
                continue
            args = set(rule.arguments)
            if args - set(FILL):
                skipped.append((rule.rule, ", ".join(sorted(args - set(FILL)))))
                continue
            try:
                paths.append(rule.build({k: FILL[k] for k in args}, append_unknown=False)[1])
            except Exception as exc:                  # noqa: BLE001 (said in the index)
                skipped.append((rule.rule, f"not built: {exc}"))
        from tests.signed_off_screens import SIGNED_OFF
        tabs = sorted(k.split(":", 1)[1] for k in SIGNED_OFF if k.startswith("tab:"))
        paths += [f"/v2/device/{DEVICE}?tab={t}" for t in tabs]
        return list(dict.fromkeys(paths)), skipped

    def _viewport(b, width, height):
        """The window sized so the page's viewport is *width* x *height*."""
        b._call("POST", f"/session/{b.session}/window/rect", {"width": width, "height": height})
        iw, ih = b.js("return [window.innerWidth, window.innerHeight]")
        b._call("POST", f"/session/{b.session}/window/rect",
                {"width": width + (width - iw), "height": height + (height - ih)})

    def test_shoot_every_page(served):  # noqa: F811
        import base64

        import app as A

        srv, b = served
        out = os.environ[OUT_ENV]
        paths, skipped = _pages(A.app)
        lines = ["# Review shots", "",
                 f"Shot {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())} from the suite's "
                 "fixture world (tools/review_screenshots.py).", "",
                 "| Page | " + " | ".join(f"{w}x{h}" for w, h in SIZES) + " |",
                 "|---|" + "---|" * len(SIZES)]
        not_pages = []
        for path in paths:
            cells = []
            for w, h in SIZES:
                folder = os.path.join(out, f"{w}x{h}")
                os.makedirs(folder, exist_ok=True)
                b.go("about:blank")
                _viewport(b, w, h)
                b.go(srv.url(path))
                try:
                    b.wait_for("return document.readyState === 'complete'", 15)
                except Exception:                     # noqa: BLE001 (said in the index)
                    pass
                is_page = b.js("return !!(document.body && document.body.classList.contains('v2'))")
                if not is_page:
                    not_pages.append(path)
                    cells = None
                    break
                time.sleep(0.6)                       # htmx's on-load fetches draw
                name = _slug(path)
                b.screenshot(os.path.join(folder, f"{name}.png"))
                png = b._call("GET", f"/session/{b.session}/moz/screenshot/full")
                with open(os.path.join(folder, f"{name}.full.png"), "wb") as fh:
                    fh.write(base64.b64decode(png))
                cells.append(f"[{name}.png]({w}x{h}/{name}.png)")
            if cells:
                lines.append(f"| `{path}` | " + " | ".join(cells) + " |")
        lines += ["", f"## Not a v2 page ({len(not_pages)}: a fragment, a redirect or a file)",
                  ""] + [f"- `{p}`" for p in not_pages]
        lines += ["", f"## Skipped ({len(skipped)}: an argument the fixture cannot fill)", ""] + [
            f"- `{r}`: {why}" for r, why in skipped]
        with open(os.path.join(out, "index.md"), "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        print(f"review shots: {len(paths) - len(not_pages)} pages at {len(SIZES)} sizes in {out}")


if __name__ == "__main__":
    sys.exit(main())
