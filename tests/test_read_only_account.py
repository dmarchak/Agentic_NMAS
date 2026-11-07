"""The read-only device account: the credential chain's read role (board H, artboard N; H28;
docs/HEAL_TO_INTENT.md 19.5, prerequisite 1; `modules/credentials.py`, `modules/nsot/reads.py`,
`modules/connection.py`, `routes/credential_profiles_v2.py`), on a credential store and change
record in this test's own folder; no device (the session is faked at the reads engine's seam).

- **The store:** a profile's read-only account is set by a named person, its password sealed
  (never in the file, never returned, never logged), masked by value for redaction; set again,
  only its password changes; it goes with its profile when the profile is deleted;
- **refused, nothing written, each naming both operands:** a profile that does not exist, the
  deploy account's name or its password, a different name for an account that exists (an
  account is added, never changed), a password outside its shape, no actor;
- **resolution** walks platform, kind, site, default, the first profile carrying one; a profile
  without one is passed over; none resolves to nothing, naming every profile it looked under,
  never the deploy account;
- **the reads engine** signs an `ai_analysis` read in as the read-only account, recording its
  name and the profile, never its password; a device without one is refused by name before any
  session opens; a person's read keeps the deploy account; the read-only session never calls
  `enable()`;
- **credential health** lists each read-only account by its age;
- **the card** on Credentials › Profiles: Set the read-only account…, the save recorded on
  History with the fields and no value, a refusal in place that echoes no password.
"""

import json
import logging
import os

import pytest

from modules import credentials as C

DEPLOY_PW, RO_PW, RO_PW2 = "Deploy-Pass-5531", "ReadOnly-Pass-8812", "ReadOnly-Pass-9934"
DEVICES = [{"hostname": "r1", "ip": "192.0.2.11", "device_type": "cisco_xe", "role": "router",
            "_platform": "cisco-ios-xe", "_site": "lab"},
           {"hostname": "s1", "ip": "192.0.2.21", "device_type": "cisco_ios", "role": "switch",
            "_platform": "cisco-ios", "_site": "lab"},
           {"hostname": "r6", "ip": "2001:db8::6", "device_type": "cisco_xe", "role": "router",
            "_platform": "cisco-ios-xe", "_site": "lab"}]


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "_FILE", str(tmp_path / "credential_profiles.json"))
    monkeypatch.setattr("modules.config.DATA_DIR", str(tmp_path))
    return tmp_path


def _profiles(*names):
    for n in names:
        C.save_profile(n, username="netops", password=DEPLOY_PW)


def _set(profile="default", username="mercury-ro", password=RO_PW, **kw):
    return C.set_read_account(profile, username, password, actor=kw.pop("actor", "op@x"),
                              verified="access", **kw)


def _raw(store):
    return (store / "credential_profiles.json").read_text(encoding="utf-8")


class TestTheStore:
    def test_added_sealed_and_never_returned(self, store, caplog):
        _profiles("default")
        with caplog.at_level(logging.DEBUG):
            got = _set()
        assert got == {"ok": True, "profile": "default", "username": "mercury-ro",
                       "replaced": False}
        assert RO_PW not in _raw(store), "sealed at rest"
        assert RO_PW not in caplog.text, "never logged"
        info = C.read_accounts()["default"]
        assert info["username"] == "mercury-ro" and info["password_set"] is True
        assert info["set_by"] == "op@x" and info["set_verified"] == "access"
        assert RO_PW not in json.dumps(info)
        # Masked by value wherever a device could echo it.
        assert C.device_credential_values()[RO_PW] == "device-password"

    def test_set_again_replaces_the_password_keeping_the_name(self, store):
        _profiles("default")
        _set()
        got = _set(username="", password=RO_PW2)
        assert got["replaced"] is True and got["username"] == "mercury-ro"
        assert C.resolve_read()["password"] == RO_PW2

    def test_it_goes_with_its_profile(self, store):
        _profiles("default")
        _set()
        assert C.delete_profile("default") == {"ok": True, "read_account_removed": True}
        assert C.read_accounts() == {} and RO_PW not in C.device_credential_values()

    def test_a_profile_save_keeps_it(self, store):
        """A profile's save rewrites its entry whole; the read account is held beside it."""
        _profiles("default")
        _set()
        C.save_profile("default", username="netops2", password="")
        assert C.read_accounts()["default"]["username"] == "mercury-ro"


