"""Every write a Lab 9 objective's test list has, walked in the laptop kit's mode (the operator,
2026-11-10: "an objective is Ready for test only after EVERY write in its test list has been
walked on the kit (sign-in, export commit, publish, deploy, AI call)").

**Why.** At the Lab 9 sitting the kit had no verified person. Mercury listened on loopback with
no access proxy, the kit's identity exception had turned the gates for configure, confirm and
approve off, and the operations that ask for a verified person themselves then refused (the NSOT
export's commit, Add an app as a Draft, Run its tests, Publish, the response policy, every AI
call a person starts). The suite had run each of those writes only as the harness's default
verified person (tests/conftest.py, `_a_verified_person_by_default`), so nothing saw it. The
installation's one local account (modules/local_account.py) is what lets a person be verified
there; these walks hold that it does, for each write.

**Kit mode** is one fixture, `kit`, entered by each walk on the store its own fixture made:

- the real `identify()` (`pytest.mark.real_identity`), no access proxy configured;
- Mercury bound to loopback (`config.FLASK_HOST`), each request from 127.0.0.1 carrying the
  Origin a page of Mercury's own sends (the kit turns `require_same_origin_writes` on);
- the kit's own settings, written by the kit's own script (lab/sdn-laptop/kit_settings.py,
  loaded here and called: its `INSTALLATION` values but its own NetBox and port, its
  `exception_on` and its `local_account`), so nothing of the kit's list is typed here;
- the local account set and SIGNED IN through the real sign-in route with the test client, so
  every later request of that client carries the session.

**A walk** drives one write through its real v2 routes on the back-end the write's own test
file fakes (each class borrows that file's fixtures; they share names such as `lab` and
`world`, which is why an objective whose writes need several back-ends has a class for each),
and holds three things:

1. signed in as the local account, the write is not refused;
2. its record (the commit's trailers, the settings record, the receipt, the AI call's row)
   names the account, verified as ``local-account``;
3. the signed-out control: the same request without the session. What that does is the write's
   row in `WALKS`, one of four, and each is asserted exactly:
   - `BY_ITSELF`: the operation asks for a verified person itself and refuses;
   - `AT_ITS_GATE`: a gate the kit's exception leaves on (reveal) refuses before the route;
   - `AS_UNVERIFIED`: the kit's exception opened its gate and the operation refuses no
     unverified actor itself, so the write is taken and its record says ``unverified``,
     verified ``none``. The walk shows the sign-in is what puts a person's name on it;
   - `A_READ`: nothing is written for a person; it answers signed out too.

`WALKS` is the table (objective, then each write and its signed-out control). The last test
holds it against the tests in this file: a write in the table with no walk, a walk with no row,
and a walk that asserts another control than its row says all fail.

No address is parsed, stored or served by anything here but the borrowed back-ends' own (their
IPv4 and IPv6 cases are in their files), and the bind address, whose IPv6 loopback case is
tests/test_local_account.py's.
"""

import ast
import importlib.machinery
import importlib.util
import json
import os
import re
import sys
import types
from html import unescape

import pytest

from tests import test_app_publish as _publish
from tests import test_coderepo as _coderepo
from tests import test_credential_profiles_v2 as _profiles
from tests import test_device_v2 as _device
from tests import test_dhcp_steer as _dhcp
from tests import test_dhcp_steer_v2 as _dhcp_ui
from tests import test_draft_write as _draft
from tests import test_installation_settings as _install
from tests import test_nsot_export_op as _export
from tests import test_openflow_vendor as _vendor
from tests import test_sdn_analyst as _analyst
from tests import test_sdn_analyst_tools as _tools
from tests import test_sdn_apps_v2 as _apps
from tests import test_sdn_link_failure as _link
from tests import test_sdn_ops_v2 as _ops
from tests import test_sdn_policies_v2 as _policies
from tests import test_sdn_policy as _policy
from tests import test_sdn_policy_intent as _intent
from tests import test_sdn_switches_v2 as _switches
from tests import test_sdn_trace_v2 as _trace
from tests import test_sdn_v2 as _sdn_page
from tests import test_settings_v2 as _settings
from tests import test_show_commands as _show
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture, the SDN store

#: Every walk meets the real `identify()`: nobody is a person here unless the local account
#: signed them in.
pytestmark = pytest.mark.real_identity

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
#: The throwaway account every walk signs in as.
NAME = "kit-walker"
PW = "walk every write on the kit 73"
KIND = "local-account"
ORIGIN = "http://localhost"
SIGN_IN = "/v2/settings/installation/local-account/sign-in"
#: The kit's settings that name its own services (its NetBox, its port and its Prometheus):
#: each walk's fake back-end stands in for them, so they are the three of the kit's values
#: not written here.
ITS_OWN_SERVICES = ("netbox_url", "flask_port", "prometheus_url")

BY_ITSELF = "refused by the operation itself"
AT_ITS_GATE = "refused at its gate"
AS_UNVERIFIED = "taken, recorded as unverified"
A_READ = "a read: it answers signed out too"
#: The `Kit` method a walk calls for each control, which the last test reads from the source.
CONTROLS = {BY_ITSELF: "refused_by_itself", AT_ITS_GATE: "refused_at_its_gate",
            AS_UNVERIFIED: "taken_as_unverified", A_READ: "a_read"}

#: The walks whose back-end here keeps no record to read, each with why: the one kind of
#: walk, beside a read, that checks no record.
KEEPS_NO_RECORD_HERE = {
    ("Obj 1(b) and Obj 3", "previewing an app deploy"): (
        "the preview's record is the reads engine's, of the controller host's three reads; "
        "tests/test_sdn_apps_v2.py's fake sources stand in for them and keep none"),
}

#: Objective, then each write its test list has and what the same request does signed out.
#: The lists: the labs roadmap's "Obj 1(a)", "Obj 2", "Obj 1(b) and Obj 3", "Obj 5", "Obj 6" and
#: "B1" to "B5" test lists, the bring-up sheet's steps 4 to 9, and docs/LAB9_DHCP_TEST.md.
WALKS = {
    "Obj 1(a)": {
        "adding a platform": AS_UNVERIFIED,
        "saving a credential profile": AS_UNVERIFIED,
        "reading through show commands": AT_ITS_GATE,
        "saving the controller connection": AS_UNVERIFIED,
        "declaring a planned restart window": AS_UNVERIFIED,
        "committing the nsot export": BY_ITSELF,
    },
    "Obj 2": {
        "confirming a template against a capture": BY_ITSELF,
        "configuring openflow from netbox": BY_ITSELF,
        "asking for a verify now": A_READ,
    },
    "Obj 1(b) and Obj 3": {
        "setting who may publish": BY_ITSELF,
        "adding an app as a draft": BY_ITSELF,
        "running its tests": BY_ITSELF,
        "publishing a version": BY_ITSELF,
        "publishing its author s own draft as self review": BY_ITSELF,
        "previewing an app deploy": AT_ITS_GATE,
        "confirming an app deploy": AS_UNVERIFIED,
        "removing a hand installed flow": AS_UNVERIFIED,
    },
    "Obj 4": {
        "steering dhcp": AS_UNVERIFIED,
        "removing the steering": AS_UNVERIFIED,
    },
    "Obj 5": {
        "tracing a path": A_READ,
    },
    "Obj 6": {
        "adding a flow": AS_UNVERIFIED,
        "reading what was written": A_READ,
    },
    "B1": {
        "collecting now": AS_UNVERIFIED,
        "adding a planted issue": AS_UNVERIFIED,
        "correcting the sheet": AS_UNVERIFIED,
        "downloading the sheet": A_READ,
        "analysing this network": BY_ITSELF,
        "saying whether a finding was right": BY_ITSELF,
    },
    "B2": {
        "drafting a policy": BY_ITSELF,
        "sending a policy": AS_UNVERIFIED,
    },
    "B3": {
        "marking the network lab": BY_ITSELF,
        "reading what each switch can do": A_READ,
        "starting and stopping the loop": AS_UNVERIFIED,
        "confirming a response": AS_UNVERIFIED,
        "dismissing a response": AS_UNVERIFIED,
        "verifying a reroute": AS_UNVERIFIED,
        "turning auto on": BY_ITSELF,
        "setting the response policy": BY_ITSELF,
    },
    "B4": {
        "analysing with the trace tool": BY_ITSELF,
    },
    "B5": {
        "downloading the export": A_READ,
    },
}


# ── kit mode ─────────────────────────────────────────────────────────────────────────────────

def _kit_settings(monkeypatch):
    """The kit's own settings script, loaded as the kit runs it (it puts the working folder
    first on the import path, put back when the test ends)."""
    path = os.path.join(ROOT, "lab", "sdn-laptop", "kit_settings.py")
    monkeypatch.setattr(sys, "path", list(sys.path))
    loader = importlib.machinery.SourceFileLoader("kit_settings_for_the_walks", path)
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(mod)
    return mod


