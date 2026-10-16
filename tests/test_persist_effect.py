"""C886 (the operator's walk W1, section I, 2026-10-16): Persist's preview
(`/v2/device/r6?op=persist`) did not show which lines startup would gain or lose, though the
Reload check that sends a person there knows them. C913 (found fixing C881): Adopt's persist
preview compared startup with running directly (`configs_equivalent`), so on a C8000v it named
C881's false differences, the startup header and the CA certificate's storage.

Both now draw `persist_op.startup_effect`, over the ONE comparison Reload's gate makes
(`roundtrip.startup_is_running`), from the reads Reload makes (`reload_op.read_boot_pair`:
`dir nvram:` only when startup keeps a certificate there). Through the real routes, the device
answering with real captures: r1's running and startup (`tests/fixtures/transcripts/r1/`, the
same chains, certificates and files as r6's), r6's real `dir nvram:`, and s1's real pair (vIOS):

- Persist's card asks for its read on load; the read is a job; its part draws, for r1's pair
  with both files listed, "Startup is already what r2 runs", what Persist still does, and the
  two certificates kept as files (not a difference); `dir nvram:` read, every command sent a
  Tier 1 read;
- a real line differing: the line startup gains and the line it loses, each drawn, masked; a
  file `dir nvram:` does not list: named;
- vIOS: no `dir nvram:` sent, the same;
- the control: the comparison it replaced counts r1's pair as 4 differing lines;
- Adopt's preview (`/v2/adopt/preview`) over r1's pair: "the running and startup configs are
  the same", `dir nvram:` read; a file missing, named; s1 sends no `dir nvram:`;
- C923: Adopt's card draws the lines by Persist's drawing (`_startup_effect.html`): r1's pair
  with a line changed, the gained and lost lines, a planted community masked; the same, its
  words and no lines, the two files no difference; a missing file named once; and the
  manual's step 6 still saying the preview lists them.
"""

import html as _h
import re

import pytest

from modules import readonly_commands
from modules.nsot import capture_job, persist_op, roundtrip
from tests.test_persist_screen import lab  # noqa: F401 (the inventory: r2 in Lab)
from tests.test_reload_certificate_storage import DIR_NVRAM, _read

#: A planted value in a secret's position: drawn nowhere.
PLANTED = "Planted-Secret-77q"


class Device:
    """The device's side of one session: what it prints for each command it is sent."""

    def __init__(self, running, startup, nvram=DIR_NVRAM):
        self.answers = {"show running-config": running, "show startup-config": startup,
                        "dir nvram:": nvram}
        self.sent = []

    def send_command(self, command, **_kw):
        self.sent.append(command)
        return self.answers.get(command, "")


def _as(text: str, name: str, host: str) -> str:
    """*text* with its `hostname` line naming *host*: the one edit, so the read of the lab's
    device (Mercury checks a running config names the device it was read from) is r1's or
    s1's configuration."""
    assert f"\nhostname {name}\n" in text
    return text.replace(f"\nhostname {name}\n", f"\nhostname {host}\n")


@pytest.fixture
def r1():
    """r1's real pair, as the persist lab's r2 (`_as`); Adopt's adopts it as r1."""
    return {"running": _read("r1", "show running-config"),
            "startup": _read("r1", "show startup-config")}


@pytest.fixture
def s1():
    return {"running": _read("s1", "show running-config"),
            "startup": _read("s1", "show startup-config")}


def _r2(pair: dict, name: str) -> dict:
    return {k: _as(v, name, "r2") for k, v in pair.items()}


@pytest.fixture
def device(monkeypatch):
    """r2's session answers as the device it is given; `with_temp_connection` hands it over."""
    holder = {}

    def connect(dev, fn):
        holder["device"] = dev
        return fn(holder["session"])

    monkeypatch.setattr("modules.connection.with_temp_connection", connect)

    def give(session):
        holder["session"] = session
        return session
    return give


def _words(html: str) -> str:
    return " ".join(_h.unescape(re.sub(r"<[^>]+>", " ", html)).split())


