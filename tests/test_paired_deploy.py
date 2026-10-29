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

C1964's tests are `TestTheFirstEndsTransient`: the same two devices through the pipeline's OWN
pre-snapshot, post-snapshot and verify (`_Lab` answers each read from r3's real captures, as
the two running configs make them). OSPF authentication on r3–r4's link, both ends' intent
gaining it: while only the first end has it, the first end's `show ip ospf neighbor` lacks the
Gi4 row (the one edit: that row removed while the two Gi4s disagree, as a router drops a
neighbour whose hellos it refuses; no capture shows a neighbour going from FULL to down and
back). The first end's verify does not roll back; both apply; the link verifies FULL; both are
saved. Its failure cases roll both back, the first end restored byte for byte; its controls
show the transient is the link's alone.

C1965's tests are `TestTheOrder` and `TestTheOrderAtApply`: planted Topology reads (`_topo`),
the host's own among them, and the attachment found by Mercury's own address, IPv4 and IPv6.
"""

import os
import subprocess

import pytest

from modules import pipeline as _P
from modules.nsot import paired_deploy as PD

#: The pipeline's own stages and the link's own read, kept before any fixture replaces them.
_REAL = {name: getattr(_P, f"_stage_{name}") for name in ("pre_snapshot", "post_snapshot",
                                                          "verify")}
_REAL_READ = PD._read

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


# ── planted Topology reads (C1965): each cable (a, port, b, port[, state]) ──────────

def _id(name):
    return name if name == "mercury" else f"dev:{name}"


def _topo(*cables, why=""):
    """A Topology read as `paired_deploy.topology` returns it, in the network model's shape
    (`network_model.observed`: a cable's two ends by model id and port, ``mercury`` Mercury's
    own host and ``mercury_attaches_here`` on its cable)."""
    out = {}
    for c in cables:
        (x, px), (y, py) = sorted(((_id(c[0]), c[1]), (_id(c[2]), c[3])))
        out[f"cable:{x}/{px}~{y}/{py}"] = dict(
            {"ends": [{"dev": x, "port": px}, {"dev": y, "port": py}],
             "state": c[4] if len(c) > 4 else "up"},
            **({"mercury_attaches_here": True} if "mercury" in (c[0], c[2]) else {}))
    names = {"r3", "r4"} | {n for c in cables for n in (c[0], c[2]) if n != "mercury"}
    return {"names": {n: _id(n) for n in sorted(names)}, "nodes": {},
            "cables": {} if why else out, "read_at": "2026-10-27T16:42:49Z", "why": why}


#: Mercury reaches each end on its own management port: neither through the other.
INDEPENDENT = (("mercury", "eth0", "r3", "Gi1"), ("mercury", "eth0", "r4", "Gi1"),
               ("r3", "Gi4", "r4", "Gi4"))
#: The far end behind the near end: r4 reached only through r3 Gi4, the link.
BEHIND = (("mercury", "eth0", "r3", "Gi1"), ("r3", "Gi4", "r4", "Gi4"))
#: The reverse: r3 reached only through r4 Gi4.
REVERSED = (("mercury", "eth0", "r4", "Gi1"), ("r3", "Gi4", "r4", "Gi4"))
#: The host's own read (scripts/nmas-host, 2026-10-27 16:42 UTC, names and ports only): Mercury
#: attaches at s3 Gi1/1; s3 to r3 Gi3 and to s4; s4 to r4 Gi3; r3 Gi4 to r4 Gi4. r4 is three
#: hops away by s4 and by r3 Gi4 alike.
HOST = (("mercury", "enp6s19", "s3", "Gi1/1"), ("s3", "Gi0/2", "r3", "Gi3"),
        ("s3", "Gi0/3", "s4", "Gi0/3"), ("s4", "Gi0/2", "r4", "Gi3"), ("r3", "Gi4", "r4", "Gi4"))
DESCRIBE = ["interface GigabitEthernet4", " description r3-r4 core", "exit"]


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
    seen = {"verify_fails": set(), "reads": _reads(), "written": [], "golden": [], "saved": [],
            "program": list(PROGRAM), "push_fails": set(), "pushed": [],
            # Mercury reaches each end on its own management port (C1965): the link's order.
            "topology": _topo(*INDEPENDENT)}

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
            seen["pushed"].append(by_ip[ip].host)
            by_ip[ip].sent.append(list(cmds))
            by_ip[ip].apply(cmds)
            if by_ip[ip].host in seen["push_fails"]:
                # The lines landed and the session closed before the push could say so; the
                # failed push recorded as the real stage records one (`_stage_deploy`).
                ctx.push_results[ip] = {"ok": False, "error": "OSError: the session closed"}
                raise P.PipelineStageError(f"{by_ip[ip].host}: the session closed mid-push")
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
        "commands": list(seen["program"]), "merge": list(seen["program"]), "keys": [], "ids": [],
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
    monkeypatch.setattr(PD, "topology", lambda list_name: seen["topology"])

    def apply(order=("r3", "r4"), hashes=None):
        from modules.nsot.deploy import command_fingerprint
        from routes.deploy import _capture_hash, apply_batch
        confirmed = {h: _capture_hash(devs[h].before) for h in order}
        hashes = hashes or {h: command_fingerprint(seen["program"], [], [], []) for h in order}
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


# ── C1964: the first end's expected transient, through the pipeline's own verify ───────

#: OSPF authentication on the link, both ends' intent gaining it (a key chain: no key here).
AUTH = ["interface GigabitEthernet4", " ip ospf authentication key-chain r3-r4", "exit"]
#: An OSPFv3 setting on the link (the IPv6 case beside the IPv4 one).
V3 = ["interface GigabitEthernet4", " ipv6 ospf hello-interval 5", "exit"]
GI4_UP = "GigabitEthernet4 is up, line protocol is up"
#: r3's real rows (tests/fixtures/operational) another adjacency's controls remove.
R3_GI3_R1 = "10.255.1.11     100   FULL/DROTHER    00:00:39    10.255.3.11     GigabitEthernet3"
R3_GI3_R4 = "10.255.1.14     200   FULL/BDR        00:00:39    10.255.3.14     GigabitEthernet3"


class _Lab:
    """Both fake devices' reads, from r3's REAL captures as the two running configs make them
    (r4's: the Gi4 rows' neighbour and address edited to r3's, as `_reads`). While the two Gi4
    sections disagree on the program's line, each *drops* family is down on BOTH ends: the
    OSPF or OSPFv3 Gi4 row removed, or Gi4's line protocol down (the one edit each). *lost*:
    ``{host: [(command, text, replacement)]}`` edited into that host's reads once it holds the
    change (the other losses the tests plant). r4's BGP read is its own capture; every read no capture exists for (EIGRP,
    IS-IS) answers empty, as a router running neither does."""

    def __init__(self, devices, line, drops):
        self.devices, self.line, self.drops, self.lost = devices, line, set(drops), {}

    def differ(self):
        return (self.line in self.devices["r3"].running) != (self.line in
                                                               self.devices["r4"].running)

    def answer(self, host, cmd):
        from modules import pipeline as P
        dev = self.devices[host]
        if cmd.strip() == "show running-config":
            return dev.running
        base = _reads()
        text = {P._INTERFACES_READ: base.get((host, P._INTERFACES_READ)),
                "show ip ospf neighbor": base.get((host, "show ip ospf neighbor")),
                "show ospfv3 neighbor": base.get((host, "show ospfv3 neighbor")),
                "show bgp all summary": _read(f"{host}__show_bgp_all_summary.txt"),
                "show ip route summary": _read("r3__show_ip_route_summary.txt"),
                "show ip protocols": _read("r3__show_ip_protocols.txt"),
                "show ipv6 rip next-hops": _read("r3__show_ipv6_rip_next_hops.txt"),
                }.get(cmd.strip(), "")
        if self.differ():
            gi4 = {"r3": (R3_GI4, V3_R3_GI4), "r4": (R4_GI4, V3_R4_GI4)}[host]
            if "ospf" in self.drops and cmd.strip() == "show ip ospf neighbor":
                text = text.replace(gi4[0], "")
            if "ospfv3" in self.drops and cmd.strip() == "show ospfv3 neighbor":
                text = text.replace(gi4[1], "")
            if "line" in self.drops and cmd.strip() == P._INTERFACES_READ:
                text = text.replace(GI4_UP, "GigabitEthernet4 is up, line protocol is down")
        if self.line in dev.running:
            for command, old, new in self.lost.get(host) or []:
                if command == cmd.strip():
                    assert old in text, f"the planted loss {old!r} is not in {host}'s read"
                    text = text.replace(old, new)
        return text


@pytest.fixture
def lab(pair, monkeypatch):
    """`pair` with the pipeline's OWN pre-snapshot, post-snapshot and verify, and the link's
    own read (`paired_deploy._read`, the allowlist and a session of its own), every read
    answered by `_Lab`. The program is OSPF authentication on the link (`AUTH`) unless a test
    sets another; the settle windows' sleeps are no-ops (the windows' time is counted, not
    slept)."""
    from modules import pipeline as P
    for name, fn in _REAL.items():
        monkeypatch.setattr(P, f"_stage_{name}", fn)
    monkeypatch.setattr(PD, "_read", _REAL_READ)
    monkeypatch.setattr("time.sleep", lambda _s: None)
    pair["program"] = list(AUTH)
    pair["lab"] = _Lab(pair["devices"], AUTH[1], ("ospf",))

    def answer(conn, cmd, *a, **k):
        conn = conn() if callable(conn) and not hasattr(conn, "send_command") else conn
        return pair["lab"].answer(conn.dev.host, cmd)
    monkeypatch.setattr("modules.commands.run_device_command", answer)
    return pair


def _by(report):
    return {r["device"]: r for r in report["results"]}


class TestTheFirstEndsTransient:
    """C1964: the shared link's own adjacency and line protocol on the FIRST end are an
    expected transient, judged by the link's verify after both ends; nothing else is."""

    @pytest.mark.parametrize("program,drops,family", [
        (AUTH, ("ospf",), "ospf"),
        (AUTH, ("ospf", "line"), "ospf"),
        (V3, ("ospfv3",), "ospfv3"),
    ], ids=["ospf-adjacency", "line-protocol-and-adjacency", "ospfv3-adjacency"])
    def test_the_first_end_is_not_rolled_back_and_the_link_verifies(self, lab, program, drops,
                                                                     family):
        """(a) OSPF authentication on r3–r4's link: between the applies r3's Gi4 adjacency to
        r4 (and, in the second case, Gi4's line protocol) is down; r3's verify does not roll
        back, both apply, the link verifies FULL, both are saved."""
        lab["program"], lab["lab"] = list(program), _Lab(lab["devices"], program[1], drops)
        report = lab["apply"]()
        by = _by(report)
        for host, dev in lab["devices"].items():
            assert dev.sent == [program], f"{host}: {dev.sent}"
            assert program[1] in dev.running, f"{host} does not hold the change"
            assert by[host]["outcome"] == "deployed", by[host]
        assert report["pair"]["verify"]["state"] == PD.PASSED, report["pair"]["verify"]
        assert {c["family"]: c["state"] for c in report["pair"]["verify"]["checks"]}[family] \
            == PD.PASSED
        assert sorted(lab["saved"]) == ["r3", "r4"] and _notes(lab) == {}
        assert report["result"]["level"] == "success"
        # Said on the first end's result, with what was seen there between the applies.
        r3 = _rows(lab)["r3"]["checks"]["pair_transient"]
        assert r3["words"] == "the link to r4: judged after both ends", r3
        proto = "OSPFv3" if family == "ospfv3" else "OSPF"
        assert f"{proto} adjacency to r4 on GigabitEthernet4 down" in r3["seen"], r3
        assert ("GigabitEthernet4 line protocol not up" in r3["seen"]) == ("line" in drops)
        # The second end: its line protocol judged as ever, the link's adjacency (which its
        # change brings back) out of both sides of its count.
        r4 = _rows(lab)["r4"]["checks"]["pair_transient"]
        assert r4["words"] == ("the adjacency to r3 on GigabitEthernet4: judged by the link's "
                               "verify after both ends") and r4["seen"] == [], r4
        from modules.preview_confirm import verify_words
        assert any(w.startswith("The link to r4: judged after both ends (seen here between the "
                                "two applies: ") for w in verify_words(_rows(lab)["r3"]["checks"]))

    def test_the_far_end_first_carries_the_transient(self, lab):
        """On the host's own topology r4 goes first (C1965), so r4 is the end whose link is
        the transient."""
        lab["topology"] = _topo(*HOST)
        report = lab["apply"](order=("r4", "r3"))
        assert lab["pushed"] == ["r4", "r3"]
        assert {r["device"]: r["outcome"] for r in report["results"]} == {
            "r4": "deployed", "r3": "deployed"}, report["results"]
        assert report["pair"]["verify"]["state"] == PD.PASSED
        rows = _rows(lab)
        assert rows["r4"]["checks"]["pair_transient"]["words"] == \
            "the link to r3: judged after both ends"
        assert rows["r3"]["checks"]["pair_transient"]["words"].startswith(
            "the adjacency to r4 on GigabitEthernet4: judged by the link's verify")

    @pytest.mark.parametrize("how", ["push_fails", "drifted", "own_verify_fails",
                                     "own_link_line_protocol"])
    def test_the_second_end_failing_rolls_both_back_the_first_byte_for_byte(self, lab, how):
        """(b) r4 fails after r3 applied (its push fails; it is found changed since its capture
        and refused at its apply, nothing sent to it; its own verify fails on an adjacency that
        is not the link's, lost as the link's returns, which a count alone would net to
        nothing; or on its own Gi4's line protocol, which the second end judges as ever): both
        roll back, r3 restored byte for byte, and the r3–r4 adjacency with it (the two Gi4s
        agree again)."""
        from modules import pipeline as P
        r3, r4 = lab["devices"]["r3"], lab["devices"]["r4"]
        if how == "push_fails":
            lab["push_fails"].add("r4")
        elif how == "drifted":
            r4.running = r4.running.replace(" description P2P to r3 Gi4", " description by hand")
        elif how == "own_verify_fails":
            lab["lab"].lost["r4"] = [("show ip ospf neighbor", R3_GI3_R1, "")]
        else:
            lab["lab"].lost["r4"] = [(P._INTERFACES_READ, GI4_UP,
                                      "GigabitEthernet4 is up, line protocol is down")]
        report = lab["apply"]()
        by = _by(report)
        assert r3.sent and r3.running == r3.before, "r3 still holds the change"
        assert by["r3"]["outcome"] == "failed" and by["r3"]["stage"] == "pair", by["r3"]
        assert by["r3"]["rollback_outcome"]["state"] == "restored", by["r3"]
        assert "its far end r4 did not deploy" in by["r3"]["reason"]
        assert by["r4"]["outcome"] != "deployed"
        if how == "drifted":
            assert r4.sent == [], "a device found changed was sent its half"
        else:
            assert r4.sent, "r4 was never sent its half: this is not the case"
            assert AUTH[1] not in r4.running, "r4 still holds the change"
        assert not lab["lab"].differ(), "the two ends disagree after the rollback"
        assert lab["saved"] == [] and "r3" in _notes(lab)

    @pytest.mark.parametrize("command,old,new,drops", [
        ("show ip ospf neighbor", R3_GI3_R1, "", ("ospf",)),
        ("show ip ospf neighbor", R3_GI3_R1, "", ()),
        ("show ip ospf neighbor", R3_GI3_R4, "", ("ospf",)),
        ("show interfaces | include (line protocol|Internet address)",
         "GigabitEthernet3 is up, line protocol is up",
         "GigabitEthernet3 is up, line protocol is down", ("ospf",)),
    ], ids=["another-adjacency", "another-adjacency-link-still-up",
            "the-far-ends-router-id-on-another-interface", "another-interfaces-line-protocol"])
    def test_anything_else_lost_on_the_first_end_still_rolls_it_back(self, lab, command, old,
                                                                     new, drops):
        """The control: the transient is the link's alone. r3 loses, with its change, an
        adjacency on Gi3 (r1's; or r4's own router ID on Gi3, the core VLAN: the same router ID
        as the link's far end, on another interface), with the link's own adjacency down or
        still up, or Gi3's line protocol: r3's verify fails and rolls it back, and r4 is never
        sent."""
        from modules import pipeline as P
        assert command in (P._INTERFACES_READ, "show ip ospf neighbor")
        lab["lab"] = _Lab(lab["devices"], AUTH[1], drops)
        lab["lab"].lost["r3"] = [(command, old, new)]
        report = lab["apply"]()
        by = _by(report)
        r3, r4 = lab["devices"]["r3"], lab["devices"]["r4"]
        assert by["r3"]["outcome"] == "failed" and by["r3"]["stage"] == "verify", by["r3"]
        assert r3.running == r3.before and r4.sent == []
        assert by["r4"]["outcome"] == "unattempted"


