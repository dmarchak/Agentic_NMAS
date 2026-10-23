"""C1225: every v2 confirm control is drawn from its REAL preview, and is not pressable when that
preview is blocked (C1148's shape, held for the whole population at once).

C1148: v2's Add device… review never drew its Create button (the template read a key its
producer did not set), and no test saw it, because the test asserted the form's action, not the
button. The survey that found C1225 (Lab 7, cat4_buttons) found ten more confirms whose label no
test saw drawn from a real preview, and 26 with no test that the button is absent when the
preview is blocked. Rather than ten more tests one by one, this constrains the class:

THE POPULATION, by property, parsed from templates/v2/*.html (`population`): a `<button>` that
- carries `gate('confirm')` or `gate('approve')` (`preview_confirm.control_gate`); or
- carries `gate('configure')` inside a `<form>` that carries a preview's binding (a hidden
  `fingerprint` or `seen`); or
- posts from Alpine (`x-on:click`) inside an `x-data` element carrying a preview-bound body
  (`data-hash` or `data-body`).
Its floor is 51 sites (52 controls: `_netbox_job.html` draws Import and Remove at one site), and a
planted template it must find.

EACH SITE has a case in a class below (or is on EXCUSED, which only shrinks): the card is drawn
from its REAL producer through the REAL route with the test client, on the fixtures the per-card
tests use (imported into the class, so each class has its own `lab`), and the button's label is
asserted drawn on a button a person can press (not `disabled`); then the same card is drawn from a
BLOCKED preview, and the label is asserted not pressable. Each case says which block it draws:
`data` (the preview itself refuses: a reason not given, nothing to send, a gate failing) or
`viewer` (a verified service, not a person: `may` refuses, as `route_gates` would at confirm).
"""

import html as html_mod
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V2 = os.path.join(ROOT, "templates", "v2")

# ── the population ──────────────────────────────────────────────────────────

_TAG = r"(?:[^>{]|\{\{.*?\}\}|\{%.*?%\})*>"
_BUTTON = re.compile(r"<button\b" + _TAG, re.S)


def _open_at(text, pos, open_re, close):
    """The start of the innermost element matching *open_re* still open at *pos*."""
    stack = []
    for m in re.finditer(open_re + "|" + re.escape(close), text[:pos]):
        if m.group(0) == close:
            if stack:
                stack.pop()
        else:
            stack.append(m.start())
    return stack[-1] if stack else None


def _label_source(inner):
    """A button's label as its template writes it: the op-idle span's content up to its first
    `</span>`, else the button's text."""
    idle = re.search(r'<span class="op-idle">(.*?)</span>', inner, re.S)
    return re.sub(r"\s+", " ", (idle.group(1) if idle else re.sub(r"<[^>]+>", "", inner))).strip()


def controls(name, text):
    """``[(template, label source, kind)]``: the confirm controls of one template's *text*."""
    out = []
    for m in _BUTTON.finditer(text):
        tag = m.group(0)
        inner = text[m.end():text.index("</button>", m.end())]
        kind = None
        if "gate('confirm')" in tag or "gate('approve')" in tag:
            kind = "confirm"
        elif "gate('configure')" in tag:
            f = _open_at(text, m.start(), r"<form\b", "</form>")
            if f is not None and re.search(r'name="(fingerprint|seen)"',
                                           text[f:text.index("</form>", m.end())]):
                kind = "configure, bound to its preview"
        elif "x-on:click" in tag:
            owner = None
            for x in re.finditer(r"<\w+\b[^>]*?x-data=", text[:m.start()]):
                owner = x
            if owner is not None:
                start = re.match(r"<\w+\b" + _TAG, text[owner.start():], re.S).group(0)
                if "data-hash=" in start or "data-body=" in start:
                    kind = "Alpine, posting a preview-bound body"
        if kind:
            out.append((name, _label_source(inner), kind))
    return out


def population():
    out = []
    for name in sorted(os.listdir(V2)):
        if name.endswith(".html"):
            with open(os.path.join(V2, name), encoding="utf-8") as fh:
                out.extend(controls(name, fh.read()))
    return out


#: Sites (51) a floor below which the scan has lost its population, not shrunk it.
FLOOR = 51


# ── reading a drawn button ──────────────────────────────────────────────────

def _buttons(html):
    """``[(start tag, label text)]`` for every button in *html*, the busy words left out."""
    out = []
    for m in re.finditer(r"<button\b[^>]*>", html):
        end = html.find("</button>", m.end())
        inner = html[m.end():end]
        inner = re.sub(r'<span class="op-busy">.*?</span>', "", inner, flags=re.S)
        text = re.sub(r"\s+", " ", html_mod.unescape(re.sub(r"<[^>]+>", "", inner))).strip()
        out.append((m.group(0), text))
    return out


def pressable(html, label):
    """A button whose label is *label* (a regex, matched whole) that a person can press."""
    return any(re.fullmatch(label, text) and not re.search(r"\sdisabled[\s>=]", tag)
               for tag, text in _buttons(html))


def drawn(html, label):
    """A button whose label is *label*, pressable or not (an Alpine control is drawn disabled
    until its own fields enable it)."""
    return any(re.fullmatch(label, text) for _tag, text in _buttons(html))


def family(source):
    """Every label a control's template can draw, as a regex: its literal words kept, each
    `{{ … }}` any text (so a blocked card's "Save 0 devices" is the same control as "Save 1
    device"). None where the source chooses between labels (`{% … %}`) or keeps too few
    literal words to name the control alone; the case's own label is checked there."""
    if "{%" in source:
        return None
    text = re.sub(r"<[^>]+>", "", source)
    parts = re.split(r"(\{\{.*?\}\})", text)
    literal = "".join(p for p in parts if not p.startswith("{{"))
    if len(re.sub(r"\W", "", literal)) < 4:
        return None
    return "".join(".*?" if p.startswith("{{") else re.escape(p) for p in parts)


SERVICE = dict(actor="service:abc.access", kind="service", service_id="abc.access",
               verified=True, outcome="ok", peer="198.51.100.7", peer_trusted=True,
               header_present=True)


def as_service(monkeypatch):
    """The viewer is a verified service, not a person: every `may` of a confirm refuses."""
    from modules import identity
    svc = identity.Identity(**SERVICE)
    monkeypatch.setattr(identity, "identify", lambda _r: svc)


def _text(r):
    return r.get_data(as_text=True)


def hosted(fixture, scope="function"):
    """*fixture* (a per-card test module's own) as a fixture of the class it is assigned in, so
    each class below has its own `lab` and the rest of that module's fixture graph, resolved in
    the class first. The fixture's own function is run (`__wrapped__`, set by functools as pytest
    wraps it), with the arguments it names; *scope* is the one its module gives it."""
    import inspect

    func = fixture.__wrapped__
    params = list(inspect.signature(func).parameters.values())
    if inspect.isgeneratorfunction(func):
        def method(self, **kw):
            yield from func(**kw)
    else:
        def method(self, **kw):
            return func(**kw)
    method.__signature__ = inspect.Signature(
        [inspect.Parameter("self", inspect.Parameter.POSITIONAL_OR_KEYWORD)] + params)
    method.__name__ = func.__name__
    return pytest.fixture(method, scope=scope)


# ── the scan ────────────────────────────────────────────────────────────────

class _Cards:
    """A class of cases. ``CASES``: ``{case: (template, label source, label regex, block)}``;
    ``drawn_<case>(request)`` returns the card drawn from the real preview, and
    ``blocked_<case>(request, monkeypatch)`` the card drawn from a blocked one (each asserts
    its own floor: the card it meant to draw is there)."""

    CASES: dict = {}
    #: ``drawn`` for an Alpine control drawn disabled until its own fields enable it.
    MATCH: dict = {}

    def test_its_confirm_is_drawn_from_its_real_preview(self, case, request):
        _tpl, _src, label, _block = self.CASES[case]
        html = getattr(self, f"drawn_{case}")(request)
        check = drawn if self.MATCH.get(case) == "drawn" else pressable
        assert check(html, label), (
            f"{case}: no button labelled {label!r} that a person can press; the buttons drawn: "
            f"{[t for _g, t in _buttons(html)]}")

    def test_no_confirm_when_its_preview_is_blocked(self, case, request, monkeypatch):
        _tpl, src, label, _block = self.CASES[case]
        html = getattr(self, f"blocked_{case}")(request, monkeypatch)
        check = drawn if self.MATCH.get(case) == "drawn" else pressable
        for want in filter(None, (label, family(src))):
            assert not check(html, want), f"{case}: a blocked preview still offers {want!r}"


def pytest_generate_tests(metafunc):
    if "case" in metafunc.fixturenames and metafunc.cls is not None:
        metafunc.parametrize("case", sorted(metafunc.cls.CASES))


# ── device cards on test_profile_apply's lab (r2's real capture and intent) ─

