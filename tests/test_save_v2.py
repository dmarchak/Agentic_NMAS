"""Devices › Save (C593; 7.4's boards A and C, approved 2026-10-04): the ticked devices, or
every device of the network, saved to startup and recorded as golden together.

On test_capture's lab: r2's REAL configuration as its committed golden, in a real
repository. The device side is replaced at the two seams the operation is built from: the ONE
save of a startup config (`onboard.persist_on_device`, whose own tests drive its session) and
the running config's read (`routes.golden._read_running`). Everything else is real: the plan,
the hash, the holds, the job registry, `save_golden`, the routes and the templates.

- the plan reads stored records only (the inventory, the hourly startup check, reachability,
  the holds), groups each device with why, and binds a hash a moved device breaks;
- the page draws what is measured (accounts in startup) and never claims "startup differs";
- the confirm runs a job that holds each device while it saves, records each persist row as
  the person (`via: save`), and commits the persisted devices' goldens once, `Source: save`;
- a read-back that did not match is saved and NOT recorded; a device the manifest does not
  know is left out before anything is sent, and never spoils the batch;
- a moved plan, a write with no list, and an unknown job are refused or said;
- the Devices page draws the selection bar with Save in its Actions, and the Startup column
  in words that say what the check compares.
"""

import json
import os
import re
import subprocess
import threading

import pytest

from tests.test_capture import build_capture_lab
from tests.test_intent_match import _broken

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PW = "Save-Pw-4k8r2m"


@pytest.fixture
def lab(tmp_path, monkeypatch):
    from modules import device

    cap = build_capture_lab(monkeypatch, tmp_path)
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr("modules.config.DATA_DIR", str(data))
    pw = device.fernet.encrypt(PW.encode()).decode()
    rows = [{"hostname": "r2", "ip": "203.0.113.12", "device_type": "cisco_xe",
             "platform": "cisco_iosxe", "username": "nmas", "password": pw},
            # Answering, and not in the manifest: never onboarded.
            {"hostname": "r3", "ip": "192.0.2.13", "device_type": "cisco_xe",
             "platform": "cisco_iosxe", "username": "nmas", "password": pw},
            # Not answering at the last reachability read.
            {"hostname": "r4", "ip": "192.0.2.14", "device_type": "cisco_xe",
             "platform": "cisco_iosxe", "username": "nmas", "password": pw},
            # No driver recorded.
            {"hostname": "s9", "ip": "192.0.2.19", "device_type": "",
             "platform": "cisco_ios", "username": "nmas", "password": pw}]
    monkeypatch.setattr("modules.nsot.restore._devices_of", lambda ln: [dict(r) for r in rows])
    monkeypatch.setattr("modules.device.load_saved_devices", lambda *a, **k: [dict(r) for r in rows])
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: str(name) == "Lab")
    _store("reachability", {"devices": {
        "203.0.113.12": {"hostname": "r2", "list": "Lab", "answering": True},
        "192.0.2.13": {"hostname": "r3", "list": "Lab", "answering": True},
        "192.0.2.14": {"hostname": "r4", "list": "Lab", "answering": False}}})
    sent, records = [], []
    answers = {}

    def persist(ip, username, password, secret, device_type):
        from modules.nsot import device_ops

        sent.append({"ip": ip, "held": device_ops.may_write(ip), "password_ok": password == PW})
        # As the real one does between its save and its read (C605; held to it below).
        device_ops.note("read_back")
        return dict(answers.get(ip) or {"ok": True, "state": "persisted",
                                        "detail": "the startup config carries every username "
                                                  "line the running config holds (1)"})

    monkeypatch.setattr("modules.nsot.onboard.persist_on_device", persist)
    monkeypatch.setattr("modules.nsot.onboard._record_native_persist",
                        lambda host, out, actor, via, **_k: records.append(
                            {"device": host, "state": out.get("state"), "actor": actor,
                             "via": via}))
    return dict(cap, rows=rows, sent=sent, records=records, answers=answers, data=str(data))


def _store(name, value):
    from modules import reader_job

    path = reader_job.store_path(name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"last_good": {"value": value, "value_at": "2026-10-08T10:00:00Z"}}, fh)


def _startup_check(lab, devices):
    import time

    with open(os.path.join(lab["data"], "startup_check.json"), "w") as fh:
        json.dump({"at": time.time() - 600, "devices": devices}, fh)


def _head(repo):
    return subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"], capture_output=True,
                          text=True).stdout.strip()


def _message(repo, ref="HEAD"):
    return subprocess.run(["git", "-C", repo, "log", "-1", "--format=%B", ref],
                          capture_output=True, text=True).stdout


def _tags(repo):
    return subprocess.run(["git", "-C", repo, "tag", "-l", "baseline/*"], capture_output=True,
                          text=True).stdout.split()


def _page(lab, *devices, **args):
    q = "&".join([f"device={d}" for d in devices] + [f"{k}={v}" for k, v in args.items()])
    r = lab["client"].get(f"/v2/devices/save?list=Lab&{q}")
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    return r.get_data(as_text=True)


