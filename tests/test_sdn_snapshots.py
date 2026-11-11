"""SDN › Flows' Collect now names what it kept (C3001; modules/sdn/analyst.py's `collections`,
`kept` and `kept_page`, routes/sdn_analyse_v2.py's `snapshots`, `history_sources.
sdn_collections`). At the Lab 9 sitting (2026-11-10) a snapshot's id was only in a hover text,
History recorded no collection, and no screen listed the kept snapshots.

**The data** is tests/test_sdn_analyst.py's: the recorded Ryu of the lab's fabric
(tests/fixtures/lab9_captures/2026-11-06, through `LabRyu`), collected by the analyst's own
`collect_job` and kept by its own `build_snapshot` and `save_snapshot`. Further snapshots are
the same collection with its time moved (the one edit), each file's write time set to its
collection's, as a snapshot is written when it is collected.

- **The card** draws the latest snapshot's id as text with Copy, its collection time in UTC
  and what it holds, and a collapsed Kept snapshots line counting them; it reads no snapshot
  file to do so.
- **The list**, asked when opened: each snapshot's id, collection time, switches, flows and
  seal (holds, broken, unreadable with why), newest first, ten a page with Older and Newer,
  never more than ten files read; a read that writes nothing.
- **History** has a row per collection: who and how verified, what the snapshot holds, or
  why it kept nothing; a device's History tab draws none.
- **A record that cannot be read** is never written over, and the card and History say so.
"""
import json
import os
from html import unescape

import pytest

from modules import history_sources as H
from modules.sdn import analyst as AN
from modules.sdn import connections as C
from tests.ai_person import PERSON
from tests.conftest import TEST_PERSON
from tests.test_sdn_analyst import NET, LabRyu, collect, world  # noqa: F401 (the fixture)
from tests.test_sdn_connections import networks  # noqa: F401 (the fixture)

T0 = 1_794_000_000                       # the recorded collection's own time


def _iso(epoch):
    import time
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def _job(session=None, **kw):
    session = session or LabRyu()
    return AN.collect_job(NET, sleep=lambda s: None, announce=False, now=lambda: float(T0),
                          driver=lambda net, name: C.driver_for(net, name, session=session),
                          **kw)


def _keep(hours):
    """The recorded collection kept as it would have been *hours* after the first: its time
    the one edit, its file's write time its collection's."""
    got, _s = collect(links=True)
    snap = AN.build_snapshot(NET, dict(got, collected_at=_iso(T0 + 3600 * hours)), by=PERSON)
    AN.save_snapshot(NET, snap)
    path = os.path.join(AN._dir(NET), "snapshots", f"{snap['id']}.json")
    os.utime(path, (T0 + 3600 * hours, T0 + 3600 * hours))
    return snap


def _ctx(device=""):
    from modules.nsot import listref
    return {"device": device, "ref": listref.resolve(NET), "limit": 50, "since": None,
            "until": None, "members": None}


def _tree(folder):
    out = {}
    for base, _dirs, files in os.walk(folder):
        for name in files:
            path = os.path.join(base, name)
            with open(path, "rb") as fh:
                out[os.path.relpath(path, folder)] = fh.read()
    return out


@pytest.fixture
def client(world, monkeypatch):  # noqa: F811
    """The app, Collect now's job run in the request over the recorded Ryu."""
    import app as APP

    session = LabRyu()
    monkeypatch.setattr(AN, "_spawn", lambda fn: fn())
    monkeypatch.setattr(AN, "collect_job", (lambda real: lambda network, **kw: real(
        network, sleep=lambda s: None, announce=False,
        driver=lambda net, name: C.driver_for(net, name, session=session), **kw))(AN.collect_job))
    return APP.app.test_client()


def _html(r):
    return unescape(r.get_data(as_text=True))


# ── the record of collections, and History ──────────────────────────────────────────────────

