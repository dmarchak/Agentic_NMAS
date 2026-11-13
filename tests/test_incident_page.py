"""One incident's own page, its first slice (`modules/incident_page.py`,
`routes/incident_v2.py`, `templates/v2/incident.html`; the incident page's board, parts B, C
and F; the operator's design change of 2026-11-11: "each incident gets its own page"). Through
the real app, on the heal's lab (tests/test_heal_decide.py's: the real decision, and
tests/test_heal_act.py's and tests/test_heal_propose.py's real act over their fakes), every
incident planted by the heal modules' own writers. No device, no network.

- **The timeline, each time from its record:** detected is the first trigger's epoch, decided
  the decision's row, applied (and Fixed) the act's ``intent`` step, verified the act's
  ``record`` step with ``healed``, and TIME TO REPAIR verified minus detected in whole
  seconds. The expectations are read from the stores' own rows, never through the page's code.
- **A failed verify never reads "Fixed"** (the operator, 2026-11-11): a heal rolled back,
  partial, or with its symptom still there is "needs a person", its Fixed cell empty with its
  reason, its attempt "applied … · verify failed: …", its TIME TO REPAIR "not repaired: verify
  failed"; and a scan of the page finds no claim that it was fixed, for every outcome that is
  not a passed verify.
- **Who:** "by Mercury's self-healing · policy set by <display name>" only where the record
  shows the policy alone; a person's approval reads "… · approved by <display name>".
- **What Mercury has done** is THE stepper's five stages, the same stages its device's page
  draws for History's Open the card.
- **The five states** in their words, a fold's redirect, an unknown id, another kind of id, a
  record that cannot be read, and an incident past the ones kept.
- **The page:** no identity outside its collapsed record, the strict policy, the viewer
  through `identity.viewer()`, a read that writes nothing and reaches nothing but the
  network's own stores (the page-speed rule), and one place per incident: History's heal rows
  and Needs attention's heal rows link it.
- **The operator's test of the page, 2026-11-13:** a drill's incident says Drill (beside its
  state and beside its Needs attention link, its fd- id on hover, keyed on the record's tag); a
  fixed incident ends at its verify, never at the act's start its store kept as the close; the
  Fixing stage holds the whole apply and names the BGP hold the deploy's verify waited out (on
  r3's real captures, through the real pipeline's watch); TIME TO REPAIR and Done say one
  duration, from the same two records, in one format; a sub-mode's exit is no line.
"""
import calendar
import json
import os
import re
import time
from html import unescape

import pytest

from modules import incident_page as IP
from tests import people_drawn
from tests.conftest import TEST_PERSON
from tests.test_bgp_hold_watch import _summary
from tests.test_bgp_hold_watch import world  # noqa: F401  (the fixture `bgp_watch` builds on)
from tests.test_heal_act import ADJ, SETTER, FakeAct
from tests.test_heal_analysis import ACL_RUNNING
from tests.test_heal_decide import GOLDEN, ROUTE4, Fake, settle
from tests.test_heal_decide import lab  # noqa: F401  (the fixture, named by each test below)
from tests.test_heal_policy import T0, auto, iso
from tests.test_heal_propose import PERSON, R8, WHO, FakeApproved, proposed, run_approved
from tests.test_heal_propose import measured  # noqa: F401  (a fixture)
from tests.test_heal_triggers import _Lazy
from tests.test_sdn_connections import networks  # noqa: F401  (the fixture `lab` builds on)

A, DC, DS, I, P, SL = (_Lazy("act"), _Lazy("decide"), _Lazy("decisions"), _Lazy("incidents"),
                       _Lazy("propose"), _Lazy("steplog"))
NET = "Default"
EDGE = {"hostname": "edge-b", "ip": "192.0.2.6", "device_type": "cisco_xe"}
#: The configuration change that opens each planted incident: its receive time carries a
#: fraction of a second, as a log line's does, so "whole seconds" is something the page does.
DETECTED = T0 - 1000.6
CFG = {"kind": "config_change", "key": "cfg:1", "epoch": DETECTED, "at": iso(DETECTED),
       "source": "logs-tail", "attribution": {"by": "outside"},
       "person": {"user": "alice", "words": "the line names the account alice on vty0"},
       "words": "SYS-5-CONFIG_I on edge-b: from outside Mercury; the line names the account "
                "alice on vty0"}


@pytest.fixture(autouse=True)
def no_host_addresses(monkeypatch):
    monkeypatch.setattr("modules.nsot.removal.host_addresses", lambda: ["192.0.2.60"])


@pytest.fixture
def client(lab, monkeypatch):  # noqa: F811
    """The heal's lab behind the real app, edge-b on its network's pages."""
    import app as APP

    monkeypatch.setattr("modules.device.load_saved_devices", lambda path=None: [dict(EDGE)])
    monkeypatch.setattr("modules.integration_groups.network_names", lambda: [NET])
    APP.app.config["TESTING"] = True
    return APP.app.test_client()


# ── The planted incidents, each by the heal modules' own writers ───────────────────────────

class Ticking:
    """An act's clock while an incident is planted: each reading 7 s after the last, from
    just after the decision. The act stamps each step from the wall clock, so a test's steps
    would share one second and no check could tell the intent step's time from the record
    step's; with this, every step's time is its own. Everything else is the real `time`."""

    def __init__(self, start=T0 + 5):
        self.now = float(start)

    def time(self):
        self.now += 7.0
        return self.now

    def __getattr__(self, name):
        return getattr(time, name)


def heal(running=GOLDEN + ROUTE4, *, triggers=None, **kw):
    """One incident decided by the real decision's pass in Auto (its decision and its steps
    recorded) and acted on by the real act over its fakes: ``(incident id, the act's
    answer)``. *kw* is the act's fake (``post``, ``recheck``, ``symptom``, ``result``)."""
    auto(NET, now=T0 - 60, kinds=("added_line",))
    settle(running, triggers=triggers or [CFG], claim=False)
    (d,) = DC.run(NET, now=T0, sources=Fake(running))["decided"]
    assert d["outcome"] == "heal", d
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("modules.heal.act.time", Ticking())
        got = A.act_one(NET, d["decision"], now=T0 + 5, sources=FakeAct(running, **kw))
    return d["incident"], got


def healed():
    iid, got = heal()
    assert got["outcome"] == "healed", got["words"]
    return iid


def rolled_back():
    """The read after the change still holds the route: what landed was undone."""
    iid, got = heal(post=GOLDEN + ROUTE4)
    assert got["outcome"] == "rolled_back", got["words"]
    return iid


def cant_fix():
    """A can't-fix in dry run: it stands on its decision, open."""
    settle(ACL_RUNNING, triggers=[CFG], claim=False)
    (d,) = DC.run(NET, now=T0, sources=Fake(ACL_RUNNING))["decided"]
    assert d["outcome"] == "cant_fix", d
    return d["incident"]


def approved(src=None):
    """A Tier 2 proposal a person approved, applied as them and verified."""
    d = proposed()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("modules.heal.propose.time", Ticking())
        got, _approval, _v = run_approved(d, src or FakeApproved(R8))
    assert got["outcome"] == "healed", got["words"]
    return d["incident"]


def declined():
    """A Tier 2 proposal a person declined, with their reason."""
    d = proposed()
    P.decline(NET, d["id"], reason="not during the course lab", now=T0 + 2, **WHO)
    return d["incident"]


def busy():
    """A can't-fix on edge-b that took other devices in: core-a's own incident folded into
    it (edge-b is the far end of core-a's lost adjacency), dist-c attached to it and then
    moved to an incident of its own when it changed too (each names the other), and an AI
    analysis kept for it. ``(its id, the folded incident's id, the related incident's id)``."""
    far = dict(ADJ, key="adj:far", related=["edge-b"], epoch=T0 - 1100, at=iso(T0 - 1100),
               words="the OSPF adjacency core-a – edge-b is down")
    old = I.sight(NET, "core-a", far, now=T0 - 1100)["incident"]
    iid = I.sight(NET, "edge-b", CFG, now=T0 - 1000)["incident"]
    also = dict(ADJ, key="adj:also", related=["edge-b"], epoch=T0 - 900, at=iso(T0 - 900),
                words="the OSPF adjacency dist-c – edge-b is down")
    assert I.sight(NET, "dist-c", also, now=T0 - 900)["action"] == "attached"
    moved = I.sight(NET, "dist-c", dict(CFG, key="cfg:dist-c", epoch=T0 - 800, at=iso(T0 - 800)),
                    now=T0 - 800)
    assert moved["action"] == "moved", moved
    assert cant_fix() == iid
    SL.record_advisory(NET, iid, device="edge-b", state="answered", passes=1, now=T0 + 30,
                       words="AI analysis: asked for 2 reads; 2 run; answered", steps=[])
    return iid, old, moved["incident"]


