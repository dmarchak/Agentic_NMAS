"""`NMAS_REQUIRE_BROWSER=1` (C2412, C1169): where a browser is required (CI's browser shards and
the gate's), a browser that cannot start FAILS the test asking, at `tests/browser.available`, so
every one of its callers' skips (both shapes, about 72 files) becomes a failure in one place;
elsewhere it still answers `(False, why)` and the caller skips (#1295: 80 skipped and green)."""
import pytest
from _pytest.outcomes import Failed

from tests import browser

WHY = "Firefox could not start in this runner: Process unexpectedly closed with status 1"


def test_required_and_no_browser_fails_naming_why(monkeypatch):
    monkeypatch.setenv("NMAS_REQUIRE_BROWSER", "1")
    monkeypatch.setattr(browser, "_probe", lambda: (False, WHY))
    with pytest.raises(Failed) as got:
        browser.available()
    assert str(got.value) == f"NMAS_REQUIRE_BROWSER=1 and no real browser starts here: {WHY}"


@pytest.mark.parametrize("value", [None, "", "0"])
def test_not_required_it_answers_and_the_caller_skips(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("NMAS_REQUIRE_BROWSER", raising=False)
    else:
        monkeypatch.setenv("NMAS_REQUIRE_BROWSER", value)
    monkeypatch.setattr(browser, "_probe", lambda: (False, WHY))
    assert browser.available() == (False, WHY)


def test_required_with_a_browser_answers_as_before(monkeypatch):
    monkeypatch.setenv("NMAS_REQUIRE_BROWSER", "1")
    monkeypatch.setattr(browser, "_probe", lambda: (True, ""))
    assert browser.available() == (True, "")
