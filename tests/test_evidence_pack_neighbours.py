"""The evidence pack's neighbour evidence (C2176, schema 8; the operator's decision of
2026-10-29, built as proposed in the overnight report's section 2b): what the alerting device's
ONE-HOP neighbours logged and recorded in its log window, a section of its own
(modules/evidence_pack.py, `neighbour_events_section`), never counted as the device's own by the
fact sheet (modules/ai/fact_sheet.py) or WHO (modules/ai/who.py), sent by Explain under the
topology class and dropped first under the budget (modules/ai/explain.py), drawn on the card
(templates/v2/_evidence_pack.html).

**Why:** the run sheets' R3, R8, C1 and C4 (C2179 to C2182): the change and its adjacency line
were logged on r6 or r8, the alert fired on r7 or s5, and the pack held only the alerting
device's lines, so Explain could not cite the cause.

On test_evidence_pack_context's world (`ctx`): the eight REAL fleet configs committed as intent,
an inventory naming each with a NetBox id, the Topology reader's value built by the real reader
from the real captures, r1 alerting by IPv6 and r2 by IPv4 (`Interface error rate elevated`,
onset 08:15:00 on 2026-10-15, the pack built at 08:25:00). The network model's one-hop devices,
stated here from the configs (an expectation independent of the walk): r1 shares
10.255.3.0/24 with r2, r3, r4, s3 and s4, and 10.255.2.10/31 with s1; r2 shares 10.255.3.0/24 with
r1, r3, r4, s3 and s4, and 10.255.2.12/31 with s2. s2's committed addresses removed, its
neighbours are its LLDP cables alone (the captured graph: r2 Gi3 to s2 Gi0/2, s1 Gi0/3 to s2
Gi0/3), the shape of C2182's s5, whose only neighbour is r8 by cabling.

The log lines: Loki's capture (tests/fixtures/loki/ask_lines_labelled.json, 2026-10-15: r1's real
`%OSPF-5-ADJCHG` at 08:16:53, and the neighbours' `%SEC_LOGIN`, `%DBAL` and heartbeat lines the
filter leaves out), answered as Loki answers a range (`RangeLoki`: only the lines inside it). Each
planted line is a real line with minimal edits, said where it is planted: s3's captured
`%SYS-5-CONFIG_I` (tests/fixtures/loki/lines_s3.json) moved to a neighbour and into the window,
its `<user>` made `admin`; the console capture's `%LINEPROTO-5-UPDOWN` and `%LINK-3-UPDOWN`
(tests/fixtures/console/s5-kickstart-take-syslog.txt); the reload line is Cisco's documented
form (tests/test_explain_fact_sheet.py's RELOAD4, no capture holds one). The History records
are Walk 2's pack's real History pieces (tests/fixtures/evidence_pack/walk2_r1_pack.json) moved
into the window, answered for the neighbour by History's reader (`timeline`, patched for the
neighbour alone).
"""
import calendar
import copy
import json
import re
import time
from html import unescape

import pytest

from modules import evidence_pack as EP
from modules import history_logq as Q
from modules import history_sources as HS
from modules import network_model as NM
from modules.ai import explain, fact_sheet, who
from tests.test_ai_explain import world  # noqa: F401 (the fixture)
from tests.test_device_v2 import lab  # noqa: F401 (the fixture)
from tests.test_evidence_pack import (V4, V6, DeviceLoki, _alerts, _build,  # noqa: F401
                                      _section, pack_lab)
from tests.test_evidence_pack_context import _pack_sent, ctx  # noqa: F401
from tests.test_history_ask_logs import go_unquote
from tests.test_network_model import commit_fleet

with open("tests/fixtures/evidence_pack/walk2_r1_pack.json", encoding="utf-8") as _fh:
    WALK = json.load(_fh)
with open("tests/fixtures/loki/lines_s3.json", encoding="utf-8") as _fh:
    _S3 = json.load(_fh)
#: s3's captured configuration-change line (lines_s3.json), on vty0 from an IPv4 address.
CONFIG_S3 = next(v for s in _S3["answer"]["data"]["result"] for _t, v in s["values"]
                 if "%SYS-5-CONFIG_I" in v and "on vty0" in v)
