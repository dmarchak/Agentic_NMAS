"""AI troubleshooting's mode and its per-incident cap (modules/fixit/policy.py; the fix-it plan's
S2; the operator's order of 2026-11-12, overnight item 6: "a per-incident cap of $1.00" and
"Settings › Background processes, AI mode Manual by default"). No AI call, nothing drawn.

**The cap refuses** (the operator's test 2, at its core): spent in the incident plus the next
attempt's worst case, against the cap: just under it and at it allowed, past it refused with
the four numbers named; a cap that is not a positive amount (a stored null, zero, text) is
refused as a value, never read as "no cap"; a cost that cannot be read or is partial refuses,
never compared as if it were known. **On real records:** spent is summed from the record of AI
calls by its own writer (`calls.record`) and the incident's record by its own (`incident.
record_proposal`), as tests/test_fixit_incident.py makes them; the settings are written by the
one write path (`write_settings`).
"""
import json

import pytest

from modules.fixit import incident as F
from modules.fixit import policy as P
from tests.test_fixit_incident import CALL_A, CALL_B, a_call, inc
from tests.test_heal_resubscribe import lab  # noqa: F401 (the fixture)
from tests.test_sdn_connections import networks  # noqa: F401 (the fixture `lab` builds on)


def spent(usd_a, usd_b=None, incident=None):
    """The incident's calls: one (or two) recorded calls its AI proposals name."""
    a_call(CALL_A, usd_a)
    ids = [CALL_A]
    if usd_b is not None:
        a_call(CALL_B, usd_b)
        ids.append(CALL_B)
    F.record_proposal(incident or inc(), "ai", calls=ids)


def setting(**values):
    from modules.settings_schema import write_settings
    got = write_settings(values, actor="op@example.invalid")
    assert got["ok"], got
    return got


def stored(raw: dict):
    """A hand-edited settings file: *raw* written past the write path."""
    from modules import config
    with open(config.USER_SETTINGS_FILE, "w", encoding="utf-8") as fh:
        json.dump(raw, fh)


# ── The settings ────────────────────────────────────────────────────────────────────────────