def _form(html):
    form = html[html.index('class="save-ft"'):]
    form = form[:form.index("</form>")]
    return {"list": re.search(r'name="list" value="([^"]*)"', form).group(1),
            "hash": re.search(r'name="hash" value="([^"]*)"', form).group(1),
            "device": re.findall(r'name="device" value="([^"]*)"', form)}


def _run(lab, *devices, form=None):
    """Confirm the page's own form, wait for the job, and return its card."""
    from modules.nsot import capture_job

    body = form or _form(_page(lab, *devices))
    r = lab["client"].post("/v2/devices/save/confirm", data=body)
    html = r.get_data(as_text=True)
    if r.status_code != 200:
        return r.status_code, html
    job = re.search(r"/v2/devices/save/job/([0-9a-f]+)", html).group(1)
    assert capture_job.wait(job, 60), f"save {job} still running after 60 s"
    return 200, lab["client"].get(f"/v2/devices/save/job/{job}?list=Lab").get_data(as_text=True)


class TestThePlan:
    def test_each_device_is_grouped_with_why(self, lab):
        from modules.nsot import save_op

        p = save_op.plan("Lab", ["r2", "r3", "r4", "s9", "nope"])
        groups = {d["host"]: (d["group"], d["why"]) for d in p["devices"]}
        assert groups["r2"] == ("save", "") and groups["r3"] == ("save", "")
        assert groups["r4"] == ("not_answering", "not answering at the last reachability read")
        assert groups["s9"][0] == "refused" and "no device_type" in groups["s9"][1]
        assert groups["nope"] == ("refused", "nope is not in Lab's inventory")
        assert p["counts"] == {"save": 2, "not_answering": 1, "held": 0, "refused": 2}
        assert p["save"] == ["r2", "r3"] and p["fleet"] is False

    def test_it_asks_no_device(self, lab, monkeypatch):
        def _never(*a, **k):
            raise AssertionError("the plan opened a session")
        monkeypatch.setattr("modules.connection.open_ssh", _never)
        from modules.nsot import save_op
        save_op.plan("Lab", ["r2", "r3"])
        _page(lab, "r2", "r3")
        assert lab["sent"] == []

    def test_the_hash_binds_each_device_to_save(self, lab):
        """Persist's own device checks and hash (`persist_op.row_checks`), so the two
        operations cannot disagree about a device."""
        from modules.nsot import save_op

        before = save_op.plan("Lab", ["r2", "r3"])["hash"]
        assert save_op.plan("Lab", ["r3", "r2"])["hash"] == before, "the order is not the plan"
        lab["rows"][0]["ip"] = "192.0.2.12"
        assert save_op.plan("Lab", ["r2", "r3"])["hash"] != before
        lab["rows"][0]["ip"] = "203.0.113.12"
        # A device left out is not in the hash; one joining or leaving the save is.
        assert save_op.plan("Lab", ["r2", "r3", "s9"])["hash"] == before
        assert save_op.plan("Lab", ["r2"])["hash"] != before

    def test_a_held_device_is_left_out_naming_its_holder(self, lab):
        from modules.nsot import device_ops, save_op

        held, done = threading.Event(), threading.Event()

        def _other():
            with device_ops.hold("Lab", "r3", "deploy", "someone@example.com"):
                held.set()
                done.wait(10)

        worker = threading.Thread(target=_other)
        worker.start()
        try:
            assert held.wait(10)
            (r3,) = [d for d in save_op.plan("Lab", ["r3"])["devices"]]
        finally:
            done.set()
            worker.join(10)
        assert r3["group"] == "held" and "someone@example.com" in r3["why"]

    def test_the_whole_network_may_earn_a_baseline(self, lab):
        from modules.nsot import save_op

        lab["rows"][:] = lab["rows"][:2]
        assert save_op.plan("Lab", ["r2", "r3"])["fleet"] is True
        assert save_op.plan("Lab", ["r2"])["fleet"] is False




