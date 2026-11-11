"""Re-subscribe a telemetry stream (C2838; modules/heal/resubscribe.py), and the receiver read and
the stream's series it is verified by (C2890, C2892).

On real captures, each edit said beside it:
- **the intent and the running configuration:** r2's real configuration
  (tests/fixtures/configs/fleet/r2.cfg) and its intent parsed by the real parser
  (tests/test_heal_diagnose.py's `fleet`): subscriptions 101 and 102, each with its receiver;
- **the device's receiver:** `show telemetry ietf subscription <id> receiver` read through the
  reads engine on r2 (Connected on connection 984, streaming) and r7 (Connected on connection 496,
  NOT streaming), 2026-11-10 (tests/fixtures/diagnose/README.md). A re-subscribe that worked is
  r2's capture with its connection id 984 written as 985 (the one edit: the new connection);
- **the collector:** the kernel's socket tables and `ss -tni` captures
  (tests/fixtures/diagnose/collector/README.md), a new session after the re-add being the
  device's row copied with its remote port 60235 written as 60999.

The device is a box holding r2's running configuration and changing it as each session's batch
says (a `no receiver` removes that line from its subscription, a `receiver` adds it back), so
the read-backs read what the sends did.
"""
import json
import os

import pytest

from tests.test_heal_diagnose import fleet
from tests.test_heal_diagnose_stream import COLLECTOR, FIX, proc
from tests.test_sdn_connections import networks  # noqa: F401 (the fixture)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ACTOR = "op@example.invalid"
NET = "Default"
R2_CFG = open(os.path.join(ROOT, "tests", "fixtures", "configs", "fleet", "r2.cfg"),
              encoding="utf-8").read()
LINE = "receiver ip address 10.255.1.10 57000 protocol grpc-tcp"
REASON = "r2's streams stay lost after their path came back"
DEV = {"hostname": "r2", "ip": "192.0.2.12", "device_type": "cisco_xe"}


def capture(name: str) -> str:
    with open(os.path.join(FIX, name), encoding="utf-8") as fh:
        return fh.read()


R2_101 = capture("r2__show_telemetry_ietf_subscription_101_receiver.txt")
R2_102 = capture("r2__show_telemetry_ietf_subscription_102_receiver.txt")
R7_101 = capture("r7__show_telemetry_ietf_subscription_101_receiver.txt")
R7_102 = capture("r7__show_telemetry_ietf_subscription_102_receiver.txt")


def new_connection(text: str) -> str:
    """The edit: a re-subscribe that worked reads a new connection id."""
    assert "Connection: 984" in text
    return text.replace("Connection: 984", "Connection: 985")


# ── The device ──────────────────────────────────────────────────────────────────────────────

class Box:
    """r2's running configuration, changed by each batch as IOS-XE changes it. *readd_fails*:
    how many re-adds the device drops; *removes_also*: a line the removal takes with it;
    *ignores_removal_of* and *drops_readd_of*: the subscription ids whose removal, or whose
    every re-add, the device does not take."""

    def __init__(self, text=R2_CFG, readd_fails=0, removes_also="", on_send=None,
                 ignores_removal=False, ignores_removal_of=(), drops_readd_of=()):
        self.lines = text.splitlines()
        self.readd_fails, self.removes_also, self.on_send = readd_fails, removes_also, on_send
        self.ignores_removal = ignores_removal
        self.ignores_removal_of, self.drops_readd_of = set(ignores_removal_of), set(drops_readd_of)
        self.batches, self.opened = [], 0

    def apply(self, batch: str) -> str:
        if self.on_send:
            self.on_send(self, batch)
        lines = batch.split("\n")
        self.batches.append(lines)
        head = None
        for ln in lines:
            if ln.startswith("telemetry ietf subscription "):
                head = ln
            elif ln.startswith(" no ") and head:
                if self.ignores_removal or head.rsplit(" ", 1)[1] in self.ignores_removal_of:
                    continue
                self._drop(head, ln[4:])
                if self.removes_also:
                    self._drop(head, self.removes_also)
            elif ln.startswith(" receiver ") and head:
                if head.rsplit(" ", 1)[1] in self.drops_readd_of:
                    continue
                if self.readd_fails:
                    self.readd_fails -= 1
                    continue
                self._add(head, ln.strip())
        return "r2(config)#\nr2#"

    def _block(self, head):
        i = self.lines.index(head)
        j = i + 1
        while j < len(self.lines) and self.lines[j].startswith(" "):
            j += 1
        return i, j

    def _drop(self, head, line):
        i, j = self._block(head)
        self.lines[i + 1:j] = [x for x in self.lines[i + 1:j] if x.strip() != line.strip()]

    def _add(self, head, line):
        i, j = self._block(head)
        if f" {line}" not in self.lines[i + 1:j]:
            self.lines.insert(j, f" {line}")

    def text(self) -> str:
        return "\n".join(self.lines) + "\n"


class Conn:
    def __init__(self, box):
        self.box = box

    def send_command_timing(self, text, **kw):
        return self.box.apply(text)

    def answer(self, command):
        assert command == "show running-config", command
        return self.box.text()

    def disconnect(self):
        pass


class Clock:
    def __init__(self, t=1_794_250_000.0):
        self.t, self.slept = t, []

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.slept.append(s)
        self.t += s


def seq(items):
    """Each call answers the next item; the last one is kept."""
    items = list(items)
    state = {"n": 0}

    def ask(*_a):
        got = items[min(state["n"], len(items) - 1)]
        state["n"] += 1
        return got() if callable(got) else got
    ask.calls = state
    return ask


def receiver_read(text):
    from modules.heal import diagnose_parse as P
    got = P.parse("telemetry_receiver", text)
    return {"state": "read", "rows": got["facts"]["receivers"], "why": "", "run": ""}


UNREAD = {"state": "unread", "rows": None, "why": "the session failed", "run": ""}
PRESENT = {"state": "present", "count": 1, "why": "1 series with a sample in the last 90 s"}
ABSENT = {"state": "absent", "count": 0, "why": "no sample in the last 90 s"}
UNREAD_SERIES = {"state": "unread", "count": None, "why": "Prometheus is not configured"}


def coll(*sessions, state="read"):
    return {"state": state, "why": "" if state == "read" else "not read here",
            "listening": ["192.0.2.10:57000"], "others": 0, "activity": "read",
            "sessions": [dict(zip(("remote", "rport", "state", "lastrcv_ms"), s))
                         for s in sessions]}


OLD = ("192.0.2.6", 60235, "ESTABLISHED", 5966281)
NEW = ("192.0.2.6", 60999, "ESTABLISHED", 287)


class Src:
    """The operation's sources: the inventory and intent, the box's sessions, and each verify
    read in turn (`seq`)."""

    def __init__(self, box=None, receiver=None, series=None, collector=None, intent_edit=None,
                 clock=None):
        import copy
        from modules.heal.diagnose_stream import _addresses
        self.box = box or Box()
        self.clock = clock or Clock()
        self.sleep = self.clock.sleep
        _model, intents = fleet()
        self._intents = copy.deepcopy(intents)
        if intent_edit:
            intent_edit(self._intents)
        self.receiver = receiver or seq([receiver_read(R2_101), receiver_read(R2_102),
                                         receiver_read(new_connection(R2_101)),
                                         receiver_read(new_connection(R2_102))])
        self.series = series or seq([PRESENT])
        self.collector = collector or seq([coll(OLD), coll(OLD), coll(OLD, NEW)])
        self.addresses = _addresses
        self.network = NET

    def device(self, host):
        return dict(DEV) if host == "r2" else {}

    def intents(self):
        return self._intents, ""

    def opener(self, dev):
        self.box.opened += 1
        return Conn(self.box)

    def values(self):
        return {}


