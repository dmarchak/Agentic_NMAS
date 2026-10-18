"""Nothing outside templates/v2 (P7-27, 2026-10-17: the last of today's interface removed; before
it, "no new capability on a v1 page", the operator, 2026-10-03: "nothing new on the v1 export;
once the v2 card exists, every link opens it and the v1 export joins CUTOVER's remove list").

Today's interface was every template outside `templates/v2` and every script no v2 page loads.
It only shrank, its counts held by ceilings measured 2026-10-03 (43 controls, 31 handlers, 333
functions, 20 fields before 7.8's removals), and P7-27 took the last of it: today's index, its
base, its six partials, its nine scripts and the vendored Bootstrap. What is held now:

- **no template outside `templates/v2`**, and the counts a v1 template or script would add
  (controls, handlers, functions, fields) at 0, so a new one fails the day it exists;
- **no script outside v2's**: every project script under `static/js` (the vendored libraries
  aside) is one a v2 template loads;
- **no route outside the redesign but the declared non-GUI ones** (`NON_GUI`, each with its
  caller): `/v2/...` and `/update/...` are the interface; anything else is an endpoint a
  host, a browser or a v2 page's own request calls, never a page of its own;
- **`/` answers 302 into v2**, keeping the address's network.

The population is defined by where a thing is drawn, loaded or routed, never by a list of files:
a new template or script outside v2 is counted the moment it exists, and a planted one is found.
"""

import os
import re

from tests import manual_actions as M
from tests.source_index import track_all, tracked

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES = os.path.join(ROOT, "templates")
JS = os.path.join(ROOT, "static", "js")

#: 0 since 2026-10-17 (7.8, P7-27): today's index, base and last partials left. Before: 6
#: (P7-25), 12 (P7-23), 19 (P7-26), 23 (P7-21), 25 (P7-22), 36 (P7-20), 43 measured 2026-10-03.
CONTROLS_CEILING = 0
#: 0 since 2026-10-17 (P7-27). Before: 3 (P7-25), 8, 13, 16, 18, 26, 31 measured 2026-10-03.
HANDLERS_CEILING = 0
#: 0 since 2026-10-17 (P7-27): today's last nine scripts left (nmas_attention, nmas_breakglass,
#: nmas_capture, nmas_in_flight, nmas_preview_confirm, nmas_profile and the three under
#: js/gen). Before: 195 (P7-24 and P7-25), 259, 281, 312, 314, 333 measured 2026-10-03.
FUNCTIONS_CEILING = 0
#: Fields a person could fill on today's pages: form elements in its templates, and the settings
#: fields its scripts drew from a spec (`{key: '<setting>', ...}`), less the recorded exceptions
#: below. 0 since 2026-10-17 (P7-27: the device list's search box left with today's index).
#: Before: 1 (P7-25), 12, 15, 17, 19, 20 measured 2026-10-03 (261 elements and 68 spec fields).
FIELDS_CEILING = 0

#: RECORDED EXCEPTIONS to the rule, each a v1 settings field by its key, with its reason and
#: where it goes at cutover. A field is excepted only by the operator's decision.
#: Empty since 2026-10-15: the two (grafana_token_expires and proxmox_token_expires, the
#: operator's of 2026-10-03) moved at cutover as decided, leaving with today's Settings modal at
#: 7.8; they are fields of Settings › Default's Grafana card and Installation's Proxmox card.
EXCEPTIONS = {}

#: Every route outside the redesign (`/v2/...`, `/update/...`), by its rule, with who calls it.
#: None draws a page of its own; each is CUTOVER's STAYS or BUILT row of the same path.
NON_GUI = {
    "/": "today's old address: 302 to Needs attention on v2, keeping ?list= (P7-27)",
    "/attention/acknowledge": "Needs attention's Acknowledge (templates/v2/_attention.html)",
    "/breakglass/export": "Credentials › The break-glass record's export",
    "/favicon.ico": "browsers ask for the icon",
    "/health": "the Update page and the root updater",
    "/health/operations": "scripts/nmas-deploy",
    "/identity/status": "the identity diagnostic, read with curl",
    "/jobs/finished": "nmas-job-finished@, from each job's systemd unit",
    "/operations/in_flight": "every v2 page's In progress chip (templates/v2/base.html)",
    "/remote/push": "History's header, Push now",
    "/remote/verify": "History's header, Verify the remote",
    "/restarts/planned": "scripts/nmas-planned-restart and the Reload's own window",
    "/settings/integrations/status": "docs/DEPLOY_LINUX.md's Verify, read with curl",
    "/static/<path:filename>": "the static files every v2 page loads",
}
REDESIGN = ("/v2/", "/update/")

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
    """Every project script under static/js no v2 template loads (the vendored libraries under
    static/js/vendor are MANIFEST.json's, held by tests/test_csp.py: each loaded by a page)."""
    v2 = v2_scripts()
    out = []
    for path in tracked(JS, root=ROOT):
        rel = os.path.relpath(path, JS)
        if not rel.endswith(".js") or rel.split(os.sep)[0] == "vendor":
            continue
        if os.sep in rel or rel not in v2:
            out.append(path)
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


def outside_the_redesign(rules) -> list:
    """The rules no `/v2/` or `/update/` prefix covers, each once."""
    return sorted({r for r in rules if not r.startswith(REDESIGN) and r != "/v2"})