class TestThePage:
    def test_it_draws_what_is_measured_and_never_startup_differs(self, lab):
        _startup_check(lab, [{"list": "Lab", "device": "r2", "state": "not_persisted"},
                             {"list": "Lab", "device": "r3", "state": "persisted"}])
        html = _page(lab, "r2", "r3", "r4", "s9")
        assert "Save 4 devices: to startup, and as golden" in html
        assert "Before it runs" in html
        summary = html[html.index('class="save-sum"'):html.index("</div>\n", html.index('class="save-sum"'))]
        for words in ("2</strong>to save", "1</strong>not answering: left out",
                      "1</strong>cannot be saved from here: left out"):
            assert words in summary.replace("\n", ""), (words, summary)
        said = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html))
        assert "1 accounts not in startup; 1 accounts in startup." in said
        assert "whether the rest of startup differs is not measured" in said
        assert "startup differs" not in said.replace("the rest of startup differs", "")
        assert "Recording without saving is not offered here" in said

    def test_the_confirm_is_bound_and_busy_on_itself(self, lab):
        html = _page(lab, "r2", "r4")
        form = _form(html)
        assert form["list"] == "Lab" and form["device"] == ["r2", "r4"]
        from modules.nsot import save_op
        assert form["hash"] == save_op.plan("Lab", ["r2", "r4"])["hash"]
        foot = html[html.index('class="save-ft"'):]
        assert 'class="op-idle">Save 1 device<' in foot and 'class="op-busy">' in foot
        assert 'hx-disabled-elt="this"' in foot and 'data-op="save"' in foot
        assert 'aria-label="How does Save work?"' in foot
        assert "You are confirming as test-person@example.invalid." in foot
        assert f"Bound to plan {form['hash']}" in foot

    def test_nothing_to_save_offers_no_confirm(self, lab):
        html = _page(lab, "r4", "s9")
        assert "op-confirm" not in html
        assert "Nothing in the selection can be saved now" in html

    def test_every_device_and_none(self, lab):
        html = _page(lab, all=1)
        assert "Save 4 devices" in html and _form(html)["device"] == ["r2", "r3", "r4", "s9"]
        assert "No device chosen" in _page(lab)

    def test_an_unknown_network_is_said(self, lab):
        r = lab["client"].get("/v2/devices/save?list=Elsewhere&device=r2")
        assert r.status_code == 404 and "There is no device list named 'Elsewhere'" in \
            r.get_data(as_text=True)


def _repeats(html):
    """The plan's repeated-baseline notice in words, or None."""
    m = re.search(r'<div class="notice notice-warn save-repeats">(.*?)</div>', html, re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", m.group(1))).strip() if m else None


def _said(html):
    from html import unescape

    return unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))).replace(" .", ".").strip()


class TestTheNoGoldenScope:
    """C1232: today's toolbar's "Capture devices with no golden" (`/golden/capture/preview`,
    `scope: no_golden`) on v2, as a scope of Devices › Save: every device of the network with
    no committed golden, decided from git (the one enumerator, `repo.list_goldens`), never from
    files on disk. The plan names the devices it chose and each one it left out with why; with
    none to choose it says what it looked at and offers no confirm."""

    def test_only_the_devices_with_no_committed_golden_are_planned(self, lab):
        from modules.nsot import save_op

        html = _page(lab, scope="no_golden")
        assert 'class="save-ft"' in html, _said(html)[-300:]
        form = _form(html)
        assert form["device"] == ["r3", "r4", "s9"], form
        assert form["hash"] == save_op.plan("Lab", ["r3", "r4", "s9"])["hash"]
        said = _said(html)
        assert ("Only the devices of Lab with no committed golden: 3 of the 4 looked at in "
                "Lab's repository.") in said, said
        assert 'data-keep="save-scope-left"' in html, said
        left = html[html.index('data-keep="save-scope-left"'):]
        left = _said(left[left.index("<summary>"):left.index("</details>")])
        assert left.startswith("1 already has a committed golden: left out"), left
        assert "r2 its golden committed" in left, left

    def test_decided_from_git_never_from_the_file_on_disk(self, lab):
        """r2's golden file removed from the working tree is still committed: still left out."""
        from modules.nsot import manifest

        _ident, entry = manifest.find_by_name(lab["repo"], "r2")
        os.remove(os.path.join(lab["repo"], entry["golden"]))
        html = _page(lab, scope="no_golden")
        assert 'class="save-ft"' in html, _said(html)[-300:]
        assert _form(html)["device"] == ["r3", "r4", "s9"]

    def test_nothing_to_save_says_what_was_looked_at(self, lab):
        lab["rows"][:] = lab["rows"][:1]                     # r2, with its golden, is all
        html = _page(lab, scope="no_golden")
        said = _said(html)
        assert ("Every device of Lab has a committed golden (1 device looked at in Lab's "
                "repository): nothing to save, and no device was asked.") in said, said
        assert "op-confirm" not in html and 'class="save-ft"' not in html
        assert re.search(r'<a class="btn" href="/v2/devices(\?[^"]*)?">Back</a>', html), html

    def test_an_unknown_scope_is_refused_naming_the_one_there_is(self, lab):
        r = lab["client"].get("/v2/devices/save?list=Lab&scope=everything")
        said = _said(r.get_data(as_text=True))
        assert r.status_code == 400, r.status_code
        assert ("the scope 'everything' is not one Save knows; the one it knows is "
                "'no_golden' (the devices with no committed golden). Nothing was planned.") \
            in said, said

    def test_the_confirm_never_reaches_a_device_left_out(self, lab):
        """The scoped plan's own form confirmed: r2, left out for its golden, is never sent to
        and its golden never moves."""
        lab["rows"][:] = lab["rows"][:2]                     # r2 (golden) and r3 (none)
        html = _page(lab, scope="no_golden")
        assert 'class="save-ft"' in html, _said(html)[-300:]
        form = _form(html)
        assert form["device"] == ["r3"]
        before = _head(lab["repo"])
        status, html = _run(lab, form=form)
        assert status == 200 and lab["sent"] == [], lab["sent"]
        assert _head(lab["repo"]) == before

    def test_the_devices_page_offers_it(self, lab, monkeypatch):
        from modules.nsot import listref

        monkeypatch.setattr(listref, "active", lambda: listref.resolve("Lab"))
        html = lab["client"].get("/v2/devices").get_data(as_text=True)
        bar = html[html.index('id="dev-bar"'):html.index('class="table-wrap"')]
        assert 'href="/v2/devices/save?list=Lab&amp;scope=no_golden"' in bar, bar
        at = bar.index('href="/v2/devices/save?list=Lab&amp;scope=no_golden"')
        row = bar[bar.rindex('<div class="menu-row">', 0, at):]
        row = row[:row.index("</div>")]
        assert 'data-op="save"' in row and "Save the devices of Lab with no golden…" in row, row
        assert 'aria-label="How does Save work?"' in row, row


