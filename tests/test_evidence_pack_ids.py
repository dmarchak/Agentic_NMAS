"""One device, one id, in everything Explain sends (C1849); the other alerts around the onset
(C1850); and a rebuilt pack's two-hop health over the network model as it is now (C1851).
modules/evidence_pack.py (`concurrent_section`, `build`'s one walk), modules/ai/explain.py
(`one_id`, `as_now_of`), modules/network_model.py (`capture(observe=False)`).

The walk that found it (the operator's Walk 2, 2026-10-27): Explain on r1's "Device
unreachable (SNMP)" alert, its pack rebuilt from the alert history, answered "couldn't analyse:
the evidence checked cites 'health:dev:uc038a8be:discards', which is not in the pack or the
topology sent". The pack named r1 ``dev:@r1`` (its health figures, read with no walk of the
model) and the topology sent with it named r1 by the model's id: one device, two ids in one
prompt, and the model joined the topology's id to the health figures' form.

On tests/test_evidence_pack_context.py's `ctx` (the real builder over the real captures, the
eight real fleet configs committed as intent, an inventory naming each device with a NetBox
id, so the model's ids are ``dev:<NetBox id>``), each pack kind built by the product's own
builder: captured as its alert fired (live), replayed (built an hour after its time), rebuilt
from the alert history (mode history), and a stored pack of the shape the walk's was (rebuilt
while the model could not be read: ``dev:@r1``). For each, the request Explain makes
(`explain.topology`, `sent_sections`, `parts`, `context`: the code `explain_pack` runs):

- every device the request names has one id, across the topology and the pack as sent;
- every id the request holds is citable (`explain.check` accepts a hypothesis citing it), and
  every citable id is in the request;
- every health figure the request holds is citable by the topology's id for its device: the
  walk's failure exactly.

The alert history is planted in the pack's own network, Lab (its transitions in Grafana's
shape, `alert_history._row`): r3's and r4's "Device unreachable (SNMP)" in the window (r3
resolved before the alert's time, r4 resolved after it), an earlier episode of the alert
itself, two alerts by address only (one IPv4, one IPv6), one before the window, one begun
before the window with no resolve recorded, and one of another network.
"""
import copy
import json
import re

import pytest
import yaml

from modules import alert_history as AH
from modules import evidence_pack as EP
from modules import network_model as NM
from modules.ai import explain
from tests.test_ai_explain import world  # noqa: F401 (the fixture)
from tests.test_device_v2 import lab  # noqa: F401 (the fixture)
from tests.test_evidence_pack import V6, _alerts, _section, pack_lab  # noqa: F401
from tests.test_evidence_pack_context import ctx  # noqa: F401 (the fixture)
from tests.test_history_ask_logs import NOW

RULE = "Device unreachable (SNMP)"
STORE = "grafana-alerts"
V4_ADDR, V6_ADDR = "192.0.2.77", "2001:db8::77"


def _t(hhmm: str) -> float:
    """2026-10-15 at *hhmm* (HH:MM or HH:MM:SS) UTC."""
    hhmm = hhmm if hhmm.count(":") == 2 else hhmm + ":00"
    return AH.epoch(f"2026-10-15T{hhmm}Z")


def _inst():
    return EP.firing(_alerts(V6))[0]


def _rows(inst):
    """The planted history (the module's docstring). The alert's onset is 08:15:00 and its
    time 08:25:00, so its window is 08:00:00 to 08:25:00."""
    def row(rule, state, labels, at, networks=("Lab",)):
        return AH._row(STORE, list(networks), rule, state, labels, _t(at), "backfill")

    def dev(name):
        return {"alertname": RULE, "device": name, "instance": f"192.0.2.{40 + int(name[1])}"}
    own = dict(inst["labels"])
    by_v4 = {"alertname": "Interface output discards", "instance": V4_ADDR}
    by_v6 = {"alertname": "Interface output discards", "instance": V6_ADDR}
    return [
        row(RULE, "Pending", dev("r3"), "08:12"), row(RULE, "Alerting", dev("r3"), "08:14"),
        row(RULE, "Normal", dev("r3"), "08:20"),
        row(RULE, "Pending", dev("r4"), "08:13"), row(RULE, "Alerting", dev("r4"), "08:16"),
        row(RULE, "Normal", dev("r4"), "08:40"),
        # An earlier episode of the alert itself, in the window.
        row(inst["rule"], "Pending", own, "08:02"), row(inst["rule"], "Normal", own, "08:04"),
        # By address only, IPv4 and IPv6.
        row("Interface output discards", "Pending", by_v4, "08:10"),
        row("Interface output discards", "Normal", by_v4, "08:11"),
        row("Interface output discards", "Alerting", by_v6, "08:18"),
        # Before the window: resolved before it opened.
        row(RULE, "Alerting", dev("s1"), "07:00"), row(RULE, "Normal", dev("s1"), "07:05"),
        # Begun before the window, its resolve never recorded.
        row(RULE, "Alerting", dev("s2"), "06:00"),
        # Another network's, in the window.
        row(RULE, "Alerting", dev("r2"), "08:14", networks=("Other",)),
    ]


