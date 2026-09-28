"""P.3 step 3 (register D5): "Restore Golden Config" goes through the guarded
restore preview, and that preview draws the exact program.

Two buttons, the device page's and bulk ops', POSTed to a replay that pushed
the whole golden line by line: no plan, no confirm hash, no rollback. Both now
open `previewBaselineRestore('HEAD', ..., {devices})`, the path the approval
queue already hands off to, and the replay routes are gone.

Routing two more buttons into that preview exposed its own defect: its confirm
dialog showed counts and at most three replace and three residue lines, and
never the lines to be ADDED. `commands` was computed by the route, carried to
the browser, and drawn nowhere, while the confirm hash covered it.

Stage 7.1 moved the preview onto THE preview-then-confirm component: the
route builds the six parts (`modules/preview_confirm.restore_preview`) and
`previewConfirmHtml` draws them, executed here against the route's real
payload over REAL `RestoreTarget`s (a stub target could not exhibit the
restore's own gates, and C75 lived there).
"""

import html as _html
import json
import os
import re

import pytest

from tests.js_source import shipped_js
from tests.payload_render import render_preview

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLDEN_JS = os.path.join(ROOT, "static", "js", "gen", "partials__golden_repo.3.js")

# The device carries a line the ref does not mention INSIDE a section (the
# description under Gi3), so the residue part can show whether it names the
# section (C73's fix, in the restore path this time).
CAPTURED = """hostname r1
interface GigabitEthernet2
 description old text
 ip address 10.1.1.1 255.255.255.0
interface GigabitEthernet3
 description retired uplink
 shutdown
logging host 192.0.2.50
"""
TARGET = """hostname r1
interface GigabitEthernet2
 description restored text
 ip address 10.1.1.1 255.255.255.0
interface GigabitEthernet3
 shutdown
interface GigabitEthernet4
 shutdown
ip domain name example.invalid
snmp-server location lab
"""


def _target(device, target_config=TARGET, captured=CAPTURED):
    from modules.nsot.deploy import RestoreTarget

    return RestoreTarget(device=device, platform="cisco_iosxe",
                         target_config=target_config, captured=captured, ref="HEAD")


def _preview_for(monkeypatch, targets, skipped=(), body=None):
    """What POST /golden/restore/preview returns for *targets*, with the real
    merge_diff, merge_commands, prepare_restore and adapter."""
    import flask

    import routes.golden as golden

    monkeypatch.setattr(golden, "_active_list", lambda data=None: "Lab")
    # build_targets is stubbed with a made-up list, so coverage() is too: it
    # reads that list's inventory, and resolving a list that does not exist
    # creates it (get_list_data_dir). Coverage is tested on a real repo in
    # TestTheInventoryIsThePopulation.
    monkeypatch.setattr("modules.nsot.restore.coverage",
                        lambda ln, devices=None, skipped=None: {
                            "inventory_size": 0, "partial": False,
                            "denominator": 0, "scope_words": "in this list"})
    monkeypatch.setattr(golden, "_intent_preview", lambda ln, t: {"action": "none"})
    # Honours `authorise` as the real one does (C79): each target carries
    # the keys of its authorisations whose reason has the shape of one.
    import dataclasses

    from modules.nsot.authorisation import valid_keys

    def _built(*a, authorise=None, **k):
        return ([dataclasses.replace(t, authorised=tuple(valid_keys(
                    (authorise or {}).get(t.device) or []))) for t in targets],
                list(skipped))

    monkeypatch.setattr("modules.nsot.restore.build_targets", _built)
    app = flask.Flask(__name__)
    app.register_blueprint(golden.bp)
    out = app.test_client().post("/golden/restore/preview",
                                 json=body or {"ref": "HEAD"}).get_json()
    assert out["ok"], out
    return out


def _real_payload(monkeypatch):
    """Two real targets, one restorable and one with no stored config, and
    one skipped device."""
    return _preview_for(monkeypatch, [_target("r1"), _target("r2", target_config="")],
                        [{"hostname": "r9", "reason": "stale"}],
                        # r1's program shuts a new interface: a dangerous
                        # line, authorised, so the fixture reaches both lists.
                        {"ref": "HEAD", "devices": ["r1", "r2"],
                         "authorise": {"r1": [{"line": "shutdown",
                                               "reason": "new interface, left down for now"}]}})


def _lift(page: str, name: str) -> str:
    start = page.index(f"function {name}(")
    depth, i, seen = 0, page.index("{", start), False
    while i < len(page):
        if page[i] == "{":
            depth += 1
            seen = True
        elif page[i] == "}":
            depth -= 1
            if seen and depth == 0:
                break
        i += 1
    return page[start:i + 1]


def _html_of(payload) -> str:
    return _html.unescape(render_preview(payload["preview"]))


def _part(html: str, part: str, target: str = None) -> str:
    """One part's HTML: in *target*'s card when named."""
    if target:
        html = html[html.index(f'data-pc-target="{target}"'):]
    return re.search(rf'data-pc-part="{part}"(.*?)</section>', html, re.S).group(1)


