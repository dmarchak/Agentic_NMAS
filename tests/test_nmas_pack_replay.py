"""`scripts/nmas-pack-replay`, offline: a past alert's evidence pack built through the real
`evidence_pack.build` as of the alert's time, and Explain asked twice (v1, then the current
prompt) through the real gateway with a fake `send`.

On tests/test_evidence_pack_context.py's world (the eight real fleet configs committed, the
Loki capture, the planted health answers), with the clock three days after the alert (a replay)
and the Topology reader's questions answered from the real captures
(tests/test_topology_graph.py's `_capture`: LLDP, the routing tables, `up`), each recorded with
the time it was asked for.

- The pack is as of the alert's time: built_at is it, the replay's own time and trigger said;
  every Prometheus question (the topology's, the neighbours', the health figures') asked at
  it; the observed overlay the reader's own code run as of it, never the store's value (which
  is planted later and down); History's later record left out and counted; the Intent check
  said to be of now.
- The synthesized alert is a firing instance in the reader's shape, its onset the one given.
- `--out` inside the checkout is refused; outside it the pack is written owner-only and never
  kept in Mercury's pack store.
- `--explain` prints each call's four token counts, its cost and the answer as recorded, v1's
  request the six sections alone, the current one the topology and the health figures; a
  refusal stops the run with nothing more asked.
"""
import importlib.machinery
import importlib.util
import json
import os
import stat

import pytest

from modules import evidence_pack as EP
from modules.readers import topology_graph as T
from tests.test_ai_explain import _answer, world  # noqa: F401 (fixtures)
from tests.test_device_v2 import lab  # noqa: F401 (the fixture)
from tests.test_evidence_pack import pack_lab  # noqa: F401 (the fixture)
from tests.test_evidence_pack_context import _Resp, _section, ctx  # noqa: F401
from tests.test_history_ask_logs import NOW
from tests.test_network_model import store_observed
from tests.test_topology_graph import _capture

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AT = "2026-10-15T08:25:00Z"
#: The replay's clock: three days after the alert.
LATER = NOW + 3 * 86400


def _driver():
    loader = importlib.machinery.SourceFileLoader(
        "nmas_pack_replay", os.path.join(ROOT, "scripts", "nmas-pack-replay"))
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(mod)
    return mod


@pytest.fixture
def replay(ctx, monkeypatch):  # noqa: F811
    """The Topology reader's questions answered from the captures, each asked time recorded;
    the store's value planted LATER and with r1's adjacency to r3 down (it must not be read);
    the clock three days on."""
    from modules.integrations.prometheus import PrometheusIntegration

    results, up = _capture()
    asked = []
    inner = PrometheusIntegration._get

    def get(prom, path, **params):
        q = params.get("query", "")
        if q not in T.METRICS + ("up",):
            # An instant query's evaluation time, or a range query's end.
            asked.append(("other", params.get("time") or params.get("end")))
            return inner(prom, path, **params)
        asked.append((q, params.get("time")))
        if q == "up":
            rows = [{"metric": {"device": d, "job": j}, "value": [NOW, str(v)]}
                    for d, jobs in up.items() for j, v in jobs.items()]
        else:
            rows = [r for d in results for r in results[d].get(q) or []]
        return {"ok": True, "response": _Resp({"status": "success",
                                               "data": {"resultType": "vector",
                                                        "result": rows}})}
    monkeypatch.setattr(PrometheusIntegration, "_get", get)
    from tests.test_topology_graph import _graph
    graph = _graph()
    for link in graph["layers"]["ospf"]:
        if {link["a"], link["b"]} == {"r1", "r3"}:
            link.update(state="down", words="init")
    store_observed(at="2026-10-18T08:00:00Z", graph=graph)
    monkeypatch.setattr(EP, "_now", lambda: LATER)
    monkeypatch.setattr(T, "here", lambda: [])
    ctx.asked = asked
    ctx.driver = _driver()
    return ctx


def _built(w, **kw):
    d = w.driver
    return d.build("Lab", "r1", NOW, NOW - 600, **kw)


def test_the_replayed_pack_is_as_of_the_alerts_time(replay):
    pack = _built(replay)
    assert pack["built_at"] == AT and pack["replayed_at"] == "2026-10-18T08:25:00Z"
    assert pack["trigger"].startswith("replayed by scripts/nmas-pack-replay")
    assert pack["device"] == "r1" and pack["onset"] == "2026-10-15T08:15:00Z"
    w = _section(pack, "health")["window"]
    assert (w["from"], w["to"]) == ("2026-10-15T08:00:00Z", AT), "the onset passed through"
    topo = [t for q, t in replay.asked if q != "other"]
    assert len(topo) == len(T.METRICS) + 1 and set(topo) == {f"{NOW:.3f}"}
    assert {t for q, t in replay.asked if q == "other"} == {f"{NOW:.3f}"}, \
        "the neighbours and the health figures asked as of the alert"
    obs = _section(pack, "observed")
    assert obs["state"] == "ok" and obs["observed_at"] == AT and obs["as_of"] == AT
    r1r3 = [p for p in obs["pieces"] if p.get("proto") is None and p["kind"] == "adjacency"
            and "10.255.3.0/24" in p["id"] and "dev:300" in p["id"] and "dev:302" in p["id"]]
    assert r1r3 and r1r3[0]["state"] == "up", "the store's later value was never read"
    hist = _section(pack, "history")
    assert all(p["at"] <= AT for p in hist["pieces"])
    assert "recorded after the alert's time 2026-10-15T08:25:00Z left out" in hist["source"]
    assert "not as of the alert's time" in _section(pack, "intent")["source"]
    assert EP.intact(pack)


