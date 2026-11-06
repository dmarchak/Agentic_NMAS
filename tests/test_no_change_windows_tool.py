"""C2613: `scripts/nmas-no-change-windows` sets the installation's `no_change_windows` only
through `settings_schema.write_settings()`, and only over the value it was told to expect;
`scripts/host-steps/c2613-no-change-windows.sh` sets the one UTC value that holds the backup's
window in both seasons.

1. `show` prints the windows set, `[]` with none.
2. `set` refuses, writing nothing, when the windows set now are not the expected ones, naming
   both; when no actor is named; when the schema refuses the new windows.
3. `set` over the expected value writes it and reads it back; set again, it writes nothing.
4. The host step's OLD and NEW are in the tool's own form, so its plain compare holds, and NEW
   holds every minute the guards' backup window holds (nmas-tier2-probe's), in both seasons,
   ending at its end: 08:30 to 10:30 UTC for 02:30 to 03:30 America/Denver.
"""

import calendar
import importlib.util
import json
import os
import re
from importlib.machinery import SourceFileLoader

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(ROOT, "scripts", "nmas-no-change-windows")
STEP = os.path.join(ROOT, "scripts", "host-steps", "c2613-no-change-windows.sh")
PROBE = os.path.join(ROOT, "scripts", "nmas-tier2-probe")


def _load(path, name):
    loader = SourceFileLoader(name, path)
    spec = importlib.util.spec_from_file_location(name, path, loader=loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


@pytest.fixture
def tool(monkeypatch):
    from modules import settings_schema
    store = {}
    monkeypatch.setattr(settings_schema, "load_user_settings", lambda: dict(store))
    monkeypatch.setattr(settings_schema, "save_user_settings",
                        lambda s: (store.clear(), store.update(s)))
    mod = _load(TOOL, "nmas_no_change_windows")
    mod.store = store
    return mod


def _step_value(name):
    text = open(STEP, encoding="utf-8").read()
    m = re.search(r"^" + name + r"='(.*)'$", text, re.M)
    assert m, name
    return m.group(1).replace("'\"'\"'", "'")


OLD = [{"start": "08:30", "end": "09:10", "reason": "a nightly backup"}]
NEW = [{"start": "08:30", "end": "10:30", "reason": "a nightly backup, both seasons"}]


class TestTheTool:
    def test_show_prints_none_as_an_empty_list(self, tool, capsys):
        assert tool.main(["show"]) == 0
        assert capsys.readouterr().out.strip() == "[]"

    def test_a_value_other_than_the_expected_one_is_refused_naming_both(self, tool, capsys):
        tool.store["no_change_windows"] = NEW
        rc = tool.main(["set", "--expect", json.dumps([]), "--to", json.dumps(OLD),
                        "--actor", "op@example.invalid"])
        out = capsys.readouterr().out
        assert rc == 1 and "REFUSED" in out and "set now" in out and "expected []" in out, out
        assert tool.store["no_change_windows"] == NEW, "nothing written"

    def test_no_actor_is_refused(self, tool, capsys):
        rc = tool.main(["set", "--expect", "[]", "--to", json.dumps(NEW)])
        assert rc == 1 and "no --actor" in capsys.readouterr().out
        assert "no_change_windows" not in tool.store

    def test_a_window_the_schema_refuses_is_refused(self, tool, capsys):
        bad = [{"start": "8:30", "end": "10:30"}]
        rc = tool.main(["set", "--expect", "[]", "--to", json.dumps(bad),
                        "--actor", "op@example.invalid"])
        assert rc == 1 and "write_settings refused" in capsys.readouterr().out
        assert "no_change_windows" not in tool.store

    def test_the_expected_value_is_replaced_and_read_back_then_left(self, tool, capsys):
        tool.store["no_change_windows"] = OLD
        args = ["set", "--expect", json.dumps(OLD), "--to", json.dumps(NEW),
                "--actor", "op@example.invalid"]
        assert tool.main(args) == 0
        out = capsys.readouterr().out
        assert "before: " + json.dumps(OLD, sort_keys=True) in out
        assert "after: " + json.dumps(NEW, sort_keys=True) in out and "read back" in out
        assert tool.store["no_change_windows"] == NEW
        assert tool.main(args) == 0 and "already set" in capsys.readouterr().out


class TestTheHostStepsValue:
    def test_old_and_new_are_in_the_tools_own_form(self):
        for name in ("OLD", "NEW"):
            raw = _step_value(name)
            assert raw == json.dumps(json.loads(raw), sort_keys=True), name

    def test_new_holds_the_guards_window_in_both_seasons_and_ends_at_its_end(self):
        from modules import change_windows
        probe = _load(PROBE, "tier2probe_for_windows")
        (window,) = json.loads(_step_value("NEW"))
        for day in ((2026, 10, 30), (2026, 11, 6)):          # MDT, MST
            midnight = calendar.timegm(day + (0, 0, 0, 0, 0, 0))
            held = [m for m in range(24 * 60) if probe.in_backup_window(midnight + 60 * m)]
            assert held, day
            assert all(change_windows.covers(window, midnight + 60 * m) for m in held), day
        assert window == {**window, "start": "08:30", "end": "10:30"}
        assert change_windows.covers(window, calendar.timegm((2026, 11, 6, 10, 29, 0, 0, 0, 0)))
        assert not change_windows.covers(window,
                                         calendar.timegm((2026, 11, 6, 10, 30, 0, 0, 0, 0)))
