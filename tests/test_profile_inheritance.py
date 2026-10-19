"""K11 (the operator, 2026-10-18: "a network with no profile still gets monitoring"): a network
that inherits from Default (P.8's mode) and has no monitoring profile of its own takes
Default's, as a setting would.

- its own profile wins; an inheriting network with none takes Default's, named as Default's;
  a standalone network with none has none; Default with none has none; a broken profile
  raises, never read as none;
- the render (`profile.effective_for`) and onboarding's profile step (`profile_apply`) take
  the inherited profile, so the lines a ZTP device receives at Verify are the lines its intent
  renders;
- the Monitoring › Profile page says the profile is inherited, and from where.
"""

import pytest

from modules import list_settings as L
from modules.nsot import profile as P

DEFAULT_DOC = {"sections": {"syslog": {"applies": {}, "data": {"logging_hosts": ["192.0.2.5"]}}}}
OWN_DOC = {"sections": {"ntp": {"applies": {}, "data": {"ntp_servers": ["192.0.2.6"]}}}}


class _Ref:
    def __init__(self, name):
        self.name, self.repo_dir = name, f"/repos/{name}"


@pytest.fixture
def world(monkeypatch):
    """Committed profiles by repository, and each network's settings mode."""
    docs = {"/repos/Default": DEFAULT_DOC}
    modes = {"Lab9": L.INHERIT, "Alone": L.STANDALONE, "Own": L.INHERIT}

    def read_committed(repo):
        got = docs.get(repo)
        if got == "broken":
            raise P.ProfileRefused("profiles/monitoring.yml at HEAD is not a profile")
        return got

    monkeypatch.setattr(P, "read_committed", read_committed)
    monkeypatch.setattr(L, "mode", lambda name: modes[name])
    monkeypatch.setattr("modules.nsot.listref.resolve", lambda name: _Ref(name))
    return docs


class TestWhichProfileANetworkTakes:
    def test_an_inheriting_network_with_none_takes_default_s(self, world):
        assert P.read_for("Lab9", "/repos/Lab9") == {"doc": DEFAULT_DOC, "from": "Default"}

    def test_its_own_profile_wins(self, world):
        world["/repos/Own"] = OWN_DOC
        assert P.read_for("Own", "/repos/Own") == {"doc": OWN_DOC, "from": "Own"}

    def test_a_standalone_network_with_none_has_none(self, world):
        assert P.read_for("Alone", "/repos/Alone") == {"doc": None, "from": ""}

    def test_default_with_none_has_none(self, world):
        world.pop("/repos/Default")
        assert P.read_for("Default", "/repos/Default") == {"doc": None, "from": ""}
        assert P.read_for("Lab9", "/repos/Lab9") == {"doc": None, "from": ""}

    def test_a_broken_default_profile_raises_never_none(self, world):
        world["/repos/Default"] = "broken"
        with pytest.raises(P.ProfileRefused):
            P.read_for("Lab9", "/repos/Lab9")


class TestTheRenderAndOnboardingTakeIt:
    def test_effective_for_renders_default_s_sections(self, world, monkeypatch):
        monkeypatch.setattr(P, "role_of", lambda ln, host: "router")
        got = P.effective_for("/repos/Lab9", "Lab9", "tw-ztp-a", {"hostname": "tw-ztp-a"},
                              "cisco_iosxe")
        assert got.get("logging_hosts") == ["192.0.2.5"], got

    def test_a_standalone_network_renders_its_intent_unchanged(self, world, monkeypatch):
        monkeypatch.setattr(P, "role_of", lambda ln, host: "router")
        intent = {"hostname": "a1"}
        assert P.effective_for("/repos/Alone", "Alone", "a1", intent, "cisco_iosxe") == intent

    def test_onboarding_s_profile_step_reads_the_inherited_profile(self, world, monkeypatch):
        """`profile_apply.for_capture` (Verify's preview, phase 2's profile step) asks
        `read_for`, so its 'no profile' answer comes only when nothing is inherited either."""
        from modules.nsot import profile_apply
        asked = []
        monkeypatch.setattr(P, "read_for",
                            lambda ln, repo: asked.append(ln) or {"doc": None, "from": ""})
        got = profile_apply.for_capture("Lab9", "tw-ztp-a", "cisco_iosxe", "router",
                                        "hostname tw-ztp-a\n", repo="/repos/Lab9")
        assert asked == ["Lab9"] and not got["applies"]
        assert "inherits none from Default" in got["why"]


class TestTheProfilePageSaysWhereItComesFrom:
    def test_an_inherited_profile_is_named_as_default_s(self, world, monkeypatch):
        from modules import monitoring_coverage, monitoring_profile_page as MP
        monkeypatch.setattr(monitoring_coverage, "fleet", lambda ref: {"profile": {}})
        got = MP.sections(_Ref("Lab9"))
        assert got["committed"] and got["inherited_from"] == "Default"

    def test_its_own_profile_names_no_inheritance(self, world, monkeypatch):
        from modules import monitoring_coverage, monitoring_profile_page as MP
        monkeypatch.setattr(monitoring_coverage, "fleet", lambda ref: {"profile": {}})
        world["/repos/Own"] = OWN_DOC
        got = MP.sections(_Ref("Own"))
        assert got["committed"] and got["inherited_from"] == ""

    def test_the_template_draws_it(self):
        from app import app
        with app.test_request_context("/v2/monitoring/profile"):
            from flask import render_template
            html = render_template("v2/_profile_table.html", p={
                "list": "Lab9", "ok": True, "error": "", "committed": True, "rows": [],
                "not_rendered": 0, "inherited_from": "Default", "commit": "", "committed_at": ""})
        assert "Lab9 has no profile of its own, so its devices take Default's" in html