class TestAnEndNeverSentIsMarkedAsTheOtherIs:
    """C1967 (2026-10-29): an end found changed since its capture is refused at its own apply
    and sent nothing; its pair failed, so its intent is marked rolled back as an unattempted
    end's is (`_note_unsent`, keyed on its program), its half never offered alone, and it
    never reads as rolled back (nothing was sent, so nothing was undone). The drift is the
    lab's real pre-snapshot (the `lab` fixture: the pipeline's own stages over r3's and r4's
    captures), r4's or r3's running config edited by hand (the one edit)."""

    @staticmethod
    def _drift(dev):
        dev.running = dev.running.replace(" description P2P to r3 Gi4", " description by hand")
        if dev.running == dev.before:
            dev.running = dev.running.replace(" description P2P to r4 Gi4",
                                              " description by hand")
        assert dev.running != dev.before, "the hand edit did not land: this is not the case"

    @pytest.mark.parametrize("drifted", ["r4", "r3"], ids=["second-end", "first-end"])
    def test_the_drifted_end_is_marked_and_never_read_as_rolled_back(self, lab, drifted):
        other = "r3" if drifted == "r4" else "r4"
        self._drift(lab["devices"][drifted])
        report = lab["apply"]()
        by = _by(report)
        assert lab["devices"][drifted].sent == [], "a device found changed was sent its half"
        assert by[drifted]["outcome"] != "deployed", by[drifted]
        notes = _notes(lab)
        assert set(notes) == {"r3", "r4"}, notes
        note = notes[drifted]
        assert note["intent_commit"] == lab["sha"] and note["commands"] == AUTH, note
        assert "not sent" in note["reason"] and "change together or neither does" in \
            note["reason"], note
        # Nothing was sent to it, so nothing was rolled back: never said so.
        assert drifted not in report["pair"]["rolled_back"], report["pair"]
        assert by[drifted]["pair"]["rolled_back_for"] == "", by[drifted]["pair"]
        assert not by[drifted].get("rolled_back"), by[drifted]
        row = _rows(lab)[drifted]
        assert row["sent"] is False and row["rollback"]["performed"] is False, row
        assert lab["saved"] == []
        if drifted == "r4":
            # The first end deployed and was rolled back by its far end's failure.
            assert by[other]["outcome"] == "failed" and by[other]["stage"] == "pair"
            assert other in report["pair"]["rolled_back"]
        else:
            # The first end failed, so the second was never sent: marked as ever.
            assert by[other]["outcome"] == "unattempted" and lab["devices"][other].sent == []
            assert report["pair"]["rolled_back"] == []

    def test_an_end_stopped_before_the_send_is_marked_too(self, lab, monkeypatch):
        """The same class by another stage: r4's pre-snapshot read fails (its session refused
        the read), so its run stops before the send with its program in hand; r3 deployed and
        is rolled back, and r4's intent is marked, never said rolled back."""
        real = lab["lab"].answer

        def answer(host, cmd):
            if host == "r4" and cmd.strip() == "show running-config":
                raise OSError("Authentication to device failed")
            return real(host, cmd)
        monkeypatch.setattr(lab["lab"], "answer", answer)
        report = lab["apply"]()
        by = _by(report)
        assert by["r4"]["outcome"] == "failed" and by["r4"]["stage"] == "pre_snapshot", by["r4"]
        assert by["r4"].get("commands"), "r4 stopped with no program: this is not the case"
        assert lab["devices"]["r4"].sent == []
        notes = _notes(lab)
        assert set(notes) == {"r3", "r4"}, notes
        assert notes["r4"]["commands"] == AUTH and "not sent: pre_snapshot: " in \
            notes["r4"]["reason"], notes["r4"]
        assert report["pair"]["rolled_back"] == ["r3"]
        assert _rows(lab)["r4"]["sent"] is False

    def test_its_own_failure_keeps_the_pipelines_mark(self, lab):
        """The control's other side: an end its own pipeline sent to and rolled back keeps the
        pipeline's mark (its additions, its run's reason), never overwritten by the pair's."""
        lab["push_fails"].add("r4")
        report = lab["apply"]()
        notes = _notes(lab)
        assert set(notes) == {"r3", "r4"}
        assert "not sent" not in notes["r4"]["reason"], notes["r4"]
        assert _by(report)["r4"]["outcome"] == "failed"