def _client(app):
    """A browser on the kit's own machine: its requests come from 127.0.0.1 (the test client's
    own peer) and carry the Origin of Mercury's own pages."""
    c = app.test_client()
    c.environ_base["HTTP_ORIGIN"] = ORIGIN
    return c


def _text(r) -> str:
    return unescape(r.get_data(as_text=True))


class Kit:
    """Kit mode entered: `me` is signed in as the local account, `nobody` is the same browser
    with no session. The four controls and the two record checks are the walks' vocabulary."""

    def __init__(self, me, nobody):
        self.me, self.nobody = me, nobody

    def recorded(self, actor, verified):
        """The record of what `me` did names the account, verified as local-account."""
        assert (actor, verified) == (NAME, KIND), (actor, verified)

    def recorded_by_name(self, actor):
        """The same, for a record that keeps who and not how."""
        assert actor == NAME, actor

    def refused_by_itself(self, r, words):
        """Signed out: the operation's own refusal, in its own words, never the gate's."""
        said = _text(r)
        assert words in said, said[:800]
        assert "requires_identity" not in said

    def refused_at_its_gate(self, r):
        """Signed out: the gate's refusal, before the route ran."""
        assert r.status_code in (401, 403), (r.status_code, _text(r)[:400])
        assert (r.get_json() or {}).get("requires_identity") is True, _text(r)[:400]

    def taken_as_unverified(self, actor, verified="none"):
        """Signed out: the write was taken, and its record names nobody verified."""
        from modules import identity

        assert actor == identity.UNVERIFIED and actor != NAME, actor
        assert verified == "none", verified

    def a_read(self, mine, theirs):
        """A read: answered for the person signed in and for nobody alike."""
        assert mine.status_code == 200, (mine.status_code, _text(mine)[:400])
        assert theirs.status_code == 200, (theirs.status_code, _text(theirs)[:400])


@pytest.fixture
def kit(monkeypatch, tmp_path):
    """Kit mode, entered by the walk once its own fixtures have made the store: ``k = kit()``.
    *settings* is for a store whose settings are its fixture's own table (tests/test_device_v2's
    `lab`): what the kit's script wrote is copied into it, as the file would have been read."""
    import shutil

    from modules import config
    from modules import installation_settings as IS
    from modules import local_account as LA

    kept = {}

    def enter(settings=None) -> Kit:
        import app as A
        from modules import identity

        # The kit's settings land in a file of this test's own, holding what the walk's
        # fixture stored: a store whose fixture left the settings file where the whole run
        # reads it would otherwise carry the kit's exception into the next test.
        own = str(tmp_path / "kit_user_settings.json")
        if os.path.exists(config.USER_SETTINGS_FILE):
            shutil.copyfile(config.USER_SETTINGS_FILE, own)
        monkeypatch.setattr(config, "USER_SETTINGS_FILE", own)
        for name in (LA.FILE, LA.ATTEMPTS_FILE, IS.RECORD):
            path = os.path.join(config.DATA_DIR, name)
            kept[path] = open(path, "rb").read() if os.path.exists(path) else None
        monkeypatch.setattr(config, "FLASK_HOST", "127.0.0.1")
        K = _kit_settings(monkeypatch)
        K._write({k: v for k, v in K.INSTALLATION.items() if k not in ITS_OWN_SERVICES})
        K.exception_on("the walk's end")
        LA.set_password(NAME, PW)
        K.local_account(True, "the kit-mode walks")
        if settings is not None:
            settings.update(config.load_user_settings())
        assert not identity.is_configured(), "an access proxy is configured"
        assert LA.state()["enabled"], LA.state()
        opened = {a: identity._setting(f"require_identity_for_{a}", True) for a in K.OPENED}
        assert opened == {a: False for a in K.OPENED}, opened
        me, nobody = _client(A.app), _client(A.app)
        r = me.post(SIGN_IN, data={"name": NAME, "password": PW})
        assert r.status_code == 200, _text(r)
        assert 'data-identified="yes"' in me.get("/v2/who").get_data(as_text=True)
        assert 'data-identified="no"' in nobody.get("/v2/who").get_data(as_text=True)
        return Kit(me, nobody)

    yield enter
    # What the kit wrote beside the settings, where the store is the whole run's: put back.
    for path, data in kept.items():
        if data is None:
            if os.path.exists(path):
                os.remove(path)
        else:
            with open(path, "wb") as fh:
                fh.write(data)


def _hidden(html: str) -> dict:
    """A card's hidden fields as the browser sends them (the first of each name)."""
    out = {}
    for m in re.finditer(r'<input type="hidden" name="([a-z_0-9]+)" value="([^"]*)"', html):
        out.setdefault(m.group(1), unescape(m.group(2)))
    return out


def _last_commit(repo_dir) -> str:
    from modules.nsot.repo import git

    rc, body, err = git(str(repo_dir), "log", "-1", "--format=%B")
    assert rc == 0, err
    return body


def _trailers(message: str) -> tuple:
    """``(Actor, Actor-Verified)`` of a commit's message."""
    def one(key):
        m = re.search(rf"^{key}: (.*)$", message, re.M)
        return m.group(1).strip() if m else ""
    return one("Actor"), one("Actor-Verified")


# ── Obj 1(a): the bring-up ───────────────────────────────────────────────────────────────────

class TestObj1aPlatforms:
    """Settings › Installation › Platforms and roles (the bring-up sheet's step 4)."""

    OBJECTIVE = "Obj 1(a)"
    networks = staticmethod(_settings.networks)
    netbox_branch = staticmethod(_install.netbox_branch)

    def test_adding_a_platform(self, networks, netbox_branch, kit):
        from modules import installation_settings as I
        from modules.settings_schema import get_setting

        k = kit()

        def add(client, slug):
            html = client.post("/v2/settings/installation/platforms/preview",
                               data=_install._platform_form(
                                   new_slug=slug, new_driver="cisco_ios",
                                   new_dialect="cisco_ios", new_transport="ssh")
                               ).get_data(as_text=True)
            f = _hidden(html)
            return client.post("/v2/settings/installation/platforms/apply", data={
                "proposal": f["proposal"], "fingerprint": f["fingerprint"]})

        r = add(k.nobody, "nexus")
        assert r.status_code == 200, _text(r)[:600]
        row = I.changes(kinds=("platforms_map",))["rows"][0]
        k.taken_as_unverified(row["actor"], row["actor_verified"])
        r = add(k.me, "linux")
        assert r.status_code == 200 and "linux" in get_setting("platform_map"), _text(r)[:600]
        row = I.changes(kinds=("platforms_map",))["rows"][0]
        k.recorded(row["actor"], row["actor_verified"])
        assert row["actor_label"] == f"{NAME} (local account, kit)"


class TestObj1aCredentialProfiles:
    """Credentials › Profiles, Add a profile… (the bring-up sheet's step 6)."""

    OBJECTIVE = "Obj 1(a)"
    store = staticmethod(_profiles.store)

    def test_saving_a_credential_profile(self, store, kit):
        k = kit()

        def save(client, value):
            return client.post("/v2/credentials/profiles", data={
                "kind": "role", "value": value, "username": "netops",
                "password": _profiles.PW, "secret": ""})

        r = save(k.nobody, "switch")
        assert r.status_code == 200 and "Saved role:switch" in _text(r), _text(r)[:600]
        row = _profiles._changes(store)[-1]
        k.taken_as_unverified(row["actor"], row["verified"])
        r = save(k.me, "router")
        assert r.status_code == 200 and "Saved role:router" in _text(r), _text(r)[:600]
        row = _profiles._changes(store)[-1]
        assert row["profile"] == "role:router" and row["action"] == "saved"
        k.recorded(row["actor"], row["verified"])
        assert _profiles.PW not in (store["dir"] / "credential_changes.jsonl").read_text()


