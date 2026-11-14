"""Board R's R8 (provisional, operator review pending; the operator, 2026-11-13: "the probe as a
Mercury action recorded in History"): Probe the read-only account… as a Mercury operation
(`modules/nsot/read_account_op.py` over the probe's one home, `modules/read_account_probe.py`,
which the command line runs too), on tests/test_read_account_probe.py's lab: a credential store
in the test's own folder, the inventory, committed intent and golden, the device hold recorded,
and a stand-in device at the session seam. No device is reached.

- **The preview** is the probe's own plan: whom it signs in as (never the password), every
  command in order, the program's hash; it says when a confirm would be refused now (one of the
  installation's no-change windows, a device another operation holds), and touches no device
  (nothing opened).
- **The confirm** is refused, naming both hashes, when the program moved, and inside a
  no-change window, with nothing opened; else the probe runs holding the device, and its record is
  written under the device's network and identity (`record_dir`), masked, never the password.
- **The record** is read again: History's "Read-only account probes" draws it for the device,
  and the coverage's Last probe reads it; a record under another identity of the same name is
  not this device's.
- **The routes** preview, confirm by hash as a person, and draw the verdict in place.

IPv6: nothing here parses an address; the probe's reads carry IPv4 and IPv6 forms alike.
"""

import json
import os

import pytest

from modules.read_account_probe import no_change_now as NO_CHANGE_NOW
from tests.test_read_account_probe import HOST, NET, RO_PW, Device, lab  # noqa: F401

#: The installation's no-change windows (`change_windows`): two halves of the day, so any now
#: is in one (a single window is [start, end) and always leaves a minute out).
WINDOWS = [{"start": "00:00", "end": "12:00", "reason": "a nightly backup"},
           {"start": "12:00", "end": "00:00", "reason": "a nightly backup"}]


@pytest.fixture
def op(lab, monkeypatch):  # noqa: F811
    """The operation and the probe, where they exist. On this commit's parent they do not: the
    fixture then hands each test a stand-in that raises the import's own error at first use,
    so the test's body fails (red), never its setup."""
    try:
        from modules.nsot import read_account_op as RAO
        from modules import read_account_probe as P
    except ImportError as exc:
        RAO = P = _Absent(exc)
    else:
        monkeypatch.setattr(P, "identity_of", lambda network, host, repo="": "uid:probe-test-0001")
    lab["device"] = Device(lab["log"])
    return {"RAO": RAO, "P": P, "lab": lab}


class _Absent:
    """A module this test needs and the tree lacks: any use raises the import's error."""

    def __init__(self, exc):
        self._exc = exc

    def __getattr__(self, name):
        raise ImportError(f"{self._exc} (asked for {name})")


def _job(job):
    from modules.nsot import capture_job
    assert capture_job.wait(job, 20)
    return capture_job.get(job)["payload"]


class TestThePreview:
    def test_it_is_the_probe_s_own_plan_and_opens_nothing(self, op):
        p = op["RAO"].preview(NET, HOST)
        assert p["ok"] and p["hash"] == op["P"].plan(NET, HOST, {})["hash"]
        assert p["lines"] == op["P"].preview_lines(op["P"].plan(NET, HOST, {}))
        assert p["account"]["username"] and RO_PW not in json.dumps(p)
        assert op["lab"]["opened"] == [] and p["now"] == ""

    def test_inside_a_no_change_window_it_says_a_confirm_is_refused_now(self, op, monkeypatch):
        monkeypatch.setattr("modules.change_windows.windows", lambda: list(WINDOWS))
        # The lab answers no window of its own; the product's own reading of the setting here.
        monkeypatch.setattr(op["P"], "no_change_now", NO_CHANGE_NOW)
        assert "no-change window" in op["RAO"].preview(NET, HOST)["now"]
        assert "(a nightly backup)" in op["RAO"].preview(NET, HOST)["now"]

    def test_a_device_with_nothing_to_probe_is_refused_by_name(self, op):
        p = op["RAO"].preview(NET, "nowhere")
        assert not p["ok"] and "nowhere is not a device of" in p["refused"]


