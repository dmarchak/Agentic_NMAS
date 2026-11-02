"""Board FC phase 2 (c), PHASE8_PLAN 22.2: a layer's change planned from Source of Truth › Intent
(routes/intent_layers_v2.py `change`, `change_plan`, `change_job` over
`fleet_change.plan_start`), on r2's real config and committed intent through the deploy's own
plan, r2's inventory row tagged.

- **FC2's controls:** Edit… on each value, Add a value… and Add a layer… open the form; Edit…
  prefills what the layer holds there, before and after.
- **Plan the change:** the card answers at once, planning, and re-reads on `fleet_change`; the
  job's card is the plan, counts first, r2's one line, nothing written (the repository's HEAD
  unmoved).
- **A before the layer does not hold** is refused by name; **a form with no setting** is refused.
- **An unknown job** says the server has no record of it.
"""

import subprocess

import pytest

from tests.test_fleet_change_plan import r2, _head, lab  # noqa: F401 (the fixtures)


def _commit_layer(repo, name, text):
    import os
    os.makedirs(os.path.join(repo, "layers"), exist_ok=True)
    with open(os.path.join(repo, "layers", name), "w", encoding="utf-8") as fh:
        fh.write(text)
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid")
    for args in (("add", "--", f"layers/{name}"), ("commit", "-q", "-m", f"layer {name}")):
        subprocess.run(["git", "-C", repo, *args], check=True, env=env, capture_output=True)


@pytest.fixture
def page(r2, lab, monkeypatch):  # noqa: F811
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
    return lab["client"]


def _plan(client, layer, path, before, after):
    return client.post("/v2/intent/change/plan", data={
        "list": "Lab", "layer": layer, "path": path, "before": before, "after": after})


class TestFC2sControls:
    def test_edit_add_a_value_and_add_a_layer_open_the_form(self, page, r2):  # noqa: F811
        _commit_layer(r2["repo"], "tag-blind-lab.yml", "domain_name: corp.example\n")
        html = page.get("/v2/intent?list=Lab&layer=tag-blind-lab").get_data(as_text=True)
        assert 'href="/v2/intent/change?list=Lab&amp;layer=tag-blind-lab&amp;path=domain_name"' \
            in html and ">Edit…</a>" in html
        assert ">Add a value…</a>" in html and ">Add a layer…</a>" in html

    def test_edit_prefills_what_the_layer_holds(self, page, r2):  # noqa: F811
        _commit_layer(r2["repo"], "tag-blind-lab.yml", "domain_name: corp.example\n")
        r = page.get("/v2/intent/change?list=Lab&layer=tag-blind-lab&path=domain_name")
        html = r.get_data(as_text=True)
        assert r.status_code == 200 and 'id="fc-plan"' in html
        assert 'name="before" type="text" class="mono" value="corp.example"' in html
        assert 'name="layer" value="tag-blind-lab"' in html

    def test_add_a_layer_asks_its_rank_and_slug(self, page):
        html = page.get("/v2/intent/change?list=Lab").get_data(as_text=True)
        assert 'name="rank"' in html and 'name="slug"' in html and 'name="layer"' not in html


class TestPlanTheChange:
    def test_the_card_plans_as_a_job_and_draws_the_plan_writing_nothing(self, page, r2):  # noqa: F811
        from modules import csp
        from modules.nsot import capture_job
        head = _head(r2["repo"])
        r = _plan(page, "tag-blind-lab", "ntp_servers", "(absent)", "[192.0.2.123]")
        html = r.get_data(as_text=True)
        assert r.status_code == 200 and r.headers.get("Content-Security-Policy") == csp.STRICT_POLICY
        assert 'hx-trigger="nmas:fleet_change from:body"' in html and "Planning" in html
        job = html.split("/v2/intent/change/job/", 1)[1].split("?", 1)[0]
        assert capture_job.wait(job, 30)
        html = page.get(f"/v2/intent/change/job/{job}?list=Lab&layer=tag-blind-lab") \
            .get_data(as_text=True)
        assert "<strong>1 device, 1 group</strong> · 0 refused · 0 unchanged" in html, html
        assert "+ ntp server 192.0.2.123" in html and "layers/tag-blind-lab.yml" in html
        assert "Nothing was sent and nothing was written" in html
        assert _head(r2["repo"]) == head, "a plan commits nothing"

    def test_a_before_the_layer_does_not_hold_is_refused_by_name(self, page, r2):  # noqa: F811
        from modules.nsot import capture_job
        html = _plan(page, "tag-blind-lab", "ntp_servers", "[192.0.2.1]", "[192.0.2.123]") \
            .get_data(as_text=True)
        job = html.split("/v2/intent/change/job/", 1)[1].split("?", 1)[0]
        assert capture_job.wait(job, 30)
        html = page.get(f"/v2/intent/change/job/{job}?list=Lab&layer=tag-blind-lab") \
            .get_data(as_text=True)
        assert "data-fc-error" in html and "ntp_servers holds nothing" in html, html

    def test_a_form_with_no_setting_is_refused(self, page):
        r = _plan(page, "tag-blind-lab", "", "", "")
        assert r.status_code == 400 and "the change has no setting" in r.get_data(as_text=True)

    def test_an_unknown_job_says_so(self, page):
        html = page.get("/v2/intent/change/job/nosuchjob?list=Lab&layer=tag-blind-lab") \
            .get_data(as_text=True)
        assert "This server has no record of that plan" in html
