"""C543, C544: a Needs attention row about a deploy offers the action its OUTCOME needs, on v2.

C543 (C537's survey, 2026-10-06): `deploy_source` gave one action, "Read its receipt … then
plan again", to every deploy that did not finish clean, including a change that passed verify
and was NOT saved to startup (a reload loses it), whose remedy is Persist; the deploy's result
card said Persist and the row did not. Now that outcome is its own kind, `deploys/unsaved`,
whose action opens Persist on the device's v2 page, and a save of the device read back SAFE
after the deploy clears it. Any other fault reads the receipt on the device's History tab and
plans again, offering Persist too when the change is also unsaved.

C544: the rollback block's row said Revert and Retry had "no screen yet (7.3's Device
actions)"; both are cards on the v2 device page since 7.3. It offers both, as the result card.

Each outcome is a REAL receipt: the real `/deploy/apply` route, the real `_deploy_one`, the
real pipeline runner with its real save stage and the real save judgement
(`onboard.persist_on_device`) over a session answering with s4's captured configuration
(tests/fixtures/configs/fleet/s4.cfg). Only the stages that need a device (the snapshots, the
push, verify, the rollback, the golden) are stubbed, each setting what its real stage records.
The rows are read by the real reader (`attention.deploy_source`, `rollback_source`) and drawn
by `v2/_attention.html`.
"""

import os
import time

import pytest

from modules import attention as A
from tests import payload_providers as P
# test_device_revert_retry_v2's served lab with a block standing, and the fixtures it needs.
from tests.test_device_revert_retry_v2 import blocked, page  # noqa: F401
from tests.test_intent_ops import classify, lab  # noqa: F401

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S4_CFG = os.path.join(ROOT, "tests", "fixtures", "configs", "fleet", "s4.cfg")
IP = "203.0.113.24"
#: IOS's own answer to `show startup-config` when NVRAM holds none.
NO_STARTUP = "startup-config is not present\n"
#: The verify a passing s4 records (payload_providers.deploy_apply's, the real shape).
VERIFY_OK = {"ok": True, "issues": [], "checked_protocols": ["ospf"],
             "pre": {"routing_protocol": "ospf", "routing_neighbors": 5,
                     "routing_protocols": {"ospf": 5}, "routes": 13, "interfaces_up": 7},
             "post": {"routing_protocol": "ospf", "routing_neighbors": 5,
                      "routing_protocols": {"ospf": 5}, "routes": 13, "interfaces_up": 7}}


def _s4() -> str:
    with open(S4_CFG, encoding="utf-8") as fh:
        return fh.read()


class _Session:
    """A device session answering `persist_on_device`'s reads with s4's captured config: its
    username lines for `show running-config | include ^username`, and *startup* for
    `show startup-config`."""

    def __init__(self, startup: str):
        self.startup = startup

    def enable(self):
        return ""

    def save_config(self):
        return "Building configuration...\n[OK]"

    def send_command(self, cmd, read_timeout=None):
        if cmd == "show startup-config":
            return self.startup
        assert cmd == "show running-config | include ^username", cmd
        return "\n".join(l for l in _s4().splitlines() if l.startswith("username "))

    def disconnect(self):
        return None


@pytest.fixture
def store(monkeypatch, tmp_path):
    """This test's own receipts and save record: the session's store holds other tests'."""
    monkeypatch.setattr("modules.config.list_data_path",
                        lambda name: str(tmp_path / "lists" / name))
    monkeypatch.setattr("modules.config.DATA_DIR", str(tmp_path))
    return tmp_path


def _pipeline(mp, *, startup: str, verify: dict = None, verify_fails: str = ""):
    """The real runner with its device stages stubbed, each recording what its real stage
    does; the save stage is real, its session answering with *startup*."""
    import modules.pipeline as PL
    from modules.pipeline import STAGE_NAMES, PipelineStageError

    for name in STAGE_NAMES:
        if name in ("save_startup",):
            continue

        def stage(ctx, _n=name):
            if _n == "deploy":
                ctx.push_results = {IP: {"ok": True, "output": ""}}
            elif _n == "verify":
                ctx.verify_result = {IP: dict(verify or VERIFY_OK)}
                if verify_fails:
                    raise PipelineStageError(verify_fails)
        mp.setattr(PL, f"_stage_{name}", stage)

    def rollback(ctx):
        ctx.rollback_performed = True
        ctx.rollback_outcome = {IP: {"state": "restored", "detail": "read back: nothing "
                                     "left to undo"}}
        ctx.final_status = "rolled_back"
    mp.setattr(PL, "_stage_rollback", rollback)
    mp.setattr(PL, "_capture_failure_state", lambda ctx: None)
    mp.setattr("modules.connection.open_ssh", lambda params, owner="": _Session(startup))