def _effect(lab):  # noqa: F811
    """The card, then its part's read as the browser makes it: the POST its `load` sends, the
    job waited for, the GET its announcement sends. The part's HTML."""
    card = lab["client"].get("/v2/device/r2/persist").get_data(as_text=True)
    m = re.search(r'hx-post="(/v2/device/r2/persist/read[^"]*)" hx-trigger="load"', card)
    assert m, "the card asks for no read"
    vals = re.search(r"hx-vals='([^']*)'", card[m.start():]).group(1)
    assert '"list": "Lab"' in _h.unescape(vals)
    r = lab["client"].post(_h.unescape(m.group(1)), data={"list": "Lab"})
    reading = r.get_data(as_text=True)
    assert r.status_code == 200 and 'hx-trigger="nmas:persist_read from:body"' in reading
    get = _h.unescape(re.search(r'hx-get="([^"]+)"', reading).group(1))
    job = get.split("?", 1)[0].rsplit("/", 1)[1]
    assert capture_job.wait(job, 10)
    r = lab["client"].get(get)
    assert r.status_code == 200
    return r.get_data(as_text=True)


class TestPersistsPreview:
    def test_r1_s_pair_is_the_same_and_says_what_persist_still_does(self, lab, r1,  # noqa: F811
                                                                     device):
        pair = _r2(r1, "r1")
        session = device(Device(pair["running"], pair["startup"]))
        words = _words(_effect(lab))
        assert "Startup is already what r2 runs: saving changes no line it boots." in words
        assert ("Persist still saves it ( write memory ) and reads startup back, checking it "
                "carries every account line running holds.") in words
        assert ("Startup keeps 2 certificates as files in nvram:, which running shows inline: "
                "the same certificates stored two ways, not a difference.") in words
        assert "gains" not in words and "loses" not in words
        assert session.sent == ["show running-config", "show startup-config", "dir nvram:"]
        for command in session.sent:
            assert readonly_commands.refusal(command) == "", command
        assert lab["sent"] == [], "the read saves nothing"

    def test_the_lines_startup_gains_and_loses_are_drawn_masked(self, lab, r1, device):  # noqa: F811
        pair = _r2(r1, "r1")
        running = pair["running"].replace("\nlogging trap notifications\n",
                                          "\nlogging trap informational\n")
        running = running.replace("\nlogin on-success log\n",
                                  f"\nlogin on-success log\nsnmp-server community {PLANTED} RO\n")
        assert "logging trap informational" in running and PLANTED in running
        device(Device(running, pair["startup"]))
        html = _effect(lab)
        words = _words(html)
        assert "startup gains 2 lines and loses 1" in words
        gains = re.findall(r'<span class="op-add">\+ ([^<]*)</span>', html)
        loses = re.findall(r'<span class="op-del">- ([^<]*)</span>', html)
        assert loses == ["logging trap notifications"], loses
        assert "logging trap informational" in gains and len(gains) == 2, gains
        assert PLANTED not in html, "a secret's value is masked on the way out"
        assert any(g.startswith("snmp-server community ") for g in gains)

    def test_a_file_dir_nvram_does_not_list_is_named(self, lab, r1, device):  # noqa: F811
        pair = _r2(r1, "r1")
        device(Device(pair["running"], pair["startup"],
                      DIR_NVRAM.replace("CiscoLicensi#1CA.cer", "something-else.cer")))
        words = _words(_effect(lab))
        assert ("Startup keeps certificate ca 01 of SLA-TrustPoint as nvram:CiscoLicensi#1CA.cer "
                ", which dir nvram: does not list: a reload now would boot without it.") in words
        assert "gains" not in words, "no line differs: only the file is named"
        assert "Startup keeps 1 certificate as a file in nvram:" in words, "the other one"

    def test_vios_sends_no_dir_nvram(self, lab, s1, device):  # noqa: F811
        pair = _r2(s1, "s1")
        session = device(Device(pair["running"], pair["startup"]))
        words = _words(_effect(lab))
        assert "Startup is already what r2 runs" in words and "certificate" not in words
        assert session.sent == ["show running-config", "show startup-config"]

    def test_a_read_that_fails_says_couldn_t_load(self, lab, monkeypatch):  # noqa: F811
        def refuse(dev, fn):
            raise OSError("No route to host")
        monkeypatch.setattr("modules.connection.with_temp_connection", refuse)
        words = _words(_effect(lab))
        assert "Couldn't load: r2 could not be read: OSError: No route to host." in words

    def test_a_plan_that_cannot_run_asks_for_no_read(self, lab):  # noqa: F811
        card = lab["client"].get("/v2/device/s9/persist").get_data(as_text=True)
        assert "Persist s9" in card and "persist/read" not in card


