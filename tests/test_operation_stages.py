"""Every confirm- or approve-gated route declares its preview, hash, verify, rollback and record
(modules/operation_stages.py; the operator, 2026-10-02, rules_audit check 3). The population
is the gate table's own; every reference resolves (an endpoint, a field the view or its helper
reads, an importable function); a stage that does not apply says why, and a gap is MISSING
with its reason, the gaps pinned so they only shrink. Controls: an undeclared gated route, a
reference to nothing, and a stage with no reason are each found.
"""

import importlib
import inspect

import pytest

from modules import operation_stages as S
from modules import route_gates as G

KINDS = ("confirm", "approve")


def population():
    return {ep for ep, gate in G.GATES.items() if gate.kind in KINDS}


@pytest.fixture(scope="module")
def app():
    import app as A
    return A.app


def _resolve(dotted):
    mod, _, attr = dotted.rpartition(".")
    return getattr(importlib.import_module(mod), attr)


def problems(stages, app, gated):
    out = []
    missing = gated - set(stages)
    ghosts = set(stages) - gated
    out += [f"{ep}: gated {G.GATES[ep].kind} with no stages declared" for ep in sorted(missing)]
    out += [f"{ep}: declared but not gated confirm or approve" for ep in sorted(ghosts)]
    endpoints = {r.endpoint for r in app.url_map.iter_rules()}
    for ep, st in stages.items():
        if ep not in gated:
            continue
        for name, value in st._asdict().items():
            if value.startswith(("n/a:", "MISSING:")):
                if len(value.split(":", 1)[1].split()) < 3:
                    out.append(f"{ep}.{name}: says {value!r} with no reason")
                continue
            if name == "preview":
                if value not in endpoints:
                    out.append(f"{ep}.preview: {value} is no endpoint")
            elif name == "hash":
                field, _, where = value.partition(" in ")
                fn = _resolve(where) if where else app.view_functions.get(ep)
                src = inspect.getsource(fn) if fn else ""
                if f'"{field}"' not in src and f"'{field}'" not in src:
                    out.append(f"{ep}.hash: {field!r} is not read by {where or 'the view'}")
            else:
                try:
                    _resolve(value)
                except (ImportError, AttributeError, ValueError) as exc:
                    out.append(f"{ep}.{name}: {value} does not resolve ({exc})")
    return out


def missing_count(stages):
    return sum(1 for st in stages.values() for v in st if v.startswith("MISSING:"))


def test_every_gated_route_declares_its_stages_and_every_reference_resolves(app):
    gated = population()
    assert len(gated) >= 38, len(gated)                       # the floor
    assert problems(S.STAGES, app, gated) == []


def test_the_gaps_only_shrink():
    assert missing_count(S.STAGES) <= S.MISSING_CEILING, missing_count(S.STAGES)


def test_the_operations_that_change_a_device_have_every_stage(app):
    """The deploy pipeline's three entry points, persist and rotate carry all five, no gap."""
    for ep in ("deploy.apply", "golden.restore_apply", "v2.profile_apply_confirm",
               "rotate.apply"):
        assert not any(v.startswith(("MISSING", "n/a")) for v in S.STAGES[ep]), ep


class TestTheControls:
    def test_an_undeclared_gated_route_is_found(self, app):
        stages = dict(S.STAGES)
        stages.pop("deploy.apply")
        assert "deploy.apply: gated confirm with no stages declared" in problems(
            stages, app, population())

    def test_a_reference_to_nothing_is_found(self, app):
        stages = dict(S.STAGES)
        stages["persist.apply"] = S.STAGES["persist.apply"]._replace(
            preview="persist.no_such_preview", hash="no_such_field",
            record="modules.nsot.persist_op.no_such_function")
        got = problems(stages, app, population())
        assert any("persist.apply.preview" in p for p in got)
        assert any("persist.apply.hash" in p for p in got)
        assert any("persist.apply.record" in p for p in got)

    def test_a_stage_with_no_reason_is_found(self, app):
        stages = dict(S.STAGES)
        stages["ai_chat"] = S.STAGES["ai_chat"]._replace(verify="n/a:")
        assert "ai_chat.verify: says 'n/a:' with no reason" in problems(stages, app, population())
