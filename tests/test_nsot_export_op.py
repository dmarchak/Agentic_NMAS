"""Committing a network's NSOT export as one operation (C2777; the operator's decision 8 of
2026-11-08; board docs/boards/nsot-export.html; `modules/nsot/export_op.py`).

Cases, each planted on a network whose NetBox is the Lab 9 records served by a fake client:
- the preview reads NetBox, writes nothing, and draws the export's hash beside the committed
  one with what changes by kind; the hash it carries binds the export and the committed file;
- the confirm, as a verified person with that hash, reads NetBox again and commits
  ``nsot/export.json`` with Actor, Actor-Verified, Export-Sha256 and Source; the card at rest
  then reads that commit from the repository's history; every page hears ``nsot_export``;
- a preview whose export is the committed one offers no confirm, and its confirm commits
  nothing;
- NetBox moving after the preview, or another commit of the export, refuses the confirm naming
  both values, and nothing is committed; so does an unverified actor or a missing hash;
- `export.changes` names what was added, removed and changed by each object's natural key (an
  IPv6 prefix beside an IPv4 one);
- the routes: SDN › Apps draws the card (none committed, then committed), the preview and the
  confirm answer in the card's place, the confirm's response declares ``nsot_export``, and a
  network whose devices are not NetBox's has the control disabled, saying why."""

import copy
import json

import pytest

from modules.nsot import export as X
from modules.nsot import export_op as OP
from tests.test_openflow_golden import _records, fake_netbox
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture

NET = "Default"
ACTOR, VERIFIED = "op@example.invalid", "access-assertion"


@pytest.fixture
def lab(networks, monkeypatch):  # noqa: F811 - the fixture, used
    """Default read from NetBox (the Lab 9 records, served by a fake client that `state` can
    change), its configuration repository under the networks' tmp folder."""
    state = {"records": copy.deepcopy(_records()), "announced": []}
    monkeypatch.setattr("modules.inventory.source_config.load",
                        lambda name: {"source": "netbox", "filters": {"role": "openflow-switch"}})
    monkeypatch.setattr("modules.nsot.hooks.run_post_commit", lambda ctx: None)
    real = X.build

    def build(network, **kw):
        get, _calls = fake_netbox(state["records"])
        return real(network, get=get, version=lambda: state["records"]["netbox_version"])

    monkeypatch.setattr(X, "build", build)
    monkeypatch.setattr("modules.invalidation.announce",
                        lambda keys, by, ok=True: state["announced"].append((tuple(keys), by)))
    return state


def _rename_a_switch(state):
    for d in state["records"]["devices"]:
        if d["name"] == "ovs1":
            d["custom_fields"] = dict(d.get("custom_fields") or {}, os_version="3.3.9")
            return
    raise AssertionError("the fixture has no ovs1")


def _head():
    from modules.nsot import listref
    from modules.nsot.repo import git

    return git(listref.resolve(NET).repo_dir, "rev-parse", "HEAD")[1]


def _commit():
    p = OP.preview(NET)
    assert p["ok"] and p["state"] == "preview", p
    return p, OP.apply(NET, p["hash"], actor=ACTOR, actor_verified=VERIFIED)


# ── the operation ────────────────────────────────────────────────────────────────────────────

def test_the_first_preview_names_every_object_added_and_binds_no_committed_file(lab):
    p = OP.preview(NET)
    assert p["ok"] and p["state"] == "preview"
    assert p["committed"]["blob"] == "" and not p["committed"]["readable"]
    assert p["hash"] == OP.plan_hash(NET, p["sha256"], "")
    devices = next(k for k in p["changes"]["kinds"] if k["kind"] == "devices")
    assert devices["added_n"] == len(lab["records"]["devices"]) and devices["removed_n"] == 0
    assert p["changes"]["total"] >= devices["added_n"]


def test_the_confirm_commits_as_the_person_and_the_card_reads_it_back(lab):
    p, done = _commit()
    assert done["outcome"] == "committed" and done["sha256"] == p["sha256"], done
    from modules.nsot import listref
    from modules.nsot.repo import git
    _rc, body, _ = git(listref.resolve(NET).repo_dir, "log", "-1", "--format=%B")
    assert f"Actor: {ACTOR}" in body and f"Actor-Verified: {VERIFIED}" in body
    assert f"Export-Sha256: {p['sha256']}" in body and "Source: nsot_export" in body
    rest = OP.last(NET)
    assert rest["state"] == "ok" and rest["sha256"] == p["sha256"]
    assert rest["commit"] == done["commit"] and rest["actor"] == ACTOR
    assert rest["counts"]["devices"] == len(lab["records"]["devices"])
    assert lab["announced"] == [(OP.ANNOUNCE_KEYS, OP.ANNOUNCER)]