def test_each_collection_is_recorded_with_who_how_verified_and_what_it_holds(world):  # noqa: F811
    got = _job(actor=PERSON, actor_verified="access")
    assert got["ok"]
    snap = got["snapshot"]
    held = AN.counts(snap)
    assert held["switches"] == 5 and 0 < held["flows"] <= held["flows_read"]
    assert AN.collections(NET) == {"state": "ok", "error": "", "rows": [{
        "at": _iso(T0), "by": PERSON, "by_verified": "access", "outcome": "kept",
        "snapshot": snap["id"], "collected_at": snap["collected_at"], "state": snap["state"],
        **held}]}
    failed = _job(LabRyu(fail={"/stats/switches"}), actor="unverified", actor_verified="none")
    assert not failed["ok"]
    kept, lost = AN.collections(NET)["rows"]
    assert (lost["outcome"], lost["by"], lost["by_verified"]) == ("failed", "unverified", "none")
    assert lost["error"] == failed["error"] and "snapshot" not in lost
    assert AN.view(NET)["snapshot"]["flows"] == held["flows"]


def test_history_has_a_row_per_collection_naming_who_and_how_verified(world):  # noqa: F811
    snap = _job(actor=PERSON, actor_verified="access")["snapshot"]
    _job(LabRyu(fail={"/stats/switches"}), actor="unverified", actor_verified="none")
    held = AN.counts(snap)
    ok, bad = H.sdn_collections(_ctx())["events"]
    words = f"5 switches, {held['flows']} flows"
    if held["flows_read"] != held["flows"]:
        words += f" of the {held['flows_read']} read"
    assert ok["what"] == f"SDN collection kept a snapshot: {words}"
    assert (ok["kind"], ok["who"], ok["outcome"], ok["devices"]) == ("sdn", PERSON, "kept", [])
    record = dict(ok["record"])
    assert record["Snapshot"] == snap["id"] and record["Verified by"] == "access"
    assert record["Collected"] == snap["collected_at"] and record["Switches"] == 5
    assert ok["record_closed"] is True, "the id sits under Details for the record"
    assert bad["what"] == "SDN collection kept nothing"
    assert bad["who"] == "unverified (not verified)", "never a bare name (C3023's gap)"
    assert bad["detail"].startswith("the collection read no switch") and bad["outcome"] == \
        "failed"
    assert H.sdn_collections(_ctx("ovs1"))["events"] == [], "about no one device"
    assert "sdn_collections" in H.SOURCES and H.SOURCE_KINDS["sdn_collections"] == ("sdn",)
    from modules import operation_stages
    assert operation_stages.HISTORY["sdn_analyse_v2.collect"] == ("sdn_collections",)


def test_the_history_page_draws_the_collection_as_the_person_who_pressed(client):
    r = client.post("/v2/sdn/analyse/collect", data={"list": NET}, headers={"HX-Request": "true"})
    assert r.status_code == 200
    (row,) = AN.collections(NET)["rows"]
    assert (row["by"], row["by_verified"], row["outcome"]) == (TEST_PERSON, "access", "kept")
    page = _html(client.get(f"/v2/history?list={NET}&kind=sdn"))
    assert "SDN collection kept a snapshot: 5 switches, " in page
    assert row["snapshot"] in page, "under the row's Details for the record"


# ── the card ────────────────────────────────────────────────────────────────────────────────

def test_the_card_names_the_snapshot_by_its_id_and_counts_the_kept(client):
    r = client.post("/v2/sdn/analyse/collect", data={"list": NET}, headers={"HX-Request": "true"})
    html = _html(r)
    snap = AN.latest_snapshot(NET)
    held = AN.counts(snap)
    when = snap["collected_at"].replace("T", " ").replace("Z", " UTC")
    assert f'Snapshot <code class="mono">{snap["id"]}</code>' in html, "the id as text"
    assert f'data-copy="{snap["id"]}"' in html and ">Copy</button>" in html
    assert f'collected <time datetime="{snap["collected_at"]}">{when}</time> by {TEST_PERSON}' \
        in html
    assert f": 5 switches, {held['flows']} flow" in html
    assert "Kept snapshots (1), the newest collected " in html
    assert ('hx-get="/v2/sdn/analyse/snapshots?list=Default" hx-trigger="toggle once" '
            'hx-target="find .sdn-an-kept-rows"') in html
    assert "<details class=\"sdn-an-kept\" data-keep=\"sdn-an-kept\" hx-get" in html, \
        "collapsed: no open attribute"
    assert "sdn-an-kept-tbl" not in html, "its rows are asked when it is opened"
    # The press's effect, read again and not only its own answer: the snapshot it kept is the
    # one row the kept list holds.
    again = _html(client.get(f"/v2/sdn/analyse/snapshots?list={NET}"))
    assert again.count(snap["id"]) >= 1 and "Showing 1 to 1 of 1" in again, again[:400]


