"""Every pure render helper is called by something.

**Five times in one session** a renderer was written, tested directly, and
wired to nothing:

1. `loadOnboardPending` — its only callers were the buttons inside the
   banner it draws, so the banner could appear only after using a control
   that exists once it has appeared;
2. the pending banner's Verify and Abandon buttons read `#obList`, the
   wizard's select, empty unless the wizard had been opened;
3. `nbCascadeHtml` — a control that deleted its call site left every
   renderer test green;
4. `_gBaselineCoverage` — computed by the route, carried to the browser,
   drawn nowhere, **in the commit that was fixing (3)**;
5. and the same shape in `scripts/`, where `_remove_excluded` sat below the
   `__main__` guard.

The lesson has been learned individually five times, which means it has not
been learned. **A renderer executed directly in a test proves the render
and says nothing about the wiring** — so this sweeps for the property
instead of remembering to check it, the way
`test_script_entry_points.py` does for scripts and `nmas-verify-runbook`
does for routes.

**Scope, deliberately narrow.** Only *helper* functions — the ones whose
whole job is to return markup for something else to place. An event handler,
an entry point called from `onclick=`, or a function called only from
another template are all legitimately "uncalled" within one file, so the
scan looks across every template and counts `onclick`/`addEventListener`
references too.
"""

import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES = os.path.join(ROOT, "templates")

#: A helper is a function whose name says it returns markup or state for a
#: caller to use. Matching on the NAME rather than the body, because a
#: body-based rule ("returns a template literal") would also catch every
#: loader that builds its own innerHTML and is called from a tab click.
_HELPER = re.compile(
    r"^(?:_?[a-z][A-Za-z0-9]*)?(?:Html|Coverage|Banner|Badge|Warning|"
    r"State|Text|Label|Row|Cell|Summary)$")

#: Declared and used only via `window.x = ...` assignment, or called from a
#: sibling template. Each entry needs a reason.
_ALLOWED = {
    # (name, why)
}


def _template_files() -> list:
    out = []
    for base, _dirs, names in os.walk(TEMPLATES):
        for n in sorted(names):
            if n.endswith(".html"):
                out.append(os.path.join(base, n))
    return sorted(out)


def _all_text() -> str:
    return "\n".join(open(p, encoding="utf-8").read() for p in _template_files())


def declared_helpers() -> dict:
    """``{name: path}`` for every function whose name marks it a helper."""
    found = {}
    for path in _template_files():
        text = open(path, encoding="utf-8").read()
        for m in re.finditer(r"\bfunction\s+([A-Za-z_$][\w$]*)\s*\(", text):
            name = m.group(1)
            if _HELPER.match(name):
                found[name] = path
    return found


def uncalled(helpers: dict, corpus: str) -> list:
    """Helpers referenced nowhere but their own definition."""
    out = []
    for name, path in sorted(helpers.items()):
        refs = len(re.findall(rf"\b{re.escape(name)}\b", corpus))
        defs = len(re.findall(rf"\bfunction\s+{re.escape(name)}\s*\(", corpus))
        if refs - defs < 1 and name not in {n for n, _ in _ALLOWED}:
            out.append(f"{name} ({os.path.relpath(path, ROOT)})")
    return out


class TestEveryRenderHelperIsCalled:
    def test_the_scan_finds_something(self):
        """**The floor.** "No offenders" is also what a scan that matched
        nothing produces, and this one matches on a name pattern — the
        easiest kind to get silently wrong."""
        files = _template_files()
        assert len(files) >= 10, f"only {len(files)} templates found"
        helpers = declared_helpers()
        assert len(helpers) >= 8, \
            f"the helper pattern matched only {sorted(helpers)}"
        # The five that motivated this sweep must be among them, or the
        # pattern has drifted away from the thing it was built for.
        for known in ("nbCascadeHtml", "_gBaselineCoverage",
                      "pendingBannerHtml", "agentHealthBanner"):
            assert known in helpers, f"{known} is no longer recognised"

    def test_none_is_defined_and_never_used(self):
        helpers = declared_helpers()
        offenders = uncalled(helpers, _all_text())
        assert not offenders, (
            "these return markup and nothing calls them — computed, carried "
            "to the browser, drawn nowhere: " + "; ".join(offenders))

    def test_the_check_can_say_no(self):
        """Driven against a corpus built to fail, so a green sweep is a
        result rather than a silence."""
        corpus = ("function somethingHtml(x) { return `<b>${x}</b>`; }\n"
                  "function otherHtml(y) { return y; }\n"
                  "el.innerHTML = otherHtml(1);\n")
        helpers = {"somethingHtml": "x.html", "otherHtml": "x.html"}

        out = uncalled(helpers, corpus)
        assert out == ["somethingHtml (x.html)"], out

    def test_a_helper_called_from_ANOTHER_template_is_not_an_offender(self):
        """The scan is corpus-wide for exactly this reason: partials call
        into each other, and a per-file check would report every one."""
        corpus = ("function sharedHtml(x) { return x; }\n"
                  "const s = sharedHtml(2);\n")
        assert uncalled({"sharedHtml": "a.html"}, corpus) == []


class TestTheOneThatMotivatedIt:
    """`_gBaselineCoverage`, pinned by name as well as by the sweep.

    The sweep is the general answer; this is the specific one, because a
    pattern-based scan can stop matching a name without anybody noticing and
    the general test would then pass by finding nothing.
    """

    def test_it_is_called_from_the_baseline_row(self):
        page = open(os.path.join(TEMPLATES, "partials", "golden_repo.html"),
                    encoding="utf-8").read()
        assert "${_gBaselineCoverage(b)}" in page

    def test_and_the_bare_count_is_gone_from_that_row(self):
        """The row rendered `${b.device_count} device(s)` directly. If that
        string returns to the baselines table, the call site was replaced
        rather than added to."""
        page = open(os.path.join(TEMPLATES, "partials", "golden_repo.html"),
                    encoding="utf-8").read()
        block = page[page.index("baselines.map"):]
        block = block[:block.index("</table>")]
        assert "device_count" not in block, \
            "the baseline row renders the count directly again"