def test_a_preview_that_changes_nothing_offers_no_confirm_and_its_confirm_commits_nothing(lab):
    _commit()
    head = _head()
    p = OP.preview(NET)
    assert p["state"] == "nothing" and p["committed"]["sha256"] == p["sha256"]
    done = OP.apply(NET, p["hash"], actor=ACTOR, actor_verified=VERIFIED)
    assert done["outcome"] == "unchanged" and _head() == head


def test_a_preview_writes_nothing(lab):
    _commit()
    head = _head()
    _rename_a_switch(lab)
    p = OP.preview(NET)
    assert p["state"] == "preview" and _head() == head
    changed = next(k for k in p["changes"]["kinds"] if k["kind"] == "devices")["changed"]
    assert changed == ["ovs1"]


def test_netbox_moving_after_the_preview_commits_nothing_naming_both_hashes(lab):
    p = OP.preview(NET)
    _rename_a_switch(lab)
    done = OP.apply(NET, p["hash"], actor=ACTOR, actor_verified=VERIFIED,
                    then_sha=p["sha256"], then_blob=p["base_blob"])
    assert done["outcome"] == "refused" and done["moved"]
    assert f"the preview showed sha256:{p['sha256'][:12]}" in done["error"]
    assert "now hashes sha256:" in done["error"] and "nothing was committed" in done["error"]
    assert OP.last(NET)["state"] == "none"


def test_another_commit_of_the_export_since_the_preview_is_refused_naming_both(lab):
    _commit()
    _rename_a_switch(lab)
    mine = OP.preview(NET)
    lab["records"]["devices"][0]["custom_fields"] = dict(
        lab["records"]["devices"][0].get("custom_fields") or {}, note="another person's")
    theirs = OP.preview(NET)
    OP.apply(NET, theirs["hash"], actor="other@example.invalid", actor_verified=VERIFIED)
    head = _head()
    lab["records"]["devices"][0]["custom_fields"].pop("note")
    done = OP.apply(NET, mine["hash"], actor=ACTOR, actor_verified=VERIFIED,
                    then_sha=mine["sha256"], then_blob=mine["base_blob"])
    assert done["outcome"] == "refused" and _head() == head
    assert "the committed export moved since the preview" in done["error"]
    assert f"previewed blob {mine['base_blob'][:4]}" in done["error"]


def test_the_write_checks_the_committed_file_inside_the_lock(lab):
    _commit()
    built = X.build(NET)
    got = X.write(NET, ACTOR, VERIFIED, data=built["bytes"], base_blob="0" * 40)
    assert not got["ok"] and got["moved"]
    assert "previewed blob 0000…0000" in got["error"] and "nothing was committed" in got["error"]


@pytest.mark.parametrize("actor, verified, hash_, words", [
    ("", VERIFIED, "a" * 64, "verified person"),
    (ACTOR, "none", "a" * 64, "verified person"),
    (ACTOR, VERIFIED, "", "carries no preview hash"),
])
def test_an_unverified_actor_or_no_hash_is_refused(lab, actor, verified, hash_, words):
    done = OP.apply(NET, hash_, actor=actor, actor_verified=verified)
    assert done["outcome"] == "refused" and words in done["error"]
    assert OP.last(NET)["state"] == "none"


def test_a_network_not_netboxs_is_refused_and_its_card_says_why(lab, monkeypatch):
    # The fake client stands in for NetBox's GETs only: `collect` still asks the source first.
    monkeypatch.setattr("modules.inventory.source_config.load",
                        lambda name: {"source": "local"})
    p = OP.preview(NET)
    assert not p["ok"] and "not NetBox" in p["error"]
    rest = OP.last(NET)
    assert rest["state"] == "none" and not rest["netbox"]
    assert "not NetBox" in rest["source_words"]


def test_a_committed_export_that_does_not_read_is_unreadable_never_none(lab):
    _commit()
    import os

    from modules.nsot import listref
    from modules.nsot.repo import commit, git, repo_lock
    repo = listref.resolve(NET).repo_dir
    path = os.path.join(repo, X.PATH)
    with open(path, encoding="utf-8") as fh:
        doc = json.loads(fh.read())
    doc["network"] = "edited"
    with repo_lock(repo):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(doc))
        git(repo, "add", X.PATH)
        commit(repo, "edit the export by hand\n\nSource: test\n", publish_now=False)
    rest = OP.last(NET)
    assert rest["state"] == "unreadable" and "edited after it was built" in rest["error"]


# ── what changed ─────────────────────────────────────────────────────────────────────────────

def _doc(prefixes, devices=()):
    return {"netbox_version": "4.2.9", "body": {
        "devices": [{"name": n, "status": "active"} for n in devices], "interfaces": [],
        "vlans": [], "services": [], "cables": [],
        "prefixes": [{"prefix": p, "site": "lab"} for p in prefixes]}}