class TestProfileLabCards(_Cards):
    from tests import test_profile_apply as _pa, test_device_deploy_v2 as _dd
    from tests import test_device_restore_v2 as _dr, test_profile_apply_v2 as _pav
    from tests import test_coverage_deploy as _cd, test_coverage_grid as _cg
    from tests import test_coverage_reporting as _cr
    lab, deploy, history = hosted(_pa.lab), hosted(_dd.deploy), hosted(_dr.history)
    idle, ready = hosted(_pav.idle), hosted(_pav.ready)
    r6_probe_unsent, r2_snmp_down = hosted(_cd.r6_probe_unsent), hosted(_cg.r2_snmp_down)
    read = hosted(_cr.read)
    from tests import test_template_bring as _tbr, test_monitoring_profile_v2 as _mp
    from tests import test_profile_new_devices as _pn
    stale, prof, pending = hosted(_tbr.stale), hosted(_mp.prof), hosted(_pn.pending)

    @pytest.fixture
    def routed(self, pending, monkeypatch):
        """tests/test_profile_new_devices.py's `TestTheRoutes.routed`: r7 answers, its capture
        is the pending lab's own."""
        from tests.test_profile_new_devices import IP7
        monkeypatch.setattr("modules.nsot.onboard.verify_device", lambda *a, **k: {
            "answered": True, "state": "answered", "mgmt_ip": IP7})
        monkeypatch.setattr("modules.nsot.onboard.capture_config", lambda *a, **k: {
            "ok": True, "config": pending["before"], "error": ""})
        return pending

    CASES = {
        "deploy": ("_deploy.html", "Deploy {{ c.sent | length }} line(s) to {{ c.host }}",
                   r"Deploy \d+ line\(s\) to r2", "data: the dangerous line's reason not given"),
        "restore": ("_restore.html", "Re-apply {{ c.sent | length }} line(s) to {{ c.host }}",
                    r"Re-apply \d+ line\(s\) to r2",
                    "data: the dangerous line's reason not given"),
        "profile_apply": ("_apply_preview.html",
                          "{{ 'Deploy to' if scope == 'intent' else 'Apply to' }} "
                          "{{ ready | length }} device(s) in this order",
                          r"Apply to 2 device\(s\) in this order",
                          "data: no device has anything to send"),
        "coverage_deploy": ("_coverage_deploy_preview.html",
                            "Deploy to {{ ready | length }} device{{ 's' if ready | length != 1 "
                            "}}, in this order",
                            r"Deploy to 1 device, in this order", "viewer"),
        "bring": ("_template_op.html", "Commit the shipped {{ b.path }}",
                  r"Commit the shipped _common\.j2", "viewer"),
        "profile": ("_profile_op.html", "Commit the profile ({{ q.changes | length }} section"
                    "{{ '' if q.changes | length == 1 else 's' }} {{ 'changed' if q.changes | "
                    "selectattr('state', 'equalto', 'changed') | list else 'added' }})",
                    r"Commit the profile \(\d+ sections? (changed|added)\)",
                    "data: the connectors propose nothing new"),
        "verify": ("_onboard_pending.html", "Verify {{ name }}", r"Verify r7",
                   "data: r7 does not answer"),
    }

    def _verify(self, request):
        lab = request.getfixturevalue("routed")
        return _text(lab["client"].post("/v2/onboard/r7/verify/preview",
                                        data={"list_name": "Lab"}))

    def drawn_verify(self, request):
        return self._verify(request)

    def blocked_verify(self, request, monkeypatch):
        request.getfixturevalue("routed")
        monkeypatch.setattr("modules.nsot.onboard.verify_device", lambda *a, **k: {
            "answered": False, "state": "did_not_answer", "mgmt_ip": "",
            "error": "timed out", "causes": []})
        html = self._verify(request)
        assert "Not verified" in html, "floor: the refusal is drawn"
        return html

    def _bring(self, request):
        lab = request.getfixturevalue("stale")
        return _text(lab["client"].get("/v2/templates/bring?list=Lab&path=_common.j2"))

    def drawn_bring(self, request):
        return self._bring(request)

    def blocked_bring(self, request, monkeypatch):
        request.getfixturevalue("stale")
        as_service(monkeypatch)
        html = self._bring(request)
        assert "Bring in the shipped" in html and "Nothing can be committed from here" in html, \
            "floor: the bring preview is drawn, refusing"
        return html

    def _profile(self, request):
        from tests.test_monitoring_profile_v2 import _get
        return _get(request.getfixturevalue("prof"), "/v2/monitoring/profile/propose")[1]

    def drawn_profile(self, request):
        return self._profile(request)

    def blocked_profile(self, request, monkeypatch):
        """Proposed and committed once, the same proposal again changes nothing."""
        from tests.test_monitoring_profile_v2 import _hidden
        prof = request.getfixturevalue("prof")
        first = self._profile(request)
        assert prof["client"].post("/v2/monitoring/profile/propose", data={
            "list": "Lab", "hash": _hidden(first, "hash")}).status_code == 200
        html = self._profile(request)
        assert "Propose the profile from the connectors" in html, "floor: the proposal is drawn"
        return html

    def drawn_deploy(self, request):
        lab = request.getfixturevalue("deploy")
        return _text(lab["client"].get("/v2/device/r2/deploy?back=overview"
                                       "&dz::0=the link is being retired"))

    def blocked_deploy(self, request, monkeypatch):
        lab = request.getfixturevalue("deploy")
        html = _text(lab["client"].get("/v2/device/r2/deploy?back=overview"))
        assert 'name="dz::0"' in html, "floor: the card waits on the reason"
        return html

    def drawn_restore(self, request):
        lab = request.getfixturevalue("history")
        return _text(lab["client"].get(f"/v2/device/r2/restore/preview?moment={lab['middle']}"
                                       "&dz::0=the port is unused"))

    def blocked_restore(self, request, monkeypatch):
        lab = request.getfixturevalue("history")
        html = _text(lab["client"].get(
            f"/v2/device/r2/restore/preview?moment={lab['middle']}"))
        assert 'name="dz::0"' in html, "floor: the card waits on the reason"
        return html

    def drawn_profile_apply(self, request):
        lab = request.getfixturevalue("ready")
        return _text(lab["client"].get("/v2/monitoring/apply?list=Lab&device=r6&device=r2"))

    def blocked_profile_apply(self, request, monkeypatch):
        lab = request.getfixturevalue("idle")
        html = _text(lab["client"].get("/v2/monitoring/apply?list=Lab&device=r2"))
        assert 'id="apply-nothing"' in html, "floor: r2 is drawn with nothing to send"
        return html

    def _coverage(self, request, monkeypatch):
        from tests.test_coverage_deploy import _page
        lab = request.getfixturevalue("lab")
        request.getfixturevalue("r6_probe_unsent")
        report = request.getfixturevalue("r2_snmp_down")
        _r, html = _page(lab, monkeypatch, report)
        return html

    def drawn_coverage_deploy(self, request):
        return self._coverage(request, request.getfixturevalue("monkeypatch"))

    def blocked_coverage_deploy(self, request, monkeypatch):
        as_service(monkeypatch)
        html = self._coverage(request, monkeypatch)
        assert 'id="apply-r6"' in html, "floor: r6's program is drawn"
        return html


# ── device cards on test_device_capture_v2's lab (r2 captured, read by a fake) ─