@pytest.mark.parametrize("kw,said", [
    (dict(profile="role:router"), "no profile is named 'role:router': a read-only account "
                                  "belongs to a profile, and the profiles are default"),
    (dict(username="netops"), "the read-only account's name netops is default's deploy "
                              "account's: the AI's reads must never sign in as the account "
                              "that changes devices"),
    (dict(password=DEPLOY_PW), "the password typed is default's deploy account's password: two "
                               "accounts with one password are one account; type another"),
    (dict(password="short"), "the password is 5 characters; it must be 8 to 128 printable ASCII "
                             "characters with no space (it reaches the device's command line)"),
    (dict(password="has a space in it"), "the password is 17 characters; it must be 8 to 128 "
                                         "printable ASCII characters with no space (it reaches "
                                         "the device's command line)"),
    (dict(password=""), "a read-only account needs its password, typed here: none was given"),
    (dict(username="1bad"), "the account name '1bad' is not one word of letters, digits, dot, "
                            "dash and underscore, starting with a letter or underscore, at most "
                            "32 characters"),
    (dict(actor=""), "a read-only account is set by a named person, and no actor was given"),
])
def test_refused_with_nothing_written(store, kw, said):
    _profiles("default")
    before = _raw(store)
    with pytest.raises(C.ReadAccountRefused) as exc:
        _set(**kw)
    assert str(exc.value) == said
    assert _raw(store) == before


def test_an_account_is_added_never_changed(store):
    _profiles("default")
    _set()
    before = _raw(store)
    with pytest.raises(C.ReadAccountRefused) as exc:
        _set(username="other-ro", password=RO_PW2)
    assert str(exc.value) == ("default's read-only account is mercury-ro, and the form named "
                              "other-ro: an account is added, never changed, so its name stays; "
                              "Replace its password… keeps the name")
    assert _raw(store) == before


class TestResolution:
    def test_the_order_is_platform_kind_site_default(self, store):
        _profiles("platform:cisco-ios-xe", "role:router", "site:lab", "default")
        for name in ("default", "site:lab", "role:router", "platform:cisco-ios-xe"):
            _set(profile=name, username=f"ro-{name.replace(':', '-')}")
            got = C.resolve_read(role="router", site="lab", platform="cisco-ios-xe")
            assert got["ok"] and got["source"] == f"read-account:profile:{name}"
            assert got["username"] == f"ro-{name.replace(':', '-')}"

    def test_a_profile_without_one_is_passed_over(self, store):
        _profiles("platform:cisco-ios-xe", "default")
        _set(profile="default")
        got = C.resolve_read(role="router", site="lab", platform="cisco-ios-xe")
        assert got["source"] == "read-account:profile:default"

    def test_none_resolves_to_nothing_never_the_deploy_account(self, store):
        _profiles("default")
        got = C.resolve_read(role="router", site="lab", platform="cisco-ios-xe")
        assert got == {"ok": False, "username": "", "password": "", "source": "", "error": (
            "no read-only account: none of the profiles it is looked for under "
            "(platform:cisco-ios-xe, role:router, site:lab, default) carries one")}
        assert C.resolve("192.0.2.11", role="router")["ok"], "the deploy account exists"

    def test_an_unreadable_store_resolves_nothing(self, store):
        _profiles("default")
        _set()
        (store / "credential_profiles.json").write_text("{not json", encoding="utf-8")
        assert C.resolve_read()["ok"] is False


# ── The reads engine ─────────────────────────────────────────────────────────────────────────

class Session:
    """The engine's seam: what each session signed in as, and the answers."""

    def __init__(self):
        self.signed = []

    def __call__(self, dev, fn):
        from modules.device import decrypt_field
        self.signed.append({"host": dev["hostname"], "username": dev.get("username"),
                            "password": decrypt_field(dev["password"]) if dev.get("password")
                            else ""})
        return fn(self)

    def answer(self, command):
        return f"{command}: answered"


@pytest.fixture
def lab(store, monkeypatch, tmp_path):
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(tmp_path / name))
    monkeypatch.setattr("modules.device.load_saved_devices",
                        lambda path: [dict(d) for d in DEVICES])
    monkeypatch.setattr("modules.commands.run_device_command", lambda conn, c: conn.answer(c))
    monkeypatch.setattr("modules.list_settings.value",
                        lambda ln, key, default=None: default)
    _profiles("role:router", "default")
    return tmp_path


def _routers_read_account():
    """The routers' role profile carries the read-only account. Set in each test's own body
    (never the fixture), so a parent without the account's code fails the test itself."""
    _set(profile="role:router")


def _read(hosts, by, session):
    from modules.nsot import reads
    return reads.run("Lab", hosts, ["show version"], "admin@x", by=by, session=session)


def test_an_ai_read_signs_in_as_the_read_only_account_ipv4_and_ipv6(lab):
    _routers_read_account()
    s = Session()
    rec = _read(["r1", "r6"], "ai_analysis", s)
    assert {x["host"] for x in s.signed} == {"r1", "r6"}
    for x in s.signed:
        assert x["username"] == "mercury-ro" and x["password"] == RO_PW
    for host in ("r1", "r6"):
        out = rec["results"][host]
        assert out["state"] == "answered"
        assert out["signed_in_as"] == {"username": "mercury-ro",
                                       "source": "read-account:profile:role:router"}
    from modules.nsot import reads
    assert reads.actor_words(rec) == ("the AI analysis, turned on by admin@x, as the read-only "
                                      "account")
    assert RO_PW not in json.dumps(rec)
    with open(os.path.join(str(lab), "Lab", "reads", f"{rec['id']}.json"),
              encoding="utf-8") as fh:
        assert RO_PW not in fh.read()