class TestTheSettings:
    def test_both_are_declared_with_their_defaults_and_the_installations(self):
        from modules import settings_scope as S
        from modules.settings_schema import DEFAULTS, SEEDS_BY_VERSION
        assert DEFAULTS["ai_troubleshoot_mode"] == "manual" == P.DEFAULT_MODE
        assert DEFAULTS["ai_cap_usd_per_incident"] == 1.00 == P.DEFAULT_CAP_USD
        assert S.scope_of("ai_troubleshoot_mode") == S.scope_of("ai_cap_usd_per_incident") == (
            S.HOST, "ai_troubleshoot")
        # Read through the default, never seeded into a file.
        assert all(v == "*" or not ({"ai_troubleshoot_mode", "ai_cap_usd_per_incident"}
                                    & set(v)) for v in SEEDS_BY_VERSION.values())

    def test_never_set_reads_manual_and_one_dollar(self, lab):  # noqa: F811
        assert P.mode() == {"state": "ok", "mode": "manual", "error": ""}
        assert P.cap_usd() == {"state": "ok", "usd": 1.0, "error": ""}
        assert P.ai_refusal() == ""

    @pytest.mark.parametrize("value", ["manual", "off"])
    def test_each_mode_is_written_and_read(self, lab, value):  # noqa: F811
        setting(ai_troubleshoot_mode=value)
        assert P.mode()["mode"] == value

    @pytest.mark.parametrize("value", ["automatic", "auto", "", None, True, "Manual"])
    def test_any_other_mode_is_refused_by_the_write_path(self, lab, value):  # noqa: F811
        from modules.settings_schema import write_settings
        got = write_settings({"ai_troubleshoot_mode": value}, actor="op@example.invalid")
        assert got["ok"] is False and "ai_troubleshoot_mode" in got["error"]
        assert P.mode()["mode"] == "manual"

    @pytest.mark.parametrize("value", [None, 0, -1.0, "1.00", True])
    def test_a_cap_that_is_no_positive_amount_is_refused_by_the_write_path(self, lab,  # noqa
                                                                           value):
        from modules.settings_schema import write_settings
        got = write_settings({"ai_cap_usd_per_incident": value}, actor="op@example.invalid")
        assert got["ok"] is False and "ai_cap_usd_per_incident" in got["error"]
        assert P.cap_usd()["usd"] == 1.0

    def test_off_says_why_no_ai_troubleshoot_is_offered(self, lab):  # noqa: F811
        setting(ai_troubleshoot_mode="off")
        assert P.ai_refusal() == ("AI troubleshooting is off for this installation (its mode is "
                                  "Off): Mercury's own diagnosis still proposes a fix")

    @pytest.mark.parametrize("raw", ["automatic", 7, None])
    def test_a_hand_edited_mode_is_unreadable_never_either(self, lab, raw):  # noqa: F811
        stored({"ai_troubleshoot_mode": raw})
        got = P.mode()
        assert (got["state"], got["mode"]) == ("unreadable", "")
        assert got["error"] == (f"the AI troubleshooting mode holds {raw!r}, and the modes are "
                                "Manual and Off")
        assert P.ai_refusal() == f"AI troubleshooting is not offered: {got['error']}"

    def test_an_unreadable_settings_file_allows_nothing(self, lab):  # noqa: F811
        from modules import config
        with open(config.USER_SETTINGS_FILE, "w", encoding="utf-8") as fh:
            fh.write('{"ai_troubleshoot_mode": "man')
        assert P.mode()["state"] == P.cap_usd()["state"] == "unreadable"
        assert P.ai_refusal().startswith("AI troubleshooting is not offered: the AI "
                                         "troubleshooting mode cannot be read (")
        assert P.cap_refusal(inc(), 0.25).startswith(
            "Retry isn't available: the per-incident AI cap cannot be read (")


# ── The cap refuses ─────────────────────────────────────────────────────────────────────────

