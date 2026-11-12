"""A host step a person declines with a reason (the operator, 2026-11-11).

"The seven host-step rows have no action, against our own rule. Add a recorded way to close one
("declined, with reason" or "done, verified") ... My intent: decline the local-CI-runner steps
("CI stays on GitHub-hosted runners")."

On the two real commits whose AFTER steps the host owes (8bd25396's runner install, its
`[updater]` step checked done, and 8c059523's five, each trailer cut to its first clause):

- Decline this step… on the Update page posts the step and a typed reason; the decline is kept
  beside the done rows in the same store (who, how established, when, the reason masked at
  rest), the step leaves Still to do and its Needs attention row, and the panel draws it under
  Host steps declined: "Declined by <name> at <time>: <reason>. It is no longer owed; History
  keeps it.";
- History draws it, and a person's "It is done" too;
- refused, nothing recorded: no reason (or one without the shape of one); a step already
  declined or said done (naming who and when); an unverified request;
- a step with a check can be declined, and its done stays the check's;
- the row's words name both ways and its one action is the Update page, drawn on its line.
"""

import json

import pytest

RUNNER = "8bd2539600efd045393cefa00c6da6fcc8e19961"
SLICE = "8c05952345c88717c6ae213aa6c2dc2c23bf58fa"
INSTALL = "install the local CI runner when the operator chooses, by docs/LOCAL_CI.md section 11"
STEPS = ("install the slice and the units, rendered fresh and installed by name",
         "reinstall the root-owned runner from the host's checkout at this commit",
         "rebuild the job image and pin the new ID",
         "remove what the scheduled runs left",
         "keep 487ed333's false red, marked and set aside, never deleted")
REASON = "CI stays on GitHub-hosted runners"
PERSON = "p@example.invalid"
#: PERSON as a screen names them (board E2a): by display name, the part before the "@".
SHOWN = PERSON.split("@")[0]


def _log(*commits):
    return "".join(f"{sha}\x1f{body}\x1e" for sha, body in commits)


TEXT = _log((SLICE, "Local CI after its first host run\n\n"
             + "".join(f"Host-Step-After: {s}\n" for s in STEPS)),
            (RUNNER, "Local CI, workstream 0\n\nHost-Step-After: [updater] re-install the "
                     f"updater's copy of scripts/nmas-deploy\nHost-Step-After: {INSTALL}\n"))


@pytest.fixture
def host(tmp_path, monkeypatch):
    """The running release SLICE, its history the two commits, the updater's check done, and
    the done store in this test's folder."""
    from modules import host_steps, identity
    from routes import health
    monkeypatch.setattr(host_steps, "DONE", str(tmp_path / "done.jsonl"))
    monkeypatch.setattr(host_steps, "_log", lambda root, rng, limit, run=None: TEXT)
    monkeypatch.setattr(health, "_COMMIT", SLICE)
    monkeypatch.setattr(identity, "request_actor", lambda: PERSON)
    monkeypatch.setitem(host_steps.CHECKS, "updater",
                        lambda root: {"state": "done", "detail": "the copy matches"})
    return tmp_path


def _client():
    from app import app
    app.config["TESTING"] = True
    return app.test_client()


def _decline(sha, step, why=REASON):
    return _client().post("/update/host-step/decline", data={"sha": sha, "step": step, "why": why})


def _rows(path):
    return [json.loads(x) for x in path.read_text().splitlines()] if path.exists() else []