def raw(incident_id):
    """The stores' own rows for one incident, read here and never through the page's code:
    ``(the incident, its step-log rows, its decision store's lines)``."""
    inc = next(i for i in I.read(NET)["incidents"] if i["id"] == incident_id)
    rows = [r for r in SL.read(NET)["rows"] if r.get("incident") == incident_id]
    with open(DS.path(NET), encoding="utf-8") as fh:
        lines = [json.loads(x) for x in fh if x.strip()]
    return inc, rows, lines


def seconds(stamp):
    return calendar.timegm(time.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ"))


def tree(root):
    return sorted((os.path.join(p, f), os.path.getsize(os.path.join(p, f)),
                   os.stat(os.path.join(p, f)).st_mtime_ns)
                  for p, _d, fs in os.walk(root) for f in fs)


def stores():
    """Every file the lab's store holds, with its size and its time."""
    from modules import config

    return tree(config.DATA_DIR)


def read(client, url, code=200):
    """One GET, held to the page's first property each time it is made: it answers *code*,
    and it leaves every file of the store exactly as it was (the page is a read)."""
    before = stores()
    r = client.get(url)
    assert r.status_code == code, (url, r.status_code, r.get_data(as_text=True)[:300])
    assert stores() == before, f"reading {url} wrote to the store"
    return r


def page(client, incident_id, code=200):
    return read(client, f"/v2/incident/{incident_id}?list={NET}", code).get_data(as_text=True)


def cell(body, name):
    """One header cell's own HTML (``data-cell``); a cell holds no nested div."""
    m = re.search(rf'<div class="inc-time[^"]*" data-cell="{name}".*?</div>', body, re.S)
    assert m, f"no {name} cell is drawn"
    return m.group(0)


def text_of(html):
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", html)).split())


def times_in(html):
    return re.findall(r'<time class="clock" datetime="([^"]+)"', html)


def model(incident_id):
    found = IP.resolve(NET, incident_id)
    return found["incident"], found["entry"], found["decisions"]


# ── The timeline, each time from its record ────────────────────────────────────────────────

class TestTheTimelineFromItsRecords:
    def test_each_time_is_its_record_s_and_the_repair_is_whole_seconds(self, client):
        iid = healed()
        inc, rows, lines = raw(iid)
        (act_row,) = [r for r in rows if r["row"] == "act"]
        (decision,) = [x for x in lines if x.get("row") == "decision"]
        detected = iso(inc["triggers"][0]["epoch"])
        applied = next(s["at"] for s in act_row["steps"] if s["step"] == "intent")
        verified = next(s["at"] for s in act_row["steps"]
                        if s["step"] == "record" and s["result"] == "healed")
        ttr = seconds(verified) - int(inc["triggers"][0]["epoch"])
        assert inc["triggers"][0]["epoch"] != int(inc["triggers"][0]["epoch"]), \
            "the planted receive time carries a fraction"
        tl = IP.timeline(*model(iid))
        assert (tl["detected"]["state"], tl["detected"]["at"]) == ("at", detected)
        assert (tl["decided"]["state"], tl["decided"]["at"]) == ("at", decision["at"])
        assert (tl["fixed"]["state"], tl["fixed"]["at"]) == ("at", applied)
        assert (tl["verified"]["state"], tl["verified"]["at"]) == ("at", verified)
        assert detected < decision["at"] < applied < verified, \
            "four times, each its own: no two of these records share one"
        assert tl["ttr"]["seconds"] == ttr and tl["ttr"]["words"] == f"{ttr:,} s"
        assert isinstance(tl["ttr"]["seconds"], int)
        body = page(client, iid)
        assert times_in(cell(body, "detected")) == [detected]
        assert times_in(cell(body, "decided")) == [decision["at"]]
        assert times_in(cell(body, "fixed")) == [applied]
        assert times_in(cell(body, "verified")) == [verified]
        assert f"{ttr:,} s" in text_of(cell(body, "ttr"))
        assert 'data-state="fixed"' in body and "inc-ttr-repaired" in body

    def test_every_time_is_drawn_by_the_page_s_clock_with_utc_on_its_hover(self, client):
        body = page(client, healed())
        drawn = re.findall(r"<time [^>]*>", body.split('id="incident-live"', 1)[1])
        assert len(drawn) >= 8, len(drawn)
        for tag in drawn:
            # The header's and the timeline's own, to the second with their date; a cause's
            # and a step's, the shared macros' (`_macros.clock`): each the viewer's own time.
            assert 'class="clock"' in tag and " data-clock" in tag, tag
            assert re.search(r'title="\d{4}-\d\d-\d\d \d\d:\d\d:\d\d UTC"', tag), tag
        head = body.split('class="card inc-head', 1)[1].split("</section>", 1)[0]
        mine = re.findall(r"<time [^>]*>", head)
        assert len(mine) >= 6 and all('data-clock="date-seconds"' in t for t in mine), mine
        assert " UTC<" not in re.sub(r"<time [^>]*>[^<]*</time>", "", body.split(
            'id="incident-live"', 1)[1]), "no bare UTC time is drawn beside the local ones"

    def test_the_attempt_reads_applied_then_verified(self, client):
        iid = healed()
        _inc, rows, _lines = raw(iid)
        (act_row,) = [r for r in rows if r["row"] == "act"]
        applied = next(s["at"] for s in act_row["steps"] if s["step"] == "intent")
        verified = next(s["at"] for s in act_row["steps"] if s["step"] == "record")
        (line,) = re.findall(r'<p class="inc-attempt[^"]*" data-attempt="1">.*?</p>',
                             page(client, iid), re.S)
        assert "inc-attempt-verified" in line and times_in(line) == [applied, verified]
        assert re.search(r"Attempt 1: applied .* · verified ", text_of(line))

    def test_what_mercury_has_done_is_the_one_stepper_s_five_stages(self, client):
        body = page(client, healed())
        done = body.split('id="inc-done"', 1)[1].split("</section>", 1)[0]
        assert done.count("data-run-stepper") == 1, "THE stepper's macro drew it, once"
        assert re.findall(r'data-stage="([a-z]+)"', done) == [
            "detected", "decided", "fixing", "checking", "done"]
        for key in ("x-opened", "d-claim", "d-decide", "take", "apply", "intent", "record"):
            assert f'data-step="{key}"' in done, key
        assert "run-stage-failed" not in done and "run-step-failed" not in done
        assert "Healed and verified" in text_of(done.split('data-stage="done"', 1)[1])
        record = body.split("inc-record", 1)[1]
        assert "documentation updated and tested" in record

    @pytest.mark.parametrize("plant", ["healed", "rolled_back"])
    def test_its_stages_are_the_card_its_device_s_page_draws(self, client, plant):
        """Never a second stepper or its own copy of the steps: the stages drawn here are the
        ones History's Open the card opens on the device's page (`run_card.named_heal`), byte
        for byte."""
        iid = {"healed": healed, "rolled_back": rolled_back}[plant]()
        here = re.search(r'<ol class="run-stages".*?</ol>\s*</div>',
                         page(client, iid), re.S)
        card = read(client, f"/v2/device/edge-b?list={NET}&tab=history&result={iid}")
        there = re.search(r'<ol class="run-stages".*?</ol>\s*</div>',
                          card.get_data(as_text=True), re.S)
        assert here and there, "both pages draw the heal's stages"
        assert here.group(0) == there.group(0)


# ── A failed verify never reads "Fixed" ────────────────────────────────────────────────────

def fixed_claims(body: str) -> list:
    """Every way the page claims an incident was fixed, found by where it is drawn: the
    state's mark, a title or a line saying it was put back or fixed, a repaired TIME TO
    REPAIR, a Fixed cell holding a time, an attempt drawn verified, a green outcome, and the
    word "Fixed" anywhere but as the Fixed cell's own label."""
    live = body.split('id="incident-live"', 1)[1].split('class="card tl-record-d', 1)[0]
    found = []
    if 'data-state="fixed"' in live:
        found.append("the state reads fixed")
    if "inc-ttr-repaired" in live:
        found.append("a repaired TIME TO REPAIR")
    if times_in(cell(body, "fixed")):
        found.append("the Fixed cell holds a time")
    if "inc-attempt-verified" in live:
        found.append("an attempt drawn verified")
    if 'data-outcome-level="ok"' in live:
        found.append("a green outcome")
    words = text_of(live)
    if re.search(r"put (it )?back by|Mercury put it back|fix was verified|fixed and verified",
                 words):
        found.append("words saying it was fixed")
    others = len(re.findall(r"\bFixed\b", words)) - len(re.findall(r"<dt>Fixed</dt>", live))
    if others:
        found.append(f'"Fixed" drawn {others} time(s) besides the cell\'s label')
    return found


class TestAFailedVerifyNeverReadsFixed:
    def test_a_rolled_back_heal_needs_a_person(self, client):
        iid = rolled_back()
        inc, entry, decisions = model(iid)
        assert entry["outcome"] == "rolled_back" and entry["sent"] is True
        assert IP.state_of(inc, entry, decisions) == "needs_person"
        tl = IP.timeline(inc, entry, decisions)
        assert tl["fixed"] == {"state": "none", "at": "", "words": "not fixed: verify failed",
                               "hover": ""}
        assert tl["verified"]["state"] == "failed"
        assert tl["ttr"]["seconds"] is None
        assert tl["ttr"]["words"] == "not repaired: verify failed"
        body = page(client, iid)
        assert 'data-state="needs_person"' in body and "Needs a person" in body
        assert "resolved: read-only" not in body and "(was)" not in body
        assert ">Critical<" in body and "was Critical" not in body
        assert text_of(cell(body, "fixed")) == "Fixed — not fixed: verify failed"
        assert "Verify failed (UTC)" in body and "Verified (UTC)" not in body, \
            "the record never calls a failed verify's time verified"
        assert "✗ verify failed" in text_of(cell(body, "verified"))
        assert "not repaired: verify failed" in text_of(cell(body, "ttr"))
        (line,) = re.findall(r'<p class="inc-attempt[^"]*" data-attempt="1">.*?</p>', body,
                             re.S)
        said = text_of(line)
        assert "inc-attempt-failed" in line
        assert re.search(r"Attempt 1: applied .* · verify failed: .*so what landed was undone",
                         said), said
        _inc, rows, _lines = raw(iid)
        (act_row,) = [r for r in rows if r["row"] == "act"]
        applied = next(s["at"] for s in act_row["steps"] if s["step"] == "intent")
        assert times_in(line) == [applied], "applied is the intent step's time"

    @pytest.mark.parametrize("fake, outcome", [
        ({"post": GOLDEN + ROUTE4}, "rolled_back"),
        ({"recheck": "drifted"}, "partial"),
        ({"symptom": {"state": "present", "words": "the OSPF adjacency edge-b – core-a is "
                                                   "still down"}}, "symptom_remains"),
        ({"result": {"outcome": "failed", "stage": "verify", "commands": ["x"],
                     "reason": "verify did not pass"}}, "failed")])
    def test_no_page_of_a_failed_verify_claims_it_fixed(self, client, fake, outcome):
        """The scan, over real records: each way a heal sends and does not pass its verify."""
        triggers = [CFG, ADJ] if outcome == "symptom_remains" else None
        iid, got = heal(triggers=triggers, **fake)
        assert got["outcome"] == outcome and got["sent"], got["words"]
        body = page(client, iid)
        assert fixed_claims(body) == [], outcome
        assert 'data-state="needs_person"' in body
        assert "not repaired: verify failed" in text_of(cell(body, "ttr"))

    def test_the_scan_finds_a_fixed_incident_s_claims(self, client):
        """The planted case: a healed incident's page holds each claim the scan looks for."""
        found = fixed_claims(page(client, healed()))
        assert len(found) >= 6, found

    def test_no_outcome_but_a_passed_verify_is_ever_fixed(self, client):
        """Every outcome self-healing can record, put in place of the healed incident's own
        (a real record, its outcome alone changed): only the allowlist is fixed."""
        from modules.heal import bounce, run_card, session_clear

        iid = healed()
        inc, entry, decisions = model(iid)
        outcomes = (set(SL.MARKS) | set(A.OUTCOMES) | set(bounce.OUTCOMES)
                    | set(session_clear.OUTCOMES) | {"dampened", "unheard_of"})
        assert len(outcomes) >= 25 and set(SL.NOT_HEALED) <= outcomes, len(outcomes)
        fixed = set()
        for outcome in sorted(outcomes):
            steps = [dict(s, result=outcome) if s.get("step") == "record" else s
                     for s in entry["steps"]]
            edited = dict(entry, outcome=outcome, steps=steps)
            state = IP.state_of(inc, edited, decisions)
            tl = IP.timeline(inc, edited, decisions)
            if state == "fixed":
                fixed.add(outcome)
                continue
            assert tl["ttr"]["seconds"] is None and tl["fixed"]["state"] != "at", outcome
            assert "put it back" not in IP.title(inc, edited, decisions), outcome
        assert fixed == set(run_card.HEALED) & outcomes == {"healed", "bounced", "cleared",
                                                            "dampened"}
        for outcome in SL.NOT_HEALED:
            steps = [dict(s, result=outcome) if s.get("step") == "record" else s
                     for s in entry["steps"]]
            edited = dict(entry, outcome=outcome, steps=steps)
            assert IP.state_of(inc, edited, decisions) == "needs_person", outcome
            assert IP.timeline(inc, edited, decisions)["ttr"]["words"] == \
                "not repaired: verify failed", outcome

    def test_a_heal_refused_at_its_apply_sent_nothing_and_fixed_nothing(self, client):
        iid, got = heal(read_error="timed out")
        assert got["outcome"] == "refused" and not got["sent"]
        body = page(client, iid)
        assert fixed_claims(body) == [] and 'data-state="needs_person"' in body
        assert text_of(cell(body, "fixed")) == "Fixed — not fixed: nothing was sent"
        assert "not repaired: nothing was sent" in text_of(cell(body, "ttr"))
        assert "data-attempt=" not in body, "nothing was sent, so no attempt was made"


# ── Who took part ──────────────────────────────────────────────────────────────────────────

class TestNoHumanOnlyFromTheRecord:
    def test_the_policy_alone_reads_mercury_s_self_healing_by_the_policy_s_setter(self, client):
        """The operator, 2026-11-12: a self-heal reads "by Mercury's self-healing · policy set
        by <display name>", the words its card and History use."""
        iid = healed()
        inc, entry, decisions = model(iid)
        assert entry["by"] == "heal to intent (policy set by admin)"
        assert entry["policy_by"] == SETTER
        assert [d["taken"]["by"] for d in decisions] == ["heal to intent: the apply"]
        assert IP.who_of(entry, decisions) == {"kind": "none", "actor": SETTER}
        body = page(client, iid)
        said = "· by Mercury's self-healing · policy set by admin"
        assert said in text_of(cell(body, "ttr"))
        head = text_of(body.split('class="card inc-head', 1)[1].split("</section>", 1)[0])
        assert head.count("Mercury's self-healing") == 1, "said once, beside the repair time"
        assert "No person needed" in body and "No person took part in this incident" in body
        assert text_of(body.split("<h1", 1)[1].split("</h1>", 1)[0]).endswith(
            ", and Mercury put it back")

    def test_a_person_s_approval_reads_approved_by_their_display_name(self, client, measured):  # noqa: F811
        iid = approved()
        inc, entry, decisions = model(iid)
        assert IP.who_of(entry, decisions) == {"kind": "person", "actor": PERSON}
        _inc, _rows, lines = raw(iid)
        (taken,) = [x for x in lines if x.get("row") == "taken"]
        tl = IP.timeline(inc, entry, decisions)
        assert tl["decided"]["at"] == taken["at"], "decided is the person's confirm"
        body = page(client, iid)
        assert times_in(cell(body, "decided")) == [taken["at"]]
        assert "· by Mercury's self-healing · approved by op" in text_of(cell(body, "ttr"))
        head = text_of(body.split('class="card inc-head', 1)[1].split("</section>", 1)[0])
        assert head.count("approved by op") == 1, "said once, beside the repair time"
        assert "policy set by" not in head and "No person needed" not in body
        assert ", and it was put back by op" in text_of(
            body.split("<h1", 1)[1].split("</h1>", 1)[0])

    def test_a_set_display_name_is_the_one_drawn(self, client, measured):  # noqa: F811
        from modules import display_names

        iid = approved()
        display_names.set_name(PERSON, "Orla", by=PERSON, actor_verified="access")
        body = page(client, iid)
        assert "approved by Orla" in text_of(cell(body, "ttr"))

    @pytest.mark.parametrize("what", ["dry run", "an approval recorded", "a person's take",
                                      "a person's own act"])
    def test_any_sign_of_a_person_or_no_auto_is_never_the_policy_alone(self, client, what):
        """The healed incident's own records, one piece of the evidence changed at a time."""
        inc, entry, decisions = model(healed())
        if what == "dry run":
            entry = dict(entry, mode="dry_run")
        elif what == "an approval recorded":
            entry = dict(entry, records=dict(entry["records"], approval="declined by x (access)"))
        elif what == "a person's take":
            decisions = [dict(d, taken=dict(d["taken"], by="someone: by hand"))
                         for d in decisions]
        else:
            entry = dict(entry, by=PERSON)
        assert IP.who_of(entry, decisions)["kind"] != "none", what
        assert "policy set by" not in IP.timeline(inc, entry, decisions)["ttr"]["who"], what


# ── The states, and what is not a page ─────────────────────────────────────────────────────

class TestTheStates:
    def test_open_while_mercury_is_watching(self, client):
        got = I.sight(NET, "edge-b", CFG, now=T0 - 1000)
        body = page(client, got["incident"])
        assert 'data-state="open"' in body and ">Open<" in body
        for name in ("decided", "fixed", "verified"):
            assert text_of(cell(body, name)).endswith("— not yet"), name
        assert times_in(cell(body, "detected")) == [iso(DETECTED)]
        assert text_of(cell(body, "ttr")).endswith("not repaired")
        assert "Nothing has run in this incident." in body
        assert "Mercury is still reading edge-b" in body
        assert "resolved: read-only" not in body

    def test_a_cant_fix_standing_needs_a_person(self, client):
        iid = cant_fix()
        body = page(client, iid)
        assert 'data-state="needs_person"' in body and "Critical" in body
        assert text_of(cell(body, "decided")).endswith("— not yet"), \
            "no fix was chosen: a can't-fix decides none"
        assert "Mercury cannot fix this yet" in body and "It needs a person." in body
        assert 'data-step="d-decide"' in body and "run-step-failed" in body
        assert fixed_claims(body) == []

    def test_cleared_when_it_closed_with_no_fix_recorded(self, client):
        got = I.sight(NET, "edge-b", CFG, now=T0 - 1000)
        assert I.close_watching(NET, "self-healing was turned off", now=T0) == [got["incident"]]
        body = page(client, got["incident"])
        assert 'data-state="cleared"' in body and ">Cleared<" in body
        assert "cleared, no repair recorded" in text_of(cell(body, "ttr"))
        for name in ("decided", "fixed", "verified"):
            assert text_of(cell(body, name)).endswith("— not needed"), name
        assert "resolved: read-only" in body and fixed_claims(body) == []
        assert text_of(body.split("<h1", 1)[1].split("</h1>", 1)[0]).endswith(
            ", and it cleared")

    def test_cancelled_when_a_person_declined_the_fix(self, client):
        body = page(client, declined())
        assert 'data-state="cancelled"' in body and ">Cancelled<" in body
        assert "declined by op" in text_of(cell(body, "decided"))
        assert "not repaired: the fix was declined" in text_of(cell(body, "ttr"))
        assert fixed_claims(body) == [] and "data-attempt=" not in body

    def test_a_proposal_waiting_needs_a_person(self, client):
        d = proposed()
        inc, entry, decisions = model(d["incident"])
        assert inc["state"] == "claimed" and decisions[-1]["outcome"] == "propose"
        assert IP.state_of(inc, entry, decisions) == "needs_person"

    def test_the_five_states_are_the_only_ones(self):
        assert IP.STATES == ("open", "needs_person", "fixed", "cleared", "cancelled")
        assert set(IP.STATE_WORDS) == set(IP.STATES)


class TestWhatIsNotAPage:
    def test_a_folded_incident_redirects_to_the_one_it_was_folded_into(self, client):
        far = dict(ADJ, key="adj:far", related=["edge-b"],
                   words="the OSPF adjacency core-a – edge-b is down")
        old = I.sight(NET, "core-a", far, now=T0 - 1100)["incident"]
        new = I.sight(NET, "edge-b", CFG, now=T0 - 1000)["incident"]
        folded = next(i for i in I.read(NET)["incidents"] if i["id"] == old)
        assert folded["state"] == "closed" and folded["folded_into"] == new
        r = read(client, f"/v2/incident/{old}?list={NET}", 302)
        assert r.headers["Location"] == f"/v2/incident/{new}?list={NET}"
        body = page(client, new)
        line = text_of(re.search(r'<div class="notice notice-muted inc-folded".*?</div></div>',
                                 body, re.S).group(0))
        assert line.startswith("Folded into this incident at ")
        assert f"core-a's incident ({old}) was taken in because edge-b is the far end" in line
        assert "and 1 device attached" in body

    def test_what_an_incident_took_in_and_what_it_is_related_to_are_said(self, client):
        iid, old, other = busy()
        body = page(client, iid)
        said = text_of(body)
        assert f"core-a's incident ({old}) was taken in because" in said
        assert f'<a href="/v2/incident/{other}?list={NET}">dist-c\'s incident</a>' in \
            unescape(body)
        assert "both changed: a cause spanning devices" in said
        assert "and 1 device attached" in said
        evidence = body.split("inc-evidence", 1)[1].split("</details>", 1)[0]
        assert ">core-a</a>" in evidence and "is the far end of its link" in evidence
        assert "AI analysis (advisory; self-healing never reads it)" in said
        assert read(client, f"/v2/incident/{old}?list={NET}", 302).headers["Location"] == \
            f"/v2/incident/{iid}?list={NET}"

    def test_an_unknown_id_is_a_404_saying_so(self, client):
        healed()
        body = text_of(page(client, "hi-000000000000", 404))
        assert "No incident hi-000000000000 is recorded." in body
        assert f"It was looked for in {NET}" in body and "newest 200 closed" in body

    def test_an_id_out_of_shape_is_unknown_and_reads_no_store(self, client, monkeypatch):
        import modules.heal.incidents as INC

        monkeypatch.setattr(INC, "read", lambda network: pytest.fail("a store was read"))
        body = text_of(page(client, "hi-not-an-id", 404))
        assert "No incident hi-not-an-id is recorded." in body

    @pytest.mark.parametrize("other", ["al-0123456789abcdef0123", "resp-0123456789", "x"])
    def test_another_kind_of_id_is_a_404_naming_its_slice(self, client, other):
        body = text_of(page(client, other, 404))
        assert "This kind of incident's page comes with S4." in body
        assert "No incident" not in body

    def test_a_record_that_cannot_be_read_is_a_200_saying_so(self, client):
        iid = healed()
        os.makedirs(os.path.dirname(I.path(NET)), exist_ok=True)
        with open(I.path(NET), "w", encoding="utf-8") as fh:
            fh.write("{torn")
        body = text_of(page(client, iid, 200))
        assert "Part of this incident's record couldn't be read:" in body
        assert "Default's heal incidents cannot be read (JSONDecodeError)" in body
        assert f"Whether {iid} is open is not known" in body
        assert "healed and verified" in body, "what could be read is drawn"
        # An id nothing readable holds: absent is not known, so never a 404.
        other = text_of(page(client, "hi-000000000000", 200))
        assert "This incident's record couldn't be read:" in other
        assert "No incident hi-000000000000 is recorded" not in other

    def test_an_incident_past_the_ones_kept_is_drawn_from_its_step_log(self, client,
                                                                        monkeypatch):
        import modules.heal.incidents as INC

        iid = healed()
        monkeypatch.setattr(INC, "CLOSED_KEPT", 0)
        I.sight(NET, "core-a", dict(ADJ, key="adj:later"), now=T0 + 100)
        assert iid not in [i["id"] for i in I.read(NET)["incidents"]], "pruned by its writer"
        body = page(client, iid)
        said = text_of(body)
        assert "this page is drawn from its step log alone" in said
        assert 'data-state="fixed"' in body
        assert text_of(cell(body, "detected")).startswith("Detected — not recorded:")
        assert "not recorded: its detected time is not kept" in text_of(cell(body, "ttr"))
        assert "inc-ttr-repaired" not in body, "no repair time without both of its records"


# ── The page ───────────────────────────────────────────────────────────────────────────────

class TestThePage:
    @pytest.mark.parametrize("plant, said", [
        (approved, "taken on {}'s approval"), (declined, "declined by {}: not during")])
    def test_no_identity_is_drawn_outside_its_collapsed_record(self, client, measured,  # noqa: F811
                                                               plant, said):
        """A person's approval and a person's decline are recorded with their identity, in
        the steps' words and the act's: each is drawn by display name, and the identity as
        recorded is only in The record."""
        body = page(client, plant())
        drawn, kept = people_drawn.scan(body)
        assert drawn == [], drawn
        assert PERSON in {i for i, _w, _a in kept}, "The record keeps the identity"
        shown, record = unescape(body).split('class="card tl-record-d', 1)
        assert said.format("op") in shown, "the recorded words, by display name"
        assert said.format(PERSON) in record, "the record, as recorded"

    def test_an_identity_in_a_trigger_s_own_words_is_drawn_by_name(self, client):
        """A device's log line may name the account that changed it by an identity; the
        incident's title is built from those words before any decision, and draws the name."""
        who = "ops@example.invalid"
        got = I.sight(NET, "edge-b", dict(
            CFG, words=f"SYS-5-CONFIG_I on edge-b: configured from vty0 by {who}"),
            now=T0 - 1000)
        body = page(client, got["incident"])
        drawn, kept = people_drawn.scan(body)
        assert drawn == [], drawn
        assert who in {i for i, _w, _a in kept}, "The record keeps the words as recorded"
        assert "configured from vty0 by ops" in text_of(
            body.split("<h1", 1)[1].split("</h1>", 1)[0])

    def test_a_secret_in_a_record_is_masked_on_the_way_out(self, client):
        """The incidents store keeps a trigger's words as they arrived; the page masks every
        text again, the title and The record alike, and leaves the store as written."""
        line = "snmp-server community S3cretRO RO"
        got = I.sight(NET, "edge-b", dict(CFG, words=f"SYS-5-CONFIG_I on edge-b: {line}"),
                      now=T0 - 1000)
        body = page(client, got["incident"])
        assert "S3cretRO" not in body, "a secret's value reached the page"
        assert body.count("snmp-server community") >= 2, "its words are drawn, masked"
        with open(I.path(NET), encoding="utf-8") as fh:
            assert "S3cretRO" in fh.read(), "masked on the way out only"

    def test_a_policy_s_setter_is_named_and_never_their_identity(self, client):
        body = page(client, healed())
        drawn, kept = people_drawn.scan(body)
        assert drawn == [] and SETTER in {i for i, _w, _a in kept}
        assert "admin confirmed" in body, "the no-human hover names the policy's confirmer"

    def test_it_carries_the_strict_policy_whatever_it_answers(self, client):
        from modules import csp

        iid = healed()
        for url, code in ((iid, 200), ("hi-000000000000", 404), ("al-1", 404)):
            r = read(client, f"/v2/incident/{url}?list={NET}", code)
            assert r.headers["Content-Security-Policy"] == csp.STRICT_POLICY, url

    def test_the_viewer_is_drawn_through_identity_viewer(self, client, monkeypatch):
        from modules import identity

        body = page(client, healed())
        assert 'data-identified="yes"' in body and TEST_PERSON.split("@")[0] in body
        other = identity.Identity(actor="second@example.invalid", email="second@example.invalid",
                                  kind="person", verified=True, outcome="ok",
                                  peer="198.51.100.7", peer_trusted=True, header_present=True)
        monkeypatch.setattr(identity, "viewer", lambda: other)
        again = page(client, "hi-000000000000", 404)
        assert ">second<" in again and "second@example.invalid" not in again

    def test_a_read_writes_nothing_and_creates_no_network(self, client, lab):  # noqa: F811
        iid = healed()
        open_one = I.sight(NET, "core-a", dict(ADJ, key="adj:open"), now=T0 + 50)["incident"]
        before = tree(lab)
        for url, code in ((iid, 200), (open_one, 200), ("hi-000000000000", 404), ("al-1", 404)):
            page(client, url, code)
        assert client.get(f"/v2/incident/{iid}?list=Nowhere").status_code == 404
        assert tree(lab) == before, "a read wrote something"
        assert not os.path.exists(os.path.join(lab, "lists", "nowhere"))

    def test_it_draws_from_what_the_background_holds_and_opens_no_connection(self, client,
                                                                             monkeypatch):
        """The page-speed rule (CLAUDE.md, "No page load or badge poll waits on…"): the page
        reads the network's own heal stores and this server's jobs; it opens no connection,
        loopback included, so it waits on no device, Grafana, Loki or NetBox."""
        import socket

        iid = healed()
        watching = I.sight(NET, "core-a", dict(ADJ, key="adj:open"), now=T0 + 50)["incident"]
        opened = []

        def refuse(*args, **_kw):
            opened.append(args[1:2] or args[:1])
            raise OSError("the incident page opened a connection")

        monkeypatch.setattr(socket.socket, "connect", refuse)
        monkeypatch.setattr(socket.socket, "connect_ex", refuse)
        monkeypatch.setattr(socket, "create_connection", refuse)
        for url, code in ((iid, 200), (watching, 200), ("hi-000000000000", 404)):
            body = page(client, url, code)
            assert "couldn't be read" not in body, url
        assert opened == [], opened

    def test_it_starts_nothing_links_only(self, client):
        body = page(client, cant_fix())
        live = body.split('id="incident-live"', 1)[1].split("</main>", 1)[0]
        assert "<form" not in live and "<button" not in live and "hx-post" not in live
        todo = live.split('id="inc-todo"', 1)[1].split("</section>", 1)[0]
        assert todo.count("<a ") == 3 and "Open Needs attention" in todo

    def test_it_is_drawn_again_when_self_healing_announces_and_never_polls(self, client):
        iid = healed()
        body = page(client, iid)
        tag = re.search(r'<div id="incident-live"[^>]*>', body).group(0)
        assert 'hx-trigger="nmas:drift from:body, nmas:privileged from:body"' in tag
        assert 'hx-select="#incident-live"' in tag
        assert 'hx-disinherit="*"' in tag and "every " not in tag
        assert f'hx-get="/v2/incident/{iid}?list={NET}"' in unescape(tag)

    def test_a_long_reason_stops_at_its_stated_length(self, client):
        long = "the verify did not pass because " + "the route was still there and " * 20
        iid, got = heal(result={"outcome": "failed", "stage": "verify", "commands": ["x"],
                                "reason": long})
        assert got["outcome"] == "failed" and len(got["words"]) > 2 * IP.REASON_CHARS
        (line,) = re.findall(r'<p class="inc-attempt[^"]*" data-attempt="1">.*?</p>',
                             page(client, iid), re.S)
        reason = text_of(line).split("verify failed: ", 1)[1].split(" · by Mercury")[0]
        assert len(reason) <= IP.REASON_CHARS and reason.endswith("…")
        assert long.strip() in text_of(page(client, iid).split("inc-record", 1)[1]), \
            "the whole of it is in The record"

    def test_the_ai_frame_says_it_is_not_built_and_keeps_today_s_advisory(self, client):
        iid = cant_fix()
        body = page(client, iid)
        ai = body.split('id="inc-ai"', 1)[1].split("</section>", 1)[0]
        # The section is built (the fix-it plan's S4): edge-b is in no inventory row that gives
        # it an identity, so the section says why it is not offered, and keeps the advisory.
        assert "AI troubleshooting is not offered here: edge-b&#39;s identity is not known" in ai
        assert "advisory" not in ai
        SL.record_advisory(NET, iid, device="edge-b", state="answered", passes=1,
                           words="AI analysis: asked for 2 reads; 2 run; answered", steps=[])
        ai = page(client, iid).split('id="inc-ai"', 1)[1].split("</section>", 1)[0]
        assert "AI analysis (advisory; self-healing never reads it)" in ai
        assert "asked for 2 reads; 2 run; answered" in ai

    def test_a_fixed_incident_with_no_ai_call_says_none_was_needed(self, client):
        ai = page(client, healed()).split('id="inc-ai"', 1)[1].split("</section>", 1)[0]
        assert "Not needed: Mercury fixed it without AI." in ai


class TestInARealBrowser:
    """In Firefox (where one runs; skipped naming why elsewhere): the one clock draws each
    recorded time in the viewer's zone, kept on their first visit and drawn by the server
    (`_macros.clock`, routes/v2.clock_words), with its date and to the second (the form this
    page adds), the zone named once on the page (one time zone per screen, docs/UI_RULES.md),
    and nothing on the page scrolls inside a card."""

    FORM = r"[A-Z][a-z]{2} \d{1,2} \d\d:\d\d:\d\d( \S+)?"

    def test_each_time_is_the_viewer_s_own_to_the_second_and_no_card_scrolls(self, client):
        from tests import browser

        ok, why = browser.available()
        if not ok:
            pytest.skip(f"no real browser here ({why}); the page's own checks above still run")
        import app as APP

        iid = healed()
        inc, _rows, _lines = raw(iid)
        detected = iso(inc["triggers"][0]["epoch"])
        kept = (I.read(NET), SL.read(NET), DS.read(NET))
        with browser.Served(APP.app) as srv, browser.Browser() as b:
            try:
                from tests.test_local_times import first_visit
                # The first visit keeps the browser's zone; the page opened again is drawn by
                # the server in it ("Sep 21 07:56:39", the zone beside the first time only).
                b.go(srv.url(f"/v2/incident/{iid}?list={NET}"))
                with first_visit():
                    b.go(srv.url(f"/v2/incident/{iid}?list={NET}"))
                    first = b.wait_for(
                        "var t = document.querySelector('[data-cell=detected] time');"
                        "return t && t.textContent")
                    drawn = b.js("return Array.prototype.map.call(document.querySelectorAll("
                                 "'.inc-head time'), function (t) { return t.textContent; })")
                    # Every clock on the page, as [its text, its hover].
                    clocks = b.js("return Array.prototype.map.call(document.querySelectorAll("
                                  "'time[data-clock]'), function (t) { return [t.textContent, "
                                  "t.title]; })")
                zone = b.js("return new Date(Date.parse(arguments[0])).getSeconds()", detected)
                scrolls = b.js(
                    "return Array.prototype.filter.call(document.querySelectorAll("
                    "'#incident-live *'), function (e) { var o = getComputedStyle(e);"
                    "return (o.overflowY === 'auto' || o.overflowY === 'scroll') && "
                    "e.scrollHeight > e.clientHeight + 1; }).length")
            finally:
                b.go("about:blank")
                browser.close_socketio_sessions()
        assert len(drawn) >= 6 and all(re.fullmatch(self.FORM, t) for t in drawn), drawn
        # One zone in the fixture's times: named beside one time on the page and no other.
        named = [t for t, _h in clocks if re.search(r"\d [A-Z][A-Za-z+0-9:-]+$", t)]
        assert len(named) == 1, ("the zone is named once on the page", clocks)
        assert all(re.fullmatch(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d UTC", h) for _t, h in clocks), \
            "each time's hover is its UTC instant"
        assert first.split()[2].endswith(f":{zone:02d}") and zone == int(detected[17:19]), \
            "the second drawn is the record's"
        assert scrolls == 0, "something scrolls inside the page"
        assert (I.read(NET), SL.read(NET), DS.read(NET)) == kept, \
            "the page, opened in a real browser, left the heal's stores as they were"


class TestTheWalksFixtures:
    """tests/fixtures/incident_page/ holds the stores as these builders left them, for the
    interface walk's provider (tests/v2_context.py `_incident_page`): each is still what its
    builder leaves, record for record and field for field (the ids and the times aside)."""

    @staticmethod
    def shape(incidents, decisions, steps):
        return (sorted((i["state"], i["device"], tuple(sorted(i))) for i in incidents),
                sorted((d.get("row"), d.get("outcome") or "", tuple(sorted(d)))
                       for d in decisions),
                sorted((r["row"], r.get("outcome") or "", tuple(sorted(r)),
                        tuple((x.get("step"), x.get("result")) for x in r.get("steps") or []))
                       for r in steps))

    @pytest.mark.parametrize("name, plant", [("healed", healed), ("failed", rolled_back),
                                             ("busy", busy)])
    def test_each_is_what_its_builder_leaves(self, client, name, plant):
        with open(os.path.join(os.path.dirname(__file__), "fixtures", "incident_page",
                               f"{name}.json"), encoding="utf-8") as fh:
            kept = json.load(fh)
        plant()
        with open(DS.path(NET), encoding="utf-8") as fh:
            lines = [json.loads(x) for x in fh if x.strip()]
        assert self.shape(kept["incidents"], kept["decisions"], kept["steps"]) == self.shape(
            I.read(NET)["incidents"], lines, SL.read(NET)["rows"])
        assert len(kept["steps"]) >= 2 and kept["page"].startswith("hi-")


def incident_links(body: str) -> list:
    """Every link to an incident's own page on a page, as ``(href, its words)``."""
    return re.findall(r'<a href="(/v2/incident/[^"]+)" data-incident="[^"]+"[^>]*>([^<]+)</a>',
                      unescape(body))


class TestOnePlacePerIncident:
    """Needs attention's rows for a heal incident and History's heal rows link to the one
    page per incident (the operator's item 5: "so the email and Needs attention link to one
    place per incident")."""

    def test_a_heal_row_on_history_opens_the_incident_beside_its_card(self, client):
        iid = healed()
        r = read(client, f"/v2/history?list={NET}&since=")     # every record, whatever its age
        body = r.get_data(as_text=True)
        assert incident_links(body) == [(f"/v2/incident/{iid}?list={NET}", "Open the incident")]
        line = re.search(r'<p class="small tl-links tl-card">.*?</p>', body, re.S).group(0)
        assert ">Open the card</a>" in line and "Open the incident" in line, \
            "the card's link stays, the incident's beside it"
        assert page(client, iid).count("<h1") == 1

    def test_a_decision_alone_has_no_card_and_still_opens_its_incident(self, client):
        iid = cant_fix()
        body = read(client, f"/v2/history?list={NET}&since=").get_data(as_text=True)
        assert incident_links(body) == [(f"/v2/incident/{iid}?list={NET}", "Open the incident")]
        assert ">Open the card</a>" not in body, "a decision alone ran nothing"

    def test_a_heal_row_on_needs_attention_opens_its_incident(self, client, monkeypatch):
        from modules import attention

        iid = cant_fix()
        monkeypatch.setattr(attention, "SOURCES", [attention.heal_source])
        # The heal's lab decides at T0, in 2026-09: the row's window is widened to reach it.
        monkeypatch.setattr(attention, "CANT_FIX_DAYS", 10 ** 5)
        body = read(client, f"/v2/attention?list={NET}").get_data(as_text=True)
        assert incident_links(body) == [(f"/v2/incident/{iid}?list={NET}", "Open the incident")]
        row = body.split(f'data-incident="{iid}"', 1)[0].rsplit('data-attention-row="', 1)[1]
        assert row.startswith("heal:"), "the link is on the incident's own row"

    def test_a_row_about_no_one_incident_links_none(self):
        from modules import attention

        rows = [{"operands": {"list": NET}}, {"operands": {"incident": "hd-0123456789ab"}},
                {"operands": {"incident": "hi-0123456789ab"}}]
        attention._link_incident_pages(NET, rows)
        assert [r.get("incident_page") for r in rows] == [
            None, None, {"id": "hi-0123456789ab", "list": NET}]

    def test_only_an_id_the_page_takes_is_linked(self):
        """A notification's row also names an incident: its value stays words."""
        from modules import history_sources as H

        row = H._event("2026-11-11T00:00:00Z", "notification", "a notice", ["edge-b"],
                       record=[("Incident", "hi-0123456789ab")])
        assert "incident_page" not in row


# ── The operator's test of the page, 2026-11-13: "structure PASSES. Fixes, as one slice" ──

#: The fault each planted drill expects, in its declaration's words.
EXPECTS = "an IPv4 route added on edge-b"


def declare(at=DETECTED - 30):
    """A fault drill on edge-b declared BEFORE its fault (the declaration's one writer,
    `fault_drills.record_declared`), covering the planted incidents' sight at T0 - 1000: its
    record."""
    from modules import fault_drills

    got = fault_drills.record_declared(
        NET, "edge-b", minutes=10, expects=EXPECTS, by="op@example.com",
        actor_verified="access", via="test", now=at,
        inventory=lambda _n, d: {"hostname": d, "_netbox_id": 41})
    assert got["ok"], got
    return got["record"]


def stage(body, key):
    """One of the heal's five stages as drawn: ``(its sentence, its time)``, in words."""
    m = re.search(rf'<li class="run-stage[^"]*" data-stage="{key}".*?<summary>(.*?)</summary>',
                  body, re.S)
    assert m, f"no {key} stage is drawn"
    said = re.search(r'<span class="run-stage-said"[^>]*>(.*?)</span>\s*<span class="run-stage-'
                     r'time">', m.group(1), re.S)
    when = re.search(r'<span class="run-stage-time">(.*)</span>', m.group(1), re.S)
    return text_of(said.group(1)), text_of(when.group(1))


def act_steps(iid):
    _inc, rows, _lines = raw(iid)
    (act_row,) = [r for r in rows if r["row"] == "act"]
    return act_row["steps"]


def heal_with(src, running, kinds=("added_line",)):
    """One incident decided in Auto and acted on by the real act over *src* (an act's fake
    sources), its steps 7 s apart (`Ticking`): its id, healed."""
    auto(NET, now=T0 - 60, kinds=kinds)
    settle(running, triggers=[CFG], claim=False)
    (d,) = DC.run(NET, now=T0, sources=Fake(running))["decided"]
    assert d["outcome"] == "heal", d
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("modules.heal.act.time", Ticking())
        got = A.act_one(NET, d["decision"], now=T0 + 5, sources=src)
    assert got["outcome"] == "healed", got["words"]
    return d["incident"]


class HeldBGP(FakeAct):
    """The act's sources, whose apply's deploy verify waited out BGP's hold first: *watch* is
    the pipeline's own record of that wait (`pipeline._watch_bgp_hold`, on r3's real
    captures), and the act's clock moves by the seconds it watched, as the deploy's sleep
    moves the wall clock."""

    def __init__(self, running, watch, **kw):
        super().__init__(running, **kw)
        self.watch = watch

    def apply(self, device, **kw):
        inner = kw["after_verify"]

        def after_verify(host, r, ctx):
            from modules.heal import act

            act.time.now += self.watch["watched_s"]
            return inner(host, dict(r, verify={"bgp_watch": self.watch}), ctx)

        return super().apply(device, **dict(kw, after_verify=after_verify))


@pytest.fixture
def bgp_watch(world):
    """The pipeline's verify watching r3's real BGP sessions to their hold time (IOS's 180 s)
    and finding them held: its ``bgp_watch``, as the deploy's row carries it."""
    from modules import pipeline

    ctx, _clock = world(_summary())
    pipeline._stage_verify(ctx)
    watch = ctx.verify_result["x"]["bgp_watch"]
    assert (watch["state"], watch["hold_s"], watch["watched_s"]) == ("converged", 180, 180)
    return watch


class TestADrillSaysSo:
    """1. "A drill's incident says so": a Drill tag beside the state (its fd- id on hover) and
    beside its link on Needs attention, keyed on the tag the incident took at its creation
    (`fault_drills.tag_of`), never on a name; a real incident has none."""

    def test_a_drill_s_incident_carries_the_tag_and_its_drill_s_id(self, client):
        drill = declare()
        iid = healed()
        inc, _rows, _lines = raw(iid)
        assert inc["fault_drill"]["id"] == drill["id"], "the premise: tagged at creation"
        body = page(client, iid)
        head = body.split('class="card inc-head', 1)[1].split("</section>", 1)[0]
        (tag,) = re.findall(r'<span class="inc-drill" data-drill="([^"]+)">(.*?)</span></span>',
                            head, re.S)
        assert tag[0] == drill["id"] and tag[0].startswith("fd-")
        assert text_of(tag[1]) == "Drill"
        hover = unescape(re.search(r'title="([^"]+)"', tag[1]).group(1))
        assert hover.startswith(f"Fault drill {drill['id']}, declared by op before its fault")
        assert EXPECTS in hover and "op@example.com" not in hover
        record = unescape(body.split("inc-record", 1)[1])
        assert f"{drill['id']}, declared by op@example.com: {EXPECTS}" in record

    def test_a_real_incident_never_carries_it(self, client):
        body = page(client, healed())
        assert "inc-drill" not in body and "data-drill" not in body
        assert "Fault drill" not in body

    def test_the_tag_is_the_record_s_never_a_word(self):
        """A drill's id in the words alone tags nothing; the tag on any of the incident's own
        records does."""
        tag = {"id": "fd-0123456789", "declared_by": "op@example.com", "expects": EXPECTS,
               "until": "2026-09-21T14:00:00Z"}
        words = {"incident": {"id": "hi-0123456789ab", "closed_why": "fd-0123456789 drill"},
                 "entry": {"words": "Fault drill fd-0123456789"}, "decisions": []}
        assert IP.drill_tag(words) is None
        for where in ("incident", "entry"):
            assert IP.drill_tag(dict(words, **{where: {"fault_drill": tag}}))["id"] == tag["id"]
        assert IP.drill_tag(dict(words, decisions=[{"fault_drill": tag}]))["id"] == tag["id"]

    def test_needs_attention_s_row_for_a_drill_says_drill_beside_its_link(self, client,
                                                                         monkeypatch):
        from modules import attention

        drill = declare()
        iid = cant_fix()
        monkeypatch.setattr(attention, "SOURCES", [attention.heal_source])
        monkeypatch.setattr(attention, "CANT_FIX_DAYS", 10 ** 5)
        body = read(client, f"/v2/attention?list={NET}").get_data(as_text=True)
        assert incident_links(body) == [(f"/v2/incident/{iid}?list={NET}", "Open the incident")]
        line = re.search(r'<p class="small att-incident">.*?</p>', body, re.S).group(0)
        assert f'data-drill="{drill["id"]}"' in line and text_of(line) == \
            "Open the incident Drill"


class TestItEndsWhenItsFixIsVerified:
    """2. "The incident ends when its fix is verified ... not at 20:42:07": the act stamps its
    store's close with the time its job started, so the header's span and the timeline's
    close are its act's record step, the verify that passed."""

    def test_the_span_and_the_close_are_the_verify_never_the_act_s_start(self, client):
        iid = healed()
        inc, _rows, lines = raw(iid)
        verified = next(s["at"] for s in act_steps(iid)
                        if s["step"] == "record" and s["result"] == "healed")
        taken = next(x["at"] for x in lines if x.get("row") == "taken")
        assert inc["closed_at"] == taken != verified, \
            "the premise, as the host's record held it: the store's close is the act's start"
        body = page(client, iid)
        span = re.search(r'<span class="inc-span">(.*?)</span> <span class="inc-ro">', body,
                         re.S).group(1)
        assert times_in(span) == [iso(inc["triggers"][0]["epoch"]), verified]
        events = re.findall(r"<li>(<time [^>]*>[^<]*</time>): (.*?)</li>",
                            body.split('class="inc-event-list"', 1)[1].split("</ol>", 1)[0])
        closed = [times_in(t) for t, words in events if words == "the incident closed"]
        assert closed == [[verified]], events
        tl = IP.timeline(*model(iid))
        assert (tl["closed"], tl["ended"]) == (verified, verified)
        record = unescape(body.split("inc-record", 1)[1])
        assert f"{inc['closed_at']}: {inc['closed_why']}" in record, "kept as recorded"
        assert "Closed, by its act's record step (UTC)" in record

    def test_a_close_no_act_made_is_its_store_s(self, client):
        """A decision that closed its incident (a cleared one) stamped its own time."""
        iid = cant_fix()
        I.close(NET, iid, "nothing: it went back by itself (decision hd-000000000000)", T0 + 9)
        tl = IP.timeline(*model(iid))
        assert tl["closed"] == iso(T0 + 9)


class TestFixingShowsItsWholeDuration:
    """3. "Fixing shows its whole duration, including waits: e.g. "applied 3 lines (11 s),
    then waited out r3's BGP hold (180 s)", from the recorded step times."""

    def test_the_apply_ends_where_the_next_step_began(self, client):
        from modules.run_stepper import duration_words

        iid = healed()
        steps = act_steps(iid)
        (apply,) = [s for s in steps if s["step"] == "apply"]
        intent = next(s for s in steps if s["step"] == "intent")
        first = min(seconds(s["at"]) for s in steps if s.get("at"))
        assert apply["result"] == "running", "the premise: the act writes no end of its apply"
        said, when = stage(page(client, iid), "fixing")
        assert said == "Applied 1 line to edge-b"
        assert when.endswith(" · " + duration_words(seconds(intent["at"]) - first)), when

    def test_a_wait_the_deploy_s_verify_made_is_said_inside_it(self, client, bgp_watch):
        from modules.run_stepper import duration_words

        iid = heal_with(HeldBGP(GOLDEN + ROUTE4, bgp_watch), GOLDEN + ROUTE4)
        steps = act_steps(iid)
        intent = next(s for s in steps if s["step"] == "intent")
        assert intent["bgp_hold"] == {"hold_s": 180, "watched_s": 180}
        whole = seconds(intent["at"]) - min(seconds(s["at"]) for s in steps if s.get("at"))
        said, when = stage(page(client, iid), "fixing")
        assert said == (f"Applied 1 line to edge-b ({duration_words(whole - 180)}), then "
                        "waited out edge-b's BGP hold (3 min)"), said
        assert when.endswith(" · " + duration_words(whole)) and whole > 180, when


class TestOneDuration:
    """4. "One duration everywhere": TIME TO REPAIR and Done from the same two recorded times
    (the first trigger's receive time, the act's record step), by one function, in one
    format."""

    def test_time_to_repair_and_done_say_one_duration(self, client):
        from modules.run_stepper import duration_words

        iid = healed()
        inc, _rows, _lines = raw(iid)
        verified = next(s["at"] for s in act_steps(iid) if s["step"] == "record")
        ttr = seconds(verified) - int(inc["triggers"][0]["epoch"])
        assert int(inc["opened_epoch"]) != int(inc["triggers"][0]["epoch"]), \
            "the premise: Mercury's sight and the trigger's receive time differ"
        body = page(client, iid)
        assert text_of(cell(body, "ttr")).split(" · ")[0].endswith(
            f"{ttr:,} s ({duration_words(ttr)})")
        said, _when = stage(body, "done")
        assert said == f"Healed and verified in {duration_words(ttr)}", said

    def test_no_time_is_worded_in_python(self, client):
        body = page(client, healed())
        hover = unescape(re.search(r'data-cell="ttr" title="([^"]+)"', body).group(1))
        assert hover.startswith("From Detected, when ") and "to Verified, when" in hover
        assert "UTC" not in hover and not re.search(r"\d\d:\d\d", hover), hover

    def test_the_one_format_reaches_days(self):
        from modules.run_stepper import duration_words

        assert [duration_words(s) for s in (45, 399, 3780, 330612, 86400)] == [
            "45 s", "6 min 39 s", "1 h 3 min", "3 d 19 h 50 min", "1 d"]


class TestLinesAsAPersonCountsThem:
    """5. "3 lines, not 4": a sub-mode's exit is not a line re-applied; one count
    (`deploy.config_line_count`) wherever the count is drawn."""

    APPLET = ("event manager applet HB\n event timer watchdog time 60\n"
              " action 1 syslog msg heartbeat\n")

    def test_a_stanza_put_back_is_its_three_lines(self, client):
        running = GOLDEN.replace(self.APPLET, "")
        iid = heal_with(FakeAct(running), running, kinds=("missing_line",))
        _inc, entry, _d = model(iid)
        assert entry["program"][-1] == "exit" and len(entry["program"]) == 4, \
            "the premise: the program sends the applet's three lines and the exit"
        body = page(client, iid)
        said, _when = stage(body, "fixing")
        assert said == "Applied 3 lines to edge-b", said
        record = unescape(body.split("inc-record", 1)[1])
        assert re.search(r"<dt>Program</dt><dd>3 line\(s\), hash ", record)
        decided = next(s for s in entry["steps"] if s["step"] == "classify")
        plan = next(s for s in act_steps(iid) if s["step"] == "plan")
        assert "the fix 3 line(s)" in decided["words"] and ": 3 line(s)," in plan["words"]

    def test_the_count_leaves_out_every_sub_mode_exit(self):
        from modules.nsot import receipts
        from modules.nsot.deploy import config_line_count

        program = ["router bgp 65001", " address-family ipv4", "  neighbor 192.0.2.1 activate",
                   " exit-address-family", "exit", "!", "", "ipv6 route 2001:db8:9::/48 Null0"]
        assert config_line_count(program) == 4
        assert receipts.config_lines({"program": program}) == 4, "the receipt's count is it"


class TestTheTagAndTheEndInARealBrowser:
    """In Firefox (where one runs; skipped naming why elsewhere): a drill's page shows its Drill
    tag beside the state, its drill's id on hover, and the header's span and the timeline's
    close end at the verify that passed; once the drill is ended, the page drawn again when
    self-healing announces keeps the tag (the incident's, from its creation) and the end."""

    #: What the page draws of the tag and the end, read in the browser.
    READ = ("var t = document.querySelector('.inc-head .inc-line .inc-drill .badge');"
            "var s = document.querySelectorAll('.inc-span time');"
            "var c = Array.prototype.filter.call(document.querySelectorAll('.inc-event-list li'),"
            " function (l) { return /: the incident closed$/.test(l.textContent); });"
            "return t && [t.textContent, t.title, t.getBoundingClientRect().width > 0,"
            " t.closest('.inc-drill').previousElementSibling.dataset.state,"
            " s.length && s[s.length - 1].getAttribute('datetime'),"
            " c.map(function (l) { return l.querySelector('time').getAttribute('datetime'); })]")

    def test_the_drill_tag_and_the_end_are_drawn_and_kept(self, client):
        from modules import fault_drills
        from tests import browser

        ok, why = browser.available()
        if not ok:
            pytest.skip(f"no real browser here ({why}); the page's own checks above still run")
        import app as APP

        drill = declare()
        iid = healed()
        verified = next(s["at"] for s in act_steps(iid) if s["step"] == "record")
        with browser.Served(APP.app) as srv, browser.Browser() as b:
            try:
                b.go(srv.url(f"/v2/incident/{iid}?list={NET}"))
                first = b.wait_for(self.READ)
                ended = fault_drills.record_ended(NET, drill["id"], by="op@example.com",
                                                  actor_verified="access", via="test",
                                                  now=T0 - 900)
                assert ended["ok"], ended
                # Self-healing's announcement, as the page's relay fires it; the region's own
                # request answered and settled is the redraw.
                b.js("window.__incDrawn = 0; document.body.addEventListener('htmx:afterSettle',"
                     " function (e) { var d = e.detail || {}; var p = (d.pathInfo || {})"
                     ".requestPath || (d.requestConfig || {}).path || '';"
                     " if (p.indexOf('/v2/incident/') === 0) window.__incDrawn++; });"
                     "document.body.dispatchEvent(new CustomEvent('nmas:drift')); return 1")
                again = b.wait_for("return window.__incDrawn > 0 && (function () {"
                                   + self.READ + "})()", 15)
            finally:
                b.go("about:blank")
                browser.close_socketio_sessions()
        assert first[0] == "Drill" and first[2], first
        assert first[1].startswith(f"Fault drill {drill['id']}, declared by op"), first
        assert first[3] == "fixed", "the tag sits beside the state"
        assert first[4:] == [verified, [verified]], "the span and the close end at the verify"
        assert again == first, "ending the drill changes no incident already tagged"