class TestWhatEachEndLeavesToTheLink:
    """`transient_for`: what each end's own verify leaves to the link's (C1964)."""

    def _checks(self, program):
        return PD.link_checks(LINK, _both(program), _intents())

    def test_the_first_end_leaves_its_line_protocol_and_the_judged_adjacency(self):
        got = PD.transient_for(LINK, "r3", _intents(), self._checks(AUTH))
        assert got == {"interface": "GigabitEthernet4", "far": "r4",
                       "ids": {"ospf": "10.255.1.14"}, "line": True,
                       "words": "the link to r4: judged after both ends"}

    def test_an_adjacency_the_link_verify_does_not_judge_is_judged_here(self):
        """A description: the link's verify reads its state alone, so the first end leaves
        only its line protocol, and the second end nothing."""
        got = PD.transient_for(LINK, "r3", _intents(), self._checks(DESCRIBE))
        assert got["ids"] == {} and got["line"] is True and got["words"] == (
            "the link to r4: judged after both ends (its line protocol only: the change does "
            "not touch the adjacency across it, which is judged here as ever)")
        assert PD.transient_for(LINK, "r4", _intents(), self._checks(DESCRIBE),
                                first=False) is None

    def test_the_second_end_leaves_the_adjacency_alone_never_its_line_protocol(self):
        got = PD.transient_for(LINK, "r4", _intents(), self._checks(V3), first=False)
        assert got == {"interface": "GigabitEthernet4", "far": "r3",
                       "ids": {"ospfv3": "10.255.1.13"}, "line": False,
                       "words": "the adjacency to r3 on GigabitEthernet4: judged by the link's "
                                "verify after both ends"}

    def test_a_far_end_with_no_router_id_in_intent_is_judged_here(self):
        intents = _intents()
        intents["r4"] = dict(intents["r4"], routing={})
        got = PD.transient_for(LINK, "r3", intents, self._checks(AUTH))
        assert got["ids"] == {} and "r4's router ID is not in its committed intent" in \
            got["words"]