class TestObj1aShowCommands:
    """Show commands, Run on N devices (the bring-up sheet's step 8, and Obj 2's captures).
    Its gate is reveal, which the kit's exception leaves on (C2897 opened it for the first
    sitting alone, and the kit refuses that after its cap)."""

    OBJECTIVE = "Obj 1(a)"
    lab = staticmethod(_device.lab)
    sc = staticmethod(_show.sc)

    def test_reading_through_show_commands(self, sc, kit):
        from modules.nsot import capture_job, reads

        k = kit(settings=sc["settings"])
        page = k.me.get("/v2/show-commands?list=Lab").get_data(as_text=True)
        fp = re.search(r'name="fingerprint" value="([0-9a-f]+)"', page).group(1)
        data = {"list": "Lab", "command": ["show clock"], "fingerprint": fp}
        r = k.nobody.post("/v2/show-commands/run", data=data, headers={"HX-Request": "true"})
        k.refused_at_its_gate(r)
        assert sc["fleet"].sent == [], "no device was asked"
        r = k.me.post("/v2/show-commands/run", data=data, headers={"HX-Request": "true"})
        target = r.headers.get("HX-Redirect", "")
        assert r.status_code == 204 and target, (r.status_code, _text(r)[:600])
        job = re.search(r"job=([0-9a-f]{32})", target).group(1)
        assert capture_job.wait(job, 30)
        run = re.search(r"/run/([^?/]+)", target).group(1)
        record = reads.get("Lab", run)
        assert sorted(sc["fleet"].sent) == [("r3", "show clock"), ("r9", "show clock")]
        assert record["results"]["r3"]["state"] == "answered", record["results"]
        k.recorded_by_name(record["actor"])


class TestObj1aTheController:
    """Settings › the network › Integrations, the SDN controllers card (the bring-up sheet's
    step 9), and the planned-restart window a restart there is declared with first."""

    OBJECTIVE = "Obj 1(a)"
    lab = staticmethod(_sdn_page.lab)

    def test_saving_the_controller_connection(self, lab, kit):
        from modules import list_settings

        k = kit()

        def save(client, name):
            form = _sdn_page._form(name=name)
            tested = _hidden(client.post("/v2/settings/network/Branch/sdn/test",
                                         data=form).get_data(as_text=True))
            return client.post("/v2/settings/network/Branch/sdn/save",
                               data=dict(form, tested=tested["tested"]))

        def last():
            return [x for x in list_settings.changes("Branch")["rows"]
                    if x.get("kind") == "sdn_connection"][0]

        r = save(k.nobody, "left-ctl")
        assert r.status_code == 200, _text(r)[:600]
        k.taken_as_unverified(last()["actor"], last()["actor_verified"])
        r = save(k.me, "branch-ctl")
        assert r.status_code == 200 and "branch-ctl" in _text(r), _text(r)[:600]
        k.recorded(last()["actor"], last()["actor_verified"])

    def test_declaring_a_planned_restart_window(self, lab, kit):
        from modules.restarts import _data, _read_jsonl

        k = kit()

        def declare(client, why):
            return client.post("/restarts/planned", json={
                "list": "Default", "devices": ["*"], "minutes": 20, "why": why})

        def last():
            return _read_jsonl(_data("planned_restarts.jsonl"))["rows"][-1]

        r = declare(k.nobody, "nobody's window")
        assert r.status_code == 200, r.get_json()
        k.taken_as_unverified(last()["by"])
        r = declare(k.me, "Ryu to User=ryu")
        assert r.status_code == 200, r.get_json()
        assert last()["why"] == "Ryu to User=ryu" and last()["via"] == "api"
        k.recorded_by_name(last()["by"])


class TestObj1aTheExport:
    """SDN › Apps, Export from NetBox… and Commit the export (the list's step 6; Obj 2, Obj 4
    and B2 each need it committed)."""

    OBJECTIVE = "Obj 1(a)"
    lab = staticmethod(_export.lab)

    def test_committing_the_nsot_export(self, lab, kit):
        from modules.nsot import export_op, listref

        k = kit()
        net = _export.NET
        r = k.me.post("/v2/sdn/export/preview", data={"list": net})
        assert r.status_code == 200 and "Commit the export" in _text(r), _text(r)[:600]
        f = _hidden(r.get_data(as_text=True))
        form = {"list": net, "hash": f["hash"], "sha256": f["sha256"], "base_blob": ""}
        out = k.nobody.post("/v2/sdn/export/confirm", data=form)
        assert out.status_code == 409 and export_op.last(net)["state"] == "none"
        k.refused_by_itself(out, "an NSOT export is committed by a verified person")
        r = k.me.post("/v2/sdn/export/confirm", data=form)
        assert r.status_code == 200 and f"Committed {net}'s NSOT export" in _text(r), \
            _text(r)[:600]
        assert export_op.last(net)["actor"] == NAME
        k.recorded(*_trailers(_last_commit(listref.resolve(net).repo_dir)))


# ── Obj 2: the OpenFlow configuration ────────────────────────────────────────────────────────

class TestObj2OpenFlowConfig:
    """SDN › Switches: Confirm against a capture…, Configure from NetBox… and Verify now."""

    OBJECTIVE = "Obj 2"
    netmiko_fake = staticmethod(_vendor.netmiko_fake)
    net = staticmethod(_vendor.net)
    tab = staticmethod(_switches.tab)
    LIST = _vendor.LIST

    def _confirm_template(self, client, capture):
        r = client.post("/v2/sdn/switches/template/preview", data={
            "list": self.LIST, "template": "arista_eos", "capture": capture})
        assert r.status_code == 200, _text(r)[:600]
        return client.post("/v2/sdn/switches/template/confirm",
                           data=_hidden(r.get_data(as_text=True)))

    def test_confirming_a_template_against_a_capture(self, tab, net, kit, monkeypatch):
        from modules.sdn import openflow_templates as T

        k = kit()
        capture = _switches.TestTheTemplatesCard()._capture(monkeypatch)
        # C3022: the check said "by a verified person" and took "none"; it refuses now.
        r = self._confirm_template(k.nobody, capture)
        k.refused_by_itself(r, "a template is confirmed by a verified person")
        assert T.status(self.LIST, "arista_eos")["status"] != T.CONFIRMED
        r = self._confirm_template(k.me, capture)
        assert r.status_code == 200 and "Confirmed arista_eos" in _text(r), _text(r)[:600]
        assert T.status(self.LIST, "arista_eos")["status"] == T.CONFIRMED
        message = _last_commit(net / "config_repo")
        assert "OpenFlow template confirmed: arista_eos" in message
        k.recorded(*_trailers(message))

    def test_configuring_openflow_from_netbox(self, tab, kit, monkeypatch):
        from modules.sdn import flow_intent

        k = kit()
        _vendor._confirm(monkeypatch, "arista-sw1", "arista_eos")

        def configure(client):
            sw = _vendor.SwitchConn.at["192.0.2.2"] = _vendor.Switch(
                "arista-sw1.txt", running="hostname x\n")
            pv = client.post("/v2/sdn/switches/configure/preview",
                             data={"list": self.LIST, "device": "arista-sw1"})
            f = _switches._fields(pv.get_data(as_text=True))
            done = client.post("/v2/sdn/switches/configure/confirm", data={
                "list": self.LIST, "hash": f["hash"][0], "plan": f["plan"]})
            return sw, done

        # C3022: the apply said "by a verified person" and took "none"; it refuses now, and
        # nothing reaches the switch.
        sw, done = configure(k.nobody)
        k.refused_by_itself(done, "an OpenFlow configuration is applied by a verified person")
        assert sw.sets == [] and not sw.saved
        assert flow_intent.operations(self.LIST)["rows"] == []
        sw, done = configure(k.me)
        assert done.status_code == 200 and "Configured 1 of 1" in _text(done), _text(done)[:800]
        assert len(sw.sets) == 1 and not sw.saved
        rows = flow_intent.operations(self.LIST)["rows"]
        mine = [x for x in rows if x["actor"] == NAME]
        assert len(rows) == 1 and len(mine) == 1 and mine[0]["outcome"] == "verified", rows
        assert mine[0]["response"]["device"] == "arista-sw1"
        k.recorded(mine[0]["actor"], mine[0]["actor_verified"])

    def test_asking_for_a_verify_now(self, tab, kit, monkeypatch):
        """Verify now asks the SDN reader to read the controllers again, as its schedule does
        anyway: nothing is sent to a switch and nobody is asked for. The reader's run is
        stood in for, as SDN › Switches' own test does."""
        asked = []
        monkeypatch.setattr("modules.reader_job.running", lambda name: True)
        monkeypatch.setattr("modules.reader_job.request_run",
                            lambda reader, by, **kw: asked.append((reader.name, by)) or
                            {"started": True, "run": "x"})
        k = kit()
        theirs = k.nobody.post("/v2/sdn/switches/verify", data={"list": self.LIST})
        mine = k.me.post("/v2/sdn/switches/verify", data={"list": self.LIST})
        k.a_read(mine, theirs)
        assert "Reading the controllers now" in _text(mine)
        assert asked == [("sdn-controllers", "unverified"), ("sdn-controllers", NAME)]
        assert tab["opened"] == [], "no session was opened to any switch"


# ── Obj 1(b) and Obj 3: the app path ─────────────────────────────────────────────────────────

