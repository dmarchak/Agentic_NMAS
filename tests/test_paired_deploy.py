"""The paired deploy: both ends of a link as ONE change (C1908's deploy side, C1909; the
operator's design on board F7-Q, 2026-10-27; `modules/nsot/paired_deploy.py`).

C1909's test is `TestTheSecondEndsLinkVerifyFails`: two fake devices deployed as one change
through THE apply (`routes.deploy.apply_batch` with *pair*) and the pipeline's own runner,
rollback and intent note; each end's own verify passes, the link's verify fails at the second
end, and both devices are back to their before, byte for byte, both receipts say what each
achieved, and both devices' intent is marked rolled back on the pair's commit (the
single-device path's record of a change that did not land: the next plan is blocked, and
Revert or Retry lifts it). Its control keeps the first device's change, and fails it.

The devices are r3 and r4's REAL fleet configs (tests/fixtures/configs/fleet), their link
r3 GigabitEthernet4 to r4 GigabitEthernet4 (OSPF and OSPFv3 across a /31 and a /64), and the
link is read from r3's REAL captures (tests/fixtures/operational): r4's reads are r3's with
the Gi4 row's neighbour and address edited to r3's, the one minimal edit. The fake device
applies what it is sent to its running config; nothing opens a session.
"""

import os
import subprocess

import pytest

from modules.nsot import paired_deploy as PD

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FLEET = os.path.join(ROOT, "tests", "fixtures", "configs", "fleet")
OPER = os.path.join(ROOT, "tests", "fixtures", "operational")
LIST = "Lab"
LINK = {"device": "r3", "port": "GigabitEthernet4", "far": "r4", "far_port": "GigabitEthernet4"}
#: Both ends' program: one OSPF setting on the link's interface, as a two-ended draft makes it.
PROGRAM = ["interface GigabitEthernet4", " ip ospf hello-interval 5", "exit"]
IPS = {"r3": "192.0.2.13", "r4": "192.0.2.14"}


def _read(name):
    return open(os.path.join(OPER, name), encoding="utf-8").read()


def _cfg(host):
    return open(os.path.join(FLEET, f"{host}.cfg"), encoding="utf-8").read()


R3_GI4 = "10.255.1.14       1   FULL/DR         00:00:34    10.255.2.15     GigabitEthernet4"
R4_GI4 = "10.255.1.13       1   FULL/BDR        00:00:34    10.255.2.14     GigabitEthernet4"
V3_R3_GI4 = "10.255.1.14       1   FULL/DR         00:00:38    10              GigabitEthernet4"
V3_R4_GI4 = "10.255.1.13       1   FULL/BDR        00:00:38    10              GigabitEthernet4"


def _reads(lost_on_r4=False, v3_lost_on_r4=False, r4_ospf_raises=False):
    """``{(host, command): text or an exception}``: the link's reads on both ends."""
    from modules import pipeline as P

    ospf, v3, ifs = (_read("r3__show_ip_ospf_neighbor.txt"),
                     _read("r3__show_ospfv3_neighbor.txt"),
                     _read("r3__show_interfaces_include_line_protocol_internet_address.txt"))
    assert R3_GI4 in ospf and V3_R3_GI4 in v3, "the r3 captures moved"
    r4_ospf = ospf.replace(R3_GI4, "" if lost_on_r4 else R4_GI4)
    r4_v3 = v3.replace(V3_R3_GI4, "" if v3_lost_on_r4 else V3_R4_GI4)
    return {("r3", P._INTERFACES_READ): ifs,
            ("r4", P._INTERFACES_READ): ifs.replace("10.255.2.14/31", "10.255.2.15/31"),
            ("r3", "show ip ospf neighbor"): ospf,
            ("r4", "show ip ospf neighbor"): (OSError("the session closed") if r4_ospf_raises
                                              else r4_ospf),
            ("r3", "show ospfv3 neighbor"): v3, ("r4", "show ospfv3 neighbor"): r4_v3}


def _intents():
    from modules.nsot.parsers import get_parser
    return {h: get_parser("cisco_iosxe").parse(_cfg(h)) for h in ("r3", "r4")}