class TestTheCapRefuses:
    def test_just_under_the_cap_it_allows(self, lab):  # noqa: F811
        spent(0.40, 0.34)
        got = P.cap_state(inc(), 0.25)
        assert got == {"state": "allowed", "spent": pytest.approx(0.74), "worst": 0.25,
                       "total": pytest.approx(0.99), "cap": 1.0, "words": ""}
        assert P.cap_refusal(inc(), 0.25) == ""

    def test_at_the_cap_exactly_it_allows(self, lab):  # noqa: F811
        """A cap is reached, not passed: $0.10 spent and $0.20 worst make the cap of $0.30,
        which floating point alone reads as 0.30000000000000004, past it."""
        spent(0.10)
        setting(ai_cap_usd_per_incident=0.30)
        assert 0.10 + 0.20 > 0.30
        got = P.cap_state(inc(), 0.20)
        assert (got["state"], got["total"], got["cap"]) == ("allowed", 0.3, 0.3)
        assert P.cap_state(inc(), 0.2001)["state"] == "refused"

    def test_spent_and_worst_past_the_cap_refuse_naming_all_four(self, lab):  # noqa: F811
        spent(0.92)
        got = P.cap_state(inc(), 0.25)
        assert (got["state"], got["spent"], got["worst"], got["cap"]) == (
            "refused", pytest.approx(0.92), 0.25, 1.0)
        assert got["total"] == pytest.approx(1.17)
        assert got["words"] == (
            "Retry isn't available: this incident's AI spend would pass its cap. Spent $0.92 "
            "in this incident; the next attempt costs at most $0.25, which would make $1.17 "
            "against the cap of $1.00. Mercury never raises the cap")
        assert P.cap_refusal(inc(), 0.25) == got["words"]

    def test_the_worst_case_alone_past_the_cap_refuses_with_nothing_spent(self, lab):  # noqa
        assert P.cap_refusal(inc(), 1.01).startswith(
            "Retry isn't available: this incident's AI spend would pass its cap. Spent $0.00 "
            "in this incident; the next attempt costs at most $1.01, which would make $1.01 "
            "against the cap of $1.00.")

    def test_only_this_incidents_calls_count(self, lab):  # noqa: F811
        spent(0.90, incident=inc("hi-0000000000ee"))
        assert P.cap_refusal(inc(), 0.25) == ""
        assert P.cap_refusal(inc("hi-0000000000ee"), 0.25) != ""

    def test_a_cap_an_admin_set_is_the_one_compared(self, lab):  # noqa: F811
        spent(0.92)
        setting(ai_cap_usd_per_incident=2.5)
        assert P.cap_refusal(inc(), 0.25) == ""
        setting(ai_cap_usd_per_incident=0.5)
        assert P.cap_refusal(inc(), 0.25).endswith(
            "which would make $1.17 against the cap of $0.50. Mercury never raises the cap")

    @pytest.mark.parametrize("raw", [None, 0, -1, "1.00", True, float("inf")])
    def test_a_stored_cap_that_is_no_positive_amount_refuses_never_no_cap(self, lab,  # noqa
                                                                          raw):
        if raw == float("inf"):
            from modules import config
            with open(config.USER_SETTINGS_FILE, "w", encoding="utf-8") as fh:
                fh.write('{"ai_cap_usd_per_incident": Infinity}')
        else:
            stored({"ai_cap_usd_per_incident": raw})
        got = P.cap_state(inc(), 0.01)
        assert (got["state"], got["cap"]) == ("refused", None)
        assert got["words"] == (
            f"Retry isn't available: the per-incident AI cap holds {raw!r}, and it is a "
            "positive amount of US dollars: this cap has no \"no cap\", so the next attempt's "
            "worst case of $0.01 cannot be compared with it")

    @pytest.mark.parametrize("worst", [0, -0.25, None, "0.25", True, float("nan")])
    def test_a_worst_case_that_is_no_positive_amount_refuses(self, lab, worst):  # noqa: F811
        got = P.cap_state(inc(), worst)
        assert got["state"] == "refused" and got["worst"] is None
        assert got["words"].startswith(
            f"Retry isn't available: the next attempt's worst case was given as {worst!r}")

    def test_an_unreadable_record_of_calls_refuses_never_reads_as_nothing_spent(self, lab):  # noqa
        import os

        from modules.ai import calls
        F.record_proposal(inc(), "ai", calls=[CALL_A])
        os.makedirs(calls._path())          # a folder where the file should be: unreadable
        got = P.cap_state(inc(), 0.01)
        assert (got["state"], got["spent"], got["cap"]) == ("refused", None, 1.0)
        assert got["words"].startswith("Retry isn't available: what this incident's AI calls "
                                       "cost is not known (the record of AI calls could not "
                                       "be read (IsADirectoryError: ")
        assert got["words"].endswith("so spent plus the next attempt's worst case of $0.01 "
                                     "cannot be compared with the cap of $1.00")

    def test_a_call_the_record_does_not_hold_refuses(self, lab):  # noqa: F811
        a_call(CALL_A, 0.05)
        F.record_proposal(inc(), "ai", calls=[CALL_A, CALL_B])
        got = P.cap_state(inc(), 0.01)
        assert got["state"] == "refused" and got["spent"] is None
        assert f"holds no row for 1 of the 2 call(s) {inc().id} names ({CALL_B})" in \
            got["words"]

    def test_the_cap_reads_and_writes_nothing_but_what_it_names(self, lab, monkeypatch):  # noqa
        """A read: the settings, the incident's record, the record of AI calls."""
        from tests.test_fixit_incident import tree
        from modules import config
        spent(0.92)
        before = tree(config.DATA_DIR)
        for worst in (0.01, 0.25):
            P.cap_refusal(inc(), worst)
        assert tree(config.DATA_DIR) == before