class TestCaptureLabCards(_Cards):
    from tests import test_device_capture_v2 as _dc
    lab = hosted(_dc.lab)

    CASES = {
        "capture": ("_capture.html", "Record {{ c.host }}'s golden", r"Record r2's golden",
                    "viewer"),
        "reload": ("_reload.html", "Reload {{ c.host }} (up to {{ (p.bound_s / 60) | "
                   "round(0, 'ceil') | int }} minutes out)",
                   r"Reload r2 \(up to \d+ minutes out\)",
                   "data: startup differs from running (unsaved changes)"),
        "reapply": ("reapply.html", "Re-apply to {{ counts.ready }} device(s)",
                    r"Re-apply to 2 device\(s\)", "data: no device in the plan can go"),
        "adopt": ("_adopt.html", "Adopt {{ f.hostname }}", r"Adopt r9", "viewer"),
    }

    def _adopt(self, request, monkeypatch):
        """test_adopt_v2's preview: `adopt.plan` answered as it answers (its `_plan`)."""
        from modules.nsot import adopt
        from tests.test_adopt_v2 import FORM, _plan
        lab = request.getfixturevalue("lab")
        monkeypatch.setattr(adopt, "plan", lambda *a, **k: _plan())
        return lab, FORM

    def drawn_adopt(self, request):
        lab, form = self._adopt(request, request.getfixturevalue("monkeypatch"))
        return _text(lab["client"].post("/v2/adopt/preview", data=form))

    def blocked_adopt(self, request, monkeypatch):
        lab, form = self._adopt(request, monkeypatch)
        as_service(monkeypatch)
        html = _text(lab["client"].post("/v2/adopt/preview", data=form))
        assert "Saving makes 1 running line" in html, "floor: the plan is drawn"
        return html

    def _moved(self, request):
        """test_device_capture_v2's preview: r2 runs a line its golden lacks."""
        from tests.test_intent_match import _broken
        lab = request.getfixturevalue("lab")
        lab["running"]["r2"] = _broken(lab["captured"])
        return lab

    def drawn_capture(self, request):
        from tests.test_device_capture_v2 import _preview_card
        return _preview_card(self._moved(request))

    def blocked_capture(self, request, monkeypatch):
        from tests.test_device_capture_v2 import _preview_card
        lab = self._moved(request)
        as_service(monkeypatch)
        html = _preview_card(lab)
        assert "Capture r2 as its golden" in html, "floor: the preview is drawn"
        return html

    def _reload(self, request, monkeypatch, **reads):
        from modules.nsot import blast_radius, capture_job, reload_op
        from tests.test_reload_v2 import _reads
        lab = request.getfixturevalue("lab")
        monkeypatch.setattr(reload_op, "read_device", lambda d: _reads(lab, **reads))
        monkeypatch.setattr(blast_radius, "for_device", lambda repo, host: {
            "state": "known", "cut": ["s1", "s2"], "attached": [], "why": blast_radius.CAVEAT})
        html = _text(lab["client"].post("/v2/device/r2/reload/start", data={"list": "Lab"}))
        job = re.search(r"/reload/job/([0-9a-f]+)", html).group(1)
        assert capture_job.wait(job, 30)
        return _text(lab["client"].get(f"/v2/device/r2/reload/job/{job}"))

    def drawn_reload(self, request):
        return self._reload(request, request.getfixturevalue("monkeypatch"))

    def blocked_reload(self, request, monkeypatch):
        lab = request.getfixturevalue("lab")
        html = self._reload(request, monkeypatch,
                            startup=lab["captured"].replace("hostname r2", "hostname r2-old"))
        assert "Persist" in html, "floor: the unsaved-changes gate fails, naming Persist"
        return html

    def _reapply(self, request, monkeypatch, plan):
        import json
        from tests.test_reapply_v2 import TAG
        lab = request.getfixturevalue("lab")
        monkeypatch.setattr("routes.golden.restore_plan",
                            lambda *a, **k: json.loads(json.dumps(plan)))
        return _text(lab["client"].get(f"/v2/history/reapply?list=Lab&tag={TAG}"))

    def drawn_reapply(self, request):
        from tests.test_reapply_v2 import PLAN
        return self._reapply(request, request.getfixturevalue("monkeypatch"), PLAN)

    def blocked_reapply(self, request, monkeypatch):
        from tests.test_reapply_v2 import PLAN
        plan = dict(PLAN, devices=[d for d in PLAN["devices"]
                                   if d["device"] in ("r3", "r5")])
        html = self._reapply(request, monkeypatch, plan)
        assert "blocked: nothing is sent <strong>2</strong>" in html, "floor: both drawn blocked"
        return html


# ── device cards on test_persist_screen's lab (r2, its account and session faked) ─

class TestPersistLabCards(_Cards):
    from tests import test_persist_screen as _ps, test_rekey_v2 as _rk
    from tests import test_device_rotate_v2 as _rt
    lab, keys, world, rot = hosted(_ps.lab), hosted(_rk.keys), hosted(_rk.world), hosted(_rt.rot)

    CASES = {
        "persist": ("_persist.html", "{{ c.button or ('Save and read back ' ~ c.host) }}",
                    r"Save and read back r2", "viewer"),
        "rekey": ("_rekey.html", "{{ c.button or ('Keep the new key for ' ~ c.host) }}",
                  r"Keep the new key for r2", "viewer"),
        "rotate": ("_rotate.html", "{{ c.button or ('Rotate ' ~ c.host) }}", r"Rotate r2",
                   "viewer"),
    }

    def drawn_persist(self, request):
        from tests.test_device_persist_v2 import _card
        return _card(request.getfixturevalue("lab"))

    def blocked_persist(self, request, monkeypatch):
        from tests.test_device_persist_v2 import _card
        lab = request.getfixturevalue("lab")
        as_service(monkeypatch)
        html = _card(lab)
        assert "Persist r2" in html, "floor: the preview is drawn"
        return html

    def drawn_rekey(self, request):
        from tests.test_rekey_v2 import _card
        return _card(request.getfixturevalue("world"))

    def blocked_rekey(self, request, monkeypatch):
        from tests.test_rekey_v2 import _card
        world = request.getfixturevalue("world")
        as_service(monkeypatch)
        html = _card(world)
        assert "What will not happen" in html, "floor: the preview is drawn"
        return html

    def drawn_rotate(self, request):
        from tests.test_device_rotate_v2 import _preview
        return _preview(request.getfixturevalue("rot"))

    def blocked_rotate(self, request, monkeypatch):
        from tests.test_device_rotate_v2 import _preview
        rot = request.getfixturevalue("rot")
        as_service(monkeypatch)
        html = _preview(rot)
        assert "Rotate r2's credential" in html, "floor: the preview is drawn"
        return html


# ── Seed intent, on test_device_seed_v2's lab ───────────────────────────────

class TestSeedLabCards(_Cards):
    from tests import test_device_seed_v2 as _ds
    lab = hosted(_ds.lab)

    CASES = {
        "seed": ("_seed.html", "{{ c.button or ('Seed ' ~ c.host ~ \"'s intent\") }}",
                 r"Seed r2's intent", "data: r2 already has full intent"),
    }

    def drawn_seed(self, request):
        return _text(request.getfixturevalue("lab")["client"].get("/v2/device/r2/seed"))

    def blocked_seed(self, request, monkeypatch):
        from tests.test_device_seed_v2 import _vals
        lab = request.getfixturevalue("lab")
        card = _text(lab["client"].get("/v2/device/r2/seed"))
        assert lab["client"].post("/v2/device/r2/seed/confirm",
                                  data=_vals(card)).status_code == 200
        html = _text(lab["client"].get("/v2/device/r2/seed"))
        assert "Not available: no full intent to replace" in html, "floor: the refusal is drawn"
        return html


# ── Retire, on test_retire_screen's world (r5 in the list 'Lab') ────────────

class TestRetireCards(_Cards):
    from tests import test_retire as _rt, test_retire_screen as _rs
    from tests import test_device_retire_v2 as _dr
    world, screen = hosted(_rt.world), hosted(_rs.screen)
    page, exported = hosted(_dr.page), hosted(_dr.exported)

    CASES = {
        "retire": ("_retire.html", "{{ c.button or ('Retire ' ~ c.host) }}", r"Retire r5",
                   "data: the break-glass record does not hold r5 yet"),
    }

    def drawn_retire(self, request):
        from tests.test_device_retire_v2 import _card
        return _card(request.getfixturevalue("exported"))[1]

    def blocked_retire(self, request, monkeypatch):
        from tests.test_device_retire_v2 import _card
        html = _card(request.getfixturevalue("page"))[1]
        assert "Refused until the break-glass record holds r5" in html, "floor: the refusal"
        return html


# ── Revert and Retry, on test_intent_ops's lab (r2 with a rolled-back change) ─

class TestRollbackCards(_Cards):
    from tests import test_intent_ops as _io, test_device_revert_retry_v2 as _rr
    lab, classify = hosted(_io.lab), hosted(_io.classify)
    page, blocked = hosted(_rr.page), hosted(_rr.blocked)

    CASES = {
        "revert": ("_revert.html", "{{ c.button or ('Revert ' ~ c.chosen ~ ' on ' ~ c.host) }}",
                   r"Revert \w+ on r2", "viewer"),
        "retry": ("_retry.html", "{{ c.button or ('Authorise the retry on ' ~ c.host) }}",
                  r"Authorise the retry on r2", "data: no reason given"),
    }

    def drawn_revert(self, request):
        return _text(request.getfixturevalue("blocked")["client"].get("/v2/device/r2/revert"))

    def blocked_revert(self, request, monkeypatch):
        lab = request.getfixturevalue("blocked")
        as_service(monkeypatch)
        html = _text(lab["client"].get("/v2/device/r2/revert"))
        assert "Revert a change to r2" in html, "floor: the preview is drawn"
        return html

    def drawn_retry(self, request):
        return _text(request.getfixturevalue("blocked")["client"].get(
            "/v2/device/r2/retry?reason=the link was down for maintenance"))

    def blocked_retry(self, request, monkeypatch):
        html = _text(request.getfixturevalue("blocked")["client"].get("/v2/device/r2/retry"))
        assert "waits on your reason" in html, "floor: the card waits on its reason"
        return html


# ── Run a privileged command, on test_privileged's t2 (r3's session faked) ──