class TestTheRepeatedBaseline:
    """C860, C539 (2) on v2: a Save of the whole network just after a baseline says so first,
    with when, by whom and the tag. The plan reads no device, so it claims only what it
    measured: no golden has changed since, and every device to save had one at the baseline."""

    def test_a_baseline_just_taken_is_said_first_and_a_golden_since_ends_it(self, lab):
        lab["rows"][:] = lab["rows"][:1]                     # r2 is the whole network
        before = set(_tags(lab["repo"]))
        assert _repeats(_page(lab, all=1)) is None, "no baseline taken yet: nothing to repeat"
        status, _html = _run(lab, form=_form(_page(lab, all=1)))
        assert status == 200
        (tag,) = sorted(set(_tags(lab["repo"])) - before)
        html = _page(lab, all=1)
        said = _repeats(html)
        assert said == (f"A baseline was taken just now by test-person@example.invalid ({tag}), "
                        "and no golden has changed since. This plan reads no device, so whether "
                        "one has changed since is not known here; if none has, this Save "
                        "records the same state again."), said
        # First: before the card says what Save does, the groups, or the confirm.
        assert html.index("save-repeats") < html.index("Each device saves its running config")
        assert "op-confirm" in html, "the confirm is still offered"
        # A golden committed after the baseline (r2 off its intent, so no new baseline is
        # earned): the baseline is no longer the state.
        lab["running"]["r2"] = _broken(lab["captured"])
        head = _head(lab["repo"])
        assert _run(lab, "r2")[0] == 200
        assert _head(lab["repo"]) != head and sorted(set(_tags(lab["repo"])) - before) == [tag]
        assert _repeats(_page(lab, all=1)) is None, "a golden committed since the baseline"

    def test_said_only_for_the_whole_network_and_a_baseline_holding_each_device(self, lab):
        """The controls: a selection short of the network asks for no baseline, so it repeats
        none; a device with no golden at the baseline (r3, never onboarded) would be recorded
        new, so the Save would not repeat the baseline."""
        lab["rows"][:] = lab["rows"][:1]
        assert _run(lab, form=_form(_page(lab, all=1)))[0] == 200
        assert _repeats(_page(lab, all=1)), "the baseline just taken"
        lab["rows"][:] = [lab["rows"][0], {**lab["rows"][0], "hostname": "r3",
                                           "ip": "192.0.2.13"}]
        assert _repeats(_page(lab, "r2")) is None, "r2 alone is not the network"
        html = _page(lab, all=1)
        assert "Every device of Lab: the commit may earn a baseline." in html
        assert _repeats(html) is None, "r3 had no golden at the baseline"


