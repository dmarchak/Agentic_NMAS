"""The device page's Retire, on v2 (7.3; the device-actions canvas, board 12, signed off
2026-10-03 with the change asked: what is GENERATED is dropped at its next regeneration and
the result says so; what SURVIVES is named with how it is removed), and a retired device's
address showing its retired record (C185, the flagged choice agreed).

On test_retire_screen's world (r4 and r5 in the list 'Lab': a real repository, CSV, manifest
and credential store; NetBox holding r5 as device 9, created by hand). The plan is
`retire.plan`, the apply `retire.apply` with the export log as the break-glass basis, the
ones `/retire/*` use:

- the menu row runs here, and the menu says every action does;
- the card: the reason, the steps in order (the row last), the generated (the heartbeat rule;
  the scrape targets where a target directory is set) with when each drops, what survives
  with how each is removed (NetBox, Oxidized's row, a hand-built panel), what it leaves
  unchanged, the checks; with no export holding r5's credential it is refused and points at
  Credentials; a preview writes nothing; an empty reason offers no confirm;
- the confirm carries its list and retires as the person; the result says what was done, what
  was dropped (the targets read back) and what is still to remove; the device's address then
  shows its retired record; a plan that moved does nothing; no list or no hash refused;
- `targets_after` reads the files back (dropped, still, not managed); `retired_record` matches
  the trailer exactly;
- in a real browser, from the menu to the result, then the address showing the record.
"""

import html as html_mod
import json
import os
import re

import pytest

from tests.conftest import TEST_PERSON
from tests.test_retire_screen import REASON, _export, _state, screen  # noqa: F401
from tests.test_retire import world  # noqa: F401


@pytest.fixture
def page(screen, monkeypatch):  # noqa: F811
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
    return screen


@pytest.fixture
def exported(page):
    _export(page)
    return page


def _get(lab, url):
    r = lab["client"].get(url)
    return r, r.get_data(as_text=True)


def _vals(card):
    m = re.search(r"hx-vals='([^']*)'", card[card.index("op-confirm"):])
    return json.loads(html_mod.unescape(m.group(1)))


def _part(card, title):
    start = card.index(f"<h3>{title}</h3>")
    nxt = card.find('<div class="op-part">', start)
    return card[start:nxt if nxt > 0 else len(card)]


def _card(lab, reason=REASON):
    from urllib.parse import quote
    return _get(lab, f"/v2/device/r5/retire?reason={quote(reason)}")


def _targets(monkeypatch, tmp_path, devices):
    """A target directory, and a generation naming *devices* (what the keeper would write)."""
    from modules import prometheus_targets as PT
    d = tmp_path / "targets"
    d.mkdir(exist_ok=True)
    monkeypatch.setattr(PT, "target_dir", lambda: str(d))
    monkeypatch.setattr(PT, "_record_path", lambda: str(tmp_path / "targets-record.json"))
    groups = [{"targets": [ip], "labels": {"device": h}} for h, ip in devices]
    monkeypatch.setattr(PT, "generate", lambda: {
        "files": {"nmas-snmp-all.json": groups}, "devices": len(groups), "inventory": 2,
        "notes": [], "excluded": {}})
    return d


class TestTheMenu:
    def test_the_row_runs_here_and_every_action_does(self, page):
        _r, body = _get(page, "/v2/device/r5")
        menu = body[body.index('role="menu"'):body.index('class="tabs"')]
        assert 'hx-get="/v2/device/r5/retire?back=overview&amp;list=Lab"' in menu
        assert "manage_device" not in menu and "/manage/" not in menu
        assert "Every action runs here." in menu
        _r, body = _get(page, "/v2/device/r5?op=retire")
        assert "Retire r5 from management" in body[body.index('id="tab-body"'):]