class TestPrivilegedCards(_Cards):
    from tests import test_device_v2 as _dv, test_privileged as _pr
    lab, t2 = hosted(_dv.lab), hosted(_pr.t2)

    CASES = {
        "undebug_anyway": ("_privileged.html", "Run undebug all anyway (records it)",
                           r"Run undebug all anyway \(records it\)", "viewer"),
        "run": ("_privileged.html", "Run <span class=\"mono\">{{ p.command }}",
                r"Run clear counters GigabitEthernet2 on r3", "viewer"),
    }

    def _card(self, request, key, arg, viewer=None):
        """test_privileged's preview: the route's preview, its read job, then the card (drawn
        for a service, *viewer*'s monkeypatch given: a preview is a person's to start)."""
        from modules.nsot import capture_job
        from tests.test_privileged import COUNTERS_BEFORE, OPS, _cap
        t2 = request.getfixturevalue("t2")
        s = t2["session"]
        s.reads["show interfaces GigabitEthernet2"] = [COUNTERS_BEFORE, COUNTERS_BEFORE]
        s.reads["show debugging"] = _cap(OPS, "r2__show_debugging.txt")
        html = _text(t2["client"].post("/v2/device/r3/privileged/preview",
                                       data={"list": "Lab", "key": key, "arg": arg},
                                       headers={"HX-Request": "true"}))
        job = re.search(r"job=([0-9a-f]{32})", html)
        run = re.search(r"(?:run=|name=\"run\" value=\")([0-9TZ]+-[0-9a-f]{32})", html).group(1)
        if job:
            assert capture_job.wait(job.group(1), 30)
        if viewer is not None:
            as_service(viewer)
        return _text(t2["client"].get(f"/v2/device/r3/privileged?list=Lab&key={key}&arg={arg}"
                                      f"&run={run}"))

    def drawn_undebug_anyway(self, request):
        return self._card(request, "undebug-all", "")

    def blocked_undebug_anyway(self, request, monkeypatch):
        html = self._card(request, "undebug-all", "", viewer=monkeypatch)
        assert 'name="hash"' in html, "floor: the confirm form is drawn"
        return html

    def drawn_run(self, request):
        return self._card(request, "clear-counters", "GigabitEthernet2")

    def blocked_run(self, request, monkeypatch):
        html = self._card(request, "clear-counters", "GigabitEthernet2", viewer=monkeypatch)
        assert 'name="hash"' in html, "floor: the confirm form is drawn"
        return html


# ── Templates, on test_approvals_record's lab (s1, s2, s3 through cisco_ios/base.j2) ─

class TestTemplateCards(_Cards):
    from tests import test_approvals_record as _ar, test_templates_v2 as _tv
    from tests import test_template_bindings_v2 as _tb
    lab, tl, alt = hosted(_ar.lab), hosted(_tv.tl), hosted(_tb.alt)

    CASES = {
        "approve": ("_template_op.html", "Approve {{ c.template }}",
                    r"Approve cisco_ios/base\.j2", "data: s1's unmodelled line not acknowledged"),
        "revoke": ("_template_op.html", "Revoke the approval", r"Revoke the approval",
                   "viewer"),
        "edit": ("_template_edit.html", "Commit {{ c.path }}", r"Commit cisco_ios/base\.j2",
                 "viewer"),
        "bindings": ("_template_bindings.html", "Commit the bindings", r"Commit the bindings",
                     "viewer"),
    }

    def _approve_card(self, request):
        from tests.test_templates_v2 import _check
        return _check(request.getfixturevalue("tl"))[1]

    def drawn_approve(self, request):
        from tests.test_templates_v2 import _ack_s1
        _ack_s1(request.getfixturevalue("tl"))
        return self._approve_card(request)

    def blocked_approve(self, request, monkeypatch):
        html = self._approve_card(request)
        assert "quantum-tunnel profile ALPHA" in html and "Not available" in html, \
            "floor: the check names the line and refuses"
        return html

    def _approved(self, request):
        """tests/test_templates_v2.py's `TestRevoke._approved`: acknowledged, then approved
        through the route."""
        from tests.test_templates_v2 import REL, _ack_s1, _check, _hidden
        tl = request.getfixturevalue("tl")
        _ack_s1(tl)
        _r, card = _check(tl)
        assert tl["client"].post("/v2/templates/approve", data={
            "list": "Lab", "path": REL, "fingerprint": _hidden(card, "fingerprint"),
            "seen": _hidden(card, "seen")}).status_code == 200
        return tl

    def drawn_revoke(self, request):
        from tests.test_templates_v2 import REL
        tl = self._approved(request)
        return _text(tl["client"].get(f"/v2/templates/revoke?list=Lab&path={REL}"))

    def blocked_revoke(self, request, monkeypatch):
        from tests.test_templates_v2 import REL
        tl = self._approved(request)
        as_service(monkeypatch)
        html = _text(tl["client"].get(f"/v2/templates/revoke?list=Lab&path={REL}"))
        assert 'name="reason"' in html, "floor: the revoke card is drawn"
        return html

    def drawn_edit(self, request):
        from tests.test_template_edit_v2 import _open
        return _open(request.getfixturevalue("tl"))

    def blocked_edit(self, request, monkeypatch):
        from tests.test_template_edit_v2 import _open
        tl = request.getfixturevalue("tl")
        as_service(monkeypatch)
        html = _open(tl)
        assert 'id="te-text"' in html, "floor: the editor is drawn"
        return html

    def drawn_bindings(self, request):
        from tests.test_template_bindings_v2 import ALT, _preview
        return _text(_preview(request.getfixturevalue("alt"), add_device="s2", add_template=ALT))

    def blocked_bindings(self, request, monkeypatch):
        from tests.test_template_bindings_v2 import ALT, _preview
        alt = request.getfixturevalue("alt")
        as_service(monkeypatch)
        html = _text(_preview(alt, add_device="s2", add_template=ALT))
        assert 'name="fingerprint"' in html, "floor: the preview is drawn, bound"
        return html


class TestTemplateSeedCards(_Cards):
    from tests import test_template_seed_v2 as _ts
    bare = hosted(_ts.bare)

    CASES = {
        "seed_library": ("_template_op.html", "Seed the library", r"Seed the library",
                         "viewer"),
    }

    def drawn_seed_library(self, request):
        return _text(request.getfixturevalue("bare")["client"].get(
            "/v2/templates/seed?list=Lab"))

    def blocked_seed_library(self, request, monkeypatch):
        bare = request.getfixturevalue("bare")
        as_service(monkeypatch)
        html = _text(bare["client"].get("/v2/templates/seed?list=Lab"))
        assert "Nothing can be seeded from here" in html, "floor: the refusal is drawn"
        return html


class TestIntentEditCards(_Cards):
    from tests import test_intent_editor as _ie, test_intent_editor_v2 as _iv
    world, ed = hosted(_ie.world), hosted(_iv.ed)

    CASES = {
        "intent_edit": ("_intent_edit.html", "Commit to {{ host }}'s intent",
                        r"Commit to s4's intent", "viewer"),
    }

    def drawn_intent_edit(self, request):
        return _text(request.getfixturevalue("ed")["client"].get("/v2/device/s4/intent/edit"))

    def blocked_intent_edit(self, request, monkeypatch):
        ed = request.getfixturevalue("ed")
        as_service(monkeypatch)
        html = _text(ed["client"].get("/v2/device/s4/intent/edit"))
        assert "Editing s4's intent" in html, "floor: the editor is drawn"
        return html


# ── Bulk intent, on test_bulk_intent's lab (s1, s2, r1 with logging intent) ─

class TestBulkIntentCards(_Cards):
    from tests import test_bulk_intent as _bi, test_bulk_intent_v2 as _bv
    lab, web = hosted(_bi.lab), hosted(_bv.web)

    CASES = {
        "bulk_intent": ("_bulk_intent.html", "Commit the change to {{ c.accepted }} device"
                        "{{ 's' if c.accepted != 1 }}' intent",
                        r"Commit the change to 3 devices' intent", "viewer"),
    }

    def drawn_bulk_intent(self, request):
        from tests.test_bulk_intent_v2 import _form
        web = request.getfixturevalue("web")
        return _text(web["client"].post("/v2/devices/change/preview", data=_form()))

    def blocked_bulk_intent(self, request, monkeypatch):
        from tests.test_bulk_intent_v2 import _form
        web = request.getfixturevalue("web")
        as_service(monkeypatch)
        html = _text(web["client"].post("/v2/devices/change/preview", data=_form()))
        assert 'data-keep="bi-group-1"' in html, "floor: the preview's group is drawn"
        return html


# ── Decline a section, on test_decline's lab (r2's IP SLA) ──────────────────

class TestDeclineCards(_Cards):
    from tests import test_decline as _de
    lab = hosted(_de.lab)

    CASES = {
        "decline": ("_decline.html", "{% if d.undo %}Remove the decline from {{ d.device }}'s "
                    "intent{% else %}Record the decline in {{ d.device }}'s intent{% endif %}",
                    r"Record the decline in r2's intent", "data: no reason given"),
    }

    def drawn_decline(self, request):
        from tests.test_decline import WHY, _card
        return _card(request.getfixturevalue("lab"), reason=WHY.replace(" ", "+").replace(
            ";", "%3B").replace("'", "%27"))

    def blocked_decline(self, request, monkeypatch):
        from tests.test_decline import _card
        html = _card(request.getfixturevalue("lab"))
        assert "Not ready to record" in html, "floor: the card waits on the reason"
        return html


# ── Save, on test_save_v2's lab (r2 saveable; r4 not answering; s9 no driver) ─

