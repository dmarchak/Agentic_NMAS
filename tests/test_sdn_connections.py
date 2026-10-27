"""A network's SDN controller connections (`modules/sdn/connections.py`, PHASE8_PLAN 17.1 S2),
on a temporary store with three networks (Default; Branch with its own list; Lab-3 inheriting
every other group from Default), the drivers over S1's fake HTTP layer and Ryu's captured
answers.

- **The model and where it is kept:** a connection's fields saved in the network setting
  `sdn_controllers` through `list_settings` (Default's in the global file, Branch's in its own
  store), each network's own and never inherited (C1841: Lab-3, inheriting every other group,
  reads no controller of Default's, standalone or not); the schema refuses any field it does
  not name, so no credential can be in it; the group is drawn by no generic Settings card. None
  by default.
- **Credentials:** encrypted in the credential store, keyed by the network that holds the
  list; never in any read (the list, a driver's connection, Test's answer, the health
  probe, the log); a blank on save keeps the stored one, `clear_credentials` erases; a token
  typed replaces a user and password; the driver resolves it at each request.
- **Checks:** a built driver's kind, the URL as the driver checks it (IPv4, IPv6 bracketed, a
  name), the southbound address (IPv6 too), own cookies (never in Mercury's range).
- **Writes carry their network** and an actor; a network's first save starts its own list,
  holding only what it saved; a save from a form drawn before another person's change is
  refused naming both values; each recorded with names, never values.
- **Test connection** with the values as typed, before anything is saved, through the driver's
  `test()`; the stored credential when none is typed for a saved connection.
- **More than one per network, counted in the top bar's integrations total** (the
  integrations reader's `controllers`, the strip adding them).
"""
import json
import logging

import pytest

from modules import credentials
from modules import list_settings as L
from modules.sdn import connections as C
from tests.sdn_fakes import Response, Routes, Session, fixture

BASE = "http://192.0.2.10:8080"
BASE6 = "http://[2001:db8::10]:8080"
WITH_PEER = fixture("rest_with_peer.json")
PASSWORD, TOKEN, USER = "Pw-sdn-7731xq", "tok-sdn-55aa9c", "ctl-operator"


@pytest.fixture
def networks(tmp_path, monkeypatch):
    return make_networks(tmp_path, monkeypatch)


def make_networks(tmp_path, monkeypatch):
    """The three networks' store under *tmp_path* (the fixture's body, for a caller that is not
    a test of this module: tests/test_board_shots.py's SDN shots)."""
    from modules import config, device

    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "LISTS_DIR", str(tmp_path / "lists"))
    settings = tmp_path / "user_settings.json"
    settings.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(config, "USER_SETTINGS_FILE", str(settings))
    registry = tmp_path / "device_lists.json"
    registry.write_text(json.dumps({"current_list": "Default", "lists": {
        "Default": "default", "Branch": "branch", "Lab-3": "lab-3"}}), encoding="utf-8")
    monkeypatch.setattr(device, "DEVICE_LISTS_CONFIG", str(registry))
    monkeypatch.setattr(credentials, "_FILE", str(tmp_path / "credential_profiles.json"))
    return tmp_path


def values(**kw):
    out = {"name": "ctl-1", "kind": "ryu", "url": BASE}
    out.update(kw)
    return out


def save(network="Default", **kw):
    return C.save_connection(network, values(**kw), actor="op@example.com")


def everything_read(network):
    """Every read that could carry a credential, as one text."""
    parts = [json.dumps(C.connections(network))]
    for conn in C.connections(network)["connections"]:
        got = C.driver_for(network, conn["name"])
        parts.append(json.dumps(got.get("connection")))
        parts.append(repr(got.get("driver")))
    return "\n".join(parts)


# ───────────────────────────────────────────────────────────────────────────── the model