@pytest.fixture
def kinds(ctx, monkeypatch, tmp_path):  # noqa: F811
    """Each pack kind, built after the planted history is kept (the module's docstring)."""
    monkeypatch.setattr(AH, "_path", lambda: str(tmp_path / "alert_history.jsonl"))
    monkeypatch.setattr(AH, "_networks", lambda: {STORE: ["Lab"]})
    monkeypatch.setattr(AH, "_firing_now", lambda: set())
    inst = _inst()
    assert AH.record(_rows(inst))["ok"]
    packs = {"live": EP.build(inst, store=STORE, value_at="2026-10-15T08:24:00Z", now=NOW),
             "history": EP.build(inst, store=STORE, value_at="", now=NOW, mode="history")}
    with monkeypatch.context() as m:
        m.setattr(EP, "_now", lambda: NOW + 3600)
        packs["replay"] = EP.build(inst, store=STORE, value_at="2026-10-15T08:24:00Z", now=NOW)
    with monkeypatch.context() as m:
        m.setattr(NM, "model_for", lambda network: (None, "planted: the model is unreadable"))
        packs["stored"] = EP.build(inst, store=STORE, value_at="", now=NOW, mode="history")
    NM.forget()
    ctx.packs, ctx.inst = packs, inst
    return ctx


def _request(pack):
    """What Explain sends for *pack* (prompt v4's path in `explain_pack`): the topology, the
    pack as sent, the context; and the sections the check resolves against."""
    topo = explain.topology(pack)
    sections = explain.sent_sections(pack, topo)
    data, ctxp = explain.parts(pack, topo), explain.context(topo)
    return topo, sections, data, ctxp


_LINE = re.compile(r"^(\S+) \(([^,]+), hop (\d+)\): (.*)$")


def _named(data) -> dict:
    """``{device name: {id, ...}}``: every id the request gives each device, from the topology
    sent (its devices) and the pack as sent (the health lines, each piece's ``dev``)."""
    out = {}
    topo = yaml.safe_load(data.get("network_topology") or "") or {}
    for i, d in ((topo.get("devices") or {}) if isinstance(topo, dict) else {}).items():
        if isinstance(d, dict) and d.get("name"):
            out.setdefault(d["name"], set()).add(i)
    for s in json.loads(data["pack"]):
        for line in s.get("lines") or []:
            m = _LINE.match(line)
            assert m, line
            out.setdefault(m.group(1), set()).add(m.group(2))
        for p in s.get("pieces") or []:
            if p.get("dev") and p.get("device"):
                out.setdefault(p["device"], set()).add(p["dev"])
    return out


def _in_request(data) -> set:
    """Every reference the request holds: each "ref" in the pack as sent, each health line's
    figures (health:<the line's id>:<figure>, the pack format's rule), and every id of the
    topology sent."""
    out = set()
    for s in json.loads(data["pack"]):
        out.add(s["ref"])
        out |= {p["ref"] for p in s.get("pieces") or []}
        for line in s.get("lines") or []:
            m = _LINE.match(line)
            out |= {f"health:{m.group(2)}:{part.split()[0]}" for part in m.group(4).split("; ")}
    topo = yaml.safe_load(data.get("network_topology") or "") or {}
    if isinstance(topo, dict):
        for key in ("devices", "links", "adjacencies", "cables"):
            if isinstance(topo.get(key), dict):
                out |= set(topo[key])
    return out


def _citable(pack, topo, sections, ref) -> str:
    """`explain.check`'s verdict on one hypothesis citing *ref*: "" when it is accepted."""
    ans = explain.ExplanationV2(
        outcome=explain.Assessment.answer, rationale="", needs_human=True, why_not="",
        checked=[],
        hypotheses=[explain.Hypothesis(claim="x", evidence_refs=[ref],
                                       confirm_with="show version")])
    return explain.check(ans, pack, topo["ids"] if topo["sent"] else (), sections=sections)