LINEPROTO = ("%LINEPROTO-5-UPDOWN: Line protocol on Interface Vlan1, changed state to down")
LINK = "%LINK-3-UPDOWN: Interface Vlan1, changed state to up"
RELOAD = "%SYS-5-RELOAD: Reload requested by admin on vty0 (192.0.2.5). Reload Reason: test."
SEC_LOGIN = ("%SEC_LOGIN-5-LOGIN_SUCCESS: Login Success [user: admin] [Source: 192.0.2.25] "
             "[localport: 22] at 08:16:57 UTC Thu Oct 15 2026")
#: r1's neighbours and r2's, from the configs (the module's docstring).
R1_NEAR = ["r2", "r3", "r4", "s1", "s3", "s4"]
R2_NEAR = ["r1", "r3", "r4", "s2", "s3", "s4"]
#: The window both packs' log lines are read over: the onset 08:15:00 less 15 minutes, to the
#: pack's time 08:25:00 (sooner than 15 minutes after the onset).
FROM, TO = "2026-10-15T08:00:00Z", "2026-10-15T08:25:00Z"


def _t(hms):
    return calendar.timegm(time.strptime(f"2026-10-15T{hms}Z", "%Y-%m-%dT%H:%M:%SZ"))


def _line(dev, hms, message):
    """A syslog line as the collector writes it (the capture's form: the receive time, the
    device, its sequence, its own timestamp, the message)."""
    return f"Oct 15 {hms} {dev} 6001: {dev}: Oct 15 {hms}.120 UTC: {message}"


def _config(dev, hms, address="192.0.2.1", tail=""):
    """s3's captured CONFIG_I line, moved to *dev* at *hms*: its user `admin`, its address
    *address* (an IPv6 one is the rule's IPv6 case), and *tail* (a planted secret) after it."""
    msg = CONFIG_S3[CONFIG_S3.index("%SYS"):]
    msg = msg.replace("<user>", "admin").replace("(192.0.2.1)", f"({address})")
    return _line(dev, hms, msg + tail)


class RangeLoki(DeviceLoki):
    """The capture, answered as Loki answers a range: only the lines inside it, the device
    selector applied (one value or an alternation, read with Go's string rules), and *planted*
    streams ``{device: [(hh:mm:ss, line)]}`` beside the capture's."""

    def __init__(self, planted=None, **k):
        super().__init__(plant=False, **k)
        self.planted = planted or {}

    def _get(self, path, **params):
        got = super()._get(path, **params)
        if not got.get("ok") or not path.endswith("query_range") \
                or params.get("direction") == "forward" or params.get("step"):
            return got
        q = params.get("query", "")
        body = copy.deepcopy(got["response"].json())
        streams = body["data"]["result"]
        labels = {"detected_level": "5", "filename": "/var/log/network/192.0.2.27.log",
                  "host": "nmas", "job": "network_syslog", "service_name": "network_syslog",
                  "severity": "5"}
        for dev, rows in self.planted.items():
            streams.append({"stream": dict(labels, device=dev),
                            "values": [[str(int(_t(hms) * 1e9)), text] for hms, text in rows]})
        m = re.search(r'device(=~?)"', q)
        if m:
            want, _end = go_unquote(q, m.end() - 1)
            regex = m.group(1) == "=~"
            streams = [s for s in streams if (re.fullmatch(want, s["stream"].get("device", ""))
                                              if regex else s["stream"].get("device") == want)]
        lo, hi = int(params["start"]), int(params["end"])
        for s in streams:
            s["values"] = [v for v in s["values"] if lo <= int(v[0]) <= hi]
        body["data"]["result"] = [s for s in streams if s["values"]]
        return {"ok": True, "response": type(got["response"])(body)}


@pytest.fixture
def near(ctx, monkeypatch):  # noqa: F811
    """`ctx` with Loki answering ranges and planted lines (`near.plant`), and History's reader
    answering for a neighbour with planted records (`near.history`)."""
    loki = RangeLoki()
    monkeypatch.setattr(Q, "_client", lambda *a, **k: loki)
    ctx.loki = loki
    ctx.history = {}
    ctx.asked_history = []
    real = HS.timeline

    def timeline(ref, device="", *a, **k):
        if k.get("before") is not None:
            ctx.asked_history.append((device, dict(k)))
            if device in ctx.history:
                return {"events": [dict(e) for e in ctx.history[device]], "errors": [],
                        "total": len(ctx.history[device]), "more": False}
        return real(ref, device, *a, **k)
    monkeypatch.setattr(HS, "timeline", timeline)
    return ctx