def _apply(mp, **pipeline):
    """payload_providers.deploy_apply's plan and apply of s4, through the REAL `_deploy_one`:
    the lab's inventory row carries the driver and account the save opens a session with."""
    import routes.deploy as rd
    from modules.nsot.render_artifact import build_artifact
    from tests import test_p3_wizard_draws_the_program as w

    from modules.device import fernet

    P.deploy_plan(mp)
    # As the inventory stores a row: its credential fields Fernet-encrypted.
    stored = {"password": fernet.encrypt(b"unused").decode(),
              "secret": fernet.encrypt(b"").decode()}

    def _fake(list_name, hostname, cache=None):
        artifact = build_artifact(hostname, w.CAPTURE, "cisco_ios", template_approved=True)
        return (artifact, w.CAPTURE, {"hostname": hostname, "ip": IP,
                                      "device_type": "cisco_ios", "username": "admin",
                                      **stored}), ""
    mp.setattr(rd, "_artifact_for", _fake)
    _pipeline(mp, **pipeline)
    mp.setattr(rd, "_commit_batch_golden", lambda *a, **k: {
        "ok": True, "commit": "0123456789abcdef0123", "devices": ["s4"],
        "tags": ["golden/s4/20260927T000000Z"], "baseline": False,
        "baseline_reasons": ["the batch targeted 1 of 9 inventory devices"]})
    auth = {"s4": [{"line": "shutdown", "reason": "planned maintenance, port unused"}]}
    plan = P._ok(P._client().post("/deploy/plan", json={"devices": ["s4"], "authorise": auth}))
    device = plan["devices"][0]
    out = P._ok(P._client().post("/deploy/apply", json={
        "confirmations": {"s4": device["capture_hash"]},
        "command_hashes": {"s4": device["command_hash"]}, "authorise": auth}))
    from modules.config import get_current_list_name
    from modules.nsot import receipts
    (row,) = [r for r in receipts.read(get_current_list_name())["rows"]
              if r.get("device") == "s4"][:1]
    return out, row


def _s4_rows(res):
    return [r for r in res["rows"] if r["devices"] == ["s4"]]


def _drawn(r) -> str:
    """The row's action, as Needs attention draws it."""
    from flask import render_template

    import app as APP
    with APP.app.test_request_context("/v2/"):
        html = render_template("v2/_attention.html", a={
            "ok": True, "rows": [r], "sources": [], "headline": "1", "counts": {},
            "badge": {"n": 1, "level": r["level"]}})
    return html.split('class="att-action"')[1].split('class="att-ack"')[0]


def _persist(startup: str, *, earlier_by: int = 0):
    """A save of s4 through the real judgement and the real recorder, as the device page's
    Persist records it; *earlier_by* seconds back on the recorder's clock."""
    from modules.nsot import onboard

    got = onboard.persist_on_device(IP, "admin", "unused", "", "cisco_ios",
                                    connect=lambda **p: _Session(startup))
    real = time.gmtime
    if earlier_by:
        time.gmtime = lambda *a: real(*a) if a else real(time.time() - earlier_by)
    try:
        onboard._record_native_persist("s4", got, "op@example.invalid", via="device page")
    finally:
        time.gmtime = real
    return got


class TestNotSavedToStartupOffersPersist:
    """C543: verified, running and NOT saved to startup."""

    def test_the_receipt_is_the_real_shape(self, monkeypatch, store):
        _out, row = _apply(monkeypatch, startup=NO_STARTUP)
        assert row["outcome"] == "deployed" and row["stage"] == "save_startup", row
        assert row["saved_startup"] == {
            "state": "not_saved",
            "detail": "after write memory the device still has NO startup config"}

    def test_its_row_is_persist_on_the_v2_device_page(self, monkeypatch, store):
        _apply(monkeypatch, startup=NO_STARTUP)
        res = A.deploy_source()
        (r,) = _s4_rows(res)
        assert (r["kind"], r["level"]) == ("unsaved", "warning"), r
        assert "NOT saved to startup" in r["what"] and "done" not in r["what"]
        assert "NO startup config" in r["cause"]
        assert r["action"].get("open") == "persist" and r["action"]["device"] == "s4"
        assert "plan again" not in r["action"]["label"]
        assert "Persist" in r["clears"]["when"]
        drawn = _drawn(r)
        assert 'href="/v2/device/s4?list=' in drawn and "op=persist" in drawn, drawn
        assert ">Persist s4…</a>" in drawn

    def test_a_save_read_back_after_it_clears_it(self, monkeypatch, store):
        _apply(monkeypatch, startup=NO_STARTUP)
        assert _persist(_s4())["ok"] is True
        res = A.deploy_source()
        assert _s4_rows(res) == [], res["rows"]
        assert "1 not saved to startup by the deploy and saved since" in res["checked"]

    def test_a_save_that_did_not_read_back_safe_leaves_it(self, monkeypatch, store):
        _apply(monkeypatch, startup=NO_STARTUP)
        assert _persist(NO_STARTUP)["ok"] is False
        assert [r["kind"] for r in _s4_rows(A.deploy_source())] == ["unsaved"]

    def test_a_save_before_the_deploy_leaves_it(self, monkeypatch, store):
        assert _persist(_s4(), earlier_by=3600)["ok"] is True
        _apply(monkeypatch, startup=NO_STARTUP)
        assert [r["kind"] for r in _s4_rows(A.deploy_source())] == ["unsaved"]

    def test_saved_to_startup_is_no_row(self, monkeypatch, store):
        _out, row = _apply(monkeypatch, startup=_s4())
        assert row["saved_startup"]["state"] == "saved"
        res = A.deploy_source()
        assert _s4_rows(res) == [] and "1 clean" in res["checked"]


