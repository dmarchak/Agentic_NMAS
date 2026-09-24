"""Does a plan actually reach `to_deploy` when nothing has changed?

**The question the suite could not answer.** `plan_batch()` is well covered and
`/deploy/plan` is well covered, but nothing drove **one route into the other**
— so "the capture hash the plan publishes is the capture hash the apply
recomputes" was true by inspection and by nothing else.

That matters because the only outcome a mismatch can produce is
`skipped_drifted`, and the one thing that would notice a guard refusing
everything is a deploy that completes. The branch site is the first
configuration this tool authors, so the path it must travel has carried very
little.

Same seam as `/onboard/create` sending `body: '{}'`, and as `loadOnboardPending`
having no caller: two halves each tested on their own, and the defect living
only in the relationship.
"""

import hashlib

import pytest

CAPTURE = (
    "hostname r6\n"
    "username admin privilege 15 secret 9 $9$abcdefghijklmnop\n"
    "interface GigabitEthernet2\n"
    " ip address 10.255.0.32 255.255.255.0\n"
    "end\n"
)


@pytest.fixture
def client(monkeypatch):
    """A deployable artifact for `r6`, identical on both calls.

    `_artifact_for` is stubbed rather than a repo built, because what is under
    test is the **hash handshake between the two routes**, not artifact
    construction. Returning the same capture from both calls is the control:
    if the routes still disagree, they disagree about something other than the
    device having changed.
    """
    import app as nmas
    import routes.deploy as rd
    from modules.nsot.render_artifact import build_artifact

    def _fake(list_name, hostname, cache=None):
        artifact = build_artifact(hostname, CAPTURE, "cisco_iosxe",
                                  template_approved=True)
        return (artifact, CAPTURE, {"hostname": hostname,
                                    "ip": "203.0.113.32"}), ""

    monkeypatch.setattr(rd, "_artifact_for", _fake)
    nmas.app.config["TESTING"] = False
    return nmas.app.test_client()


def _plan(client):
    response = client.post("/deploy/plan", json={"devices": ["r6"]})
    assert response.status_code == 200
    body = response.get_json()
    assert body["ok"] is True
    return body["devices"][0]


class TestTheCaptureHashHandshake:

    def test_the_plan_publishes_the_hash_of_the_capture(self, client):
        device = _plan(client)
        assert device["capture_hash"] == \
            hashlib.sha256(CAPTURE.encode("utf-8")).hexdigest()[:16]

    def test_an_unchanged_capture_reaches_to_deploy(self, client):
        """**The one that was missing.** If the two sides ever hash different
        things, this is the only test that can tell."""
        device = _plan(client)
        result = client.post("/deploy/apply",
                             json={"confirmations": {"r6": device["capture_hash"]}})
        body = result.get_json()
        assert body["ok"] is True
        assert "r6" in body.get("deployed", []), (
            f"a plan with nothing changed did not deploy: {body.get('by_outcome')}")
        assert "r6" not in (body.get("by_outcome") or {}).get("skipped_drifted", [])

    def test_a_stale_hash_is_skipped_as_drifted(self, client):
        """**The floor.** Without it the test above passes against a guard
        that was deleted."""
        _plan(client)
        result = client.post("/deploy/apply",
                             json={"confirmations": {"r6": "0" * 16}})
        body = result.get_json()
        assert "r6" not in body.get("deployed", [])
        outcomes = body.get("by_outcome") or {}
        assert "r6" in outcomes.get("skipped_drifted", []), outcomes

    def test_an_empty_confirmation_is_not_a_pass(self, client):
        """A client that failed to read `capture_hash` sends `''`. That must
        skip, not deploy — and it is the shape a rendering bug produces."""
        _plan(client)
        result = client.post("/deploy/apply",
                             json={"confirmations": {"r6": ""}})
        body = result.get_json()
        assert "r6" not in body.get("deployed", [])