class TestSaveCards(_Cards):
    from tests import test_save_v2 as _sv
    lab = hosted(_sv.lab)

    CASES = {
        "save": ("_save.html", "Save {{ s.save | length }} device{{ 's' if s.save | length != 1 "
                 "}}", r"Save 1 device", "data: nothing in the selection can be saved"),
    }

    def drawn_save(self, request):
        from tests.test_save_v2 import _page
        return _page(request.getfixturevalue("lab"), "r2", "r4")

    def blocked_save(self, request, monkeypatch):
        from tests.test_save_v2 import _page
        html = _page(request.getfixturevalue("lab"), "r4", "s9")
        assert "Nothing in the selection can be saved now" in html, "floor: the refusal"
        return html


# ── Onboarding's Add device… and Abandon…, on test_onboard_v2's client ──────

class TestOnboardCards(_Cards):
    from tests import test_onboard_v2 as _ov, test_onboard_abandon as _oa
    client, person, repo = hosted(_ov.client), hosted(_ov.person), hosted(_oa.repo)

    CASES = {
        "create": ("_onboard_add.html", "Create {{ f.hostname }}", r"Create r6",
                   "data: the plan has a blocking reason"),
        "abandon": ("_onboard_pending.html", "Abandon {{ name }}", r"Abandon bp1", "viewer"),
    }

    def _create(self, request, monkeypatch, **plan):
        """test_onboard_v2's review: `build_plan` answered as it answers (its `_plan`)."""
        from modules.nsot import onboard as O
        from tests.test_onboard_v2 import FORM, _plan
        request.getfixturevalue("person")
        monkeypatch.setattr(O, "build_plan", lambda **k: _plan(**plan))
        return _text(request.getfixturevalue("client").post("/v2/onboard/preview", data=FORM))

    def drawn_create(self, request):
        return self._create(request, request.getfixturevalue("monkeypatch"))

    def blocked_create(self, request, monkeypatch):
        html = self._create(request, monkeypatch, blocking_reasons=["192.0.2.6 is in use"])
        assert "192.0.2.6 is in use" in html, "floor: the review names its blocking reason"
        return html

    def _abandon(self, request, monkeypatch):
        from tests.test_onboard_abandon import _onboard
        _onboard(request.getfixturevalue("repo"))
        monkeypatch.setattr("modules.netbox_client.remove_device_from_netbox",
                            lambda *a, **k: {"ok": True, "deleted": [], "skipped": [],
                                             "message": "dry"})
        return request.getfixturevalue("client")

    def drawn_abandon(self, request):
        client = self._abandon(request, request.getfixturevalue("monkeypatch"))
        return _text(client.post("/v2/onboard/bp1/abandon/preview",
                                 data={"list_name": "probe"}))

    def blocked_abandon(self, request, monkeypatch):
        client = self._abandon(request, monkeypatch)
        as_service(monkeypatch)
        html = _text(client.post("/v2/onboard/bp1/abandon/preview", data={"list_name": "probe"}))
        assert "intent: would remove host_vars/bp1.yml" in html, "floor: the dry run is drawn"
        return html


# ── DHCP's reservation, subnet and exclusion, on test_dhcp_v2's page and Kea as captured ─

class TestDhcpCards(_Cards):
    from tests import test_dhcp_v2 as _dv, test_dhcp_reservations as _dr
    from tests import test_dhcp_subnets as _ds
    web, kea_dir, board_b, moved = (hosted(_dv.web), hosted(_dr.kea_dir), hosted(_dv.board_b),
                                    hosted(_ds.moved))

    CASES = {
        "reservation": ("_dhcp_reserve.html", "{% if s.op == 'remove' %}Remove {{ name }}'s "
                        "reservation{% elif s.op == 'edit' %}Change {{ name }}'s reservation"
                        "{% else %}Reserve {{ s.address }} for {{ name }}{% endif %}",
                        r"Reserve 10\.10\.20\.150 for h5", "viewer"),
        "subnet": ("_dhcp_subnet.html", "{{ {'add': 'Add', 'remove': 'Remove'}.get(s.op, "
                   "'Change') }} {{ p.prefix }}", r"Change 10\.10\.10\.0/24",
                   "data: the pool is outside the subnet"),
        "exclusion": ("_dhcp_exclusion.html", "{{ 'Remove the exclusion' if s.op == 'remove' "
                      "else 'Exclude ' ~ s.range }}", r"Exclude 10\.10\.10\.120 - 10\.10\.10\.129",
                      "viewer"),
        # C1403: DHCP › Leases' Release lease…, on Kea's captured leases.
        "lease": ("_dhcp_lease.html", "Release {{ p.address }}", r"Release 10\.10\.10\.102",
                  "viewer"),
    }

    def drawn_reservation(self, request):
        from tests.test_dhcp_v2 import ADD, _card
        return _text(_card(request.getfixturevalue("board_b"), **ADD))

    def blocked_reservation(self, request, monkeypatch):
        from tests.test_dhcp_v2 import ADD, _card
        board_b = request.getfixturevalue("board_b")
        as_service(monkeypatch)
        html = _text(_card(board_b, **ADD))
        assert "Reserve an address on 10.10.20.0/24" in html, "floor: the preview is drawn"
        return html

    def _kea(self, request, monkeypatch):
        """test_dhcp_subnets' Kea after the subnet move, behind the page (as board_b puts Kea
        as captured behind it)."""
        from modules.nsot import ztp
        web = request.getfixturevalue("web")
        moved = request.getfixturevalue("moved")
        monkeypatch.setattr("modules.integrations.kea.KeaIntegration", lambda **kw: moved["kea"])
        monkeypatch.setattr(ztp, "_run_kea_test", lambda path, program="kea-dhcp4": (True, "ok"))
        return web

    def _get(self, request, monkeypatch, path, args):
        from urllib.parse import urlencode
        web = self._kea(request, monkeypatch)
        return _text(web["client"].get(f"/v2/dhcp/{path}?" + urlencode(dict(args, list="Lab"))))

    def drawn_subnet(self, request):
        from tests.test_dhcp_subnets import EDIT
        return self._get(request, request.getfixturevalue("monkeypatch"), "subnet", EDIT)

    def blocked_subnet(self, request, monkeypatch):
        from tests.test_dhcp_subnets import EDIT
        html = self._get(request, monkeypatch, "subnet",
                         dict(EDIT, pool="10.10.99.101 - 10.10.99.149"))
        assert "10.10.99.101" in html, "floor: the refused change is drawn"
        return html

    def drawn_exclusion(self, request):
        from tests.test_dhcp_exclusions import RIG
        return self._get(request, request.getfixturevalue("monkeypatch"), "exclusion", RIG)

    def blocked_exclusion(self, request, monkeypatch):
        from tests.test_dhcp_exclusions import RIG
        self._kea(request, monkeypatch)
        as_service(monkeypatch)
        html = self._get(request, monkeypatch, "exclusion", RIG)
        assert "10.10.10.120 - 10.10.10.129" in html, "floor: the preview is drawn"
        return html

    def drawn_lease(self, request):
        from tests.test_dhcp_leases import RIG
        return self._get(request, request.getfixturevalue("monkeypatch"), "lease", RIG)

    def blocked_lease(self, request, monkeypatch):
        from tests.test_dhcp_leases import RIG
        self._kea(request, monkeypatch)
        as_service(monkeypatch)
        html = self._get(request, monkeypatch, "lease", RIG)
        assert "lease 10.10.10.102 (IPv4, MAC aa:c1:ab:b0:85:65" in html, \
            "floor: the preview is drawn"
        return html


# ── Rotate due devices now…, on test_scheduled_rotation's store ─────────────

class TestRotateDueCards(_Cards):
    from tests import test_scheduled_rotation as _sr
    data, client = hosted(_sr.data), hosted(_sr.client)

    CASES = {
        "rotate_due": ("_credential_profiles.html", "Rotate {{ p.chosen | length }} device"
                       "{{ '' if p.chosen | length == 1 else 's' }}", r"Rotate 2 devices",
                       "data: inside a no-change window"),
    }

    def _card(self, request, monkeypatch, blocked):
        """test_scheduled_rotation's due devices (`_states`: r1 and r3 due under role:router's
        policy), the window declared as the test's run declares it."""
        import time
        from modules.nsot import scheduled_rotation as SR
        from tests.test_scheduled_rotation import _states
        client = request.getfixturevalue("client")
        states = _states(now=time.time())
        monkeypatch.setattr(SR, "device_states", lambda now=None, **_k: states)
        window = {"start": "22:00", "end": "23:00", "reason": "a freeze"} if blocked else None
        monkeypatch.setattr(SR, "in_no_change_window", lambda now=None: window)
        return _text(client.get("/v2/credentials/profiles/rotate-due"))

    def drawn_rotate_due(self, request):
        return self._card(request, request.getfixturevalue("monkeypatch"), False)

    def blocked_rotate_due(self, request, monkeypatch):
        html = self._card(request, monkeypatch, True)
        assert "r1" in html and "r3" in html, "floor: the due devices are drawn"
        return html


# ── NetBox's Import, Remove and Stop tracking, on test_netbox_v2's networks ─

