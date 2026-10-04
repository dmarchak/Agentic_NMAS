"""C411: nmas-device's interface panels answer for a switch, on real data (the operator,
2026-10-04: Traffic in/out, Interface errors and Interface discards were empty for s1 to s4,
in Grafana too, while the fleet dashboard showed their data).

Measured on the host, read-only: the fallback's PromQL was sound; Grafana's `$__rate_interval`
gave a 1 min window (its 15 s default scrape interval, four times over), the switches' SNMP job
is scraped every 60 s, and `rate()` needs two samples in its window: 0 series at 1 min, 10 at
2 min, for s1. The generator now floors every rate's window (`build_nmas_device.rate`).

The data is a REAL capture from the host's Prometheus (`tests/fixtures/prometheus/
interface_series.json`, masked to the labels the panels read: 10 min of r2's telemetry and SNMP
at 30 s, and s1's SNMP at 60 s), evaluated by Prometheus's own engine (`tests/promql.py`,
promtool), every panel query at six moments over the capture's last two minutes, with
`$__rate_interval` as Grafana sets it for a short range (1 min):

- every generated interface panel returns series for r2 (telemetry), for s1 (SNMP only), and
  for r2 with its telemetry removed (a stream that stopped falls back to SNMP);
- the capture reproduces the host's failure: the panels as generated before the floor return
  NOTHING for s1, so the test above is a test of the fix and not of the data.
"""

import importlib.util
import json
import os

import pytest

from tests import promql

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAPTURE = os.path.join(ROOT, "tests", "fixtures", "prometheus", "interface_series.json")
BUILDER = os.path.join(ROOT, "deploy", "grafana", "build_nmas_device.py")
PANELS = ("Traffic in", "Traffic out", "Interface errors", "Interface discards")
#: Grafana's `$__rate_interval` for a short range with its default 15 s scrape interval.
GRAFANA_RATE_INTERVAL = "1m"
TELEMETRY = "Cisco_IOS_XE_interfaces_oper:"


@pytest.fixture(autouse=True)
def _promtool():
    ok, why = promql.available()
    if not ok and os.environ.get("CI"):
        pytest.fail(f"CI unpacks promtool before the tests (.github/workflows/ci.yml): {why}")
    if not ok:
        pytest.skip(why)


def _builder():
    spec = importlib.util.spec_from_file_location("build_nmas_device", BUILDER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _exprs(mod):
    out = {}
    for p in mod.build()["panels"]:
        if p.get("title") in PANELS:
            out[p["title"]] = [t["expr"] for t in p.get("targets", [])]
    assert sorted(out) == sorted(PANELS), sorted(out)
    return out


def _capture():
    with open(CAPTURE, encoding="utf-8") as fh:
        return json.load(fh)


def _run(exprs: dict, series: list, device: str, end: float) -> dict:
    """{panel: [series counts at each moment]}."""
    moments = [end - 120 + 24 * i for i in range(6)]
    queries, index = [], []
    for title, targets in exprs.items():
        for e in targets:
            q = e.replace("$device", device).replace("$__rate_interval", GRAFANA_RATE_INTERVAL)
            for t in moments:
                queries.append((q, t))
                index.append((title, q, t))
    got = promql.evaluate(series, queries)
    counts = {}
    for title, q, t in index:
        counts.setdefault(title, []).append(len(got[(q, t)]))
    return counts


@pytest.mark.parametrize("case", ["r2 with telemetry", "s1 without telemetry",
                                  "r2 with its telemetry removed"])
def test_every_interface_panel_answers(case):
    cap = _capture()
    series = cap["series"]
    device = case.split()[0]
    if case.endswith("removed"):
        series = [s for s in series if not s["labels"]["__name__"].startswith(TELEMETRY)]
    counts = _run(_exprs(_builder()), series, device, cap["captured_at"])
    empty = {title: c for title, c in counts.items() if 0 in c}
    assert empty == {}, f"{case}: a panel returned nothing at some moment: {empty}"


def test_the_capture_reproduces_the_hosts_failure():
    """The panels as generated before the floor (the window `$__rate_interval` alone) return
    nothing for s1 on this data: the capture holds the failure the fix is tested against."""
    mod = _builder()
    mod.rate = lambda series: f"rate({series}[$__rate_interval])"
    cap = _capture()
    counts = _run(_exprs(mod), cap["series"], "s1", cap["captured_at"])
    assert all(c == [0] * 6 for c in counts.values()), counts
    # Not asserted, measured on this capture: r2's 30 s series answered at five of the six
    # moments under those panels: a 1 min window over a 30 s scrape can hold one sample, so a
    # router's panel could blink empty too.