@pytest.mark.usefixtures("networks")
class TestTheModel:
    def test_none_by_default_reproduces_before_the_setting(self):
        from modules.settings_schema import DEFAULTS
        assert DEFAULTS["sdn_controllers"] == []
        assert C.connections("Default")["state"] == "none"
        assert C.connections("Branch") == {
            "ok": True, "network": "Branch", "state": "none", "owner": "branch",
            "connections": [], "error": ""}

    def test_a_saved_connection_reads_back_whole(self):
        got = save(own_cookies=[0, "0x10"], southbound="192.0.2.10:6653", timeout=7,
                   verify_tls=False)
        assert got["created"] and got["written"] == sorted(C.FIELDS)
        (conn,) = C.connections("Default")["connections"]
        assert conn == {"name": "ctl-1", "kind": "ryu", "label": "Ryu", "status": "built",
                        "url": BASE, "verify_tls": False, "timeout": 7.0,
                        "southbound": "192.0.2.10:6653", "own_cookies": [0, 16],
                        "credentials": {"set": False, "auth": "none"}, "owner": "default"}

    def test_own_cookies_default_to_zero_and_an_empty_list_is_a_choice(self):
        save()
        save(name="ctl-2", own_cookies=[])
        conns = {c["name"]: c for c in C.connections("Default")["connections"]}
        assert conns["ctl-1"]["own_cookies"] == [0] and conns["ctl-2"]["own_cookies"] == []

    def test_more_than_one_per_network_each_kept(self):
        save()
        save(name="ctl-2", url=BASE6)
        assert [c["name"] for c in C.connections("Default")["connections"]] == ["ctl-1", "ctl-2"]

    def test_default_s_list_is_in_the_global_file_and_branch_s_in_its_store(self, networks):
        save()
        save("Branch", name="b-1")
        glob = json.loads((networks / "user_settings.json").read_text())
        assert [c["name"] for c in glob["sdn_controllers"]] == ["ctl-1"]
        own = json.loads((networks / "lists" / "branch" / "settings.json").read_text())
        assert [c["name"] for c in own["values"]["sdn_controllers"]] == ["b-1"]

    @pytest.mark.parametrize("mode", ["inherit", "standalone"])
    def test_a_second_network_reads_no_controller_of_default_s(self, networks, mode):
        """C1841 (the operator, 2026-10-27): SDN controllers are never inherited. Lab-3,
        inheriting every other group from Default (or standalone), has none of Default's: no
        connection, no driver, no probe, and none in the closed loop's read."""
        if mode == "standalone":
            store = __import__("pathlib").Path(L.path("Lab-3"))
            store.parent.mkdir(parents=True, exist_ok=True)
            store.write_text(json.dumps({"mode": "standalone"}), encoding="utf-8")
        save(password=PASSWORD)
        assert L.group_choice(L.load("Lab-3"), "grafana") == (
            "inherit" if mode == "inherit" else "own"), "the network's other groups as set"
        got = C.connections("Lab-3")
        assert got["state"] == "none" and got["connections"] == [] and got["owner"] == "lab_3"
        assert C.driver_for("Lab-3", "ctl-1") == {
            "ok": False, "error": "Lab-3 has no controller connection 'ctl-1'"}
        assert not [p for p in C.health_probes() if "lab_3" in p["name"]]
        from modules.sdn import closed_loop
        assert closed_loop.collect_threat_data("Lab-3", 1.0, sleep=lambda s: None)["state"] \
            == "none"

    def test_a_network_declaring_them_not_applicable_has_none(self, networks):
        store = __import__("pathlib").Path(L.path("Lab-3"))
        store.parent.mkdir(parents=True, exist_ok=True)
        store.write_text(json.dumps({"not_applicable": {"sdn_controllers": {}}}),
                         encoding="utf-8")
        save()
        assert C.connections("Lab-3")["state"] == "not_applicable"

    def test_the_schema_refuses_a_credential_in_the_setting(self):
        bad = [dict(values(), password=PASSWORD)]
        got = L.write("Default", {"sdn_controllers": bad})
        assert not got["ok"] and "password" in got["error"]

    def test_no_generic_settings_card_draws_or_saves_it(self):
        from modules import settings_page
        from modules.settings_scope import network_groups
        assert "sdn_controllers" not in network_groups()
        assert "sdn_controllers" not in settings_page.tab_groups("network")
        with pytest.raises(L.SwitchRefused):
            L.save_values("Branch", "sdn_controllers", {"sdn_controllers": []}, actor="x")

    def test_an_unreadable_store_is_unreadable_never_none(self, networks):
        (networks / "lists" / "branch").mkdir(parents=True)
        (networks / "lists" / "branch" / "settings.json").write_text("{not json")
        got = C.connections("Branch")
        assert got["state"] == "unreadable" and not got["ok"] and "could not be read" in \
            got["error"]


# ───────────────────────────────────────────────────────────────────────────── the checks

