"""Console runs' records at rest hold no secret the device printed (the operator, 2026-10-23,
blocking deploy 2).

A known secret's value, held in the run's masking values (`redact.redact_text`'s table, as the
installation's would be), is planted in EVERY device-printed input each console run can quote,
one case per (run kind, input):

- the run kinds: the console SURVEY (`console_ztp.survey_run`), the console KICK-START
  (`console_ztp.kickstart_apply`, the static path) and the one-decision OUT-OF-BAND ONBOARD run
  (`oob_onboard.run`);
- the inputs: the greeting the console prints before the wake (s5's PnP release), the wake's
  banner, a refusal (a ``%`` line), an unexpected (unknown) prompt, the blank check's answer
  (`dir nvram:`), a read's answer (the survey's MAC read; the read-back of the kick-start and
  the onboard run) and the copy's output (the kick-start and the onboard run).

Each case runs on the existing loopback worlds (tests/test_console_ztp.World,
tests/test_oob_onboard.OobWorld: the fake NetBox, the console-server store, a raw TCP fake
console answering with the real captures of tests/fixtures/console/, each with one minimal edit
carrying the secret) and then reads back from disk EVERY file the run left under the test's
folder (the data folder, the lists folder and everything else in it, found by walking it, never
by a list of names), plus any file under the session's NMAS_DATA_DIR changed since the case
began, plus the in-memory record returned. Every string at any depth of each JSON document, keys
included, is searched (never named fields); a file that is not JSON is searched whole. The
assertion names each JSON path where the value was found.

Controls: each case asserts the run reached the step that quotes its input (its outcome or stop
says so), and that the masked placeholder occurs in at least one stored field (the input reached
the record); the population of cases has a floor.
"""

import json
import os
import socket
import time

import pytest

from modules.nsot import console_ztp as Z
from modules.nsot import oob_onboard as O
from tests.console_ios import read_index
from tests.test_console_session import PNP
from tests.test_console_ztp import (ACTOR, FAST as ZFAST, LIST, World, _hardware_summary,
                                    _lines as kick_lines, _real, blank_answers, kick_answers)
from tests.test_oob_onboard import (ADDRESS, FAST as OFAST, FIELDS, MASK, OobWorld,
                                    answers as oob_answers)

#: A secret the installation holds (``{value: label}``, `redact.redact_text`'s table).
SECRET = "Pl4ntedS3cretValue"
VALUES = {SECRET: "enable secret"}
#: How the secret stands in the device's text (C1629, 2026-10-24): a word of its own (every
#: case), or inside a longer token, a URL's path, a file path and a dotted name (the second
#: plant, `test_no_secret_inside_a_longer_token_is_at_rest`). The search is for the bare value
#: either way.
FORMS = {"word": "{}", "url": "tftp://192.0.2.10/{}.cfg", "path": "flash:/{}/vlan.dat",
         "dotted": "cfg.{}.bak"}
_FORM = {"now": "word"}


def planted() -> str:
    """The secret as tonight's case plants it (`FORMS`)."""
    return FORMS[_FORM["now"]].format(SECRET)
PLACEHOLDER = "<redacted:enable secret>"


# ── the device's text, each a real capture with one minimal edit carrying the secret ─────────

def greeting() -> bytes:
    """s5's PnP release (printed before the wake), the PnP line naming the secret."""
    assert b"(Config Wizard)" in PNP
    return PNP.replace(b"(Config Wizard)", f"(Config Wizard {planted()})".encode())


def banner() -> bytes:
    """The wake's answer (s5's evaluation banner and `Switch>`), the banner naming the secret."""
    wake = _real()[0]
    assert b"Cisco in writing." in wake
    return wake.replace(b"Cisco in writing.", f"Cisco in writing. {planted()}".encode())


def nvram() -> bytes:
    """`dir nvram:`'s answer on the blank s5 (startup-config 0 bytes), one file named the
    secret."""
    text = _real()[2]
    assert b"persistent-data" in text
    return text.replace(b"persistent-data", planted().encode())


