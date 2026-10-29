"""C2043, C2044 and C2062: every intent write path asks the one VLAN check
(`vlan_capability.judge` and its words, `vlan_capability.refusal`), so C1692's refusal holds
wherever intent is written.

The four paths: the intent patch (`intent_patch`, per operation; C1692), the intent editor's
commit (`intent_edit.commit`, `commit_many`, and the Intent tab's route over them; C2044),
bulk intent (`bulk_intent.plan` and `apply`, and Devices › Change a setting over them; C2043)
and Revert intent (`intent_ops.revert_entry`, the preview its apply computes again, and the
device page's revert card and confirm over them; C2062: a revert of a commit that took a VLAN
off puts it back). Each refuses a change that ADDS a VLAN to a device whose VLAN database is declared "no" or is
unknown, naming the device, its platform and device type, where the answer came from and what
would answer it; each allows it on a switch measured to have one; none refuses a VLAN removed,
or a change leaving the list as it was, and none reads the answer for such a change. The
editor's check as you type (`intent_edit.preview`; C2061) runs the same check and draws it, so
an edit its commit would refuse never shows as committable.

The worlds are the suite's own: the host's committed intent for r2 and s1
(`tests/test_committed_before_p1.host`), the fleet's real intent for bulk intent
(`tests/test_bulk_intent.lab`); the measurement is the reads engine run for real with a lab
switch's captured answer (`tests/test_vlan_capability.measure`).

A VLAN id carries no address, so the IPv4/IPv6 parity rule has no case here.
"""

import ast
import os
import re
import subprocess

import pytest

from tests.test_bulk_intent import _render, lab  # noqa: F401 (the fixture)
from tests.test_committed_before_p1 import DEVICES, host  # noqa: F401 (the fixture)
from tests.test_vlan_capability import (PLAIN_SWITCH, REFUSALS, ROUTER_NAMED_LIKE_A_SWITCH,
                                        SWITCH_ANSWERS, measure)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUESTS = {"extra": [], "id": "40", "name": "GUESTS"}
#: VLAN 40 with no name, in the shape of s1's committed VLAN 10 (tests/fixtures/committed/
#: s1.yml): a `vlans` list holding an unnamed VLAN is one leaf to `hostvars.plan_revert`, so a
#: revert of its removal puts the whole list back (C2062's case; a named VLAN alone is keyed
#: by its name, and a revert of its removal does not put it back: found building C2062).
BARE = {"extra": [], "id": "40", "name": ""}
#: r2 as the router it is, its NetBox device type the one the platform table declares.
R2_DECLARED = dict(DEVICES["r2"], _model="C8000V")


def _inventory(monkeypatch, *devices):
    from modules.nsot import vlan_capability
    monkeypatch.setattr(vlan_capability, "_inventory",
                        lambda name: [dict(d) for d in devices])


def _no_read(monkeypatch):
    from modules.nsot import vlan_capability
    monkeypatch.setattr(vlan_capability, "of",
                        lambda *a: pytest.fail("the VLAN database was read for a change "
                                               "adding no VLAN"))


def _head(repo):
    return subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"], capture_output=True,
                          text=True, check=True).stdout.strip()


# ── the one check ────────────────────────────────────────────────────────────

class TestTheCheck:
    def test_added_is_present_after_and_not_before(self):
        from modules.nsot.vlan_capability import added
        before = {"vlans": [{"id": "10"}, {"id": "20", "name": "USERS"}]}
        assert added(before, {"vlans": [{"id": 10}, {"id": "20", "name": "STAFF"},
                                        {"id": "40"}]}) == ["40"]
        assert added(before, {"vlans": [{"id": "10"}]}) == [], "a removal adds nothing"
        assert added(before, before) == []
        assert added({"vlans": []}, {"vlans": [{"id": "40"}, {"id": "50"}]}) == ["40", "50"]
        assert added({}, {"vlans": [{"id": "40"}]}) == ["40"], "no list before is none held"

    def test_a_change_adding_none_reads_nothing(self, monkeypatch):
        from modules.nsot import vlan_capability
        _no_read(monkeypatch)
        got = vlan_capability.judge("Lab", "r2", {"vlans": [{"id": "10"}]}, {"vlans": []},
                                    subject="this edit")
        assert got == {"ok": True, "added": [], "capability": None}

    def test_a_given_answer_is_not_read_again(self, monkeypatch):
        from modules.nsot import vlan_capability
        _no_read(monkeypatch)
        got = vlan_capability.judge("Lab", "s1", {}, {"vlans": [GUESTS]}, subject="the change",
                                    capability={"has": True})
        assert got["ok"] and got["added"] == ["40"]

    def test_no_network_named_is_refused_saying_it_was_not_read(self, monkeypatch):
        from modules.nsot import vlan_capability
        _no_read(monkeypatch)
        got = vlan_capability.judge("", "s1", {}, {"vlans": [GUESTS]}, subject="the change")
        assert (got["ok"], got["status"], got["stage"]) == (False, 409, "capability")
        assert "has a VLAN database is not read: no network was named" in got["error"]