def _walk_event(i, at):
    """Walk 2's History piece *i* (1 first) as History's reader returns it, moved to *at*."""
    p = next(x for s in WALK["sections"] if s["name"] == "history" for x in s["pieces"]
             if x["ref"] == f"history:{i}")
    e = {k: v for k, v in p.items() if k not in ("ref", "who")}
    return dict(e, who_short=p["who"], at=at, id=f"e{i}")


def _neighbours(sec):
    return [n["device"] for n in sec.get("neighbours") or []]


def _pieces(sec, **want):
    return [p for p in sec["pieces"] if all(p.get(k) == v for k, v in want.items())]


# ---------------------------------------------------------------- who the neighbours are

class TestTheNeighboursAreTheModelsOneHopDevices:
    @pytest.mark.parametrize("address,device,want", [(V6, "r1", R1_NEAR),
                                                     (V4, "r2", R2_NEAR)])
    def test_by_the_models_links_ipv6_and_ipv4(self, near, address, device, want):
        pack = _build(_alerts(address))
        assert pack["schema"] == EP.SCHEMA == 8 and EP.intact(pack)
        assert pack["device"] == device
        sec = _section(pack, "neighbour_events")
        assert _neighbours(sec) == want
        assert all(n["dev"] == near.ids[n["device"]] for n in sec["neighbours"])
        assert all(n["via"].startswith("link:") for n in sec["neighbours"])
        assert sec["neighbours_total"] == len(want)
        # The same window as the device's own log lines.
        logs = _section(pack, "logs")
        assert (sec["window"]["from"], sec["window"]["to"]) == (FROM, TO)
        assert (logs["window"]["from"], logs["window"]["to"]) == (FROM, TO)

    def test_a_switch_whose_only_neighbours_are_by_cable(self, near):
        """C2182's shape: s2's committed addresses removed, it shares no subnet; its neighbours
        are the LLDP cables the Topology reader captured, never nothing."""
        def edit(host, hv):
            if host == "s2":
                for iface in hv["interfaces"]:
                    for key in ("ipv4", "ipv6", "address", "addresses", "ip"):
                        iface.pop(key, None)
        commit_fleet(near.lab["repo"], edit=edit)
        NM.forget()
        cap = NM.capture("Lab", "s2", hops=NM.CAPTURE_HOPS, now=EP._now())
        got, total = EP.neighbours_of(cap)
        assert [(n, v.split(":")[0]) for _d, n, v in got] == [("r2", "cable"), ("s1", "cable")]
        assert total == 2


# ---------------------------------------------------------------- the lines and the records