class TestAnotherFaultBesidesTheSave:
    """Verify did not pass without failing (intent declares a protocol still not up), and the
    save did not land: read the receipt and plan again, with Persist offered too."""

    def test_it_reads_the_receipt_and_offers_persist(self, monkeypatch, store):
        unmet = dict(VERIFY_OK, ok=False, intent_unmet=["bgp"])
        _out, row = _apply(monkeypatch, startup=NO_STARTUP, verify=unmet)
        assert row["outcome"] == "deployed" and row["checks"]["ok"] is False
        (r,) = _s4_rows(A.deploy_source())
        assert r["kind"] == "failed" and r["level"] == "danger"
        assert "declared by intent and not up after: bgp" in r["cause"]
        assert "NOT saved to startup" in r["cause"]
        assert "History tab" in r["action"]["label"] and "plan again" in r["action"]["label"]
        assert r["action"].get("open") == "persist"
        assert ">Persist s4…</a>" in _drawn(r)


class TestRolledBackReadsItsReceipt:
    """Verify failed and the rollback restored s4: nothing ran unsaved, so no Persist."""

    def test_it_reads_the_receipt_on_v2_and_offers_no_persist(self, monkeypatch, store):
        _out, row = _apply(monkeypatch, startup=_s4(), verify_fails="ospf: 5 -> 3 neighbours")
        assert row["outcome"] == "failed" and row["rollback"]["performed"] is True
        assert row["saved_startup"]["state"] == "not_run"
        (r,) = _s4_rows(A.deploy_source())
        assert r["kind"] == "failed" and "rollback: restored" in r["cause"]
        assert "open" not in r["action"] and "NOT saved" not in r["cause"]
        assert r["action"]["href"] == "/v2/device/s4?tab=history"
        assert 'href="/v2/device/s4?tab=history">Open…</a>' in _drawn(r)


class TestTheRollbackBlockOffersRevertAndRetry:
    """C544, on test_rollback_block_enforced's lab: r2's real config and committed intent, a
    block planted by the real recorder on the program the real plan computes."""

    @pytest.fixture
    def planted(self, monkeypatch, tmp_path):
        from tests.test_capture import build_capture_lab
        from tests.test_rollback_block_enforced import _plant, _program, _set_description

        lab = build_capture_lab(monkeypatch, tmp_path)
        _set_description(lab["repo"], "GigabitEthernet2", "C118-FAILED-CHANGE")
        _artifact, failed = _program(lab["repo"])
        _plant(lab["repo"], failed)
        monkeypatch.setattr("modules.config.get_current_list_name", lambda: "Lab")
        return lab

    def test_both_ways_out_are_drawn_as_v2_links(self, planted):
        (r,) = A.rollback_source()["rows"]
        assert r["action"]["known"] is True
        drawn = _drawn(r)
        assert "no screen" not in drawn and "7.3" not in drawn
        assert ('href="/v2/device/r2?list=Lab&amp;op=revert">Revert intent…</a>' in drawn), drawn
        assert ('href="/v2/device/r2?list=Lab&amp;op=retry">Retry with a reason…</a>'
                in drawn), drawn
        assert 'data-next-acts="revert"' in drawn and 'data-next-acts="retry"' in drawn
        assert "is not on these pages yet" not in drawn


class TestEachWayOutOpensItsCard:
    """C544's two links, loaded as a browser without script loads them, on
    test_device_revert_retry_v2's served lab (r2 in 'Lab', a block standing): the device page
    with that card open in place of the tab."""

    @pytest.mark.parametrize("op, heading", [("revert", "Revert a change to r2"),
                                             ("retry", "Retry the blocked change on r2")])
    def test_each_link_opens_its_card(self, blocked, monkeypatch, op, heading):
        import re

        monkeypatch.setattr("modules.config.get_current_list_name", lambda: "Lab")
        (r,) = A.rollback_source()["rows"]
        drawn = _drawn(r)
        found = re.search(rf'href="(/v2/device/[^"]*op={op})"', drawn)
        assert found, f"no v2 link opening {op}: {drawn}"
        href = found.group(1).replace("&amp;", "&")
        page = blocked["client"].get(href)
        assert page.status_code == 200, href
        assert heading in page.get_data(as_text=True)