KINDS = ("live", "replay", "history", "stored")


# --------------------------------------------------------------------- C1849: one id

class TestOneIdPerDevice:
    @pytest.mark.parametrize("kind", KINDS)
    def test_every_device_the_request_names_has_one_id(self, kinds, kind):
        topo, _sections, data, _ctx = _request(kinds.packs[kind])
        assert topo["sent"], topo["why"]
        named = _named(data)
        assert named.get("r1"), named
        assert {n: ids for n, ids in named.items() if len(ids) != 1} == {}
        # The model's id wherever the model knows the device.
        for n, ids in named.items():
            if n in kinds.ids:
                assert ids == {kinds.ids[n]}, (n, ids)

    @pytest.mark.parametrize("kind", KINDS)
    def test_every_id_in_the_request_is_citable_and_every_citable_one_is_in_it(self, kinds,
                                                                               kind):
        pack = kinds.packs[kind]
        topo, sections, data, _ctx = _request(pack)
        held = _in_request(data)
        citable = set(topo["ids"]) | {s["ref"] for s in sections} | {
            p["ref"] for s in sections for p in s.get("pieces") or []}
        assert len(held) > 20, sorted(held)
        assert {r: _citable(pack, topo, sections, r) for r in held
                if _citable(pack, topo, sections, r)} == {}
        assert sorted(citable - held) == []

    @pytest.mark.parametrize("kind", KINDS)
    def test_a_figure_is_citable_by_the_topology_s_id_for_its_device(self, kinds, kind):
        """The walk's failure exactly: a figure cited as health:<the topology's id>:<figure>."""
        pack = kinds.packs[kind]
        topo, sections, data, _ctx = _request(pack)
        sent = yaml.safe_load(data["network_topology"])["devices"]
        by_name = {d["name"]: i for i, d in sent.items() if isinstance(d, dict) and "name" in d}
        health = next(s for s in json.loads(data["pack"]) if s["name"] == "health")
        cited = []
        for line in health["lines"]:
            m = _LINE.match(line)
            if m.group(1) not in by_name:
                continue
            for part in m.group(4).split("; "):
                ref = f"health:{by_name[m.group(1)]}:{part.split()[0]}"
                cited.append(ref)
                assert _citable(pack, topo, sections, ref) == "", ref
        assert f"health:{kinds.ids['r1']}:discards" in cited, cited

    def test_a_pack_is_built_with_the_model_s_ids(self, kinds):
        for kind in ("live", "replay", "history"):
            devs = {p["dev"] for p in _section(kinds.packs[kind], "health")["pieces"]}
            assert kinds.ids["r1"] in devs and not any(d.startswith("dev:@") for d in devs), \
                (kind, devs)

    def test_a_stored_pack_is_translated_as_sent_and_never_rewritten(self, kinds):
        """The walk's pack (built while the model could not be read) names r1 dev:@r1; what is
        sent names it by the model's id, the stored pack unchanged and still intact."""
        stored = kinds.packs["stored"]
        before = copy.deepcopy(stored)
        assert {p["dev"] for p in _section(stored, "health")["pieces"]} == {"dev:@r1"}
        topo, sections, _data, _ctx = _request(stored)
        sent = {p["ref"] for s in sections if s["name"] == "health" for p in s["pieces"]}
        assert sent == {f"health:{kinds.ids['r1']}:{f}" for f in ("cpu", "heartbeat",
                                                                    "scrapes", "discards")}
        assert stored == before and EP.intact(stored)
        # What was not sent is not citable, so a citation of the pack's own form is refused.
        assert "as sent" in _citable(stored, topo, sections, "health:dev:@r1:cpu")

    def test_explain_takes_the_walk_s_citation_and_links_it_to_the_pack_s_piece(self, kinds):
        from tests.test_ai_explain import _answer
        stored = kinds.packs["stored"]
        assert EP.record(stored)["ok"]
        ref = f"health:{kinds.ids['r1']}:discards"
        kinds.answer = _answer(stored, outcome="no_fault_found", hypotheses=[],
                               checked=[ref])
        got = explain.explain(stored["id"], actor="operator@example.com", send=kinds.send,
                              today="2026-10-27")
        assert got["ok"] is True, got
        assert got["answer"]["checked"] == [{"ref": "health:dev:@r1:discards", "in_pack": True,
                                             "as_sent": ref}]