# ── the link: what the change touches, and what its verify checks ─────────────────

class TestTheLink:
    def test_the_link_as_a_page_carries_it(self):
        assert PD.link_of("r3:Gi4,r4:GigabitEthernet4") == LINK
        assert PD.link_text(LINK) == "r3:GigabitEthernet4,r4:GigabitEthernet4"
        for bad in ("r3:Gi4", "r3:Gi4,r3:Gi5", "r3,r4:Gi4", ""):
            with pytest.raises(PD.LinkRefused):
                PD.link_of(bad)

    def test_an_ospf_line_on_the_port_checks_the_adjacency_full_on_both_ends(self):
        checks = PD.link_checks(LINK, {"r3": PROGRAM, "r4": PROGRAM}, _intents())
        assert [c["family"] for c in checks] == ["state", "ospf"]
        assert checks[1]["expect"] == "full"
        assert checks[1]["rid"] == {"r3": "10.255.1.13", "r4": "10.255.1.14"}

    def test_an_ipv6_ospf_line_checks_ospfv3(self):
        """The IPv6 case beside the IPv4 one: OSPFv3 across the /64."""
        prog = ["interface GigabitEthernet4", " ipv6 ospf hello-interval 5", "exit"]
        checks = PD.link_checks(LINK, {"r3": prog, "r4": prog}, _intents())
        assert [(c["family"], c["expect"]) for c in checks] == [("state", {"r3": "", "r4": ""}),
                                                                ("ospfv3", "full")]

    def test_a_description_checks_the_link_state_alone(self):
        prog = ["interface GigabitEthernet4", " description r3-r4 core", "exit"]
        assert [c["family"] for c in PD.link_checks(LINK, {"r3": prog, "r4": prog},
                                                    _intents())] == ["state"]

    def test_a_trunk_says_what_it_reads_and_what_it_does_not(self):
        prog = ["interface GigabitEthernet4", " switchport trunk allowed vlan 10,20", "exit"]
        (state,) = PD.link_checks(LINK, {"r3": prog, "r4": prog}, _intents())
        assert "VLANs each end forwards are not read" in " ".join(state["notes"])

    def test_a_line_on_another_interface_touches_nothing_of_the_link(self):
        prog = ["interface GigabitEthernet3", " ip ospf hello-interval 5", "exit"]
        assert PD.touched(prog, "GigabitEthernet4") == {"families": set(), "admin": ""}

    def test_the_link_must_be_in_both_ends_committed_intent(self):
        intents = _intents()
        assert PD.link_problem(LINK, intents, ["r4", "r3"]) == ""
        assert "not exactly the two ends" in PD.link_problem(LINK, intents, ["r3"])
        assert "is not in r4's committed intent" in PD.link_problem(
            dict(LINK, far_port="GigabitEthernet9"), intents)