class TestNetBoxCards(_Cards):
    from tests import test_settings_v2 as _st, test_netbox_v2 as _nv
    from tests import test_free_held_address as _fh
    networks, nb, tracked = hosted(_st.networks), hosted(_nv.nb), hosted(_nv.tracked)
    retired_v4 = hosted(_fh.retired_v4)

    CASES = {
        # C1504: Free <address> from <record>…'s own preview, its confirm Free <address>.
        "free": ("_netbox_job.html", "Free {{ job.address }}", r"Free 192\.0\.2\.9", "viewer"),
        "import": ("_netbox_job.html", "{{ 'Remove' if op == 'remove' else 'Import' }}",
                   r"Import", "viewer"),
        "remove": ("_netbox_job.html", "{{ 'Remove' if op == 'remove' else 'Import' }}",
                   r"Remove", "data: what a prefix's delete takes is not established"),
        "stop_tracking": ("_netbox_job.html", "Stop tracking", r"Stop tracking",
                          "data: Mercury's record holds nothing to forget"),
    }

    def _import(self, request):
        from tests.test_netbox_v2 import _job, _post
        networks = request.getfixturevalue("networks")
        request.getfixturevalue("nb")
        _r, card = _post(networks, "/v2/netbox/preview", {"operation": "import",
                                                          "list": "Branch"})
        return networks, _job(card)

    def drawn_import(self, request):
        networks, job = self._import(request)
        return _text(networks["client"].get(f"/v2/netbox/job/{job}"))

    def drawn_free(self, request):
        from tests.test_free_held_address import _free_card
        retired = request.getfixturevalue("retired_v4")
        return _free_card(request.getfixturevalue("networks"), retired)[2]

    def blocked_free(self, request, monkeypatch):
        from tests.test_free_held_address import _free_card
        retired = request.getfixturevalue("retired_v4")
        as_service(monkeypatch)
        html = _free_card(request.getfixturevalue("networks"), retired)[2]
        assert "clears primary_ip4, primary_ip6" in html, "floor: the free's preview is drawn"
        return html

    def blocked_import(self, request, monkeypatch):
        networks, job = self._import(request)
        as_service(monkeypatch)
        html = _text(networks["client"].get(f"/v2/netbox/job/{job}"))
        assert "create dcim/devices r9" in html, "floor: the import's preview is drawn"
        return html

    def drawn_remove(self, request):
        from tests.test_netbox_v2 import _remove_card
        request.getfixturevalue("tracked")
        return _remove_card(request.getfixturevalue("networks"))[1]

    def blocked_remove(self, request, monkeypatch):
        from modules import netbox_guard as guard
        from tests.test_netbox_v2 import _remove_card
        tracked = request.getfixturevalue("tracked")
        tag = [{"slug": guard.MANAGED_TAG_SLUG, "name": guard.MANAGED_TAG}]
        pfx = tracked["fake"].seed("ipam/prefixes", {"prefix": "192.0.2.0/24",
                                                     "name": "192.0.2.0/24", "tags": tag})
        guard.record_created("Branch", "ipam/prefixes", pfx["id"], "192.0.2.0/24")
        html = _remove_card(request.getfixturevalue("networks"))[1]
        assert "Remove is not offered" in html, "floor: the refusal names its comparison"
        return html

    def drawn_stop_tracking(self, request):
        from tests.test_netbox_v2 import _forget_card
        request.getfixturevalue("tracked")
        return _forget_card(request.getfixturevalue("networks"))[1]

    def blocked_stop_tracking(self, request, monkeypatch):
        from modules import netbox_guard as guard
        from tests.test_netbox_v2 import _forget_card
        request.getfixturevalue("tracked")
        guard.forget_created("Branch")
        html = _forget_card(request.getfixturevalue("networks"))[1]
        assert "there is nothing to forget" in html, "floor: the empty record is said"
        return html


# ── Update and Stop waiting, on test_update_when_ci_passes' store ───────────

class TestUpdateCards(_Cards):
    from tests import test_update_when_ci_passes as _uw
    store = hosted(_uw.store)

    CASES = {
        "update": ("_update.html", "Update to {{ f.target[:10] or '?' }}{{ ' when CI passes' if "
                   "p.waitable else '' }}", r"Update to b{10}",
                   "data: the checkout has local changes"),
        "stop_waiting": ("_update.html", "Stop waiting", r"Stop waiting", "viewer"),
    }

    def _panel(self, request, monkeypatch, **kw):
        """The panel with `update_op.plan` given test_update_when_ci_passes' values (`_kw`)."""
        import app as A
        from modules import update_op
        from tests.test_update_when_ci_passes import VERIFIED, _kw
        request.getfixturevalue("store")
        real = update_op.plan
        monkeypatch.setattr(update_op, "plan", lambda **_k: real(**_kw(ci=VERIFIED, **kw)))
        return _text(A.app.test_client().get("/v2/update/panel"))

    def drawn_update(self, request):
        return self._panel(request, request.getfixturevalue("monkeypatch"))

    def blocked_update(self, request, monkeypatch):
        html = self._panel(request, monkeypatch, checkout_changes=["M app.py"])
        assert 'id="update-why-not"' in html, "floor: the reason it cannot update is drawn"
        return html

    def drawn_stop_waiting(self, request):
        return self._panel(request, request.getfixturevalue("monkeypatch"))

    def blocked_stop_waiting(self, request, monkeypatch):
        as_service(monkeypatch)
        html = self._panel(request, monkeypatch)
        assert 'id="update-stop-waiting"' in html, "floor: the control is drawn (disabled)"
        return html


# ── It is done, on test_host_steps' record ──────────────────────────────────

class TestHostStepCards(_Cards):
    from tests import test_host_steps as _hs
    store = hosted(_hs.store)

    CASES = {
        "step_done": ("_update.html", "It is done", r"It is done",
                      "data: the step is one the tool checks itself"),
    }

    def _panel(self, request, monkeypatch, body):
        """test_host_steps' running release (`_log`), its After step owed."""
        import app as A
        from modules import host_steps
        from routes import health
        from tests.test_host_steps import _log
        request.getfixturevalue("store")
        text = _log(("b" * 40, body))
        monkeypatch.setattr(host_steps, "_log", lambda root, rng, limit, run=None: text)
        monkeypatch.setattr(health, "_COMMIT", "b" * 40)
        return _text(A.app.test_client().get("/v2/update/panel"))

    def drawn_step_done(self, request):
        return self._panel(request, request.getfixturevalue("monkeypatch"),
                           "x\n\nHost-Step-After: tell the team\n")

    def blocked_step_done(self, request, monkeypatch):
        from modules import host_steps
        monkeypatch.setitem(host_steps.CHECKS, "topology-renderer",
                            lambda root: {"state": "not_done", "detail": "absent"})
        html = self._panel(request, monkeypatch, "x\n\nHost-Step-After: [topology-renderer] "
                           "install the renderer as a symlink and restart it\n")
        assert 'id="update-owed-steps"' in html and "checked: absent" in html, \
            "floor: the owed step is drawn with its check's answer"
        return html


# ── Settings: a group's and a network's switch, networks, the source, platforms ─