class TestTheRun:
    def test_it_saves_holding_each_device_and_records_once_as_the_person(self, lab):
        lab["running"]["r2"] = _broken(lab["captured"])
        before = _head(lab["repo"])
        status, html = _run(lab, "r2")
        assert status == 200
        assert lab["sent"] == [{"ip": "203.0.113.12", "held": True, "password_ok": True}]
        assert lab["records"] == [{"device": "r2", "state": "persisted",
                                   "actor": "test-person@example.invalid", "via": "save"}]
        after = _head(lab["repo"])
        assert after != before
        msg = _message(lab["repo"])
        assert "Source: save" in msg and "Actor: test-person@example.invalid" in msg
        said = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html))
        assert "1 device: 1 saved and recorded" in said and "done" in said
        assert f"Commit {after[:12]}" in said and "Source: save" in said
        assert "Retry" not in said

    def test_a_golden_that_already_matched_commits_nothing(self, lab):
        before = _head(lab["repo"])
        status, html = _run(lab, "r2")
        assert status == 200 and _head(lab["repo"]) == before
        assert "saved; its golden already matched" in html
        assert "every golden already matched" in html

    def test_a_read_back_that_did_not_match_is_saved_and_not_recorded(self, lab):
        lab["running"]["r2"] = _broken(lab["captured"])
        lab["answers"]["203.0.113.12"] = {
            "ok": False, "state": "not_persisted",
            "detail": "the startup config does not carry username nmas secret 9 <value>"}
        before = _head(lab["repo"])
        status, html = _run(lab, "r2")
        assert status == 200 and _head(lab["repo"]) == before, "nothing recorded"
        assert lab["records"][0]["state"] == "not_persisted"
        said = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html))
        assert "1 device: 0 saved and recorded, 1 not" in said and "failed" in said
        assert "saved; the read-back did not match: not recorded" in said
        assert "does not carry username nmas" in said
        assert "Retry the 1 not saved" in said
        assert 'href="/v2/devices/save?list=Lab&amp;device=r2"' in html

    def test_a_device_the_manifest_does_not_know_never_spoils_the_batch(self, lab):
        """`save_golden` refuses a whole batch for one unknown device: Save leaves it out
        BEFORE anything is sent to it, and records the rest."""
        lab["running"]["r2"] = _broken(lab["captured"])
        before = _head(lab["repo"])
        status, html = _run(lab, "r2", "r3")
        assert status == 200
        assert [s["ip"] for s in lab["sent"]] == ["203.0.113.12"], "nothing sent to r3"
        assert _head(lab["repo"]) != before
        said = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html))
        assert "2 devices: 1 saved and recorded, 1 not" in said and "partial" in said
        assert "r3 is not in Lab&#39;s manifest" in html and "onboard or adopt it first" in said

    def test_a_moved_plan_is_refused_with_nothing_sent(self, lab):
        form = _form(_page(lab, "r2"))
        lab["rows"][0]["username"] = "someone-else"
        status, html = _run(lab, form=form)
        assert status == 409 and lab["sent"] == [] and lab["records"] == []
        assert "the selection&#39;s plan changed since you saw it" in html
        assert "Nothing was sent" in html and "Plan it again" in html

    def test_the_whole_network_saved_earns_a_baseline(self, lab):
        """The operator, 2026-10-09: "v2 save all devices needs to add a new baseline". The
        whole network saved together is Save All (`Source: save_all`), whose baseline the
        decision WANTS; with every device at its intent it is earned, even with nothing to
        commit (an in-sync network is the strongest evidence, `repo.save_golden`)."""
        lab["rows"][:] = lab["rows"][:1]                     # r2 is the whole network
        before = _tags(lab["repo"])
        status, html = _run(lab, form=_form(_page(lab, all=1)))
        assert status == 200
        new = sorted(set(_tags(lab["repo"])) - set(before))
        assert len(new) == 1, new
        msg = _message(lab["repo"], new[0])
        assert "Source: save_all" in msg and "Baseline: earned" in msg
        said = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html))
        assert f"baseline earned {new[0]}: every device of Lab was saved and recorded" in said
        assert "Source: save_all" in said and "No baseline" not in said

    def test_a_network_off_its_intent_is_saved_and_its_baseline_denied_saying_why(self, lab):
        lab["rows"][:] = lab["rows"][:1]
        lab["running"]["r2"] = _broken(lab["captured"])      # r2 departs from its intent
        before = _tags(lab["repo"])
        status, html = _run(lab, form=_form(_page(lab, all=1)))
        assert status == 200 and lab["records"][0]["state"] == "persisted"
        assert sorted(set(_tags(lab["repo"])) - set(before)) == [], "no baseline tag"
        said = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html))
        assert "1 device: 1 saved and recorded" in said
        assert re.search(r"No baseline: [^.]*r2", said), said[said.find("No baseline") - 50:][:300]

    def test_a_selection_asks_for_no_baseline(self, lab):
        lab["running"]["r2"] = _broken(lab["captured"])
        before = _tags(lab["repo"])
        status, html = _run(lab, "r2")
        assert status == 200 and _tags(lab["repo"]) == before
        assert "Source: save" in _message(lab["repo"]) and "Source: save_all" not in _message(lab["repo"])
        assert "baseline" not in re.sub(r"<[^>]+>", "", html).lower()

    def test_the_job_makes_the_plan_again_when_its_turn_comes(self, lab):
        """The confirm checks the hash, and the job checks it again when it runs: a device
        that moved in between (here, its account) is refused with nothing sent."""
        from modules.nsot import save_op

        confirmed = save_op.plan("Lab", ["r2"])["hash"]
        lab["rows"][0]["username"] = "someone-else"
        got = save_op.run("Lab", ["r2"], "test-person@example.invalid", confirmed)
        assert got["state"] == "refused" and lab["sent"] == [] and lab["records"] == []
        assert f"({confirmed} -> " in got["detail"] and "Nothing was sent" in got["detail"]

    def test_a_write_with_no_list_or_no_plan_is_refused(self, lab):
        c = lab["client"]
        r = c.post("/v2/devices/save/confirm", data={"device": "r2", "hash": "x"})
        assert r.status_code == 400 and "names no network this server knows" in r.get_data(as_text=True)
        r = c.post("/v2/devices/save/confirm", data={"list": "Lab", "device": "r2"})
        assert r.status_code == 400 and "no plan to be bound to" in r.get_data(as_text=True)
        assert lab["sent"] == []

    def test_an_unknown_job_is_said(self, lab):
        html = lab["client"].get("/v2/devices/save/job/0123abcd?list=Lab").get_data(as_text=True)
        assert "This server has no record of that Save" in html