class TestDecliningAStep:
    def test_the_six_owed_steps_are_the_two_commits_unchecked_ones(self, host):
        from modules import host_steps
        got = host_steps.owed(SLICE)
        assert [s["step"] for s in got["steps"]] == [INSTALL, *STEPS]
        assert all(s["check_state"] == "not_checkable" for s in got["steps"])

    def test_through_the_route_it_is_recorded_and_no_longer_owed(self, host):
        from modules import attention, host_steps
        r = _decline(RUNNER, INSTALL)
        html = r.get_data(as_text=True)
        assert r.status_code == 200, html
        card = html.split('id="update-declined"')[1].split("</section>")[0]
        assert f"{INSTALL} <span class=\"muted\">· Declined by {SHOWN} at <time" in card
        assert f": {REASON}. It is no longer owed; History keeps it." in card
        (row,) = _rows(host / "done.jsonl")
        assert (row["sha"], row["step"], row["by"], row["decision"], row["why"]) == (
            RUNNER, INSTALL, PERSON, "declined", REASON)
        assert row["verified"] and row["at"]
        got = host_steps.owed(SLICE)
        assert INSTALL not in [s["step"] for s in got["steps"]]
        assert [d["step"] for d in got["declined"]] == [INSTALL]
        assert got["said_done"] == [], "a decline is never saying it is done"
        rows = attention.host_steps_source()["rows"]
        assert INSTALL not in " ".join(x["what"] for x in rows) and len(rows) == 5

    def test_declining_all_six_leaves_none_owed(self, host):
        from modules import attention, host_steps
        for s in host_steps.owed(SLICE)["steps"]:
            assert _decline(s["sha"], s["step"]).status_code == 200
        assert host_steps.owed(SLICE)["steps"] == []
        assert attention.host_steps_source()["rows"] == []
        assert len(host_steps.owed(SLICE)["declined"]) == 6

    def test_the_reason_is_masked_at_rest(self, host):
        # A configuration line pasted as the reason, masked as every typed reason is
        # (`redact_text`, as an acknowledgement's).
        _decline(SLICE, STEPS[0], why="password Secr3tPassw0rd is what the runner kept")
        (row,) = _rows(host / "done.jsonl")
        assert "Secr3tPassw0rd" not in json.dumps(row) and "<redacted" in row["why"]

    def test_one_row_for_several_commits_is_declined_for_each(self, host, monkeypatch):
        from modules import host_steps
        body = "x\n\nHost-Step-After: tell the team\n"
        monkeypatch.setattr(host_steps, "_log", lambda root, rng, limit, run=None:
                            _log(("b" * 40, body), ("a" * 40, body)))
        assert _decline("a" * 40, "tell the team").status_code == 200
        assert [r["sha"] for r in _rows(host / "done.jsonl")] == ["a" * 40, "b" * 40]
        (d,) = host_steps.owed("b" * 40)["declined"]
        assert d["shas"] == ["a" * 40, "b" * 40]

    def test_a_checked_step_can_be_declined_and_done_stays_the_check_s(self, host, monkeypatch):
        from modules import host_steps
        monkeypatch.setitem(host_steps.CHECKS, "updater",
                            lambda root: {"state": "not_done", "detail": "the copy differs"})
        step = "re-install the updater's copy of scripts/nmas-deploy"
        assert _decline(RUNNER, step).status_code == 200
        assert [d["step"] for d in host_steps.owed(SLICE)["declined"]] == [step]
        monkeypatch.setitem(host_steps.CHECKS, "updater",
                            lambda root: {"state": "done", "detail": "the copy matches"})
        got = host_steps.owed(SLICE)
        assert [c["step"] for c in got["checked_done"]] == [step] and got["declined"] == []


class TestRefusals:
    @pytest.mark.parametrize("why", ["", "   ", "ok", "fine ok"])
    def test_a_decline_with_no_reason_is_refused_and_nothing_recorded(self, host, why):
        from modules import host_steps
        r = _decline(RUNNER, INSTALL, why=why)
        html = r.get_data(as_text=True)
        assert r.status_code == 409 and 'id="update-step-refused"' in html
        assert f'Not declined ("{INSTALL}"): a decline needs a reason' in html
        assert _rows(host / "done.jsonl") == []
        assert INSTALL in [s["step"] for s in host_steps.owed(SLICE)["steps"]]

    def test_a_step_already_declined_names_who_when_and_why(self, host):
        assert _decline(RUNNER, INSTALL).status_code == 200
        r = _decline(RUNNER, INSTALL, why="a second reason for the same step")
        html = r.get_data(as_text=True)
        assert r.status_code == 409
        assert f"that step was already declined by {SHOWN} at 20" in html
        assert f"UTC: {REASON}" in html
        assert len(_rows(host / "done.jsonl")) == 1

    def test_a_step_already_said_done_names_who_and_when(self, host):
        assert _client().post("/update/host-step/done",
                              data={"sha": SLICE, "step": STEPS[3]}).status_code == 200
        r = _decline(SLICE, STEPS[3])
        assert r.status_code == 409
        assert f"that step was already said done by {SHOWN} at 20" in r.get_data(as_text=True)
        assert len(_rows(host / "done.jsonl")) == 1

    def test_a_step_not_owed_is_refused(self, host):
        r = _decline(SLICE, "invented")
        assert r.status_code == 409
        assert "not one the running release owes" in r.get_data(as_text=True)

    def test_an_unverified_request_is_refused_and_nothing_recorded(self, host, monkeypatch):
        from modules import identity
        monkeypatch.setattr(identity, "request_actor", lambda: identity.UNVERIFIED)
        r = _decline(RUNNER, INSTALL)
        assert r.status_code == 409 and "no verified person" in r.get_data(as_text=True)
        assert _rows(host / "done.jsonl") == []

    def test_record_decline_itself_refuses_no_person_and_no_reason(self, host):
        from modules import host_steps
        assert not host_steps.record_decline(RUNNER, INSTALL, "", REASON)["ok"]
        assert not host_steps.record_decline(RUNNER, INSTALL, PERSON, "")["ok"]
        assert _rows(host / "done.jsonl") == []