# ── the intent editor's commit (C2044) ───────────────────────────────────────

def _with_vlan(text: str, *, add=None, drop=None, rename=None) -> str:
    """*text* (a committed document) with VLAN *add* added, the VLAN id *drop* removed, or
    VLAN *rename* = (id, name) renamed, in Mercury's own formatting."""
    from modules.nsot import hostvars
    doc = hostvars.from_yaml(text)
    vlans = list(doc.get("vlans") or [])
    if add:
        vlans.append(dict(add))
    if drop:
        vlans = [v for v in vlans if str(v.get("id")) != drop]
    if rename:
        vlans = [dict(v, name=rename[1]) if str(v.get("id")) == rename[0] else v
                 for v in vlans]
    doc["vlans"] = vlans
    return hostvars.to_yaml(doc)


def _edit(host_, name, **change):  # noqa: F811
    from modules.nsot import intent_edit
    opened = intent_edit.open_doc("Lab", name)
    return _with_vlan(opened["yaml"], **change), opened["base"]


class TestTheEditor:
    def test_a_router_declared_without_one_is_refused_naming_why(self, host,  # noqa: F811
                                                                 monkeypatch):
        """C2044 itself: the router's real committed intent holds `vlans: []`."""
        from modules.nsot import intent_edit
        _inventory(monkeypatch, R2_DECLARED, DEVICES["s1"])
        text, base = _edit(host, "r2", add=GUESTS)
        before = _head(host["repo"])
        got = intent_edit.commit("Lab", "r2", text, "add guests", base, "a.person")
        assert (got["ok"], got["status"], got["stage"]) == (False, 409, "capability")
        assert got["error"].startswith(
            "this edit adds VLAN 40, and r2 (cisco_iosxe, device type C8000V) has no VLAN "
            "database: declared: no VLAN database (Mercury's platform table, cisco_iosxe "
            "device type C8000V, documented: ")
        assert got["error"].endswith(". Nothing is added")
        assert _head(host["repo"]) == before, "nothing was committed"

    def test_an_unknown_router_is_refused_naming_what_would_answer_it(self, host,  # noqa: F811
                                                                     monkeypatch):
        from modules.nsot import intent_edit
        _inventory(monkeypatch, DEVICES["r2"], DEVICES["s1"])
        text, base = _edit(host, "r2", add=GUESTS)
        got = intent_edit.commit("Lab", "r2", text, "add guests", base, "a.person")
        assert got["stage"] == "capability"
        assert got["error"] == (
            "this edit adds VLAN 40, and whether r2 (cisco_iosxe, device type not named) has a "
            "VLAN database is not declared and not measured: run `show vlan id 1` on r2 (Show "
            "commands, or Ask the device on its page) to measure it, or name its device type "
            "in NetBox, by which Mercury's platform table declares a VLAN database (none is "
            "named). A VLAN is added only where a VLAN database is declared or measured")

    def test_a_measured_switch_takes_it(self, host):  # noqa: F811
        from modules.nsot import hostvars, intent_edit
        measure("Lab", "s1", SWITCH_ANSWERS[0])
        text, base = _edit(host, "s1", add=GUESTS)
        got = intent_edit.commit("Lab", "s1", text, "add guests", base, "a.person")
        assert got["ok"] and got["changed"], got
        assert GUESTS in hostvars.read_committed(host["repo"], "s1")["vlans"]

    def test_a_switch_measured_without_one_is_refused(self, host):  # noqa: F811
        from modules.nsot import intent_edit
        measure("Lab", "s1", REFUSALS[1])
        text, base = _edit(host, "s1", add=GUESTS)
        got = intent_edit.commit("Lab", "s1", text, "add guests", base, "a.person")
        assert got["stage"] == "capability"
        assert "has no VLAN database: measured: no VLAN database (s1's answer to " \
               "`show vlan id 1` at " in got["error"]

    @pytest.mark.parametrize("change", [{"drop": "30"}, {"rename": ("20", "STAFF")}],
                             ids=["removed", "unchanged-ids"])
    def test_a_removal_or_an_unchanged_list_is_never_asked(self, host,  # noqa: F811
                                                           monkeypatch, change):
        """s1 unknown (never measured), and no answer read: a committed document stays
        committable."""
        from modules.nsot import intent_edit
        _no_read(monkeypatch)
        text, base = _edit(host, "s1", **change)
        got = intent_edit.commit("Lab", "s1", text, "tidy vlans", base, "a.person")
        assert got["ok"] and got["changed"], got

    def test_commit_many_refuses_every_device_and_writes_nothing(self, host,  # noqa: F811
                                                                 monkeypatch):
        """Two documents, one committable: the one commit is refused whole, naming r2."""
        from modules.nsot import intent_edit
        _inventory(monkeypatch, R2_DECLARED, DEVICES["s1"])
        r2_text, r2_base = _edit(host, "r2", add=GUESTS)
        s1_text, s1_base = _edit(host, "s1", drop="30")
        before = _head(host["repo"])
        got = intent_edit.commit_many("Lab", [("s1", s1_text, s1_base),
                                              ("r2", r2_text, r2_base)], "both", "a.person")
        assert (got["ok"], got["stage"], got["hostname"]) == (False, "capability", "r2")
        assert _head(host["repo"]) == before

    def test_the_tab_draws_the_refusal_and_keeps_the_text(self, host,  # noqa: F811
                                                         monkeypatch):
        """Through the Intent tab's commit: the refusal where its other refusals are drawn,
        the person's document, summary and opened version kept in the editor."""
        import html as _h
        from types import SimpleNamespace
        _inventory(monkeypatch, R2_DECLARED, DEVICES["s1"])
        monkeypatch.setattr("routes.intent_v2._device_or_404", lambda name: (
            (SimpleNamespace(name="Lab"), dict(DEVICES[name])), None))
        text, base = _edit(host, "r2", add=GUESTS)
        r = host["client"].post("/v2/device/r2/intent/commit",
                                data={"yaml": text, "base": base, "summary": "add guests"})
        body = r.get_data(as_text=True)
        assert r.status_code == 409, body[:600]
        refused = re.search(r'<div class="notice notice-danger ie-refused".*?</div></div>',
                            body, re.S).group(0)
        words = " ".join(_h.unescape(re.sub(r"<[^>]+>", " ", refused)).split())
        assert "Not committed: this edit adds VLAN 40, and r2 (cisco_iosxe, device type " \
               "C8000V) has no VLAN database: declared: " in words
        assert words.endswith("Nothing is added. Nothing was written.")
        area = re.search(r'<textarea id="ie-text" name="yaml"[^>]*>(.*?)</textarea>', body,
                         re.S).group(1)
        assert _h.unescape(area).strip() == text.strip(), "the person's text kept"
        assert f'value="{base}"' in body and 'value="add guests"' in body


