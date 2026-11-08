"""Mercury's half of the controller app deploy channel (the SDN platform design revision 6,
section 10 H; revision 7, decision 25; P6): `modules/apps/channel.py` (staging from the pinned
revision's blobs, the plan and its refusals), `modules/apps/conformance.py` (T17) and
`modules/apps/post_check.py` (the bounded post-check, the rollback, drift).

Cases, each planted:
- decision 25 (T13): an uncommitted edit in a Published app's folder never reaches what is
  staged, whose recomputed hash equals the pin; a pin other than the staged hash refuses,
  naming both; a Draft stages nothing and is refused naming its state;
- change C2 (T22): with the unit's User root (or empty) and `/opt/ryu-apps` writable by the
  deploy account the plan refuses naming both operands; with User=ryu the same plan goes ahead;
  with the folder root-owned and the User root (S1 to S3) it refuses naming the folder it cannot
  stage into;
- T17: an enabled set offering 1.4 with an EOS 4.17 switch is refused, as is a set that pins no
  version (C2598); of_versions pinning 1.0 and 1.3 passes;
- the plan's drop-in is the script's own render of the same request;
- the post-check passes only when every switch, link and /health is back, fires at the bound
  naming what it read and that the bound is a placeholder, and a miss rolls back;
- drift names the version the controller runs and Mercury's record."""

import os
import subprocess

import pytest

from modules.apps import channel, conformance, post_check
from modules.apps.manifest import parse_manifest
from modules.jobs.lifecycle import Version, content_hash
from modules.platforms import profile

GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid",
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
UNIT = "ryu-manager.service"
MANAGER = "/opt/ryu-venv/bin/ryu-manager"
LISTEN = {"host": "192.0.2.10", "port": 6653}


def manifest(name, versions=("1.0", "1.3"), requires=()):
    req = "[" + ", ".join(requires) + "]"
    vers = "[" + ", ".join(f'"{v}"' for v in versions) + "]"
    return parse_manifest(
        f"name: {name}\nversion: 1.0.0\ncontrollers:\n  ryu: \">=4.34\"\n"
        f"openflow_versions: {vers}\nrequires: {req}\n"
        "config_schema: {type: object}\n"
        f"rest:\n  prefix: /{name}\n  endpoints:\n    - path: /health\n      methods: [GET]\n")


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                          env=dict(os.environ, **GIT_ENV)).stdout


def code_repo(tmp_path, name="of_versions"):
    repo = tmp_path / "code"
    folder = repo / "apps" / name
    (folder / "lib").mkdir(parents=True)
    (folder / f"{name}.py").write_bytes(b"OFP_VERSIONS = [1, 4]\n")
    (folder / "lib" / "helper.py").write_bytes(b"x = 1\n")
    (folder / "run.sh").write_bytes(b"#!/bin/sh\n")
    (folder / "run.sh").chmod(0o755)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "the app")
    return repo, f"apps/{name}"


def published(name, sha):
    return Version(kind="app", name=name, version="1.0.0", author="a@example.invalid",
                   state="published", reviewer="r@example.invalid", content_sha256=sha)


# ── decision 25: the pinned revision's blobs ──────────────────────────────────────────────────

def test_an_uncommitted_edit_never_reaches_what_is_staged(tmp_path):
    repo, path = code_repo(tmp_path)
    pin = content_hash(repo, path)
    (repo / path / "of_versions.py").write_bytes(b"import socket  # an uncommitted edit\n")
    (repo / path / "untracked.py").write_bytes(b"y = 2\n")
    got = channel.stage_published(published("of_versions", pin), repo, path, "HEAD",
                                  str(tmp_path / "stage"))
    assert got["ok"] is True and got["refusal"] == ""
    staged = tmp_path / "stage"
    assert (staged / "of_versions.py").read_bytes() == b"OFP_VERSIONS = [1, 4]\n"
    assert not (staged / "untracked.py").exists()
    assert got["staged"]["sha256"] == pin
    assert os.stat(staged / "run.sh").st_mode & 0o777 == 0o755
    assert sorted(f["path"] for f in got["staged"]["files"]) == [
        "lib/helper.py", "of_versions.py", "run.sh"]


def test_a_staged_hash_other_than_the_pin_is_refused_naming_both(tmp_path):
    repo, path = code_repo(tmp_path)
    got = channel.stage_published(published("of_versions", "a" * 64), repo, path, "HEAD",
                                  str(tmp_path / "stage"))
    pin = content_hash(repo, path)
    assert got["ok"] is False
    assert got["refusal"] == (f"the staged folder's hash {pin} is not the Published {'a' * 64}")