class TestTheOneComparison:
    def test_the_comparison_it_replaced_counts_r1_s_pair_as_4_lines(self, r1):
        old = roundtrip.configs_equivalent(r1["startup"], r1["running"])
        assert len(old["only_left"]) + len(old["only_right"]) == 4, old
        assert persist_op.startup_effect(r1["startup"], r1["running"], DIR_NVRAM)["state"] \
            == "same"

    def test_no_startup_is_its_own_state(self, r1):
        got = persist_op.startup_effect("startup-config is not present", r1["running"])
        assert got["state"] == "no_startup"


@pytest.fixture
def adopting(monkeypatch):
    """Adopt's preview route on test_adopt_apply's list, its device read through the real
    `_read_device` over a session that answers as the device it is given."""
    from modules.nsot import adopt
    from tests import test_adopt_apply as T

    holder = {}
    monkeypatch.setattr("modules.nsot.credential_rotation.open_original_session",
                        lambda dev: holder["session"])
    monkeypatch.setattr(adopt, "_netbox_existing",
                        lambda hostname: {"ok": True, "objects": [], "error": ""})
    monkeypatch.setattr(adopt, "_netbox_dry_run", lambda *a, **k: {
        "ok": True, "error": "", "create_count": 0, "update_count": 0,
        "creates_by_type": {}, "updates_by_type": {}})
    import app as nmas
    client = nmas.app.test_client()

    def preview(session, hostname, raw=False):
        holder["session"] = session
        r = client.post("/v2/adopt/preview", data={
            "list_name": T.LIST, "hostname": hostname, "mgmt_ip": T.IP,
            "platform": "cisco-ios-xe", "role": "router", "supplied_username": "admin",
            "supplied_password": "Typed-Once-7731"})
        assert r.status_code == 200, r.get_data(as_text=True)[:600]
        return r.get_data(as_text=True) if raw else _words(r.get_data(as_text=True))
    return preview


class _AdoptSession(Device):
    def send_command(self, command, **kw):
        if "include ^aaa" in command or "section ^line vty" in command:
            self.sent.append(command)
            return ""
        return super().send_command(command, **kw)

    def disconnect(self):
        pass


class TestAdoptsPreview:
    @pytest.fixture(autouse=True)
    def _lab(self, monkeypatch, tmp_path):
        from tests.test_adopt_apply import lab as adopt_lab
        gen = adopt_lab.__wrapped__(monkeypatch, tmp_path)
        next(gen)
        yield
        next(gen, None)

    def test_r1_s_pair_is_the_same(self, adopting, r1):
        session = _AdoptSession(r1["running"], r1["startup"])
        words = adopting(session, "r1")
        assert ("the running and startup configs are the same: saving adds only the tool's "
                "account to what the device boots") in words
        assert "dir nvram:" in session.sent
        for command in session.sent:
            assert readonly_commands.refusal(command) == "", command

    def test_a_file_dir_nvram_does_not_list_is_named(self, adopting, r1):
        session = _AdoptSession(r1["running"], r1["startup"],
                                DIR_NVRAM.replace("CiscoLicensi#1CA.cer", "something-else.cer"))
        words = adopting(session, "r1")
        # Only a file is missing: no line differs, and no count of lines is said (C930).
        assert ("no line differs between running and startup: saving adds the tool's account "
                "to what the device boots, and writes its certificates again") in words
        assert "0 line(s)" not in words
        # C923: named by the card's drawing (`startup_lines`), no longer in the sentence too.
        assert ("Startup keeps certificate ca 01 of SLA-TrustPoint as nvram:CiscoLicensi#1CA.cer "
                ", which dir nvram: does not list") in words
        assert words.count("nvram:CiscoLicensi#1CA.cer") == 1, "named once"

    def test_vios_sends_no_dir_nvram(self, adopting, s1):
        session = _AdoptSession(s1["running"], s1["startup"])
        words = adopting(session, "s1")
        assert "the running and startup configs are the same" in words
        assert "dir nvram:" not in session.sent