class TestTheCard:
    def test_steps_generated_survives_and_a_preview_writes_nothing(self, exported, monkeypatch,
                                                                    tmp_path):
        _targets(monkeypatch, tmp_path, [("r4", "192.0.2.14"), ("r5", "192.0.2.15")])
        before = _state(exported)
        r, card = _card(exported)
        assert r.status_code == 200 and "default-src" in r.headers.get(
            "Content-Security-Policy", "")
        steps = re.findall(r"<li>(.*?)</li>", _part(card, "What retire changes, in order"))
        assert steps[-1].startswith("delete the CSV row"), "the row goes last"
        assert any("one commit: remove host_vars/r5.yml, golden/r5.cfg" in s for s in steps)
        gen = _part(card, "Generated, so dropped")
        assert "Prometheus&#39;s scrape targets" in gen and "drops it at its next run" in gen
        assert "Its Grafana heartbeat rule" in gen
        survives = _part(card, "What survives")
        assert "The NetBox device 9" in survives and "delete it in NetBox" in survives
        assert "Oxidized" not in survives, "Oxidized is retired (Phase 3)"
        assert "removed in Grafana" in survives
        assert "Its credential survives ONLY in the break-glass record" in survives
        unchanged = _part(card, "Not changed")
        assert "running configuration is not changed" in unchanged
        assert "NetBox device 9 is KEPT" not in unchanged, "said once, under What survives"
        vals = _vals(card)
        assert vals["list"] == "Lab" and vals["reason"] == REASON and vals["hash"]
        assert _state(exported) == before, "a preview writes nothing"

    def test_without_an_export_it_is_refused_and_points_at_credentials(self, page):
        _r, card = _card(page)
        assert "op-confirm" not in card
        assert "Refused until the break-glass record holds r5" in card
        assert 'href="/v2/credentials?list=Lab&amp;open=export"' in card

    def test_an_empty_reason_offers_no_confirm(self, exported):
        _r, card = _card(exported, reason="")
        assert "op-confirm" not in card and "a reason is given" in card


class TestTheConfirm:
    def test_it_retires_as_the_person_and_the_address_shows_the_record(self, exported,
                                                                       monkeypatch, tmp_path):
        d = _targets(monkeypatch, tmp_path, [("r4", "192.0.2.14")])
        _r, card = _card(exported)
        r = exported["client"].post("/v2/device/r5/retire/confirm", data=_vals(card))
        out = r.get_data(as_text=True)
        assert r.status_code == 200 and "r5 is retired" in out and "op-ok" in out, out[:600]
        dropped = _part(out, "Dropped")
        assert "Prometheus&#39;s targets were regenerated without r5 (read back at" in dropped
        assert "heartbeat rule" in dropped
        assert "Oxidized" not in _part(out, "Still to remove")
        assert "this address shows its retired record" in out and "Back to Devices" in out
        assert json.loads((d / "nmas-snmp-all.json").read_text())[0]["labels"]["device"] == "r4"
        msg = exported["R"].git(exported["repo"], "log", "-1", "--format=%B")[1]
        assert "Retired-Device: r5" in msg and f"Actor: {TEST_PERSON}" in msg
        r, page_html = _get(exported, "/v2/device/r5")
        assert r.status_code == 200 and "Its record" in page_html
        assert f"Retired by {TEST_PERSON}" in page_html and REASON in page_html
        head = exported["R"].git(exported["repo"], "rev-parse", "HEAD")[1]
        assert head[:12] in page_html
        assert "/v2/history?device=r5" in page_html.replace("&amp;", "&")

    def test_a_plan_that_moved_does_nothing(self, exported):
        _r, card = _card(exported)
        vals = dict(_vals(card), hash="0" * 16)
        before = _state(exported)
        out = exported["client"].post("/v2/device/r5/retire/confirm",
                                      data=vals).get_data(as_text=True)
        assert "op-ok" not in out and "the plan changed since you confirmed it" in out
        assert _state(exported) == before

    @pytest.mark.parametrize("drop, said", [("list", "names no list"),
                                            ("hash", "carried no plan")])
    def test_a_confirm_without_its_list_or_hash_is_refused(self, exported, drop, said):
        _r, card = _card(exported)
        vals = dict(_vals(card))
        vals.pop(drop)
        before = _state(exported)
        r = exported["client"].post("/v2/device/r5/retire/confirm", data=vals)
        assert r.status_code == 400 and said in r.get_data(as_text=True)
        assert _state(exported) == before