def test_the_synthesized_alert_is_a_firing_instance_in_the_readers_shape(replay):
    from modules import attention as A
    inst = replay.driver.instance("r1", NOW, NOW - 600)
    assert EP.firing({"instances": [inst]}) == [inst]
    assert A._onset(inst) == (NOW - 600, "when the condition first held")
    assert inst["labels"]["device"] == "r1" and inst["device_from"] == "label"


def test_out_inside_the_checkout_is_refused_and_the_pack_is_never_stored(replay, tmp_path,
                                                                         capsys):
    d = replay.driver
    before = len(EP.read()["rows"])
    args = ["--network", "Lab", "--device", "r1", "--at", AT]
    inside = os.path.join(ROOT, "nmas-pack-replay-test-pack.json")
    try:
        assert d.main(args + ["--out", inside]) == 2
        assert not os.path.exists(inside)
    finally:
        # A refusal that failed has written into the checkout: the next test must not find it.
        if os.path.exists(inside):
            os.remove(inside)
    out = tmp_path / "replay" / "pack.json"
    assert d.main(args + ["--onset", "2026-10-15T08:05:30Z", "--out", str(out)]) == 0
    pack = json.loads(out.read_text(encoding="utf-8"))
    assert pack["built_at"] == AT and EP.intact(pack)
    assert pack["onset"] == "2026-10-15T08:05:30Z"
    assert _section(pack, "health")["window"]["from"] == "2026-10-15T07:50:30Z", \
        "--onset reaches the window: 15 minutes before it"
    assert stat.S_IMODE(os.stat(out).st_mode) == 0o600
    assert len(EP.read()["rows"]) == before, "never kept in Mercury's pack store"
    said = capsys.readouterr().out
    assert f"written to {out}" in said and "observed ok" in said and "health ok" in said


def test_explain_twice_prints_tokens_cost_and_the_answer(replay):
    from modules.ai import calls
    pack = _built(replay)
    replay.answer = _answer(pack)
    lines = []
    assert replay.driver.explain_twice(pack, "operator@example.com", out=lines.append) == 0
    text = "\n".join(lines)
    assert text.count("input_tokens 4000, output_tokens 300, cache_creation_input_tokens 0, "
                      "cache_read_input_tokens 0, cost $") == 2
    assert "== explain.v1: answered and checked" in text
    assert "== explain.v4: answered and checked" in text
    assert "A configuration change on r1 preceded the errors." in text
    v1, now = (s["body"] for s in replay.sent[-2:])
    import re
    assert re.findall(r'<data name="([^"]+)">', v1["messages"][0]["content"]) == ["alert",
                                                                               "pack"]
    assert '"name":"health"' not in v1["messages"][0]["content"]
    assert re.findall(r'<data name="([^"]+)">', now["messages"][0]["content"]) == [
        "network_topology", "pack", "the_alert"]
    assert '"name":"health"' in now["messages"][0]["content"]
    rows = calls.read()["rows"][:2]
    assert {r["prompt"] for r in rows} == {"explain.v1", "explain.v4"}
    assert {r["schema"] for r in rows} == {"explain.v1", "explain.v2"}


def test_named_versions_are_asked_in_order_a_candidate_s_before_and_after(replay):
    """`--prompt 4 --prompt 5`: the current prompt and the candidate, each through the real
    gateway and recorded under its own version; nothing else is asked."""
    from modules.ai import calls
    pack = _built(replay)
    replay.answer = _answer(pack)
    lines = []
    assert replay.driver.explain_twice(pack, "operator@example.com", out=lines.append,
                                       versions=[4, 5]) == 0
    text = "\n".join(lines)
    assert "== explain.v4: answered and checked" in text
    assert "== explain.v5: answered and checked" in text and "explain.v1" not in text
    assert text.index("== explain.v4") < text.index("== explain.v5"), "asked in order"
    assert {r["prompt"] for r in calls.read()["rows"][:2]} == {"explain.v4", "explain.v5"}


def test_v5_is_a_candidate_never_the_pin():
    """Proved only on newly replayed incidents and the baselines (the operator, 2026-10-26)."""
    from modules.ai import explain, prompts
    assert explain.PROMPT == ("explain", 4) and ("explain", 5) in explain.CANDIDATES
    text = " ".join(prompts.load("explain", 5)["text"].split())
    assert ("When symptoms appear on several devices in the same window, consider a common "
            "cause beneath them early, citing the cross-device evidence.") in text
    assert "s3" not in text and "C1547" not in text and "r1" not in text


def test_a_refusal_stops_the_run(replay):
    replay.settings.pop("ai_hosted")
    lines = []
    assert replay.driver.explain_twice(_built(replay), "operator@example.com",
                                       out=lines.append) == 1
    assert lines[0].startswith("== explain.v1: ai_off")
    assert "stopped at ai_off" in lines[-1] and replay.sent == []
    assert not any("explain.v4" in line for line in lines)