def _gates(payload, name):
    t = next(t for t in payload["preview"]["targets"] if t["name"] == name)
    return {g["name"]: g for g in t["gates"]}


class TestThePreviewDrawsTheProgram:
    def test_every_line_that_will_be_sent_is_on_screen(self, monkeypatch):
        payload = _real_payload(monkeypatch)
        r1 = next(d for d in payload["devices"] if d["device"] == "r1")
        assert len(r1["commands"]) >= 3, r1["commands"]       # the fixture can fail
        program = _part(_html_of(payload), "program", "r1")
        for line in r1["commands"]:
            assert line in program, (line, program)
        assert f"Exactly these {len(r1['commands'])} line(s) will be sent" in program

    def test_what_it_replaces_is_drawn(self, monkeypatch):
        payload = _real_payload(monkeypatch)
        program = _part(_html_of(payload), "program", "r1")
        assert "What these lines replace on the device" in program
        assert "description old text  ->  description restored text" in program

    def test_residue_is_drawn_under_its_section(self, monkeypatch):
        """C73 in the restore path: the leftover line names its interface."""
        payload = _real_payload(monkeypatch)
        r1 = next(d for d in payload["devices"] if d["device"] == "r1")
        assert " description retired uplink" in r1["residue"], r1["residue"]
        part = _part(_html_of(payload), "what_not")
        assert "interface GigabitEthernet3\n description retired uplink" in part, part
        assert "logging host 192.0.2.50" in part
        assert 'data-concept="merge-only"' in part

    def test_a_blocked_device_says_nothing_is_sent_and_why(self, monkeypatch):
        payload = _real_payload(monkeypatch)
        html = _html_of(payload)
        assert "r2</strong>: Not sent: no golden config for this device at HEAD" in html
        assert "r9</strong>: Not touched: stale" in html
        assert "Nothing is sent to this device: it is blocked" in _part(html, "program", "r2")

    def test_the_scope_is_a_stated_non_action(self, monkeypatch):
        html = _html_of(_real_payload(monkeypatch))
        assert "Never templates, bindings or approvals" in _part(html, "what_not")


class TestTheRestoresOwnGates:
    """The gates are `RestoreTarget.checks`, the list its refusal is computed
    from, never the deploy's template gates (a restore has no template)."""

    def test_a_restorable_device(self, monkeypatch):
        gates = _gates(_real_payload(monkeypatch), "r1")
        assert {n: g["state"] for n, g in gates.items()} == {
            "golden config at this ref": "pass", "printable ASCII": "pass",
            "credential unchanged": "pass",
            "no secret re-added": "pass",                               # C79
            "this ref's intent usable today": "not_applicable",
            "lines needing an authorisation (dangerous, or a secret re-added)": "pass",
            "capture unchanged since this preview": "at_apply",
            "no other operation holds this device": "at_apply"}      # C99

    def test_a_device_with_no_stored_config_reached_nothing_else(self, monkeypatch):
        gates = _gates(_real_payload(monkeypatch), "r2")
        assert gates["golden config at this ref"]["state"] == "fail"
        assert gates["printable ASCII"]["state"] == "not_reached"
        assert gates["credential unchanged"]["state"] == "not_reached"
        assert gates["no secret re-added"]["state"] == "not_reached"

    def test_no_template_gate_is_drawn(self, monkeypatch):
        names = set(_gates(_real_payload(monkeypatch), "r1"))
        assert not names & {"template approved", "committed intent",
                            "template reproduces the device"}


class TestARestoreMayNotChangeACredential:
    """C75. A ref holding the pre-rotation secret: the restore's program was
    the old `username` line and the target was deployable. Measured
    2026-09-27 before the guard; the deploy's rule now applies here too."""

    OLD = "username admin privilege 15 secret 5 $1$oldsalt$oldoldoldoldold\n"
    NEW = "username admin privilege 15 secret 5 $1$newsalt$newnewnewnewnew\n"

    def test_the_device_is_blocked_by_the_credential_gate(self, monkeypatch):
        payload = _preview_for(monkeypatch, [
            _target("s4", target_config="hostname s4\n" + self.OLD,
                    captured="hostname s4\n" + self.NEW)])
        gate = _gates(payload, "s4")["credential unchanged"]
        assert gate["state"] == "fail"
        assert "re-apply HEAD to s4" in gate["detail"]
        assert "with a different value" in gate["detail"]
        target = payload["preview"]["what"]["targets"][0]
        assert target["state"] == "blocked" and target["selectable"] is False

    def test_the_refusal_never_prints_a_value(self, monkeypatch):
        payload = _preview_for(monkeypatch, [
            _target("s4", target_config="hostname s4\n" + self.OLD,
                    captured="hostname s4\n" + self.NEW)])
        text = json.dumps(payload["preview"])
        for value in ("oldoldoldoldold", "newnewnewnewnew"):
            assert value not in text

    def test_the_apply_path_refuses_it_too(self):
        from modules.nsot.deploy import DeployRefused, prepare_restore

        with pytest.raises(DeployRefused, match="credential"):
            prepare_restore(_target("s4", target_config="hostname s4\n" + self.OLD,
                                    captured="hostname s4\n" + self.NEW))

    def test_the_same_credential_passes(self, monkeypatch):
        """Control: an unchanged credential line is not a change."""
        payload = _preview_for(monkeypatch, [
            _target("s4", target_config="hostname s4\n" + self.NEW + "ip domain name x\n",
                    captured="hostname s4\n" + self.NEW)])
        assert _gates(payload, "s4")["credential unchanged"]["state"] == "pass"

    def test_an_account_the_device_lacks_is_added_not_refused(self, monkeypatch):
        """May ADD an account: the deploy rule's second half, unchanged."""
        payload = _preview_for(monkeypatch, [
            _target("s4", target_config="hostname s4\n" + self.NEW
                    + "username backup privilege 15 secret 5 $1$b$bbbbbbbbbbbbbbbb\n",
                    captured="hostname s4\n" + self.NEW)])
        assert _gates(payload, "s4")["credential unchanged"]["state"] == "pass"