class TestObj1bObj3TheAppPath:
    """Who may publish, Add an app as a Draft…, Run its tests, and Review and publish…, on a
    code repository made here with the container harness faked (tests/test_app_publish.py's
    world)."""

    OBJECTIVE = "Obj 1(b) and Obj 3"
    lab = staticmethod(_coderepo.lab)
    code = staticmethod(_coderepo.code)
    bare = staticmethod(_draft.bare)
    world = staticmethod(_publish.world)
    NET = _coderepo.NET
    VERSION = {"list": _coderepo.NET, "app": "of_versions", "version": "1.0.0"}

    def _review(self, client, value, loaded):
        return client.post(f"/v2/settings/network/{self.NET}/code-review",
                           data={"review": value, "loaded_review": loaded})

    def _add_draft(self, client, files):
        """Add an app as a Draft… with the folder's files: the preview, then its confirm."""
        pv = _draft.upload(client, files)
        assert pv.status_code == 200, _text(pv)[:800]
        f = _draft.hidden(pv.get_data(as_text=True))
        return client.post("/v2/sdn/apps/draft/confirm", data={
            "list": self.NET, "name": _draft.NAME, "hash": f["hash"][0], "base": f["base"][0],
            "files_sha": f["files_sha"][0], "path": f["path"], "content": f["content"]})

    def test_setting_who_may_publish(self, world, kit):
        from modules import coderepo, list_settings

        k = kit()
        out = self._review(k.nobody, "self_recorded", "another_person")
        assert out.status_code == 409 and coderepo.review_policy(self.NET)["value"] == \
            "another_person"
        k.refused_by_itself(out, "a network's review policy is set by a verified person")
        r = self._review(k.me, "self_recorded", "another_person")
        assert r.status_code == 200 and "are published by its author too" in _text(r), \
            _text(r)[:600]
        assert coderepo.review_policy(self.NET)["value"] == "self_recorded"
        row = [x for x in list_settings.changes(self.NET)["rows"]
               if x.get("kind") == "code_review"][0]
        k.recorded(row["actor"], row["actor_verified"])

    def test_adding_an_app_as_a_draft(self, world, bare, kit):
        k = kit()
        _coderepo.set_to(bare, "main")
        base = _draft.head(bare)
        pv = _draft.upload(k.me)
        f = _draft.hidden(pv.get_data(as_text=True))
        form = {"list": self.NET, "name": _draft.NAME, "hash": f["hash"][0],
                "base": f["base"][0], "files_sha": f["files_sha"][0], "path": f["path"],
                "content": f["content"]}
        out = k.nobody.post("/v2/sdn/apps/draft/confirm", data=form)
        assert out.status_code == 409 and _draft.head(bare) == base
        k.refused_by_itself(out, "a Draft is added by a verified person")
        r = k.me.post("/v2/sdn/apps/draft/confirm", data=form)
        done = _text(r)
        assert r.status_code == 200 and "dhcp_watch 0.1.0 added as a Draft" in done, done[:800]
        assert "Fetched and registered as a Draft" in done and _draft.head(bare) != base
        message = _coderepo.git(bare, "log", "-1", "--format=%B", "main")
        assert _coderepo.git(bare, "log", "-1", "--format=%an", "main") == NAME
        k.recorded(*_trailers(message))

    def test_running_its_tests(self, world, kit):
        k = kit()
        out = k.nobody.post("/v2/sdn/apps/version/test", data=self.VERSION)
        assert out.status_code == 409 and world["runs"] == [] and \
            _publish._entry()["test"] is None
        k.refused_by_itself(out, "a version's tests are run for a verified person")
        r = k.me.post("/v2/sdn/apps/version/test", data=self.VERSION)
        assert r.status_code == 200 and "3 passed" in _text(r), _text(r)[:600]
        assert len(world["runs"]) == 1
        test = _publish._entry()["test"]
        assert test["ok"] is True and test["passed"] == 3, test
        k.recorded(test["by"], test["actor_verified"])

    def test_publishing_a_version(self, world, kit):
        """A version another person wrote (the repository's own author): tested and published
        by the local account."""
        k = kit()
        assert k.me.post("/v2/sdn/apps/version/test", data=self.VERSION).status_code == 200
        pv = k.me.post("/v2/sdn/apps/version/publish/preview", data=self.VERSION)
        assert pv.status_code == 200 and "you may publish it" in _text(pv), _text(pv)[:800]
        form = dict(self.VERSION, hash=_hidden(pv.get_data(as_text=True))["hash"],
                    reason="read it")
        out = k.nobody.post("/v2/sdn/apps/version/publish/confirm", data=form)
        assert out.status_code == 409 and _publish._entry()["version"].state == "draft"
        k.refused_by_itself(out, "a version is published by a verified person")
        r = k.me.post("/v2/sdn/apps/version/publish/confirm", data=form)
        assert r.status_code == 200 and "Published of_versions 1.0.0" in _text(r), \
            _text(r)[:800]
        entry = _publish._entry()
        assert entry["version"].state == "published"
        k.recorded(entry["version"].reviewer, entry["publication"]["reviewer_verified"])

    def test_publishing_its_author_s_own_draft_as_self_review(self, world, bare, kit):
        """The kit's own path (the list's steps 2 to 4): one person sets "its author too,
        recorded as self-review", adds the Draft, runs its tests and publishes it. The
        publication is theirs and says it was a self-review; and under the default policy,
        someone other than its author, the author is refused."""
        k = kit()
        _coderepo.set_to(bare, "main")
        files = _draft.draft(**{"manifest.yml": (
            _coderepo.manifest(_draft.NAME, _draft.VERSION)
            + "tests:\n  - tests/test_watch.py\n").encode()})
        added = self._add_draft(k.me, files)
        assert added.status_code == 200, _text(added)[:800]
        mine = {"list": self.NET, "app": _draft.NAME, "version": _draft.VERSION}
        assert k.me.post("/v2/sdn/apps/version/test", data=mine).status_code == 200
        entry = _publish._entry(_draft.NAME, _draft.VERSION)
        # Someone other than its author (the default): its author is told so, by name.
        pv = k.me.post("/v2/sdn/apps/version/publish/preview", data=mine)
        assert "you are its author" in _text(pv), (entry["version"].author, _text(pv)[:800])
        assert self._review(k.me, "self_recorded", "another_person").status_code == 200
        pv = k.me.post("/v2/sdn/apps/version/publish/preview", data=mine)
        assert pv.status_code == 200 and "you may publish it" in _text(pv), _text(pv)[:800]
        form = dict(mine, hash=_hidden(pv.get_data(as_text=True))["hash"],
                    reason="one person runs this network")
        out = k.nobody.post("/v2/sdn/apps/version/publish/confirm", data=form)
        assert out.status_code == 409
        k.refused_by_itself(out, "a version is published by a verified person")
        r = k.me.post("/v2/sdn/apps/version/publish/confirm", data=form)
        assert r.status_code == 200 and f"Published {_draft.NAME} {_draft.VERSION}" in \
            _text(r), _text(r)[:800]
        entry = _publish._entry(_draft.NAME, _draft.VERSION)
        k.recorded(entry["version"].reviewer, entry["publication"]["reviewer_verified"])
        assert entry["version"].self_review is True, (entry["version"].author,
                                                      entry["version"].reviewer)


class TestObj1bObj3TheDeploy:
    """Preview deploying … and Deploy … and restart <controller>, with the registry and the
    controller host faked at `deploy_op.Sources` (tests/test_sdn_apps_v2.py's)."""

    OBJECTIVE = "Obj 1(b) and Obj 3"
    apps = staticmethod(_apps.apps)

    def test_previewing_an_app_deploy(self, apps, kit):
        """The preview reads the controller host through the reads engine, so its gate is
        reveal, which the kit's exception leaves on."""
        from modules import controller_deploy_receipts as receipts

        k = kit()
        out = _apps.preview(k.nobody)
        k.refused_at_its_gate(out)
        r = _apps.preview(k.me)
        html = r.get_data(as_text=True)
        assert r.status_code == 200 and "The set, in load order" in html, _text(r)[:800]
        assert len(_apps.fields(html)["hash"]) == 64
        # Nothing was sent and no receipt is kept by a preview. The record of its host reads
        # is the wired sources' (the reads engine's), which the fake stands in for here.
        assert apps["src"].sent == [] and receipts.read(_apps.NET)["rows"] == []

    def test_confirming_an_app_deploy(self, apps, kit):
        from modules import controller_deploy_receipts as receipts

        k = kit()

        def deploy(previewed_by, confirmed_by, chosen):
            html = _apps.preview(previewed_by, chosen).get_data(as_text=True)
            apps["src"].reads = [_apps.ALL_BACK_TWO]
            _r, done = _apps.confirm(confirmed_by, html)
            return done, receipts.read(_apps.NET)["rows"][0]

        done, row = deploy(k.me, k.nobody, "of_versions=1.0.0")
        assert row["outcome"] == "deployed", done[:800]
        k.taken_as_unverified(row["actor"], row["actor_verified"])
        done, row = deploy(k.me, k.me, "of_versions=1.1.0")
        assert "Deployed" in done and row["outcome"] == "deployed", done[:800]
        k.recorded(row["actor"], row["actor_verified"])
        got = k.me.get(f"/v2/sdn/apps/receipt/{row['id']}.json")
        assert got.status_code == 200 and json.loads(got.get_data())["actor"] == NAME