@pytest.fixture
def lab(networks, monkeypatch):  # noqa: F811 (the fixture)
    monkeypatch.setattr("modules.commands.run_device_command",
                        lambda conn, c, read_timeout=None: conn.answer(c))
    monkeypatch.setattr("modules.device.load_saved_devices", lambda path=None: [dict(DEV)])
    return networks


def hashes(src, subs=("101", "102"), readd=False):
    from modules.heal import resubscribe as R
    p = R.plan(NET, "r2", list(subs), readd=readd, sources=src)
    assert p["ok"], p["refusals"]
    return {u["sub"]: u["hash"] for u in p["units"]}


def selection(src, subs=("101", "102"), readd=False):
    """The selection's hash as the card would carry it for *subs*, in that order."""
    from modules.heal import resubscribe as R
    return R.plan(NET, "r2", list(subs), readd=readd, sources=src).get("hash") or ""


def run(src, subs=("101", "102"), reason=REASON, readd=False, confirmed=None, actor=ACTOR,
        actor_verified="access", person=True, program=None, previewed=None):
    """The run as a person the access proxy verified, unless the test says who; confirmed by
    each subscription's hash and the selection's, as the card for *subs* carries them, unless
    the test gives others."""
    from modules.heal import resubscribe as R
    return R.apply(NET, "r2", list(subs), actor=actor, actor_verified=actor_verified,
                   person=person,
                   confirmed=confirmed if confirmed is not None else hashes(src, subs, readd),
                   program=program if program is not None else selection(src, subs, readd),
                   previewed=previewed if previewed is not None else ",".join(subs),
                   reason=reason, readd=readd, sources=src)


def stored(rec):
    from modules.nsot import privileged
    return privileged.get(NET, rec["id"])


# ── The receiver read, on its real captures (C2890) ─────────────────────────────────────────

class TestTheReceiverParser:
    @pytest.mark.parametrize("text,sub,conn", [(R2_101, "101", "984"), (R2_102, "102", "984"),
                                               (R7_101, "101", "496"), (R7_102, "102", "496")])
    def test_each_capture_reads_its_state_and_connection(self, text, sub, conn):
        from modules.heal.diagnose_parse import parse
        got = parse("telemetry_receiver", text)
        assert got["state"] == "parsed", got
        assert got["facts"]["receivers"] == [{
            "subscription": sub, "address": "10.255.1.10", "port": 57000,
            "protocol": "grpc-tcp", "profile": "", "connection": conn, "state": "Connected",
            "explanation": "", "connected": True}]

    def test_streaming_and_not_both_read_connected(self):
        """r7 was not streaming and reads Connected: Connected is not a stream (the README)."""
        from modules.heal.diagnose_parse import parse
        r2 = parse("telemetry_receiver", R2_101)["facts"]["receivers"][0]
        r7 = parse("telemetry_receiver", R7_101)["facts"]["receivers"][0]
        assert r2["state"] == r7["state"] == "Connected"
        assert r2["connection"] != r7["connection"]

    def test_an_ipv6_receiver_address_is_compressed(self):
        from modules.heal.diagnose_parse import parse
        got = parse("telemetry_receiver", R2_101.replace("10.255.1.10", "2001:DB8:0::10"))
        assert got["facts"]["receivers"][0]["address"] == "2001:db8::10"

    def test_a_state_the_device_prints_is_kept_as_printed(self):
        """The Disconnected form is not captured: a state is read as printed, never mapped."""
        from modules.heal.diagnose_parse import parse
        text = R7_101.replace("State: Connected", "State: Disconnected").replace(
            "Explanation: ", "Explanation: Connection is not up")
        r = parse("telemetry_receiver", text)["facts"]["receivers"][0]
        assert (r["state"], r["explanation"], r["connected"]) == (
            "Disconnected", "Connection is not up", False)

    def test_unreadable_and_none_held_are_different(self):
        from modules.heal.diagnose_parse import parse
        assert parse("telemetry_receiver", "")["state"] == "unreadable"
        assert parse("telemetry_receiver", R2_101.split("\n\n")[0] + "\n") == {
            "state": "parsed", "facts": {"receivers": []}, "why": ""}
        no_state = R2_101.replace("  State: Connected\n", "")
        assert parse("telemetry_receiver", no_state)["state"] == "unreadable"
        assert parse("telemetry_receiver", "% Invalid input detected at '^' marker.\n")[
            "state"] == "unsupported"


# ── The plan, the program and the hash ──────────────────────────────────────────────────────

