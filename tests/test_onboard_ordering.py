""""Nothing committed" means no commit was CREATED.

Stage 4C.3.

A commit followed by a reset leaves a clean tree and looks identical from
`git status` — and it is not the same thing at all:

* the object is still in `.git`, reachable from the reflog;
* the post-commit hook fired **in between**, so if the list has a remote the
  commit is already on GitHub, **where nothing local can retract it**.

So the assertion is on the **commit count**, on **HEAD's sha**, on the
**reflog**, and — the sharpest of the four — on the **post-commit hook never
having run**. That last one is what actually distinguishes "no commit" from
"a commit that was undone", because it is the hook that makes the commit
somebody else's problem.

It also constrains the ordering: **the commit must be genuinely last among
the things that can fail.** Anything fallible after it is a partial state the
repository already records.
"""

import os
import subprocess

import pytest


def _git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args],
                          capture_output=True, text=True).stdout.strip()


@pytest.fixture
def world(tmp_path, monkeypatch):
    """A real repo with one commit, and a spy on the post-commit hook."""
    from modules.nsot import repo as _repo

    list_dir = tmp_path / "probe"
    repo_dir = str(list_dir / "config_repo")
    os.makedirs(os.path.join(repo_dir, "golden"), exist_ok=True)

    monkeypatch.setattr("modules.config.get_list_data_dir",
                        lambda name: str(list_dir))
    monkeypatch.setattr("modules.settings_schema.get_setting",
                        lambda k, d=None: {"nsot_git_author_name": "NMAS",
                                           "nsot_git_author_email": "n@l"}.get(k, d))
    fired = []
    monkeypatch.setattr("modules.nsot.hooks.run_post_commit",
                        lambda ctx: fired.append(ctx))

    _repo.init_repo(repo_dir)
    return {"repo": repo_dir, "hook_fired": fired}


class _Plan:
    """The minimum `run_onboarding` reads. Not a mock of OnboardPlan — a
    stand-in for it, so this file tests the ORDERING and not the plan."""

    hostname = "bp-onboard-c"
    onboardable = True
    blocking_reasons = []


def _state(repo):
    """Everything that would distinguish 'no commit' from 'undone commit'."""
    return {
        "head": _git(repo, "rev-parse", "HEAD"),
        "count": _git(repo, "rev-list", "--count", "HEAD"),
        "reflog": len(_git(repo, "reflog", "--format=%H").splitlines()),
        "all_objects": len(_git(repo, "rev-list", "--all", "--reflog").splitlines()),
    }


def _run(world, **over):
    from modules.nsot.onboard import run_onboarding

    steps = {"bind_credentials": lambda p: None,
             "commit": lambda p: "deadbeef",
             "render": lambda p: "config"}
    steps.update(over)
    return run_onboarding(_Plan(), repo=world["repo"], **steps)


class TestAFailureBeforeTheCommitCreatesNoCommit:
    """Your precision: not "the branch ended where it started"."""

    def _fail_at_netbox(self, world):
        """Named for what it tests, not for the step that used to fail.

        NetBox creation moved to phase 2 (a device record is a claim the
        device exists, and phase 1 has not seen it), so the step before the
        commit is now `credentials`. The PROPERTY is unchanged and is the
        point: a failure anywhere before the commit creates no commit.
        """
        def _boom(plan):
            raise RuntimeError("the credential store rejected the write")

        return _run(world, bind_credentials=_boom)

    def test_the_run_reports_where_it_failed(self, world):
        out = self._fail_at_netbox(world)
        assert out["ok"] is False
        assert out["failed_at"] == "credentials"
        assert "rejected" in out["reason"]

    def test_the_commit_count_is_unchanged(self, world):
        before = _state(world["repo"])
        self._fail_at_netbox(world)
        assert _state(world["repo"])["count"] == before["count"]

    def test_heads_sha_is_unchanged(self, world):
        before = _state(world["repo"])
        self._fail_at_netbox(world)
        assert _state(world["repo"])["head"] == before["head"]

    def test_the_reflog_has_no_new_entry(self, world):
        """A reset leaves one. This is what separates 'never committed' from
        'committed and moved back'."""
        before = _state(world["repo"])
        self._fail_at_netbox(world)
        assert _state(world["repo"])["reflog"] == before["reflog"]

    def test_no_unreachable_commit_object_exists(self, world):
        """`rev-list --all --reflog` finds a commit a reset orphaned."""
        before = _state(world["repo"])
        self._fail_at_netbox(world)
        assert _state(world["repo"])["all_objects"] == before["all_objects"]

    def test_the_post_commit_hook_never_fired(self, world):
        """**The sharpest of the five.** The hook is what pushes; once it has
        run, the commit may already be on a remote where nothing local can
        retract it. A clean tree proves nothing about that."""
        self._fail_at_netbox(world)
        assert world["hook_fired"] == []

    def test_the_run_never_calls_commit_at_all(self, world):
        """Not "committed and undone" — not called."""
        called = []
        self._fail_at_netbox_with(world, called)
        assert called == []

    def _fail_at_netbox_with(self, world, called):
        def _boom(plan):
            raise RuntimeError("x")

        return _run(world, bind_credentials=_boom,
                    commit=lambda p: called.append(p) or "sha")


