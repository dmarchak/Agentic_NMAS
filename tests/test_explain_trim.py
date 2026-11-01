"""Every Explain version's pack trimmed to the task's bound (C2198; the operator's decision of
2026-10-29: trim per version). v9's 3-run screen (2026-10-29) had recorded case 6 refused
"prompt_too_long" on all three runs, since only v6's `budgeted` fitted a pack to the bound and
every other version sent the pack whole. `explain.trimmed` drops the pack's pieces in
`PACK_DROPS`' order until the version's own request fits; each section that lost some says so
in the pack as sent; the answer keeps what was left out and the card draws it.

On test_evidence_pack_neighbours.py's world (`near`): r1's pack with its neighbour r3's
change and reload lines and History, built by the real trigger over the Loki capture. The
bound is lowered to make the real request too long, as a larger pack would be under the real
bound: the request's size is measured, never assumed.
"""
import json

import pytest

from modules import evidence_pack as EP
from modules.ai import explain, gateway, profiles, prompts
from tests.test_ai_explain import world  # noqa: F401 (the fixture)
from tests.test_device_v2 import lab  # noqa: F401 (the fixture)
from tests.test_evidence_pack import pack_lab  # noqa: F401 (the fixture)
from tests.test_evidence_pack_context import _pack_sent, ctx  # noqa: F401
from tests.test_evidence_pack_neighbours import _neighbour_pack, near  # noqa: F401


def _request(pack, prompt=("explain", 4)):
    """The version's own request parts, as `_prepare_pack` builds them before the trim."""
    topo = explain.topology(pack)
    return (pack, prompt, explain.SCHEMA_OF[prompt[1]], explain.parts(pack, topo),
            explain.context(topo), explain.sent_sections(pack, topo))


def _whole(pack, prompt=("explain", 4)):
    _p, _v, schema, data, ctx_, _s = _request(pack, prompt)
    body = gateway.build_request(prompts.load(*prompt), schema, data,
                                 profiles.TASKS[explain.FEATURE], ctx_)
    return gateway.prompt_tokens(body)


def _bound(monkeypatch, tokens):
    monkeypatch.setitem(profiles.TASKS, explain.FEATURE,
                        dict(profiles.TASKS[explain.FEATURE], max_prompt_tokens=tokens))


class TestTheTrim:
    def test_a_pack_that_fits_is_sent_as_built(self, near):
        pack = _neighbour_pack(near)
        args = _request(pack)
        got = explain.trimmed(*args)
        assert got["data"] is args[3] and got["sections"] == args[5]
        assert got["said"]["pack_dropped"] == {} and got["said"]["dropped"] == []

    @pytest.mark.parametrize("version", [4, 9])
    def test_over_the_bound_the_pack_is_trimmed_until_it_fits(self, near, monkeypatch,
                                                              version):
        pack = _neighbour_pack(near)
        whole = _whole(pack, ("explain", version))
        _bound(monkeypatch, whole - 300)
        got = explain.trimmed(*_request(pack, ("explain", version)))
        said = got["said"]
        assert said["estimate"] <= said["budget"] == whole - 300, said
        assert said["pack_dropped"], said
        # The lowest priority first: the neighbours' pieces before any of the device's own.
        if set(said["pack_dropped"]) - {"neighbour_events"}:
            assert said["pack_dropped"]["neighbour_events"] == 4, said
        assert said["dropped"][0] == explain.PACK_DROPS[0]
        # The marker, in the pack as sent.
        sent = json.loads(got["data"]["pack"])
        trimmed = {s["name"]: s["omitted_for_size"] for s in sent if s.get("omitted_for_size")}
        assert set(trimmed) == set(said["pack_dropped"])
        n = said["pack_dropped"]["neighbour_events"]
        assert trimmed["neighbour_events"].startswith(f"{n} of its ")
        assert "left out to fit the prompt's size (not the same as not read)" in \
            trimmed["neighbour_events"]

    def test_the_fact_sheet_cites_nothing_that_was_left_out(self, near, monkeypatch):
        """The 2026-11-01 round's case 1: a sheet computed before the trim named a health
        figure the trim dropped, the model cited it from the sheet, and every answer was
        refused. The sheet is computed again from the pack as trimmed, with the same
        topology."""
        import re
        from modules.ai import fact_sheet
        pack = _neighbour_pack(near)
        args = _request(pack)
        topo = explain.topology(pack)
        _bound(monkeypatch, 10)                       # every droppable piece goes
        got = explain.trimmed(*args, topo=topo)
        sheet = got["data"][fact_sheet.PART]
        sent = {p["ref"] for s in got["sections"] for p in s.get("pieces") or []}
        gone = {p["ref"] for s in args[5] for p in s.get("pieces") or []} - sent
        assert gone, "the floor: something was left out"
        cited = set(re.findall(r"[a-z_]+:[A-Za-z0-9_:.\-]*[A-Za-z0-9_]", sheet))
        assert not cited & gone, sorted(cited & gone)
        assert sheet == explain.facts(pack, got["sections"], topo)
        assert sheet != args[3][fact_sheet.PART], "the sheet before the trim cited them"

    def test_other_alerts_are_left_out_last_farthest_from_the_onset_first(self, near):
        """The 2026-11-01 round's case 6 stayed over the bound with every other droppable piece
        gone: the other alerts around the onset (10,246 characters there) are the last class,
        the farthest from the onset first. On the neighbours world's pack, its own sections,
        with three other alerts beside them (the pack holds none)."""
        pack = _neighbour_pack(near)
        conc = {"name": "concurrent", "pieces": [
            {"ref": f"concurrent:{i}", "started_at": at, "rule": "Interface down"}
            for i, at in ((1, "2026-10-15T08:14:00Z"), (2, "2026-10-15T08:01:00Z"),
                          (3, "2026-10-15T08:16:30Z"))]}
        sections = [s for s in _request(pack)[5] if s["name"] != "concurrent"] + [conc]
        order = explain._pack_drop_order(pack, sections)
        classes = [c for c, _n, _r in order]
        assert classes == sorted(classes) and classes[-1] == 4, "each class after the last"
        assert [r for c, n, r in order if n == "concurrent"] == [
            "concurrent:2", "concurrent:3", "concurrent:1"], "farthest from 08:15:00 first"
        assert explain.PACK_DROPS[4].startswith("other alerts in the network")

    def test_nothing_left_to_drop_is_sent_whole_trimmed_and_refused_by_the_gateway(
            self, near, monkeypatch):
        """The floor: the alert, device and Intent sections are never dropped, so a bound
        below them leaves the request over it, and the gateway refuses it as before."""
        pack = _neighbour_pack(near)
        _bound(monkeypatch, 10)
        got = explain.trimmed(*_request(pack))
        assert got["said"]["estimate"] > 10
        order = explain._pack_drop_order(pack, _request(pack)[5])
        assert sum(got["said"]["pack_dropped"].values()) == len(order)