class TestHistoryKeepsIt:
    def test_a_decline_and_a_done_are_history_rows(self, host):
        from modules import history_sources as HS
        assert _decline(RUNNER, INSTALL).status_code == 200
        assert _client().post("/update/host-step/done",
                              data={"sha": SLICE, "step": STEPS[3]}).status_code == 200
        got = HS.host_steps({"device": "", "limit": 50, "since": None, "until": None})
        assert got["errors"] == []
        by = {e["what"]: e for e in got["events"]}
        dec = by[f"Host step declined: {INSTALL}"]
        assert dec["kind"] == "host_step" and dec["devices"] == []
        assert dec["detail"].startswith(f"{REASON}; asked for by {RUNNER[:10]}")
        assert dec["who"].startswith(PERSON)
        assert ("Reason", REASON) in dec["record"]
        assert f"Host step said done: {STEPS[3]}" in by
        assert HS.host_steps({"device": "r1", "limit": 50, "since": None,
                              "until": None})["events"] == [], "the installation's, no device's"

    def test_an_unreadable_record_is_said(self, host):
        from modules import history_sources as HS
        (host / "done.jsonl").write_text("{not json\n")
        got = HS.host_steps({"device": "", "limit": 50, "since": None, "until": None})
        assert got["events"] == [] and "could not be read" in got["errors"][0]


class TestTheRow:
    def test_its_words_name_both_ways_and_its_one_action_is_the_update_page(self, host):
        from modules import attention
        r = attention.host_steps_source()["rows"][0]
        assert r["clears"]["when"] == (
            "its check finds it done, or a person says it is done, or declines it with a "
            "reason, on the Update page (History keeps either)")
        assert r["action"]["open"] == "app_update"
        assert r["action"]["label"] == ("Open the Update page: say it is done, or decline it "
                                        "with a reason")

    def test_each_row_s_line_opens_the_update_page_where_its_step_is_declined(
            self, host, monkeypatch):
        """Pressed: each row's line link is followed, and the step it names is declined from
        the form that page draws for it."""
        import html as H
        import re

        from modules import attention, host_steps
        monkeypatch.setattr(attention, "SOURCES", [attention.host_steps_source])
        page = _client().get("/v2/attention").get_data(as_text=True)
        # The line is the row's summary: its primary, never What to do's link below it.
        lines = [x.split("</summary>")[0] for x in page.split('<span class="att-primary">')[1:]]
        links = [(re.search(r'href="([^"]+)">Open the Update page</a>', x) or [None, None])[1]
                 for x in lines]
        assert links == ["/v2/update"] * 6
        update = _client().get(links[0]).get_data(as_text=True)
        form = update.split('class="update-step-decline-form"')[1].split("</form>")[0]
        sha, step = (H.unescape(re.search(rf'name="{n}" value="([^"]*)"', form).group(1))
                     for n in ("sha", "step"))
        assert _decline(sha, step).status_code == 200
        assert [d["step"] for d in host_steps.owed(SLICE)["declined"]] == [step]

    def test_each_owed_step_s_drawn_form_declines_that_step(self, host):
        """Pressed: every Decline the step the page draws posts its own step's fields, and
        each declines exactly that step."""
        import html as H
        import re

        from modules import host_steps
        page = _client().get("/v2/update").get_data(as_text=True)
        owed = page.split('id="update-owed-steps"')[1].split("</ul>")[0]
        forms = owed.split('class="update-step-decline-form"')[1:]
        assert len(forms) == 6 and all("Decline the step" in f for f in forms)
        for f in forms:
            sha, step = (H.unescape(re.search(rf'name="{n}" value="([^"]*)"', f).group(1))
                         for n in ("sha", "step"))
            assert _decline(sha, step).status_code == 200, step
        assert host_steps.owed(SLICE)["steps"] == []
        assert sorted(d["step"] for d in host_steps.owed(SLICE)["declined"]) == sorted(
            [INSTALL, *STEPS])