class TestSettingsCards(_Cards):
    from tests import test_settings_v2 as _st, test_network_source_v2 as _ns
    from tests import test_installation_settings as _is
    networks, netbox = hosted(_st.networks), hosted(_ns.netbox)
    netbox_branch = hosted(_is.netbox_branch)

    CASES = {
        "group_switch": ("_settings_switch.html", "{% if p.to == 'inherit' %}Inherit Default's "
                         "{{ p.label }} for {{ list_name }}{% if p.removed %} and remove its own "
                         "{{ p.removed | length }}{% endif %}{% elif p.to == 'own' %}Save "
                         "{{ p.label }} for {{ list_name }}{% else %}Declare {{ p.label }} not "
                         "applicable{% if p.removed %} and remove its {{ p.removed | length }} "
                         "value{{ '' if p.removed | length == 1 else 's' }}{% endif %}{% endif %}",
                         r"Inherit Default's Grafana for Branch and remove its own \d+",
                         "viewer"),
        "mode_switch": ("_settings_mode.html", "{% if p.to == 'standalone' %}Make {{ list_name }} "
                        "standalone{% if p.unconfigured %}: {{ p.unconfigured | length }} group"
                        "{{ '' if p.unconfigured | length == 1 else 's' }} become{{ 's' if "
                        "p.unconfigured | length == 1 }} not configured{% endif %}{% else %}"
                        "Inherit from Default{% if p.picked %}: picks up {{ p.picked | length }} "
                        "group{{ '' if p.picked | length == 1 else 's' }}{% endif %}{% endif %}",
                        r"Make Lab-3 standalone: 2 groups become not configured", "viewer"),
        "network_create": ("_network_create.html", "Create {{ pv.name }}", r"Create Site East",
                           "data: the name is taken"),
        "network_delete": ("_network_delete.html", "Delete {{ pv.name }}", r"Delete Branch",
                           "viewer"),
        "network_source": ("_network_source.html", "Save the source", r"Save the source",
                           "viewer"),
        "platforms": ("_install_platforms_preview.html", "Save{% if e.changes %} and refresh the "
                      "NetBox lists{% endif %}", r"Save and refresh the NetBox lists", "viewer"),
    }

    def _get(self, request, path):
        return _text(request.getfixturevalue("networks")["client"].get(path))

    def _post(self, request, path, data=None):
        return _text(request.getfixturevalue("networks")["client"].post(
            path, data=data or {}, headers={"HX-Request": "true"}))

    def drawn_group_switch(self, request):
        return self._get(request, "/v2/settings/network/Branch/group/grafana/switch?to=inherit")

    def blocked_group_switch(self, request, monkeypatch):
        request.getfixturevalue("networks")
        as_service(monkeypatch)
        html = self._get(request, "/v2/settings/network/Branch/group/grafana/switch?to=inherit")
        assert "It would pick up" in html, "floor: the preview is drawn"
        return html

    def drawn_mode_switch(self, request):
        return self._get(request, "/v2/settings/network/Lab-3/mode?to=standalone")

    def blocked_mode_switch(self, request, monkeypatch):
        request.getfixturevalue("networks")
        as_service(monkeypatch)
        html = self._get(request, "/v2/settings/network/Lab-3/mode?to=standalone")
        assert 'id="settings-mode-op"' in html and "requires a person" in html, \
            "floor: the preview is drawn, refusing the viewer"
        return html

    def drawn_network_create(self, request):
        return self._post(request, "/v2/settings/networks/new/preview", {"name": "Site East"})

    def blocked_network_create(self, request, monkeypatch):
        html = self._post(request, "/v2/settings/networks/new/preview", {"name": "Branch"})
        assert "Branch" in html and 'name="fingerprint"' not in html, \
            "floor: the taken name's preview is drawn, unbound"
        return html

    def drawn_network_delete(self, request):
        return self._post(request, "/v2/settings/network/Branch/delete/preview")

    def blocked_network_delete(self, request, monkeypatch):
        request.getfixturevalue("networks")
        as_service(monkeypatch)
        html = self._post(request, "/v2/settings/network/Branch/delete/preview")
        assert 'name="fingerprint"' in html, "floor: the preview is drawn, bound"
        return html

    def drawn_network_source(self, request):
        from tests.test_network_source_v2 import TO_NETBOX
        request.getfixturevalue("netbox")
        return self._post(request, "/v2/settings/network/Branch/source/preview", TO_NETBOX)

    def blocked_network_source(self, request, monkeypatch):
        from tests.test_network_source_v2 import TO_NETBOX
        request.getfixturevalue("netbox")
        as_service(monkeypatch)
        html = self._post(request, "/v2/settings/network/Branch/source/preview", TO_NETBOX)
        assert 'name="fingerprint"' in html, "floor: the preview is drawn, bound"
        return html

    def drawn_platforms(self, request):
        from tests.test_installation_settings import _platform_form
        request.getfixturevalue("netbox_branch")
        return self._post(request, "/v2/settings/installation/platforms/preview",
                          _platform_form(driver=["cisco_ios", "cisco_ios"]))

    def blocked_platforms(self, request, monkeypatch):
        from tests.test_installation_settings import _platform_form
        request.getfixturevalue("netbox_branch")
        as_service(monkeypatch)
        html = self._post(request, "/v2/settings/installation/platforms/preview",
                          _platform_form(driver=["cisco_ios", "cisco_ios"]))
        assert "requires a person" in html, "floor: the preview is refused to a service"
        return html


# ── Records stores, on test_records_receipts' real records database ─────────

@pytest.mark.real_receipts_path   # as tests/test_records_receipts.py: the move reads every
class TestRecordsStoreCards(_Cards):   # network's file where receipts keep it, not the redirect
    from tests import test_settings_v2 as _st, test_records_receipts as _rr
    networks, pg, app_db = hosted(_st.networks), hosted(_rr.pg, "class"), hosted(_rr.app_db)

    CASES = {
        "records_stores": ("_records_stores.html", "{% if back %}Move back{% elif total %}Move "
                           "{{ total }} line{{ '' if total == 1 else 's' }}{% else %}Switch to the "
                           "database (no lines to copy){% endif %}", r"Move 6 lines", "viewer"),
    }

    def _preview(self, request):
        n = request.getfixturevalue("app_db")
        return _text(n["client"].post("/v2/settings/installation/records/stores/move/preview",
                                      headers={"HX-Request": "true"}))

    def drawn_records_stores(self, request):
        return self._preview(request)

    def blocked_records_stores(self, request, monkeypatch):
        request.getfixturevalue("app_db")
        as_service(monkeypatch)
        html = self._preview(request)
        assert "Move deploy receipts to the records database" in html, "floor: the preview"
        return html


# ── The Alpine confirms: the break-glass export, IP SLA's two, the heartbeat's ─

class TestBreakglassCards(_Cards):
    from tests import test_breakglass_export as _be, test_credentials_v2 as _cv
    lab, page = hosted(_be.lab), hosted(_cv.page)

    CASES = {
        "export": ("_breakglass_export.html", "The passphrase needs 12 characters or more",
                   r"The passphrase needs 12 characters or more", "viewer"),
    }
    #: Drawn disabled until its passphrase fields enable it (Alpine): drawn is the property.
    MATCH = {"export": "drawn"}

    def _card(self, request):
        from tests.test_breakglass_export import LIST
        return _text(request.getfixturevalue("page")["client"].get(
            f"/v2/credentials?list={LIST}&open=export"))

    def drawn_export(self, request):
        return self._card(request)

    def blocked_export(self, request, monkeypatch):
        request.getfixturevalue("page")
        as_service(monkeypatch)
        html = self._card(request)
        assert 'id="bg-export"' in html and "Not available:" in html, "floor: the refusal"
        return html


class TestIpSlaCards(_Cards):
    from tests import test_ip_sla_policy as _ip
    lab = hosted(_ip.lab)

    CASES = {
        "policy": ("ip_sla.html", "{{ 'Change the policy' if policy.words else "
                   "'Set the policy' }}", r"Set the policy",
                   "data: the network has no monitoring profile"),
        "probes": ("ip_sla.html", "Commit the ticked probes to intent, then preview sending them",
                   r"Commit the ticked probes to intent, then preview sending them",
                   "data: no policy chosen, so nothing is suggested"),
        "retunes": ("ip_sla.html", "Commit the ticked frequencies to intent, then preview "
                    "sending them",
                    r"Commit the ticked frequencies to intent, then preview sending them",
                    "data: no policy chosen, so no probe is off its frequency"),
    }

    def drawn_retunes(self, request):
        """C1491: the lab's r2 runs `ip sla 1` every 10 s; with the policy at 60 s it is
        proposed back."""
        from tests.test_ip_sla_policy import _page, _policy
        lab = request.getfixturevalue("lab")
        assert _policy(lab).status_code == 200
        return _page(lab)[1]

    def blocked_retunes(self, request, monkeypatch):
        from tests.test_ip_sla_policy import _page
        html = _page(request.getfixturevalue("lab"))[1]
        assert "Choose a policy above" in html, "floor: no policy, so nothing is proposed"
        return html

    def drawn_policy(self, request):
        from tests.test_ip_sla_policy import _page
        return _page(request.getfixturevalue("lab"))[1]

    def blocked_policy(self, request, monkeypatch):
        """The profile removed in a commit, as a network that never proposed one holds none."""
        import subprocess
        from modules.nsot.profile import PROFILE_REL
        from tests.test_ip_sla_policy import _page
        lab = request.getfixturevalue("lab")
        for args in (["rm", "-q", PROFILE_REL],
                     ["-c", "user.email=t@example.invalid", "-c", "user.name=t", "commit", "-q",
                      "-m", "profile: removed for the test"]):
            assert subprocess.run(["git", "-C", lab["repo"], *args],
                                  capture_output=True).returncode == 0
        html = _page(lab)[1]
        assert "has no monitoring profile yet" in html, "floor: the page says so"
        return html

    def drawn_probes(self, request):
        from tests.test_ip_sla_policy import _page, _policy
        lab = request.getfixturevalue("lab")
        assert _policy(lab).status_code == 200
        return _page(lab)[1]

    def blocked_probes(self, request, monkeypatch):
        from tests.test_ip_sla_policy import _page
        html = _page(request.getfixturevalue("lab"))[1]
        assert "Choose a policy above" in html, "floor: the page asks for a policy"
        return html


class TestHeartbeatCards(_Cards):
    from tests import test_heartbeat_remeasure as _hb
    lab = hosted(_hb.lab)

    CASES = {
        "heartbeat": ("heartbeat.html", "Write the ticked windows",
                      r"Write the ticked windows", "data: every window is current"),
    }

    def _page(self):
        import app as A
        return _text(A.app.test_client().get("/v2/monitoring/heartbeat"))

    def drawn_heartbeat(self, request):
        request.getfixturevalue("lab")
        return self._page()

    def blocked_heartbeat(self, request, monkeypatch):
        lab = request.getfixturevalue("lab")
        monkeypatch.setattr(lab["H"], "expected_devices", lambda: ({"s3"}, []))
        html = self._page()
        assert "nothing needs writing" in html, "floor: the page says nothing needs writing"
        return html


