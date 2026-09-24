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

    def test_the_apply_call_does_NOT_send_command_hashes(self):
        """**A recorded gap, pinned so it cannot change unnoticed.**

        `/deploy/apply` recomputes the command fingerprint and compares it
        *only* when `command_hashes` is supplied:

            expected = command_hashes.get(hostname)
            if expected is not None:
                ...

        The wizard sends `{confirmations}` and nothing else, so from the UI
        that comparison **never runs** — the deploy path's central claim, that
        the program is recomputed at apply and refused if anything moved, is
        not exercised by the only client that reaches it. The restore path
        (`partials__golden_repo.3.js`) does send `command_hashes`.

        Pinned rather than fixed here because changing what the wizard sends
        changes deploy behaviour, and this file's job is to record the seam.
        """
        source = self._wizard_js()
        apply_call = source[source.index("async function applyDeploy"):]
        assert "command_hashes" not in apply_call, (
            "the wizard now sends command_hashes — good, and this test should "
            "become an assertion that it does, plus one that a stale one is "
            "refused")

    def test_the_restore_path_does_send_them(self):
        """The positive anchor: the payload is not impossible to build, and
        one client already builds it."""
        from tests.js_source import read_shipped

        source = read_shipped("static/js/gen/partials__golden_repo.3.js")
        assert "command_hashes: hashes" in source