@pytest.mark.usefixtures("networks")
class TestTheChecks:
    @pytest.mark.parametrize("url", [BASE, BASE6, "https://controller.example:8443"])
    def test_ipv4_ipv6_and_a_name_are_each_a_url(self, url):
        assert C.check(values(url=url))["ok"]

    @pytest.mark.parametrize("url,words", [
        ("http://2001:db8::10:8080", "not a URL"),
        ("http://user:pw@192.0.2.10:8080", "user part"),
        ("ftp://192.0.2.10", "http or https"),
        ("", "not set")])
    def test_a_url_the_driver_refuses_is_refused_in_its_words(self, url, words):
        got = C.check(values(url=url))
        assert not got["ok"] and words in got["error"]

    @pytest.mark.parametrize("southbound", ["192.0.2.10", "192.0.2.10:6653", "2001:db8::10",
                                            "[2001:db8::10]:6653", "ctl.example:6653", ""])
    def test_a_southbound_address_ipv4_or_ipv6(self, southbound):
        assert C.check(values(southbound=southbound))["ok"]

    @pytest.mark.parametrize("southbound", ["two words", "[2001:db8::10", "x" * 300])
    def test_a_southbound_address_that_is_not_one(self, southbound):
        assert "southbound" in C.check(values(southbound=southbound))["error"]

    def test_a_kind_not_built_or_unknown_is_refused(self):
        assert "not built" in C.check(values(kind="onos"))["error"]
        assert "no controller driver of kind 'nope'" in C.check(values(kind="nope"))["error"]

    def test_an_own_cookie_in_mercury_s_range_is_refused(self):
        from modules.sdn.flow_intent import mercury_cookie
        got = C.check(values(own_cookies=[0, mercury_cookie(5)]))
        assert not got["ok"] and "Mercury's range" in got["error"]

    @pytest.mark.parametrize("name", ["", "-x", "a b", "x" * 64])
    def test_a_name_must_be_a_name(self, name):
        assert "the name" in C.check(values(name=name))["error"]

    def test_a_timeout_out_of_bounds(self):
        assert "timeout" in C.check(values(timeout=0))["error"]
        assert "timeout" in C.check(values(timeout=500))["error"]


# ───────────────────────────────────────────────────────────────────────────── credentials

@pytest.mark.usefixtures("networks")
class TestCredentials:
    def test_stored_encrypted_and_resolved_for_the_driver_only(self, networks):
        save(username=USER, password=PASSWORD)
        raw = (networks / "credential_profiles.json").read_text()
        assert PASSWORD not in raw and USER not in raw and "enc:v1:" in raw
        assert credentials.get_controller_credential("default/ctl-1") == {
            "username": USER, "password": PASSWORD}

    def test_no_read_returns_a_credential(self, caplog):
        caplog.set_level(logging.DEBUG)
        save(username=USER, password=PASSWORD)
        save(name="ctl-2", token=TOKEN)
        text = everything_read("Default") + everything_read("Lab-3")
        text += json.dumps(C.test_connection(values(network="Default"),
                                             session=Routes(WITH_PEER, BASE)))
        text += json.dumps([C._probe("Default", "ctl-1")])
        text += caplog.text
        for secret in (PASSWORD, TOKEN, USER):
            assert secret not in text, secret
        conns = {c["name"]: c for c in C.connections("Default")["connections"]}
        assert conns["ctl-1"]["credentials"] == {"set": True, "auth": "basic"}
        assert conns["ctl-2"]["credentials"] == {"set": True, "auth": "token"}

    def test_a_blank_on_save_keeps_the_stored_one(self):
        save(username=USER, password=PASSWORD)
        got = save(timeout=9)                         # every credential field blank
        assert got["credentials"] == {"state": "kept", "auth": "basic"}
        assert credentials.get_controller_credential("default/ctl-1") == {
            "username": USER, "password": PASSWORD}
        save(password="")                             # an empty string is a blank too
        assert credentials.get_controller_credential("default/ctl-1")["password"] == PASSWORD

    def test_clearing_is_said_by_name(self):
        save(username=USER, password=PASSWORD)
        got = C.save_connection("Default", values(), actor="op", clear_credentials=True)
        assert got["credentials"]["state"] == "cleared"
        assert credentials.get_controller_credential("default/ctl-1") == {}

    def test_a_token_replaces_a_user_and_password_and_both_at_once_is_refused(self):
        save(username=USER, password=PASSWORD)
        save(token=TOKEN)
        assert credentials.get_controller_credential("default/ctl-1") == {"token": TOKEN}
        with pytest.raises(C.ConnectionRefused, match="not both"):
            save(password=PASSWORD, token=TOKEN)

    def test_the_driver_reads_it_at_each_request_never_keeps_it(self):
        save(username=USER, password=PASSWORD)
        sess = Session(Response(200, "[1]"), Response(200, "[1]"))
        drv = C.driver_for("Default", "ctl-1", session=sess)["driver"]
        drv.switches()
        save(password="Pw-changed-9921")
        drv.switches()
        assert [s["auth"] for s in sess.sent] == [(USER, PASSWORD), (USER, "Pw-changed-9921")]
        assert PASSWORD not in repr(vars(drv)) and PASSWORD not in repr(drv.connection)

    def test_a_new_connection_never_takes_up_a_credential_left_under_its_name(self):
        credentials.set_controller_credential("default/ctl-1", password=PASSWORD)
        save()
        assert credentials.get_controller_credential("default/ctl-1") == {}

    def test_removal_clears_it(self):
        save(password=PASSWORD)
        got = C.remove_connection("Default", "ctl-1", actor="op")
        assert got["credential_cleared"] and C.connections("Default")["state"] == "none"
        assert credentials.get_controller_credential("default/ctl-1") == {}
        assert "flow-intent records" in got["survives"]

    def test_a_credential_is_redacted_by_value(self):
        from modules import redact
        save(password=PASSWORD)
        redact.invalidate_cache()
        assert PASSWORD not in redact.redact_text(f"the controller said {PASSWORD}")

    def test_a_failed_list_write_puts_the_credential_back(self, monkeypatch):
        save(password=PASSWORD)
        monkeypatch.setattr(L, "write", lambda *a, **k: {"ok": False, "error": "disk full"})
        with pytest.raises(C.ConnectionRefused, match="disk full"):
            save(timeout=11, password="Pw-new-0001")
        assert credentials.get_controller_credential("default/ctl-1")["password"] == PASSWORD