class TestThePlan:
    def test_the_program_is_two_sessions_of_intents_own_line(self, lab):
        from modules.heal import resubscribe as R
        p = R.plan(NET, "r2", ["101"], sources=Src())
        assert p["ok"], p["refusals"]
        (u,) = p["units"]
        assert u["line"] == LINE
        assert u["remove"] == ["configure terminal", "telemetry ietf subscription 101",
                               f" no {LINE}", "end"]
        assert u["readd"] == ["configure terminal", "telemetry ietf subscription 101",
                              f" {LINE}", "end"]
        assert p["program"] == u["remove"] + u["readd"]
        assert p["words"] == "re-subscribe r2's telemetry subscription 101"

    def test_each_hash_is_its_own_and_the_reason_is_in_the_runs(self, lab):
        from modules.heal import resubscribe as R
        from modules.nsot.deploy import command_fingerprint
        p = R.plan(NET, "r2", ["101", "102"], sources=Src())
        a, b = p["units"]
        assert a["hash"] != b["hash"]
        assert a["hash"] == command_fingerprint(a["remove"] + a["readd"], [],
                                                ["resubscribe:telemetry ietf subscription 101"])
        one = R.run_hash(p["units"], REASON)
        assert one != R.run_hash(p["units"], REASON + " again"), "the reason is in the hash"
        assert R.authorised(p["units"], REASON) == [
            {"line": f"no {LINE}", "reason": REASON}] * 2
        assert R.plan(NET, "r2", ["101"], readd=True, sources=Src())["units"][0]["hash"] != \
            a["hash"], "the re-add's hash is its own"

    def test_several_subscriptions_are_one_batch_every_removal_then_every_re_add(self, lab):
        """Two chosen: the program is remove 101, remove 102, then add 101, add 102, each its
        own four lines, never one subscription's removal and re-add before the other's."""
        from modules.heal import resubscribe as R
        p = R.plan(NET, "r2", ["101", "102"], sources=Src())
        a, b = p["units"]
        assert p["program"] == a["remove"] + b["remove"] + a["readd"] + b["readd"]
        assert [ln for ln in p["program"] if "receiver" in ln] == [
            f" no {LINE}", f" no {LINE}", f" {LINE}", f" {LINE}"]
        assert [ln for ln in p["program"] if ln.startswith("telemetry")] == [
            "telemetry ietf subscription 101", "telemetry ietf subscription 102"] * 2

    def test_the_selections_hash_differs_with_the_selection_and_its_order(self, lab):
        """One subscription and two are two programs, so two hashes; each subscription's own
        hash is the same in both; and another order is another program."""
        from modules.heal import resubscribe as R
        one = R.plan(NET, "r2", ["101"], sources=Src())
        two = R.plan(NET, "r2", ["101", "102"], sources=Src())
        other = R.plan(NET, "r2", ["102", "101"], sources=Src())
        hashes_ = [one.get("hash"), two.get("hash"), other.get("hash")]
        assert all(hashes_) and len(set(hashes_)) == 3, hashes_
        assert one["units"][0]["hash"] == two["units"][0]["hash"], "its own hash is its own"
        assert R.run_hash(one["units"], REASON) != R.run_hash(two["units"], REASON)
        assert R.run_hash(two["units"], REASON) != R.run_hash(other["units"], REASON)

    def test_a_subscription_not_chosen_that_shares_the_receiver_is_named(self, lab):
        """Read from intent's own receiver lines: 102 sends to 101's receiver, so choosing 101
        alone names 102 (it may keep their connection); choosing both names nobody; one that
        sends elsewhere is not named."""
        from modules.heal import resubscribe as R
        p = R.plan(NET, "r2", ["101"], sources=Src())
        assert p.get("sharing") == [{"sub": "102", "shares": ["101"],
                                     "address": LINE.split()[3], "port": 57000}]
        assert R.plan(NET, "r2", ["101", "102"], sources=Src()).get("sharing") == []

        def elsewhere(intents):
            for s in intents["r2"]["telemetry"]:
                if str(s["subscription"]) == "102":
                    s["settings"] = [x.replace("57000", "57001") for x in s["settings"]]
        assert R.plan(NET, "r2", ["101"], sources=Src(intent_edit=elsewhere)).get(
            "sharing") == [], "another port is another receiver"

    def test_an_ipv6_receiver_shared_is_named_whatever_its_spelling(self, lab):
        from modules.heal import resubscribe as R

        def edit(intents):
            for s in intents["r2"]["telemetry"]:
                v6 = ("2001:db8::10" if str(s["subscription"]) == "101"
                      else "2001:DB8:0:0:0:0:0:10")
                s["settings"] = [f"receiver ip address {v6} 57000 protocol grpc-tcp"
                                 if x.startswith("receiver ") else x for x in s["settings"]]
        p = R.plan(NET, "r2", ["102"], sources=Src(intent_edit=edit))
        assert p["ok"], p["refusals"]
        assert p.get("sharing") == [{"sub": "101", "shares": ["102"],
                                     "address": "2001:db8::10", "port": 57000}]
        assert p["units"][0]["remove"][2] == (
            " no receiver ip address 2001:DB8:0:0:0:0:0:10 57000 protocol grpc-tcp"), \
            "the line is sent as intent holds it"

    def test_a_confirm_of_another_selection_is_refused_naming_both(self, lab):
        """Each subscription's own hash is right, and the selection's is the one drawn for 101
        alone: confirming 101 and 102 with it is another program, refused, both named."""
        src = Src()
        drawn_for_one, now = selection(src, ("101",)), selection(src, ("101", "102"))
        rec = run(src, subs=("101", "102"), program=drawn_for_one, previewed="101")
        assert rec["state"] == "refused" and rec["outcome"] == "refused", rec["why"]
        assert "the selection is not the one previewed" in rec["why"]
        assert f"{drawn_for_one}, for subscription 101, and" in rec["why"]
        assert f"{now}, for subscription 101 and 102" in rec["why"]
        assert src.box.batches == [] and src.box.opened == 0, "nothing was sent"
        # No selection hash at all is refused the same way; the one drawn is taken.
        rec = run(src, subs=("101", "102"), program="", previewed="")
        assert rec["state"] == "refused" and "no hash, for no named selection" in rec["why"]
        assert src.box.batches == []
        assert run(src, subs=("101", "102"))["outcome"] == "resubscribed"

    def test_an_ipv6_receiver_line_is_sent_as_intent_holds_it(self, lab):
        from modules.heal import resubscribe as R
        v6 = "receiver ip address 2001:db8::10 57000 protocol grpc-tcp"

        def edit(intents):
            for s in intents["r2"]["telemetry"]:
                s["settings"] = [v6 if x.startswith("receiver ") else x for x in s["settings"]]
        p = R.plan(NET, "r2", ["102"], sources=Src(intent_edit=edit))
        assert p["ok"], p["refusals"]
        (u,) = p["units"]
        assert (u["address"], u["port"], u["remove"][2]) == ("2001:db8::10", 57000, f" no {v6}")

    @pytest.mark.parametrize("subs,words", [
        (["103"], "intent declares no telemetry subscription 103 on r2"),
        (["101 | redirect"], "is not a telemetry subscription id"),
        ([], "no subscription was chosen")])
    def test_refusals_name_why_and_send_nothing(self, lab, subs, words):
        from modules.heal import resubscribe as R
        p = R.plan(NET, "r2", subs, sources=Src())
        assert not p["ok"] and words in p["refusals"][0] and p["refusals"][0].endswith(
            "Nothing was sent")

    def test_an_unmeasured_platform_is_refused_by_its_shape(self, lab, monkeypatch):
        from modules.heal import resubscribe as R
        from modules.nsot import removal
        rec = removal.measured()
        rec["by_dialect"] = {d: {k: v for k, v in rows.items() if k != "telemetry.receiver"}
                             for d, rows in rec["by_dialect"].items()}
        monkeypatch.setattr(removal, "measured", lambda: rec)
        p = R.plan(NET, "r2", ["101"], sources=Src())
        assert not p["ok"] and "`telemetry.receiver` has not been measured on cisco_iosxe" in \
            p["refusals"][0]

    def test_the_shape_is_mode_bs_and_measured(self):
        from modules.nsot import removal
        shape = removal.shape_for(["telemetry ietf subscription 101"], f" {LINE}", "leaf")
        assert shape is not None and shape.key == "telemetry.receiver"
        assert removal.shape_refusal(["telemetry ietf subscription 101"], f" {LINE}", "leaf",
                                     "cisco_iosxe") == ""
        assert removal.shape_for([], LINE, "leaf") is None, "only under its subscription"

    def test_a_moved_hash_or_a_short_reason_is_refused_naming_both(self, lab):
        from modules.heal import resubscribe as R
        src = Src()
        rec = run(src, subs=("101",), confirmed={"101": "0" * 16})
        assert rec["state"] == "refused" and "confirmed 0000000000000000, now" in rec["why"]
        rec = run(Src(), subs=("101",), reason="why")
        assert rec["state"] == "refused" and "too short to be a reason" in rec["why"]
        assert src.box.batches == [] and src.box.opened == 0, "nothing was sent"
        assert stored(rec)["state"] == "refused"


# ── Who confirms: a verified person, by either way a request's identity is established ──────