class TestObj1bObj3TheFlows:
    """The list's step 6: the flows installed by hand at the last visit read "unauthorised" on
    SDN › Flows, and each is removed there before the failover test."""

    OBJECTIVE = "Obj 1(b) and Obj 3"
    lab = staticmethod(_ops.lab)
    NET = "Default"

    def test_removing_a_hand_installed_flow(self, lab, kit):
        from modules.sdn import flow_intent

        k = kit()
        # Two flows nobody installed through Mercury, under a cookie that is not the
        # controller's own: one for each browser to remove.
        by_hand = [{"table_id": 0, "priority": 200, "cookie": 0xbad1,
                    "match": {"eth_type": 2048, "ipv4_dst": f"198.51.100.{n}"}, "actions": []}
                   for n in (61, 62)]
        lab["fake"].table[1].extend(dict(f) for f in by_hand)

        def remove(client, flow):
            target = {key: flow[key] for key in ("table_id", "priority", "match", "cookie")}
            pv = client.post("/v2/sdn/flow/preview", data={
                "list": self.NET, "do": "remove", "connection": "lab-controller",
                "dpid": "0000000000000001", "target": json.dumps(target)})
            assert pv.status_code == 200, _text(pv)[:800]
            r = client.post("/v2/sdn/flow/confirm",
                            data=_ops.form_fields(pv.get_data(as_text=True)))
            assert r.status_code == 200 and "Done, verified" in _text(r), _text(r)[:800]
            assert flow["match"] not in [f["match"] for f in lab["fake"].table[1]]
            (row,) = [x for x in flow_intent.operations(self.NET)["rows"]
                      if flow["match"]["ipv4_dst"] in json.dumps(x)]
            return row

        row = remove(k.nobody, by_hand[0])
        k.taken_as_unverified(row["actor"], row["actor_verified"])
        row = remove(k.me, by_hand[1])
        assert row["outcome"] == "verified"
        k.recorded(row["actor"], row["actor_verified"])


# ── Obj 4: DHCP steering ─────────────────────────────────────────────────────────────────────

class TestObj4DhcpSteering:
    """SDN › Apps' DHCP steering card (docs/LAB9_DHCP_TEST.md, steps 1 and 5)."""

    OBJECTIVE = "Obj 4"
    netbox_list = staticmethod(_dhcp.netbox_list)
    lab = staticmethod(_dhcp.lab)
    ui = staticmethod(_dhcp_ui.ui)
    NET = _dhcp.NET

    def _steer(self, client, **choice):
        pv = client.post("/v2/sdn/dhcp/preview", data=dict({"list": self.NET}, **choice))
        assert pv.status_code == 200, _text(pv)[:800]
        r = client.post("/v2/sdn/dhcp/confirm",
                        data=_dhcp_ui.confirm_form(pv.get_data(as_text=True)))
        assert r.status_code == 200 and "DHCP steering applied" in _text(r), _text(r)[:800]

    def _remove(self, client):
        pv = client.post("/v2/sdn/dhcp/remove/preview", data={"list": self.NET})
        assert pv.status_code == 200, _text(pv)[:800]
        r = client.post("/v2/sdn/dhcp/remove/confirm",
                        data=_dhcp_ui.confirm_form(pv.get_data(as_text=True)))
        assert r.status_code == 200 and "Removed DHCP steering" in _text(r), _text(r)[:800]

    def _operations(self):
        from modules.sdn import flow_intent

        return flow_intent.operations(self.NET)["rows"]

    def test_steering_dhcp(self, ui, kit):
        from modules.sdn import flow_intent

        k = kit()
        self._steer(k.nobody, scope="chosen", switch="arista-sw2")
        theirs = self._operations()
        assert theirs and {x["outcome"] for x in theirs} == {"verified"}, theirs
        for row in theirs:
            k.taken_as_unverified(row["actor"], row["actor_verified"])
        self._steer(k.me, scope="all")
        mine = [x for x in self._operations() if x not in theirs]
        assert mine and {x["outcome"] for x in mine} == {"verified"}, mine
        for row in mine:
            k.recorded(row["actor"], row["actor_verified"])
        flows = flow_intent.intent(self.NET, _dhcp_ui.CONN)["flows"]
        assert len(flows) == 9 and {x["response"]["owner"] for x in flows} == {_dhcp.D.OWNER}
        assert NAME in {x["actor"] for x in flows}

    def test_removing_the_steering(self, ui, kit):
        from modules.sdn import flow_intent

        k = kit()
        self._steer(k.me, scope="all")
        before = self._operations()
        self._remove(k.nobody)
        theirs = [x for x in self._operations() if x not in before]
        assert theirs and flow_intent.intent(self.NET, _dhcp_ui.CONN)["flows"] == []
        for row in theirs:
            k.taken_as_unverified(row["actor"], row["actor_verified"])
        self._steer(k.me, scope="all")
        before = self._operations()
        self._remove(k.me)
        mine = [x for x in self._operations() if x not in before]
        assert mine and flow_intent.intent(self.NET, _dhcp_ui.CONN)["flows"] == []
        for row in mine:
            k.recorded(row["actor"], row["actor_verified"])


# ── Obj 5 and Obj 6: reads ───────────────────────────────────────────────────────────────────

class TestObj5Trace:
    """Topology › Path… on Flow tables: a read of the SDN reader's stored value. The list has
    no write to walk; what is held is that the trace answers for the person signed in."""

    OBJECTIVE = "Obj 5"
    web = staticmethod(_trace.web)

    def test_tracing_a_path(self, web, kit):
        k = kit()
        url = "/v2/topology/map?list=Lab&layer=of&src=192.0.2.1&dst=192.0.2.3"
        web["asked"].clear()
        mine, theirs = k.me.get(url), k.nobody.get(url)
        k.a_read(mine, theirs)
        # Each answer is one read of the SDN reader's stored value, for the network asked:
        # no controller is called for a trace.
        assert web["asked"] == ["Lab", "Lab"], web["asked"]
        card = _trace._card(mine.get_data(as_text=True))
        assert _trace._strip(card), card[:800]
        assert _trace.DPID1 in card and "The trace failed" not in card
        assert _trace._card(theirs.get_data(as_text=True)) == card


class TestObj6AllViaRest:
    """Every flow Mercury writes goes through SDN › Flows' operation core and is one row on
    History. B1's stale drop flow and Obj 1(b)'s Remove are this same route."""

    OBJECTIVE = "Obj 6"
    lab = staticmethod(_ops.lab)
    NET = "Default"

    def _add(self, client, source):
        pv = client.post("/v2/sdn/flow/preview", data={
            "list": self.NET, "do": "add", "connection": "lab-controller",
            "dpid": "0000000000000001", "priority": "250", "hard_timeout": "60",
            "match": f"eth_type=0x0800, ipv4_src={source}", "actions": "drop"})
        assert pv.status_code == 200, _text(pv)[:800]
        r = client.post("/v2/sdn/flow/confirm",
                        data=_ops.form_fields(pv.get_data(as_text=True)))
        assert r.status_code == 200 and "Done, verified" in _text(r), _text(r)[:800]

    def _operation(self, source):
        from modules.sdn import flow_intent

        (row,) = [x for x in flow_intent.operations(self.NET)["rows"]
                  if source in json.dumps(x)]
        return row

    def test_adding_a_flow(self, lab, kit):
        from modules.sdn import flow_intent

        k = kit()
        self._add(k.nobody, "198.51.100.8")
        row = self._operation("198.51.100.8")
        k.taken_as_unverified(row["actor"], row["actor_verified"])
        self._add(k.me, "198.51.100.9")
        row = self._operation("198.51.100.9")
        assert row["outcome"] == "verified"
        k.recorded(row["actor"], row["actor_verified"])
        kept = {x["match"]["ipv4_src"]: x["actor"]
                for x in flow_intent.intent(self.NET, "lab-controller")["flows"]}
        assert kept["198.51.100.9"] == NAME

    def test_reading_what_was_written(self, lab, kit):
        """The list's reads: History's SDN flow operations, SDN › Controllers and SDN › Flows.
        The row of what the person signed in wrote names them and how they were verified."""
        from modules import history_sources as HS
        from modules.nsot import listref

        k = kit()
        self._add(k.me, "198.51.100.9")
        got = HS.timeline(listref.resolve(self.NET), kinds=["sdn"])
        (event,) = got["events"]
        assert got["errors"] == [] and event["who"] == NAME, got
        for url in (f"/v2/history?list={self.NET}&kind=sdn", f"/v2/sdn?list={self.NET}",
                    f"/v2/sdn/flows?list={self.NET}"):
            mine, theirs = k.me.get(url), k.nobody.get(url)
            k.a_read(mine, theirs)
        assert NAME in _text(k.me.get(f"/v2/history?list={self.NET}&kind=sdn"))


