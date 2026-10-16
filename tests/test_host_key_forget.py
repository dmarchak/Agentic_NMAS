"""C940: a device that leaves forgets the SSH host key Mercury kept for its address.

Mercury keeps a device's SSH host key on first contact and refuses a different one (C906).
Retire and Abandon kept the key of the device that left, so the next machine at its address
(a reused address, a throwaway onboarding) was refused as a changed key, and a pending device
has no page to re-key from: onboarding there was blocked with no remedy in the interface.

Through the REAL routes (the device page's Retire card and its confirm; the pending page's
Abandon preview and its confirm), against a real repository, inventory, manifest and host-key
record:

- the preview names the key it forgets (its address and fingerprint), the confirm forgets it
  through the one write path (`host_keys.forget`, under the record's lock), and the key stays
  in the record's history with when, who and why ("r5 retired by <person>: <reason>");
- the next machine to answer at that address is a FIRST CONTACT: its key is kept, its
  credential sent (a real SSH server records it), the forgotten key still in the history,
  and History draws the forget;
- an address another device in another network also has keeps its key, and the preview and
  the result say so naming both devices.
"""

import html as html_mod
import json
import os
import re

import paramiko
import pytest

from modules import connection as C
from modules import host_keys as HK
from tests.conftest import TEST_PERSON
from tests.test_device_retire_v2 import _card, _part, _vals, exported, page  # noqa: F401
from tests.test_host_keys import IP, PW, SSHServer, _params
from tests.test_onboard_abandon import _onboard, repo  # noqa: F401
from tests.test_onboard_v2 import client, person  # noqa: F401
from tests.test_retire import world  # noqa: F401
from tests.test_retire_screen import REASON, screen  # noqa: F401

R5 = "192.0.2.15"


def _key():
    return paramiko.ECDSAKey.generate()


def _fp(key) -> str:
    return HK.offered(key)["fingerprint"]


def _keep(ip, key):
    """The address's first contact, through the policy every session asks (`check`)."""
    assert HK.check(ip, key, owner="test:first-contact")["state"] == "kept"


def _other_network(tmp_path, monkeypatch, lab_dir, lab_name, host, ip):
    """A second network, "Other", whose inventory has *host* at *ip*: each network resolves
    to its own folder, as `config.get_list_data_dir` resolves them on a host."""
    from modules import device

    other = tmp_path / "other"
    other.mkdir()
    device.write_devices_csv([{"hostname": host, "device_type": "cisco_xe", "ip": ip,
                               "username": "admin", "password": "", "secret": "",
                               "platform": "cisco_iosxe"}], str(other / "devices.csv"))
    dirs = {lab_name: str(lab_dir), "Other": str(other)}
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda n: dirs[n])
    monkeypatch.setattr("modules.device.get_device_lists",
                        lambda: [{"name": lab_name, "filename": os.path.basename(str(lab_dir))},
                                 {"name": "Other", "filename": "other"}])


def _steps(card) -> list:
    return [html_mod.unescape(s) for s in
            re.findall(r"<li>(.*?)</li>", _part(card, "What retire changes, in order"))]


