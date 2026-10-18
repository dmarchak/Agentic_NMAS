"""C1317 (the operator, 2026-10-18): no-change windows are the installation's setting, none by
default, and nothing in the product names one.

- the setting's default is none, and with none set no instant is held;
- a configured window is ``[start, end)`` in UTC; one that starts after its end wraps past
  midnight; a start equal to its end holds nothing and says so;
- the schema refuses any shape but ``{start, end, reason}`` as HH:MM, through the one write
  path; an entry put in the file by hand that is not that shape holds nothing and is logged;
- Credentials › Profiles names each window set, and nothing when none is;
- no product module, route or template names the lab's window (the value the constant held),
  by a scan with a floor and a planted case.

The rotation's own use of a window (refused, stopped, the timer idle) is
tests/test_scheduled_rotation.py's "no-change windows" section.
"""

import calendar
import os
import re
import time

import pytest

from modules import change_windows as CW

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _at(hhmm: str) -> float:
    return calendar.timegm(time.strptime(f"2026-10-12T{hhmm}Z", "%Y-%m-%dT%H:%M:%SZ"))


@pytest.fixture
def data(tmp_path, monkeypatch):
    monkeypatch.setattr("modules.config.DATA_DIR", str(tmp_path))
    monkeypatch.setattr("modules.config.USER_SETTINGS_FILE", str(tmp_path / "user_settings.json"))
    return tmp_path


def _set(*windows):
    from modules.settings_schema import write_settings
    return write_settings({"no_change_windows": list(windows)})


class TestNoneByDefault:
    def test_the_default_is_none(self, data):
        from modules.settings_schema import DEFAULTS, get_setting
        assert DEFAULTS["no_change_windows"] == [] and get_setting("no_change_windows") == []
        assert CW.windows() == []

    @pytest.mark.parametrize("at", ["00:00:00", "08:30:00", "08:45:00", "12:00:00", "23:59:59"])
    def test_with_none_set_no_instant_is_held(self, data, at):
        assert CW.holding(_at(at)) is None


class TestAConfiguredWindow:
    @pytest.mark.parametrize("at,held", [("21:59:59", False), ("22:00:00", True),
                                         ("22:59:59", True), ("23:00:00", False)])
    def test_start_inclusive_end_exclusive(self, data, at, held):
        assert _set({"start": "22:00", "end": "23:00", "reason": "a freeze"})["ok"]
        assert (CW.holding(_at(at)) is not None) is held

    @pytest.mark.parametrize("at,held", [("22:59:59", False), ("23:30:00", True),
                                         ("00:00:00", True), ("00:59:59", True),
                                         ("01:00:00", False)])
    def test_a_start_after_its_end_wraps_past_midnight(self, data, at, held):
        assert _set({"start": "23:30", "end": "01:00"})["ok"]
        assert (CW.holding(_at(at)) is not None) is held

    def test_a_start_equal_to_its_end_holds_nothing_and_says_so(self, data):
        assert _set({"start": "05:00", "end": "05:00"})["ok"]
        assert CW.holding(_at("05:00:00")) is None
        assert "which holds nothing" in CW.words(CW.windows()[0])

    def test_the_first_window_covering_now_is_named(self, data):
        assert _set({"start": "01:00", "end": "02:00", "reason": "one"},
                    {"start": "10:00", "end": "11:00", "reason": "two"})["ok"]
        got = CW.holding(_at("10:15:00"))
        assert got == {"start": "10:00", "end": "11:00", "reason": "two"}
        assert CW.words(got) == "the no-change window 10:00 to 11:00 UTC (two)"
        assert CW.words({"start": "10:00", "end": "11:00", "reason": ""}) == \
            "the no-change window 10:00 to 11:00 UTC"


class TestTheShapeIsHeld:
    @pytest.mark.parametrize("bad", [{"start": "8:30", "end": "09:10"},
                                     {"start": "24:00", "end": "01:00"},
                                     {"start": "08:60", "end": "09:10"},
                                     {"start": "08:30"},
                                     {"start": "08:30", "end": "09:10", "days": "mon"},
                                     "08:30-09:10"])
    def test_the_write_path_refuses_any_other_shape(self, data, bad):
        from modules.settings_schema import get_setting
        got = _set(bad)
        assert got["ok"] is False and "no_change_windows" in (got.get("error") or ""), got
        assert get_setting("no_change_windows") == [], "a refused write stores nothing"

    def test_one_put_in_the_file_by_hand_holds_nothing_and_is_logged(self, data, caplog):
        import json
        with open(data / "user_settings.json", "w", encoding="utf-8") as fh:
            json.dump({"no_change_windows": [{"start": "8:30", "end": "09:10"},
                                             {"start": "10:00", "end": "11:00"}]}, fh)
        assert CW.windows() == [{"start": "10:00", "end": "11:00", "reason": ""}]
        assert CW.holding(_at("08:45:00")) is None
        assert any("holds nothing" in r.getMessage() for r in caplog.records)


class TestTheProfilesPageNamesThem:
    """The page's data; the page drawing it is test_scheduled_rotation's
    `test_the_profiles_page_names_each_window_set`."""

    def test_each_window_set_is_named_and_none_when_none(self, data, monkeypatch):
        from modules.nsot import scheduled_rotation as SR
        monkeypatch.setattr(SR, "device_states", lambda now=None, **_k: [])
        assert SR.page_view(_at("12:00:00"))["no_change_set"] == []
        assert _set({"start": "22:00", "end": "23:00", "reason": "a freeze"})["ok"]
        view = SR.page_view(_at("12:00:00"))
        assert view["no_change_set"] == ["the no-change window 22:00 to 23:00 UTC (a freeze)"]
        assert view["no_change"] == ""
        assert SR.page_view(_at("22:30:00"))["no_change"] == view["no_change_set"][0]


class TestNothingInTheProductNamesTheLabsWindow:
    """The lab's nightly backup window, the value the constant held, in the product's code
    and screens: modules, routes, templates, app.py. The lab's tooling (scripts/, lab/) and
    the docs may name it; the product reads the installation's setting."""

    LABS = re.compile(r"\b08:30\b|\b09:10\b|\(\s*\(\s*8\s*,\s*30\s*\)|BACKUP_WINDOW|"
                      r"in_backup_window")
    DIRS = ("modules", "routes", "templates")

    def _files(self, root):
        from tests import source_index
        return source_index.tracked("app.py", *self.DIRS, suffix=(".py", ".html", ".js"),
                                    root=root)

    def _hits(self, root):
        hits = []
        for path in self._files(root):
            with open(path, encoding="utf-8", errors="replace") as fh:
                hits += [f"{os.path.relpath(path, root)}:{i}" for i, line in enumerate(fh, 1)
                         if self.LABS.search(line)]
        return hits

    def test_the_population_is_the_product(self):
        assert len(self._files(ROOT)) > 300, "floor: the product's files were scanned"

    def test_none_names_it(self):
        assert self._hits(ROOT) == []

    def test_a_planted_one_is_found(self, tmp_path):
        from tests import source_index
        (tmp_path / "modules").mkdir()
        (tmp_path / "modules" / "planted.py").write_text(
            "WINDOW = ((8, 30), (9, 10))\nSAID = 'no run in 08:30 to 09:10 UTC'\n"
            "CLEAN = '18:30'\n", encoding="utf-8")
        source_index.track_all(tmp_path)
        assert self._hits(str(tmp_path)) == ["modules/planted.py:1", "modules/planted.py:2"]