# ── B1 and B4: the analyst ───────────────────────────────────────────────────────────────────

def _provider(monkeypatch, send):
    """The gateway's provider answers from the walk's fake sender (as the analyst's own route
    tests set it): no call leaves the test."""
    from modules.ai import gateway

    monkeypatch.setattr(gateway, "anthropic_adapter", types.SimpleNamespace(
        **{**vars(gateway.anthropic_adapter), "send": send}))


def _analysis_calls(feature) -> list:
    from modules.ai import calls

    return [x for x in calls.read()["rows"] if x.get("feature") == feature]


class TestB1Analyst:
    """SDN › Flows' Analyse this network region: Collect now, Add a planted issue…, Analyse this
    network (an AI call a person starts) and Was this right? (Download the sheet is a read.)"""

    OBJECTIVE = "B1"
    world = staticmethod(_analyst.world)
    NET = _analyst.NET

    def _collector(self, monkeypatch):
        """Collect now's job run at once against the recorded controller, with no wait
        between its two port reads (the analyst's own route test's seam)."""
        from modules.sdn import analyst as AN
        from modules.sdn import connections as C

        session = _analyst.LabRyu()
        monkeypatch.setattr(AN, "_spawn", lambda fn: fn())
        monkeypatch.setattr(AN, "collect_job", (lambda real: lambda network, **kw: real(
            network, sleep=lambda s: None, announce=False,
            driver=lambda net, name: C.driver_for(net, name, session=session), **kw))(
                AN.collect_job))

    def test_collecting_now(self, world, kit, monkeypatch):
        from modules.sdn import analyst as AN

        k = kit()
        self._collector(monkeypatch)
        r = k.nobody.post("/v2/sdn/analyse/collect", data={"list": self.NET})
        assert r.status_code == 200 and "5 switches, collected" in _text(r), _text(r)[:800]
        theirs = AN.latest_snapshot(self.NET)
        k.taken_as_unverified(theirs["by"])
        r = k.me.post("/v2/sdn/analyse/collect", data={"list": self.NET})
        assert r.status_code == 200 and "5 switches, collected" in _text(r), _text(r)[:800]
        k.recorded_by_name(AN.latest_snapshot(self.NET)["by"])

    def test_adding_a_planted_issue(self, world, kit):
        from modules.sdn import analyst as AN

        k = kit()
        evidence = f"port:ctl-1:{_analyst.OVS3}:3"

        def plant(client, name):
            r = client.post("/v2/sdn/analyse/planted", data={
                "list": self.NET, "name": name, "evidence": evidence, "why": ""})
            assert r.status_code == 200 and name in _text(r), _text(r)[:800]
            (entry,) = [e for e in AN.planted(self.NET)["history"] if e["name"] == name]
            return entry

        k.taken_as_unverified(plant(k.nobody, "Planted by nobody")["by"])
        mine = plant(k.me, "Port 3 pulled")
        assert mine["action"] == "add" and len(AN.planted(self.NET)["issues"]) == 2, mine
        k.recorded_by_name(mine["by"])

    def test_correcting_the_sheet(self, world, kit):
        """A row's Save (its why), Edit… and Remove… (the list's steps 4 and 7): each change in
        the sheet's history is its person's."""
        from modules.sdn import analyst as AN

        k = kit()

        def issue(pid):
            got = AN.planted(self.NET)
            return next(i for i in got["issues"] + got["removed"] if i["id"] == pid)

        def correct(client, name):
            r = client.post("/v2/sdn/analyse/planted", data={
                "list": self.NET, "name": name, "why": "",
                "evidence": f"port:ctl-1:{_analyst.OVS3}:33"})
            assert r.status_code == 200, _text(r)[:800]
            pid = next(i["id"] for i in AN.planted(self.NET)["issues"] if i["name"] == name)
            r = client.post(f"/v2/sdn/analyse/planted/{pid}/why", data={
                "list": self.NET, "why": "the port's LINK_DOWN"})
            assert r.status_code == 200 and issue(pid)["why"] == "the port's LINK_DOWN"
            r = client.post(f"/v2/sdn/analyse/planted/{pid}/edit", data={
                "list": self.NET, "name": name, "rev": AN.rev(issue(pid)),
                "evidence": f"port:ctl-1:{_analyst.OVS3}:3"})
            assert r.status_code == 200, _text(r)[:800]
            assert issue(pid)["evidence"] == [f"port:ctl-1:{_analyst.OVS3}:3"]
            r = client.post(f"/v2/sdn/analyse/planted/{pid}/remove", data={
                "list": self.NET, "rev": AN.rev(issue(pid))})
            assert r.status_code == 200 and issue(pid)["removed_at"], _text(r)[:800]
            return [e for e in AN.planted(self.NET)["history"] if e["id"] == pid]

        theirs = correct(k.nobody, "Planted by nobody")
        assert [e["action"] for e in theirs] == ["add", "why", "edit", "remove"], theirs
        for entry in theirs:
            k.taken_as_unverified(entry["by"])
        mine = correct(k.me, "Port 3 pulled")
        assert [e["action"] for e in mine] == ["add", "why", "edit", "remove"], mine
        for entry in mine:
            k.recorded_by_name(entry["by"])
        assert AN.planted(self.NET)["issues"] == []

    def test_downloading_the_sheet(self, world, kit):
        """Download the sheet, as Markdown and as CSV: a read, whose file says who made it
        (the person signed in, or nobody verified)."""
        from modules.sdn import analyst as AN

        k = kit()
        assert k.me.post("/v2/sdn/analyse/planted", data={
            "list": self.NET, "name": "Port 3 pulled", "why": "",
            "evidence": f"port:ctl-1:{_analyst.OVS3}:3"}).status_code == 200
        assert len(AN.planted(self.NET)["issues"]) == 1

        def made_by(r):
            (line,) = [x for x in r.get_data(as_text=True).splitlines()
                       if x.startswith(("- Made ", "# made,"))]
            return re.split(r" by |,by,", line)[1].strip()

        for fmt in ("md", "csv"):
            mine = k.me.get(f"/v2/sdn/analyse/sheet/{fmt}?list={self.NET}")
            theirs = k.nobody.get(f"/v2/sdn/analyse/sheet/{fmt}?list={self.NET}")
            k.a_read(mine, theirs)
            assert "Port 3 pulled" in mine.get_data(as_text=True)
            assert (made_by(mine), made_by(theirs)) == (NAME, "unverified"), fmt

    def test_analysing_this_network(self, world, kit, monkeypatch):
        k = kit()
        _provider(monkeypatch, world.send)
        snap = _analyst.snap_of(world)
        world.answer = _analyst.answer(_analyst.finding([f"port:ctl-1:{_analyst.OVS3}:3"]))
        ask = {"list": self.NET, "snapshot": snap["id"]}
        out = k.nobody.post("/v2/sdn/analyse/ask", data=ask)
        assert world.sent == [] and "1 finding" not in _text(out)
        k.refused_by_itself(out, "a person trigger names a verified person")
        r = k.me.post("/v2/sdn/analyse/ask", data=ask)
        html = _text(r)
        assert r.status_code == 200 and "1 finding" in html, html[:800]
        assert "Link down on 0000000000000003" in html and len(world.sent) == 1
        (row,) = [x for x in _analysis_calls("sdn_analyse") if x.get("verdict") == "ok"]
        assert row["trigger"]["kind"] == "person" and row["trigger"]["by"] == NAME
        k.recorded(row["actor"], row["trigger"]["verified"])

    def test_saying_whether_a_finding_was_right(self, world, kit, monkeypatch):
        from modules.ai import feedback

        k = kit()
        _provider(monkeypatch, world.send)
        snap = _analyst.snap_of(world)
        world.answer = _analyst.answer(_analyst.finding([f"port:ctl-1:{_analyst.OVS3}:3"]))
        assert k.me.post("/v2/sdn/analyse/ask", data={
            "list": self.NET, "snapshot": snap["id"]}).status_code == 200
        (call,) = [x for x in _analysis_calls("sdn_analyse") if x.get("verdict") == "ok"]
        url = f"/v2/ai/feedback/answer/{call['id']}"
        out = k.nobody.post(url, data={"verdict": "yes"})
        assert out.status_code == 409 and feedback.read()["rows"] == []
        k.refused_by_itself(out, "recorded only as a verified person")
        r = k.me.post(url, data={"verdict": "yes"})
        assert r.status_code == 200, _text(r)[:800]
        (said,) = feedback.read()["rows"]
        assert said["call_id"] == call["id"] and said["verdict"] == "yes"
        k.recorded(said["actor"], said["verified"])