class TestTheLinesKept:
    def test_a_real_neighbour_line_is_kept_named_and_never_the_devices_own(self, near):
        """r2's pack: r1's captured ADJCHG at 08:16:53 is a neighbour's line, kept in the
        section naming r1, and not among r2's own lines; the neighbours' captured SEC_LOGIN,
        DBAL and heartbeat lines are left out."""
        pack = _build(_alerts(V4))
        sec = _section(pack, "neighbour_events")
        assert sec["state"] == "ok", sec
        (p,) = sec["pieces"]
        assert (p["evidence"], p["device"], p["dev"], p["line"]) == (
            "log", "r1", near.ids["r1"], "adjacency")
        assert p["text"].startswith("%OSPF-5-ADJCHG: Process 1, Nbr 192.0.2.21")
        assert p["ref"] == "neighbour_events:1" and p["after_onset"] is True
        assert all(x["device"] == "r2" for x in _section(pack, "logs")["pieces"])
        assert "ADJCHG" not in json.dumps(_section(pack, "logs"))
        others = [v for s in near.loki._get("loki/api/v1/query_range", query='{job=~".+"}',
                                            start=str(int(_t("08:00:00") * 1e9)),
                                            end=str(int(_t("08:25:00") * 1e9)))
                  ["response"].json()["data"]["result"]
                  if s["stream"].get("device") in R2_NEAR for v in s["values"]]
        assert len(others) >= 10, "the floor: the neighbours' other captured lines"
        assert sec["lines_total"] == 1 and sec["state"] == "ok"

    def test_change_reload_and_adjacency_lines_kept_the_rest_left_out(self, near):
        near.loki.planted = {"r3": [("08:14:30", _config("r3", "08:14:30")),
                                    ("08:15:10", _line("r3", "08:15:10", RELOAD)),
                                    ("08:15:20", _line("r3", "08:15:20", SEC_LOGIN))],
                             "s1": [("08:16:00", _line("s1", "08:16:00", LINEPROTO)),
                                    ("08:16:01", _line("s1", "08:16:01", LINK))]}
        sec = _section(_build(_alerts(V6)), "neighbour_events")
        got = [(p["device"], p["line"]) for p in sec["pieces"]]
        assert got == [("r3", "config"), ("r3", "reload"), ("s1", "lineproto"),
                       ("s1", "link")]
        assert "SEC_LOGIN" not in json.dumps(sec)
        assert EP.section_count(sec) == "4 lines from 2 neighbours"

    def test_a_line_outside_the_window_is_not_in_the_section(self, near):
        near.loki.planted = {"r3": [("07:50:00", _config("r3", "07:50:00")),
                                    ("08:14:30", _config("r3", "08:14:30"))]}
        sec = _section(_build(_alerts(V6)), "neighbour_events")
        assert [p["at"] for p in sec["pieces"]] == ["2026-10-15T08:14:30Z"]

    def test_at_most_ten_a_neighbour_and_thirty_in_all_nearest_the_onset(self, near):
        """Fourteen lines each on r2, r3, r4 and s3, a minute apart about the onset: ten each
        kept would be forty, so thirty are kept, those nearest the onset, the rest counted."""
        def rows(dev):
            out = []
            for i in range(14):
                at = time.strftime("%H:%M:%S", time.gmtime(_t("08:08:00") + 60 * i))
                out.append((at, _line(dev, at, LINEPROTO)))
            return out
        near.loki.planted = {d: rows(d) for d in ("r2", "r3", "r4", "s3")}
        sec = _section(_build(_alerts(V6)), "neighbour_events")
        assert len(sec["pieces"]) == EP.NEIGHBOUR_LINES_ALL == 30
        per = {n["device"]: n for n in sec["neighbours"]}
        assert all(per[d]["lines"] == 14 for d in ("r2", "r3", "r4", "s3"))
        assert all(per[d]["lines_kept"] <= EP.NEIGHBOUR_LINES_EACH for d in per)
        assert sum(per[d]["lines_kept"] for d in per) == 30
        onset = _t("08:15:00")
        kept = [abs(HS.epoch(p["at"]) - onset) for p in sec["pieces"]]
        # Each neighbour's ten nearest are within 5 minutes of the onset (08:10 to 08:20 holds
        # eleven a neighbour); thirty of the forty, the nearest.
        assert max(kept) <= 300
        assert sec["subset"] is True and sec["total"] == 56
        assert EP.section_count(sec) == "30 lines from 4 neighbours (30 of 56 kept)"

    def test_their_history_inside_the_window_only_at_most_five_a_neighbour(self, near):
        inside = [_walk_event(1, "2026-10-15T08:14:%02dZ" % s) for s in range(0, 14, 2)]
        inside.append(_walk_event(4, "2026-10-15T08:16:00Z"))
        outside = [_walk_event(2, "2026-10-15T07:40:00Z")]
        near.history = {"r3": inside + outside}
        sec = _section(_build(_alerts(V6)), "neighbour_events")
        mine = _pieces(sec, device="r3", evidence="history")
        assert len(mine) == EP.NEIGHBOUR_HISTORY_EACH == 5
        assert all(FROM <= p["at"] <= TO for p in mine)
        assert {p["kind"] for p in mine} <= {"restart", "receipt"}
        per = {n["device"]: n for n in sec["neighbours"]}
        assert (per["r3"]["history"], per["r3"]["history_kept"]) == (8, 5)
        # Each neighbour's History asked by History's own reader, up to the window's end.
        asked = dict(near.asked_history)
        assert set(asked) == set(R1_NEAR)
        assert asked["r3"]["before"] == (int(_t("08:25:00")) + 1, "")
        assert asked["r3"]["kinds"] == EP.HISTORY_KINDS


# ---------------------------------------------------------------- every state said