def refusal(line: str, prompt: str) -> bytes:
    """*line*'s echo answered by a refusal naming the secret (tests/test_oob_run_stops.py's)."""
    return f"{line}\r\n% Bad secret {planted()} refused\r\n\r\n{prompt}".encode()


def unknown_prompt(line: str) -> bytes:
    """*line*'s echo answered by a question no profile names, carrying the secret (IOS's copy
    question's shape, tests/test_console_ztp_static.py's)."""
    return f"{line}\r\nAddress or name of remote host [{planted()}]? ".encode()


def copy_error() -> str:
    """The copy's transfer failing, IOS's `%Error opening` naming the secret."""
    return (f"Accessing tftp://192.0.2.10/edge1.cfg...\r\n%Error opening "
            f"tftp://192.0.2.10/edge1.cfg ({planted()})\r\n")


# ── the walk ─────────────────────────────────────────────────────────────────────────────

def _strings(obj, path):
    """Every ``(path, string)`` in *obj*: each dict key and every string value at any depth."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield f"{path}.<key {k!r}>", str(k)
            yield from _strings(v, f"{path}[{k!r}]")
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            yield from _strings(v, f"{path}[{i}]")
    elif isinstance(obj, str):
        yield path, obj
    elif obj is not None and not isinstance(obj, (bool, int, float)):
        yield path, repr(obj)


def found(obj, needle: str, path: str = "$") -> list:
    return [p for p, s in _strings(obj, path) if needle in s]


def stored(roots, since: float = None) -> dict:
    """``{path: document}`` for every file under each of *roots* (``(folder, only_since)``): a
    ``.json`` file parsed, any other file its text (decoded, replacement for bytes that are not
    text). *only_since*: only files changed at or after *since*."""
    out = {}
    for root, only_since in roots:
        if not root or not os.path.isdir(root):
            continue
        for folder, _dirs, files in os.walk(root):
            for name in files:
                path = os.path.join(folder, name)
                try:
                    if only_since and os.stat(path).st_mtime < since:
                        continue
                    with open(path, "rb") as fh:
                        raw = fh.read()
                except FileNotFoundError:
                    continue                    # a hold's mark gone as it was listed
                text = raw.decode("utf-8", "replace")
                if name.endswith(".json"):
                    try:
                        out[path] = json.loads(text)
                        continue
                    except ValueError:
                        pass
                out[path] = text
    return out


def assert_nothing_at_rest(rec: dict, tmp_path, since: float, kind: str) -> dict:
    """The secret in no stored field and not in the record returned; the placeholder in at least
    one stored field. The documents read."""
    docs = stored([(str(tmp_path), False), (os.environ.get("NMAS_DATA_DIR"), True)], since)
    runs = [p for p in docs if rec["id"] in os.path.basename(p)]
    assert runs, f"no stored run record named {rec['id']} among {sorted(docs)}"
    leaks = [f"{os.path.relpath(p, tmp_path)}:{at}" for p, doc in docs.items()
             for at in found(doc, SECRET)]
    leaks += [f"<the record returned>:{at}" for at in found(rec, SECRET)]
    assert not leaks, f"{kind}: the secret's value is at rest in: " + "; ".join(leaks)
    masked = [f"{os.path.relpath(p, tmp_path)}:{at}" for p, doc in docs.items()
              for at in found(doc, PLACEHOLDER)]
    assert masked, (f"{kind}: no stored field holds {PLACEHOLDER}: the planted input never "
                    f"reached the record (files: {sorted(docs)})")
    return docs


# ── the runs ─────────────────────────────────────────────────────────────────────────────

def survey(w, got, greet=b""):
    w.consoles.append((greet, list(got)))
    p = Z.survey_preview(LIST, w.dev["id"], profile="cisco_ios_switch", values=VALUES,
                         **w.nb())
    assert p["ok"], p["refusals"]
    return Z.survey_run(LIST, w.dev["id"], profile="cisco_ios_switch", confirmed_hash=p["hash"],
                        actor=ACTOR, actor_verified=Z.VERIFIED, timings=ZFAST, values=VALUES,
                        **w.nb())


def kick(w, got, greet=b""):
    """A blank survey first (the kick-start stands on it), then the kick-start on *got*."""
    rec = w.survey(greeting=PNP, answers=blank_answers())
    assert rec["outcome"] == "surveyed" and rec["blank"] is True, rec["reason"]
    return w.kick(got, greeting=greet, values=VALUES)


def onboard(w, got, greet=b""):
    p = O.preview(LIST, dict(FIELDS), values=VALUES, **w.nbk())
    assert p["ok"], p["refusals"]
    w.consoles.append((greet, list(got)))
    return O.run(LIST, dict(FIELDS), confirmed_hash=p["hash"], actor=ACTOR,
                 actor_verified="access", reason="a new access switch", timings=OFAST,
                 wall=w.wall, sleep=w.sleep, values=VALUES, probe=w.probe, create=w.create,
                 undo=w.undo, record_mac=w.record_mac, **w.nbk())


# The survey: its sends after the wake are enable, the pager, show version (the MAC read),
# dir nvram: (the blank check) and disable; blank_answers() answers each.

def survey_greeting(w):
    rec = survey(w, blank_answers(), greet=greeting())
    assert rec["outcome"] == "surveyed" and rec["attach_state"] == "press_return", rec["reason"]
    return rec


def survey_banner(w):
    got = blank_answers()
    got[0] = banner()
    rec = survey(w, got)
    assert rec["outcome"] == "surveyed" and rec["blank"] is True, rec["reason"]
    return rec


def survey_refusal(w):
    got = blank_answers()
    got[3] = refusal("show version", "Switch#")
    rec = survey(w, got[:4])
    assert rec["outcome"] == "aborted" and "was refused" in rec["reason"], rec["reason"]
    assert rec["reasons"][0].startswith("the survey stopped in its mac phase"), rec["reasons"]
    return rec


def survey_unexpected(w):
    got = blank_answers()
    got[4] = unknown_prompt("dir nvram:")
    rec = survey(w, got[:5])
    assert rec["outcome"] == "aborted" and "found an unknown prompt" in rec["reason"], \
        rec["reason"]
    assert rec["reasons"][0].startswith("the survey stopped in its blank phase"), rec["reasons"]
    return rec


def survey_blank(w):
    got = blank_answers()
    got[4] = nvram()
    rec = survey(w, got)
    assert rec["outcome"] == "surveyed" and rec["startup_config_bytes"] == 0, rec["reason"]
    return rec


def survey_read(w):
    got = blank_answers()
    summary = _hardware_summary()
    assert b"Processor board ID <serial>" in summary
    got[3] = summary.replace(b"Processor board ID <serial>",
                             f"Processor board ID {planted()}".encode())
    rec = survey(w, got)
    assert rec["outcome"] == "surveyed" and rec["blank"] is True, rec["reason"]
    return rec


# The kick-start: kick_answers(lines) answers the wake, enable, the recheck (dir nvram:), each
# line (index 3 + i), each read-back (found by its command, `read_index`) and the copy (its
# last two).

def _svi(lines) -> int:
    return lines.index(f" ip address {ADDRESS} {MASK}")


def kick_greeting(w):
    _wake, *rest = kick_answers(kick_lines())
    rec = kick(w, [_real()[0]] + rest, greet=greeting())
    assert rec["outcome"] == "done" and rec["attach_state"] == "press_return", rec["reason"]
    return rec


def kick_banner(w):
    got = kick_answers(kick_lines())
    got[0] = banner()
    rec = kick(w, got)
    assert rec["outcome"] == "done", rec["reason"]
    return rec


def kick_refusal(w):
    lines = kick_lines()
    i = _svi(lines)
    got = kick_answers(lines)
    got[3 + i] = refusal(lines[i], "edge1(config-if)#")
    rec = kick(w, got[:4 + i])
    assert rec["outcome"] == "line_refused" and rec["refused"]["words"], rec["reason"]
    return rec


def kick_unexpected(w):
    lines = kick_lines()
    i = _svi(lines)
    got = kick_answers(lines)
    got[3 + i] = unknown_prompt(lines[i])
    rec = kick(w, got[:4 + i])
    assert rec["outcome"] == "aborted" and rec["reason"].startswith("typing: ") \
        and "found an unknown prompt" in rec["reason"], rec["reason"]
    return rec


def kick_blank(w):
    got = kick_answers(kick_lines())
    got[2] = nvram()
    rec = kick(w, got)
    assert rec["outcome"] == "done" and rec["recheck"]["blank"] is True, rec["reason"]
    return rec


def kick_read(w):
    lines = kick_lines()
    got = kick_answers(lines)
    at = read_index(got, "show running-config interface Vlan10")   # the SVI's read-back
    want = f" ip address {ADDRESS} {MASK}".encode()
    assert want in got[at], got[at]
    got[at] = got[at].replace(want, f" ip address {planted()} {MASK}".encode())
    rec = kick(w, got)
    assert rec["outcome"] == "readback_differs" and rec["readback_differs"], rec["reason"]
    return rec


def kick_copy(w):
    got = kick_answers(kick_lines())
    got[-1] = ("\r\n" + copy_error() + "edge1#").encode()
    rec = kick(w, got)
    assert rec["outcome"] == "copy_failed" and rec["copied"]["refused"], rec["reason"]
    return rec


# The onboard run: oob_answers() answers the wake, enable, the pager, the blank check, the
# blank check again, each line, each read-back and the copy.

def oob_greeting(w):
    rec = onboard(w, [_real()[0]] + oob_answers()[1:], greet=greeting())
    assert rec["outcome"] == "done" and rec["attach_state"] == "press_return", rec["reason"]
    return rec


def oob_banner(w):
    got = oob_answers()
    got[0] = banner()
    rec = onboard(w, got)
    assert rec["outcome"] == "done", rec["reason"]
    return rec


def oob_refusal(w):
    line = f"ip address {ADDRESS} {MASK}"
    got = oob_answers()
    at = next(i for i, a in enumerate(got) if a.startswith(f" {line}\r\n".encode()))
    got[at] = refusal(f" {line}", "edge1(config-if)#")
    rec = onboard(w, got)
    assert rec["outcome"] == "refused_line" and rec["stop"]["rule"] == "refused_line", \
        rec["reason"]
    return rec


def oob_unexpected(w):
    got = oob_answers()[:3] + [unknown_prompt("dir nvram:")]
    rec = onboard(w, got)
    assert rec["outcome"] == "unexpected" and "found an unknown prompt" in \
        rec["stop"]["compared"], rec["reason"]
    return rec


def oob_blank(w):
    rec = onboard(w, oob_answers(nvram=nvram()))
    assert rec["outcome"] == "done" and rec["blank"]["blank"] is True, rec["reason"]
    return rec


def oob_read(w):
    """On Phase A's own read-back (`console_kickstart.readback_plan` and `readback_verdict`,
    the adapter's production pieces, put back over the world's stand-ins): its differences
    quote what the device showed, which the stand-in's do not. The reads' answers are
    tests/console_ios.py's for a device that took every line, the SVI's showing the secret."""
    from modules.nsot import console_kickstart as K
    from modules.nsot import oob_steps
    from tests.console_ios import readback_answers
    from tests.test_oob_onboard import _lines as oob_lines

    w.monkeypatch.setattr(oob_steps, "readback_plan", K.readback_plan)
    w.monkeypatch.setattr(oob_steps, "readback_verdict", K.readback_verdict)
    lines = oob_lines()
    reads = readback_answers(lines, "edge1#")
    want = f" ip address {ADDRESS} {MASK}".encode()
    (at,) = [i for i, r in enumerate(reads) if want in r]
    reads[at] = reads[at].replace(want, f" ip address {planted()} {MASK}".encode())
    rec = onboard(w, oob_answers()[:5 + len(lines)] + reads)
    assert rec["outcome"] == "read_back" and rec["read_back"]["differs"], rec["reason"]
    return rec


def oob_copy(w):
    """On Phase A's own `console_kickstart.verify_copy` (the adapter's production piece, put
    back over the world's stand-in), whose verdict quotes the refusal the copy printed."""
    from modules.nsot import console_kickstart as K
    from modules.nsot import oob_steps

    w.monkeypatch.setattr(oob_steps, "verify_copy", K.verify_copy)
    rec = onboard(w, oob_answers(copy=copy_error()))
    assert rec["outcome"] == "copy_failed" and rec["stop"]["rule"] == "copy", rec["reason"]
    return rec