class TestB4TraceTool:
    """Analyse with the trace tool: at most two AI calls a person starts, the model's reads
    answered from the kept snapshot."""

    OBJECTIVE = "B4"
    world = staticmethod(_analyst.world)
    tw = staticmethod(_tools.tw)
    NET = _analyst.NET

    def test_analysing_with_the_trace_tool(self, tw, kit, monkeypatch):
        k = kit()
        _provider(monkeypatch, tw.send)
        snap, _session = _tools.collected_snapshot()
        port = f"port:ctl-1:{_analyst.OVS3}:3"
        ask = {"list": self.NET, "snapshot": snap["id"]}
        tw.script = []
        out = k.nobody.post("/v2/sdn/analyse/ask-tools", data=ask)
        assert tw.sent == [] and "With the trace tool: 1 finding" not in _text(out)
        k.refused_by_itself(out, "a person trigger names a verified person")
        tw.script = [{"findings": [], "reads": [_tools.ask(
                         "trace", src="2001:db8::10", dst="2001:db8::20", proto="icmp")]},
                     {"findings": [_analyst.finding([port], "high",
                                                    "Port 3 on OVS 3 is down, traced")]}]
        r = k.me.post("/v2/sdn/analyse/ask-tools", data=ask)
        html = _text(r)
        assert r.status_code == 200 and "With the trace tool: 1 finding" in html, html[:800]
        assert "Tool calls" in html and len(tw.sent) == 2
        rows = [x for x in _analysis_calls("sdn_analyse_tools") if x.get("verdict") == "ok"]
        assert len(rows) == 2, rows
        for row in rows:
            assert row["trigger"]["by"] == NAME
            k.recorded(row["actor"], row["trigger"]["verified"])


# ── B2: the intent controller ────────────────────────────────────────────────────────────────

class TestB2Policies:
    """SDN › Policies: Draft the policy (an AI call a person starts), then Preview the flows…
    and its confirm."""

    OBJECTIVE = "B2"
    lab = staticmethod(_intent.lab)
    ui = staticmethod(_policies.ui)
    NET = _intent.NET

    def _draft(self, client, words):
        return client.post("/v2/sdn/policies/draft", data={"list": self.NET, "words": words})

    def test_drafting_a_policy(self, ui, kit):
        k = kit()
        ui.answer = _intent.answer(_intent.rule("block", "h2", "tag:web", "tcp", 443,
                                                duration=3600))
        words = "Block h2 from reaching the web servers on TCP 443 for an hour"
        out = self._draft(k.nobody, words)
        assert ui.sent == [] and "Checked against NetBox and the network" not in _text(out)
        k.refused_by_itself(out, "a person trigger names a verified person")
        r = self._draft(k.me, words)
        assert r.status_code == 200 and "Checked against NetBox and the network" in _text(r), \
            _text(r)[:800]
        assert len(ui.sent) == 1 and ui.fake.writes == []
        (row,) = [x for x in _analysis_calls("sdn_policy") if x.get("verdict") == "ok"]
        assert row["trigger"]["by"] == NAME
        k.recorded(row["actor"], row["trigger"]["verified"])

    def test_sending_a_policy(self, ui, kit):
        from modules.sdn import flow_intent

        k = kit()

        def previewed(words, rule):
            ui.answer = _intent.answer(rule)
            drafted = self._draft(k.me, words)
            assert drafted.status_code == 200, _text(drafted)[:800]
            pv = k.me.post("/v2/sdn/policies/preview",
                           data=_policies.fields(drafted.get_data(as_text=True)))
            assert pv.status_code == 200, _text(pv)[:800]
            return _policies.fields(pv.get_data(as_text=True))

        def send(client, form):
            done = client.post("/v2/sdn/policies/confirm", data=form)
            assert done.status_code == 200 and "Done, verified" in _text(done), \
                _text(done)[:800]
            return flow_intent.intent(self.NET)["flows"]

        theirs = send(k.nobody, previewed(
            "Block h2 from reaching the web servers on TCP 443 for an hour",
            _intent.rule("block", "h2", "tag:web", "tcp", 443, duration=3600)))
        assert theirs and {x["response"]["kind"] for x in theirs} == {"policy"}
        for row in theirs:
            k.taken_as_unverified(row["actor"], row["actor_verified"])
        both = send(k.me, previewed("Allow h1 to reach web-1 on tcp 80",
                                    _intent.rule("allow", "h1", "web-1", "tcp", 80)))
        mine = [x for x in both if x not in theirs]
        assert mine and {x["response"]["kind"] for x in mine} == {"policy"}
        for row in mine:
            k.recorded(row["actor"], row["actor_verified"])


# ── B3: the closed loop ──────────────────────────────────────────────────────────────────────