def test_a_draft_stages_nothing_and_is_refused_naming_its_state(tmp_path):
    repo, path = code_repo(tmp_path)
    draft = Version(kind="app", name="of_versions", version="1.0.0", author="a@example.invalid",
                    content_sha256=content_hash(repo, path))
    got = channel.stage_published(draft, repo, path, "HEAD", str(tmp_path / "stage"))
    assert got["ok"] is False and got["staged"] is None
    assert "is draft: only a Published version deploys" in got["refusal"]
    assert not (tmp_path / "stage").exists()


def test_a_link_in_the_folder_is_refused_at_staging(tmp_path):
    repo, path = code_repo(tmp_path)
    os.symlink("/etc/passwd", repo / path / "passwd")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "a link")
    with pytest.raises(channel.ChannelRefused, match="passwd in apps/of_versions at HEAD is a "
                                                     "symbolic link"):
        channel.stage(repo, path, "HEAD", str(tmp_path / "stage"))


# ── the plan: C2, the folder, conformance ────────────────────────────────────────────────────

def show(user):
    return (f"User={user}\nExecStart={{ path={MANAGER} ; argv[]={MANAGER} --observe-links "
            "--ofp-tcp-listen-port 6653 ; ignore_errors=no ; start_time=[n/a] ; pid=0 ; "
            "code=(null) ; status=0/0 }\n")


def ls(owner, mode="drwxr-xr-x"):
    return (f"total 12\n{mode} 3 {owner} {owner} 4096 Nov 17 10:00 .\n"
            "drwxr-xr-x 9 root root 4096 Nov 10 10:00 ..\n")


def eos(name="sw-a"):
    return {"name": name, "dpid": 1, "selected": profile.select("arista_eos", "4.17.0F")}


def enabled(tmp_path, names=("of_versions",), versions=("1.0", "1.3")):
    out = []
    for name in names:
        repo, path = code_repo(tmp_path / name, name)
        pin = content_hash(repo, path)
        staged = channel.stage(repo, path, "HEAD", str(tmp_path / name / "stage"))
        out.append({"version": published(name, pin), "manifest": manifest(name, versions),
                    "staged": staged})
    return out


def plan(tmp_path, user="ryu", owner="mercury", mode="drwxr-xr-x", items=None, switches=None,
         links=None, previous=None, observed=None, listen=None, cat=""):
    return channel.plan(network="lab9", controller="ctl", unit=UNIT,
                        enabled=enabled(tmp_path) if items is None else items,
                        host={"show": show(user), "ls": ls(owner, mode), "cat": cat},
                        listen=LISTEN if listen is None else listen,
                        switches=[eos()] if switches is None else switches,
                        links=[] if links is None else links, previous=previous,
                        observed=observed)


def test_user_ryu_and_a_folder_the_deploy_account_owns_plans_the_deploy(tmp_path):
    got = plan(tmp_path)
    assert got["ok"] is True, got["refusals"]
    assert got["request"]["apps"][0]["name"] == "of_versions"
    assert got["window"] == {"devices": ["ctl"], "unreachable": ["sw-a"],
                             "seconds": channel.window_seconds()}
    assert "placeholder" in got["reconnect"]["words"] and got["reconnect"]["switches"] == ["sw-a"]
    assert len(got["plan_sha256"]) == 64 and got["files"]["of_versions"]


@pytest.mark.parametrize("user", ["", "root"])
def test_root_over_a_folder_the_deploy_account_writes_is_refused_naming_both(tmp_path, user):
    got = plan(tmp_path, user=user)
    assert got["ok"] is False and "request" not in got
    [c2] = [r for r in got["refusals"] if r.startswith("refused before staging (C2)")]
    assert f"User is {user!r} (root)" in c2
    assert "/opt/ryu-apps is mercury:mercury drwxr-xr-x, which mercury may write" in c2


def test_a_group_writable_folder_counts_as_writable_for_c2(tmp_path):
    got = channel.plan(network="lab9", controller="ctl", unit=UNIT, enabled=enabled(tmp_path),
                       host={"show": show("root"), "ls": ls("root", "drwxrwxr-x"), "cat": ""},
                       listen=LISTEN, switches=[eos()],
                       links=[], previous=None)
    assert any(r.startswith("refused before staging (C2)") for r in got["refusals"])


def test_root_over_a_root_owned_folder_is_refused_naming_the_folder_it_cannot_stage_into(
        tmp_path):
    got = plan(tmp_path, user="", owner="root")
    assert got["ok"] is False
    assert any(r.startswith("mercury cannot stage into /opt/ryu-apps: it is root:root "
                            "drwxr-xr-x") for r in got["refusals"]), got["refusals"]
    assert not any("(C2)" in r for r in got["refusals"])