class TestRetireForgetsTheKey:
    def test_the_preview_names_it_and_the_confirm_forgets_it_recorded(self, exported):
        old = _key()
        _keep(R5, old)
        _r, card = _card(exported)
        named = [s for s in _steps(card) if "SSH host key" in s]
        assert len(named) == 1, f"the preview does not name the key it forgets: {_steps(card)}"
        line = named[0]
        assert line.startswith(f"forget the SSH host key Mercury kept for {R5}: {_fp(old)}"), line
        assert _steps(card)[-1].startswith("delete the CSV row"), "the row still goes last"
        r = exported["client"].post("/v2/device/r5/retire/confirm", data=_vals(card))
        out = r.get_data(as_text=True)
        assert r.status_code == 200 and "r5 is retired" in out, out[:600]
        steps = dict((k, s) for s, k in re.findall(
            r'<li class="run-step run-step-([a-z_]+)" data-step="([a-z_]+)"', out))
        assert steps.get("host_key") == "done", steps
        assert HK.held(R5) is None, "the key is still held"
        rec = HK.read()["keys"][R5]
        (gone,) = rec["history"]
        assert gone["fingerprint"] == _fp(old) and gone["forgotten"] is True
        assert (gone["device"], gone["network"]) == ("r5", "Lab")
        assert gone["replaced_by"] == TEST_PERSON
        assert gone["replaced_why"] == f"r5 retired by {TEST_PERSON}: {REASON}"
        assert rec["forgotten_by"] == TEST_PERSON and rec["forgotten_at"]

    def test_the_next_machine_there_is_a_first_contact_and_history_draws_both(self, exported):
        from modules import history_sources
        from modules.nsot.listref import resolve

        old, new = _key(), _key()
        _keep(R5, old)
        _r, card = _card(exported)
        exported["client"].post("/v2/device/r5/retire/confirm", data=_vals(card))
        try:
            got = HK.check(R5, new, owner="test:the next machine")
        except HK.HostKeyRefused as exc:
            pytest.fail(f"the next machine at the address was refused: {exc}")
        assert got["state"] == "kept", got
        rec = HK.held(R5)
        assert rec["fingerprint"] == _fp(new) and rec["how"] == HK.FIRST_CONTACT
        assert [h["fingerprint"] for h in rec["history"]] == [_fp(old)], "the history is kept"
        tl = history_sources.timeline(resolve("Lab"), device="r5", kinds=["hostkeys"])
        said = [(e["what"], e["outcome"]) for e in tl["events"]]
        assert ("SSH host key forgotten", "forgotten") in said, said
        (forgot,) = [e for e in tl["events"] if e["what"] == "SSH host key forgotten"]
        assert forgot["who"] == TEST_PERSON and REASON in forgot["detail"]

    def test_it_forgets_only_the_key_the_preview_named(self, exported):
        """A key re-keyed since the preview: the confirm's plan moved, so nothing is done, and
        the one write path itself refuses a key it was not told (compare-and-swap)."""
        old, new = _key(), _key()
        _keep(R5, old)
        _r, card = _card(exported)
        HK.replace(R5, expected=_fp(old), new=HK.offered(new), by="someone", why="rebuilt")
        out = exported["client"].post("/v2/device/r5/retire/confirm",
                                      data=_vals(card)).get_data(as_text=True)
        assert "the plan changed since you confirmed it" in out
        assert HK.held(R5)["fingerprint"] == _fp(new)
        got = HK.forget(R5, network="Lab", device="r5", by="p", why="w", expected=_fp(old))
        assert got["state"] == "moved" and not got["ok"], got
        assert _fp(new) in got["error"] and _fp(old) in got["error"], "both are named"
        assert HK.held(R5)["fingerprint"] == _fp(new), "a key nobody was shown was forgotten"

    def test_without_the_forget_the_next_machine_is_refused(self, exported):
        """The control: what the forget removes is a real refusal."""
        _keep(R5, _key())
        with pytest.raises(HK.HostKeyRefused):
            HK.check(R5, _key(), owner="test:the next machine")

    def test_an_address_another_network_has_keeps_its_key_named(self, exported, tmp_path,
                                                                 monkeypatch):
        old = _key()
        _keep(R5, old)
        _other_network(tmp_path, monkeypatch, os.path.dirname(exported["repo"]), "Lab",
                       "r9", R5)
        _r, card = _card(exported)
        assert not [s for s in _steps(card) if "SSH host key" in s], "no forget step"
        kept = html_mod.unescape(_part(card, "Not changed"))
        assert (f"SSH host key Mercury kept for {R5} ({_fp(old)}) is KEPT, not forgotten: "
                f"r5 in Lab leaves, and {R5} is also the address of r9 in Other") in kept, kept
        r = exported["client"].post("/v2/device/r5/retire/confirm", data=_vals(card))
        assert "r5 is retired" in r.get_data(as_text=True)
        rec = HK.held(R5)
        assert rec is not None and rec["fingerprint"] == _fp(old) and rec["history"] == []

    def test_an_unreadable_record_refuses_the_retirement(self, exported):
        """Could not read is not nothing there: the gate fails, naming the record."""
        _keep(R5, _key())
        with open(HK.path(), "w", encoding="utf-8") as fh:
            fh.write("{torn")
        os.chmod(HK.path(), 0o600)
        _r, card = _card(exported)
        assert "op-confirm" not in card
        assert "could not be read" in html_mod.unescape(card)


# ---------------------------------------------------------------------------
# Abandon, from the pending device's page, against a real SSH server
# ---------------------------------------------------------------------------

@pytest.fixture
def pending(repo, tmp_path, monkeypatch):  # noqa: F811
    """bp1 pending in 'probe' at the loopback address a real SSH server answers on, its key
    kept by its preview's SSH login (a real Netmiko session through the one opener)."""
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr("modules.config.DATA_DIR", str(data))
    monkeypatch.setattr(C, "vty_lines", lambda ip: (5, "the test's device"))
    list_dir = os.path.dirname(repo)
    monkeypatch.setattr("modules.device.get_device_lists",
                        lambda: [{"name": "probe", "filename": "probe"}])
    monkeypatch.setattr("modules.netbox_client.remove_device_from_netbox",
                        lambda *a, **k: {"ok": True, "deleted": [], "skipped": [],
                                         "message": "none"})
    _onboard(repo, ip=IP)
    servers = [SSHServer(paramiko.RSAKey.generate(2048)) for _ in range(2)]
    _sign_in(servers[0])
    C._sessions.clear()
    yield {"repo": repo, "servers": servers, "dir": list_dir}
    C._sessions.clear()
    for s in servers:
        s.close()