class TestTheRunningCard:
    def _card(self, job, rows):
        """The running card for *rows* ``(host, state, trail)``, as the job keeps them."""
        import time

        from flask import render_template

        import app as A
        from modules import save_page
        from modules.nsot import save_op

        for host, state, trail in rows:
            save_op._mark(job, host, state, trail=trail)
        s = save_page.job_card("Lab", job, {"state": "running", "elapsed_s": 41,
                                            "started_at": time.time() - 41})
        with A.app.test_request_context():
            return s, render_template("v2/_save.html", s=s)

    def test_a_row_per_device_on_the_stepper_and_the_commit_its_own_row(self, lab):
        """Board C605 (approved 2026-10-09): a device through its turn waits for the commit
        and is never counted as running (the host's "9 running" was 8 and r1 waiting)."""
        import time

        t = time.time() - 30
        s, html = self._card("a" * 32, [
            ("r1", "through", [["save", t], ["read_back", t + 4], ["read_running", t + 10],
                               ["commit_wait", t + 22]]),
            ("s1", "running", [["save", t], ["read_back", t + 9]]),
            ("r6", "waiting", []),
            ("s9", "not_persisted", [["save", t], ["read_back", t + 5]])])
        assert s["counts"] == {"failed": 1, "running": 1, "waiting": 1, "through": 1}
        assert s["grouped"] is False, "under 25 devices, every row is drawn"
        r1 = next(r for r in s["rows"] if r["host"] == "r1")
        assert [(x["key"], x["state"]) for x in r1["steps"]] == [
            ("save", "done"), ("read_back", "done"), ("read_running", "done"),
            ("commit_wait", "running"), ("recorded", "waiting")]
        assert [x["took_s"] for x in r1["steps"][:3]] == [4, 6, 12]
        s9 = next(r for r in s["rows"] if r["host"] == "s9")
        assert [x["state"] for x in s9["steps"]][:2] == ["done", "failed"]
        assert 'hx-trigger="nmas:save from:body, nmas:device_progress from:body"' in html
        assert "Saving 4 devices" in html and "1 of 4 through their turn" in html
        assert "at most 6 at once" in html
        assert re.search(r'class="run-step run-step-running"[^>]*aria-current="step"', html)
        assert "waiting its turn: starts when one of the 6 running finishes" in html
        assert "waits for every device&#39;s turn, then one commit for the batch" in html
        assert 'name="q"' not in html, "no search under 25 devices"

    def test_from_25_devices_the_rows_group_with_a_search(self, lab):
        import time

        t = time.time() - 5
        rows = [(f"d{i:02}", "waiting", []) for i in range(24)] + [("s9", "running",
                                                                   [["save", t]])]
        s, html = self._card("b" * 32, rows)
        assert s["grouped"] is True and 'name="q"' in html
        assert 'data-keep="save-run-running" open' in html
        assert 'data-keep="save-run-waiting">' in html, "waiting collapsed"

    def test_a_real_run_keeps_each_device_s_steps_in_order(self, lab):
        """The run notes each step as it begins, on the device's hold (save, then the
        read-back persist notes, then the running read), keeps the trail when it lets go, and
        adds the wait for the commit and the record."""
        from modules.nsot import capture_job, save_op

        lab["running"]["r2"] = _broken(lab["captured"])
        r = lab["client"].post("/v2/devices/save/confirm", data=_form(_page(lab, "r2")))
        job = re.search(r"/v2/devices/save/job/([0-9a-f]+)", r.get_data(as_text=True)).group(1)
        assert capture_job.wait(job, 60)
        row = save_op.live(job)["r2"]
        assert row["state"] == "saved_recorded"
        names = [n for n, _at in row["trail"]]
        assert names == ["save", "read_back", "read_running", "commit_wait", "recorded"], names
        ats = [a for _n, a in row["trail"]]
        assert ats == sorted(ats)

    def test_persist_notes_its_read_back_between_the_save_and_the_read(self):
        """The real `persist_on_device`, its session faked: the hold's trail has `read_back`
        after the save was sent and before `show startup-config`."""
        from modules.nsot import device_ops, onboard

        seen = []

        class Conn:
            def enable(self):
                pass

            def save_config(self):
                seen.append("save_config")

            def send_command(self, cmd, read_timeout=None):
                trail = [n for n, _a in (device_ops.holder("Lab", "r9") or {})
                         .get("progress", {}).get("trail", [])]
                seen.append((cmd, "read_back" in trail))
                return "username admin secret 9 x\n" if "startup" in cmd or "username" in cmd \
                    else ""

            def disconnect(self):
                pass

        with device_ops.hold("Lab", "r9", "save", "t@example.com", ip="192.0.2.99"):
            onboard.persist_on_device("192.0.2.99", "admin", "pw", "", "cisco_xe",
                                      connect=lambda **k: Conn())
        assert seen[0] == "save_config"
        assert seen[1] == ("show startup-config", True), seen

    def test_the_job_announces_what_its_announcer_declares(self, lab):
        from modules import invalidation
        from modules.nsot import capture_job

        status, _html = _run(lab, "r2")
        assert status == 200
        jobs = [j for j in capture_job._jobs.values() if j.get("kind") == "save"]
        assert jobs and all(j["keys"] == invalidation.ANNOUNCERS["save"] for j in jobs)