class TestTheJudgement:
    def _verify(self, monkeypatch, reads, checks):
        monkeypatch.setattr(PD, "_read", lambda dev, cmd: _answer(reads, dev["hostname"], cmd))
        monkeypatch.setattr(PD, "SLEEP", lambda _s: None)
        monkeypatch.setattr("modules.list_settings.value", lambda _l, _k, d=None: d)
        devices = {h: {"hostname": h, "ip": IPS[h]} for h in IPS}
        before = PD.read_state(LINK, devices)
        return PD.verify_link(LINK, devices, checks, list_name=LIST, before=before)

    def test_both_ends_full_passes(self, monkeypatch):
        got = self._verify(monkeypatch, _reads(),
                           PD.link_checks(LINK, {"r3": PROGRAM, "r4": PROGRAM}, _intents()))
        assert got["state"] == PD.PASSED, got

    def test_one_end_without_its_neighbour_fails_naming_it(self, monkeypatch):
        got = self._verify(monkeypatch, _reads(lost_on_r4=True),
                           PD.link_checks(LINK, {"r3": PROGRAM, "r4": PROGRAM}, _intents()))
        assert got["state"] == PD.FAILED
        assert "r4 GigabitEthernet4 has no FULL adjacency to r3 (10.255.1.13)" in got["words"]

    def test_ospfv3_lost_on_one_end_fails(self, monkeypatch):
        prog = ["interface GigabitEthernet4", " ipv6 ospf hello-interval 5", "exit"]
        got = self._verify(monkeypatch, _reads(v3_lost_on_r4=True),
                           PD.link_checks(LINK, {"r3": prog, "r4": prog}, _intents()))
        assert got["state"] == PD.FAILED and "OSPFv3: r4 GigabitEthernet4" in got["words"]

    def test_a_read_that_cannot_be_made_neither_passes_nor_fails(self, monkeypatch):
        got = self._verify(monkeypatch, _reads(r4_ospf_raises=True),
                           PD.link_checks(LINK, {"r3": PROGRAM, "r4": PROGRAM}, _intents()))
        assert got["state"] == PD.UNREADABLE and "the session closed" in got["words"]

    def test_a_link_down_before_and_not_brought_up_is_not_judged(self, monkeypatch):
        reads = _reads()
        for host in IPS:
            key = (host, PD._command("state"))
            reads[key] = reads[key].replace("GigabitEthernet4 is up, line protocol is up",
                                            "GigabitEthernet4 is up, line protocol is down")
        prog = ["interface GigabitEthernet4", " description r3-r4 core", "exit"]
        got = self._verify(monkeypatch, reads, PD.link_checks(LINK, {"r3": prog, "r4": prog},
                                                              _intents()))
        assert got["state"] == PD.NOT_JUDGED and "was not up before the change" in got["words"]

    def _gi4(self, reads, host, words):
        key = (host, PD._command("state"))
        reads[key] = reads[key].replace("GigabitEthernet4 is up, line protocol is up",
                                        f"GigabitEthernet4 is {words}")
        return reads

    def test_a_shut_end_must_read_administratively_down(self, monkeypatch):
        """Both ends shut: each must read administratively down after; one still up fails,
        naming it. The far end of a one-end shutdown is not judged (an emulated link can stay
        up), so only the shut end is."""
        prog = ["interface GigabitEthernet4", " shutdown", "exit"]
        checks = PD.link_checks(LINK, {"r3": prog, "r4": prog}, _intents())
        down = "administratively down, line protocol is down"

        def verify(after):
            monkeypatch.setattr(PD, "_read", lambda dev, cmd: _answer(
                after, dev["hostname"], cmd))
            monkeypatch.setattr(PD, "SLEEP", lambda _s: None)
            monkeypatch.setattr("modules.list_settings.value", lambda _l, _k, d=None: d)
            devices = {h: {"hostname": h, "ip": IPS[h]} for h in IPS}
            return PD.verify_link(LINK, devices, checks, list_name=LIST,
                                  before={h: {"state": "up"} for h in IPS})
        both = self._gi4(self._gi4(_reads(), "r3", down), "r4", down)
        assert verify(both)["state"] == PD.PASSED
        one = self._gi4(_reads(), "r3", down)
        got = verify(one)
        assert got["state"] == PD.FAILED and "expected r3 admin down, r4 admin down" in \
            got["words"], got

    def test_a_link_that_was_up_and_is_down_after_fails(self, monkeypatch):
        prog = ["interface GigabitEthernet4", " description r3-r4 core", "exit"]
        checks = PD.link_checks(LINK, {"r3": prog, "r4": prog}, _intents())
        after = self._gi4(_reads(), "r4", "up, line protocol is down")
        monkeypatch.setattr(PD, "_read", lambda dev, cmd: _answer(after, dev["hostname"], cmd))
        monkeypatch.setattr(PD, "SLEEP", lambda _s: None)
        monkeypatch.setattr("modules.list_settings.value", lambda _l, _k, d=None: d)
        devices = {h: {"hostname": h, "ip": IPS[h]} for h in IPS}
        got = PD.verify_link(LINK, devices, checks, list_name=LIST,
                             before={h: {"state": "up"} for h in IPS})
        assert got["state"] == PD.FAILED and "read r3 up, r4 down" in got["words"], got

    def test_only_a_read_only_command_is_sent(self, monkeypatch):
        import modules.connection as C
        monkeypatch.setattr(C, "with_temp_connection", lambda dev, func: "asked")
        assert PD._read({"ip": "192.0.2.13"}, "show ip ospf neighbor") == "asked"
        with pytest.raises(ValueError, match="REFUSED"):
            PD._read({"ip": "192.0.2.13"}, "clear ip ospf process")