# ── the intent editor's check as you type (C2061) ────────────────────────────

def _counted(monkeypatch):
    """Every read of the device's answer, recorded, the real read answering."""
    from modules.nsot import vlan_capability
    real, reads = vlan_capability.of, []
    monkeypatch.setattr(vlan_capability, "of", lambda *a: reads.append(a) or real(*a))
    return reads


def _words(html_text: str) -> str:
    import html as _h
    return " ".join(_h.unescape(re.sub(r"<[^>]+>", " ", html_text)).split())


class TestTheEditorsCheck:
    """C2061: the editor's check as you type (`intent_edit.preview`) runs the commit's VLAN
    check, so an edit the commit refuses never shows as committable; it reads the device's
    answer only for an edit that adds a VLAN, and once."""

    def test_a_router_declared_without_one_fails_with_the_commits_words(  # noqa: F811
            self, host, monkeypatch):
        from modules.nsot import intent_edit
        _inventory(monkeypatch, R2_DECLARED, DEVICES["s1"])
        reads = _counted(monkeypatch)
        text, base = _edit(host, "r2", add=GUESTS)
        p = intent_edit.preview("Lab", "r2", text)
        assert p["ok"] and p["valid"], "the document is valid; the VLAN check fails apart"
        assert p["vlan_database"]["ok"] is False and p["vlan_database"]["added"] == ["40"]
        assert reads == [("Lab", "r2")], "read once for the preview"
        got = intent_edit.commit("Lab", "r2", text, "add guests", base, "a.person")
        assert got["stage"] == "capability"
        assert p["vlan_database"]["words"] == got["error"], "the commit's words, exactly"
        assert p["vlan_database"]["words"].startswith(
            "this edit adds VLAN 40, and r2 (cisco_iosxe, device type C8000V) has no VLAN "
            "database: declared: ")

    def test_an_unknown_router_fails_naming_what_would_answer_it(self, host,  # noqa: F811
                                                                monkeypatch):
        from modules.nsot import intent_edit
        _inventory(monkeypatch, DEVICES["r2"], DEVICES["s1"])
        text, _base = _edit(host, "r2", add=GUESTS)
        p = intent_edit.preview("Lab", "r2", text)
        assert p["ok"] and p["vlan_database"]["ok"] is False
        assert p["vlan_database"]["words"] == (
            "this edit adds VLAN 40, and whether r2 (cisco_iosxe, device type not named) has a "
            "VLAN database is not declared and not measured: run `show vlan id 1` on r2 (Show "
            "commands, or Ask the device on its page) to measure it, or name its device type "
            "in NetBox, by which Mercury's platform table declares a VLAN database (none is "
            "named). A VLAN is added only where a VLAN database is declared or measured")

    def test_a_measured_switch_passes_saying_where_the_answer_came_from(  # noqa: F811
            self, host):
        from modules.nsot import intent_edit
        measure("Lab", "s1", SWITCH_ANSWERS[0])
        text, _base = _edit(host, "s1", add=GUESTS)
        p = intent_edit.preview("Lab", "s1", text)
        assert p["ok"] and p["vlan_database"]["ok"] is True, p.get("vlan_database")
        assert p["vlan_database"]["added"] == ["40"]
        assert p["vlan_database"]["words"].startswith(
            "measured: a VLAN database (s1's answer to `show vlan id 1` at ")

    @pytest.mark.parametrize("change", [{"drop": "30"}, {"rename": ("20", "STAFF")}, {}],
                             ids=["removed", "unchanged-ids", "as-committed"])
    def test_a_removal_or_an_unchanged_list_reads_nothing(self, host,  # noqa: F811
                                                          monkeypatch, change):
        """s1 never measured, so a read would fail it: none is made, and no check drawn."""
        from modules.nsot import intent_edit
        reads = _counted(monkeypatch)
        text, _base = _edit(host, "s1", **change)
        p = intent_edit.preview("Lab", "s1", text)
        assert p["ok"] and "vlan_database" not in p, p.get("vlan_database")
        assert reads == []

    def test_the_patch_preview_hands_its_answer_in(self, host, monkeypatch):  # noqa: F811
        """Change it in words' preview reads the answer for its add_vlan and hands it to the
        editor's check, which draws it: one read per request, not two."""
        from modules.nsot import intent_patch
        measure("Lab", "s1", SWITCH_ANSWERS[0])
        reads = _counted(monkeypatch)
        shown = intent_patch.preview("Lab", "s1", {"hostname": "s1", "operations": [
            {"op": "add_vlan", "vlan": 40, "name": "GUESTS"}]})
        assert shown["ok"] and shown["vlan_database"]["ok"] is True, shown
        assert reads == [("Lab", "s1")]

    def test_a_drafts_row_carries_it(self):
        """The words row draws a draft's preview through the editor's check partial, cut to
        what it draws: the VLAN check is among them."""
        from routes import intent_v2
        check = {"ok": True, "added": ["40"], "words": "measured: a VLAN database (planted)"}
        assert intent_v2._drawn({"ok": True, "vlan_database": check})["vlan_database"] == check

    @staticmethod
    def _check(host_, name, text):  # noqa: F811
        r = host_["client"].post(f"/v2/device/{name}/intent/check", data={"yaml": text})
        body = r.get_data(as_text=True)
        assert r.status_code == 200, body[:600]
        row = re.search(r'<li data-check="vlan-database">.*?</li>', body, re.S)
        commit = re.search(r'<span class="op-act ie-commit" id="ie-commit" '
                           r'hx-swap-oob="true">(.*?)(<button\b[^>]*>)', body, re.S)
        assert commit, "the check draws the editor's Commit again, out of band"
        return (_words(row.group(0)) if row else None), _words(commit.group(1)), \
            commit.group(2)

    def test_the_tab_draws_a_failure_and_the_commit_waits(self, host,  # noqa: F811
                                                         monkeypatch):
        from types import SimpleNamespace
        _inventory(monkeypatch, R2_DECLARED, DEVICES["s1"])
        monkeypatch.setattr("routes.intent_v2._device_or_404", lambda name: (
            (SimpleNamespace(name="Lab"), dict(DEVICES[name])), None))
        text, base = _edit(host, "r2", add=GUESTS)
        row, said, button = self._check(host, "r2", text)
        assert row is not None and row.startswith(
            "fail Refused at commit: this edit adds VLAN 40, and r2 (cisco_iosxe, device type "
            "C8000V) has no VLAN database: declared: "), row
        assert row.endswith("Nothing is added.")
        assert re.search(r"\sdisabled[\s>]", button), "the Commit waits on the failing check"
        assert said.endswith("It waits until the VLAN check passes: take the VLAN out, or "
                             "declare or measure r2's VLAN database.")
        # The server refuses whatever the page showed.
        r = host["client"].post("/v2/device/r2/intent/commit",
                                data={"yaml": text, "base": base, "summary": "add guests"})
        assert r.status_code == 409

    def test_the_tab_draws_a_pass_and_the_commit_is_offered(self, host,  # noqa: F811
                                                           monkeypatch):
        from types import SimpleNamespace
        monkeypatch.setattr("routes.intent_v2._device_or_404", lambda name: (
            (SimpleNamespace(name="Lab"), dict(DEVICES[name])), None))
        measure("Lab", "s1", SWITCH_ANSWERS[0])
        text, _base = _edit(host, "s1", add=GUESTS)
        row, said, button = self._check(host, "s1", text)
        assert row is not None and row.startswith(
            "pass s1 can hold the VLAN this edit adds (40): measured: a VLAN database "), row
        assert not re.search(r"\sdisabled[\s>]", button) and "It waits" not in said
        row, said, button = self._check(host, "s1", _edit(host, "s1", drop="30")[0])
        assert row is None, "an edit adding no VLAN draws no VLAN check"
        assert not re.search(r"\sdisabled[\s>]", button)


