"""PromQL evaluated by Prometheus's own engine, in a test (C411): `promtool test rules` over
captured series, the series each expression returns read back from its report.

promtool is test tooling, as the browser is: `~/.local/share/nmas-promtool/usr/bin/promtool`
(the distribution's `promtool` package unpacked there, or `prometheus` where it carries it;
CI's workflow does the same), else one on PATH. A test that needs it skips, naming why, where
it is absent.

Each sample keeps its real time to the millisecond (`STEP_MS`), so a range selector over the
captured series sees the samples a live Prometheus would: a 1 min window over a 60 s scrape
holds one sample, not the two a whole-second grid can line up on its edges.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile

STEP_MS = 100
_HOME = os.path.expanduser("~/.local/share/nmas-promtool/usr/bin/promtool")


def promtool() -> str:
    return _HOME if os.path.exists(_HOME) else (shutil.which("promtool") or "")


def available() -> tuple:
    p = promtool()
    if not p:
        return False, "no promtool (unpack the promtool package into ~/.local/share/nmas-promtool)"
    return True, ""


def _values(samples, t0: float) -> str:
    """promtool's series notation on a STEP_MS grid: each value at its own slot, `_xN` between."""
    out, slot = [], 0
    for t, v in sorted(samples):
        at = int(round((t - t0) * 1000 / STEP_MS))
        if at < slot:
            continue                      # two samples in one slot: the first is kept
        if at > slot:
            out.append(f"_x{at - slot}")
        out.append(repr(float(v)))
        slot = at + 1
    return " ".join(out)


def _series_name(labels: dict) -> str:
    inner = ", ".join(f'{k}="{v}"' for k, v in sorted(labels.items()) if k != "__name__")
    return f"{labels['__name__']}{{{inner}}}"


def evaluate(series: list, queries: list) -> dict:
    """*series*: ``[{"labels", "samples": [[t, v], ...]}]``; *queries*: ``[(expr, t)]``, t in
    the series' own seconds. ``{(expr, t): [labels as text, ...]}``: what each returned, an
    empty list when nothing."""
    t0 = min(t for s in series for t, _v in s["samples"])
    tests = [{"interval": f"{STEP_MS}ms",
              "input_series": [{"series": _series_name(s["labels"]),
                                "values": _values(s["samples"], t0)} for s in series],
              "promql_expr_test": [{"expr": e, "eval_time": f"{int(round((t - t0) * 1000))}ms",
                                    "exp_samples": []} for e, t in queries]}]
    with tempfile.TemporaryDirectory(prefix="nmas-promql-") as d:
        path = os.path.join(d, "t.yml")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"tests": tests}, fh)          # JSON is YAML
        proc = subprocess.run([promtool(), "test", "rules", path], capture_output=True,
                              text=True, timeout=120)
    text = proc.stdout + proc.stderr
    if "error" in text.lower() and "FAILED" not in text and proc.returncode != 0:
        raise RuntimeError(f"promtool refused the test file: {text[-800:]}")
    got = {(e, t): [] for e, t in queries}
    # Each failing expression's entry: `expr: "<expr>", time: <dur>,` then `exp:` and `got:`,
    # the returned series comma-separated on the `got:` line, up to the next entry.
    entry = re.compile(r'expr: "(.*?)", time: ([^,\n]+),.*?got:(.*?)(?=\n\s*expr: |\Z)', re.S)
    for m in entry.finditer(text):
        expr = m.group(1).replace('\\"', '"')
        lines = re.findall(r"\{[^}]*\}", m.group(3))
        for (e, t) in got:
            if e == expr and _same_time(m.group(2), t, t0):
                got[(e, t)] = lines
    return got


def _same_time(dur: str, t: float, t0: float) -> bool:
    ms = int(round((t - t0) * 1000))
    total = 0.0
    for n, unit in re.findall(r"(\d+(?:\.\d+)?)(ms|h|m|s)", dur):
        total += float(n) * {"h": 3600000, "m": 60000, "s": 1000, "ms": 1}[unit]
    return abs(total - ms) < 1