def _answer(reads, host, cmd):
    got = reads[(host, cmd)]
    if isinstance(got, Exception):
        raise got
    return got


# ── C1909: two fake devices through THE apply ──────────────────────────────────────

class _Device:
    """A device's running config: every line sent applied to it, `no X` removing X."""

    def __init__(self, host):
        self.host, self.running = host, _cfg(host)
        self.before, self.sent, self.saved = self.running, [], 0

    def apply(self, lines):
        rows, head = self.running.splitlines(), None
        for raw in lines:
            if raw.strip() in ("exit", "end"):
                head = None
                continue
            if not raw.startswith(" "):
                head = raw.strip()
                if head not in rows:
                    rows.append(head)
                continue
            child = raw.strip()
            i = rows.index(head)
            j = i + 1
            while j < len(rows) and rows[j].startswith(" "):
                j += 1
            if child.startswith("no "):
                rows[i + 1:j] = [r for r in rows[i + 1:j] if not r.strip().startswith(child[3:])]
            else:
                rows.insert(j, " " + child)
        self.running = "\n".join(rows) + "\n"


class _Conn:
    def __init__(self, dev):
        self.dev = dev

    def enable(self):
        return None

    def send_command(self, cmd, read_timeout=None, **_k):
        return self.dev.running

    def send_config_set(self, lines, **_k):
        self.dev.sent.append(list(lines))
        self.dev.apply(lines)
        return ""


class _Artifact:
    deployable, blocking_reasons, platform, host_vars = True, [], "cisco_iosxe", None

    def __init__(self, device):
        self.device = device


def _token():
    from modules.device import fernet
    return fernet.encrypt(b"").decode()