# ───────────────────────────────────────────────────────────────────────────── writes

@pytest.mark.usefixtures("networks")
class TestWrites:
    def test_a_write_carries_its_network_and_an_actor(self):
        with pytest.raises(C.ConnectionRefused, match="FOR a network"):
            C.save_connection("", values(), actor="op")
        with pytest.raises(C.ConnectionRefused, match="who made it"):
            C.save_connection("Default", values(), actor="")

    def test_a_network_s_first_save_starts_its_own_list(self):
        save(password=PASSWORD)
        got = save("Lab-3", name="lab-1")
        assert "stopped_inheriting" not in got
        lab = C.connections("Lab-3")
        assert lab["owner"] == "lab_3"
        assert [c["name"] for c in lab["connections"]] == ["lab-1"]
        # Default's credential is never the new list's.
        assert credentials.get_controller_credential("lab_3/lab-1") == {}
        assert [c["name"] for c in C.connections("Default")["connections"]] == ["ctl-1"]

    def test_default_s_connection_is_never_removed_from_another_network(self):
        save()
        with pytest.raises(C.ConnectionRefused, match="Lab-3 has no controller connection"):
            C.remove_connection("Lab-3", "ctl-1", actor="op")
        assert [c["name"] for c in C.connections("Default")["connections"]] == ["ctl-1"]

    def test_a_save_from_a_form_drawn_before_another_change_is_refused(self):
        save()
        drawn = {k: v for k, v in C.connections("Default")["connections"][0].items()
                 if k in C.FIELDS}
        C.save_connection("Default", values(url=BASE6), actor="other@example.com")
        with pytest.raises(C.ConnectionRefused, match=r"url is now .*2001:db8::10.*\(this form "
                                                      r"drew .*192\.0\.2\.10"):
            C.save_connection("Default", values(timeout=9), actor="op", loaded=drawn)
        with pytest.raises(C.ConnectionRefused, match="saved since this form was drawn"):
            C.save_connection("Default", values(), actor="op", loaded={})
        assert C.connections("Default")["connections"][0]["url"] == BASE6
        drawn["url"] = BASE6
        assert C.save_connection("Default", values(url=BASE6, timeout=9), actor="op",
                                 loaded=drawn)["written"] == ["timeout"]

    def test_each_save_and_removal_is_recorded_with_names_never_values(self):
        save(password=PASSWORD)
        C.remove_connection("Default", "ctl-1", actor="op")
        rows = L.changes("Default")["rows"]
        assert [r["action"] for r in rows] == ["remove", "create"]
        assert rows[1]["credentials"] == "replaced" and PASSWORD not in json.dumps(rows)

    def test_removing_what_is_not_there_is_refused(self):
        with pytest.raises(C.ConnectionRefused, match="no controller connection 'x'"):
            C.remove_connection("Default", "x", actor="op")