class TestAVerifiedPerson:
    """`person_refusal` is an allowlist of the kinds a request's identity can state
    (`identity.REQUEST_VERIFICATIONS`), typed here so a kind added there is not taken here
    unseen."""

    @pytest.mark.parametrize("kind", ["access", "local-account"])
    def test_a_person_verified_either_way_is_taken_and_recorded_as_that(self, lab, kind):
        from modules import identity
        assert set(identity.REQUEST_VERIFICATIONS) == {"access", "local-account"}
        src = Src()
        rec = run(src, subs=("101",), actor_verified=kind)
        assert rec["outcome"] == "resubscribed", rec["why"]
        assert stored(rec)["actor_verified"] == kind
        assert len(src.box.batches) == 2

    @pytest.mark.parametrize("kind", ["", "none", None, "host-shell", "policy", "ACCESS",
                                      "access ", "local", "unverified", True, 1])
    def test_any_other_kind_is_refused_and_nothing_is_sent(self, lab, kind):
        from modules.heal import resubscribe as R
        src = Src()
        rec = run(src, subs=("101",), actor_verified=kind)
        assert rec["state"] == "refused" and rec["outcome"] == "refused"
        assert "is confirmed by a verified person, and this request is not one" in rec["why"]
        assert f"actor {ACTOR}, verified {kind or 'none'}" in rec["why"]
        assert src.box.batches == [] and src.box.opened == 0, "nothing was sent"
        got = stored(rec)
        assert got["state"] == "refused" and got["config_change"] is False
        assert got["actor_verified"] == (kind if isinstance(kind, str) and kind else "none")
        assert got["actor_verified"] != "access"
        assert R.person_refusal(ACTOR, kind, True)

    @pytest.mark.parametrize("actor, person", [("", True), (None, True), ("unverified", True),
                                               (ACTOR, False), (ACTOR, None), (ACTOR, "yes")])
    def test_nobody_an_unverified_actor_or_a_service_is_refused(self, lab, actor, person):
        src = Src()
        rec = run(src, subs=("101",), actor=actor, person=person)
        assert rec["state"] == "refused"
        assert "is confirmed by a verified person, and this request is not one" in rec["why"]
        assert src.box.batches == [] and src.box.opened == 0, "nothing was sent"

    def test_it_is_refused_before_the_plan_or_the_hash_is_said(self, lab):
        """A request that is not a verified person's learns nothing of a valid confirm: the
        refusal is the person's, whatever the subscriptions, the hashes and the reason."""
        from modules.heal import resubscribe as R
        rec = run(Src(), subs=("999",), confirmed={"999": "0" * 16}, reason="",
                  actor_verified="none")
        assert "verified person" in rec["why"] and "999" not in rec["why"]
        assert "0000000000000000" not in rec["why"]
        got = R.start(NET, "r2", ["999"], actor=ACTOR, actor_verified="", person=True,
                      confirmed={}, reason="")
        assert got["not_a_person"] is True and "verified person" in got["refused"]
        assert "999" not in got["refused"]

    def test_neither_who_nor_how_has_a_default(self):
        """A caller that does not say who and how they were verified is an error, never a
        person verified through the access proxy."""
        import inspect
        from modules.heal import resubscribe as R
        for fn in (R.apply, R.start):
            params = inspect.signature(fn).parameters
            for name in ("actor", "actor_verified", "person"):
                assert params[name].default is inspect.Parameter.empty, (fn.__name__, name)
                assert params[name].kind is inspect.Parameter.KEYWORD_ONLY, (fn.__name__, name)


# ── The run ─────────────────────────────────────────────────────────────────────────────────

