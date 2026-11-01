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


def test_the_screen_the_person_is_on_scores_its_page_higher():
    q = "what does this row mean and how does it clear"
    plain = {(s["slug"], s["anchor"]): s["score"] for s in M.select(q, limit=10**4, budget=10**9)}
    on = {(s["slug"], s["anchor"]): s["score"]
          for s in M.select(q, screen="Needs attention", limit=10**4, budget=10**9)}
    mine = [k for k in on if k[0] == "needs-attention"]
    assert mine and all(on[k] == pytest.approx(plain[k] + M.SCREEN_BOOST) for k in mine)
    assert all(on[k] == plain[k] for k in on if k[0] != "needs-attention")


def test_a_question_the_manual_does_not_cover_is_a_gap():
    assert M.select("zebra giraffe") == []
    assert M.select("how do it") == [], "no telling word at all"


def test_the_limit_and_the_budget_hold():
    got = M.select("device", limit=3, budget=10**7)
    assert len(got) == 3
    small = M.select("device", limit=20, budget=3000)
    assert sum(len(s["text"]) for s in small) <= 3000


def test_the_same_question_gives_the_same_sections():
    q = "how do I deploy a change to a device"
    assert M.select(q) == M.select(q)


def test_its_size_is_measured():
    got = M.size()
    assert got["pages"] >= 60 and got["sections"] >= 400 and got["chars"] > 500_000