class TestEveryStateIsSaid:
    def test_empty_says_what_was_read(self, near):
        sec = _section(_build(_alerts(V6)), "neighbour_events")
        assert sec["state"] == "empty" and sec["pieces"] == []
        assert sec["why"] == (f"read {', '.join(R1_NEAR)} between {FROM} and {TO}: Loki holds "
                              "no change or adjacency line from them, and History records "
                              "nothing about them in that window")
        assert EP.section_count(sec) == "no pieces"

    def test_no_log_store_is_not_configured(self, near):
        near.loki.is_configured = lambda: False
        sec = _section(_build(_alerts(V6)), "neighbour_events")
        assert sec["state"] == "not_configured"
        assert sec["why"].startswith("the neighbours' lines were not read: no log store is "
                                     "configured for Lab")

    def test_loki_failing_is_unreadable_with_why(self, near):
        near.loki.fail = "HTTP 502 from Loki"
        sec = _section(_build(_alerts(V6)), "neighbour_events")
        assert sec["state"] == "unreadable" and "HTTP 502" in sec["why"], sec["why"]

    def test_history_failing_for_one_neighbour_is_said(self, near, monkeypatch):
        real = HS.timeline

        def timeline(ref, device="", *a, **k):
            if k.get("before") is not None and device == "s1":
                raise OSError("the receipts store could not be read")
            return real(ref, device, *a, **k)
        monkeypatch.setattr(HS, "timeline", timeline)
        sec = _section(_build(_alerts(V6)), "neighbour_events")
        assert sec["state"] == "empty"
        assert sec["why"].endswith("and History could not be read for s1")
        assert sec["errors"] == ["s1's History: OSError: the receipts store could not be read"]

    def test_the_model_unreadable_is_unreadable_and_no_neighbour_is_absent(self, near):
        ref = type("R", (), {"name": "Lab"})()
        got = EP.neighbour_events_section(ref, "r1", {"ok": False, "error": "boom"},
                                          _t("08:15:00"), _t("08:25:00"), _t("08:25:00"))
        assert (got["state"], got["why"]) == (
            "unreadable", "the network model could not be read (boom), so r1's neighbours "
                          "are not known")
        alone = {"ok": True, "subject": "dev:1", "nodes": {"dev:1": {"name": "r1"}},
                 "reached": {"dev:1": {"hop": 0, "via": ""}}}
        got = EP.neighbour_events_section(ref, "r1", alone, _t("08:15:00"), _t("08:25:00"),
                                          _t("08:25:00"))
        assert got["state"] == "absent" and got["why"].startswith(
            "the network model gives r1 no device one hop away")
        got = EP.neighbour_events_section(ref, "r1", alone, None, _t("08:25:00"),
                                          _t("08:25:00"))
        assert got["state"] == "absent" and "onset is not recorded" in got["why"]

    def test_a_pack_rebuilt_from_the_alert_history_says_its_neighbours_are_of_now(self, near):
        inst = EP.firing(_alerts(V6))[0]
        pack = EP.build(inst, store="grafana-alerts", value_at="", now=_t("08:25:00"),
                        mode="history")
        sec = _section(pack, "neighbour_events")
        assert sec["provenance"] == "rebuilt" and "as it is now" in sec["provenance_words"]
        assert sec["neighbours_from"].startswith("the devices one hop away in the network "
                                                 "model as it is now")
        assert _neighbours(sec) == R1_NEAR


# ---------------------------------------------------------------- never the device's own

def _neighbour_pack(near, own_logs=False):
    """r1's pack with r3's reload and configuration change (IPv6) in the neighbours'
    section and r3's restart and a receipt in its History, r1's own lines and History holding
    none of them."""
    near.loki.planted = {"r3": [("08:14:30", _config("r3", "08:14:30", "2001:db8::1")),
                                ("08:15:10", _line("r3", "08:15:10", RELOAD))]}
    near.history = {"r3": [_walk_event(1, "2026-10-15T08:15:40Z"),
                           _walk_event(4, "2026-10-15T08:14:00Z")]}
    return _build(_alerts(V6))