class TestTheRun:
    def test_two_subscriptions_are_removed_together_then_added_back_and_verified(self, lab):
        """The batch, exactly: remove 101, remove 102 (each read back as gone before the
        next), one wait of 10 s, add 101, add 102, then each one's verify."""
        gone = []

        def on_send(box, batch):
            # What the device held as each send arrived: which receivers were already out.
            lines = batch.split("\n")
            gone.append((lines[1].rsplit(" ", 1)[1], lines[2].strip().split(" ", 1)[0],
                         [h for h in ("101", "102")
                          if f" {LINE}" not in box.lines[slice(*box._block(
                              f"telemetry ietf subscription {h}"))]]))
        src = Src(box=Box(on_send=on_send))
        rec = run(src)
        assert rec["outcome"] == "resubscribed", rec["why"]
        assert rec["state"] == "done"
        b = src.box.batches
        assert [x[2] for x in b] == [f" no {LINE}", f" no {LINE}", f" {LINE}", f" {LINE}"]
        assert [x[1] for x in b] == ["telemetry ietf subscription 101",
                                     "telemetry ietf subscription 102"] * 2
        assert all(len(x) == 4 and x[0] == "configure terminal" and x[3] == "end" for x in b)
        # 102's removal met 101 already out; 101's re-add met both out: no chosen subscription
        # held a receiver at the wait.
        assert gone == [("101", "no", []), ("102", "no", ["101"]),
                        ("101", "receiver", ["101", "102"]), ("102", "receiver", ["102"])]
        assert src.clock.slept[0] == 10, "the wait between the removals and the re-adds"
        assert src.box.text() == R2_CFG + ("" if R2_CFG.endswith("\n") else "\n"), \
            "the configuration ends as it began"
        got = stored(rec)
        assert [s["outcome"] for s in got["subscriptions"]] == ["resubscribed", "resubscribed"]
        assert got["config_change"] is True and got["key"] == "telemetry-resubscribe"
        assert got["reason"] == REASON and got["hash"] and got["finished_at"]
        steps = [(s["step"], s["result"]) for s in got["steps"]]
        assert [s for s, _r in steps[:5]] == ["plan", "hash", "hold", "started", "before"]
        assert steps[5:10] == [("remove", "ok"), ("remove", "ok"), ("wait", "ok"),
                               ("re-add", "ok"), ("verify", "ok")], steps
        assert [s for s, _r in steps].count("wait") == 1, "one wait, after the last removal"
        assert steps[-1][0] == "record"
        said = [s["words"] for s in got["steps"] if s["step"] == "remove"]
        assert said == ["subscription 101: exactly its receiver line left (read back)",
                        "subscription 102: exactly its receiver line left (read back)"]
        assert got["program"] == b[0] + b[1] + b[2] + b[3], "the record's program is the one sent"
        v = got["subscriptions"][0]["verify"]
        assert v["device"]["state"] == v["stream"]["state"] == v["collector"]["state"] == "pass"
        assert "connection 985, a new one (before: 984)" in v["device"]["words"]

    def test_one_subscription_keeps_its_own_program(self, lab):
        """One chosen: its removal, the wait, its re-add, as before the batch."""
        src = Src()
        rec = run(src, subs=("101",))
        assert rec["outcome"] == "resubscribed", rec["why"]
        assert src.box.batches == [
            ["configure terminal", "telemetry ietf subscription 101", f" no {LINE}", "end"],
            ["configure terminal", "telemetry ietf subscription 101", f" {LINE}", "end"]]
        steps = [s["step"] for s in stored(rec)["steps"]]
        assert steps[5:9] == ["remove", "wait", "re-add", "verify"]
        assert src.clock.slept[0] == 10

    def test_a_subscription_not_chosen_is_not_touched(self, lab):
        src = Src()
        rec = run(src, subs=("102",))
        assert rec["outcome"] == "resubscribed", rec["why"]
        assert {x[1] for x in src.box.batches} == {"telemetry ietf subscription 102"}
        assert [s["sub"] for s in stored(rec)["subscriptions"]] == ["102"]

    def test_no_save_ever_reaches_the_device(self, lab):
        from modules.heal import bounce
        src = Src()
        run(src)
        for batch in src.box.batches:
            bounce.assert_no_save(batch)
            assert not any(ln.strip().startswith(("write", "copy")) for ln in batch)

    def test_the_device_is_held_for_the_whole_run_and_a_holder_refuses(self, lab):
        from modules.nsot import device_ops
        held = []

        def on_send(box, batch):
            held.append(device_ops.holder(NET, "r2"))
        src = Src(box=Box(on_send=on_send))
        run(src)
        assert held and all(h and h["operation"] == "telemetry re-subscribe" for h in held)
        assert device_ops.holder(NET, "r2") is None, "released at its end"
        import threading
        out = {}

        def other():
            out["rec"] = run(Src())
        with device_ops.hold(NET, "r2", "deploy", "someone@example.invalid"):
            t = threading.Thread(target=other)
            t.start()
            t.join()
        assert out["rec"]["state"] == "refused" and "deploy" in out["rec"]["why"]

    def test_the_readd_is_retried_once(self, lab):
        src = Src(box=Box(readd_fails=1))
        rec = run(src, subs=("101",))
        assert rec["outcome"] == "resubscribed", rec["why"]
        sessions = stored(rec)["subscriptions"][0]["sessions"]
        assert [(s["session"], s.get("attempt")) for s in sessions] == [(1, None), (2, 1), (2, 2)]

    def test_the_first_re_add_never_landing_leaves_it_removed_and_the_other_is_still_added(
            self, lab):
        """The re-adds fail on the first: 101 is the removed danger, said first; 102 is still
        added back and verified; the run is never green."""
        from modules.heal import resubscribe as R
        src = Src(box=Box(drops_readd_of=("101",)),
                  receiver=seq([receiver_read(R2_101), receiver_read(R2_102),
                                receiver_read(new_connection(R2_102))]))
        rec = run(src)
        assert rec["outcome"] == "removed" and rec["state"] == "failed"
        assert rec["why"].startswith("r2's receiver for 101 is removed")
        assert [(x[1].rsplit(" ", 1)[1], x[2].strip().split(" ", 1)[0])
                for x in src.box.batches] == [
            ("101", "no"), ("102", "no"), ("101", "receiver"), ("101", "receiver"),
            ("102", "receiver")], "both removals, 101's re-add and its retry, then 102's"
        got = {s["sub"]: s for s in stored(rec)["subscriptions"]}
        assert (got["101"]["outcome"], got["102"]["outcome"]) == ("removed", "resubscribed")
        assert got["102"]["verify"]["device"]["state"] == "pass" and not got["101"]["verify"]
        assert "re-subscribed 102:" in rec["why"]
        block = src.box.text().split("telemetry ietf subscription 102")
        assert LINE not in block[0] and LINE in block[1], "101's is out, 102's is back"
        assert R.removed_now(NET, "r2") == [{"sub": "101", "run": rec["id"]}]

    def test_the_second_re_add_never_landing_leaves_only_it_removed(self, lab):
        from modules.heal import resubscribe as R
        src = Src(box=Box(drops_readd_of=("102",)))
        rec = run(src)
        assert rec["outcome"] == "removed" and rec["state"] == "failed"
        assert rec["why"].startswith("r2's receiver for 102 is removed")
        assert [(x[1].rsplit(" ", 1)[1], x[2].strip().split(" ", 1)[0])
                for x in src.box.batches] == [
            ("101", "no"), ("102", "no"), ("101", "receiver"), ("102", "receiver"),
            ("102", "receiver")]
        got = {s["sub"]: s["outcome"] for s in stored(rec)["subscriptions"]}
        assert got == {"101": "resubscribed", "102": "removed"}
        readd = [s for s in stored(rec)["steps"] if s["step"] == "re-add" and s["result"] == "ok"]
        assert "differs from before only by the receivers that did not come back" in \
            readd[-1]["words"]
        assert R.removed_now(NET, "r2") == [{"sub": "102", "run": rec["id"]}]

    def test_the_second_removal_not_landing_puts_the_first_back_and_says_each(self, lab):
        """The removals fail on the second: nothing more is removed, 101 (already out) is
        added back and verified, 102 was never out; the run is stopped part-way, not green."""
        from modules.heal import resubscribe as R
        src = Src(box=Box(ignores_removal_of=("102",)))
        rec = run(src)
        assert (rec["outcome"], rec["state"]) == ("partial", "failed"), rec["why"]
        assert [(x[1].rsplit(" ", 1)[1], x[2].strip().split(" ", 1)[0])
                for x in src.box.batches] == [
            ("101", "no"), ("102", "no"), ("101", "receiver")], "102 needs no re-add"
        got = {s["sub"]: s["outcome"] for s in stored(rec)["subscriptions"]}
        assert got == {"101": "resubscribed", "102": "not_removed"}
        assert rec["why"].startswith("subscription 102's receiver was not removed")
        assert "no further receiver was removed" in rec["why"]
        assert src.clock.slept[0] == 10, "101 still waits before its re-add"
        assert src.box.text() == R2_CFG + ("" if R2_CFG.endswith("\n") else "\n")
        assert R.removed_now(NET, "r2") == []

    def test_the_first_removal_not_landing_leaves_the_rest_untouched(self, lab):
        src = Src(box=Box(ignores_removal_of=("101",)))
        rec = run(src)
        assert rec["outcome"] == "not_removed" and rec["state"] == "failed"
        assert len(src.box.batches) == 1 and src.clock.slept == []
        got = {s["sub"]: s for s in stored(rec)["subscriptions"]}
        assert sorted(got) == ["101", "102"], "each chosen subscription has its own record"
        assert (got["101"]["outcome"], got["102"]["outcome"]) == ("not_removed", "not_sent")
        assert got["102"]["words"] == ("subscription 102: nothing was sent for it (the removals "
                                       "stopped at subscription 101)")
        assert got["102"]["sessions"] == []

    def test_a_run_that_fails_between_the_removals_and_the_re_adds_says_each_is_removed(
            self, lab):
        """Both receivers out, then the run breaks (here at its wait): the record says each is
        taken as removed, and the card's Re-add the receiver is there for each."""
        from modules.heal import resubscribe as R
        src = Src()

        def broken(_s):
            raise RuntimeError("the worker stopped")
        src.sleep = broken
        rec = run(src)
        assert (rec["outcome"], rec["state"]) == ("failed", "failed")
        assert "Taken as removed until read: 101 and 102" in rec["why"]
        got = {s["sub"]: s["outcome"] for s in stored(rec)["subscriptions"]}
        assert got == {"101": "removed", "102": "removed"}
        assert R.removed_now(NET, "r2") == [{"sub": "101", "run": rec["id"]},
                                            {"sub": "102", "run": rec["id"]}]

    def test_a_removed_receiver_stays_said_until_its_own_re_add(self, lab):
        """Judged per subscription: a later run of the other subscription, a refused run, and
        a run that found nothing to remove do not hide a receiver still out."""
        from modules.heal import resubscribe as R
        from modules.nsot import device_ops
        box = Box(drops_readd_of=("101",))
        first = run(Src(box=box, receiver=seq([receiver_read(R2_101), receiver_read(R2_102),
                                               receiver_read(new_connection(R2_102))])))
        want = [{"sub": "101", "run": first["id"]}]
        assert R.removed_now(NET, "r2") == want
        later = run(Src(box=box, receiver=seq([receiver_read(R2_102),
                                               receiver_read(new_connection(R2_102))])),
                    subs=("102",))
        assert later["outcome"] == "resubscribed", later["why"]
        assert R.removed_now(NET, "r2") == want, "102's run says nothing of 101"
        import threading
        out = {}

        def other():                                  # another worker's request, as it is held
            out["rec"] = run(Src(box=box), subs=("101",), readd=True, reason="")
        with device_ops.hold(NET, "r2", "deploy", "someone@example.invalid"):
            t = threading.Thread(target=other)
            t.start()
            t.join()
        assert out["rec"]["state"] == "refused" and "deploy" in out["rec"]["why"]
        assert R.removed_now(NET, "r2") == want, "a refused re-add put nothing back"
        again = run(Src(box=box), subs=("101",))
        assert again["outcome"] == "not_removed", "its receiver is already out"
        assert R.removed_now(NET, "r2") == want
        box.drops_readd_of.clear()
        back = run(Src(box=box, receiver=seq([receiver_read(R2_101),
                                              receiver_read(new_connection(R2_101))])),
                   subs=("101",), readd=True, reason="")
        assert back["outcome"] == "readded", back["why"]
        assert R.removed_now(NET, "r2") == []

    def test_an_unfinished_run_says_what_it_left_removed_once_nothing_holds_the_device(
            self, lab):
        """A record left running by a run that never ended (Mercury restarted under it): each
        receiver whose removal it sent and whose re-add it did not read back is removed.
        While a run really holds the device, its unfinished record says nothing yet."""
        from modules.heal import resubscribe as R
        from modules.nsot import device_ops, privileged
        rec = {"id": "20261110T000000000000Z-" + "0" * 32, "list": NET, "device": "r2",
               "key": "telemetry-resubscribe", "state": "running", "outcome": "running",
               "started_at": 1.0, "finished_at": None, "config_change": True, "actor": ACTOR,
               "subscriptions": [
                   {"sub": "101", "outcome": "", "removal": "sent", "landed": True},
                   {"sub": "102", "outcome": "", "removal": "sent", "landed": None},
                   {"sub": "103", "outcome": "", "removal": "", "landed": None}]}
        privileged.record(NET, rec)
        assert R.removed_now(NET, "r2") == [{"sub": "102", "run": rec["id"]}]
        with device_ops.hold(NET, "r2", R.OPERATION, ACTOR):
            assert R.removed_now(NET, "r2") == [], "its run is still going"
        with device_ops.hold(NET, "r2", "deploy", ACTOR):
            assert R.removed_now(NET, "r2") == [{"sub": "102", "run": rec["id"]}]

    def test_readd_the_receiver_puts_it_back_and_clears_the_danger(self, lab):
        from modules.heal import resubscribe as R
        box = Box(readd_fails=2)
        run(Src(box=box), subs=("101",))
        assert LINE not in box.text().split("telemetry ietf subscription 102")[0]
        src = Src(box=box, receiver=seq([receiver_read(R2_101),
                                         receiver_read(new_connection(R2_101))]))
        rec = run(src, subs=("101",), readd=True, reason="")
        assert rec["outcome"] == "readded", rec["why"]
        assert box.text() == R2_CFG + ("" if R2_CFG.endswith("\n") else "\n")
        assert [b[2] for b in box.batches[-1:]] == [f" {LINE}"]
        assert R.removed_now(NET, "r2") == []
        assert stored(rec)["key"] == "telemetry-readd"

    def test_a_removal_that_takes_more_than_its_line_is_said(self, lab):
        src = Src(box=Box(removes_also="stream yang-push"))
        rec = run(src, subs=("101",))
        assert rec["outcome"] == "moved" and rec["state"] == "failed"
        got = stored(rec)
        remove = next(s for s in got["steps"] if s["step"] == "remove")
        assert remove["result"] == "failed" and "more than its line" in remove["words"]
        assert got["subscriptions"][0]["moved"]["missing"] == [
            "telemetry ietf subscription 101 :: stream yang-push"]

    def test_a_removal_that_did_not_land_sends_nothing_more(self, lab):
        box = Box(ignores_removal=True)
        rec = run(Src(box=box), subs=("101", "102"))
        assert rec["outcome"] == "not_removed"
        assert "is as before, and nothing more was sent" in rec["why"]
        assert len(box.batches) == 1