def test_an_absent_folder_or_an_unreadable_user_is_never_a_pass(tmp_path):
    items = enabled(tmp_path)
    absent = channel.plan(network="lab9", controller="ctl", unit=UNIT, enabled=items,
                          host={"show": show("ryu"), "cat": "",
                                "ls": "ls: cannot access '/opt/ryu-apps': No such file or "
                                      "directory"}, listen=LISTEN, switches=[eos()],
                          links=[], previous=None)
    assert "/opt/ryu-apps cannot be staged into: it is absent" in absent["refusals"]
    blind = channel.plan(network="lab9", controller="ctl", unit=UNIT, enabled=items,
                         host={"show": "", "ls": ls("mercury"), "cat": ""}, listen=LISTEN,
                         switches=[eos()], links=[], previous=None)
    assert any(r.startswith(f"can't tell {UNIT}'s User") for r in blind["refusals"])


def test_a_draft_in_the_set_is_refused_at_plan(tmp_path):
    items = enabled(tmp_path)
    v = items[0]["version"]
    items[0]["version"] = Version(**dict(v.model_dump(), state="draft", reviewer=""))
    got = plan(tmp_path, items=items)
    assert any("is draft: only a Published version deploys" in r for r in got["refusals"])


def test_the_plan_s_drop_in_is_the_script_s_render_and_shows_the_one_before(tmp_path):
    before = f"[Service]\nUser=ryu\n"
    cat = (f"# /lib/systemd/system/{UNIT}\n[Service]\nExecStart={MANAGER}\n\n"
           f"# /etc/systemd/system/{UNIT}.d/mercury.conf\n{before}")
    got = channel.plan(network="lab9", controller="ctl", unit=UNIT, enabled=enabled(tmp_path),
                       host={"show": show("ryu"), "ls": ls("mercury"), "cat": cat},
                       listen=LISTEN, switches=[eos()],
                       links=[], previous=None)
    s = channel.script()
    assert got["dropin_before"] == before
    assert got["dropin_after"] == s.render_dropin(got["request"], MANAGER, "ryu",
                                                  "/opt/ryu-apps")
    assert got["request_sha256"] == s.request_sha256(got["request"])


def test_an_ipv6_listen_address_reaches_the_drop_in(tmp_path):
    got = channel.plan(network="lab9", controller="ctl", unit=UNIT, enabled=enabled(tmp_path),
                       host={"show": show("ryu"), "ls": ls("mercury"), "cat": ""},
                       listen={"host": "2001:db8::10", "port": 6653}, switches=[eos()],
                       links=[], previous=None)
    assert got["ok"] is True and "--ofp-listen-host 2001:db8::10 " in got["dropin_after"]


def test_the_load_order_puts_requirements_first_and_refuses_a_missing_one():
    order = channel.load_order([manifest("forwarding", requires=("switch_quirks",)),
                                manifest("switch_quirks", requires=("of_versions",)),
                                manifest("of_versions")])
    assert [m.name for m in order] == ["of_versions", "switch_quirks", "forwarding"]
    with pytest.raises(channel.ChannelRefused, match="forwarding 1.0.0 requires switch_quirks, "
                                                     "which the enabled set"):
        channel.load_order([manifest("forwarding", requires=("switch_quirks",))])


# ── T17: conformance ─────────────────────────────────────────────────────────────────────────

def test_an_app_set_offering_1_4_with_an_eos_4_17_switch_is_refused():
    got = conformance.check([manifest("forwarding", versions=("1.3", "1.4"))], [eos()])
    assert got["ok"] is False and got["offered"] == ["1.3", "1.4"]
    [p] = got["problems"]
    assert p.startswith("sw-a (Arista EOS, profile arista_eos") and \
        "refuses a hello above 1.3, and the controller's hello is 1.4" in p


def test_a_set_pinning_no_version_offers_1_5_and_is_refused(tmp_path):
    """C2598: Ryu's own apps alone offer 1.0 to 1.5, whose hello the Aristas refuse."""
    got = conformance.check([], [eos()])
    assert got["offered"][-1] == "1.5" and not got["ok"]
    refused = channel.plan(network="lab9", controller="ctl", unit=UNIT, enabled=[],
                           host={"show": show("ryu"), "ls": ls("mercury"), "cat": ""},
                           listen=LISTEN, switches=[eos()], links=[], previous=None)
    assert any(r.startswith("conformance: sw-a") for r in refused["refusals"])