class TestNeverTheDevicesOwn:
    def test_the_sheet_says_none_for_the_device_and_names_the_neighbours(self, near):
        pack = _neighbour_pack(near)
        sent = explain.sent_sections(pack, explain.topology(pack))
        logs = _section(pack, "logs")
        assert not [p for p in logs["pieces"] if fact_sheet.RELOAD_LINE.search(p["text"])
                    or who.config_change(p["text"])], "the floor: r1's own lines hold neither"
        reloads = fact_sheet.reloads_line(pack, sent)
        assert reloads.startswith("Reloads in the window (computed by Mercury): none: no "
                                  "%SYS-5-RELOAD or %SYS-5-RESTART line")
        assert "r3" not in reloads
        changes = fact_sheet.changes_line(pack, sent)
        assert "r3" not in changes and "configuration change" not in changes.split("History")[0]
        line = fact_sheet.neighbours_line(pack, sent)
        assert line.startswith("Its one-hop neighbours' changes and reloads in the window "
                               "(computed by Mercury), each the neighbour's own, never r1's: ")
        refs = {p["line"] if p["evidence"] == "log" else p["kind"]: p["ref"]
                for p in _section(pack, "neighbour_events")["pieces"]}
        assert (f"2026-10-15T08:14:30Z: r3 logged a configuration change from console, by admin "
                f"on vty0 from 2001:db8::1, r3's account as its log line names it, on the "
                f"neighbour r3, not the alert's device [{refs['config']}]") in line
        assert f"r3 logged '{RELOAD}' [{refs['reload']}]" in line
        # The sheet is computed from the sections as sent, where each person is their stable
        # label (C3424), never their address.
        from modules import display_names
        mark = display_names.label("operator@example.com")
        assert (f"2026-10-15T08:14:00Z: r3: IP SLA probes sent: deployed by {mark}"
                f", on the neighbour r3, not the alert's device [{refs['receipt']}]") in line
        assert "operator@example.com" not in line
        assert f"Mercury's restart record of the neighbour [{refs['restart']}]" in line
        sheet = fact_sheet.sheet(pack, sent).split("\n")
        assert len(sheet) == 1 + len(fact_sheet.LINES) == 7
        assert sheet[fact_sheet.LINES.index("neighbours") + 1] == line

    def test_who_attributes_nothing_to_the_device(self, near):
        pack = _neighbour_pack(near)
        sent = explain.sent_sections(pack, explain.topology(pack))
        refs = [p["ref"] for p in _section(pack, "neighbour_events")["pieces"]]
        got = who.changes_cited(refs + ["neighbour_events"], sent)
        assert {c["kind"] for c in got} == {"neighbour_config_log", "neighbour_history"}
        assert all(c["device"] == "r3" for c in got)
        assert all(c["words"].endswith(", on the neighbour r3, not the alert's device")
                   for c in got)
        # What the device's own sections record is never one of the neighbour's.
        own = ["logs", "history"] + [p["ref"] for s in sent if s["name"] in ("logs", "history")
                                     for p in s["pieces"]]
        assert all(c["kind"] in ("history", "config_log") and "r3" not in c["words"]
                   for c in who.changes_cited(own, sent))
        # A restart is no change by anyone; the reload line is no configuration change.
        nbr = _section(pack, "neighbour_events")["pieces"]
        quiet = [p["ref"] for p in nbr if p.get("line") == "reload" or p.get("kind") ==
                 "restart"]
        assert len(quiet) == 2 and who.changes_cited(quiet, sent) == []

    def test_explain_carries_who_on_the_neighbour_and_never_on_the_device(self, near):
        from modules.ai import triggers
        from tests.ai_person import pressed_by
        from tests.test_ai_explain import _answer
        pack = _neighbour_pack(near)
        assert EP.record(pack)["ok"]
        config = next(p["ref"] for p in _section(pack, "neighbour_events")["pieces"]
                      if p.get("line") == "config")
        near.answer = _answer(pack, rationale="A change on r3 preceded the errors on r1.",
                              hypotheses=[{"claim": "r3's configuration change dropped the "
                                                    "adjacency r1 uses.",
                                           "evidence_refs": [config, "alert"],
                                           "confirm_with": "show ip ospf neighbor"}])
        with pressed_by("operator@example.com"):
            got = explain.explain(pack["id"], actor="operator@example.com",
                                  trigger=triggers.person("operator@example.com"),
                                  send=near.send, today="2026-10-25")
        assert got["ok"] is True, got
        (h,) = got["answer"]["hypotheses"]
        (w,) = h["who"]
        assert w["by"] == "mercury" and w["refs"] == [config]
        assert w["words"].endswith("r3's account as its log line names it, on the neighbour "
                                   "r3, not the alert's device")


# ---------------------------------------------------------------- Explain