class TestCommitThenResetIsCaught:
    """The implementation this suite must reject.

    Written as a deliberate wrong implementation, run against the same
    assertions. If these pass, the assertions above are measuring a clean
    tree rather than an absent commit.
    """

    def _commit_then_reset(self, world):
        """What a 'tidy up after ourselves' implementation would do."""
        from modules.nsot import repo as _repo

        repo = world["repo"]
        before = _git(repo, "rev-parse", "HEAD")
        with open(os.path.join(repo, "golden", "x.cfg"), "w") as fh:
            fh.write("hostname x\n")
        _repo.git(repo, "add", "-A")
        _repo.git(repo, "-c", "user.email=n@l", "-c", "user.name=N",
                  "commit", "-m", "onboarding: bp-onboard-c")
        _repo.hooks_fired = True
        from modules.nsot import hooks
        hooks.run_post_commit({"repo": repo, "sha": _git(repo, "rev-parse", "HEAD")})
        _repo.git(repo, "reset", "--hard", before)

    def test_the_tree_looks_clean_afterwards(self, world):
        """Which is exactly why a status check would not have caught it."""
        self._commit_then_reset(world)
        assert _git(world["repo"], "status", "--porcelain") == ""

    def test_and_heads_sha_is_back_where_it_started(self, world):
        before = _state(world["repo"])["head"]
        self._commit_then_reset(world)
        assert _state(world["repo"])["head"] == before

    def test_but_the_reflog_records_it(self, world):
        before = _state(world["repo"])["reflog"]
        self._commit_then_reset(world)
        assert _state(world["repo"])["reflog"] > before

    def test_and_the_commit_object_survives(self, world):
        before = _state(world["repo"])["all_objects"]
        self._commit_then_reset(world)
        assert _state(world["repo"])["all_objects"] > before

    def test_and_the_hook_fired(self, world):
        """The one that matters: it may already be on a remote."""
        self._commit_then_reset(world)
        assert world["hook_fired"] != []


class TestTheCommitIsLastAmongTheFallible:

    def test_the_declared_order_puts_the_commit_second_of_three(self):
        """Three steps since NetBox creation moved to phase 2.

        The rationale is unchanged and now cheaper to hold: phase 1 is
        entirely local, so the commit is still the only step that creates
        something durable and is still last among the fallible.
        """
        from modules.nsot.onboard import STEPS

        assert STEPS == ("credentials", "commit", "render")
        assert "netbox" not in STEPS

    def test_only_the_render_follows_it(self):
        from modules.nsot.onboard import STEPS

        assert STEPS[STEPS.index("commit") + 1:] == ("render",)

    def test_a_render_failure_reports_the_device_as_onboarded(self, world):
        """It IS onboarded — the commit happened. The artefact is missing.
        Two facts, and the operator needs both."""
        def _boom(plan):
            raise RuntimeError("jinja exploded")

        out = _run(world, render=_boom)
        assert out["ok"] is True
        assert out["failed_at"] == "render"
        assert "onboarded and committed" in out["reason"]
        assert "jinja exploded" in out["reason"]

    def test_a_render_failure_does_not_offer_cleanup(self, world):
        """Removing the NetBox objects of a device that IS committed would
        leave the repository describing a device NetBox does not have."""
        out = _run(world, render=lambda p: (_ for _ in ()).throw(RuntimeError("x")))
        assert out["cleanup_offered"] is False