# ── bulk intent (C2043) ──────────────────────────────────────────────────────

def _vlans(hostvars_, repo, name):
    return list(hostvars_.read_committed(repo, name).get("vlans") or [])


def _plan(repo, devices, steps, list_name="Lab"):
    from modules.nsot import bulk_intent
    return bulk_intent.plan(repo, devices, steps, render=_render, summary="guests",
                            list_name=list_name)


def _switches(lab_):  # noqa: F811
    """s1 and s2's VLANs, the one list both hold (the floor), and the step adding VLAN 40."""
    repo, hostvars, _R = lab_
    held = _vlans(hostvars, repo, "s1")
    assert held and held == _vlans(hostvars, repo, "s2"), "the floor: both hold one list"
    return held, [{"path": ["vlans"], "before": held, "after": held + [GUESTS]}]


class TestBulkIntent:
    def test_a_measured_switch_is_accepted_and_an_unknown_one_refused_by_name(
            self, lab, monkeypatch):  # noqa: F811
        """The batch proceeds without the refused device, as a drifted one does (the core's
        existing semantics: refused per device, never applied around)."""
        repo, _hv, _R = lab
        _inventory(monkeypatch, dict(PLAIN_SWITCH, hostname="s1"),
                   dict(PLAIN_SWITCH, hostname="s2"))
        _held, steps = _switches(lab)
        measure("Lab", "s1", SWITCH_ANSWERS[1])
        r = _plan(repo, ["s1", "s2"], steps)
        assert [a["device"] for a in r["accepted"]] == ["s1"]
        assert [x["device"] for x in r["refused"]] == ["s2"]
        assert r["refused"][0]["reason"] == (
            "the result would be refused: the change adds VLAN 40, and whether s2 (cisco_ios, "
            "device type not named) has a VLAN database is not declared and not measured: run "
            "`show vlan id 1` on s2 (Show commands, or Ask the device on its page) to measure "
            "it, or name its device type in NetBox, by which Mercury's platform table declares "
            "a VLAN database (none is named). A VLAN is added only where a VLAN database is "
            "declared or measured")
        assert r["headline"] == "1 device(s), 1 group(s), 1 refused"

    def test_routers_declared_without_one_and_unknown_are_both_refused(self, lab,  # noqa: F811
                                                                       monkeypatch):
        repo, hostvars, _R = lab
        assert _vlans(hostvars, repo, "r1") == _vlans(hostvars, repo, "r3") == [], "floor"
        _inventory(monkeypatch, dict(ROUTER_NAMED_LIKE_A_SWITCH, hostname="r1"),
                   {"hostname": "r3", "platform": "cisco_iosxe"})
        r = _plan(repo, ["r1", "r3"], [{"path": ["vlans"], "before": [], "after": [GUESTS]}])
        assert r["accepted"] == [] and [x["device"] for x in r["refused"]] == ["r1", "r3"]
        r1, r3 = (x["reason"] for x in r["refused"])
        assert r1.startswith(
            "the result would be refused: the change adds VLAN 40, and r1 (cisco_iosxe, device "
            "type C8000V) has no VLAN database: declared: no VLAN database (Mercury's platform "
            "table, cisco_iosxe device type C8000V, documented: ")
        assert "whether r3 (cisco_iosxe, device type not named) has a VLAN database is not " \
               "declared and not measured" in r3

    @pytest.mark.parametrize("which", ["removed", "unchanged-ids"])
    def test_a_removal_or_an_unchanged_list_is_never_asked(self, lab,  # noqa: F811
                                                           monkeypatch, which):
        repo, _hv, _R = lab
        _no_read(monkeypatch)
        held, _steps = _switches(lab)
        after = held[:-1] if which == "removed" else [dict(v, name=f"N{v['id']}") for v in held]
        r = _plan(repo, ["s1", "s2"], [{"path": ["vlans"], "before": held, "after": after}])
        assert r["refused"] == [] and [a["device"] for a in r["accepted"]] == ["s1", "s2"]

    def test_the_apply_commits_the_accepted_and_names_the_refused(self, lab,  # noqa: F811
                                                                  monkeypatch):
        from modules.nsot import bulk_intent
        repo, hostvars, _R = lab
        _inventory(monkeypatch, dict(PLAIN_SWITCH, hostname="s1"),
                   dict(PLAIN_SWITCH, hostname="s2"))
        held, steps = _switches(lab)
        measure("Lab", "s1", SWITCH_ANSWERS[0])
        shown = _plan(repo, ["s1", "s2"], steps)
        got = bulk_intent.apply("Lab", repo, ["s1", "s2"], steps, shown["hash"],
                                render=_render, summary="guests", actor="a.person")
        assert got["ok"] and got["devices"] == ["s1"] and got["refused"] == ["s2"], got
        assert GUESTS in _vlans(hostvars, repo, "s1")
        assert _vlans(hostvars, repo, "s2") == held, "the refused device left exactly as it was"

    def test_a_vlan_measured_away_after_the_preview_commits_nothing(self, lab,  # noqa: F811
                                                                    monkeypatch):
        """The refused set is in the hash: an answer that changed since the preview changes
        what would be committed, so the apply refuses naming both hashes."""
        import time

        from modules.nsot import bulk_intent
        repo, _hv, _R = lab
        _inventory(monkeypatch, dict(PLAIN_SWITCH, hostname="s1"))
        _held, steps = _switches(lab)
        measure("Lab", "s1", SWITCH_ANSWERS[0], when=time.time() - 60)
        shown = _plan(repo, ["s1"], steps)
        assert [a["device"] for a in shown["accepted"]] == ["s1"]
        measure("Lab", "s1", REFUSALS[1])
        before = _head(repo)
        got = bulk_intent.apply("Lab", repo, ["s1"], steps, shown["hash"], render=_render,
                                summary="guests", actor="a.person")
        assert got["ok"] is False and f"you gave {shown['hash']}" in got["error"]
        assert _head(repo) == before

    def test_change_a_setting_draws_the_refused_device_with_its_reason(self, lab,  # noqa: F811
                                                                       tmp_path, monkeypatch):
        """Devices › Change a setting: the preview names s2 refused with the check's words, and
        its confirm commits s1 alone."""
        import html as _h
        repo, hostvars, _R = lab
        monkeypatch.setattr("modules.config.LISTS_DIR", str(tmp_path))
        monkeypatch.setattr("modules.device.get_device_lists",
                            lambda: [{"name": "Lab", "filename": "lab"}])
        monkeypatch.setattr("modules.nsot.listref.exists", lambda name: str(name) == "Lab")
        monkeypatch.setattr("routes.templatize._bulk_render_and_eligible",
                            lambda list_name, repo: (_render, None))
        _inventory(monkeypatch, dict(PLAIN_SWITCH, hostname="s1"),
                   dict(PLAIN_SWITCH, hostname="s2"))
        held, _steps = _switches(lab)
        measure("Lab", "s1", SWITCH_ANSWERS[0])
        import yaml

        import app as A
        flow = yaml.safe_dump(held, default_flow_style=True, width=4096).strip()
        form = {"list": "Lab", "device": ["s1", "s2"], "summary": "guests",
                "path": ["vlans"], "before": [flow],
                "after": [yaml.safe_dump(held + [GUESTS], default_flow_style=True,
                                         width=4096).strip()]}
        client = A.app.test_client()
        html = client.post("/v2/devices/change/preview", data=form).get_data(as_text=True)
        assert "1 device(s), 1 group(s), 1 refused" in html, html[:600]
        refused = re.search(r'data-keep="bi-refused".*?</details>', html, re.S).group(0)
        words = " ".join(_h.unescape(re.sub(r"<[^>]+>", " ", refused)).split())
        assert "s2 the result would be refused: the change adds VLAN 40, and whether s2 " \
               "(cisco_ios, device type not named) has a VLAN database is not declared" in words
        h = re.search(r'name="hash" value="([0-9a-f]{16})"', html).group(1)
        r = client.post("/v2/devices/change/apply", data=dict(form, hash=h))
        assert r.status_code == 200, r.get_data(as_text=True)[:600]
        assert GUESTS in _vlans(hostvars, repo, "s1")
        assert GUESTS not in _vlans(hostvars, repo, "s2")