def test_of_versions_pinning_1_0_and_1_3_passes_with_the_aristas():
    got = conformance.check([manifest("of_versions"), manifest("forwarding", ("1.3",))],
                            [eos("sw-a"), eos("sw-b")])
    assert got["ok"] is True and got["offered"] == ["1.3"]


def test_a_switch_no_profile_covers_is_can_t_tell_and_refuses():
    got = conformance.check([manifest("of_versions")],
                            [{"name": "sw-x", "selected": profile.select("arista_eos", "9.1")}])
    assert got["ok"] is False and got["problems"][0].startswith("can't tell whether sw-x")


def test_apps_sharing_no_version_are_refused():
    got = conformance.check([manifest("a_app", ("1.0",)), manifest("b_app", ("1.3",))], [])
    assert got["ok"] is False and "share no OpenFlow version" in got["problems"][0]


# ── the post-check, the rollback ─────────────────────────────────────────────────────────────

def link(a, pa, b, pb):
    return {"src": {"dpid": a, "port_no": pa}, "dst": {"dpid": b, "port_no": pb}}


EXPECTED = {"switches": [1, 2], "links": [link(1, 1, 2, 1)], "apps": ["of_versions"]}
ALL_BACK = {"switches": {"ok": True, "switches": [{"dpid": 1}, {"dpid": 2}]},
            "links": {"ok": True, "links": [link(2, 1, 1, 1)]},
            "health": {"of_versions": {"ok": True}}}
SWITCH_2_DOWN = dict(ALL_BACK, switches={"ok": True, "switches": [{"dpid": 1}]})


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


def test_the_post_check_passes_when_every_switch_link_and_health_is_back():
    clock, reads = Clock(), iter([SWITCH_2_DOWN, ALL_BACK])
    got = post_check.wait(lambda: next(reads), EXPECTED, clock=clock, sleep=clock.sleep)
    assert got["ok"] is True and got["polls"] == 2 and got["came_back"] == {1: 0.0, 2: 5.0}


def test_the_post_check_s_bound_fires_naming_what_it_read_and_that_it_is_a_placeholder():
    clock = Clock()
    got = post_check.wait(lambda: SWITCH_2_DOWN, EXPECTED, clock=clock, sleep=clock.sleep)
    assert got["ok"] is False and got["elapsed_s"] >= post_check.bound()["seconds"]
    assert "switches not back: 2" in got["words"] and f"{got['polls']} reads" in got["words"]
    assert "a placeholder" in got["words"] and "S1 (2026-11-10)" in got["words"]


def test_an_unreadable_read_never_passes_a_poll():
    got = post_check.evaluate(EXPECTED, dict(ALL_BACK, links={"ok": False, "error": "404"}))
    assert got["ok"] is False and got["unreadable"] == ["the links (404)"]
    no_health = post_check.evaluate(EXPECTED, dict(ALL_BACK, health={}))
    assert no_health["ok"] is False and no_health["unreadable"] == ["of_versions's /health "
                                                                    "(no answer)"]


class FakeChannel:
    def __init__(self, outcomes):
        self.staged, self.outcomes, self.calls = [], list(outcomes), []

    def stage(self, req):
        self.calls.append("stage")
        self.staged.append(req)

    def apply(self):
        self.calls.append("apply")
        return self.outcomes.pop(0)


def expected_switches():
    """The switches EXPECTED names, as the plan takes them (DPIDs 1 and 2)."""
    return [eos("sw-a"), dict(eos("sw-b"), dpid=2)]


def run_deploy(tmp_path, reads, outcomes, previous=None, window_ok=True):
    """A deploy of a plan whose expected is EXPECTED and whose rollback target is *previous*
    (the plan's, which the deploy takes; C2706)."""
    accepted = plan(tmp_path, switches=expected_switches(), links=EXPECTED["links"],
                    previous=previous)
    assert accepted["ok"], accepted["refusals"]
    assert accepted["expected"] == EXPECTED
    clock, chan, windows = Clock(), FakeChannel(outcomes), []

    def declare(devices, start, end, by, why, unreachable):
        windows.append({"devices": devices, "unreachable": unreachable, "staged_before":
                        len(chan.staged)})
        return {"ok": window_ok, "error": "" if window_ok else "the restart record is "
                                                               "unreadable"}
    reads = iter(reads)
    receipt = post_check.deploy(accepted, channel=chan, read=lambda: next(reads, SWITCH_2_DOWN),
                                declare_window=declare, by="op@example.invalid", clock=clock,
                                sleep=clock.sleep, now=clock)
    return receipt, chan, windows, accepted