class TestTheWiring:
    """The flow draws the component and confirms what it drew."""

    def test_the_restore_flow_confirms_on_the_drawn_preview(self):
        src = open(GOLDEN_JS, encoding="utf-8").read()
        flow = _lift(src, "previewBaselineRestore")
        assert "_confirmRestorePreview(`Re-apply ${tag}`, d, from)" in flow
        assert "_restoreSelected(d.preview)" in flow
        assert "x.deployable).forEach" not in flow, "confirms what the preview selects"
        # The only confirm() left is the un-onboard question, which has no program.
        assert flow.count("confirm(") == 1, flow.count("confirm(")

    def test_the_modal_draws_the_component(self):
        modal = _lift(open(GOLDEN_JS, encoding="utf-8").read(), "_confirmRestorePreview")
        assert "previewConfirmHtml(d.preview, {})" in modal
        assert "previewConfirmButton(d.preview" in modal

    def test_the_agents_diff_is_labelled_context_and_goes_in_as_text(self):
        modal = _lift(open(GOLDEN_JS, encoding="utf-8").read(), "_confirmRestorePreview")
        assert "NOT what will be sent" in modal
        assert "pre.textContent = from.advisoryDiff" in modal
        assert modal.index("data-advisory") < modal.index("data-restore-preview")

    def test_the_old_renderers_are_gone(self):
        src = open(GOLDEN_JS, encoding="utf-8").read()
        for gone in ("function restorePreviewText", "function _confirmProgram"):
            assert gone not in src, gone

    def test_what_is_confirmed_is_what_the_preview_selects(self, monkeypatch):
        """Executed against the real preview: r1 (restorable) and not r2
        (blocked), with the hashes the preview drew."""
        dukpy = pytest.importorskip("dukpy")
        payload = _real_payload(monkeypatch)
        src = _lift(open(GOLDEN_JS, encoding="utf-8").read(), "_restoreSelected")
        chosen = dukpy.evaljs(src + f"\n_restoreSelected({json.dumps(payload['preview'])})"
                                    ".map(function (t) { return [t.name, t.select_data]; })")
        r1 = next(d for d in payload["devices"] if d["device"] == "r1")
        assert chosen == [["r1", {"hash": r1["capture_hash"],
                                  "command-hash": r1["command_hash"]}]]

    def test_bulk_ops_opens_the_guarded_preview_at_head(self):
        src = open(os.path.join(ROOT, "static", "js", "gen", "index.1.js"),
                   encoding="utf-8").read()
        m = re.search(r"window\.bulkRestoreGoldenConfig = function\(\) \{(.*?)\n  \};", src, re.S)
        assert m
        assert "previewBaselineRestore('HEAD', null, {devices: hosts})" in m.group(1)
        assert "fetch(" not in m.group(1)

    def test_the_device_page_links_to_the_preview_at_head(self):
        import app as A
        with A.app.test_request_context("/"):
            from flask import url_for
            href = url_for("index", restore_head="r1")
        assert href == "/?restore_head=r1"
        page = open(os.path.join(ROOT, "templates", "device.html"), encoding="utf-8").read()
        assert "url_for('index', restore_head=device['hostname'])" in page

    def test_the_index_page_opens_it_from_the_url(self):
        index = open(os.path.join(ROOT, "templates", "index.html"), encoding="utf-8").read()
        assert "{% include 'partials/golden_repo.html' %}" in index
        page = shipped_js("partials", "golden_repo.html")
        assert "document.addEventListener('DOMContentLoaded', _restoreHeadFromUrl)" in page
        fn = _lift(page, "_restoreHeadFromUrl")
        assert "history.replaceState" in fn.split("previewBaselineRestore")[0], (
            "the parameter must be removed BEFORE the preview opens, or a "
            "reload re-opens a preview nobody asked for")
        # HEAD unless "Restore from…" (7.1 step 5, C80) names a ref; both
        # parameters go before the preview opens.
        assert "const ref = params.get('restore_ref') || 'HEAD';" in fn
        before = fn.split("history.replaceState")[0]
        assert "params.delete('restore_head')" in before and "params.delete('restore_ref')" in before
        assert "previewBaselineRestore(ref, null, {devices})" in fn