def test_a_view_of_the_card_reads_no_snapshot_file(world, monkeypatch):  # noqa: F811
    for hour in range(3):
        _keep(hour)
    read = []
    real = AN._read_json
    monkeypatch.setattr(AN, "_read_json", lambda path: read.append(path) or real(path))
    view = AN.view(NET)
    assert view["kept"] == {"count": 3, "error": ""} and view["unrecorded"] == ""
    assert [p for p in read if f"{os.sep}snapshots{os.sep}" in p] == []
    assert AN.kept("Branch") == {"count": 0, "error": ""}, "a network that keeps none"


# ── the list ────────────────────────────────────────────────────────────────────────────────

def test_the_list_draws_each_snapshot_s_id_time_counts_and_seal(client):
    first, second, third = _keep(0), _keep(1), _keep(2)
    folder = os.path.join(AN._dir(NET), "snapshots")
    path = os.path.join(folder, f"{second['id']}.json")
    kept = json.loads(open(path, encoding="utf-8").read())
    kept["switches"][0]["name"] = "edited"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(kept, fh)
    os.utime(path, (T0 + 3600, T0 + 3600))
    with open(os.path.join(folder, f"{first['id']}.json"), "w", encoding="utf-8") as fh:
        fh.write("{not json")
    os.utime(os.path.join(folder, f"{first['id']}.json"), (T0, T0))
    before = _tree(AN._dir(NET))
    page = AN.kept_page(NET)
    assert [(r["id"], r["seal"]) for r in page["rows"]] == [
        (third["id"], "holds"), (second["id"], "broken"), (first["id"], "unreadable")]
    held = AN.counts(third)
    assert page["rows"][0] == {"id": third["id"], "collected_at": _iso(T0 + 7200), "by": PERSON,
                               "seal": "holds", "error": "", **held}
    assert page["rows"][2]["switches"] is None and "JSONDecodeError" in page["rows"][2]["error"]
    assert (page["count"], page["shown"], page["older"], page["newer"]) == (3, 3, None, None)
    r = client.get(f"/v2/sdn/analyse/snapshots?list={NET}")
    html = _html(r)
    assert r.status_code == 200 and "Showing 1 to 3 of 3, newest first." in html
    assert html.index(third["id"]) < html.index(second["id"]) < html.index(first["id"])
    assert f'<code class="mono">{third["id"]}</code>' in html
    assert f'data-copy="{third["id"]}"' in html
    assert f'<time datetime="{_iso(T0 + 7200)}">{_iso(T0 + 7200)[:19].replace("T", " ")}</time>' \
        in html
    assert f'<td data-l="Switches">5</td>' in html
    assert f'<td data-l="Flows">{held["flows"]}' in html
    assert 'data-seal="holds"' in html and ">holds<" in html
    assert ">broken<" in html and ("it changed since it was kept, so Analyse and the "
                                   "evaluation refuse it") in html
    assert ">unreadable<" in html and "JSONDecodeError" in html and ">not read<" in html
    assert "Older" not in html and "Newer" not in html
    assert _tree(AN._dir(NET)) == before, "a read: nothing is written"
    # The seal the list draws is the one Analyse holds a snapshot to.
    assert AN.snapshot(NET, third["id"])["ok"] and not AN.snapshot(NET, second["id"])["ok"]


