"""Behaviour over presence, the inventory (board TI, item 4; decision D5, docs/TEST_INTEGRITY.md):
every UI test that asserts only presence is listed in tests/presence_only.py, which only
shrinks. The property is scripts/nmas-presence-inventory's, stated in its docstring and read by
parsing: a UI test requests a v2 page or fragment (a test client, or a real browser); it is
presence-only when every assert is on a status or on what the answer drew, and it never presses
a control and asserts the effect. The first known case: C2288's Set value…, drawn and never
pressed (C2331).

- The inventory is complete: a presence-only (or undecided) UI test the list does not hold
  fails, named.
- The list is current: each id it holds still exists and still has its verdict, so a converted
  test must leave.
- The scan's population has a floor, and planted tests are judged as the property says: a
  drawing test and one that posts and reads only its answer found, a pressing one (client or
  browser) and a stand-in that fails when called not, one hiding its press undecided, and
  C2288's shape listed as a control drawn and never pressed.
"""

import importlib.machinery
import importlib.util
import os
import textwrap

import pytest

from tests import presence_only as P

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: The UI tests the scan must keep finding: 2158 measured on 2026-11-03 (15038 test functions
#: parsed); a scan that stopped seeing a kind of request would fall below it.
UI_TESTS_FLOOR = 2000

CONVERT = "press the control and assert its effect, docs/TEST_INTEGRITY.md item 4"


def _tool():
    path = os.path.join(ROOT, "scripts", "nmas-presence-inventory")
    loader = importlib.machinery.SourceFileLoader("nmas_presence_inventory", path)
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def tool():
    return _tool()


@pytest.fixture(scope="module")
def scanned(tool):
    found, parsed = tool.inventory(ROOT)
    return found, parsed


def outside(found, verdict, listed):
    """The tests the scan gives *verdict* that *listed* does not hold."""
    return sorted(t for t, (v, _r) in found.items() if v == verdict and t not in listed)


class TestTheInventoryIsComplete:
    def test_no_presence_only_ui_test_is_outside_the_list(self, scanned):
        found, _parsed = scanned
        new = outside(found, "presence", P.PRESENCE_ONLY)
        assert new == [], (
            f"a UI test that asserts only presence: {CONVERT}. "
            + "; ".join(f"{t} ({found[t][1]})" for t in new))

    def test_no_undecided_ui_test_is_outside_the_list(self, scanned):
        found, _parsed = scanned
        new = outside(found, "undecided", P.UNDECIDED)
        assert new == [], (
            "a UI test the parse cannot decide (make its request or press readable, or "
            f"{CONVERT}): " + "; ".join(f"{t} ({found[t][1]})" for t in new))


class TestTheListIsCurrent:
    @pytest.mark.parametrize("name,verdict", [("PRESENCE_ONLY", "presence"),
                                              ("UNDECIDED", "undecided")])
    def test_each_listed_test_still_exists_with_its_verdict(self, scanned, name, verdict):
        found, _parsed = scanned
        stale = sorted(f"{t} ({found[t][0]}: {found[t][1]})" if t in found else
                       f"{t} (no longer a UI test, or gone)"
                       for t in getattr(P, name) if found.get(t, ("", ""))[0] != verdict)
        assert stale == [], (
            f"tests/presence_only.py {name} holds tests that are no longer {verdict}: take "
            "each off (a converted test leaves the list): " + "; ".join(stale))


PLANTED = '''
from tests import browser
from modules.elsewhere import press_somewhere


def test_draws_set_value_and_never_presses_it(client):
    """C2288's shape: the commit's result drew Set value…, and nothing pressed it."""
    html = client.post("/v2/device/s4/intent/commit", data={}).get_data(as_text=True)
    assert 'hx-get="/v2/device/s4/intent/secrets?set=user_lab_secret"' in html
    assert "Set value" in html and "Plan a deploy" not in html


def test_draws_only(client):
    r = client.get("/v2/devices")
    body = r.get_data(as_text=True)
    assert r.status_code == 200 and "Save" in body


def test_status_only(client):
    assert client.get("/v2/settings").status_code == 200


def test_presses_and_reads_the_card_again(client):
    client.get("/v2/device/s4?tab=intent")
    client.post("/v2/device/s4/intent/secrets", data={"ref": "user_lab_secret"})
    again = client.get("/v2/device/s4/intent/secrets").get_data(as_text=True)
    assert "1 with a value" in again


def test_presses_and_asserts_the_store(client, store):
    client.post("/v2/device/s4/intent/commit", data={})
    assert store.read("s4") == "committed"


def test_a_stand_in_that_fails_when_called(client, monkeypatch):
    import pytest
    monkeypatch.setattr("modules.jobs.start", lambda *a: pytest.fail("started"))
    r = client.post("/v2/adopt/confirm", data={})
    assert r.status_code == 400


def test_clicks_in_a_browser(served):
    srv, b = served
    b.go(srv.url("/v2/devices"))
    b.click("#save-all")
    b.wait_for("return !!document.querySelector('.save-done')")


def test_only_looks_in_a_browser(served):
    srv, b = served
    b.go(srv.url("/v2/devices"))
    assert b.js("return !!document.querySelector('#save-all')")


def test_hides_its_press_in_a_function_not_read(client):
    html = client.get("/v2/devices").get_data(as_text=True)
    assert "Save" in html
    press_somewhere(client)


def test_a_read_that_writes_nothing(client, tmp_path):
    client.get("/v2/devices")
    assert not (tmp_path / "store.json").exists()


def test_not_v2(client):
    assert client.get("/api/devices").status_code == 200


def test_not_a_ui_test():
    assert sorted([2, 1]) == [1, 2]
'''


@pytest.fixture
def planted(tool, tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_planted.py").write_text(textwrap.dedent(PLANTED))
    controls = {}
    found, _parsed = tool.inventory(str(tmp_path), controls)
    return {t.split("::")[-1]: v for t, v in found.items()}, controls


class TestTheScan:
    def test_the_population_has_its_floor(self, scanned):
        found, parsed = scanned
        assert len(found) >= UI_TESTS_FLOOR, (len(found), parsed)

    def test_planted_presence_only_tests_are_found_and_named(self, planted):
        found, _controls = planted
        assert found["test_draws_only"][0] == "presence", found["test_draws_only"]
        assert found["test_draws_only"][1].startswith("draws only")
        assert found["test_status_only"] == (
            "presence", "status only: 1 assert(s) on GET /v2/settings's status")
        assert found["test_draws_set_value_and_never_presses_it"][0] == "presence"
        assert "asserts only its own answer" in \
            found["test_draws_set_value_and_never_presses_it"][1]
        assert found["test_only_looks_in_a_browser"][0] == "presence"

    def test_planted_pressing_tests_are_not(self, planted):
        found, _controls = planted
        for name in ("test_presses_and_reads_the_card_again", "test_presses_and_asserts_the_store",
                     "test_a_stand_in_that_fails_when_called", "test_clicks_in_a_browser"):
            assert found[name][0] == "pressing", (name, found[name])
        assert "read after the press" in found["test_presses_and_reads_the_card_again"][1]
        assert "stand-in that fails when called" in \
            found["test_a_stand_in_that_fails_when_called"][1]

    def test_a_hidden_press_is_undecided_never_guessed(self, planted):
        found, _controls = planted
        verdict, reason = found["test_hides_its_press_in_a_function_not_read"]
        assert verdict == "undecided" and "press_somewhere" in reason, reason

    def test_state_and_non_ui_tests_are_told_apart(self, planted):
        found, _controls = planted
        assert found["test_a_read_that_writes_nothing"][0] == "state"
        assert "test_not_v2" not in found and "test_not_a_ui_test" not in found

    def test_a_new_presence_only_test_fails_the_inventory_naming_it(self, planted, tool,
                                                                     tmp_path):
        found, _parsed = tool.inventory(str(tmp_path))
        new = outside(found, "presence", P.PRESENCE_ONLY)
        assert "tests/test_planted.py::test_draws_only" in new, new

    def test_c2288s_shape_is_listed_as_a_control_drawn_and_never_pressed(self, planted):
        _found, controls = planted
        drawn = {t.split("::")[-1]: [p for p, _w in v] for t, v in controls.items()}
        assert drawn == {"test_draws_set_value_and_never_presses_it":
                         ["/v2/device/s4/intent/secrets?set=user_lab_secret"]}, drawn