# ── C1965: the order, from Mercury's management path to each end ─────────────────────

def _both(program):
    return {"r3": list(program), "r4": list(program)}


class TestTheOrder:
    """C1965: the end Mercury reaches through the other goes first, said with its path;
    refused when the read cannot say, or when no order keeps both ends reachable."""

    def test_the_far_end_behind_the_near_end_goes_first(self):
        got = PD.order_for(LINK, _topo(*BEHIND), _both(DESCRIBE))
        assert got["refused"] == "" and got["order"] == ["r4", "r3"], got
        assert got["words"] == ("r4 first: Mercury reaches r4 through r3 GigabitEthernet4, the "
                                "link being changed")

    def test_the_near_end_behind_the_far_end_goes_first(self):
        """The control of the above: the same link, Mercury attached at the other end."""
        got = PD.order_for(LINK, _topo(*REVERSED), _both(DESCRIBE))
        assert got["order"] == ["r3", "r4"] and got["words"] == (
            "r3 first: Mercury reaches r3 through r4 GigabitEthernet4, the link being changed")

    def test_independent_paths_keep_the_links_order(self):
        got = PD.order_for(LINK, _topo(*INDEPENDENT), _both(PROGRAM))
        assert got["refused"] == "" and got["order"] == ["r3", "r4"]
        assert got["words"] == (
            "r3 first, as the link names it: neither end is reached through the other (Mercury "
            "reaches r3 directly, on its GigabitEthernet1; Mercury reaches r4 directly, on its "
            "GigabitEthernet1)")

    def test_the_hosts_topology_puts_r4_first(self):
        """The host's read: r4 is as near by s4 as by r3 Gi4, so r3 is on one of its paths and
        r4 goes first; a change that can take the link down is offered, Mercury still
        reaching r4 by s4 without it."""
        desc = PD.order_for(LINK, _topo(*HOST), _both(DESCRIBE))
        assert desc["order"] == ["r4", "r3"] and desc["words"] == (
            "r4 first: Mercury reaches r4 through r3 GigabitEthernet4, the link being changed "
            "(and through s4 GigabitEthernet0/2)")
        auth = PD.order_for(LINK, _topo(*HOST), _both(AUTH))
        assert auth["refused"] == "" and auth["order"] == ["r4", "r3"]
        assert auth["words"] == desc["words"] + (
            "; without that link Mercury still reaches r4 through s4 GigabitEthernet0/2, so a "
            "change that takes the link down leaves both ends reachable")

    def test_no_order_keeps_both_reachable_when_the_link_is_the_far_ends_only_path(self):
        """Each order puts a change on a path it needs (the operator's "both behind each
        other"): r3 first cuts r4 off before r4 is changed; r4 first cuts r4's own path, so it
        could not be rolled back should r3 fail. Refused, naming the path. Its control is the
        same topology with a description, offered above."""
        got = PD.order_for(LINK, _topo(*BEHIND), _both(AUTH))
        assert got["refused"] == (
            "Mercury reaches r4 through r3 GigabitEthernet4, the link being changed, and that "
            "link is its only management path, while r3's program changes the link's OSPF: "
            "r3 first would cut Mercury off from r4 before r4 is changed, and r4 first would "
            "leave r4 unreachable for its rollback should r3 fail; no order keeps both ends "
            "reachable through every step and its rollback"), got["refused"]

    def test_the_confirm_judges_the_order_alone(self):
        """No programs (the confirm's call): the order, never the programs' refusal."""
        got = PD.order_for(LINK, _topo(*BEHIND))
        assert got["refused"] == "" and got["order"] == ["r4", "r3"]

    @pytest.mark.parametrize("program,words", [
        (DESCRIBE, ""),
        (PROGRAM, "changes the link's OSPF"),
        (V3, "changes the link's OSPFv3"),
        (["interface GigabitEthernet4", " shutdown", "exit"],
         "sends `shutdown` to GigabitEthernet4"),
        (["interface GigabitEthernet4", " mtu 1400", "exit"],
         "changes GigabitEthernet4 beyond its description"),
        (["router ospf 1", " area 0 authentication message-digest", "exit"],
         "changes the link's OSPF"),
        (["interface GigabitEthernet3", " mtu 1400", "exit"], ""),
    ], ids=["description", "ospf", "ospfv3", "shutdown", "mtu", "ospf-process", "another-port"])
    def test_what_can_take_the_link_down(self, program, words):
        assert PD.can_cut(program, "GigabitEthernet4") == words

    @pytest.mark.parametrize("topo,words", [
        (_topo(why="the Topology read could not be used (the Topology reader has not read yet)"),
         "Mercury's management path to r3 and r4 is unknown: the Topology read could not be "
         "used (the Topology reader has not read yet); the order is refused rather than "
         "guessed"),
        (_topo(("mercury", "eth0", "r3", "Gi1"), ("r3", "Gi4", "r4", "Gi4", "down")),
         "the Topology read names no path from Mercury to r4"),
        (_topo(("r3", "Gi4", "r4", "Gi4")), "the Topology read shows nowhere Mercury's host "
                                            "attaches"),
        (dict(_topo(*INDEPENDENT), names={"r3": "dev:r3"}),
         "r4 is not in the network's model"),
    ], ids=["unread", "no-path-to-r4", "no-attachment", "not-in-the-model"])
    def test_a_path_it_cannot_read_is_refused_never_guessed(self, topo, words):
        got = PD.order_for(LINK, topo, _both(DESCRIBE))
        assert words in got["refused"], got

    def test_the_topology_read_says_why_it_cannot_be_used(self, monkeypatch):
        from modules import network_model as M
        monkeypatch.setattr(M, "model_for", lambda net: (None, "Lab's inventory could not be "
                                                               "read"))
        assert PD.topology(LIST)["why"] == ("the network model could not be built (Lab's "
                                            "inventory could not be read)")
        monkeypatch.setattr(M, "model_for", lambda net: ({"names": {"r3": "dev:r3"}}, ""))
        monkeypatch.setattr(M, "observed", lambda net, model: {
            "state": "could not read", "why": "the Topology reader has not read yet"})
        got = PD.topology(LIST)
        assert got["why"] == ("the Topology read could not be used (the Topology reader has "
                              "not read yet)") and got["cables"] == {}

    @pytest.mark.parametrize("here,attached", [
        (("eth0", "198.51.100.1/31"), True), (("eth0", "2001:db8:51::99/64"), True),
        (("eth0", "192.0.2.9/24"), False), (("eth0", "2001:db8:99::9/64"), False),
    ], ids=["ipv4", "ipv6", "ipv4-elsewhere", "ipv6-elsewhere"])
    def test_where_mercury_attaches_is_found_by_its_own_address(self, monkeypatch, tmp_path,
                                                                 here, attached):
        """The topology reader's own attachment (`topology_graph.manager_links`: the managed
        interface whose subnet holds one of this host's addresses) through the network
        model's own mapping (`network_model.observed`), IPv4 and IPv6 alike: Mercury's host in
        r3 Gi2's subnet (198.51.100.0/31, 2001:DB8:51::/64; r5 is outside management) reaches
        r4 only through r3 Gi4, so r4 goes first. Its control: an address in no managed
        subnet attaches nowhere, and the order is refused."""
        import time
        from modules import network_model as M, reader_job
        from modules.readers import topology_graph as T
        from tests.registered_networks import register
        register(monkeypatch, tmp_path, LIST)
        cable = {"a": "r3", "port_a": "Gi4", "b": "r4", "port_b": "Gi4", "state": "up",
                 "kind": "both"}
        managers = T.manager_links(_intents(), [cable], {}, [here])
        assert [(m["b"], m["port_b"]) for m in managers] == ([("r3", "Gi2")] if attached
                                                             else [])
        at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        stored = {"value": {"networks": {"lab": {"layers": {"physical": [cable] + managers}}}},
                  "value_at": at}
        monkeypatch.setattr(reader_job, "read_cached", lambda name: {
            "state": "ok", "doc": {"last_good": stored}, "why": ""})
        monkeypatch.setattr(M, "model_for", lambda net: (
            {"names": {"r3": "dev:3", "r4": "dev:4"}, "nodes": {}, "network": LIST}, ""))
        topo = PD.topology(LIST)
        assert topo["why"] == "", topo
        got = PD.order_for(LINK, topo, _both(DESCRIBE))
        if attached:
            assert got["refused"] == "" and got["order"] == ["r4", "r3"], got
            assert got["words"] == ("r4 first: Mercury reaches r4 through r3 GigabitEthernet4, "
                                    "the link being changed")
        else:
            assert "shows nowhere Mercury's host attaches" in got["refused"], got


