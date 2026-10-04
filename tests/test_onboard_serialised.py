"""Onboarding's Create and Abandon hold the device (CONCURRENCY_AUDIT R23; 2026-10-04).

Abandon took no device hold, and refused only when `verified_at` was set, which phase two sets
LAST. So an Abandon during phase two removed the manifest entry, the staged credential, NetBox
objects and the reservation under a running onboarding. Create rebuilt its plan and ran with
nothing between the name check and the mint, so two Creates for one name could leave two
identities.

Now Abandon holds the device for its run (a dry run reads only), and Create holds the hostname
from its plan's rebuild to its last step. Another operation's hold refuses either by name and
changes nothing. Here another thread holds the device, as phase two does.
"""

import threading

import pytest

from modules.nsot import device_ops
from tests.test_onboard_abandon import _onboard, repo  # noqa: F401  (the fixture)


@pytest.fixture
def phase_two():
    """Another operation (phase two) holds bp1 on its own thread until released."""
    ready, done = threading.Event(), threading.Event()

    def run():
        with device_ops.hold("probe", "bp1", "onboard", "operator@example.invalid",
                             detail="phase two"):
            ready.set()
            done.wait(30)

    t = threading.Thread(target=run, daemon=True)
    t.start()
    assert ready.wait(10)
    yield
    done.set()
    t.join(10)


def test_an_abandon_during_phase_two_is_refused_and_removes_nothing(repo, phase_two):  # noqa: F811
    from modules.nsot import manifest
    from modules.nsot.onboard import abandon_onboarding

    _onboard(repo)
    out = abandon_onboarding(repo, "bp1", "probe", actor="t",
                             remove_netbox=lambda *a, **k: pytest.fail("NetBox touched"))
    assert out["ok"] is False and out["steps"] == []
    assert out["error"].startswith("Not abandoned: ") and "onboard" in out["error"]
    assert manifest.find_by_name(repo, "bp1")[0], "the identity was released under phase two"


def test_a_dry_run_reads_only_and_is_not_refused_by_the_hold(repo, phase_two):  # noqa: F811
    from modules.nsot.onboard import abandon_onboarding

    _onboard(repo)
    out = abandon_onboarding(repo, "bp1", "probe", actor="t", dry_run=True,
                             remove_netbox=lambda *a, **k: {"ok": True, "message": "dry"})
    assert out["dry_run"] is True and "Not abandoned" not in (out.get("error") or "")


def test_create_holds_the_hostname_from_its_plan_to_its_last_step():
    """Parsed: the Create route's plan rebuild and run are inside one device hold."""
    import ast
    import inspect
    import textwrap

    from routes import onboard

    src = textwrap.dedent(inspect.getsource(onboard.create))
    holds = [w for w in ast.walk(ast.parse(src)) if isinstance(w, ast.With)
             and any("device_ops.hold" in ast.unparse(i.context_expr) for i in w.items)]
    body = "\n".join(ast.unparse(s) for w in holds for s in w.body)
    assert "build_plan(" in body and "run_onboarding(" in body, \
        "Create's plan and run are not inside one device hold"


def test_a_second_create_for_a_held_name_is_refused(phase_two, monkeypatch, tmp_path):
    """Through the route: another operation holds bp1, so Create refuses naming it and
    nothing is planned or minted."""
    import app as nmas
    from routes import onboard

    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(tmp_path))
    monkeypatch.setattr(onboard, "_target_list", lambda data, what: "probe")
    monkeypatch.setattr("modules.identity.require",
                        lambda *a, **k: (type("I", (), {"actor": "t"})(), None))
    monkeypatch.setattr("modules.nsot.onboard.build_plan",
                        lambda **k: pytest.fail("planned under another's hold"))
    r = nmas.app.test_client().post("/onboard/create", json={"hostname": "bp1"})
    body = r.get_json()
    assert r.status_code == 409 and body["error"].startswith("Not created: "), body