class TestTheConfirm:
    def test_a_moved_program_opens_nothing_and_names_both_hashes(self, op):
        run = _job(op["RAO"].start(NET, HOST, "0" * 64, "op@example.com"))
        assert run["state"] == "refused" and "000000000000 ->" in run["error"]
        assert op["lab"]["opened"] == []

    def test_inside_a_no_change_window_it_opens_nothing(self, op, monkeypatch):
        h = op["RAO"].preview(NET, HOST)["hash"]
        monkeypatch.setattr("modules.change_windows.windows", lambda: list(WINDOWS))
        # The lab answers no window of its own; the product's own reading of the setting here.
        monkeypatch.setattr(op["P"], "no_change_now", NO_CHANGE_NOW)
        run = _job(op["RAO"].start(NET, HOST, h, "op@example.com"))
        assert run["state"] == "refused" and "(a nightly backup)" in run["error"]
        assert op["lab"]["opened"] == []

    def test_it_runs_holding_the_device_and_records_by_identity(self, op):
        h = op["RAO"].preview(NET, HOST)["hash"]
        run = _job(op["RAO"].start(NET, HOST, h, "op@example.com"))
        assert run["state"] == "done", run
        assert [k for k, _v in op["lab"]["log"]][:1] == ["hold"]
        folder = op["P"].record_dir(NET, "uid:probe-test-0001")
        (name,) = os.listdir(folder)
        assert name == run["record"]
        rec = json.loads(open(os.path.join(folder, name), encoding="utf-8").read())
        assert rec["identity"] == "uid:probe-test-0001" and rec["actor"] == "op@example.com"
        assert RO_PW not in open(os.path.join(folder, name), encoding="utf-8").read()
        assert run["rec"]["result"] == rec["verdict"]["result"]


class TestTheRecordIsReadAgain:
    def test_history_and_the_coverage_read_it_and_another_identity_does_not(self, op,
                                                                           monkeypatch):
        import types

        from modules import history_sources as HS

        h = op["RAO"].preview(NET, HOST)["hash"]
        run = _job(op["RAO"].start(NET, HOST, h, "op@example.com"))
        got = op["RAO"].newest(NET, HOST)
        assert got["result"] == run["rec"]["result"] and got["file"] == run["record"]
        assert op["RAO"].newest(NET, HOST, identity="uid:another-device") == {}
        ctx = {"ref": types.SimpleNamespace(name=NET), "device": HOST, "members": None,
               "limit": 50, "since": None, "until": None}
        (event,) = HS.read_account_probes(ctx)["events"]
        assert event["kind"] == "read_account_probe" and event["devices"] == [HOST]
        assert run["rec"]["result"] in event["what"]
        assert HS.SOURCE_KINDS["read_account_probes"] == ("read_account_probe",)


class TestTheRoutes:
    def test_preview_confirm_and_the_verdict_in_place(self, op, monkeypatch):
        import app as A

        client = A.app.test_client()
        base = "/v2/credentials/profiles/read-account/probe"
        page = client.get(f"{base}?network={NET}&device={HOST}").get_data(as_text=True)
        assert "data-ra-probe-lines" in page and RO_PW not in page
        h = page.split('name="hash" value="', 1)[1].split('"', 1)[0]
        assert h == op["RAO"].preview(NET, HOST)["hash"]
        r = client.post(base, data={"network": NET, "device": HOST, "hash": h})
        assert r.status_code == 202
        job = r.get_data(as_text=True).split("/probe/job/", 1)[1].split("?", 1)[0]
        run = _job(job)
        card = client.get(f"{base}/job/{job}?network={NET}&device={HOST}").get_data(
            as_text=True)
        assert "data-ra-probe-verdict" in card and run["rec"]["result"] in card
        assert run["record"] in card