# ── Verify ──────────────────────────────────────────────────────────────────────────────────

class TestTheVerify:
    def test_the_same_connection_is_a_fail_never_green(self, lab):
        src = Src(receiver=seq([receiver_read(R2_101)]))
        rec = run(src, subs=("101",))
        assert rec["outcome"] == "not_back" and rec["state"] == "failed"
        assert rec["why"].startswith("re-subscribed 101; the stream did not come back within "
                                     "290 s")
        v = stored(rec)["subscriptions"][0]["verify"]["device"]
        assert v["state"] == "fail" and "the same connection as before" in v["words"]
        assert "is as intent holds it" in rec["why"]

    def test_in_a_batch_each_subscription_is_judged_by_its_own_connection_before(self, lab):
        """101 comes back on a new connection; 102 reads Connected on the connection it had
        before the run: 102 fails, in words, and the run is not green."""
        src = Src(receiver=seq([receiver_read(R2_101), receiver_read(R2_102),
                                receiver_read(new_connection(R2_101)), receiver_read(R2_102)]))
        rec = run(src)
        assert rec["outcome"] == "not_back" and rec["state"] == "failed"
        got = {s["sub"]: s for s in stored(rec)["subscriptions"]}
        assert got["101"]["outcome"] == "resubscribed"
        v = got["102"]["verify"]["device"]
        assert v["state"] == "fail"
        assert ("connection 984, the same connection as before: Connected is not a stream"
                in v["words"])
        assert rec["why"].startswith("re-subscribed 102; the stream did not come back within "
                                     "290 s")

    def test_no_data_within_the_bound_fails_at_290_s(self, lab):
        src = Src(series=seq([ABSENT]))
        start = src.clock.t
        rec = run(src, subs=("101",))
        assert rec["outcome"] == "not_back"
        v = stored(rec)["subscriptions"][0]["verify"]
        assert v["stream"]["state"] == "fail" and v["device"]["state"] == "pass"
        assert 290 <= src.clock.t - start - 10 <= 300, "the bound, after the 10 s wait"

    def test_an_unreadable_read_is_cant_tell_named(self, lab):
        src = Src(series=seq([UNREAD_SERIES]))
        rec = run(src, subs=("101",))
        assert rec["outcome"] == "unverified" and rec["state"] == "unverified"
        v = stored(rec)["subscriptions"][0]["verify"]["stream"]
        assert v["state"] == "cant_tell" and "Prometheus is not configured" in v["words"]

    def test_a_device_read_unreadable_before_is_cant_tell(self, lab):
        src = Src(receiver=seq([UNREAD, receiver_read(new_connection(R2_101))]))
        rec = run(src, subs=("101",))
        v = stored(rec)["subscriptions"][0]["verify"]["device"]
        assert v["state"] == "cant_tell" and "the connection before was not read" in v["words"]
        assert rec["outcome"] == "unverified"

    def test_the_collector_through_its_real_tables_and_the_stale_flag(self, lab, tmp_path):
        """Before: the device's session 60235, nothing received for 99 minutes (ss_tni_4's).
        After: a new one, 60999, received 287 ms ago; the old one still stands: flagged."""
        from modules.heal.diagnose_stream import read_collector
        before_root = proc(tmp_path / "b", tcp6=False)

        def with_new(name, body):
            if name != "tcp":
                return body
            row = next(l for l in body.splitlines() if "060200C0:EB4B" in l)
            return body.rstrip("\n") + "\n" + row.replace("060200C0:EB4B",
                                                         "060200C0:EE47") + "\n"
        after_root = proc(tmp_path / "a", tcp6=False, tables=with_new)
        ss4 = open(os.path.join(COLLECTOR, "ss_tni_4.txt"), encoding="utf-8").read()
        lines = ss4.splitlines()
        ss_after = "\n".join(lines + [lines[1].replace("192.0.2.7:51522", "192.0.2.6:60999"),
                                      lines[2]]) + "\n"
        reads = [lambda: read_collector("192.0.2.10", 57000, ["192.0.2.6"], proc=before_root,
                                        ss=lambda p: (ss4, "")),
                 lambda: read_collector("192.0.2.10", 57000, ["192.0.2.6"], proc=after_root,
                                        ss=lambda p: (ss_after, ""))]

        def edit(intents):
            for s in intents["r2"]["telemetry"]:
                s["settings"] = [x.replace("10.255.1.10", "192.0.2.10") for x in s["settings"]]
            for i in intents["r2"]["interfaces"]:
                if i["name"] == "GigabitEthernet2":
                    i["ipv4"] = "192.0.2.6 255.255.255.0"
        # The receiver at the collector's documentation address, in intent and on the device.
        src = Src(collector=seq(reads), intent_edit=edit,
                  box=Box(text=R2_CFG.replace("10.255.1.10", "192.0.2.10")))
        rec = run(src, subs=("101",))
        assert rec["outcome"] == "resubscribed", rec["why"]
        got = stored(rec)["subscriptions"][0]
        assert got["verify"]["collector"]["state"] == "pass"
        assert "a new session from 192.0.2.6 port 60999" in got["verify"]["collector"]["words"]
        assert got["stale"] == ["stale half-open: the session from 192.0.2.6 port 60235, there "
                                "before the operation, still stands with nothing received "
                                "for 5966 s"]
        assert "flagged: stale half-open" in rec["why"], "a flag, never a failure"

    def test_a_new_session_receiving_nothing_does_not_pass(self, lab):
        quiet_new = ("192.0.2.6", 60999, "ESTABLISHED", 120000)
        src = Src(collector=seq([coll(OLD), coll(OLD, quiet_new)]))
        rec = run(src, subs=("101",))
        v = stored(rec)["subscriptions"][0]["verify"]["collector"]
        assert v["state"] == "fail" and "nothing received on it yet" in v["words"]

    def test_the_collector_elsewhere_is_cant_tell(self, lab):
        src = Src(collector=seq([coll(state="elsewhere")]))
        rec = run(src, subs=("101",))
        v = stored(rec)["subscriptions"][0]["verify"]["collector"]
        assert v["state"] == "cant_tell" and rec["outcome"] == "unverified"

    def test_the_receiver_read_goes_through_the_reads_engine(self, lab):
        """(a) on History › Reads: a run of the reads engine, recorded, as the person."""
        from modules.heal import resubscribe as R
        from modules.nsot import reads
        from tests.test_heal_diagnose import Fleet
        f = Fleet({("r2", "show telemetry ietf subscription 101 receiver"): [
            R2_101, new_connection(R2_101)]})
        src = Src()
        real = R.Sources(NET, session=f)
        src.receiver = real.receiver
        rec = run(src, subs=("101",))
        assert rec["outcome"] == "resubscribed", rec["why"]
        runs = reads.runs(NET)["runs"]
        assert len(runs) == 2 and {r["actor"] for r in runs} == {ACTOR}
        assert all(r["commands"] == ["show telemetry ietf subscription 101 receiver"]
                   for r in runs)