def _save_part(html: str) -> str:
    """Adopt's card's "What a save makes permanent" part, up to the next heading."""
    m = re.search(r'What a save makes permanent</h3>(.*?)<h3 ', html, re.S)
    assert m, "the card draws no save part"
    return m.group(1)


class TestAdoptsCardDrawsTheLines:
    """C923: Adopt's card drew only the persist sentence, though docs/manual/how-it-works/
    adopt.md step 6 says the preview lists the lines. It now draws them by Persist's own
    drawing (`_startup_effect.html`'s `startup_lines`), through `/v2/adopt/preview` with the
    real `_read_device` over r1's real pair."""

    @pytest.fixture(autouse=True)
    def _lab(self, monkeypatch, tmp_path):
        from tests.test_adopt_apply import lab as adopt_lab
        gen = adopt_lab.__wrapped__(monkeypatch, tmp_path)
        next(gen)
        yield
        next(gen, None)

    def test_the_lines_startup_gains_and_loses_are_drawn_masked(self, adopting, r1):
        running = r1["running"].replace("\nlogging trap notifications\n",
                                        "\nlogging trap informational\n")
        running = running.replace("\nlogin on-success log\n",
                                  f"\nlogin on-success log\nsnmp-server community {PLANTED} RO\n")
        assert "logging trap informational" in running and PLANTED in running
        html = adopting(_AdoptSession(running, r1["startup"]), "r1", raw=True)
        part = _save_part(html)
        words = _words(part)
        assert ("saving makes the RUNNING config the boot config, with the tool's account: 2 "
                "line(s) only the running config has become permanent, and 1 line(s) only the "
                "startup config has are gone at the next reload") in words
        assert "Startup gains, held only by running" in words
        assert "Startup loses, held only by startup: gone at the next reload" in words
        gains = re.findall(r'<span class="op-add">\+ ([^<]*)</span>', part)
        loses = re.findall(r'<span class="op-del">- ([^<]*)</span>', part)
        assert loses == ["logging trap notifications"], loses
        assert "logging trap informational" in gains and len(gains) == 2, gains
        assert any(g.startswith("snmp-server community ") for g in gains), gains
        assert PLANTED not in html, "a secret's value is masked on the way out"

    def test_the_same_draws_the_same_words_and_no_lines(self, adopting, r1):
        html = adopting(_AdoptSession(r1["running"], r1["startup"]), "r1", raw=True)
        words = _words(_save_part(html))
        assert ("the running and startup configs are the same: saving adds only the tool's "
                "account to what the device boots") in words
        assert ("Startup keeps 2 certificates as files in nvram:, which running shows inline: "
                "the same certificates stored two ways, not a difference.") in words
        assert "Startup gains" not in words and "Startup loses" not in words
        assert "op-add" not in html and "op-del" not in html

    def test_a_missing_certificate_file_is_named(self, adopting, r1):
        html = adopting(_AdoptSession(r1["running"], r1["startup"], DIR_NVRAM.replace(
            "CiscoLicensi#1CA.cer", "something-else.cer")), "r1", raw=True)
        words = _words(_save_part(html))
        assert ("Startup keeps certificate ca 01 of SLA-TrustPoint as nvram:CiscoLicensi#1CA.cer "
                ", which dir nvram: does not list: a reload now would boot without it.") in words
        assert "Startup keeps 1 certificate as a file in nvram:" in words, "the other one"
        assert "Startup gains" not in words, "no line differs: only the file is named"

    def test_the_manual_says_what_the_card_draws(self):
        """adopt.md step 6 stays true: it says the preview lists the lines, and names a file."""
        import os
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "docs", "manual", "how-it-works", "adopt.md")
        with open(path, encoding="utf-8") as fh:
            step = " ".join(fh.read().split("6. **What a save would make permanent.**", 1)[1]
                            .split("7. **", 1)[0].split())
        assert "The preview lists the lines a save would make permanent" in step
        assert "names a certificate file `dir nvram:` does not list" in step