class TestTheClientSendsWhatTheRouteReads:
    """The wizard's payload, parsed from the shipped source.

    `/onboard/create` sent `body: '{}'` and could only ever answer 409; the
    renderer test executed the render and the ordering test called the function
    directly, and the defect lived in the seam between them.
    """

    @staticmethod
    def _wizard_js():
        from tests.js_source import read_shipped

        return read_shipped("static/js/gen/partials__deploy_wizard.1.js")

    def test_the_apply_call_sends_confirmations(self):
        source = self._wizard_js()
        assert "confirmations[b.dataset.device] = b.dataset.hash" in source
        assert "d.capture_hash" in source, \
            "the checkbox no longer carries the hash the plan published"

    def test_the_apply_call_sends_command_hashes(self):
        """**It did not, from the day the wizard was written.**

        `/deploy/apply` recomputes the command fingerprint and compares it
        *only* when `command_hashes` is supplied:

            expected = command_hashes.get(hostname)
            if expected is not None:
                ...

        The wizard sent `{confirmations}` and nothing else, so from the only
        client that reaches this route the comparison **never ran** — and the
        deploy path's central claim, that the program is recomputed at apply
        and refused if anything moved, was not exercised. A plan left open
        while the device changed, or two people planning the same device,
        applied against a program nobody had read.
        """
        source = self._wizard_js()
        apply_call = source[source.index("async function applyDeploy"):]
        assert "command_hashes: commandHashes" in apply_call
        assert "b.dataset.commandHash" in apply_call

    def test_the_hashes_come_from_the_DOM_not_a_re_fetch(self):
        """**Designed in, not added after.**

        The confirmed values must be the ones the operator was *shown*.
        Re-fetching the plan at confirm time would recompute against whatever
        is current and agree with itself — the comparison would pass by
        construction, which is exactly the failure a confirm hash exists to
        prevent.
        """
        source = self._wizard_js()
        apply_call = source[source.index("async function applyDeploy"):]
        assert "/deploy/plan" not in apply_call, (
            "applyDeploy re-fetches the plan — the comparison then passes by "
            "construction")
        assert 'data-command-hash="${_dEsc(d.command_hash' in source, \
            "the card no longer carries the plan's command hash into the DOM"

    def test_the_restore_path_does_send_them(self):
        """The positive anchor: the payload is not impossible to build, and
        one client already builds it."""
        from tests.js_source import read_shipped

        source = read_shipped("static/js/gen/partials__golden_repo.3.js")
        assert "command_hashes: hashes" in source


class TestTheRefusalNamesWhatItCompared:
    """**A refusal must state what it compared, not what it thinks caused the
    difference.**

    `skipped_drifted` said *"the device configuration changed since you
    confirmed the diff"*. That is one explanation among several and the check
    establishes none of them: the capture can be byte-identical and the
    confirmed value simply not be its hash — a client sending the wrong field,
    a copied value carrying whitespace, a stale plan.

    Measured during a live diagnosis: the capture, the plan's `capture_hash`
    and the file on disk were all `c29fa63582da8f57`, the guard refused, and
    the entry carried the **whole config** and **neither** of the two
    sixteen-character strings it had compared. Four rounds and three wrong
    hypotheses, every one of which these two values would have settled.

    Third message in one session describing a state that did not occur, after
    *"a change nobody approved"* for a missing binary and *"Not a git repo, or
    nothing to commit"* for two different states.
    """

    CAPTURE = "hostname r6\ninterface Loopback0\n ip address 10.0.0.1 255.255.255.0\nend\n"

    def _skip_entry(self, confirmed_value):
        import hashlib

        from modules.nsot.deploy import plan_batch
        from modules.nsot.render_artifact import build_artifact

        artifact = build_artifact("r6", self.CAPTURE, "cisco_iosxe",
                                  template_approved=True)
        plan = plan_batch([artifact], {"r6": confirmed_value},
                          {"r6": self.CAPTURE})
        assert plan["skipped"], "expected a refusal"
        return plan["skipped"][0], hashlib.sha256(
            self.CAPTURE.encode("utf-8")).hexdigest()[:16]

    def test_both_operands_are_reported(self):
        entry, real = self._skip_entry("2c6d960d0990f2bf")
        assert entry["confirmed_hash"] == "2c6d960d0990f2bf"
        assert entry["current_hash"] == real

    def test_both_operands_appear_in_the_reason_a_human_reads(self):
        """The structured fields are for a client; the operator reads the
        sentence, and it was the sentence that was false."""
        entry, real = self._skip_entry("2c6d960d0990f2bf")
        assert "2c6d960d0990f2bf" in entry["reason"]
        assert real in entry["reason"]

    def test_it_does_not_assert_a_cause_it_has_not_established(self):
        entry, _real = self._skip_entry("2c6d960d0990f2bf")
        assert "may have changed" in entry["reason"], \
            "the device changing is offered as a possibility, not stated"
        assert not entry["reason"].startswith("the device configuration changed")

    def test_a_trailing_newline_alone_produces_it(self):
        """The shape a copied value has. It is indistinguishable from a real
        change in the old message, and obvious in the new one."""
        import hashlib

        real = hashlib.sha256(self.CAPTURE.encode("utf-8")).hexdigest()[:16]
        entry, _ = self._skip_entry(real + "\n")
        assert entry["confirmed_hash"] == real + "\n"
        assert entry["current_hash"] == real

    def test_the_matching_case_still_deploys(self):
        """**The floor.** A guard that refused everything would satisfy every
        assertion above."""
        import hashlib

        from modules.nsot.deploy import plan_batch
        from modules.nsot.render_artifact import build_artifact

        artifact = build_artifact("r6", self.CAPTURE, "cisco_iosxe",
                                  template_approved=True)
        real = hashlib.sha256(self.CAPTURE.encode("utf-8")).hexdigest()[:16]
        plan = plan_batch([artifact], {"r6": real}, {"r6": self.CAPTURE})
        assert plan["skipped"] == []
        assert len(plan["to_deploy"]) == 1


