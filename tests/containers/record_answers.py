"""Record the harness controller's REST answers as a fixture (`scripts/nmas-harness record`).

Run in the harness's runner container, inside the internal network:

    python tests/containers/record_answers.py <out.json> <dpid> [<dpid> ...]

It records `GET /stats/switches`, and for each datapath id `/stats/desc/<dpid>` and
`/stats/portdesc/<dpid>`: each answer's status and body text exactly as Ryu sent it, keyed by
path. The switch is the harness's own Open vSwitch, its port addresses OVS's dummy ports'
(aa:55:aa:55:00:xx) or random per run, so there is nothing to mask.

**One edit, stated in the record's `_edit`:** `/stats/tablefeatures/<dpid>` is recorded for the
FIRST datapath id only, and of its tables only the first two and the last are kept. Open
vSwitch answers 254 tables, 13 MB per switch (measured 2026-11-07), each the same but for its
id and its NEXT_TABLES (the tables after it); the kept three are Ryu's text for those tables,
re-serialised by `json.dumps` with Ryu's key order, every property whole.
"""

import json
import os
import sys
import urllib.error
import urllib.request

REST = os.environ["NMAS_HARNESS_REST"]


def get(path: str) -> dict:
    try:
        with urllib.request.urlopen(REST + path, timeout=30) as answer:
            return {"status": answer.status, "body": answer.read().decode("utf-8")}
    except urllib.error.HTTPError as exc:
        return {"status": exc.code, "body": exc.read().decode("utf-8", errors="replace")}


def trimmed(answer: dict, dpid: str) -> dict:
    tables = json.loads(answer["body"])[dpid]
    kept = tables[:2] + tables[-1:]
    return {"status": answer["status"], "body": json.dumps({dpid: kept}),
            "tables_answered": len(tables)}


def main(out: str, *dpids: str) -> int:
    record = {"/stats/switches": get("/stats/switches")}
    for dpid in dpids:
        for path in (f"/stats/desc/{dpid}", f"/stats/portdesc/{dpid}"):
            record[path] = get(path)
    first = dpids[0]
    record[f"/stats/tablefeatures/{first}"] = trimmed(get(f"/stats/tablefeatures/{first}"),
                                                      first)
    record["_edit"] = (f"/stats/tablefeatures/{first} keeps the first two and the last of the "
                       "tables answered (tables_answered); nothing else is edited")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=1, sort_keys=True)
        fh.write("\n")
    print(f"recorded {len(record) - 1} answers to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