class TestTheDevicesPage:
    def test_the_bar_offers_save_for_the_ticked_and_for_every_device(self, lab, monkeypatch):
        from modules.nsot import listref

        monkeypatch.setattr(listref, "active", lambda: listref.resolve("Lab"))
        html = lab["client"].get("/v2/devices").get_data(as_text=True)
        bar = html[html.index('id="dev-bar"'):html.index('class="table-wrap"')]
        assert 'x-data="deviceSelect"' in html
        assert 'formaction="/v2/devices/save?list=Lab"' in bar and 'data-op="save"' in bar
        assert 'x-bind:disabled="nonePicked"' in bar
        assert 'href="/v2/devices/save?list=Lab&amp;all=1"' in bar
        assert "Save every device of Lab (4)" in bar
        # The deploy is on v2 since 2026-10-10 (board B): the bar's form opens it.
        assert "Plan a deploy for the ticked devices…" in bar and "today" not in bar
        assert 'action="/v2/devices/deploy?list=Lab"' in html

    def test_the_startup_column_says_what_the_check_compares(self, lab, monkeypatch):
        from modules.nsot import listref

        monkeypatch.setattr(listref, "active", lambda: listref.resolve("Lab"))
        _startup_check(lab, [{"list": "Lab", "device": "r2", "state": "not_persisted",
                              "detail": "the startup config does not carry username nmas"},
                             {"list": "Lab", "device": "r3", "state": "persisted"}])
        html = lab["client"].get("/v2/devices").get_data(as_text=True)
        cells = dict(re.findall(r'<a href="/v2/device/(\w+)\?list=Lab">.*?data-label="Startup:">(.*?)</td>',
                                html, re.S))
        assert "accounts not saved" in cells["r2"] and "does not carry username nmas" in cells["r2"]
        assert "accounts saved" in cells["r3"] and "it compares accounts only" in cells["r3"]
        assert "not checked" in cells["r4"]
        with open(os.path.join(lab["data"], "startup_check.json"), "w") as fh:
            fh.write("{ not json")
        html = lab["client"].get("/v2/devices").get_data(as_text=True)
        assert "the startup check&#39;s record could not be read" in html or \
            "the startup check's record could not be read" in html


class TestTheSelectionWords:
    @pytest.mark.parametrize("names, words", [
        (["r2", "r3"], ("2 selected", "· r2, r3", "(2)")),
        ([f"s{i}" for i in range(10)], ("10 selected", "· s0, s1, s2, s3, s4, s5, s6, s7 and 2 more",
                                         "(10)")),
    ])
    def test_as_the_browser_computes_them(self, names, words):
        import dukpy
        src = open(os.path.join(ROOT, "static", "js", "nmas_apply.js"), encoding="utf-8").read()
        got = dukpy.evaljs("var window = {};\n" + src + "\nwindow.NMAS_APPLY.deviceWords("
                           f"{json.dumps(names)})")
        assert (got["summary"], got["detail"], got["count"]) == words


# ------------------------------------------------ clicking what ships, where Firefox runs

@pytest.fixture(scope="module")
def live_browser():
    from tests import browser
    ok, why = browser.available()
    if not ok:
        pytest.skip(f"no real browser here ({why}); the tests above still run")
    import app as A
    with browser.Served(A.app) as srv, browser.Browser() as b:
        yield browser, srv, b


@pytest.fixture
def served(lab, live_browser, monkeypatch):
    from modules.nsot import listref

    monkeypatch.setattr(listref, "active", lambda: listref.resolve("Lab"))
    browser, srv, b = live_browser
    yield {"b": b, "srv": srv, "lab": lab}
    try:
        b.go("about:blank")
    finally:
        browser.close_socketio_sessions()


CARD = "document.getElementById('save-op')"
SETTLED = "!document.querySelector('.htmx-swapping, .htmx-settling, .htmx-request')"