class TestB3ClosedLoop:
    """SDN › Responses and the network's stage: marking the network lab, the capability
    matrix, the loop, a response confirmed and one dismissed, a link card's Verify the reroute,
    Turn AUTO on and the response policy."""

    OBJECTIVE = "B3"
    lab = staticmethod(_ops.lab)
    NET = "Default"

    def _propose(self, key, source):
        from modules.sdn import loop

        return loop.propose(self.NET, {
            "key": key, "rule": "scan", "title": "SDN scan", "network": self.NET,
            "connection": "lab-controller", "dpid": 1, "dpid_hex": "0000000000000001",
            "source": source, "targets": ["192.0.2.2"], "confidence": "high",
            "words": f"{source} reached 25 distinct destination ports"},
            "drop_source", "low", why="HITL")

    def _pending(self, kind):
        from modules.sdn import loop

        return [x for x in loop.responses_record(self.NET)["rows"] if x.get("kind") == kind]

    def test_marking_the_network_lab(self, lab, kit):
        from modules.sdn import modes

        k = kit()
        out = _ops.mark_stage(k.nobody, "lab")
        assert out.status_code == 409 and modes.stage(self.NET)["state"] == "not_marked"
        k.refused_by_itself(out, "a network's stage is set by a verified person")
        r = _ops.mark_stage(k.me, "lab")
        assert r.status_code == 200 and modes.stage(self.NET)["stage"] == "lab", _text(r)[:800]
        (row,) = _ops._stage_rows()
        k.recorded(row["actor"], row["actor_verified"])

    def test_reading_what_each_switch_can_do(self, lab, kit):
        """Read again on the capability matrix: reads of each switch through its controller,
        kept for the matrix; nobody is asked for and nobody is recorded."""
        from modules.sdn import capability

        k = kit()
        theirs = k.nobody.post("/v2/sdn/capabilities/read", data={"list": self.NET})
        mine = k.me.post("/v2/sdn/capabilities/read", data={"list": self.NET})
        k.a_read(mine, theirs)
        assert capability.stored(self.NET)["state"] == "ok"
        assert capability.view(self.NET)["rows"], capability.view(self.NET)

    def test_starting_and_stopping_the_loop(self, lab, kit, monkeypatch):
        import threading

        from modules.sdn import loop

        k = kit()
        gate = threading.Event()
        monkeypatch.setattr(loop, "run_pass", lambda network, **kw: gate.wait(5))

        def run(client):
            r = client.post("/v2/sdn/loop", data={"list": self.NET, "run": "start",
                                                  "interval": "10", "run_for": "20"})
            assert r.status_code == 200 and loop.status(self.NET)["running"], _text(r)[:800]
            started = loop.status(self.NET)
            r = client.post("/v2/sdn/loop", data={"list": self.NET, "run": "stop"})
            gate.set()
            loop._jobs[self.NET]["thread"].join(10)
            assert r.status_code == 200 and not loop.status(self.NET)["running"]
            gate.clear()
            return started

        k.taken_as_unverified(run(k.nobody)["by"])
        k.recorded_by_name(run(k.me)["by"])

    def test_confirming_a_response(self, lab, kit):
        from modules.sdn import flow_intent, loop

        k = kit()

        def confirm(client, row):
            pv = client.post(f"/v2/sdn/response/{row['id']}/preview", data={"list": self.NET})
            assert pv.status_code == 200, _text(pv)[:800]
            r = client.post("/v2/sdn/response/confirm",
                            data=_ops.form_fields(pv.get_data(as_text=True)))
            assert "Done, verified" in _text(r), _text(r)[:800]
            closed = next(x for x in self._pending("confirmed") if x["id"] == row["id"])
            op = next(x for x in flow_intent.operations(self.NET)["rows"]
                      if x["id"] == closed["operation"])
            return closed, op

        closed, op = confirm(k.nobody, self._propose("k1", "192.0.2.1"))
        k.taken_as_unverified(op["actor"], op["actor_verified"])
        k.taken_as_unverified(closed["actor"])
        closed, op = confirm(k.me, self._propose("k2", "192.0.2.7"))
        assert op["response"]["action"] == "drop_source" and op["mode"] == "hitl"
        k.recorded(op["actor"], op["actor_verified"])
        k.recorded_by_name(closed["actor"])
        assert loop.awaiting(self.NET)["rows"] == []

    def test_dismissing_a_response(self, lab, kit):
        from modules.sdn import loop

        k = kit()

        def dismiss(client, row, reason):
            r = client.post(f"/v2/sdn/response/{row['id']}/dismiss",
                            data={"list": self.NET, "reason": reason})
            assert r.status_code == 200, _text(r)[:800]
            return next(x for x in self._pending("dismissed") if x["id"] == row["id"])

        k.taken_as_unverified(dismiss(k.nobody, self._propose("k1", "192.0.2.1"),
                                      "nobody's reason")["actor"])
        mine = dismiss(k.me, self._propose("k2", "192.0.2.7"), "a known test")
        assert mine["why"] == "a known test" and loop.awaiting(self.NET)["rows"] == []
        k.recorded_by_name(mine["actor"])

    def test_verifying_a_reroute(self, lab, kit):
        """Verify the reroute on a link card. With no stored read of the fabric here, the
        verify's own answer is pending, no pair traced; what is walked is whose it is."""
        from modules.sdn import link_failure

        k = kit()
        row = link_failure.open_down(self.NET, dict(_link._detection(), network=self.NET),
                                     mode="hitl", why="HITL: the default")

        def verify(client):
            r = client.post(f"/v2/sdn/link/{row['id']}/verify", data={"list": self.NET})
            assert r.status_code == 200, _text(r)[:800]
            (kept,) = link_failure.open_rows(self.NET)["rows"]
            return kept["verify"]

        k.taken_as_unverified(verify(k.nobody)["actor"])
        mine = verify(k.me)
        assert mine["outcome"] == "pending" and mine["checked"] == 0 and mine["words"], mine
        k.recorded_by_name(mine["actor"])

    def test_turning_auto_on(self, lab, kit):
        from modules.sdn import modes

        k = kit()
        assert _ops.mark_stage(k.me, "lab").status_code == 200
        form = {"list": self.NET, "mode": "auto", "reason": "the lab's AUTO pass",
                "hours": "1", "risk": "medium"}
        out = k.nobody.post("/v2/sdn/mode", data=form)
        assert out.status_code == 409 and modes.current(self.NET)["mode"] == "hitl"
        k.refused_by_itself(out, "AUTO is turned on by a verified person")
        r = k.me.post("/v2/sdn/mode", data=form)
        assert r.status_code == 200 and modes.current(self.NET)["mode"] == "auto", \
            _text(r)[:800]
        row = modes.history(self.NET)["rows"][-1]
        assert row["kind"] == "on" and row["reason"] == "the lab's AUTO pass"
        k.recorded(row["by"], row["actor_verified"])

    def test_setting_the_response_policy(self, lab, kit):
        from modules import list_settings
        from modules.sdn import closed_loop

        k = kit()
        drawn = _policy._policy_form(k.me.get(
            f"/v2/sdn/responses?list={self.NET}").get_data(as_text=True))
        sent = {"list": self.NET, "loaded": drawn["loaded"],
                "scan_default": "rate_limit_source", "flood_default": "rate_limit_source",
                "flood_allowed": ["drop_source"], "unauthorised_flow_default": "remove_flow"}
        out = k.nobody.post("/v2/sdn/policy", data=sent)
        assert out.status_code == 409 and closed_loop.policy(self.NET)["rules"]["scan"][
            "allowed"] == closed_loop.DEFAULT_POLICY["scan"]
        k.refused_by_itself(out, "the response policy is set by a verified person")
        r = k.me.post("/v2/sdn/policy", data=sent)
        assert r.status_code == 200, _text(r)[:800]
        assert closed_loop.policy(self.NET)["rules"]["scan"]["allowed"] == ["rate_limit_source"]
        (row,) = [x for x in list_settings.changes(self.NET)["rows"]
                  if x.get("kind") == "sdn_response_policy"]
        k.recorded(row["actor"], row["actor_verified"])


# ── B5: History › Export ─────────────────────────────────────────────────────────────────────

class TestB5Export:
    """History › Export's page and its four downloads: reads. What is held is that they answer
    for the person signed in, name them as who made the file, and list the call they started
    as theirs."""

    OBJECTIVE = "B5"
    world = staticmethod(_analyst.world)
    NET = _analyst.NET

    def test_downloading_the_export(self, world, kit, monkeypatch):
        import time

        k = kit()
        _provider(monkeypatch, world.send)
        snap = _analyst.snap_of(world)
        world.answer = _analyst.answer(_analyst.finding([f"port:ctl-1:{_analyst.OVS3}:3"]))
        assert k.me.post("/v2/sdn/analyse/ask", data={
            "list": self.NET, "snapshot": snap["id"]}).status_code == 200
        (call,) = [x for x in _analysis_calls("sdn_analyse") if x.get("verdict") == "ok"]
        today = time.strftime("%Y-%m-%d", time.gmtime())
        q = f"network={self.NET}&start={today}&end={today}"
        page = f"/v2/history?tab=export&{q}"
        mine, theirs = k.me.get(page), k.nobody.get(page)
        k.a_read(mine, theirs)
        assert "1 call · " in _text(mine), _text(mine)[:800]
        for kind in ("calls", "failures"):
            for fmt in ("csv", "json"):
                url = f"/v2/history/export/{kind}/{fmt}?{q}"
                mine, theirs = k.me.get(url), k.nobody.get(url)
                k.a_read(mine, theirs)
                assert NAME in mine.get_data(as_text=True), (kind, fmt)
        listed = json.loads(k.me.get(
            f"/v2/history/export/calls/json?{q}").get_data(as_text=True))
        (row,) = [x for x in listed["rows"] if call["id"] in json.dumps(x)]
        assert NAME in json.dumps(row), row


# ── the table against the tests ──────────────────────────────────────────────────────────────

def _slug(write: str) -> str:
    return "test_" + re.sub(r"[^a-z0-9]+", "_", write.lower()).strip("_")


def _walk_classes() -> dict:
    """``{objective: [class, ...]}`` of this file's walk classes."""
    out = {}
    for obj in globals().values():
        if isinstance(obj, type) and obj.__module__ == __name__ and hasattr(obj, "OBJECTIVE"):
            out.setdefault(obj.OBJECTIVE, []).append(obj)
    return out


def _calls_on_k(fn_node) -> set:
    """The `Kit` methods a walk's body calls on ``k`` (parsed, never matched as text)."""
    return {n.func.attr for n in ast.walk(fn_node)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and isinstance(n.func.value, ast.Name) and n.func.value.id == "k"}


def test_every_write_in_the_table_is_walked_and_asserts_the_control_its_row_says():
    classes = _walk_classes()
    assert sorted(classes) == sorted(WALKS), "an objective with no class, or a class with no row"
    with open(os.path.abspath(__file__), encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    bodies = {(c.name, f.name): f for c in tree.body if isinstance(c, ast.ClassDef)
              for f in c.body if isinstance(f, ast.FunctionDef)}
    walked = 0
    for objective, writes in WALKS.items():
        tests = {name: cls.__name__ for cls in classes[objective] for name in vars(cls)
                 if name.startswith("test_")}
        assert sorted(tests) == sorted(_slug(w) for w in writes), objective
        for write, control in writes.items():
            name = _slug(write)
            called = _calls_on_k(bodies[(tests[name], name)])
            assert called & set(CONTROLS.values()) == {CONTROLS[control]}, (objective, write)
            records = called & {"recorded", "recorded_by_name"}
            wanted = control != A_READ and (objective, write) not in KEEPS_NO_RECORD_HERE
            assert bool(records) == wanted, (objective, write, sorted(called))
            walked += 1
    assert set(KEEPS_NO_RECORD_HERE) <= {(o, w) for o, ws in WALKS.items() for w in ws}
    assert walked == sum(len(w) for w in WALKS.values()) >= 40
