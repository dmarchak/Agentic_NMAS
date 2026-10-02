"""Every Needs attention row names something wrong AND an action a person can
take (the operator, 2026-10-02, after "labs/lab/configs/r5.cfg is used by the
topology, owned by no managed device": true, nothing wrong, nothing to do, and
one more for every retired device, permanently).

- Every kind of row a source can emit is declared in ``attention.ROW_KINDS``
  with what is wrong and its action; ``row()`` refuses an undeclared kind, an
  information level, and an action whose words say there is nothing to do.
- A scan of the module holds every ``row(`` call to a declared kind and every
  declared kind to a call that emits it, both ways, with floors; a planted
  undeclared call is found.
- No action label the sources or job health hand a row says there is nothing to do.
- The two facts that were rows are said in their source's finding instead:
  r5's leftover lab file (C303's fixture shape) and a release being available.
"""

import ast
import os

import pytest

from modules import attention as A

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "modules", "attention.py")
GOOD = dict(source="drift", kind="drifted", key="Lab:drifted:r1", what="r1 has drifted",
            cause="it differs", action={"label": "Capture it, or put it back"},
            level="danger")

#: Call sites whose kind is computed: the helper's literal first argument (its
#: key prefix) or the values the expression takes, read from the code.
DYNAMIC = {"drift": "add", "grafana": "add"}
FRESHNESS_VERDICTS = ("unapproved", "inconclusive")


def _calls(text: str):
    """``[(function, source, kind)]`` for every ``row(`` call; *kind* is the
    literal, or ``None`` when it is computed."""
    out = []
    tree = ast.parse(text)
    for fn in ast.walk(tree):
        if not isinstance(fn, ast.FunctionDef):
            continue
        for node in ast.walk(fn):
            if not (isinstance(node, ast.Call) and getattr(node.func, "id", "") == "row"):
                continue
            kw = {k.arg: k.value for k in node.keywords}
            src = kw.get("source")
            kind = kw.get("kind")
            out.append((fn.name,
                        src.value if isinstance(src, ast.Constant) else "*",
                        kind.value if isinstance(kind, ast.Constant) else
                        ("<missing>" if kind is None else None)))
    return out


def _helper_kinds(text: str, owner: str) -> set:
    """The literal key prefixes passed to *owner*'s ``add(`` helper."""
    tree = ast.parse(text)
    fn = next(f for f in ast.walk(tree) if isinstance(f, ast.FunctionDef) and f.name == owner)
    kinds = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "add" and node.args:
            first = node.args[0]
            if isinstance(first, ast.Constant):
                kinds.add(first.value.split(":", 1)[0])
            elif isinstance(first, ast.JoinedStr) and isinstance(first.values[0], ast.Constant):
                kinds.add(first.values[0].value.split(":", 1)[0])
    return kinds


def emitted(text: str) -> tuple:
    """``(emitted kinds, problems)`` from the module's source."""
    found, problems = set(), []
    for fn, src, kind in _calls(text):
        if fn in DYNAMIC.values():
            continue        # a source's own add() helper: read through its source, below
        if kind == "<missing>":
            problems.append(f"{fn}: a row() with no kind")
        elif kind is None:
            if fn == "drift_source":
                found |= {("drift", k) for k in _helper_kinds(text, "drift_source")}
            elif fn == "grafana_source":
                found |= {("grafana", k) for k in _helper_kinds(text, "grafana_source")}
            elif fn == "freshness_source":
                found |= {("freshness", k) for k in FRESHNESS_VERDICTS}
            else:
                problems.append(f"{fn}: a computed kind this check cannot read")
        else:
            found.add((src, kind))
    for key in found:
        if key not in A.ROW_KINDS and ("*", key[1]) not in A.ROW_KINDS:
            problems.append(f"{key[0]}/{key[1]} is emitted and not declared in ROW_KINDS")
    return found, problems


class TestEveryKindIsDeclared:
    def test_every_row_call_has_a_declared_kind(self):
        found, problems = emitted(open(SRC, encoding="utf-8").read())
        assert problems == []
        assert len(found) >= 40, found               # the floor: the scan saw the calls

    def test_every_declared_kind_is_emitted(self):
        found, _ = emitted(open(SRC, encoding="utf-8").read())
        assert set(A.ROW_KINDS) - found == set(), "a declared kind nothing emits is a ghost"

    def test_a_planted_undeclared_kind_is_found(self):
        planted = open(SRC, encoding="utf-8").read() + (
            "\n\ndef planted_source():\n"
            "    return row(source='lab-startup', kind='unowned', key='k', what='w',\n"
            "               cause='c', action={'label': 'x'}, level='warning')\n")
        _found, problems = emitted(planted)
        assert problems == ["lab-startup/unowned is emitted and not declared in ROW_KINDS"]

    def test_every_declared_kind_says_what_is_wrong_and_an_action(self):
        assert len(A.ROW_KINDS) >= 40
        for key, (wrong, action) in A.ROW_KINDS.items():
            assert wrong.strip() and action.strip(), key
            assert not any(p in action.lower() for p in A.NOT_AN_ACTION), key