# ── one check, one home ──────────────────────────────────────────────────────

class TestThePathsShareTheOneCheck:
    """Plant the words (`vlan_capability.refusal`) and the read (`vlan_capability.of`): each
    path's refusal carries the planted words, and each reads the answer once per device."""

    @pytest.fixture
    def planted(self, monkeypatch):
        from modules.nsot import vlan_capability
        reads = []

        def of(list_name, hostname):
            reads.append(hostname)
            return {"hostname": hostname, "has": None, "words": "planted"}

        monkeypatch.setattr(vlan_capability, "of", of)
        monkeypatch.setattr(vlan_capability, "refusal",
                            lambda hostname, cap, adds: "" if cap.get("has") is True
                            else f"PLANTED {hostname}: {adds}")
        return reads

    def test_the_patch(self, host, planted):  # noqa: F811
        from modules.nsot import intent_patch
        got = intent_patch.preview("Lab", "s1", {"hostname": "s1", "operations": [
            {"op": "add_vlan", "vlan": 40, "name": "GUESTS"}]})
        assert got["error"] == "PLANTED s1: operations[0] adds VLAN 40"
        assert planted == ["s1"]

    def test_the_editor(self, host, planted):  # noqa: F811
        from modules.nsot import intent_edit
        text, base = _edit(host, "r2", add=GUESTS)
        got = intent_edit.commit("Lab", "r2", text, "add guests", base, "a.person")
        assert got["error"] == "PLANTED r2: this edit adds VLAN 40"
        assert planted == ["r2"]

    def test_bulk_intent(self, lab, planted):  # noqa: F811
        repo, _hv, _R = lab
        r = _plan(repo, ["r1", "r3"], [{"path": ["vlans"], "before": [], "after": [GUESTS]}])
        assert [x["reason"] for x in r["refused"]] == [
            f"the result would be refused: PLANTED {h}: the change adds VLAN 40"
            for h in ("r1", "r3")]
        assert planted == ["r1", "r3"]

    def test_a_patch_commit_reads_it_once(self, host, monkeypatch):  # noqa: F811
        """The patch reads the answer and hands it to the editor's commit, which asks the one
        check with it rather than reading again (C1692's once per request)."""
        from modules.nsot import intent_patch, vlan_capability
        measure("Lab", "s1", SWITCH_ANSWERS[0])
        patch = {"hostname": "s1", "operations": [{"op": "add_vlan", "vlan": 40,
                                                   "name": "GUESTS"}]}
        shown = intent_patch.preview("Lab", "s1", patch)
        assert shown["ok"], shown
        real, reads = vlan_capability.of, []
        monkeypatch.setattr(vlan_capability, "of",
                            lambda *a: reads.append(a) or real(*a))
        got = intent_patch.commit("Lab", "s1", patch, "add guests", shown["base"], "a.person")
        assert got["ok"] and got["changed"], got
        assert reads == [("Lab", "s1")]
        reads.clear()
        text, base = _edit(host, "s1", add=dict(GUESTS, id="50"))
        got = intent_patch.commit_many("Lab", [("s1", dict(patch, operations=[
            {"op": "add_vlan", "vlan": 60}]), base)], "add 60", "a.person")
        assert got["ok"] and reads == [("Lab", "s1")], (got, reads)

    def test_every_bulk_plan_caller_names_its_network(self):
        """`bulk_intent.plan` reads the VLAN database of the network it is told; a caller that
        named none would have every VLAN-adding device refused as not read. Every call outside
        the tests names ``list_name``, parsed, never matched as text."""
        calls = []
        for rel in ("routes/templatize.py", "scripts/nmas-bulk-intent",
                    "modules/nsot/bulk_intent.py"):
            with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
                tree = ast.parse(fh.read(), rel)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and (
                        (isinstance(node.func, ast.Attribute) and node.func.attr == "plan"
                         and isinstance(node.func.value, ast.Name)
                         and node.func.value.id == "bulk_intent")
                        or (isinstance(node.func, ast.Name) and node.func.id == "plan")):
                    calls.append((rel, node.lineno,
                                  {k.arg for k in node.keywords} >= {"list_name"}))
        assert len(calls) >= 3, f"the floor: the route, the script and apply; found {calls}"
        assert all(named for _r, _l, named in calls), calls

    def test_the_revert(self, host, planted):  # noqa: F811
        from modules.nsot import intent_ops
        removal = _history(host, "r2", BARE)
        got = intent_ops.revert_entry("Lab", "r2", removal)
        assert got["error"] == f"PLANTED r2: reverting {removal[:12]} adds VLAN 40"
        assert planted == ["r2"]