class TestTheOrderAtApply:
    """C1965: the apply judges the order again with the programs it recomputed; an order
    other than Mercury's, or none it can give, refuses both with nothing sent."""

    @pytest.mark.parametrize("topo,order,program,words", [
        (_topo(*BEHIND), ("r3", "r4"), DESCRIBE, "the confirmed order (r3, r4) is not the "
                                                 "order Mercury's management path gives now "
                                                 "(r4 first"),
        (_topo(*BEHIND), ("r4", "r3"), PROGRAM, "that link is its only management path"),
        (_topo(why="the Topology read could not be used (the Topology reader has not read "
                   "yet)"), ("r3", "r4"), DESCRIBE,
         "Mercury's management path to r3 and r4 is unknown: the Topology read could not be "
         "used (the Topology reader has not read yet); the order is refused rather than "
         "guessed"),
    ], ids=["moved", "no-order-keeps-both", "unread"])
    def test_refused_both_nothing_sent(self, pair, topo, order, program, words):
        pair["topology"], pair["program"] = topo, list(program)
        report = pair["apply"](order=order)
        assert all(d.sent == [] for d in pair["devices"].values())
        by = _by(report)
        for host in IPS:
            assert by[host]["outcome"] == "refused" and words in by[host]["reason"], by[host]
            assert "the order of the link r3 GigabitEthernet4 ↔ r4 GigabitEthernet4 could " \
                "not be kept" in by[host]["reason"]

    def test_mercurys_order_is_kept(self, pair):
        """The control: the same far-end-first topology, the confirmed order Mercury's, and a
        change that cannot cut its path: r4 is sent first."""
        pair["topology"], pair["program"] = _topo(*BEHIND), list(DESCRIBE)
        report = pair["apply"](order=("r4", "r3"))
        assert pair["pushed"] == ["r4", "r3"]
        assert all(r["outcome"] == "deployed" for r in report["results"]), report["results"]