class TestOnlyOneConditionProducesThisOutcome:
    """Asked directly: is `skipped_drifted` reused for a second condition, so
    that its reason text is attached to the wrong one?

    **No.** One producer. The command-fingerprint mismatch in `/deploy/apply`
    produces `outcome: "refused"` with its own reason and `continue`s, so the
    device never reaches `plan_batch` and cannot appear as drifted.
    """

    def test_exactly_one_site_produces_it(self):
        import ast
        import os

        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        sites = []
        for rel in ("modules/nsot/deploy.py", "routes/deploy.py",
                    "modules/pipeline.py"):
            tree = ast.parse(open(os.path.join(root, rel), encoding="utf-8").read())
            for node in ast.walk(tree):
                if isinstance(node, ast.Name) and node.id == "SKIPPED_DRIFTED":
                    sites.append(f"{rel}:{node.lineno}")
                if (isinstance(node, ast.Constant)
                        and node.value == "skipped_drifted"):
                    sites.append(f"{rel}:{node.lineno} (literal)")
        producers = [s for s in sites if "(literal)" not in s]
        assert len(producers) == 2, (
            f"expected the definition and one use, found {producers}")

    def test_a_command_hash_mismatch_is_refused_not_drifted(self):
        """So a stale `command_hash` can never surface wearing this name."""
        import inspect

        import routes.deploy as rd

        source = inspect.getsource(rd.apply)
        block = source[source.index("if now != expected:"):]
        # The whole block, not a slice of it: the first version read
        # `block[:400]` and broke when a comment was added above the append,
        # which is a test asserting a byte offset rather than a property.
        assert '"outcome": "refused"' in block
        assert "SKIPPED_DRIFTED" not in block
        assert "continue" in block, "the device must not fall through to plan_batch"