# ── Revert intent (C2062) ────────────────────────────────────────────────────

def _history(host_, name, vlan, *, take_off=True):  # noqa: F811
    """*name*'s intent history as one committed before the check could hold it: a commit
    adding *vlan* (written as a pre-C1692 commit was, past no check), then, *take_off*, the
    editor's commit taking it off again (a removal, never asked). The removal's sha (what a
    revert of it would put back is *vlan*), or without *take_off* the adding commit's."""
    from modules.nsot import hostvars, intent_edit
    from modules.nsot.repo import save_host_vars
    repo = host_["repo"]
    doc = hostvars.read_committed(repo, name)
    hostvars.write_committed(repo, dict(doc, vlans=list(doc.get("vlans") or []) + [vlan]))
    assert save_host_vars("Lab", [name], actor="t", source="extraction",
                          message=f"host_vars: {name} adds VLAN {vlan['id']}")["ok"]
    if not take_off:
        return _head(repo)
    text, base = _edit(host_, name, drop=str(vlan["id"]))
    took = intent_edit.commit("Lab", name, text, f"drop VLAN {vlan['id']}", base, "a.person")
    assert took["ok"] and took["changed"], took
    removal = _head(repo)
    assert vlan not in (hostvars.read_committed(repo, name).get("vlans") or []), "premise"
    return removal