@pytest.fixture
def pair(tmp_path, monkeypatch):
    """r3 and r4 as fake devices behind THE apply: the real `apply_batch`, `_deploy_one`,
    `PipelineRunner`, rollback, intent note, receipt rows and result; the pipeline's stages that
    read NetBox, render and gate are no-ops, and its push, reads and save act on the fakes. The
    list's repository holds both devices' intent, committed in ONE commit (the pair's)."""
    import modules.connection as C
    import modules.pipeline as P
    import routes.deploy as rd
    from modules.nsot import deploy, device_ops, receipts
    from modules.nsot.repo import stage_post_deploy

    folder = tmp_path / "list"
    repo = folder / "config_repo"
    (repo / "host_vars").mkdir(parents=True)
    for host in IPS:
        (repo / "host_vars" / f"{host}.yml").write_text(f"hostname: {host}\n", encoding="utf-8")
    for args in (["init", "-q"], ["add", "-A"],
                 ["-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "-m",
                  "host_vars: r3 and r4, both ends of the link", "-m",
                  "Actor: operator@example.com\nSource: ai-draft"]):
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
    sha = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], check=True,
                         capture_output=True, text=True).stdout.strip()
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(folder))
    monkeypatch.setattr("modules.list_settings.value", lambda _l, _k, d=None: d)

    devs = {h: _Device(h) for h in IPS}
    by_ip = {IPS[h]: devs[h] for h in IPS}
    rows = {h: {"hostname": h, "ip": IPS[h], "username": "u", "device_type": "cisco_xe",
                "password": _token(), "secret": _token()} for h in IPS}
    seen = {"verify_fails": set(), "reads": _reads(), "written": [], "golden": [], "saved": []}

    monkeypatch.setattr(C, "with_temp_connection", lambda dev, func: func(_Conn(by_ip[dev["ip"]])))
    monkeypatch.setattr(C, "get_persistent_connection",
                        lambda dev, pool, lock: _Conn(by_ip[dev["ip"]]))
    for name in ("netbox_query", "template_render", "ci_gate", "config_diff", "audit_log"):
        monkeypatch.setattr(P, f"_stage_{name}", lambda ctx: None)

    def pre(ctx):
        for d in ctx.selected_devices:
            ctx.pre_snapshots[d["ip"]] = {"running_config": by_ip[d["ip"]].running}

    def push(ctx):
        for ip, cmds in ctx.rendered_commands.items():
            by_ip[ip].sent.append(list(cmds))
            by_ip[ip].apply(cmds)
            ctx.push_results[ip] = {"ok": True, "output": ""}

    def post(ctx):
        for d in ctx.selected_devices:
            ctx.post_snapshots[d["ip"]] = {"running_config": by_ip[d["ip"]].running}

    def verify(ctx):
        for d in ctx.selected_devices:
            if d["hostname"] in seen["verify_fails"]:
                raise P.PipelineStageError(f"{d['hostname']}: ospf neighbours 7 -> 6")
            ctx.verify_result[d["ip"]] = {"ok": True, "issues": [], "checked_protocols": ["ospf"],
                                          "pre": {}, "post": {}}

    def golden(ctx):
        for d in ctx.selected_devices:
            text = by_ip[d["ip"]].running
            stage_post_deploy(str(repo), d["hostname"], text)
            ctx.golden_pending = [{"hostname": d["hostname"], "config_text": text,
                                   "mgmt_ip": d["ip"], "netbox_id": None, "device_uid": ""}]

    for name, fn in (("pre_snapshot", pre), ("deploy", push), ("post_snapshot", post),
                     ("verify", verify), ("save_golden", golden)):
        monkeypatch.setattr(P, f"_stage_{name}", fn)
    monkeypatch.setattr("modules.nsot.onboard.persist_on_device",
                        lambda ip, *a, **k: (seen["saved"].append(by_ip[ip].host),
                                             {"ok": True})[1])

    monkeypatch.setattr(rd, "_artifact_for",
                        lambda list_name, host: ((_Artifact(host), devs[host].before, rows[host]),
                                                 ""))
    monkeypatch.setattr(rd, "_program", lambda intended, captured, selected, device, platform: {
        "refused": [], "recreate": {"refused": [], "units": [], "commands": []},
        "commands": list(PROGRAM), "merge": list(PROGRAM), "keys": [], "ids": [],
        "removed": [], "removal_commands": []})
    monkeypatch.setattr(rd, "_effects_and_declared", lambda *a, **k: ({}, [], []))
    monkeypatch.setattr(rd, "_committed_intents_of", lambda name: (_intents(), ""))
    monkeypatch.setattr(deploy, "prepare_device", lambda artifact: {"config": "intent"})
    monkeypatch.setattr(deploy, "prepare_for_deploy", lambda artifact: {"config": "intent"})
    monkeypatch.setattr(deploy, "assert_merge_only", lambda merge, config: None)
    monkeypatch.setattr(device_ops, "acquire_many",
                        lambda list_name, hosts, op, actor, *a, **k: (list(hosts), []))
    monkeypatch.setattr(device_ops, "release_many", lambda list_name, hosts: None)
    monkeypatch.setattr(receipts, "write", lambda list_name, lines: (
        seen["written"].extend(lines), {"ok": True, "written": len(lines)})[1])

    def commit(list_name, report, **_k):
        done = [r["device"] for r in report["results"] if r.get("outcome") == "deployed"]
        seen["golden"].append(done)
        return {"ok": True, "commit": "", "devices": done, "baseline_reasons": ["a test"]}
    monkeypatch.setattr(rd, "_commit_batch_golden", commit)
    monkeypatch.setattr(PD, "_read", lambda dev, cmd: _answer(seen["reads"], dev["hostname"], cmd))
    monkeypatch.setattr(PD, "SLEEP", lambda _s: None)

    def apply(order=("r3", "r4"), hashes=None):
        from modules.nsot.deploy import command_fingerprint
        from routes.deploy import _capture_hash, apply_batch
        confirmed = {h: _capture_hash(devs[h].before) for h in order}
        hashes = hashes or {h: command_fingerprint(PROGRAM, [], [], []) for h in order}
        return apply_batch(LIST, confirmed, hashes, authorise={}, remove={}, scope="",
                           actor="operator@example.com", actor_kind="access", pair=LINK)

    seen.update(devices=devs, repo=str(repo), sha=sha, apply=apply)
    return seen


