"""P.3 step 3 (register D5): "Restore Golden Config" goes through the guarded
restore preview, and that preview draws the exact program.

Two buttons, the device page's and bulk ops', POSTed to a replay that pushed
the whole golden line by line: no plan, no confirm hash, no rollback. Both then
opened `previewBaselineRestore('HEAD', ..., {devices})`, the path the approval
queue already hands off to, and the replay routes are gone. Both buttons left
at 7.8 (2026-10-15); the device page's Restore from… opens the same preview.

Routing two more buttons into that preview exposed its own defect: its confirm
dialog showed counts and at most three replace and three residue lines, and
never the lines to be ADDED. `commands` was computed by the route, carried to
the browser, and drawn nowhere, while the confirm hash covered it.

Stage 7.1 moved the preview onto THE preview-then-confirm component: the
plan builds the six parts (`modules/preview_confirm.restore_preview`) and
`previewConfirmHtml` draws them, executed here against the plan's real
payload over REAL `RestoreTarget`s (a stub target could not exhibit the
restore's own gates, and C75 lived there). Today's route and dialog left at 7.8
(2026-10-17); THE restore plan (`routes.golden.restore_plan`) is what the v2
device page's Restore from… and History's Re-apply… draw.
"""

import html as _html
import json
import re

import pytest

from tests.payload_render import render_preview

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
    """THE restore plan for *targets* as each of its callers draws it, masked on the way out
    (`mask_payload`, as the v2 device page's restore card and History's Re-apply… apply it),
    with the real merge_diff, merge_commands, prepare_restore and adapter. Today's
    /golden/restore/preview returned exactly this until it left at 7.8 (2026-10-17); *body*
    keeps its shape (ref, devices, un_onboard, authorise, advisory_diff, approval_id)."""
    from modules.outbound import mask_payload

    import routes.golden as golden

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
    body = body or {"ref": "HEAD"}
    out = mask_payload(golden.restore_plan(
        "Lab", body["ref"], body.get("devices"), un_onboard=body.get("un_onboard"),
        authorise=body.get("authorise") or {}, advisory_diff=body.get("advisory_diff") or "",
        approval_id=body.get("approval_id") or ""))
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

    def test_residue_points_at_the_one_home_for_removal(self, monkeypatch):
        """Mode B's fourth case, decided 2026-09-29: the restore stays additive
        and removal lives in the Deploy plan, so the residue says where to go,
        not only that the lines stay."""
        part = _part(_html_of(_real_payload(monkeypatch)), "what_not")
        assert "Removal has ONE home, the Deploy plan (Mode B)" in part, part
        assert "r1&#39;s Deploy plan" in part or "r1's Deploy plan" in part, part

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
            "device and capture unchanged since this preview": "at_apply",
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


# Today's re-apply dialog (partials__golden_repo.3.js: previewBaselineRestore, its modal, what it
# confirmed, and the index page opening it from the device page's Restore from…) left at 7.8
# (2026-10-17, P7-21), and its wiring tests with it. The v2 restore card confirms the program it
# drew, bound to its hash, and a program that moved is refused with nothing sent
# (tests/test_device_restore_v2.py).