# ───────────────────────────────────────────────────────────────────────────── test connection

@pytest.mark.usefixtures("networks")
class TestTestConnection:
    @pytest.mark.parametrize("url", [BASE, BASE6])
    def test_the_values_as_typed_through_the_driver(self, url):
        got = C.test_connection(values(url=url), session=Routes(WITH_PEER, url))
        assert got == {"ok": True, "error": "", "switches": 1, "version": None,
                       "credentials": "none",
                       "version_note": "Ryu's ofctl_rest reports no version"}
        assert C.connections("Default")["state"] == "none", "nothing was saved"

    def test_a_typed_credential_is_sent(self):
        sess = Session(Response(200, "[]"))
        got = C.test_connection(values(username=USER, password=PASSWORD), session=sess)
        assert got["credentials"] == "typed" and sess.sent[0]["auth"] == (USER, PASSWORD)

    def test_none_typed_for_a_saved_connection_uses_the_stored_one(self):
        save(username=USER, password=PASSWORD)
        sess = Session(Response(200, "[]"))
        got = C.test_connection(values(network="Default", url=BASE6), session=sess)
        assert got["credentials"] == "stored" and sess.sent[0]["auth"] == (USER, PASSWORD)

    def test_a_refused_credential_and_an_unreachable_controller_in_words(self):
        import requests
        got = C.test_connection(values(), session=Session(Response(401, "")))
        assert not got["ok"] and got["refused"] and "refused the tool's credential" in \
            got["error"]
        got = C.test_connection(values(timeout=1), session=Session(
            *[requests.exceptions.ConnectionError("x")] * 3))
        assert not got["ok"] and "could not connect" in got["error"]

    def test_values_that_fail_the_checks_are_never_sent(self):
        sess = Session()
        got = C.test_connection(values(url="ftp://192.0.2.10"), session=sess)
        assert not got["ok"] and sess.sent == []


# ───────────────────────────────────────────────────────────────────────────── the total

@pytest.mark.usefixtures("networks")
class TestTheIntegrationsTotal:
    def _read(self, monkeypatch, answers):
        from modules.readers import integration_health as IH
        from tests.test_integration_health import REG

        real = C.driver_for
        monkeypatch.setattr(C, "driver_for", lambda n, name: real(
            n, name, session=Session(*answers[name])))
        return IH.read(REG)

    def test_each_connection_is_probed_once_and_kept_beside_the_integrations(self, monkeypatch):
        save()
        save(name="ctl-2")
        save("Branch", name="b-1")
        got = self._read(monkeypatch, {"ctl-1": [Response(200, "[1, 2]")],
                                       "ctl-2": [Response(401, "")],
                                       "b-1": [Response(200, "[]")]})
        rows = {r["name"]: r for r in got["controllers"]}
        assert set(rows) == {"sdn:default/ctl-1", "sdn:default/ctl-2", "sdn:branch/b-1"}, \
            "Lab-3 sets none and takes none of Default's (C1841): each probed once"
        assert rows["sdn:default/ctl-1"]["state"] == "up"
        assert rows["sdn:default/ctl-2"]["state"] == "refused"
        assert rows["sdn:branch/b-1"]["label"] == "SDN controller b-1 (Branch)"
        assert len(got["integrations"]) == 3 and "sdn" not in json.dumps(got["counts"])

    def test_the_strip_counts_them_in_the_total(self):
        from unittest import mock

        import app as Ap
        from modules import device_page
        client = Ap.app.test_client()
        value = {"integrations": [{"name": "grafana", "label": "Grafana", "state": "up"}],
                 "controllers": [{"name": "sdn:default/c", "label": "SDN controller c",
                                  "state": "down", "message": "could not connect"}]}
        with mock.patch.object(device_page, "_cached", return_value=(value, None, "")):
            html = client.get("/v2/strip").get_data(as_text=True)
        assert "Integrations 1 of 2" in html and "SDN controller c down" in html

    def test_no_controllers_leaves_the_value_as_it_was(self, monkeypatch):
        from modules.readers import integration_health as IH
        from tests.test_integration_health import REG
        assert "controllers" not in IH.read(REG)
