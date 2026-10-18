"""Decline… and Undo decline… (C718; board C603's C718 page, APPROVED 2026-10-13): a person
declines a profile section on one device with a reason; it is one `profile_exclude` entry in the
device's committed intent with who and when, previewed, confirmed by hash as a verified person,
committed once, and read by Coverage and the IP SLA page as declined, never as a gap. Nothing is
sent to the device.

On a real repository: r2's real config as its golden and its full intent seeded from it
(tests/test_seed_intent's lab).
"""

import html as html_mod
import re
import subprocess

import pytest

from tests.conftest import TEST_PERSON
from tests.test_seed_intent import LIST, build_seed_lab

HOST = "r2"
WHY = "r2's only upstream carries the management path; a probe would load it"


def _git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True,
                          text=True).stdout.strip()


@pytest.fixture
def lab(tmp_path, monkeypatch):
    return make_lab(tmp_path, monkeypatch)


def make_lab(tmp_path, monkeypatch):
    """The lab, callable outside a fixture (the board shot builds the same one)."""
    from modules.nsot import seed

    from modules.nsot import hostvars
    from modules.nsot.repo import save_host_vars

    lab = build_seed_lab(monkeypatch, tmp_path)
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == LIST)
    entry = seed.entry_for(LIST, lab["device"])
    assert seed.apply(LIST, [lab["device"]], {HOST: entry["hash"]}, "t")["save"]["ok"]
    # r2's real config runs a probe; the decline's case is a device with none (r6's), so its
    # probes leave intent first, one commit of their own.
    doc = hostvars.read_committed(lab["repo"], HOST)
    if doc.pop("ip_sla", None) is not None or doc.pop("ip_sla_schedules", None) is not None:
        doc.pop("ip_sla_schedules", None)
        hostvars.write_committed(lab["repo"], doc)
        assert save_host_vars(LIST, [HOST], actor="t", message="no probes")["ok"]
    return lab


def _card(lab, **args):
    q = "&".join(f"{k}={v}" for k, v in {"list": LIST, "device": HOST, "section": "ip_sla",
                                           **args}.items())
    r = lab["client"].get(f"/v2/monitoring/decline?{q}")
    assert r.status_code == 200
    return r.get_data(as_text=True)


def _confirm_form(card):
    form = card[card.index('class="op-ft"'):]
    form = form[:form.index("</form>")]
    return {m.group(1): html_mod.unescape(m.group(2))
            for m in re.finditer(r'<input type="hidden" name="([a-z]+)" value="([^"]*)">', form)}


class TestTheEntry:
    def test_without_a_reason_it_is_shown_and_not_ready(self, lab):
        from modules.nsot import decline
        e = decline.entry(LIST, HOST, "ip_sla", reason="", actor=TEST_PERSON)
        assert e["error"] == "" and not e["ready"] and e["hash"] == ""
        assert "too short to be a reason" in e["blocked"] or "no reason" in e["blocked"]

    def test_a_reason_and_a_person_make_it_ready_and_the_diff_names_both(self, lab):
        from modules.nsot import decline
        e = decline.entry(LIST, HOST, "ip_sla", reason=WHY, actor=TEST_PERSON)
        assert e["ready"] and e["hash"]
        added = "\n".join(l for l in e["diff"] if l.startswith("+"))
        assert "section: ip_sla" in added and WHY in added and TEST_PERSON in added
        assert ("pass", "the reason has three words or more") in e["checks"]

    def test_no_verified_person_is_a_failing_check(self, lab):
        from modules.nsot import decline
        e = decline.entry(LIST, HOST, "ip_sla", reason=WHY, actor="")
        assert not e["ready"] and "verified person" in e["blocked"]

    def test_an_unknown_section_is_refused(self, lab):
        from modules.nsot import decline
        assert "not a section" in decline.entry(LIST, HOST, "bgp", reason=WHY,
                                                actor=TEST_PERSON)["error"]

    def test_probes_in_intent_are_refused_naming_them(self, lab):
        from modules.nsot import decline, hostvars
        from modules.nsot.repo import save_host_vars
        doc = hostvars.read_committed(lab["repo"], HOST)
        # r2's real probe, as its captured intent holds it (tests/fixtures/committed/r2.yml).
        doc["ip_sla"] = [{"id": "1", "settings": [" icmp-echo 192.0.2.1 source-interface "
                                                  "Loopback0", "  frequency 10"]}]
        hostvars.write_committed(lab["repo"], doc)
        assert save_host_vars(LIST, [HOST], actor="t", message="probe")["ok"]
        e = decline.entry(LIST, HOST, "ip_sla", reason=WHY, actor=TEST_PERSON)
        assert "ip sla 1: icmp-echo 192.0.2.1" in e["error"]
        assert "remove them first" in e["error"]