# ── out-of-band ZTP (O6b) on test_console_ztp_v2's world, and a console server's re-key (C1560)

class TestConsoleCards(_Cards):
    from tests import test_console_servers_v2 as _cs, test_console_ztp_v2 as _cz
    world, cs_lab = hosted(_cz.world), hosted(_cs.lab)

    CASES = {
        "survey": ("_console_ztp.html", "{{ ('Survey ' ~ (p.device or who) ~ \"'s console\") "
                   "if survey else ('Kick-start ' ~ (p.device or who)) }}",
                   r"Survey edge1's console", "viewer"),
        "kickstart": ("_console_ztp.html", "{{ ('Survey ' ~ (p.device or who) ~ \"'s console\") "
                      "if survey else ('Kick-start ' ~ (p.device or who)) }}",
                      r"Kick-start edge1", "viewer"),
        "rekey_console": ("_console_server_op.html", "Keep the new key for {{ p.host }}",
                          r"Keep the new key for 127\.0\.0\.1", "data: the host answers with "
                                                                 "the key Mercury holds"),
    }

    @staticmethod
    def _client():
        import app as A
        return A.app.test_client()

    def _survey(self, request):
        w = request.getfixturevalue("world")
        html = _text(self._client().post(
            f"/v2/onboard/console/{w.dev['id']}/survey/preview",
            data={"list_name": self._cz.LIST, "step": "survey", "profile": "cisco_ios_switch"}))
        assert 'name="hash"' in html, "floor: the survey's confirm form is drawn"
        return html

    def drawn_survey(self, request):
        return self._survey(request)

    def blocked_survey(self, request, monkeypatch):
        as_service(monkeypatch)
        return self._survey(request)

    def _kick(self, request, monkeypatch):
        from tests.test_console_session import PNP
        from tests.test_console_ztp import blank_answers
        w = request.getfixturevalue("world")
        w.survey(greeting=PNP, answers=blank_answers())
        monkeypatch.setattr("routes.console_ztp_v2._onboarded", lambda l, h: "")
        html = _text(self._client().post(
            f"/v2/onboard/console/{w.dev['id']}/kickstart/preview",
            data={"list_name": self._cz.LIST, "step": "kickstart",
                  "param_interface": "GigabitEthernet0/1", "param_vlan": "10"}))
        assert 'name="hash"' in html, "floor: the kick-start's confirm form is drawn"
        return html

    def drawn_kickstart(self, request):
        mp = pytest.MonkeyPatch()
        try:
            return self._kick(request, mp)
        finally:
            mp.undo()

    def blocked_kickstart(self, request, monkeypatch):
        as_service(monkeypatch)
        return self._kick(request, monkeypatch)

    def _rekey(self, request, monkeypatch, same: bool):
        import paramiko

        from modules import host_keys
        from modules.nsot import console_servers
        lab = request.getfixturevalue("cs_lab")
        pid = lab.ports[0]["id"]
        assert console_servers.set_port(pid, {
            "driver": "command_bridge", "host": "127.0.0.1", "ssh_port": 2222,
            "container": "edge-a", "credential_ref": "console-bridge"}, actor="t")["ok"]
        held, now = (paramiko.RSAKey.generate(1024) for _ in range(2))
        host_keys.check("127.0.0.1", held, owner="t", port=2222)
        presented = host_keys.offered(held if same else now)
        monkeypatch.setattr("modules.connection.read_host_key",
                            lambda h, port=22, owner="", timeout=None: dict(presented))
        return _text(self._client().post(
            f"/v2/settings/installation/console-servers/port/{pid}/rekey/preview"))

    def drawn_rekey_console(self, request):
        mp = pytest.MonkeyPatch()
        try:
            return self._rekey(request, mp, same=False)
        finally:
            mp.undo()

    def blocked_rekey_console(self, request, monkeypatch):
        html = self._rekey(request, monkeypatch, same=True)
        assert "answers with the key Mercury holds" in html, "floor: the preview refuses"
        return html


# ── every site of the population has its cases ──────────────────────────────

#: Sites no case above can draw from a real preview, each with why. Only shrinks (C1225:
#: empty when written; every one of the 51 sites, 52 controls, is drawn above).
EXCUSED: dict = {}
EXCUSED_CEILING = 0


def _cases():
    """``{(template, label source): [Class.case, ...]}`` from every class of cases."""
    out: dict = {}
    for cls in [v for v in globals().values()
                if isinstance(v, type) and issubclass(v, _Cards) and v is not _Cards]:
        for case, (tpl, src, _label, block) in cls.CASES.items():
            assert block.startswith(("data: ", "viewer")), (cls.__name__, case, block)
            assert callable(getattr(cls, f"drawn_{case}", None)), (cls.__name__, case)
            assert callable(getattr(cls, f"blocked_{case}", None)), (cls.__name__, case)
            out.setdefault((tpl, src), []).append(f"{cls.__name__}.{case}")
    return out


class TestThePopulation:
    def test_the_floor_holds(self):
        sites = population()
        assert len(sites) >= FLOOR, (f"{len(sites)} confirm controls found, the floor is "
                                     f"{FLOOR}: the parse lost its population")

    def test_every_site_has_its_cases_and_every_case_a_site(self):
        sites = {(tpl, src) for tpl, src, _kind in population()}
        cases = _cases()
        missing = sorted(sites - set(cases) - set(EXCUSED))
        assert not missing, ("a confirm control with no case drawing it from a real preview "
                             "(add one to a class above): " + "; ".join(
                                 f"{t}: {s!r}" for t, s in missing))
        stale = sorted(set(cases) - sites)
        assert not stale, ("a case naming a control no template draws (its label or its "
                           "template moved): " + "; ".join(f"{t}: {s!r}" for t, s in stale))
        assert not set(EXCUSED) & set(cases), "an excused site now has a case: remove it"

    def test_the_excused_list_only_shrinks(self):
        assert len(EXCUSED) <= EXCUSED_CEILING
        for key, why in EXCUSED.items():
            assert why and len(why) > 20, (key, "an excuse says why")

    def test_netbox_jobs_one_site_is_two_controls(self):
        """`_netbox_job.html` draws Import and Remove at one site, two previews, and
        `_console_ztp.html` the survey's and the kick-start's at one: 58 controls (52 until
        C1403's Release lease… joined, 53 until C1491's IP SLA frequency commit, 54 until
        C1504's Free <address> on NetBox's job card, 55 until out-of-band ZTP's survey,
        kick-start and a console server's re-key, 2026-10-22)."""
        cases = _cases()
        assert sum(len(v) for v in cases.values()) == 58, sum(len(v) for v in cases.values())

    def test_a_planted_control_of_each_kind_is_found_and_a_plain_one_is_not(self):
        planted = """
<form><input type="hidden" name="list" value="x">
<button type="submit"{{ gate('confirm') }}><span class="op-idle">Planted confirm</span></button>
</form>
<form><input type="hidden" name="fingerprint" value="{{ pv.fp }}">
<button type="submit"{{ gate('configure') }}><span class="op-idle">Planted bound</span></button>
</form>
<form><button type="submit"{{ gate('configure') }}><span class="op-idle">Unbound</span></button>
</form>
<div x-data="ipslaPost" data-url="/x"
     data-body='{{ {"fingerprint": p.fp} | tojson }}'>
  <button type="button" x-on:click="post" x-text="label">Planted Alpine</button>
</div>
<div x-data="other"><button type="button" x-on:click="go">Plain Alpine</button></div>
<button type="button" hx-get="/x">Opener…</button>
"""
        found = {src: kind for _t, src, kind in controls("planted.html", planted)}
        assert found == {"Planted confirm": "confirm",
                         "Planted bound": "configure, bound to its preview",
                         "Planted Alpine": "Alpine, posting a preview-bound body"}, found

    def test_the_label_readers_see_a_disabled_button_as_not_pressable(self):
        on = '<button type="submit" class="btn" hx-disabled-elt="this"><span class="op-idle">Go' \
             '</span><span class="op-busy">Going…</span></button>'
        off = on.replace('hx-disabled-elt="this"', 'hx-disabled-elt="this" disabled '
                         'aria-disabled="true" data-refused="Not available to you: x"')
        assert pressable(on, "Go") and not pressable(off, "Go") and drawn(off, "Go")
        assert not pressable(on, "Going…"), "the busy words are not the label"

    def test_a_family_is_every_label_its_source_can_draw(self):
        fam = family("Save {{ s.save | length }} device{{ 's' if s.save | length != 1 }}")
        assert re.fullmatch(fam, "Save 0 devices") and re.fullmatch(fam, "Save 1 device")
        assert not re.fullmatch(fam, "Save the source")
        assert family("{% if a %}Move back{% else %}Move {{ n }} lines{% endif %}") is None
        assert family("{{ c.button or ('Rotate ' ~ c.host) }}") is None
