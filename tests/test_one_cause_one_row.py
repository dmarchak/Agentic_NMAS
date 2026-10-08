"""One cause, one row (the operator, 2026-10-02): the updater's installed copy of
`nmas-deploy` differing from the release produced TWO warnings, the host step's ("A host step
for 4a610813d7, dde849524d, 5bb86cb83d is still to do...") and job health's ("updater differs
from this release's copy"), and one re-install cleared both. By the attach rule, job health's
`differs` row folds into the host step's row, which keeps its own action (it says what to do).

Built through the REAL sources (`host_steps_source` over an owed step in its shape, and
`job_health_source` over a live job-health read), folded by the real `needs_attention`.
"""

import pytest

from modules import attention

STEP = {"id": "4a610813d7:0", "sha": "4a610813d7aa", "shas": ["4a610813d7aa", "dde849524daa",
                                                               "5bb86cb83daa"],
        "step": "re-install the updater's copy of scripts/nmas-deploy (docs/UPDATE.md, "
                "\"Re-install\")",
        "check": "updater", "check_state": "not_done",
        "check_detail": "the installed copy differs from this release's: nmas-deploy"}


def _updater(state):
    return {"jobs": [{"unit": "updater", "state": state, "what": "the Update button's updater",
                      "detail": f"updater: {state}", "since": None}]}


@pytest.fixture
def page(monkeypatch):
    from routes import health
    monkeypatch.setattr(health, "_COMMIT", "f" * 40)

    def render(updater_state, steps=(STEP,)):
        sources = [lambda: attention.host_steps_source(owed={"ok": True, "steps": list(steps)}),
                   lambda: attention.job_health_source(health=lambda: _updater(updater_state))]
        return attention.needs_attention(sources=sources)["rows"]
    return render


def test_differs_folds_into_the_host_step_row_which_keeps_its_action(page):
    rows = page("differs")
    assert [r["source"] for r in rows] == ["host_steps"], [r["what"] for r in rows]
    (r,) = rows
    assert r["action"]["label"].startswith("Do it on the host")
    assert [a["source"] for a in r["attached"]] == ["job_health"]
    assert "differs" in r["attached"][0]["what"]


def test_another_updater_state_stays_its_own_row(page):
    rows = page("writable")
    assert sorted(r["source"] for r in rows) == ["host_steps", "job_health"]


def test_no_owed_step_leaves_the_updater_row_alone(page):
    rows = page("differs", steps=())
    assert [r["id"] for r in rows] == ["job_health:updater"]


def test_an_owed_step_of_another_check_does_not_absorb_it(page):
    other = dict(STEP, id="aaaa:0", check="topology-renderer")
    rows = page("differs", steps=(other,))
    assert sorted(r["source"] for r in rows) == ["host_steps", "job_health"]


# C419 (the operator, 2026-10-04): the Oxidized helper's drift was two rows again, the host
# step's and job health's "helper:oxidized-cred differs". Every root-installed helper folds,
# by the registry (modules/host_helpers.py), not the updater alone. (The Oxidized helper has no
# row since Phase 3 step 2, 2026-10-08: the topology renderer and the updater hold the class.)

def _helper(unit, state):
    return {"jobs": [{"unit": unit, "state": state, "what": "a root-installed helper",
                      "detail": f"{unit}: {state}", "since": None}]}


@pytest.fixture
def helper_page(monkeypatch):
    from routes import health
    monkeypatch.setattr(health, "_COMMIT", "f" * 40)

    def render(check, unit, state):
        step = dict(STEP, id="c2440a6000:0", check=check, step=f"re-install {unit}")
        sources = [lambda: attention.host_steps_source(owed={"ok": True, "steps": [step]}),
                   lambda: attention.job_health_source(health=lambda: _helper(unit, state))]
        return attention.needs_attention(sources=sources)["rows"]
    return render


@pytest.mark.parametrize("check,unit,state", [
    ("topology-renderer", "helper:topology-renderer", "differs")])
def test_every_helpers_drift_folds_into_its_host_step(helper_page, check, unit, state):
    rows = helper_page(check, unit, state)
    assert [r["source"] for r in rows] == ["host_steps"], [r["what"] for r in rows]
    assert [a["source"] for a in rows[0]["attached"]] == ["job_health"]
    assert rows[0]["action"]["label"].startswith("Do it on the host")


@pytest.mark.parametrize("state", ["writable", "cannot_run", "unknown"])
def test_a_helper_state_one_install_does_not_clear_stays_its_own_row(helper_page, state):
    rows = helper_page("topology-renderer", "helper:topology-renderer", state)
    assert sorted(r["source"] for r in rows) == ["host_steps", "job_health"]


def test_a_helpers_step_does_not_absorb_another_helpers_row(helper_page):
    rows = helper_page("updater", "helper:topology-renderer", "differs")
    assert sorted(r["source"] for r in rows) == ["host_steps", "job_health"]