class TestTheApply:
    def test_one_commit_as_the_person_then_read_as_declined(self, lab):
        from modules.nsot import decline, hostvars, profile
        e = decline.entry(LIST, HOST, "ip_sla", reason=WHY, actor=TEST_PERSON)
        before = _git(lab["repo"], "rev-parse", "HEAD")
        out = decline.apply(LIST, HOST, "ip_sla", e["hash"], actor=TEST_PERSON, reason=WHY,
                            at=e["at"])
        assert out["outcome"] == "declined", out
        assert _git(lab["repo"], "rev-list", "--count", f"{before}..HEAD") == "1"
        msg = _git(lab["repo"], "log", "-1", "--format=%B")
        assert "Source: decline" in msg and f"Actor: {TEST_PERSON}" in msg
        assert "Section: ip_sla" in msg
        doc = hostvars.read_committed(lab["repo"], HOST)
        assert profile.excluded(doc) == {"ip_sla": WHY}
        d = decline.declines(doc)["ip_sla"]
        assert d["by"] == TEST_PERSON and d["at"] == e["at"]

    def test_another_person_confirming_is_refused_as_moved(self, lab):
        from modules.nsot import decline
        e = decline.entry(LIST, HOST, "ip_sla", reason=WHY, actor=TEST_PERSON)
        out = decline.apply(LIST, HOST, "ip_sla", e["hash"], actor="other@example.invalid",
                            reason=WHY, at=e["at"])
        assert out["outcome"] == "moved" and "nothing was committed" in out["reason"]

    def test_a_moved_intent_is_refused(self, lab):
        from modules.nsot import decline, hostvars
        from modules.nsot.repo import save_host_vars
        e = decline.entry(LIST, HOST, "ip_sla", reason=WHY, actor=TEST_PERSON)
        doc = hostvars.read_committed(lab["repo"], HOST)
        doc["ntp_servers"] = list(doc.get("ntp_servers") or []) + ["192.0.2.123"]
        hostvars.write_committed(lab["repo"], doc)
        assert save_host_vars(LIST, [HOST], actor="t", message="ntp")["ok"]
        out = decline.apply(LIST, HOST, "ip_sla", e["hash"], actor=TEST_PERSON, reason=WHY,
                            at=e["at"])
        assert out["outcome"] == "moved"

    def test_undo_removes_it_in_a_second_commit(self, lab):
        from modules.nsot import decline, hostvars, profile
        e = decline.entry(LIST, HOST, "ip_sla", reason=WHY, actor=TEST_PERSON)
        assert decline.apply(LIST, HOST, "ip_sla", e["hash"], actor=TEST_PERSON, reason=WHY,
                             at=e["at"])["outcome"] == "declined"
        u = decline.entry(LIST, HOST, "ip_sla", actor=TEST_PERSON, undo=True)
        assert u["ready"] and any(l.startswith("-") and WHY in l for l in u["diff"])
        out = decline.apply(LIST, HOST, "ip_sla", u["hash"], actor=TEST_PERSON, undo=True)
        assert out["outcome"] == "undone", out
        assert profile.excluded(hostvars.read_committed(lab["repo"], HOST)) == {}
        assert "undoes the decline of IP SLA" in _git(lab["repo"], "log", "-1", "--format=%s")


class TestTheCard:
    def test_the_card_previews_writes_nothing_and_confirms_in_place(self, lab):
        head = _git(lab["repo"], "rev-parse", "HEAD")
        card = _card(lab)
        assert "Decline IP SLA on r2" in card and "<textarea" in card
        assert "Not ready to record" in card and "op-confirm" not in card
        card = _card(lab, reason=WHY.replace(" ", "+").replace(";", "%3B").replace("'", "%27"))
        assert "Record the decline in r2&#39;s intent" in card or \
            "Record the decline in r2's intent" in card
        assert _git(lab["repo"], "rev-parse", "HEAD") == head, "a preview commits nothing"
        vals = _confirm_form(card)
        assert vals["hash"] and vals["reason"] == WHY
        r = lab["client"].post("/v2/monitoring/decline/confirm", data=vals)
        out = r.get_data(as_text=True)
        assert r.status_code == 200 and "IP SLA declined on r2" in out and "op-ok" in out
        assert "default-src" in r.headers.get("Content-Security-Policy", "")
        assert _git(lab["repo"], "rev-parse", "HEAD") != head

    def test_a_confirm_without_a_hash_is_refused_by_name(self, lab):
        r = lab["client"].post("/v2/monitoring/decline/confirm",
                               data={"list": LIST, "device": HOST, "section": "ip_sla"})
        assert r.status_code == 400 and "carried no preview hash" in r.get_data(as_text=True)


def test_ip_sla_suggests_nothing_for_a_declined_device():
    from modules.nsot import ip_sla_policy
    intents = {"r6": {"profile_exclude": [{"section": "ip_sla", "reason": WHY,
                                           "by": "op@example.invalid",
                                           "at": "2026-10-13T14:05:00Z"}]}}
    got = ip_sla_policy.suggest(intents, {"r6": {}}, {"policy": "upstream"}, ["r6"])
    assert got["suggestions"] == []
    [k] = got["skipped"]
    assert k["device"] == "r6" and k["declined"]["by"] == "op@example.invalid"
    assert k["why"].startswith("declined by op@example.invalid, 2026-10-13:")