# ── Self-healing sees the operation's own change as Mercury's ───────────────────────────────

class TestAttribution:
    def test_a_line_during_and_after_the_run_is_mercurys_own(self, lab):
        from modules.heal import attribution as AT
        seen = []

        def on_send(box, batch):
            # At each send: the run's record is already written, saying it changes config.
            from modules.config import list_data_path
            from modules.nsot import privileged
            r = privileged.runs(NET, device="r2", data_dir=list_data_path(NET))["runs"][0]
            seen.append((r["state"], r["config_change"]))
        src = Src(box=Box(on_send=on_send))
        t0 = src.clock.t
        rec = run(src, subs=("101",))
        assert seen and all(s == ("running", True) for s in seen)
        none = {"holder": lambda n, d: None, "receipts": lambda n, d: [],
                "rotations": lambda n: {}}
        during = AT.attribute(NET, "r2", t0 + 5, **none)
        assert during["by"] == AT.MERCURY, during
        assert during["evidence"]["operation"]["id"] == rec["id"]
        tail = AT.attribute(NET, "r2", rec["finished_at"] + 30, **none)
        assert tail["by"] == AT.MERCURY
        later = AT.attribute(NET, "r2", rec["finished_at"] + 120, **none)
        assert later["by"] == AT.OUTSIDE, later

    def test_a_run_that_never_ended_spans_nothing(self, lab):
        """A record left running (Mercury restarted under the run) has no end: it never makes
        a later line Mercury's own. While a run is really going the device is held, and the
        hold answers."""
        import time
        from modules.heal import attribution as AT
        from modules.nsot import privileged
        started = time.time() - 3600
        rec = {"id": "20261110T000000000000Z-" + "0" * 32, "list": NET, "device": "r2",
               "key": "telemetry-resubscribe", "state": "running", "outcome": "running",
               "started_at": started, "finished_at": None, "config_change": True,
               "actor": ACTOR}
        privileged.record(NET, rec)
        none = {"receipts": lambda n, d: [], "rotations": lambda n: {}}
        for at in (started + 5, started + 1800, time.time()):
            got = AT.attribute(NET, "r2", at, holder=lambda n, d: None, **none)
            assert got["by"] == AT.OUTSIDE, got
        held = AT.attribute(NET, "r2", started + 5, **none, holder=lambda n, d: {
            "operation": "telemetry re-subscribe", "actor": ACTOR, "started": started})
        assert held["by"] == AT.MERCURY and "hold" in held["evidence"]
        # The same record once its run has ended is the one the rule reads: so the answers
        # above were about a run with no end, never about a record nobody found.
        privileged.record(NET, dict(rec, state="done", outcome="resubscribed",
                                    finished_at=started + 400))
        ended = AT.attribute(NET, "r2", started + 5, holder=lambda n, d: None, **none)
        assert ended["by"] == AT.MERCURY, ended
        assert ended["evidence"]["operation"]["id"] == rec["id"]
        after = AT.attribute(NET, "r2", started + 400 + 61, holder=lambda n, d: None, **none)
        assert after["by"] == AT.OUTSIDE, after

    def test_a_refused_run_is_no_change(self, lab):
        from modules.heal import attribution as AT
        src = Src()
        t0 = src.clock.t
        run(src, subs=("101",), reason="no")
        got = AT.attribute(NET, "r2", t0 + 1, holder=lambda n, d: None,
                           receipts=lambda n, d: [], rotations=lambda n: {})
        assert got["by"] == AT.OUTSIDE

    def test_an_unreadable_record_is_unknown_never_mercurys(self, lab):
        from modules.heal import attribution as AT

        def broken(n, d):
            raise RuntimeError("1 of Default's operation records cannot be read (x.json)")
        got = AT.attribute(NET, "r2", 1.0, holder=lambda n, d: None, receipts=lambda n, d: [],
                           rotations=lambda n: {}, operations=broken)
        assert got["by"] == AT.UNKNOWN and "operation records cannot be read" in got["words"]