def _revert(name, sha):
    from modules.nsot import intent_ops
    entry = intent_ops.revert_entry("Lab", name, sha)
    return entry, intent_ops.revert_apply("Lab", name, sha, entry["hash"] or "none",
                                          "a.person")


class TestTheRevert:
    """C2062: a revert of a commit that took a VLAN off puts it back, so it asks the one check.
    The history is r2's and s1's real committed intent with a VLAN added and taken off again;
    the commit reverted is the removal."""

    def test_a_router_declared_without_one_is_refused_and_nothing_committed(  # noqa: F811
            self, host, monkeypatch):
        from modules.nsot import hostvars
        _inventory(monkeypatch, R2_DECLARED, DEVICES["s1"])
        removal = _history(host, "r2", BARE)
        before = _head(host["repo"])
        entry, out = _revert("r2", removal)
        assert (entry["selectable"], entry.get("stage"), entry["hash"]) == (
            False, "capability", "")
        assert entry["error"].startswith(
            f"reverting {removal[:12]} adds VLAN 40, and r2 (cisco_iosxe, device type C8000V) "
            "has no VLAN database: declared: no VLAN database (Mercury's platform table, "
            "cisco_iosxe device type C8000V, documented: ")
        assert entry["error"].endswith(". Nothing is added")
        assert entry["vlan_database"] == {"ok": False, "added": ["40"],
                                          "words": entry["error"]}
        assert (out["outcome"], out["reason"]) == ("refused", entry["error"])
        assert _head(host["repo"]) == before, "nothing was committed"
        assert BARE not in (hostvars.read_committed(host["repo"], "r2").get("vlans") or [])

    def test_an_unknown_router_is_refused_naming_what_would_answer_it(  # noqa: F811
            self, host, monkeypatch):
        _inventory(monkeypatch, DEVICES["r2"], DEVICES["s1"])
        removal = _history(host, "r2", BARE)
        entry, out = _revert("r2", removal)
        assert entry["error"] == (
            f"reverting {removal[:12]} adds VLAN 40, and whether r2 (cisco_iosxe, device type "
            "not named) has a VLAN database is not declared and not measured: run `show vlan "
            "id 1` on r2 (Show commands, or Ask the device on its page) to measure it, or name "
            "its device type in NetBox, by which Mercury's platform table declares a VLAN "
            "database (none is named). A VLAN is added only where a VLAN database is declared "
            "or measured")
        assert out["outcome"] == "refused"

    def test_a_switch_measured_without_one_is_refused(self, host):  # noqa: F811
        measure("Lab", "s1", REFUSALS[1])
        removal = _history(host, "s1", BARE)
        entry, out = _revert("s1", removal)
        assert entry.get("stage") == "capability" and out["outcome"] == "refused"
        assert "has no VLAN database: measured: no VLAN database (s1's answer to " \
               "`show vlan id 1` at " in entry["error"]

    def test_a_measured_switch_takes_it_back(self, host):  # noqa: F811
        from modules.nsot import hostvars
        measure("Lab", "s1", SWITCH_ANSWERS[0])
        removal = _history(host, "s1", BARE)
        entry, out = _revert("s1", removal)
        assert entry["selectable"] and entry["vlan_database"]["ok"] is True, entry
        assert entry["vlan_database"]["words"].startswith(
            "measured: a VLAN database (s1's answer to `show vlan id 1` at ")
        assert out["outcome"] == "reverted", out
        assert BARE in hostvars.read_committed(host["repo"], "s1")["vlans"]

    def test_a_revert_taking_a_vlan_off_is_never_asked(self, host, monkeypatch):  # noqa: F811
        """Reverting the commit that ADDED the VLAN takes it off: nothing is read (a read
        would fail the test), and the revert commits on r2, whose answer would refuse an add
        (a committed document stays committable)."""
        from modules.nsot import hostvars
        added_it = _history(host, "r2", BARE, take_off=False)
        _no_read(monkeypatch)
        entry, out = _revert("r2", added_it)
        assert "vlan_database" not in entry and entry["selectable"], entry
        assert out["outcome"] == "reverted", out
        assert BARE not in (hostvars.read_committed(host["repo"], "r2").get("vlans") or [])

    def test_the_card_draws_the_refusal_as_its_own_check(self, host,  # noqa: F811
                                                        monkeypatch):
        """The revert card (v2 device page, board 11): the VLAN check is its own gate, failed
        with the check's words, the change's own gate passing, and no confirm offered."""
        from modules.preview_confirm import revert_preview
        from modules.nsot import intent_ops
        _inventory(monkeypatch, R2_DECLARED, DEVICES["s1"])
        removal = _history(host, "r2", BARE)
        entry = intent_ops.public(intent_ops.revert_entry("Lab", "r2", removal))
        with host["client"].application.test_request_context("/"):
            from flask import request
            shown = revert_preview(entry, list_name="Lab", request=request)
        (target,) = shown["targets"]
        gates = {g["name"]: (g["state"], g["detail"]) for g in target["gates"]}
        assert gates["the commit's change can be undone"][0] == "pass"
        assert gates["r2 can hold the VLAN(s) this revert puts back (40)"] == (
            "fail", entry["error"])
        (what,) = shown["what"]["targets"]
        assert what["selectable"] is False and entry["error"] in what["why_not"], what

    def test_the_route_refuses_it_in_place(self, host, monkeypatch):  # noqa: F811
        """Through the card's confirm (`/v2/device/<name>/revert/confirm`): refused, the
        check's words drawn, nothing committed."""
        import html as _h
        from types import SimpleNamespace
        _inventory(monkeypatch, R2_DECLARED, DEVICES["s1"])
        monkeypatch.setattr("routes.device_v2._named_device", lambda name, lst, tpl: (
            SimpleNamespace(name="Lab"), dict(DEVICES[name]), None))
        removal = _history(host, "r2", BARE)
        before = _head(host["repo"])
        r = host["client"].post("/v2/device/r2/revert/confirm",
                                data={"list": "Lab", "sha": removal[:12], "hash": "0" * 16})
        words = _words(r.get_data(as_text=True))
        assert f"reverting {removal[:12]} adds VLAN 40, and r2 (cisco_iosxe, device type " \
               "C8000V) has no VLAN database" in words, words[:800]
        assert _head(host["repo"]) == before