# ----------------------------------------------------------------- C1850: other alerts

def _by(pack):
    return {(p["rule"], p.get("device") or p.get("address")): p
            for p in _section(pack, "concurrent")["pieces"]}


class TestTheOtherAlerts:
    @pytest.mark.parametrize("kind", ("live", "replay", "history"))
    def test_every_other_alert_in_the_window_is_listed_as_it_stood_then(self, kinds, kind):
        pack = kinds.packs[kind]
        sec = _section(pack, "concurrent")
        assert sec["state"] == "ok" and sec["window"]["from"] == "2026-10-15T08:00:00Z"
        assert sec["window"]["to"] == "2026-10-15T08:25:00Z"
        got = _by(pack)
        # The alert's own earlier episode is named as its labels name it: by the address it
        # was polled at (r1, by IPv6), the history keeping no device it was not given.
        assert sorted(got) == sorted([
            (RULE, "r3"), (RULE, "r4"), (kinds.inst["rule"], V6),
            ("Interface output discards", V4_ADDR), ("Interface output discards", V6_ADDR)]), \
            sorted(got)
        r3, r4 = got[(RULE, "r3")], got[(RULE, "r4")]
        assert r3["state"] == "resolved" and r3["resolved_at"] == "2026-10-15T08:20:00Z"
        assert r3["fired_at"] == "2026-10-15T08:14:00Z"
        assert r3["started_at"] == "2026-10-15T08:12:00Z"
        # r4 resolved at 08:40, after the alert's time: as it stood then, firing.
        assert r4["state"] == "firing" and r4["resolved_at"] == ""
        assert r3["dev"] == kinds.ids["r3"] and r4["dev"] == kinds.ids["r4"]
        assert got[(kinds.inst["rule"], V6)]["same_alert"] is True
        assert got[("Interface output discards", V6_ADDR)]["address"] == V6_ADDR
        assert got[("Interface output discards", V4_ADDR)]["state"] == "resolved"
        # Each cited by the alert history's own id for its episode.
        eids = {e["id"] for e in AH.episodes(AH.read()["rows"])}
        assert all(p["ref"].startswith("concurrent:") and p["ref"][11:] in eids
                   for p in sec["pieces"]), [p["ref"] for p in sec["pieces"]]
        assert sec["unknown_state"] == 1 and "errors" not in sec

    def test_each_piece_is_citable_and_the_format_names_the_section(self, kinds):
        pack = kinds.packs["history"]
        topo, sections, _data, ctxp = _request(pack)
        for p in _section(pack, "concurrent")["pieces"]:
            assert _citable(pack, topo, sections, p["ref"]) == "", p["ref"]
        assert "concurrent = Other alerts in the network around the onset" in ctxp["pack_format"]
        assert "concurrent:<episode id>" in ctxp["pack_format"]

    def test_marked_captured_when_live_and_rebuilt_afterwards(self, kinds):
        assert _section(kinds.packs["live"], "concurrent")["provenance"] == "captured"
        for kind in ("replay", "history"):
            sec = _section(kinds.packs[kind], "concurrent")
            assert sec["provenance"] == "rebuilt" and "the alert history" in \
                sec["provenance_words"], kind

    def test_over_the_cap_it_keeps_those_nearest_the_onset_and_says_so(self, kinds,
                                                                        monkeypatch):
        monkeypatch.setattr(EP, "MAX_CONCURRENT", 2)
        sec = EP.concurrent_section("Lab", STORE, AH.identity(STORE, kinds.inst["rule"],
                                                              kinds.inst["labels"]),
                                    _t("08:15"), NOW, NOW)
        assert sec["subset"] is True and sec["total"] == 5 and len(sec["pieces"]) == 2
        # Nearest the onset (08:15): r4 began 08:13, r3 08:12; the rest further.
        assert sorted(p["device"] for p in sec["pieces"]) == ["r3", "r4"]

    def test_an_unreadable_or_absent_history_is_said(self, kinds, monkeypatch):
        own = AH.identity(STORE, kinds.inst["rule"], kinds.inst["labels"])
        monkeypatch.setattr(AH, "read", lambda: {"state": "unreadable", "rows": [],
                                                 "error": "PermissionError: denied"})
        sec = EP.concurrent_section("Lab", STORE, own, _t("08:15"), NOW, NOW)
        assert sec["state"] == "unreadable" and "PermissionError" in sec["why"]
        monkeypatch.setattr(AH, "read", lambda: {"state": "absent", "rows": [], "error": ""})
        assert EP.concurrent_section("Lab", STORE, own, _t("08:15"), NOW, NOW)["state"] == \
            "absent"

    def test_a_quiet_network_is_read_and_empty(self, kinds):
        own = AH.identity(STORE, kinds.inst["rule"], kinds.inst["labels"])
        sec = EP.concurrent_section("Lab", STORE, own, _t("10:15"), NOW + 7200, NOW + 7200)
        assert sec["state"] == "empty" and "no other alert of the network Lab" in sec["why"]