def _sign_in(server):
    """One session through the ONE opener; the servers refuse every password, so a session
    that got as far as signing in raises Netmiko's authentication failure."""
    from netmiko.exceptions import NetmikoAuthenticationException
    with pytest.raises(NetmikoAuthenticationException):
        C.open_ssh(_params(server), owner="test:session")


def _abandon(client, preview_must=""):  # noqa: F811
    pv = client.post("/v2/onboard/bp1/abandon/preview",
                     data={"list_name": "probe"}).get_data(as_text=True)
    if preview_must:
        assert preview_must in html_mod.unescape(pv), pv[:2000]
    fp = re.search(r'name="fingerprint" value="([0-9a-f]{64})"', pv).group(1)
    r = client.post("/v2/onboard/bp1/abandon", data={"list_name": "probe", "fingerprint": fp})
    return r, r.get_data(as_text=True)


def _runs(repo):
    from modules.nsot.onboard import runs_path
    with open(runs_path(repo), encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


class TestAbandonForgetsTheKey:
    def test_it_forgets_it_and_the_next_machine_is_a_first_contact(self, client, pending,
                                                                    person):  # noqa: F811
        servers = pending["servers"]
        held = HK.held(IP)["fingerprint"]
        r, out = _abandon(client, f"host_key: would forget the SSH host key Mercury kept "
                                  f"for {IP}: {held}")
        assert r.status_code == 200 and "is abandoned" in out, out[:1500]
        assert HK.held(IP) is None
        rec = HK.read()["keys"][IP]
        (gone,) = rec["history"]
        assert gone["fingerprint"] == held and gone["forgotten"] is True
        assert gone["replaced_by"] == person.actor
        assert gone["replaced_why"] == f"bp1's onboarding abandoned by {person.actor}"
        # The run's record names the step.
        (run,) = _runs(pending["repo"])
        (step,) = [s for s in run["steps"] if s["step"] == "host_key"]
        assert step["ok"] and f"forgot the SSH host key Mercury kept for {IP}" in step["detail"]
        # The next machine at the address: kept as a first contact, its credential sent.
        try:
            _sign_in(servers[1])
        except HK.HostKeyRefused as exc:
            pytest.fail(f"the next machine at the address was refused: {exc}")
        assert servers[1].offered == [("admin", PW)], "the next machine was sent nothing"
        now = HK.held(IP)
        assert now["how"] == HK.FIRST_CONTACT and now["fingerprint"] != held
        assert [h["fingerprint"] for h in now["history"]] == [held]

    def test_without_the_forget_the_next_machine_is_refused(self, pending):
        """The control: the key the preview kept refuses another machine there."""
        with pytest.raises(HK.HostKeyRefused):
            C.open_ssh(_params(pending["servers"][1]), owner="test:session")
        assert pending["servers"][1].offered == []

    def test_an_address_another_network_has_keeps_its_key_named(self, client, pending, person,
                                                                 tmp_path,
                                                                 monkeypatch):  # noqa: F811
        held = HK.held(IP)["fingerprint"]
        _other_network(tmp_path, monkeypatch, pending["dir"], "probe", "r9", IP)
        words = (f"the SSH host key Mercury kept for {IP} ({held}) is KEPT, not forgotten: "
                 f"bp1 in probe leaves, and {IP} is also the address of r9 in Other")
        r, out = _abandon(client, words)
        assert r.status_code == 200 and "is abandoned" in out, out[:1500]
        # The run's record says it too (the result card draws the summary; History and the
        # pending page's last run read this record).
        (run,) = _runs(pending["repo"])
        (step,) = [s for s in run["steps"] if s["step"] == "host_key"]
        assert step["ok"] and words in step["detail"], step
        assert HK.held(IP)["fingerprint"] == held and HK.held(IP)["history"] == []

    def test_an_unreadable_record_keeps_the_name_so_abandon_can_run_again(
            self, client, pending, person):  # noqa: F811
        """A released name cannot be abandoned again, so a key that could not be forgotten
        keeps the name: the step says why and how to finish."""
        from modules.nsot import manifest
        with open(HK.path(), "w", encoding="utf-8") as fh:
            fh.write("{torn")
        os.chmod(HK.path(), 0o600)
        r, out = _abandon(client, "host_key: Mercury's record of SSH host keys")
        assert r.status_code == 409, out[:1500]
        assert manifest.find_by_name(pending["repo"], "bp1")[0], "the name was released"
        (run,) = _runs(pending["repo"])
        (step,) = [s for s in run["steps"] if s["step"] == "host_key"]
        assert not step["ok"] and "could not be read" in step["detail"], step
        (ident,) = [s for s in run["steps"] if s["step"] == "identity"]
        assert not ident["ok"] and "not released" in ident["detail"], ident