# ── The stream's series in Prometheus (C2892) ───────────────────────────────────────────────

class FakeProm:
    def __init__(self, result, ok=True, configured=True):
        self.result, self.ok, self.configured, self.asked = result, ok, configured, []

    def is_configured(self):
        return self.configured

    def _get(self, path, **params):
        self.asked.append((path, params))
        if not self.ok:
            return {"ok": False, "error": "connection refused"}
        body = {"data": {"result": self.result}}

        class R:
            def json(self_inner):
                return body
        return {"ok": True, "response": R()}


class TestTheSeries:
    def test_present_absent_and_unread(self):
        from modules.heal.diagnose_stream import series_of
        p = FakeProm([{"metric": {}, "value": [0, "3"]}])
        got = series_of("r2", "101", prom=p)
        assert (got["state"], got["count"]) == ("present", 3)
        assert p.asked == [("api/v1/query", {"query": 'count(last_over_time({device="r2", '
                                                      'subscription="101"}[90s]))'})]
        assert series_of("r2", "101", prom=FakeProm([]))["state"] == "absent"
        assert series_of("r2", "101", prom=FakeProm([], ok=False))["state"] == "unread"
        assert series_of("r2", "101", prom=FakeProm([], configured=False))["why"] == \
            "Prometheus is not configured"

    @pytest.mark.parametrize("device,sub", [('r2"} or vector(1) #', "101"), ("r2", "1 or 1")])
    def test_a_name_that_is_not_one_token_is_never_queried(self, device, sub):
        from modules.heal.diagnose_stream import series_of
        p = FakeProm([{"value": [0, "1"]}])
        assert series_of(device, sub, prom=p)["state"] == "unread" and p.asked == []


class TestTheSocketDiagnostics:
    def test_ss_reads_each_sessions_last_receive_ipv4_and_ipv6(self):
        import ipaddress
        from modules.heal.diagnose_stream import parse_ss
        rows, why = parse_ss(open(os.path.join(COLLECTOR, "ss_tni_4.txt")).read())
        assert why == ""
        assert [(str(r["remote"]), r["rport"], r["bytes_received"], r["lastrcv_ms"])
                for r in rows] == [("192.0.2.7", 51522, 160000, 287),
                                   ("192.0.2.6", 60235, 828, 5966281)]
        rows, why = parse_ss(open(os.path.join(COLLECTOR, "ss_tni_6.txt")).read())
        assert [(str(r["local"]), str(r["remote"]), r["rport"]) for r in rows] == [
            ("2001:db8::10", "2001:db8:4::6", 41714), ("192.0.2.10", "192.0.2.6", 60235)]
        assert rows[1]["remote"] == ipaddress.ip_address("192.0.2.6"), "mapped read as IPv4"
        assert parse_ss("nonsense")[1].startswith("the answer is not `ss`'s table")

    def test_read_collector_carries_last_receive_only_when_read(self, tmp_path):
        from modules.heal.diagnose_stream import read_collector, receiving_now
        ss4 = open(os.path.join(COLLECTOR, "ss_tni_4.txt")).read()
        root = proc(tmp_path, tcp6=False)
        got = read_collector("192.0.2.10", 57000, ["192.0.2.6"], proc=root,
                             ss=lambda port: (ss4, ""))
        (s,) = got["sessions"]
        assert (s["lastrcv_ms"], s["bytes_received"], got["activity"]) == (5966281, 828, "read")
        assert receiving_now(s) is False
        bare = read_collector("192.0.2.10", 57000, ["192.0.2.6"], proc=root)
        assert "lastrcv_ms" not in bare["sessions"][0] and receiving_now(bare["sessions"][0]) \
            is None, "can't tell from /proc alone"
        failed = read_collector("192.0.2.10", 57000, ["192.0.2.6"], proc=root,
                                ss=lambda port: ("", "`ss` exited 1"))
        assert failed["activity"] == "not read: `ss` exited 1"

    def test_ipv6_sessions_carry_their_last_receive(self, tmp_path):
        from modules.heal.diagnose_stream import read_collector
        ss6 = open(os.path.join(COLLECTOR, "ss_tni_6.txt")).read()
        got = read_collector("2001:db8::10", 57000, ["2001:db8:4::6"],
                             proc=proc(tmp_path, tcp=False), ss=lambda port: (ss6, ""))
        assert got["sessions"][0]["lastrcv_ms"] == 312


# ── The declarations ────────────────────────────────────────────────────────────────────────

class TestTheDeclarations:
    def test_the_routes_are_declared_confirm_with_their_stages(self):
        from modules.invalidation import DECLARED
        from modules.operation_stages import HISTORY, STAGES
        from modules.route_gates import GATES
        for e in ("resubscribe_v2.confirm", "resubscribe_v2.readd"):
            assert GATES[e].kind == "confirm", e
            st = STAGES[e]
            assert st.preview == "resubscribe_v2.preview"
            # The field its button carries: the selection's hash, or the re-add's own.
            assert st.hash == {"resubscribe_v2.confirm": "program",
                               "resubscribe_v2.readd": "hash"}[e]
            assert st.verify == "modules.heal.resubscribe.verify"
            assert st.rollback == "modules.heal.resubscribe.put_back"
            assert st.record == "modules.heal.resubscribe._record"
            assert HISTORY[e] == ("privileged",)
            assert DECLARED[e] == ("privileged",)
        from routes import resubscribe_v2 as RV
        assert set(RV.gates()) == set(RV.stages()) == set(RV.history()) == {
            "resubscribe_v2.confirm", "resubscribe_v2.readd"}

    def test_the_manual_names_each_step(self):
        from modules import manual
        assert manual.declared_steps("telemetry-resubscribe")[0] == "plan"
        text = manual.source("telemetry-resubscribe")
        for step in manual.declared_steps("telemetry-resubscribe") + manual.declared_steps(
                "telemetry-readd"):
            assert f"`{step}`" in text, step
