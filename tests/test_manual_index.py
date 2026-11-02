"""The manual's section index (modules/ai/manual_index.py; card P7, the toolbar assistant, stage 1:
grounding is a section index chosen by code, board P7's approved answer of 2026-11-01). Over the
real manual (docs/manual, every declared page):

- every section's link resolves to a section the Help page renders (the anchors are the
  page's own), and every declared page with words gives at least one;
- a question is answered from its own page first (Reload, Set value…, Re-key), the screen the
  person is on scores its page higher, a question sharing no telling word is ``[]`` (a manual
  gap), and the limit and the budget hold;
- the same question gives the same sections every time (no model chooses).
"""
import pytest

from modules import manual
from modules.ai import manual_index as M


def test_every_section_s_link_is_one_the_help_page_renders():
    secs = M.sections()
    assert len(secs) >= 400, f"the floor: {len(secs)} sections"
    rendered = {}
    for s in secs:
        if s["slug"] not in rendered:
            rendered[s["slug"]] = manual.load(s["slug"])["sections"]
        if s["anchor"]:
            assert s["anchor"] in rendered[s["slug"]], (s["slug"], s["anchor"])
            assert s["link"] == f"/v2/help/{s['slug']}#{s['anchor']}"
        else:
            assert s["link"] == f"/v2/help/{s['slug']}"
    pages = {slug for slug, *_rest in manual.PAGES}
    assert {s["slug"] for s in secs} >= pages - {"third-party"}, \
        pages - {s["slug"] for s in secs}


@pytest.mark.parametrize("question, slug", [
    ("how do I reload a device", "reload"),
    ("how do I set a value for a secret reference", "set-secret-value"),
    ("what does re-key do and why is my SSH key refused", "rekey"),
])
def test_a_question_is_answered_from_its_own_page_first(question, slug):
    got = M.select(question)
    assert got and got[0]["slug"] == slug, [(s["slug"], s["anchor"]) for s in got]


@pytest.mark.parametrize("screen", ["Needs attention", "needs-attention"])
def test_the_screen_the_person_is_on_scores_its_page_higher(screen):
    """By the screen's name (`manual.SCREENS`) or its page's slug, the one boost."""
    q = "what does this row mean and how does it clear"
    key = lambda p: (p["slug"], p["anchor"], p["part"])  # noqa: E731
    plain = {key(p): p["score"] for p in M.ranked(q)["passages"]}
    on = {key(p): p["score"] for p in M.ranked(q, screen=screen)["passages"]}
    mine = [k for k in on if k[0] == "needs-attention"]
    assert mine and all(on[k] == pytest.approx(plain[k] + M.SCREEN_BOOST) for k in mine)
    assert all(on[k] == plain[k] for k in on if k[0] != "needs-attention")


def test_a_question_the_manual_does_not_cover_is_a_gap():
    assert M.select("zebra giraffe") == []
    assert M.select("how do it") == [], "no telling word at all"


def test_the_limit_and_the_budget_hold():
    q = "how do I reload a device and what happens while it is down"
    got = M.select(q, limit=3, budget=10**7)
    assert len(got) == 3
    small = M.select(q, limit=20, budget=3000)
    assert small and sum(len(s["text"]) for s in small) <= 3000
    whole = M.select(q)
    assert len(whole) <= M.LIMIT and sum(len(s["text"]) for s in whole) <= M.BUDGET_CHARS


def test_a_long_section_is_split_into_passages_that_keep_its_link():
    """5 to 8 passages fit the budget (about 5,000 tokens): no passage is longer than
    PASSAGE_CHARS but one paragraph that is, and each keeps its section's link."""
    secs = {(s["slug"], s["anchor"]): s for s in M.sections()}
    long_ = [k for k, s in secs.items() if len(s["text"]) > M.PASSAGE_CHARS]
    assert long_, "the floor: the manual has sections longer than a passage"
    import re
    for p in M.passages():
        assert len(p["text"]) <= M.PASSAGE_CHARS or "\n" not in p["text"], (p["link"],
                                                                            len(p["text"]))
        assert p["link"] == secs[(p["slug"], p["anchor"])]["link"]
    for k in long_:
        parts = [p for p in M.passages() if (p["slug"], p["anchor"]) == k]
        flat = lambda t: re.sub(r"\s+", " ", t).strip()  # noqa: E731
        assert len(parts) > 1, k
        assert flat(" ".join(p["text"] for p in parts)) == flat(secs[k]["text"]), k


def test_an_alias_reaches_the_manual_s_word():
    """A person's word the manual says otherwise (reboot, the manual's reload) is found through
    `ALIASES`; without the alias it is not."""
    assert M.select("how do I reboot a router safely")[0]["slug"] == "reload"
    assert ("reload", {"reboot"}) in M.asked("how do I reboot it")


def test_weaker_passages_never_pad_the_answer():
    """On the recorded questions whose best LIMIT passages hold one under PAD_SHARE of the
    best (a floor: the two measured 2026-11-02), none of those is sent."""
    import json
    with open("tests/fixtures/ai_cases/assistant/retrieval.json", encoding="utf-8") as fh:
        cases = [c for c in json.load(fh)["cases"] if c["expect"]]
    weak = 0
    for c in cases:
        ranked = M.ranked(c["q"], c["screen"])["passages"][:M.LIMIT]
        low = [p for p in ranked if p["score"] < ranked[0]["score"] * M.PAD_SHARE]
        if not low:
            continue
        weak += 1
        sent = M.select(c["q"], c["screen"], budget=10**9)
        key = lambda p: (p["slug"], p["anchor"], p["part"])  # noqa: E731
        assert not {key(p) for p in low} & {key(p) for p in sent}, c["n"]
    assert weak >= 2, f"the floor: {weak} questions with a weaker passage in reach"


def test_recall_at_5_on_the_recorded_cases_and_every_uncovered_one_a_gap():
    """Retrieval measured alone (the operator, 2026-11-02): recall@5 on the recorded cases
    (tests/fixtures/ai_cases/assistant/retrieval.json), 22 of 24 when measured; and each question
    the manual does not cover answered with no passage. A floor that only rises."""
    import json
    with open("tests/fixtures/ai_cases/assistant/retrieval.json", encoding="utf-8") as fh:
        cases = json.load(fh)["cases"]
    got = M.evaluate(cases, k=5)
    assert (got["covered"], got["uncovered"]) == (24, 4)
    assert got["found"] >= 22, got["misses"]
    assert got["gapped"] == got["uncovered"], got["misses"]


def test_the_same_question_gives_the_same_sections():
    q = "how do I deploy a change to a device"
    assert M.select(q) == M.select(q)


def test_its_size_is_measured():
    got = M.size()
    assert got["pages"] >= 60 and got["sections"] >= 400 and got["chars"] > 500_000