def _rows(seen):
    """The receipt rows written whole, by device (a completion line names one by id)."""
    whole = [r for r in seen["written"] if "completes" not in r]
    return {r["device"]: r for r in whole}


def _notes(seen):
    import json
    path = os.path.join(seen["repo"], ".nsot", "rolled_back.json")
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}


def _staged(seen):
    folder = os.path.join(seen["repo"], ".nsot", "staging", "post_deploy")
    return sorted(os.listdir(folder)) if os.path.isdir(folder) else []


class TestTheSecondEndsLinkVerifyFails:
    """C1909: two devices, one change; the second end's link verify fails, and both are rolled
    back to their before; both receipts record it; the intent is marked not landed."""

    def test_both_devices_are_back_to_their_before(self, pair):
        pair["reads"] = _reads(lost_on_r4=True)
        report = pair["apply"]()
        for host, dev in pair["devices"].items():
            assert dev.sent, f"{host} was never sent its half: this is not the case"
            assert dev.running == dev.before, f"{host} still holds the change"
        by = {r["device"]: r for r in report["results"]}
        for host in IPS:
            assert by[host]["outcome"] == "failed" and by[host]["stage"] == "pair", by[host]
            assert by[host]["rollback_outcome"]["state"] == "restored", by[host]
            assert "the link's verify failed" in by[host]["reason"]
        assert report["pair"]["verify"]["state"] == PD.FAILED
        assert report["pair"]["rolled_back"] == ["r3", "r4"]
        assert pair["saved"] == [], "a change that did not stand was saved to startup"
        assert pair["golden"] == [[]] and _staged(pair) == [], "a rolled-back capture is a golden"

    def test_both_receipts_say_what_each_end_achieved(self, pair):
        pair["reads"] = _reads(lost_on_r4=True)
        report = pair["apply"]()
        rows = _rows(pair)
        assert set(rows) == {"r3", "r4"}
        for host, row in rows.items():
            assert row["outcome"] == "failed" and row["sent"] is True, row
            assert row["program"] == PROGRAM
            assert row["rollback"]["performed"] is True and row["rollback"]["state"] == "restored"
            assert row["rollback"]["commands"], f"{host}'s receipt holds no undo it sent"
            assert row["pair"]["link"] == "r3 GigabitEthernet4 ↔ r4 GigabitEthernet4"
            assert row["pair"]["verify"] == "failed"
            assert "r4 GigabitEthernet4 has no FULL adjacency to r3" in row["pair"]["verify_words"]
            assert "the link's verify failed" in row["pair"]["rolled_back_for"]
        assert report["result"]["level"] == "failed"

    def test_both_devices_intent_is_marked_rolled_back_on_the_pairs_commit(self, pair):
        pair["reads"] = _reads(lost_on_r4=True)
        pair["apply"]()
        notes = _notes(pair)
        assert set(notes) == {"r3", "r4"}
        for host, note in notes.items():
            assert note["intent_commit"] == pair["sha"], (host, note)
            assert note["commands"] == PROGRAM and "the link's verify failed" in note["reason"]


class TestTheJobCard:
    """The batch's card drawn from the pair's own result (`routes.v2._apply_answer`): the link's
    verify, what each end achieved, and a failed pair's plan again, never a retry of one end."""

    def _card(self, monkeypatch, report):
        import app as nmas
        from modules import deploy_job
        from modules.outbound import mask_payload
        from routes import v2
        state = {"job": "j1", "state": "done", "order": ["r3", "r4"], "steps": [],
                 "list": LIST, "scope": "", "elapsed_s": 9.0, "error": "",
                 "payload": mask_payload({"ok": True, "list": LIST, **report})}
        monkeypatch.setattr(deploy_job, "state", lambda job: state)
        with nmas.app.test_request_context("/v2/monitoring/apply/job/j1"):
            from html import unescape
            return unescape(v2._apply_answer("j1").get_data(as_text=True))

    def test_a_failed_pair_says_both_rolled_back_and_offers_both_again(self, pair, monkeypatch):
        pair["reads"] = _reads(lost_on_r4=True)
        html = self._card(monkeypatch, pair["apply"]())
        assert ("Both ends of the link r3 GigabitEthernet4 ↔ r4 GigabitEthernet4:</strong> the "
                "link's verify FAILED") in html, html[-2000:]
        assert "rolled back with its far end: r3 and r4" in html
        assert "End 1 of the link r3 GigabitEthernet4 ↔ r4 GigabitEthernet4" in html, \
            html[html.find("what was sent"):][:3000]
        assert 'id="apply-pair-again"' in html and "Retry r3" not in html
        again = html.split('id="apply-pair-again"', 1)[1].split(">", 1)[0]
        assert "pair=r3:GigabitEthernet4,r4:GigabitEthernet4" in again.replace(
            "%3A", ":").replace("%2C", ","), again

    def test_a_verified_pair_offers_nothing_again(self, pair, monkeypatch):
        html = self._card(monkeypatch, pair["apply"]())
        assert "the link verified" in html and 'id="apply-pair-again"' not in html