def test_changes_are_named_by_natural_key_ipv6_beside_ipv4():
    old = _doc(["192.0.2.0/24", "2001:db8::/64"], devices=["sw1", "sw2"])
    new = _doc(["192.0.2.0/24", "2001:db8:1::/64", "198.51.100.0/24"], devices=["sw1"])
    new["body"]["devices"][0]["status"] = "planned"
    ch = X.changes(old, new)
    by = {k["kind"]: k for k in ch["kinds"]}
    assert by["prefixes"]["added"] == ["198.51.100.0/24 (lab)", "2001:db8:1::/64 (lab)"]
    assert by["prefixes"]["removed"] == ["2001:db8::/64 (lab)"]
    assert by["devices"]["removed"] == ["sw2"] and by["devices"]["changed"] == ["sw1"]
    assert ch["total"] == 5


def test_a_cable_is_named_by_its_two_ends():
    old = _doc([])
    new = _doc([])
    new["body"]["cables"] = [{"a": [["sw1", "Ethernet3"]], "b": [["sw3", "Ethernet1"]],
                              "status": "connected", "label": ""}]
    by = {k["kind"]: k for k in X.changes(old, new)["kinds"]}
    assert by["cables"]["added"] == ["sw1:Ethernet3 to sw3:Ethernet1"]


# ── the routes ───────────────────────────────────────────────────────────────────────────────

def _client():
    import app as A
    return A.app.test_client()


def test_sdn_apps_draws_the_card_none_committed_and_its_preview_commits_nothing(lab):
    c = _client()
    html = c.get(f"/v2/sdn/apps?list={NET}").get_data(as_text=True)
    assert 'id="nsot-export"' in html and "none committed" in html
    assert f"{NET} has no committed NSOT export" in html
    assert 'data-op="nsot-export"' in html and "Export from NetBox…" in html
    # Pressed: the preview draws, and nothing is committed.
    assert c.post("/v2/sdn/export/preview", data={"list": NET}).status_code == 200
    assert OP.last(NET)["state"] == "none" and lab["announced"] == []


def test_the_apps_region_redraws_on_the_export_and_draws_the_new_commit(lab):
    """Every screen reading the export shows the new state: the Apps region listens for both
    keys a commit and a fetch announce, and its redraw after a commit draws the commit."""
    import re

    c = _client()
    p = OP.preview(NET)
    assert c.post("/v2/sdn/export/confirm", data={"list": NET, "hash": p["hash"],
                                                  "sha256": p["sha256"],
                                                  "base_blob": ""}).status_code == 200
    html = c.get(f"/v2/sdn/view?list={NET}&tab=apps").get_data(as_text=True)
    trigger = re.search(r'<div id="sdn"[^>]*hx-trigger="([^"]*)"', html).group(1)
    assert "nmas:nsot_export from:body" in trigger and "nmas:code_repo from:body" in trigger
    assert f"sha256:{p['sha256'][:4]}…{p['sha256'][-4:]}" in html and ">committed<" in html


def test_the_preview_and_confirm_answer_in_the_cards_place_and_declare_what_moved(lab):
    c = _client()
    r = c.post("/v2/sdn/export/preview", data={"list": NET})
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and "Commit the export" in html and "data-holds-live" in html
    p = OP.preview(NET)
    assert f'name="hash" value="{p["hash"]}"' in html
    assert f'name="sha256" value="{p["sha256"]}"' in html
    assert "none: this is Default's first export" in html
    r = c.post("/v2/sdn/export/confirm", data={"list": NET, "hash": p["hash"],
                                               "sha256": p["sha256"], "base_blob": ""})
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and "Committed Default's NSOT export" in html, html
    assert "nsot_export" in r.headers.get("X-NMAS-Invalidates", "")
    assert OP.last(NET)["state"] == "ok"
    rest = c.get(f"/v2/sdn/apps?list={NET}").get_data(as_text=True)
    assert f"sha256:{p['sha256'][:4]}…{p['sha256'][-4:]}" in rest and ">committed<" in rest


def test_a_confirm_whose_hash_moved_answers_409_and_commits_nothing(lab):
    c = _client()
    p = OP.preview(NET)
    _rename_a_switch(lab)
    r = c.post("/v2/sdn/export/confirm", data={"list": NET, "hash": p["hash"],
                                               "sha256": p["sha256"], "base_blob": ""})
    html = r.get_data(as_text=True)
    assert r.status_code == 409 and "the export moved since the preview" in html
    assert "Preview again" in html and OP.last(NET)["state"] == "none"


def test_a_preview_naming_no_network_is_refused(lab):
    from modules.nsot import listref

    r = _client().post("/v2/sdn/export/preview", data={"list": "nowhere"})
    assert r.status_code == 400 and "there is no network named" in r.get_data(as_text=True)
    assert not listref.exists("nowhere") and OP.last(NET)["state"] == "none"