OK_APPLY = {"ok": True, "main_pid_before": "100", "main_pid_after": "101"}


def test_a_deploy_declares_its_window_before_staging_and_is_deployed_when_all_come_back(
        tmp_path):
    receipt, chan, windows, accepted = run_deploy(tmp_path, [ALL_BACK], [OK_APPLY])
    assert receipt["outcome"] == "deployed"
    assert windows == [{"devices": ["ctl"], "unreachable": ["sw-a", "sw-b"],
                        "staged_before": 0}]
    assert chan.staged == [accepted["request"]]


def test_a_missed_post_check_rolls_back_to_the_previous_request(tmp_path):
    previous = {"apps": [], "listen": LISTEN}
    # The first post-check reads at 0, 5, ... seconds up to its bound, every read missing one
    # switch; the rollback's first read finds everything back.
    polls = int(post_check.bound()["seconds"] // post_check.POLL_S) + 1
    reads = [SWITCH_2_DOWN] * polls + [ALL_BACK]
    receipt, chan, _, accepted = run_deploy(tmp_path, reads, [OK_APPLY, OK_APPLY],
                                            previous=previous)
    assert receipt["outcome"] == "rolled back", receipt
    assert chan.staged == [accepted["request"], previous]
    assert receipt["post_check"]["ok"] is False and receipt["rollback_post_check"]["ok"] is True
    assert [s["step"] for s in receipt["steps"]] == ["window", "apply", "post-check",
                                                     "rollback apply", "rollback post-check"]


def test_a_miss_with_no_previous_request_and_no_drop_in_before_is_not_rolled_back(tmp_path):
    """No previous request and no drop-in before (the plan read none): nothing can be put
    back, so no rollback is tried, and the receipt says so in its own word, never "rollback
    failed" (C2709). With a drop-in before, the put-back runs: tests/test_controller_rollback.py."""
    receipt, chan, _, _ = run_deploy(tmp_path, [], [OK_APPLY])
    assert receipt["outcome"] == "not rolled back" and "no rollback was tried" in receipt["error"]
    assert chan.calls == ["stage", "apply"]


def test_an_unrecorded_window_stages_nothing(tmp_path):
    receipt, chan, _, _ = run_deploy(tmp_path, [ALL_BACK], [OK_APPLY], window_ok=False)
    assert receipt["outcome"] == "refused" and chan.calls == []
    assert "the planned-restart window was not recorded" in receipt["error"]


def test_a_refused_apply_is_the_receipt_s_outcome(tmp_path):
    refusal = {"ok": False, "refused": "no request: /opt/ryu-apps/.apply/request.json does "
                                       "not exist"}
    receipt, chan, _, _ = run_deploy(tmp_path, [ALL_BACK], [refusal])
    assert receipt["outcome"] == "apply failed" and receipt["error"].startswith("no request")


# ── drift ────────────────────────────────────────────────────────────────────────────────────

def test_drift_names_the_version_the_controller_runs_and_mercury_s_record():
    req = {"apps": [{"name": "switch_quirks", "version": "1.3.0", "sha256": "0" * 64}],
           "listen": LISTEN}
    running = (f"User=ryu\nExecStart={{ path={MANAGER} ; argv[]={MANAGER} --observe-links "
               "/opt/ryu-apps/switch_quirks/1.2.0/switch_quirks.py "
               "/opt/ryu-apps/extra/0.1.0/extra.py ryu.app.ofctl_rest ; pid=1 }\n")
    got = post_check.drift(req, show_text=running, cat_text="", unit=UNIT)
    assert got["state"] == "drift"
    assert ("the controller runs switch_quirks 1.2.0; Mercury's record says 1.3.0; Preview "
            "the redeploy") in got["rows"]
    assert any(r.startswith("the controller runs extra 0.1.0, which Mercury's record does not")
               for r in got["rows"])
    assert "not among the host's reads" in got["read"]


def test_no_drift_when_the_controller_runs_the_render():
    req = channel.request([{"name": "switch_quirks", "version": "1.3.0", "sha256": "0" * 64}],
                          LISTEN)
    dropin = channel.render_dropin(req, MANAGER)
    argv = dropin.splitlines()[-1][len("ExecStart="):]
    shown = f"User=ryu\nExecStart={{ path={MANAGER} ; argv[]={argv} ; pid=1 }}\n"
    cat = f"# /etc/systemd/system/{UNIT}.d/mercury.conf\n{dropin}"
    got = post_check.drift(req, show_text=shown, cat_text=cat, unit=UNIT)
    assert got == {"state": "ok", "rows": [], "read": got["read"]}