class TestTheOtherWays:
    def test_the_link_verified_saves_both_and_rolls_back_neither(self, pair):
        report = pair["apply"]()
        for host, dev in pair["devices"].items():
            assert " ip ospf hello-interval 5" in dev.running and dev.running != dev.before
        assert sorted(pair["saved"]) == ["r3", "r4"]
        assert {r["device"]: r["outcome"] for r in report["results"]} == {
            "r3": "deployed", "r4": "deployed"}
        assert report["pair"]["verify"]["state"] == PD.PASSED and _notes(pair) == {}
        assert pair["golden"] == [["r3", "r4"]]
        assert report["result"]["level"] == "success"
        assert all(r["saved_startup"]["state"] == "saved" for r in _rows(pair).values())

    def test_an_unreadable_link_is_neither_passed_nor_rolled_back(self, pair):
        pair["reads"] = _reads(r4_ospf_raises=True)
        report = pair["apply"]()
        assert all(d.running != d.before for d in pair["devices"].values())
        assert sorted(pair["saved"]) == ["r3", "r4"] and _notes(pair) == {}
        assert report["pair"]["verify"]["state"] == PD.UNREADABLE
        assert report["result"]["level"] == "partial", "an unread link drawn green"
        assert any(d["kind"] == "link_verify" for d in report["result"]["did_not"]["items"])

    def test_the_first_end_failing_never_sends_the_second(self, pair):
        """Its own verify failed, so its pipeline rolled it back; the second is never sent,
        and its half is marked so a plan never offers it alone."""
        pair["verify_fails"].add("r3")
        report = pair["apply"]()
        r3, r4 = pair["devices"]["r3"], pair["devices"]["r4"]
        assert r3.running == r3.before and r4.sent == [] and r4.running == r4.before
        by = {r["device"]: r for r in report["results"]}
        assert by["r3"]["outcome"] == "failed" and by["r4"]["outcome"] == "unattempted"
        assert "both ends of the link" in by["r4"]["reason"]
        assert set(_notes(pair)) == {"r3", "r4"}
        assert pair["saved"] == []

    def test_the_second_ends_own_verify_failing_rolls_back_the_first(self, pair):
        pair["verify_fails"].add("r4")
        report = pair["apply"]()
        assert all(d.running == d.before and d.sent for d in pair["devices"].values())
        by = {r["device"]: r for r in report["results"]}
        assert by["r3"]["stage"] == "pair" and "its far end r4 did not deploy" in by["r3"]["reason"]
        assert by["r4"]["stage"] == "verify"
        assert set(_notes(pair)) == {"r3", "r4"}

    def test_one_end_refused_at_apply_refuses_both_with_nothing_sent(self, pair):
        from modules.nsot.deploy import command_fingerprint
        good = command_fingerprint(PROGRAM, [], [], [])
        report = pair["apply"](hashes={"r3": good, "r4": "0" * 16})
        assert all(d.sent == [] for d in pair["devices"].values())
        by = {r["device"]: r for r in report["results"]}
        assert by["r3"]["outcome"] == by["r4"]["outcome"] == "refused"
        assert "its far end was refused at apply" in by["r3"]["reason"]