class TestInARealBrowser:
    def test_tick_actions_save_confirm_and_the_result_by_announcement(self, served):
        """The path a person takes: tick a device, Actions, Save (1)…, the plan, the confirm;
        the result arrives in place when the job announces `save` (the relay, never a
        timer)."""
        b, lab = served["b"], served["lab"]
        lab["running"]["r2"] = _broken(lab["captured"])
        before = _head(lab["repo"])
        b._call("POST", f"/session/{b.session}/window/rect", {"width": 1280, "height": 1000})
        b.go(served["srv"].url("/v2/devices"))
        b.wait_for("return !!window.Alpine && " + SETTLED, 15)
        assert b.js("return document.querySelector('#dev-bar strong').textContent") == "0 selected"
        assert b.js("return document.querySelector('#dev-bar button[data-op=save]').disabled")
        b.click("#dev-r2")
        b.wait_for("return document.querySelector('#dev-bar strong').textContent === '1 selected'", 5)
        b.click('#dev-bar button[aria-haspopup="menu"]')
        b.wait_for("var m=document.querySelector('#dev-bar [role=menu]'); return m && m.offsetParent", 5)
        assert "Save (1)" in b.js("return document.querySelector('#dev-bar button[data-op=save]')"
                                  ".textContent")
        b.click("#dev-bar button[data-op=save]")
        b.wait_for(f"return {CARD} && {CARD}.querySelector('.op-confirm') && {SETTLED}", 15)
        assert "/v2/devices/save" in b.js("return location.pathname")
        assert lab["sent"] == []
        b.js("window.__notReloaded = 1; return 1")
        b.click("#save-op .op-confirm")
        b.wait_for(f"return {CARD} && {CARD}.textContent.indexOf('1 saved and recorded') >= 0 "
                   f"&& {SETTLED}", 20)
        assert b.js("return window.__notReloaded") == 1
        assert len(lab["sent"]) == 1 and _head(lab["repo"]) != before
        assert "Source: save" in _message(lab["repo"])

    def test_the_running_card_draws_each_device_s_step_then_the_result(self, served,
                                                                       monkeypatch):
        """C605 in a real browser: the run held at r2's read-back, its row shows the step it
        is in and the commit waits; released, the result arrives by announcement."""
        import threading

        from modules.nsot import device_ops

        b, lab = served["b"], served["lab"]
        lab["running"]["r2"] = _broken(lab["captured"])
        reached, release = threading.Event(), threading.Event()

        def slow(ip, username, password, secret, device_type):
            device_ops.note("read_back")
            reached.set()
            release.wait(30)
            return {"ok": True, "state": "persisted", "detail": "carried"}
        monkeypatch.setattr("modules.nsot.onboard.persist_on_device", slow)
        b._call("POST", f"/session/{b.session}/window/rect", {"width": 1280, "height": 1000})
        try:
            b.go(served["srv"].url("/v2/devices/save?list=Lab&device=r2"))
            b.wait_for(f"return {CARD} && {CARD}.querySelector('.op-confirm') && {SETTLED}", 15)
            b.click("#save-op .op-confirm")
            assert reached.wait(20), "the run never reached r2's read-back"
            # The card redraws on the device's own step (device_progress), never a timer. It
            # may first show the step before (C751: under the full suite's load the card drawn
            # before the announcement arrived answered first), so wait for the step itself.
            got = b.wait_for(
                "var r=document.querySelector('.run-row-running[data-row=r2]');"
                "var c=r && r.querySelector('.run-step-running .run-words');"
                "var m=document.querySelector('.run-final');"
                "return c && m && c.textContent.trim().indexOf('Read back') === 0 && "
                "[c.textContent.trim(), m.textContent.replace(/\\s+/g,' ')]", 15)
            assert got[0].startswith("Read back"), got
            assert "waits for every device's turn" in got[1], got
            assert b.js("return !!document.querySelector('#save-op input[name=q]')") is False
        finally:
            release.set()
        b.wait_for(f"return {CARD} && {CARD}.textContent.indexOf('1 saved and recorded') >= 0", 20)

    @pytest.mark.parametrize("path", ["/v2/devices", "/v2/devices/save?list=Lab&device=r2&device=r4&device=s9"])
    def test_at_phone_width_nothing_runs_past_the_screen(self, served, monkeypatch, path):
        from modules import csp
        # For the frame the page is measured in, and nothing else (as the layout test does).
        monkeypatch.setattr(csp, "STRICT_POLICY", csp.STRICT_POLICY.replace(
            "frame-ancestors 'none'", "frame-ancestors 'self'"))
        b = served["b"]
        b._call("POST", f"/session/{b.session}/window/rect", {"width": 1200, "height": 900})
        b.go(served["srv"].url("/v2/devices"))
        b.wait_for("return !!window.Alpine", 10)
        b.js("var f=document.createElement('iframe'); f.id='phone'; f.width='390';"
             "f.height='800'; f.style.position='fixed'; f.style.left='0'; f.style.top='0';"
             "f.style.border='0'; f.style.zIndex='9999';"
             f"f.src=location.origin + {json.dumps(path)};"
             "document.documentElement.appendChild(f); return 1")
        b.wait_for("var d=document.getElementById('phone').contentDocument;"
                   "return d && d.querySelector('#devices, #save-op') && d.defaultView.Alpine", 15)
        got = b.js("var w=document.getElementById('phone').contentWindow, d=w.document;"
                   "return {inner: w.innerWidth, scroll: d.documentElement.scrollWidth};")
        assert got["inner"] == 390 and got["scroll"] <= 390, got