class TestNoPhaseOneFailureLeavesAnythingExternal:
    """**The whole of phase 1 is local now**, which is what moving NetBox to
    phase 2 bought.

    `cleanup_offered` existed for one state: NetBox objects created and no
    commit describing them, where Remove was the right next action. That
    state cannot occur any more — phase 1 creates a credential override, a
    staged credential and a commit, all of which `abandon_onboarding()`
    removes without touching NetBox.
    """

    def test_a_commit_failure_offers_nothing_external(self, world):
        out = _run(world, commit=lambda p: (_ for _ in ()).throw(
            RuntimeError("git is unhappy")))
        assert out["failed_at"] == "commit"
        assert out["cleanup_offered"] is False

    def test_no_step_reports_netbox_objects(self, world):
        """The key is gone, not merely empty. An empty list would read as
        'NetBox was involved and created nothing'."""
        assert "netbox_created" not in _run(world)

    def test_a_credentials_failure_offers_nothing(self, world):
        """Local and reversible, which is why it goes first."""
        out = _run(world, bind_credentials=lambda p: (_ for _ in ()).throw(
            RuntimeError("x")))
        assert out["failed_at"] == "credentials"
        assert out["cleanup_offered"] is False


class TestAnUnonboardablePlanNeverStarts:

    def test_it_stops_before_the_first_step(self, world):
        from modules.nsot.onboard import run_onboarding

        class _Blocked(_Plan):
            onboardable = False
            blocking_reasons = ["no management address"]

        called = []
        out = run_onboarding(_Blocked(), repo=world["repo"],
                             bind_credentials=lambda p: called.append("c"),
                             commit=lambda p: called.append("g"),
                             render=lambda p: called.append("r"))
        assert out["ok"] is False
        assert out["failed_at"] == "plan"
        assert called == []
        assert world["hook_fired"] == []


class TestTheControlItself:
    """**The assertions above are only worth what this class proves.**

    A real commit is made and then the run fails. Every assertion in
    `TestAFailureBeforeTheCommitCreatesNoCommit` must reject it — otherwise
    they are measuring a clean tree rather than an absent commit, which is
    the entire distinction 4C.3 exists to draw.
    """

    def _commit_for_real(self, world):
        """An injected `commit` that actually commits, through the real path
        so the post-commit hook fires exactly as it would in production."""
        from modules.nsot import hooks
        from modules.nsot import repo as _repo

        def _commit(plan):
            repo = world["repo"]
            with open(os.path.join(repo, "golden", "bp.cfg"), "w") as fh:
                fh.write("hostname bp-onboard-c\n")
            _repo.git(repo, "add", "-A")
            _repo.git(repo, "-c", "user.email=n@l", "-c", "user.name=N",
                      "commit", "-m", "onboarding: bp-onboard-c")
            sha = _git(repo, "rev-parse", "HEAD")
            hooks.run_post_commit({"repo": repo, "sha": sha})
            return sha

        return _commit

    def test_a_real_commit_moves_every_signal(self, world):
        """All five, so a control that moved only one would be noticed."""
        before = _state(world["repo"])
        self._commit_for_real(world)(_Plan())
        after = _state(world["repo"])

        assert after["head"] != before["head"]
        assert after["count"] != before["count"]
        assert after["reflog"] > before["reflog"]
        assert after["all_objects"] > before["all_objects"]
        assert world["hook_fired"] != []

    def test_committing_before_a_later_step_is_caught(self, world):
        """The wrong ordering, executed. `run_onboarding` is written so this
        cannot happen — the control proves the tests would say so if it did.
        """
        from modules.nsot.onboard import run_onboarding

        before = _state(world["repo"])
        commit = self._commit_for_real(world)

        # The order this suite forbids: commit, then a step that fails.
        commit(_Plan())
        out = run_onboarding(
            _Plan(), repo=world["repo"],
            bind_credentials=lambda p: (_ for _ in ()).throw(RuntimeError("boom")),
            commit=lambda p: "already-done",
            render=lambda p: None)

        assert out["failed_at"] == "credentials"
        # And every signal says a commit exists, which is the point.
        after = _state(world["repo"])
        assert after["head"] != before["head"]
        assert after["count"] != before["count"]
        assert world["hook_fired"] != [], (
            "the hook fired: on a list with a remote this is already pushed")

    def test_the_real_implementation_does_not_do_that(self, world):
        """Same failure, the shipped ordering: nothing moved."""
        before = _state(world["repo"])
        from modules.nsot.onboard import run_onboarding

        out = run_onboarding(
            _Plan(), repo=world["repo"],
            bind_credentials=lambda p: (_ for _ in ()).throw(RuntimeError("boom")),
            commit=self._commit_for_real(world),
            render=lambda p: None)

        assert out["failed_at"] == "credentials"
        assert _state(world["repo"]) == before
        assert world["hook_fired"] == []