def test_a_free_device_draws_the_card_again(exported):
    _r, out = _get(exported, "/v2/device/r5/when-free?op=retire&back=history")
    assert "Retire r5 from management" in out and 'id="device-op"' in out


def test_a_held_card_keeps_the_reason_typed_when_it_reads_again(exported):
    """C515 (the throwaway session's STOP 8): the card re-planned with "Reason: none given"
    after a reason was typed. A held card re-read itself through a URL frozen with the
    reason of its last plan; it sends its FORM now (C473's shape), so what is typed survives."""
    import os
    src = open(os.path.join(os.path.dirname(__file__), "..", "templates", "v2", "_retire.html"),
               encoding="utf-8").read()
    (held,) = [l for l in src.splitlines() if "when_free" in l and "op='retire'" in l]
    assert 'hx-include="find .op-form"' in held and "reason=" not in held, held
    _r, out = _get(exported, "/v2/device/r5/when-free?op=retire&back=history"
                             "&reason=returned+to+the+provider")
    assert 'value="returned to the provider"' in out


class TestTheReadBack:
    def test_targets_after_says_dropped_still_or_not_managed(self, monkeypatch, tmp_path):
        from modules import prometheus_targets as PT
        from modules.nsot import retire as RT
        monkeypatch.setattr(PT, "target_dir", lambda: "")
        assert RT.targets_after("r5", "192.0.2.15")["state"] == "not_managed"
        _targets(monkeypatch, tmp_path, [("r4", "192.0.2.14")])
        assert RT.targets_after("r5", "192.0.2.15")["state"] == "dropped"
        _targets(monkeypatch, tmp_path, [("r4", "192.0.2.14"), ("r5", "192.0.2.15")])
        got = RT.targets_after("r5", "192.0.2.15")
        assert got["state"] == "still" and "nmas-snmp-all.json" in got["statement"]
        monkeypatch.setattr(PT, "generate", lambda: (_ for _ in ()).throw(OSError("disk")))
        assert RT.targets_after("r5", "192.0.2.15")["state"] == "failed"

    def test_retired_record_matches_the_trailer_exactly(self, world):  # noqa: F811
        from modules.nsot import retire as RT
        R, repo = world["R"], world["repo"]
        with open(os.path.join(repo, "note.txt"), "w") as fh:
            fh.write("x\n")
        R.git(repo, "add", "note.txt")
        R.git(repo, "commit", "-q", "-m", "retire: r55\n\nRetired-Device: r55\nActor: a@b\n"
                                          "Reason: gone")
        assert RT.retired_record(repo, "r5") is None, "r55's retirement is not r5's"
        rec = RT.retired_record(repo, "r55")
        assert rec["reason"] == "gone" and rec["actor"] == "a@b"


#: The card, and htmx at rest (a swapped-in control binds while it settles).
CARD = "document.querySelector('#device-op')"
SETTLED = "!document.querySelector('.htmx-swapping, .htmx-settling, .htmx-request')"


HELPER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "scripts", "nmas-oxidized-cred")
#: router.db before: r4's and r5's rows, and a device no list manages.
ROUTER_DB = ["192.0.2.14:ios:admin:Pw1", "192.0.2.15:ios:admin:Pw2", "192.0.2.99:ios:admin:Pw3"]


@pytest.fixture
def oxidized(monkeypatch, tmp_path):
    """Oxidized configured, its router.db a temp file, and THE helper script run on it: only
    `sudo` and the install check are stood in for (C398)."""
    import subprocess
    import sys
    from modules.nsot import credential_rotation as CR

    db = tmp_path / "router.db"
    db.write_text("\n".join(ROUTER_DB) + "\n", encoding="utf-8")
    calls = []

    def run(flags, stdin, router_db=""):
        calls.append(list(flags))
        p = subprocess.run([sys.executable, HELPER, "--file", str(db), *flags],
                           input=stdin, capture_output=True, text=True)
        return json.loads(p.stdout or "{}")
    monkeypatch.setattr(CR, "oxidized_managed", lambda: True)
    monkeypatch.setattr(CR, "_run_helper", run)
    rows = lambda: [l for l in db.read_text(encoding="utf-8").splitlines() if l.strip()]  # noqa: E731
    return {"db": db, "rows": rows, "calls": calls}