class TestExplainSendsIt:
    def test_the_pack_format_describes_it_and_an_older_pack_lacks_it(self, near):
        fmt = explain.vocabulary()
        assert "neighbour_events = " + EP.SECTION_WORDS["neighbour_events"] in fmt
        assert "neighbour_events is what the devices ONE hop from the alert's device" in fmt
        assert "A pack of an older schema (7 or before) holds no such section" in fmt
        assert "sdn" not in fmt, "the SDN section stays out of the cached prefix"
        old = _older(_build(_alerts(V6)))
        sent = explain.sent_sections(old, explain.topology(old))
        lacks = fact_sheet.lacks_line(old, sent)
        assert ("neighbour_events (What its one-hop neighbours logged and recorded around the "
                "onset): not in this pack (pack schema 7)") in lacks
        assert fact_sheet.neighbours_line(old, sent).endswith(
            "not in this pack (pack schema 7, before they were gathered), which is not that "
            "they did nothing.")

    def test_sent_with_the_topology_and_withheld_without_it(self, near, monkeypatch):
        pack = _neighbour_pack(near)
        topo = explain.topology(pack)
        assert topo["sent"]
        (sec,) = [s for s in explain.sent_sections(pack, topo)
                  if s["name"] == "neighbour_events"]
        assert len(sec["pieces"]) == 4 and _neighbours(sec) == R1_NEAR
        from modules.ai import egress_classes
        monkeypatch.setattr(egress_classes, "topology_allowed",
                            lambda network: {"allowed": False, "why": "the class is off"})
        off = explain.topology(pack)
        (sec,) = [s for s in explain.sent_sections(pack, off)
                  if s["name"] == "neighbour_events"]
        assert sec["pieces"] == [] and "neighbours" not in sec and "window" not in sec
        assert sec["withheld"].startswith("what the device's neighbours logged and recorded is "
                                          "not sent: who is near the device is the topology")
        text = json.dumps(sec)
        for name in R1_NEAR:
            assert not re.search(r"(?<![\w-])" + name + r"(?![\w-])", text), name

    def test_the_budget_drops_the_neighbours_first(self, near, monkeypatch):
        from modules.ai import profiles
        pack = _neighbour_pack(near)
        topo = explain.topology(pack)
        order = explain._pack_drop_order(pack, explain.sent_sections(pack, topo))
        mine = [r for c, n, r in order if n == "neighbour_events"]
        assert len(mine) == 4 and order[:4] == [(0, "neighbour_events", r) for r in mine]
        assert all(c > 0 for c, n, _r in order if n != "neighbour_events")
        whole = explain.budgeted(pack, topo, ("explain", 6), explain.SCHEMA_OF[6])
        full, dropped = whole["said"]["estimate"], []
        for budget in (full - 1, full - 400, full // 2, 10):
            monkeypatch.setitem(profiles.TASKS, "explain", dict(
                profiles.TASKS["explain"], max_prompt_tokens=budget))
            got = explain.budgeted(pack, topo, ("explain", 6), explain.SCHEMA_OF[6])
            gone = got["said"]["pack_dropped"]
            dropped.append(gone)
            # A piece of the device's own goes only once every neighbour's piece has gone.
            if set(gone) - {"neighbour_events"}:
                assert gone.get("neighbour_events") == 4, (budget, gone)
        assert any(set(g) - {"neighbour_events"} for g in dropped), \
            "the floor: some budget dropped one of the device's own pieces"
        assert any(g.get("neighbour_events") for g in dropped)


def _older(pack):
    """*pack* as a release of schema 7 kept it: no neighbours' section, hashed so."""
    old = copy.deepcopy(pack)
    old["sections"] = [s for s in old["sections"] if s["name"] != "neighbour_events"]
    old["schema"] = 7
    old.pop("hash")
    old["hash"] = EP.digest(old)
    return old


# ---------------------------------------------------------------- egress

COMMUNITY = "Pl4ntedNbrC0mm"
ENABLE = "Pl4ntedEnabl3Secret"


def test_a_secret_in_a_neighbours_line_never_reaches_the_pack_store_or_bytes(near):
    """A community and an enable secret planted after r3's configuration-change line: the line
    is kept (it is a change line), the values masked in the pack, the store and the bytes
    Explain sends through the real gateway."""
    from modules.ai import triggers
    from tests.ai_person import pressed_by
    from tests.test_ai_explain import _answer
    tail = f" snmp-server community {COMMUNITY} RO enable secret 0 {ENABLE}"
    near.loki.planted = {"r3": [("08:14:30", _config("r3", "08:14:30", tail=tail))]}
    pack = _build(_alerts(V6))
    (p,) = _section(pack, "neighbour_events")["pieces"]
    assert p["line"] == "config" and "<redacted:" in p["text"], p["text"]
    text = json.dumps(pack)
    assert COMMUNITY not in text and ENABLE not in text
    assert EP.record(pack)["ok"]
    with open(EP._path(), encoding="utf-8") as fh:
        stored = fh.read()
    assert COMMUNITY not in stored and ENABLE not in stored
    near.answer = _answer(pack, hypotheses=[{"claim": "r3's change preceded the errors.",
                                             "evidence_refs": [p["ref"], "alert"],
                                             "confirm_with": "show logging"}])
    with pressed_by("operator@example.com"):
        got = explain.explain(pack["id"], actor="operator@example.com",
                              trigger=triggers.person("operator@example.com"),
                              send=near.send, today="2026-10-25")
    assert got["ok"] is True, got
    sent = near.sent[-1]["bytes"]
    assert COMMUNITY not in sent and ENABLE not in sent
    assert "neighbour_events" in sent and "snmp-server community <redacted:" in sent
    (as_sent,) = [s for s in _pack_sent(near) if s["name"] == "neighbour_events"]
    assert as_sent["pieces"][0]["device"] == "r3"


# ---------------------------------------------------------------- the card

def test_the_card_draws_each_piece_naming_its_neighbour(near):
    pack = _neighbour_pack(near)
    assert EP.record(pack)["ok"]
    r = near.lab["client"].get(f"/v2/monitoring/alerts/pack/{pack['id']}",
                               headers={"HX-Request": "true"})
    html = unescape(r.get_data(as_text=True))
    assert r.status_code == 200, html[:400]
    assert EP.SECTION_WORDS["neighbour_events"] in html
    sec = _section(pack, "neighbour_events")
    for p in sec["pieces"]:
        assert re.search(r'<strong data-neighbour-of="' + re.escape(p["ref"]) + r'" title="a '
                         r'neighbour one hop away; ' + re.escape(p["dev"]) + r'">r3</strong>',
                         html), p["ref"]
    assert f'data-neighbours="{len(R1_NEAR)}"' in html
    assert "r3</span> 2 lines, 2 records" in html
    assert "2 lines, 2 records from 1 neighbour" in html


def test_a_pack_of_schema_7_is_drawn_as_it_is_and_says_it_lacks_them(near):
    old = _older(_build(_alerts(V6)))
    assert EP.intact(old)
    assert EP.record(old)["ok"]
    r = near.lab["client"].get(f"/v2/monitoring/alerts/pack/{old['id']}",
                               headers={"HX-Request": "true"})
    html = unescape(r.get_data(as_text=True))
    assert r.status_code == 200, html[:400]
    assert "Kept with schema 7; this release builds schema 8." in html
    assert "It holds nothing of what its one-hop neighbours logged and recorded" in html
    assert 'data-ref="neighbour_events"' not in html


# ---------------------------------------------------------------- its size

def test_its_size_on_the_captures_and_at_its_caps(near):
    """The section as sent, in characters (about one token a character, the overnight
    report's measure of the fact sheet): r2's pack on the capture holds one line; at its caps
    (thirty lines and five records for each of six neighbours) it is bounded."""
    one = json.dumps(_section(_build(_alerts(V4)), "neighbour_events"), ensure_ascii=False)
    ats = [time.strftime("%H:%M:%S", time.gmtime(_t("08:08:00") + 60 * i)) for i in range(14)]
    near.loki.planted = {d: [(at, _config(d, at)) for at in ats] for d in R1_NEAR}
    near.history = {d: [_walk_event(4, "2026-10-15T08:1%d:00Z" % i) for i in range(6)]
                    for d in R1_NEAR}
    full = _section(_build(_alerts(V6)), "neighbour_events")
    assert len(full["pieces"]) == 30 + 5 * len(R1_NEAR)
    size = len(json.dumps(full, ensure_ascii=False))
    print(f"neighbour_events: {len(one)} characters on the capture (r2), {size} at the caps")
    assert len(one) < 4000 and size < 25000, (len(one), size)
