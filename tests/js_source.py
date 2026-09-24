"""The shipped JavaScript for a template — inline AND extracted.

**Not a test module.** Stage 7 §0b moved 275 KB of pure inline script out of
the templates into `static/js/gen/`, so that the HTML can be declared
uncacheable (§6c) without re-sending the script on every navigation. The
two policies are opposites and cannot both apply while the script lives
inside the page.

Every renderer test in this suite reads *the source the browser executes*,
which was the template file and is now the template file **plus** the files
it references. Reading only the template would make those tests pass by
finding nothing — the exact failure the extraction would otherwise have
introduced into a suite built to catch it.

Use `shipped_js(...)` anywhere a test previously did
`open(<template>).read()` to find a function.
"""

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES = os.path.join(ROOT, "templates")
GEN = os.path.join(ROOT, "static", "js", "gen")

_SRC = re.compile(r"js/gen/([\w.]+\.js)")


def shipped_js(*parts) -> str:
    """Template text, with each referenced `js/gen` file appended.

    ``shipped_js("partials", "golden_repo.html")`` or
    ``shipped_js("index.html")``.
    """
    path = os.path.join(TEMPLATES, *parts)
    text = open(path, encoding="utf-8").read()
    extracted = []
    for name in _SRC.findall(text):
        full = os.path.join(GEN, name)
        if os.path.exists(full):
            extracted.append(open(full, encoding="utf-8").read())
    return text + "\n" + "\n".join(
        f"<script>\n{e}\n</script>" for e in extracted) + "\n"


def gen_files_for(*parts) -> list:
    """The `js/gen` files a template references, by absolute path."""
    text = open(os.path.join(TEMPLATES, *parts), encoding="utf-8").read()
    return [os.path.join(GEN, n) for n in _SRC.findall(text)
            if os.path.exists(os.path.join(GEN, n))]


def read_shipped(path: str) -> str:
    """Drop-in for ``open(path).read()`` that follows an extraction.

    A template's script now lives partly in `static/js/gen/`, so a test that
    reads the template alone reads less than the browser executes. For a
    path outside `templates/` this is an ordinary read, so the swap is safe
    everywhere and there is one rule rather than a judgement per call site.
    """
    text = open(path, encoding="utf-8").read()
    if os.path.abspath(path).startswith(TEMPLATES + os.sep):
        extra = []
        for name in _SRC.findall(text):
            full = os.path.join(GEN, name)
            if os.path.exists(full):
                extra.append(open(full, encoding="utf-8").read())
        if extra:
            # Wrapped in a <script> element, because a test that slices the
            # page into script blocks must find the extracted code as one.
            # Appending it bare made `_scripts()` return nothing and the
            # assertions then read "no block defines X" -- a scan finding
            # nothing, wearing the words of a real defect.
            # ONE <script> PER FILE, not one for all of them: each
            # `<script src>` is its own block in the browser, and a test
            # that slices a block and indexes into it would otherwise find
            # a construct belonging to a different extracted file.
            return text + "\n" + "\n".join(
                f"<script>\n{e}\n</script>" for e in extra) + "\n"
    return text


def with_loaded_scripts(html: str) -> str:
    """Rendered HTML **plus** the `js/gen` files its script tags load.

    The tests that read `app.test_client().get("/")` were already using the
    best available source — the page the browser receives. After §0b that
    page *references* its script instead of containing it, so this appends
    what the browser would fetch and execute.

    Strictly more faithful than before: it models the assembled program
    rather than one file that happened to hold all of it.
    """
    extra = []
    for name in sorted(set(_SRC.findall(html))):
        full = os.path.join(GEN, name)
        if os.path.exists(full):
            extra.append(open(full, encoding="utf-8").read())
    return html + "\n" + "\n".join(
        f"<script>\n{e}\n</script>" for e in extra) + "\n"
