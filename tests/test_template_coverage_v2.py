"""Templates › Coverage on v2 (CUTOVER's "Template coverage", the board drawn 2026-10-10 under
the Phase 7 mode), on test_capture's lab: r2's REAL configuration committed as its golden, the
shipped templates seeded. Nothing is replaced but the job's thread wait.

- the measurement renders each committed golden through the device's own template and
  compares: r2 counted with its fidelity and coverage, at the commit it measured;
- a manifest entry whose golden no commit holds is "could not be checked", by name, never
  dropped from the counts;
- the tab with no measurement says so and offers Check coverage now; the check runs as a job,
  keeps its answer masked and dated, and the card then draws the counts, what to model next and
  the devices grouped; a commit after the measurement is said ("the repository has moved");
- an unreadable kept answer is its own state, not "never measured";
- a network that does not exist is refused, nothing measured.
"""

import json
import os
import re
import subprocess

from modules.nsot import capture_job, template_coverage
from tests.test_device_capture_v2 import lab  # noqa: F401 (the fixture)


def _head(repo):
    return subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"], capture_output=True,
                          text=True).stdout.strip()


def test_the_measurement_counts_r2_at_its_commit(lab):  # noqa: F811
    got = template_coverage.measure("Lab")
    assert got["commit"] == _head(lab["repo"]) and got["total"] == 1
    (d,) = [d for g in got["groups"] for d in g["devices"]]
    assert d["host"] == "r2" and d["outcome"] in ("reproduced", "partly")
    assert isinstance(d["fidelity"], (int, float)) and isinstance(d["coverage"], (int, float))
    assert d["template"], "the template it rendered through is named"
    assert got["measured_at"].endswith("Z")


def test_a_golden_no_commit_holds_is_counted_as_unchecked(lab, monkeypatch):  # noqa: F811
    from modules.nsot import manifest as _m
    real = _m.load

    def with_ghost(repo):
        doc = real(repo)
        doc["devices"]["uid:ghost"] = {"name": "r9", "golden": "golden/r9.cfg",
                                       "platform": "cisco_iosxe"}
        return doc
    monkeypatch.setattr(_m, "load", with_ghost)
    got = template_coverage.measure("Lab")
    assert got["total"] == 2 and got["counts"]["unreadable"] == 1
    (ghost,) = [d for g in got["groups"] if g["key"] == "unreadable" for d in g["devices"]]
    assert ghost["host"] == "r9" and ghost["why"]


def test_the_tab_check_and_card(lab):  # noqa: F811
    c = lab["client"]
    html = c.get("/v2/templates/coverage?list=Lab").get_data(as_text=True)
    assert 'aria-current="page">Coverage</a>' in html
    assert "Not measured for Lab yet" in html and "Check coverage now" in html
    started = c.post("/v2/templates/coverage", data={"list": "Lab"}).get_data(as_text=True)
    job = re.search(r"/v2/templates/coverage/card\?[^\"]*job=([0-9a-f]+)", started).group(1)
    assert 'aria-busy="true"' in started and "nmas:templates from:body" in started
    assert capture_job.wait(job, 60)
    card = c.get(f"/v2/templates/coverage/card?list=Lab&job={job}").get_data(as_text=True)
    said = re.search(r"Measured .*?</p>", card, re.S)
    assert said, card[:600]
    assert "for test-person@example.invalid" in said.group(0), said.group(0)
    assert _head(lab["repo"])[:12] in card and "has moved since" not in card
    assert re.search(r'<details class="sc-grp" data-keep="cov-(reproduced|partly)"', card)
    assert ">r2</a>" in card
    kept = json.load(open(os.path.join(os.path.dirname(lab["repo"]),
                                       "template_coverage.json"), encoding="utf-8"))
    assert kept["commit"] == _head(lab["repo"]) and kept["asked_by"] == \
        "test-person@example.invalid"
    # A commit after the measurement dates it.
    subprocess.run(["git", "-C", lab["repo"], "commit", "--allow-empty", "-qm", "later"],
                   check=True, env=dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
                                        GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t"))
    card = c.get("/v2/templates/coverage/card?list=Lab").get_data(as_text=True)
    assert "The repository has moved since" in card


def test_an_unreadable_kept_answer_is_its_own_state(lab):  # noqa: F811
    path = os.path.join(os.path.dirname(lab["repo"]), "template_coverage.json")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("{not json")
    html = lab["client"].get("/v2/templates/coverage/card?list=Lab").get_data(as_text=True)
    assert "The last measurement is unreadable" in html and "Not measured" not in html


def test_an_unknown_network_measures_nothing(lab, monkeypatch):  # noqa: F811
    monkeypatch.setattr(template_coverage, "start", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("measured")))
    r = lab["client"].post("/v2/templates/coverage", data={"list": "Nope"})
    assert r.status_code == 404 and "nothing was measured" in r.get_data(as_text=True)