class TestTheConstructorRefuses:
    def test_a_declared_kind_passes(self):
        r = A.row(**GOOD)
        assert r["kind"] == "drifted" and r["level"] == "danger"

    def test_an_undeclared_kind_is_refused(self):
        with pytest.raises(A.RowRefused, match="not declared"):
            A.row(**{**GOOD, "source": "lab-startup", "kind": "unowned"})

    def test_an_information_level_is_refused(self):
        with pytest.raises(A.RowRefused, match="own page's detail"):
            A.row(**{**GOOD, "level": "info"})

    @pytest.mark.parametrize("label", ["Nothing to do: it is information",
                                       "The reason above is what is known",
                                       "No remedy is recorded for this state"])
    def test_an_action_that_says_nothing_to_do_is_refused(self, label):
        with pytest.raises(A.RowRefused, match="nothing to do"):
            A.row(**{**GOOD, "action": {"label": label}})


def _labels(path: str) -> list:
    """Every literal ``"label"`` value in a module (an f-string's text parts)."""
    out = []
    for node in ast.walk(ast.parse(open(path, encoding="utf-8").read())):
        if not isinstance(node, ast.Dict):
            continue
        for k, v in zip(node.keys, node.values):
            if isinstance(k, ast.Constant) and k.value == "label":
                for part in ast.walk(v):
                    if isinstance(part, ast.Constant) and isinstance(part.value, str):
                        out.append(part.value)
    return out


class TestNoActionSaysNothingToDo:
    @pytest.mark.parametrize("module", ["modules/attention.py", "modules/job_health.py"])
    def test_no_label_says_there_is_nothing_to_do(self, module):
        labels = _labels(os.path.join(ROOT, module))
        assert len(labels) >= 20, labels             # the floor: the scan read labels
        said = [l for l in labels if any(p in l.lower() for p in A.NOT_AN_ACTION)]
        assert said == []

    def test_every_job_state_has_an_action_with_none_of_its_own(self):
        for state in list(A._JOB_STATES) + ["something new"]:
            got = A._job_action({"unit": "a-check-of-the-app", "state": state})
            assert got["label"] and not any(p in got["label"].lower() for p in A.NOT_AN_ACTION)


def _lab_cached(unowned):
    value = {"configured": True, "labs": 1, "checked": 0, "devices": [], "errors": [],
             "unowned": unowned}
    return {"state": "ok", "doc": {"last_good": {"value": value,
                                                 "value_at": "2026-10-02T04:00:00Z"},
                                   "stale_after_seconds": 1500}}


class TestTheFactsThatWereRows:
    def test_r5_s_leftover_lab_file_is_the_check_s_finding_not_a_row(self):
        res = A.lab_startup_source(cached=_lab_cached([{
            "lab": "default", "file": "labs/lab/configs/r5.cfg", "node": "r5",
            "declared_by": ["rcn-lab1.clab.yml"], "topologies": ["rcn-lab1.clab.yml"]}]))
        assert res["rows"] == []
        assert ("labs/lab/configs/r5.cfg, used by the topology (rcn-lab1.clab.yml declares "
                "node r5), owned by no managed device") in res["checked"]
        assert "nothing to do" in res["checked"]

    def test_no_leftover_file_says_nothing_extra(self):
        res = A.lab_startup_source(cached=_lab_cached([]))
        assert res["rows"] == [] and "no managed device owns" not in res["checked"]

    def test_the_startup_check_missing_a_device_once_is_the_finding_not_a_row(self):
        res = A.job_health_source(health=lambda: {"jobs": [{
            "unit": "startup-check:unread", "state": "unread", "what": "w",
            "headline": "The startup check could not read 1 of 9 device(s) this hour: s3"}]})
        assert res["rows"] == []
        assert "expected, nothing to do yet: The startup check could not read" in res["checked"]
        persisting = A.job_health_source(health=lambda: {"jobs": [{
            "unit": "startup-check:unread", "state": "unread_persisting", "what": "w",
            "headline": "The startup check has not read s3 since 03:00", "detail": "d"}]})
        assert [r["level"] for r in persisting["rows"]] == ["warning"]