def test_many_snapshots_are_a_page_of_ten_and_no_more_files_are_read(client, monkeypatch):
    snaps = [_keep(hour) for hour in range(12)]
    read = []
    real = AN._read_json
    monkeypatch.setattr(AN, "_read_json", lambda path: read.append(path) or real(path))
    page = AN.kept_page(NET)
    assert [r["id"] for r in page["rows"]] == [s["id"] for s in reversed(snaps[2:])]
    assert (page["count"], page["shown"], page["older"], page["newer"]) == (12, 10, 10, None)
    assert len(read) == AN.KEPT_PAGE == 10, "ten files read for twelve kept"
    html = _html(client.get(f"/v2/sdn/analyse/snapshots?list={NET}"))
    assert "Showing 1 to 10 of 12, newest first." in html
    assert 'hx-get="/v2/sdn/analyse/snapshots?list=Default&start=10"' in html and "Older" in html
    assert "Newer" not in html and snaps[0]["id"] not in html
    older = _html(client.get(f"/v2/sdn/analyse/snapshots?list={NET}&start=10"))
    assert "Showing 11 to 12 of 12, newest first." in older
    assert older.index(snaps[1]["id"]) < older.index(snaps[0]["id"])
    assert 'hx-get="/v2/sdn/analyse/snapshots?list=Default&start=0"' in older and "Newer" in older
    assert "Older" not in older
    # A start that is no page's is the page that holds it; one past the end, the last page.
    assert AN.kept_page(NET, 13)["start"] == 10 and AN.kept_page(NET, 999)["start"] == 10
    assert _html(client.get(f"/v2/sdn/analyse/snapshots?list={NET}&start=x")).count(
        "<tr data-seal=") == 10
    assert "No snapshot is kept for Branch yet" in _html(
        client.get("/v2/sdn/analyse/snapshots?list=Branch"))


def test_a_file_that_is_no_snapshot_is_said_and_the_page_still_draws(world):  # noqa: F811
    good = _keep(0)
    folder = os.path.join(AN._dir(NET), "snapshots")
    for name, text, hour in (("snap-00000000000000aa.json", "[]", 1),
                             ("snap-00000000000000bb.json", '{"switches": [1]}', 2)):
        with open(os.path.join(folder, name), "w", encoding="utf-8") as fh:
            fh.write(text)
        os.utime(os.path.join(folder, name), (T0 + 3600 * hour, T0 + 3600 * hour))
    rows = AN.kept_page(NET)["rows"]
    assert [(r["id"], r["seal"]) for r in rows] == [
        ("snap-00000000000000bb", "unreadable"), ("snap-00000000000000aa", "unreadable"),
        (good["id"], "holds")]
    assert rows[0]["error"] == ("snap-00000000000000bb.json: not a snapshot's shape "
                                "(AttributeError)") and rows[0]["switches"] is None
    assert rows[1]["error"] == "snap-00000000000000aa.json: not a snapshot"
    assert AN.kept(NET)["count"] == 3, "counted as kept files, each said for what it is"


def test_a_snapshot_kept_before_collections_were_recorded_is_listed_with_no_row(world):  # noqa: F811
    old = _keep(0)
    assert AN.collections(NET) == {"state": "absent", "rows": [], "error": ""}
    assert H.sdn_collections(_ctx())["events"] == []
    assert [r["id"] for r in AN.kept_page(NET)["rows"]] == [old["id"]]


# ── a record that cannot be read ────────────────────────────────────────────────────────────

def test_an_unreadable_record_is_not_written_over_and_is_said(world):  # noqa: F811
    assert _job(actor=PERSON, actor_verified="access")["ok"]
    path = os.path.join(AN._dir(NET), "collections.json")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("{not json")
    assert _job(actor=PERSON, actor_verified="access")["ok"], "the snapshot is still kept"
    with open(path, encoding="utf-8") as fh:
        assert fh.read() == "{not json", "never written over"
    said = AN.view(NET)["unrecorded"]
    assert said.startswith("the record of collections cannot be read (collections.json: "
                           "JSONDecodeError") and said.endswith("so it is not written over")
    assert AN.collections(NET)["state"] == "unreadable"
    (error,) = H.sdn_collections(_ctx())["errors"]
    assert error.startswith("the SDN collections could not be read: collections.json: ")
    import app as APP
    html = _html(APP.app.test_client().get(f"/v2/sdn/flows?list={NET}"))
    assert "The last collection could not be recorded for History: the record of " \
           "collections cannot be read" in html
    os.remove(path)
    assert _job(actor=PERSON, actor_verified="access")["ok"]
    assert AN.view(NET)["unrecorded"] == "" and len(AN.collections(NET)["rows"]) == 1