CASES = {
    ("survey", "greeting"): survey_greeting, ("survey", "banner"): survey_banner,
    ("survey", "refusal"): survey_refusal, ("survey", "unexpected_prompt"): survey_unexpected,
    ("survey", "blank_check"): survey_blank, ("survey", "read_answer"): survey_read,
    ("kickstart", "greeting"): kick_greeting, ("kickstart", "banner"): kick_banner,
    ("kickstart", "refusal"): kick_refusal, ("kickstart", "unexpected_prompt"): kick_unexpected,
    ("kickstart", "blank_check"): kick_blank, ("kickstart", "read_answer"): kick_read,
    ("kickstart", "copy_output"): kick_copy,
    ("onboard", "greeting"): oob_greeting, ("onboard", "banner"): oob_banner,
    ("onboard", "refusal"): oob_refusal, ("onboard", "unexpected_prompt"): oob_unexpected,
    ("onboard", "blank_check"): oob_blank, ("onboard", "read_answer"): oob_read,
    ("onboard", "copy_output"): oob_copy,
}
#: The floor: three run kinds, each with every input it can meet (the survey copies nothing).
FLOOR = 20
INPUTS = {"greeting", "banner", "refusal", "unexpected_prompt", "blank_check", "read_answer",
          "copy_output"}