class TestTodaysInterfaceOnlyShrinks:
    """Today's interface shrank to nothing at P7-27 (2026-10-17), and stays there."""

    def test_the_populations_are_found(self):
        """The scans see v2's own: every template under templates/v2 and the scripts they load
        (a scan that found nothing anywhere would pass the tests below by finding nothing)."""
        assert len(tracked(os.path.join(TEMPLATES, "v2"), suffix=".html",
                           root=os.path.dirname(TEMPLATES))) >= 100
        assert {"nmas_v2.js", "nmas_update.js"} <= v2_scripts()

    def test_no_template_or_script_outside_v2(self):
        rel = [os.path.relpath(p, ROOT) for p in v1_templates() + v1_scripts()]
        assert rel == [], (f"outside v2: {rel}. Today's interface left at 7.8 (P7-27): a page, "
                           "partial or script is built on v2 (templates/v2, a script a v2 "
                           "template loads)")

    def test_no_new_control_handler_or_function(self):
        c = counts()
        assert c["controls"] <= CONTROLS_CEILING, (
            f"{c['controls']} controls outside v2, the ceiling {CONTROLS_CEILING}: build "
            "the capability on v2")
        assert c["handlers"] <= HANDLERS_CEILING, (c["handlers"], HANDLERS_CEILING)
        assert c["functions"] <= FUNCTIONS_CEILING, (c["functions"], FUNCTIONS_CEILING)
        assert c["fields"] <= FIELDS_CEILING, (
            f"{c['fields']} fields outside v2, the ceiling {FIELDS_CEILING}: a new field "
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

    def test_no_route_outside_the_redesign_but_the_declared_endpoints(self):
        import app as A

        rules = [r.rule for r in A.app.url_map.iter_rules()]
        assert len(rules) >= 260, len(rules)          # the floor: 290 measured 2026-10-17
        outside = outside_the_redesign(rules)
        assert outside == sorted(NON_GUI), (
            f"undeclared: {sorted(set(outside) - set(NON_GUI))}; declared and gone: "
            f"{sorted(set(NON_GUI) - set(outside))}. A route outside /v2/ is an endpoint "
            "something other than a person's page calls, named here with its caller")
        assert all(why.strip() for why in NON_GUI.values())

    def test_the_old_address_lands_on_v2_keeping_its_network(self):
        import app as A

        client = A.app.test_client()
        r = client.get("/", headers={"Accept": "text/html"})
        assert r.status_code == 302 and r.headers["Location"].endswith("/v2/"), (
            r.status_code, r.headers.get("Location"))
        from modules.nsot import listref

        name = listref.active().name
        r = client.get(f"/?list={name}", headers={"Accept": "text/html"})
        assert r.status_code == 302 and r.headers["Location"].endswith(f"/v2/?list={name}"), (
            r.headers.get("Location"))
        r = client.get(f"/?open=breakglass_export&list={name}")
        assert r.status_code == 302
        assert r.headers["Location"].endswith(f"/v2/credentials?open=export&list={name}"), (
            r.headers.get("Location"))
        r = client.get(f"/?open=profile_propose&list={name}")
        assert r.headers["Location"].endswith(f"/v2/monitoring/profile?list={name}")
        # An opener today's index no longer had (the intent editor, revert, retry, the deploy
        # plan) lands on Needs attention for the same network, never a dead page.
        r = client.get(f"/?open=intent_editor&device=r1&list={name}")
        assert r.headers["Location"].endswith(f"/v2/?list={name}")

    def test_a_planted_control_is_found(self, tmp_path, monkeypatch):
        planted = tmp_path / "templates"
        (planted / "v2").mkdir(parents=True)
        (planted / "page.html").write_text('<button class="btn">Do a new thing…</button>')
        track_all(tmp_path)
        monkeypatch.setattr(__import__(__name__), "TEMPLATES", str(planted))
        assert len(v1_templates()) == 1
        assert sum(len(M.controls(_read(p))) for p in v1_templates()) == 1

    def test_a_planted_script_is_found(self, tmp_path, monkeypatch):
        """A script no v2 template loads, and one in a folder of its own (as js/gen was), are
        each found; a v2 template's script and a vendored library are not."""
        root = tmp_path
        (root / "templates" / "v2").mkdir(parents=True)
        (root / "templates" / "v2" / "page.html").write_text(
            '<script src="/static/js/nmas_mine.js"></script>')
        (root / "static" / "js" / "gen").mkdir(parents=True)
        (root / "static" / "js" / "vendor" / "lib").mkdir(parents=True)
        for rel in ("nmas_mine.js", "nmas_old.js", "gen/index.1.js", "vendor/lib/lib.js"):
            (root / "static" / "js" / rel).write_text("function f() {}\n")
        track_all(root)
        mod = __import__(__name__)
        monkeypatch.setattr(mod, "ROOT", str(root))
        monkeypatch.setattr(mod, "TEMPLATES", str(root / "templates"))
        monkeypatch.setattr(mod, "JS", str(root / "static" / "js"))
        assert [os.path.relpath(p, root / "static" / "js") for p in v1_scripts()] == [
            os.path.join("gen", "index.1.js"), "nmas_old.js"]
        assert counts()["functions"] == 2

    def test_a_planted_route_outside_the_redesign_is_found(self):
        rules = list(NON_GUI) + ["/v2/", "/v2/devices", "/update/apply", "/attention"]
        assert outside_the_redesign(rules) == sorted(list(NON_GUI) + ["/attention"])
