"""No new capability on a v1 page (the operator, 2026-10-03: "nothing new on the v1 export;
once the v2 card exists, every link opens it and the v1 export joins CUTOVER's remove list").

Today's interface (every template outside `templates/v2`, and every script no v2 page loads)
is frozen: what a person can press there, and what its scripts define, may only shrink. A
fix to today's pages keeps its counts; a new control or function there fails here, and the
capability is built on v2 instead. The ceilings were measured 2026-10-03 and only fall:
lower one when a cutover removes what it counted.

The population is defined by where a thing is drawn or loaded, never by a list of files:
a new v1 template or script is counted the moment it exists.
"""

import os
import re

from tests import manual_actions as M

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES = os.path.join(ROOT, "templates")
JS = os.path.join(ROOT, "static", "js")

#: Measured 2026-10-03.
CONTROLS_CEILING = 284
HANDLERS_CEILING = 275
FUNCTIONS_CEILING = 451

_FN = re.compile(r"^\s*(?:async\s+)?function\s+[A-Za-z_$][\w$]*\s*\(|^\s*root\.\w+\s*=\s*function",
                 re.M)


def v1_templates() -> list:
    out = []
    for dirpath, _dirs, files in os.walk(TEMPLATES):
        if os.path.relpath(dirpath, TEMPLATES).split(os.sep)[0] == "v2":
            continue
        out += [os.path.join(dirpath, f) for f in files if f.endswith(".html")]
    return sorted(out)


def v2_scripts() -> set:
    """Every script a v2 template loads: v2's own, free to grow."""
    found = set()
    for dirpath, _dirs, files in os.walk(os.path.join(TEMPLATES, "v2")):
        for f in files:
            text = open(os.path.join(dirpath, f), encoding="utf-8").read()
            found |= set(re.findall(r"js/(nmas_\w+\.js)", text))
    return found


def v1_scripts() -> list:
    v2 = v2_scripts()
    out = [os.path.join(JS, f) for f in os.listdir(JS) if f.endswith(".js") and f not in v2]
    gen = os.path.join(JS, "gen")
    out += [os.path.join(gen, f) for f in os.listdir(gen) if f.endswith(".js")]
    return sorted(out)


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def counts() -> dict:
    texts = [_read(p) for p in v1_templates()]
    return {"controls": sum(len(M.controls(t)) for t in texts),
            "handlers": sum(len(re.findall(r"\bon(click|change|submit|input)=", t))
                            for t in texts),
            "functions": sum(len(_FN.findall(_read(p))) for p in v1_scripts())}


class TestTodaysInterfaceOnlyShrinks:
    def test_the_populations_are_found(self):
        assert len(v1_templates()) >= 20 and len(v1_scripts()) >= 40
        assert {"nmas_v2.js", "nmas_update.js"} <= v2_scripts()

    def test_no_new_control_handler_or_function(self):
        c = counts()
        assert c["controls"] <= CONTROLS_CEILING, (
            f"{c['controls']} controls on today's pages, the ceiling {CONTROLS_CEILING}: build "
            "the new capability on v2 (a v1 page gains nothing new)")
        assert c["handlers"] <= HANDLERS_CEILING, (c["handlers"], HANDLERS_CEILING)
        assert c["functions"] <= FUNCTIONS_CEILING, (c["functions"], FUNCTIONS_CEILING)

    def test_a_ceiling_never_sits_above_what_is_there(self):
        """A ceiling left high after a removal would let the next addition through."""
        c = counts()
        assert (c["controls"], c["handlers"], c["functions"]) == (
            CONTROLS_CEILING, HANDLERS_CEILING, FUNCTIONS_CEILING), (
            f"lower the ceilings to what is there now: {c}")

    def test_a_planted_control_is_found(self, tmp_path, monkeypatch):
        planted = tmp_path / "templates"
        (planted / "v2").mkdir(parents=True)
        (planted / "page.html").write_text('<button class="btn">Do a new thing…</button>')
        monkeypatch.setattr(__import__(__name__), "TEMPLATES", str(planted))
        assert len(v1_templates()) == 1
        assert sum(len(M.controls(_read(p))) for p in v1_templates()) == 1