def test_coverage_draws_every_cell_s_meaning_and_the_profile_counts_the_decline(
        lab, monkeypatch):
    """C1305 (the operator's walk, 2026-10-18): a Coverage cell is never blank. A section the
    profile scopes away from the device says "n/a" with why on hover; a declined one draws its
    own mark, who and why on hover, and links its Undo decline row; the legend has no
    "blank"; the Profile tab's chip counts the declined ("8 of 9 hold it · 1 declined"), where
    it said "8 of 9" and nothing of the ninth."""
    import app as A
    import routes.v2 as v2
    from modules import monitoring_coverage as MC
    from modules import monitoring_profile_page as MP
    from modules.nsot import decline, listref, profile

    ref = listref.resolve(LIST)

    def fleet():
        return MC.fleet(ref, devices=[(ref, dict(lab["device"]))],
                        report=(None, "", "no reporting reader in this test"))

    row = next(r for r in fleet()["devices"] if r["host"] == HOST)
    col = next(k for k, _w in MC.COLUMNS
               if MC._SECTION_OF_COLUMN.get(k) in profile.SECTIONS            # noqa: SLF001
               and row["cells"][k]["state"] not in ("ok", "not_reporting", "unknown"))
    section = MC._SECTION_OF_COLUMN[col]                                       # noqa: SLF001
    e = decline.entry(LIST, HOST, section, reason=WHY, actor=TEST_PERSON)
    assert decline.apply(LIST, HOST, section, e["hash"], actor=TEST_PERSON, reason=WHY,
                         at=e["at"])["outcome"] == "declined"
    c = fleet()
    c["not_covered"] = []
    monkeypatch.setattr(v2, "_coverage", lambda: c)
    html = A.app.test_client().get(f"/v2/monitoring/coverage?list={LIST}").get_data(as_text=True)
    cells = re.findall(r'<td class="gc" data-state="([a-z_]+)"[^>]*>(.*?)</td>', html, re.S)
    assert cells, html[:400]
    for state, inner in cells:
        if state in ("declined", "not_applicable", "excluded", "unused"):
            seen = re.sub(r'<span class="sr-only">.*?</span>', "", inner, flags=re.S)
            assert re.sub(r"<[^>]+>|\s", "", seen) or "<svg" in seen, \
                f"a {state} cell draws nothing visible: {inner!r}"
    declined = re.search(r'<td class="gc" data-state="declined"[^>]*>(.*?)</td>', html, re.S)
    assert declined, "the declined cell is drawn as its own state"
    anchor = f"decl-{HOST}-{section}"
    assert f'href="#{anchor}"' in declined.group(1) and TEST_PERSON in declined.group(1) \
        and WHY in html_mod.unescape(declined.group(1)), declined.group(1)
    assert f'id="{anchor}"' in html, "the Undo decline row is what the mark links"
    legend = re.search(r'<p class="cov-legend[^"]*">(.*?)</p>', html, re.S).group(1)
    assert "blank" not in legend and "n/a" in legend and "declined" in legend, legend
    held = MP._held(c, section)                                                # noqa: SLF001
    assert held.get("declined") == [HOST], held


def test_coverage_reads_a_decline_as_declined_with_who_when_and_why(lab):
    """Board C: on Coverage the declined section is its own state, counted as declined, with
    who, when and why; never a gap. The section is one r2's golden does not configure (a
    configured one is drawn configured whatever intent says)."""
    from modules import monitoring_coverage as MC
    from modules.nsot import decline, listref, profile

    ref = listref.resolve(LIST)

    def fleet():
        return MC.fleet(ref, devices=[(ref, dict(lab["device"]))],
                        report=(None, "", "no reporting reader in this test"))

    got = fleet()
    row = next(r for r in got["devices"] if r["host"] == HOST)
    col = next(k for k, _w in MC.COLUMNS
               if MC._SECTION_OF_COLUMN.get(k) in profile.SECTIONS            # noqa: SLF001
               and row["cells"][k]["state"] not in ("ok", "not_reporting", "unknown"))
    section = MC._SECTION_OF_COLUMN[col]                                       # noqa: SLF001
    e = decline.entry(LIST, HOST, section, reason=WHY, actor=TEST_PERSON)
    assert decline.apply(LIST, HOST, section, e["hash"], actor=TEST_PERSON, reason=WHY,
                         at=e["at"])["outcome"] == "declined"
    c = fleet()
    cell = next(r for r in c["devices"] if r["host"] == HOST)["cells"][col]
    assert cell["state"] == "declined", cell
    assert cell["words"].startswith(f"declined by {TEST_PERSON}, ") and WHY in cell["words"]
    assert [(d["host"], d["section"], d["by"]) for d in c["declined"]] == \
        [(HOST, section, TEST_PERSON)]
    assert col not in next(r for r in c["devices"] if r["host"] == HOST)["gaps"]