class TestThroughExplain:
    def _press(self, near, pack):
        from modules.ai import triggers
        from tests.ai_person import pressed_by
        from tests.test_ai_explain import _answer
        assert EP.record(pack)["ok"]
        near.answer = _answer(pack)
        with pressed_by("operator@example.com"):
            return explain.explain(pack["id"], actor="operator@example.com",
                                   trigger=triggers.person("operator@example.com"),
                                   send=near.send, today="2026-10-25")

    def test_a_pack_over_the_bound_is_asked_trimmed_never_refused(self, near, monkeypatch):
        """A press counts its request with the provider (here the suite's typical count,
        conftest's `_a_typical_provider_token_count`), so the bound is set under that count."""
        from modules.ai import anthropic_adapter as A
        pack = _neighbour_pack(near)
        _p, prompt, schema, data, ctx_, _s = _request(pack)
        body = gateway.build_request(prompts.load(*prompt), schema, data,
                                     profiles.TASKS[explain.FEATURE], ctx_)
        _bound(monkeypatch, A.count_tokens(body, "").tokens - 300)
        got = self._press(near, pack)
        assert got["ok"] is True, got
        assert got["trimmed"]["pack_dropped"], got
        sent = near.sent[-1]["bytes"]
        assert "left out to fit the prompt's size" in sent
        (nb,) = [s for s in _pack_sent(near) if s["name"] == "neighbour_events"]
        assert nb["omitted_for_size"]

    def test_the_card_says_what_was_left_out(self, near, monkeypatch):
        """Through the pack's real route: the answer drawn with the trim's words, and the same
        when the kept answer is drawn again on reopening (no new call)."""
        from html import unescape

        from modules.ai import anthropic_adapter as A
        from tests.test_ai_explain import _answer
        pack = _neighbour_pack(near)
        _p, prompt, schema, data, ctx_, _s = _request(pack)
        body = gateway.build_request(prompts.load(*prompt), schema, data,
                                     profiles.TASKS[explain.FEATURE], ctx_)
        _bound(monkeypatch, A.count_tokens(body, "").tokens - 300)
        assert EP.record(pack)["ok"]
        near.answer = _answer(pack)
        c = near.lab["client"]
        for again in ({}, {}):
            r = c.post(f"/v2/monitoring/alerts/pack/{pack['id']}/explain", data=again,
                       headers={"HX-Request": "true"})
            html = unescape(r.get_data(as_text=True))
            assert r.status_code == 200 and "Trimmed to fit the prompt's size: " in html, html
            assert "from neighbour_events" in html and "(not the same as not read)" in html
        assert len(near.sent) == 1, "the second press drew the kept answer"

    def test_a_pack_that_fits_carries_no_trim(self, near):
        got = self._press(near, _neighbour_pack(near))
        assert got["ok"] is True and "trimmed" not in got, got
        assert "left out to fit" not in near.sent[-1]["bytes"]
