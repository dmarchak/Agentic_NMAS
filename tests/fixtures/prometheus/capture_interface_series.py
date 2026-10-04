#!/usr/bin/env python3
"""Capture the raw interface samples nmas-device's panels read, for one router that streams
telemetry and one switch that does not, from a Prometheus, READ-ONLY (C411, 2026-10-04).

    python3 tests/fixtures/prometheus/capture_interface_series.py http://<prometheus>:9090 r2 s1

Writes interface_series.json beside it. MASKED: only the labels the panels select or group by
are kept (`__name__`, `device`, `job`, `ifName`, `ifIndex`, `name`); addresses, descriptions,
aliases and roles are dropped. The values are interface counters.
"""

import json
import os
import sys
import urllib.parse
import urllib.request

KEEP = ("__name__", "device", "job", "ifName", "ifIndex", "name")
TELEMETRY = "Cisco_IOS_XE_interfaces_oper:interfaces_interface_statistics_"
METRICS = ([f"{TELEMETRY}{m}" for m in ("in_octets", "out_octets_64", "in_errors", "out_errors",
                                         "in_discards", "out_discards")]
           + ["ifHCInOctets", "ifHCOutOctets", "ifInErrors", "ifOutErrors", "ifInDiscards",
              "ifOutDiscards"])
WINDOW = "10m"


def main(base, devices):
    sel = "|".join(METRICS)
    q = f'{{__name__=~"{sel}", device=~"{"|".join(devices)}"}}[{WINDOW}]'
    url = base.rstrip("/") + "/api/v1/query?" + urllib.parse.urlencode({"query": q})
    with urllib.request.urlopen(url, timeout=30) as r:
        got = json.load(r)
    if got.get("status") != "success":
        raise SystemExit(f"Prometheus refused: {got.get('error')}")
    series = []
    for s in got["data"]["result"]:
        labels = {k: v for k, v in s["metric"].items() if k in KEEP}
        series.append({"labels": labels,
                       "samples": [[float(t), float(v)] for t, v in s["values"]]})
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "interface_series.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump({"captured_at": max(t for s in series for t, _ in s["samples"]),
                   "window": WINDOW, "devices": devices, "series": series}, fh, indent=1,
                  sort_keys=True)
        fh.write("\n")
    print(f"wrote {out}: {len(series)} series")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
