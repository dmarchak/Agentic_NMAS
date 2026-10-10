"""Credentials › Profiles on v2 (CUTOVER's "Credential profiles", the board drawn 2026-10-10 under
the Phase 7 mode), on a credential store and change record in this test's own folder, through the
real routes, the real store (`credentials.save_profile`, `delete_profile`, `resolve`) and the
real History source.

- the tab says the resolver's order; with no store, that no profile is set;
- Add a profile saves a role profile as the verified person: the resolver gives it to a device
  with that role, the change is recorded (who, which, the fields) with no value, and no response
  carries the password;
- a profile under a name the resolver never reads says so on its row;
- Edit… keeps every field left empty, and records only what it set;
- a second profile of the same name, a new one without its password, and an edit that changes
  nothing are refused, nothing written;
- Delete… removes it and records it, and the device's login falls to the next source;
- an unreadable store is its own state, offering no Add;
- a request that is no person saves nothing;
- History's Credential profiles source draws each change.
"""

import json
import re

import pytest

PW, PW2, EN = "Prof-Pass-5531", "Prof-Pass-7720", "Prof-Enable-118"


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr("modules.credentials._FILE", str(tmp_path / "credential_profiles.json"))
    monkeypatch.setattr("modules.config.DATA_DIR", str(tmp_path))
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
    # The page's top bar names the network it was opened from.
    (tmp_path / "lab").mkdir()
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(tmp_path / "lab"))
    import app as A
    return {"client": A.app.test_client(), "dir": tmp_path}


def _changes(store):
    path = store["dir"] / "credential_changes.jsonl"
    return [json.loads(l) for l in path.read_text().splitlines()] if path.exists() else []


def _add(store, **over):
    body = {"kind": "role", "value": "router", "username": "netops", "password": PW,
            "secret": ""}
    body.update(over)
    return store["client"].post("/v2/credentials/profiles", data=body)


def test_the_tab_says_the_order_and_that_none_is_set(store):
    html = store["client"].get("/v2/credentials/profiles?list=Lab").get_data(as_text=True)
    assert 'aria-current="page">Profiles</a>' in html
    assert "then a profile for its <strong>role</strong>" in html
    assert "No profile is set (the store does not exist yet)" in html
    assert "Add a profile…" in html


def test_add_saves_records_and_resolves_without_a_value_returned(store):
    from modules import credentials
    r = _add(store, secret=EN)
    html = r.get_data(as_text=True)
    assert r.status_code == 200, html[:400]
    assert "Saved role:router" in html and "username, password, secret set" in html
    assert PW not in html and EN not in html
    got = credentials.resolve("192.0.2.40", role="router")
    assert got["source"] == "profile:role:router" and got["password"] == PW
    (row,) = _changes(store)
    assert row["action"] == "saved" and row["profile"] == "role:router"
    assert row["fields"] == ["username", "password", "secret"]
    assert row["actor"] == "test-person@example.invalid"
    raw = (store["dir"] / "credential_changes.jsonl").read_text()
    assert PW not in raw and EN not in raw
    table = store["client"].get("/v2/credentials/profiles/region").get_data(as_text=True)
    assert "every device with the role router" in table and PW not in table


def test_a_name_the_resolver_never_reads_says_so(store):
    from modules import credentials
    credentials.save_profile("lab-admins", username="x", password=PW)
    html = store["client"].get("/v2/credentials/profiles/region").get_data(as_text=True)
    row = re.search(r'<th scope="row" class="mono">lab-admins</th>.*?</tr>', html, re.S).group(0)
    assert "read by nothing" in row


def test_edit_keeps_what_is_left_empty_and_records_only_what_it_set(store):
    from modules import credentials
    _add(store)
    r = store["client"].post("/v2/credentials/profiles",
                             data={"name": "role:router", "username": "netops2",
                                   "password": "", "secret": ""})
    assert r.status_code == 200 and "Saved role:router" in r.get_data(as_text=True)
    got = credentials.resolve("192.0.2.40", role="router")
    assert got["username"] == "netops2" and got["password"] == PW
    assert _changes(store)[-1]["fields"] == ["username"]


@pytest.mark.parametrize("case,body,words", [
    ("twice", {}, "a profile named role:router exists"),
    ("no password", {"value": "switch", "password": ""}, "needs its username and its password"),
    ("a spaced site", {"kind": "site", "value": "two words"}, "as one word"),
])
def test_refusals_write_nothing(store, case, body, words):
    if case == "twice":
        _add(store)
    before = (store["dir"] / "credential_profiles.json").read_text() \
        if (store["dir"] / "credential_profiles.json").exists() else None
    n = len(_changes(store))
    r = _add(store, **body)
    assert r.status_code == 400 and words in r.get_data(as_text=True)
    after = (store["dir"] / "credential_profiles.json").read_text() \
        if (store["dir"] / "credential_profiles.json").exists() else None
    assert after == before and len(_changes(store)) == n


def test_an_edit_that_changes_nothing_is_refused(store):
    _add(store)
    r = store["client"].post("/v2/credentials/profiles",
                             data={"name": "role:router", "username": "netops",
                                   "password": "", "secret": ""})
    assert r.status_code == 400 and "nothing was changed" in r.get_data(as_text=True)


def test_delete_records_and_the_login_falls_to_the_next_source(store):
    from modules import credentials
    _add(store)
    _add(store, kind="default", value="", username="fallback", password=PW2)
    form = store["client"].get("/v2/credentials/profiles/delete?name=role:router") \
        .get_data(as_text=True)
    assert "every device with the role router" in form and "next source" in form
    r = store["client"].post("/v2/credentials/profiles/delete", data={"name": "role:router"})
    assert r.status_code == 200 and "Deleted role:router" in r.get_data(as_text=True)
    got = credentials.resolve("192.0.2.40", role="router")
    assert got["source"] == "profile:default" and got["username"] == "fallback"
    assert _changes(store)[-1] == {**_changes(store)[-1], "action": "deleted",
                                   "profile": "role:router", "fields": []}


def test_an_unreadable_store_is_its_own_state(store):
    (store["dir"] / "credential_profiles.json").write_text("{not json")
    html = store["client"].get("/v2/credentials/profiles/region").get_data(as_text=True)
    assert "The profiles cannot be read" in html and "Add a profile…" not in html


@pytest.mark.real_identity
def test_no_person_saves_nothing(store):
    r = _add(store)
    assert r.status_code in (401, 403)
    assert not (store["dir"] / "credential_profiles.json").exists() and not _changes(store)


def test_history_draws_each_change(store):
    from modules import history_sources as H
    _add(store)
    out = H.credential_profiles({"device": "", "since": None})
    (e,) = out["events"]
    assert e["kind"] == "credential" and e["what"].startswith("Credential profile role:router")
    assert "username, password set" in e["what"] and e["devices"] == []
    assert PW not in json.dumps(out)