class TestTheCommandFingerprintRefusalSaysWhatMoved:
    """**The first refusal a user sees is new behaviour on a path that used to
    work**, because the wizard never sent `command_hashes`. So the message has
    to explain what changed rather than only that something did — and it can,
    because the capture hash is already in hand and separates the two causes
    at no cost.
    """

    CAPTURE = ("hostname r6\n"
               "interface GigabitEthernet2\n"
               " ip address 10.255.0.32 255.255.255.0\n"
               "end\n")

    @pytest.fixture
    def client(self, monkeypatch):
        import app as nmas
        import routes.deploy as rd
        from modules.nsot.render_artifact import build_artifact

        def _fake(list_name, hostname, cache=None):
            artifact = build_artifact(hostname, self.CAPTURE, "cisco_iosxe",
                                      template_approved=True)
            return (artifact, self.CAPTURE, {"hostname": hostname,
                                             "ip": "203.0.113.32"}), ""

        monkeypatch.setattr(rd, "_artifact_for", _fake)
        nmas.app.config["TESTING"] = False
        return nmas.app.test_client()

    def _plan(self, client):
        return client.post("/deploy/plan",
                           json={"devices": ["r6"]}).get_json()["devices"][0]

    def test_the_matching_pair_deploys(self, client):
        """**The floor.** Sending both hashes must not refuse a plan that has
        not moved — otherwise this fix makes every deploy impossible."""
        device = self._plan(client)
        result = client.post("/deploy/apply", json={
            "confirmations": {"r6": device["capture_hash"]},
            "command_hashes": {"r6": device["command_hash"]}}).get_json()
        assert "r6" in result.get("deployed", []), result.get("refused")

    def test_a_stale_command_hash_is_refused_with_both_operands(self, client):
        device = self._plan(client)
        result = client.post("/deploy/apply", json={
            "confirmations": {"r6": device["capture_hash"]},
            "command_hashes": {"r6": "deadbeefdeadbeef"}}).get_json()
        refused = result.get("refused") or []
        assert refused and refused[0]["device"] == "r6"
        entry = refused[0]
        assert entry["confirmed_hash"] == "deadbeefdeadbeef"
        assert entry["current_hash"] == device["command_hash"]
        assert "deadbeefdeadbeef" in entry["reason"]

    def test_an_unchanged_capture_attributes_the_move_to_intent(self, client):
        """The capture is byte-identical, so the difference is in the intent
        or the template — and saying so is one place to look instead of two."""
        device = self._plan(client)
        result = client.post("/deploy/apply", json={
            "confirmations": {"r6": device["capture_hash"]},
            "command_hashes": {"r6": "deadbeefdeadbeef"}}).get_json()
        entry = (result.get("refused") or [])[0]
        assert entry["moved"] == "intent_or_template"
        assert "captured config is unchanged" in entry["reason"]

    def test_a_moved_capture_is_attributed_to_the_device(self, client):
        device = self._plan(client)
        result = client.post("/deploy/apply", json={
            "confirmations": {"r6": "0" * 16},
            "command_hashes": {"r6": "deadbeefdeadbeef"}}).get_json()
        entry = (result.get("refused") or [])[0]
        assert entry["moved"] == "capture"
        assert "captured config has changed" in entry["reason"]
        assert entry["capture_confirmed"] == "0" * 16

    def test_the_refusal_says_nothing_was_sent(self, client):
        """New behaviour on a path that used to succeed reads as a malfunction
        unless it says what it did."""
        device = self._plan(client)
        result = client.post("/deploy/apply", json={
            "confirmations": {"r6": device["capture_hash"]},
            "command_hashes": {"r6": "deadbeefdeadbeef"}}).get_json()
        reason = (result.get("refused") or [])[0]["reason"]
        assert "Nothing was sent" in reason
        assert "what you confirm is what is sent" in reason.lower()


dukpy = pytest.importorskip("dukpy")