class TestTheREALStepsSatisfyTheContract:
    """**4C.7's whole point.** Everything above proves the contract holds for
    injected steps; that proves the contract, not that the production steps
    satisfy it.

    "The unit was right and the wiring was absent" has already happened twice
    in this stage — the slug/dialect gate, and six build steps declared
    complete while `run_onboarding` had no caller. The tell was the same both
    times: **every test that passed sat below the missing connection.**

    So these run `run_onboarding` with `real_steps()` — the shipped adapters
    — against faked *dependencies* rather than faked steps. The seam moves
    from "above the adapters" to "below them".
    """

    @pytest.fixture
    def wired(self, world, tmp_path, monkeypatch):
        """The real adapters, with NetBox, the credential store and the clock
        faked. Everything between `run_onboarding` and those is real code."""
        from modules.nsot import onboard

        list_dir = tmp_path / "probe"
        repo = world["repo"]
        monkeypatch.setattr("modules.config.get_list_data_dir",
                            lambda name: os.path.dirname(repo))
        monkeypatch.setattr("modules.settings_schema.get_setting",
                            lambda k, d=None: {
                                "nsot_git_author_name": "NMAS",
                                "nsot_git_author_email": "n@l",
                                "netbox_allow_writes": True}.get(k, d))
        monkeypatch.setattr("modules.secrets_store.KEY_FILE",
                            str(tmp_path / "key.key"))
        monkeypatch.setattr("modules.secrets_store._fernet", None)

        # THE REAL `set_device_override`, against a temp store.
        #
        # It used to be stubbed with
        #     lambda lst, host, values: ...
        # which is the signature the CALLER had wrongly assumed. The real one
        # is `(device_key, username, password, secret="")`. Test and code
        # agreed with each other and both disagreed with `credentials.py`, so
        # a step that raised AttributeError in production passed here every
        # time — the same shape as the BGP address-families fixtures, where
        # parse and render flattened symmetrically.
        #
        # A file, not a stub: a stub's signature can drift from the function
        # it stands in for, and this one did. "The REAL adapters" has to
        # include the adapter most likely to be misread.
        monkeypatch.setattr("modules.credentials._FILE",
                            str(tmp_path / "credentials.json"))
        synced = []
        monkeypatch.setattr(
            "modules.netbox_client.sync_list_to_netbox",
            lambda lst, devices, **kw: synced.append(devices) or {"ok": True})
        monkeypatch.setattr("modules.netbox_guard.get_created",
                            lambda lst, endpoint="": {"dcim/devices/": {9: "bp"}})

        class _Plan:
            hostname = "bp-onboard-c"
            list_name = "probe"
            mgmt_ip = "203.0.113.60"
            # The bootstrap parameters `commit_step` commits as intent, so
            # the config can be re-derived from the staged credential. A
            # stand-in missing them fails the step rather than the test,
            # which is the stand-in drifting from what it stands in for.
            mgmt_mask = "255.255.255.0"
            manager_interface = "GigabitEthernet2"
            manager_gateway = ""
            domain = "rcn.lab"
            platform = "cisco_iosxe"
            host_vars = {"hostname": "bp-onboard-c"}
            bootstrap_config = "hostname bp-onboard-c\n!\nend\n"
            onboardable = True
            blocking_reasons = []

        return {"plan": _Plan(), "repo": repo, "mgmt_ip": "203.0.113.60",
                "synced": synced, "onboard": onboard, "world": world}

    def _run(self, wired, **over):
        steps = wired["onboard"].real_steps(wired["repo"], actor="probe@lab")
        steps.update(over)
        return wired["onboard"].run_onboarding(
            wired["plan"], repo=wired["repo"], **steps)

    def test_a_clean_run_completes_every_step(self, wired):
        out = self._run(wired)
        assert out["ok"] is True, out
        assert out["completed"] == ["credentials", "commit", "render"]

    def test_the_real_credential_step_stages_and_records(self, wired):
        """Asserted through `resolve()`, which is what phase 2 will call.

        The previous version read a dict the stub had built, so it checked
        that the step called something with certain arguments. What matters
        is that the credential the device boots with is the one the resolver
        hands back for that device — a property no argument comparison can
        express, and the one that was false.
        """
        import modules.credentials as creds

        self._run(wired)
        staged = wired["onboard"].staged_bootstrap_credential(
            wired["repo"], "bp-onboard-c")
        assert staged and len(staged) >= 20

        got = creds.resolve(wired["mgmt_ip"])
        assert got["ok"] is True, got
        assert got["source"] == "device-override"
        assert got["username"] == "admin"
        assert got["password"] == staged, "the device would boot with a "\
            "credential the resolver cannot produce"

    def test_the_real_commit_step_makes_exactly_one_commit(self, wired):
        before = _state(wired["repo"])["count"]
        self._run(wired)
        assert int(_state(wired["repo"])["count"]) == int(before) + 1

    def test_no_real_step_touches_netbox(self, wired, monkeypatch):
        """**The two NetBox tests that were here are gone with the step.**

        They asserted that a blocked or failing NetBox write left no commit —
        a real property, of a step that no longer runs in phase 1. A NetBox
        device record is a claim the device exists, and phase 1 has not seen
        it; `create_netbox_record()` runs in phase 2, after promotion, when a
        capture exists for the importer to read.

        What replaces them is stronger: phase 1 must not reach NetBox at all,
        so there is no blocked-write case to get wrong.
        """
        calls = []
        monkeypatch.setattr("modules.netbox_client.sync_list_to_netbox",
                            lambda *a, **k: calls.append(a) or {"ok": True})
        out = self._run(wired)
        assert out["ok"] is True, out
        assert calls == [], "phase 1 called the NetBox importer"

    def test_the_result_carries_no_netbox_key(self, wired):
        """Absent, not empty. An empty list reads as "NetBox ran and created
        nothing", which is exactly the state that made a failed import look
        like a successful onboarding."""
        out = self._run(wired)
        assert "netbox_created" not in out
        assert out["cleanup_offered"] is False


    def test_real_steps_is_assembled_in_one_place(self):
        """Two copies of the mapping would be two orderings, and the ordering
        is what this file exists to pin."""
        from tests.astcheck import calls_in

        from modules.nsot import onboard
        from routes import onboard as route

        assert calls_in(route.create, "real_steps") == 1
        for name in ("bind_credentials_step", "commit_step", "render_step"):
            assert hasattr(onboard, name)
        # And the one that moved: it exists, and phase 1 does not use it.
        assert hasattr(onboard, "create_netbox_record")
        assert not hasattr(onboard, "create_netbox_step"), (
            "the phase-1 NetBox step is gone; a lingering copy would be a "
            "second way to create the objects")

    # ---- minting is not recording -------------------------------------
    #
    # `adopt_identity()` returns a string and persists nothing -- that is
    # its whole job, being the one place a new identity is created,
    # separate from `resolve_identity()`. Writing it to the manifest is
    # `upsert_device()`, and `commit_step` was not calling it: the return
    # value was assigned to nothing.
    #
    # Measured before the fix: after a successful `commit_step` the commit
    # existed, `host_vars/` was committed, and `manifest.load(repo)
    # ["devices"]` was `{}`. The device was in git and in NetBox and
    # unknown to the identity map. The docstring said "the identity is
    # minted here and only here" -- true about the call, false about the
    # outcome.

    def test_the_manifest_has_an_entry_afterwards(self, wired):
        from modules.nsot import manifest as _m

        self._run(wired)
        identity, entry = _m.find_by_name(wired["repo"], "bp-onboard-c")
        assert identity, "no identity recorded — minted and discarded"
        assert entry["name"] == "bp-onboard-c"
        assert entry["mgmt_ip"] == wired["mgmt_ip"]
        assert entry["platform"] == "cisco_iosxe"

    def test_the_entry_is_what_blocks_a_second_onboarding(self, wired):
        """The property the entry exists for. Without it `_name_in_manifest`
        never fires and the wizard would happily onboard the same name
        twice, into two identities, with one golden path between them."""
        from modules.nsot.onboard import _name_in_manifest

        assert _name_in_manifest(wired["repo"], "bp-onboard-c") == (False, True)
        self._run(wired)
        assert _name_in_manifest(wired["repo"], "bp-onboard-c") == (True, True)