def test_a_device_without_one_is_refused_by_name_and_no_session_opens(lab):
    """s1 is a switch: no profile on its chain carries a read-only account."""
    _routers_read_account()
    C.delete_profile("default")
    s = Session()
    rec = _read(["s1", "r1"], "ai_analysis", s)
    assert [x["host"] for x in s.signed] == ["r1"], "no session to s1"
    out = rec["results"]["s1"]
    assert out["state"] == "failed"
    assert out["why"] == ("no read-only account for s1: no read-only account: none of the "
                          "profiles it is looked for under (platform:cisco-ios, role:switch, "
                          "site:lab, default) carries one. Nothing was sent")


def test_a_persons_read_keeps_the_device_login(lab):
    _routers_read_account()
    s = Session()
    rec = _read(["r1"], "person", s)
    assert s.signed[0]["username"] is None, "the inventory's own login, untouched"
    assert "signed_in_as" not in rec["results"]["r1"]


def test_the_read_only_session_never_escalates(monkeypatch):
    from modules import connection

    seen = {}

    class Conn:
        def enable(self):
            raise AssertionError("enable() called on the read-only account's session")

        def disconnect(self):
            seen["closed"] = True

    def fake_open(params, *, owner="", plain=False, **kw):
        seen.update(plain=plain, owner=owner, username=params.get("username"))
        return Conn()

    monkeypatch.setattr(connection, "open_ssh", fake_open)
    monkeypatch.setattr(connection, "stored_connection_params",
                        lambda dev: {"ip": dev["ip"], "username": dev["username"]})
    got = connection.with_plain_connection({"ip": "2001:db8::6", "username": "mercury-ro"},
                                           lambda conn: "read")
    assert got == "read" and seen == {"plain": True, "owner": "reads:read-only account",
                                      "username": "mercury-ro", "closed": True}


def test_credential_health_lists_each_read_only_account_by_age(store):
    from modules.readers import credential_health as CH
    _profiles("default")
    _set()
    set_at = C.read_accounts()["default"]["set_at"]
    (e,) = CH.read_account_ages(set_at + 10 * CH.DAY)
    assert e["id"] == "read-account:default" and e["state"] == "ok" and e["kind"] == "age"
    assert e["label"] == "default's read-only account mercury-ro"
    (old,) = CH.read_account_ages(set_at + (CH.MAX_AGE_DAYS + 1) * CH.DAY)
    assert old["state"] == "warning"
    assert RO_PW not in json.dumps(e)


# ── The card ─────────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def page(store, tmp_path, monkeypatch):
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
    (tmp_path / "lab").mkdir()
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(tmp_path / "lab"))
    _profiles("default")
    import app as A
    return A.app.test_client()


def _changes(store):
    path = store / "credential_changes.jsonl"
    return [json.loads(l) for l in path.read_text().splitlines()] if path.exists() else []


def test_the_card_sets_the_account_records_it_and_returns_no_value(page, store):
    html = page.get("/v2/credentials/profiles?list=Lab").get_data(as_text=True)
    assert 'id="cred-read"' in html and "Set the read-only account…" in html
    form = page.get("/v2/credentials/profiles/read-account/form?name=default").get_data(
        as_text=True)
    assert 'name="password" type="password"' in form and 'name="username"' in form
    r = page.post("/v2/credentials/profiles/read-account",
                  data={"name": "default", "username": "mercury-ro", "password": RO_PW})
    html = r.get_data(as_text=True)
    assert r.status_code == 200, html[:300]
    assert "default's read-only account mercury-ro: added" in html and RO_PW not in html
    (row,) = _changes(store)
    assert row["action"] == "read_account_added" and row["profile"] == "default"
    assert row["fields"] == ["read-only account name", "read-only account password"]
    assert RO_PW not in json.dumps(row)
    from modules import history_sources as H
    (e,) = H.credential_profiles({"device": "", "since": None})["events"]
    assert e["what"] == "Credential profile default's read-only account added"
    again = page.get("/v2/credentials/profiles/read-account").get_data(as_text=True)
    assert "Replace its password…" in again and RO_PW not in again


def test_a_refusal_is_drawn_in_place_and_echoes_no_password(page, store):
    r = page.post("/v2/credentials/profiles/read-account",
                  data={"name": "default", "username": "netops", "password": RO_PW})
    html = r.get_data(as_text=True)
    assert r.status_code == 400 and "Not saved:" in html
    assert "is default&#39;s deploy account&#39;s" in html or "is default's deploy" in html
    assert RO_PW not in html and C.read_accounts() == {} and not _changes(store)
