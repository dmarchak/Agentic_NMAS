"""A network's record of its SDN evaluation runs (Lab 9 B3 and B4; C2946, C2943): where each
run found Mercury wrong, kept in the network's own folder so History › Export's false-positive
and failure log can list it (modules/history_export.py), beside each script's ``--out`` files,
which stay as they are.

**The store** (``sdn_evaluations.jsonl`` in the network's folder, `config.list_data_path`):
append-only, one JSON object a line, written under the file's lock (`filestore.PathLock`) and
owner-only (`config.open_secure`), as the SDN loop's own logs are (modules/sdn/loop.py). A run's
rows are appended in one write under one lock, so a reader sees a run whole. Each row names its
``script``:

- ``nmas-sdn-false-positives`` (B3, modules/sdn/false_positives.py `keep`): a ``run`` row (its
  id, its label, passes, detections fired, false positives by rule and per pass) and one
  ``false_positive`` row per detection that fired on traffic a person declared normal, with
  its rule, evidence, measurement and what Mercury does with it;
- ``nmas-sdn-b4-eval`` (B4, modules/sdn/b4_eval.py `run`): a ``case_run`` row for each run of
  each case and technique that missed the case's planted issue, kept a false-positive finding,
  or answered a benign case as a threat;
- ``nmas-sdn-cases`` (classify_threat's case recordings, C2954; the script's `keep`): a
  ``case_missed`` row for each run of each case the judge (`cases.sdn_classify_misses`) found a
  miss in, with the case file's expectation, what was got, the judge's misses and the call, all
  of one recording under its run's id.

Nothing here is masked at rest, as the network's other SDN records are not; the export masks
every text on the way out.
"""

import json
import os

#: The store's file, in the network's folder.
FILE = "sdn_evaluations.jsonl"
#: The scripts whose runs are kept here, each the ``script`` its rows name.
FALSE_POSITIVES = "nmas-sdn-false-positives"
B4_EVAL = "nmas-sdn-b4-eval"
SDN_CASES = "nmas-sdn-cases"


def _path(network: str) -> str:
    from modules.config import list_data_path

    return os.path.join(list_data_path(network), FILE)


def keep(network: str, rows: list) -> None:
    """Append *rows* to *network*'s record, in one write under the file's lock."""
    from modules.config import open_secure
    from modules.filestore import PathLock

    if not rows:
        return
    path = _path(network)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    text = "".join(json.dumps(r, sort_keys=True, default=str) + "\n" for r in rows)
    with PathLock(path):
        with open_secure(path, "a", encoding="utf-8") as fh:
            fh.write(text)


def read(network: str) -> dict:
    """Every row of *network*'s record, oldest first: ``{"state": "ok"|"absent"|"unreadable",
    "rows", "error"}``. A line that does not parse makes the record unreadable, said, never a
    shorter record said whole."""
    path = _path(network)
    if not os.path.exists(path):
        return {"state": "absent", "rows": [], "error": ""}
    try:
        with open(path, encoding="utf-8") as fh:
            return {"state": "ok", "error": "",
                    "rows": [json.loads(line) for line in fh if line.strip()]}
    except (OSError, ValueError) as exc:
        return {"state": "unreadable", "rows": [], "error": f"{FILE}: {exc}"}