def test_the_population_has_its_floor():
    assert len(CASES) >= FLOOR, sorted(CASES)
    for kind in ("survey", "kickstart", "onboard"):
        met = {i for k, i in CASES if k == kind}
        assert met == INPUTS - ({"copy_output"} if kind == "survey" else set()), (kind, met)


@pytest.mark.parametrize("kind,what", sorted(CASES), ids=[f"{k}-{i}" for k, i in sorted(CASES)])
def test_no_secret_the_device_printed_is_at_rest(tmp_path, monkeypatch, kind, what):
    since = time.time() - 1.0
    w = (OobWorld if kind == "onboard" else World)(tmp_path, monkeypatch, socket.AF_INET)
    w.monkeypatch = monkeypatch                # a case may put a production piece back
    try:
        rec = CASES[(kind, what)](w)
    finally:
        w.server.close()
    assert_nothing_at_rest(rec, tmp_path, since, f"{kind}/{what}")
    # the run's own record (the one History reads) is the run's end, not an earlier write
    stored_rec = Z.get_run(LIST, rec["id"])
    assert stored_rec is not None and stored_rec["outcome"] == rec["outcome"]


INSIDE = sorted(f for f in FORMS if f != "word")


@pytest.mark.parametrize("form", INSIDE)
@pytest.mark.parametrize("kind,what", sorted(CASES), ids=[f"{k}-{i}" for k, i in sorted(CASES)])
def test_no_secret_inside_a_longer_token_is_at_rest(tmp_path, monkeypatch, kind, what, form):
    """C1629's measurement: every case again with the secret inside a URL's path, a file path
    or a dotted name, which masking by whole token left in clear until 2026-10-24."""
    monkeypatch.setitem(_FORM, "now", form)
    assert SECRET in planted() and planted() != SECRET, "floor: planted inside a token"
    since = time.time() - 1.0
    w = (OobWorld if kind == "onboard" else World)(tmp_path, monkeypatch, socket.AF_INET)
    w.monkeypatch = monkeypatch
    try:
        rec = CASES[(kind, what)](w)
    finally:
        w.server.close()
    assert_nothing_at_rest(rec, tmp_path, since, f"{kind}/{what}/{form}")
