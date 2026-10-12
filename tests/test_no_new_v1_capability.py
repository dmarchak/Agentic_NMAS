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
from tests.source_index import track_all, tracked

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES = os.path.join(ROOT, "templates")
JS = os.path.join(ROOT, "static", "js")

#: Measured 2026-10-03.
CONTROLS_CEILING = 91    # 2026-10-12: today's Topology tab left (7.8). Before: the topology service panel left (7.8). Before: the Monitoring tab left with the legacy collectors (7.8). Before: the Configure tab left (7.8). Before: the stack panel's Refresh left (7.8). Before: Reload Devices left with /bulk_reload (7.8). Before: Refresh Hostnames left (7.8). Before: today's History tab left with /list/change_log (7.8). Before: 2026-10-08: the freshness panel left (Phase 3). Before: 2026-10-04: the 81 CCIE-KB config types left with ccie_kb/ (NSOT_PLAN 8.12)
HANDLERS_CEILING = 69    # 2026-10-12: today's Topology tab left (7.8). Before: the topology service panel left (7.8). Before: the Monitoring tab left with the legacy collectors (7.8). Before: the Configure tab left (7.8). Before: the stack panel's Refresh left (7.8). Before: Reload Devices left with /bulk_reload (7.8). Before: Refresh Hostnames left (7.8). Before: today's History tab left (7.8). Before: 2026-10-08: the freshness panel left (Phase 3)
FUNCTIONS_CEILING = 386   # 2026-10-12: the status polling (deviceIps, updateStatus) left with /status (7.8). Before: today's Topology tab (index.3.js) left (7.8). Before: the topology service panel's left (7.8). Before: the Monitoring tab's twelve left with the legacy collectors (7.8). Before: the stack panel's four functions left (7.8). Before: saveInventoryOrder left with /inventory/order (7.8). Before: the break-glass modal's eight functions left with /breakglass/preview (7.8). Before: the legacy store's card, the migration's card and its apply left (7.8). Before: Sync device names left with the renames routes (7.8). Before: today's History tab left (7.8). Before: 2026-10-08: the freshness panel left (Phase 3)
#: Fields a person can fill on today's pages: form elements in its templates, and the
#: settings fields its scripts draw from a spec (`{key: '<setting>', ...}`), less the
#: recorded exceptions below. Measured 2026-10-03 (261 elements and 68 spec fields).
FIELDS_CEILING = 142   # 2026-10-12: today's Topology tab left (7.8). Before: the topology service panel's interval left (7.8). Before: the Monitoring tab's forms left (7.8). Before: the Configure tab's forms left (7.8). Before: 2026-10-08: the Oxidized settings card left (Phase 3). Before: 2026-10-04: the KB's dynamic form left with it

#: RECORDED EXCEPTIONS to the rule, each a v1 settings field by its key, with its reason and
#: where it goes at cutover. A field is excepted only by the operator's decision.
EXCEPTIONS = {
    "grafana_token_expires": (
        "the operator, 2026-10-03: the Grafana token's declared expiry (P.21), which a Viewer "
        "token cannot read; a v2 Settings page waits on P.8. Moves at cutover"),
    "proxmox_token_expires": (
        "the operator, 2026-10-03: the Proxmox token's declared expiry (C380), which a "
        "PVEAuditor token cannot read and is not widened to; a v2 Settings page waits on P.8. "
        "Moves at cutover"),
}
_SPEC_FIELD = re.compile(r"\{\s*key:\s*'([a-z0-9_]+)'")
_FORM_FIELD = re.compile(r"<(?:input|select|textarea)\b")

_FN = re.compile(r"^\s*(?:async\s+)?function\s+[A-Za-z_$][\w$]*\s*\(|^\s*root\.\w+\s*=\s*function",
                 re.M)


def v1_templates() -> list:
    return [p for p in tracked(TEMPLATES, suffix=".html", root=os.path.dirname(TEMPLATES))
            if os.path.relpath(p, TEMPLATES).split(os.sep)[0] != "v2"]


def v2_scripts() -> set:
    """Every script a v2 template loads: v2's own, free to grow."""
    found = set()
    for path in tracked(os.path.join(TEMPLATES, "v2"), root=os.path.dirname(TEMPLATES)):
        text = open(path, encoding="utf-8").read()
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


def spec_fields() -> list:
    """Every settings field a v1 script draws from a spec, by its key."""
    return [k for p in v1_scripts() for k in _SPEC_FIELD.findall(_read(p))]


def counts() -> dict:
    texts = [_read(p) for p in v1_templates()]
    return {"fields": (sum(len(_FORM_FIELD.findall(t)) for t in texts)
                       + len([k for k in spec_fields() if k not in EXCEPTIONS])),
            "controls": sum(len(M.controls(t)) for t in texts),
            "handlers": sum(len(re.findall(r"\bon(click|change|submit|input)=", t))
                            for t in texts),
            "functions": sum(len(_FN.findall(_read(p))) for p in v1_scripts())}


class TestTodaysInterfaceOnlyShrinks:
    def test_the_populations_are_found(self):
        # v1 templates 19 and scripts 37 since 2026-10-12: the stack and topology service panels and
        # today's Topology tab's script left (7.8).
        assert len(v1_templates()) >= 19 and len(v1_scripts()) >= 37
        assert {"nmas_v2.js", "nmas_update.js"} <= v2_scripts()

    def test_no_new_control_handler_or_function(self):
        c = counts()
        assert c["controls"] <= CONTROLS_CEILING, (
            f"{c['controls']} controls on today's pages, the ceiling {CONTROLS_CEILING}: build "
            "the new capability on v2 (a v1 page gains nothing new)")
        assert c["handlers"] <= HANDLERS_CEILING, (c["handlers"], HANDLERS_CEILING)
        assert c["functions"] <= FUNCTIONS_CEILING, (c["functions"], FUNCTIONS_CEILING)
        assert c["fields"] <= FIELDS_CEILING, (
            f"{c['fields']} fields on today's pages, the ceiling {FIELDS_CEILING}: a new field "
            "goes on v2, or is a recorded exception the operator decided (EXCEPTIONS)")

    def test_each_exception_is_there_with_its_reason_and_where_it_goes(self):
        """An exception names a field that exists (a stale one would excuse the next field
        under its key), the operator's decision, and that it moves at cutover."""
        present = set(spec_fields())
        for key, why in EXCEPTIONS.items():
            assert key in present, f"{key}: excepted and not on today's pages: remove it"
            assert "the operator" in why and why.endswith("Moves at cutover"), key

    def test_a_ceiling_never_sits_above_what_is_there(self):
        """A ceiling left high after a removal would let the next addition through."""
        c = counts()
        assert (c["controls"], c["handlers"], c["functions"], c["fields"]) == (
            CONTROLS_CEILING, HANDLERS_CEILING, FUNCTIONS_CEILING, FIELDS_CEILING), (
            f"lower the ceilings to what is there now: {c}")

    def test_a_planted_control_is_found(self, tmp_path, monkeypatch):
        planted = tmp_path / "templates"
        (planted / "v2").mkdir(parents=True)
        (planted / "page.html").write_text('<button class="btn">Do a new thing…</button>')
        track_all(tmp_path)
        monkeypatch.setattr(__import__(__name__), "TEMPLATES", str(planted))
        assert len(v1_templates()) == 1
        assert sum(len(M.controls(_read(p))) for p in v1_templates()) == 1