class TestTheSpecificReasonReachesTheSCREEN:
    """The payload carrying it is not the question — *"computed, carried to
    the browser, drawn nowhere"* has been the shape four times in this
    project, so the renderer is executed against the real payload.

    Refusals are built **outside** `run_batch()` and folded into the report
    afterwards, which is exactly the join where a row can be carried and not
    drawn.
    """

    CAPTURE = ("hostname r1\ninterface GigabitEthernet2\n"
               " ip address 10.255.0.32 255.255.255.0\nend\n")

    @pytest.fixture
    def report(self, monkeypatch):
        import app as nmas
        import routes.deploy as rd
        from modules.nsot.render_artifact import build_artifact

        monkeypatch.setattr(rd, "_artifact_for", lambda l, h, c=None: (
            (build_artifact(h, self.CAPTURE, "cisco_iosxe",
                            template_approved=True),
             self.CAPTURE, {"hostname": h, "ip": "203.0.113.1"}), ""))
        nmas.app.config["TESTING"] = False
        client = nmas.app.test_client()
        device = client.post("/deploy/plan",
                             json={"devices": ["r1"]}).get_json()["devices"][0]
        return client.post("/deploy/apply", json={
            "confirmations": {"r1": device["capture_hash"]},
            "command_hashes": {"r1": "deadbeefdeadbeef"}}).get_json()

    @staticmethod
    def _render(report):
        import json as _json

        from tests.js_source import read_shipped

        source = read_shipped(
            "static/js/gen/partials__deploy_wizard.1.js")

        def _lift(name):
            start = source.index(f"function {name}(")
            depth, i, seen = 0, source.index("{", start), False
            while i < len(source):
                if source[i] == "{":
                    depth += 1
                    seen = True
                elif source[i] == "}":
                    depth -= 1
                    if seen and depth == 0:
                        break
                i += 1
            return source[start:i + 1]

        # `_dEsc` too: the renderer escapes every field through it, so a
        # harness that lifts only the renderer tests a function that cannot
        # run. The shipped escaper is also the thing that would silently
        # mangle a message, so it belongs in the execution rather than stubbed.
        fn = _lift("_dEsc") + "\n" + _lift("_renderDeployResult")
        # A stub DOM: duktape has no document, and the renderer writes into one.
        stub = """
        var __html = '';
        var __els = {};
        function __el(id) { return {
          set innerHTML(v) { __html += v; }, get innerHTML() { return __html; },
          classList: { add: function () {} }, textContent: '' }; }
        var document = { getElementById: function (id) {
          if (!__els[id]) __els[id] = __el(id); return __els[id]; } };
        function showToast() {}
        var _OUTCOME_STYLE = {};
        """
        return dukpy.evaljs(
            stub + fn + f"\n_renderDeployResult({_json.dumps(report)});\n__html;")

    def test_the_reason_is_drawn(self, report):
        html = self._render(report)
        assert "the exact command list changed since you confirmed it" in html

    def test_it_names_WHICH_SIDE_MOVED_on_screen(self, report):
        """The point of the message design. The generic form makes the reader
        check both; this leaves one place to look."""
        html = self._render(report)
        assert "captured config is unchanged" in html
        assert "intent or the template" in html

    def test_it_says_nothing_was_sent(self, report):
        assert "Nothing was sent" in self._render(report)

    def test_the_device_appears_in_the_table(self, report):
        assert "r1" in self._render(report)


class TestTheFooterCountMatchesTheRows:
    """`report.total` is printed as *"N device(s) accounted for. Every device
    in a batch appears here."* — a sentence claiming **completeness**.

    Refusals are built outside `run_batch()`, which computed `total` from the
    batch they never entered. Measured: one refusal rendered as **"0 device(s)
    accounted for"** beside a row for that device. Not a stale number — a
    false statement of coverage, in the one place this project's reports
    promise it.
    """

    CAPTURE = TestTheSpecificReasonReachesTheSCREEN.CAPTURE

    @pytest.fixture
    def report(self, monkeypatch):
        return TestTheSpecificReasonReachesTheSCREEN.report.__wrapped__(
            TestTheSpecificReasonReachesTheSCREEN(), monkeypatch)

    def test_total_equals_the_number_of_results(self, report):
        assert report["total"] == len(report["results"])

    def test_by_outcome_covers_every_result(self, report):
        counted = sum(len(v) for v in report["by_outcome"].values())
        assert counted == len(report["results"])

    def test_the_refusal_is_in_by_outcome(self, report):
        assert report["by_outcome"].get("refused") == ["r1"]

    def test_both_merge_sites_use_one_helper(self):
        """The restore path folded refusals the same way and had the same
        disagreement. Two copies of a fold is how they come to differ."""
        import inspect

        import routes.deploy as rd

        source = inspect.getsource(rd)
        assert source.count('setdefault("results", []).extend(refused)') == 1, \
            "a second hand-rolled merge has appeared"
        assert source.count("_merge_refusals(report, refused)") == 2