# --------------------------------------------- C1851: a rebuilt pack's topology, as now

class TestARebuiltPackIsOfNow:
    def test_its_health_covers_two_hops_in_the_model_as_now_and_says_so(self, kinds):
        sec = _section(kinds.packs["history"], "health")
        hops = {p["device"]: p["hop"] for p in sec["pieces"]}
        assert hops["r1"] == 0 and len(hops) > 1 and max(hops.values()) == 2, hops
        assert "as it is now" in sec["devices_from"] and "may differ from then" in \
            sec["devices_from"]
        assert "as it is now, which may differ from then" in sec["provenance_words"]
        assert sec["errors"] == [] or not any("only the alert's device" in e
                                               for e in sec["errors"])

    def test_nothing_observed_is_read_for_it(self, kinds, monkeypatch):
        def boom(*a, **k):
            raise AssertionError("a rebuilt pack read the observed state")
        monkeypatch.setattr(NM, "observed", boom)
        pack = EP.build(kinds.inst, store=STORE, value_at="", now=NOW, mode="history")
        assert len({p["device"] for p in _section(pack, "health")["pieces"]}) > 1
        for name in ("neighbours", "observed", "endpoints"):
            assert _section(pack, name)["provenance"] == "missing"

    def test_what_is_sent_with_it_says_the_topology_is_of_now(self, kinds):
        topo, _sections, data, _ctx = _request(kinds.packs["history"])
        doc = yaml.safe_load(data["network_topology"])
        assert "as it is now" in doc["as_now"] and "may differ from then" in doc["as_now"]
        assert "nothing observed then was captured" in doc["as_now"]
        assert topo["as_now"] == doc["as_now"]
        assert doc["observed"]["state"].startswith("could not read")

    def test_the_card_draws_the_other_alerts_and_the_answer_says_the_network_is_of_now(
            self, kinds):
        from html import unescape

        from tests.test_ai_explain import _answer
        pack = kinds.packs["history"]
        assert EP.record(pack)["ok"]
        c = kinds.lab["client"]
        page = unescape(c.get(f"/v2/monitoring/alerts/pack/{pack['id']}").get_data(as_text=True))
        assert "Other alerts in the network around the onset" in page
        r3 = _by(pack)[(RULE, "r3")]
        assert f'id="{pack["id"]}-{r3["ref"]}"' in page, "each other alert has its anchor"
        assert "at the alert's time" in page and V6_ADDR in page
        assert "1 other alert begun before the window with no resolve recorded is not listed" \
            in page
        assert "the network model as it is now" in page, "the health section says it"
        kinds.answer = _answer(pack, hypotheses=[{
            "claim": "A cause shared with r3 and r4.", "evidence_refs": [
                r3["ref"], _by(pack)[(RULE, "r4")]["ref"]],
            "confirm_with": "show logging"}])
        r = c.post(f"/v2/monitoring/alerts/pack/{pack['id']}/explain",
                   headers={"HX-Request": "true"})
        html = unescape(r.get_data(as_text=True))
        assert r.status_code == 200 and "A cause shared with r3 and r4." in html, html
        assert f'href="#{pack["id"]}-{r3["ref"]}"' in html
        assert "The network sent with the pack is the network model as it is now" in html

    def test_a_pack_captured_as_its_alert_fired_says_nothing_of_now(self, kinds):
        topo, _sections, data, _ctx = _request(kinds.packs["live"])
        assert "as_now" not in yaml.safe_load(data["network_topology"])
        assert topo["as_now"] == ""
        assert "observed overlay captured" in _section(kinds.packs["live"],
                                                       "health")["devices_from"]
