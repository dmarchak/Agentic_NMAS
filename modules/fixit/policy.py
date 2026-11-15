"""AI troubleshooting's mode and its per-incident cap: the two settings the fix-it path is held
to before any AI call is made for an incident.

The operator's order (overnight item 6, 2026-11-12), which this module implements in part:
"AI troubleshooting, as designed: a background job; the AI proposes one catalog operation with
parameters; code validates it against intent and the guards; a person approves it; on failure
STOP with Retry with more information (cost shown first), Cancel or Hand over; a per-incident
cap of $1.00; a repeated failed proposal is flagged; payloads use stable labels. Settings ›
Background processes, AI mode Manual by default. Section 12's rule stays in force."

**The mode, per network** (C3769, Gate 2: ONE control, AI troubleshooting Off, Manual or
Automatic for each network; `mode`): ``off``, none is offered or started and Mercury's own
proposer still is (`modules/fixit/proposers.py`); ``manual``, an AI troubleshoot runs only on
a verified person's press; Automatic is Manual with the network's ``fixit_auto`` switch on
(CLAUDE.md, "AI cost safety"; `modules/fixit/auto.py`), which starts an investigation by itself
when Mercury's fix fails, within the network's acknowledged limits (`modules/troubleshoot_control.py`
turns it on and off, from Settings › AI or the control strip). The stored value is Off or
Manual: Automatic is never stored as a mode, so the switch stays the one owner of whether
anything starts by itself. **Expand, then contract:** a network's own value rides in its
``fixit_auto`` record (`background.OWN_FIELDS`); a network with none reads the installation's
``ai_troubleshoot_mode``, which every release before Gate 2 read alone. A mode that cannot be
read is said and allows nothing (`ai_refusal`).

**The cap** (the incident's network's own per-incident limit, C3769, else the installation's
`ai_cap_usd_per_incident`, the operator's $1.00; `cap_usd`, `cap_state`, `cap_refusal`): what
the incident's AI calls cost so far (`incident.cost_so_far`, summed from the record of AI calls
by the ids the incident's proposals name, each time) plus the next attempt's worst case, against
the cap, as the gateway's day cap compares a call (`gateway.day_cap`, `controls.cap_state`).
Over it is refused, the words naming the spent amount, the worst case, their sum and the cap.
At it exactly is allowed: a cap is reached, not passed. **No "no cap"** (the fix-it plan's
decision 1): a cap that is not a positive amount (a hand-edited null, zero, text) refuses, and
so does a cost that cannot be read or is partial: a sum not known is never compared as if it
were. Mercury never raises the cap.

Reads only: the settings and the incident's records. Nothing here calls the model, sends or
starts anything (tests/test_fixit_incident.py's scan of `modules/fixit/`).
"""

import logging
import math

log = logging.getLogger(__name__)

MODE_KEY = "ai_troubleshoot_mode"
CAP_KEY = "ai_cap_usd_per_incident"
MODES = ("manual", "off")
DEFAULT_MODE = "manual"
#: Each mode as a person reads it, on the setting's control, in a saved change's words and in a
#: refusal (the operator, 2026-11-13: "Manual" capitalised). The stored value stays the key.
MODE_WORDS = {"manual": "Manual", "off": "Off"}
#: The operator's figure (2026-11-12): $1.00 an incident.
DEFAULT_CAP_USD = 1.00
#: How finely spent and worst case are compared: a millionth of a dollar, so a float's
#: rounding never moves a sum that equals the cap past it.
PRECISION = 6


def money(value) -> str:
    """US dollars as the cap's words say them, always with cents ("$1.00", "$0.92", "$0"
    written "$0.00"), and to four places below a cent ("$0.0257"): a spent amount and a cap
    side by side read alike. The one formatter's exact amount (`modules.money.usd`)."""
    from modules.money import usd

    return usd(value, exact=True)


def _own(network) -> tuple:
    """``(record, error)``: *network*'s AI troubleshooting record (its ``fixit_auto`` entry, on
    or off: `background.record_of`), ``({}, "")`` for no network, none kept, or a name no
    network answers to (which can hold no record of its own, so the installation's answers).
    A settings file that cannot be read is said by the installation's read that follows (the
    record and the installation's value are in the same file), so ``({}, "")`` then too; *error*
    is for a record of the wrong shape."""
    if not network:
        return {}, ""
    from modules.ai import background
    from modules.config import SettingsUnreadable
    from modules.nsot import listref

    try:
        slug = listref.network_id(network)
    except Exception:                                           # noqa: BLE001 (none of its own)
        return {}, ""
    try:
        return background.record_of(slug, "fixit_auto"), ""
    except SettingsUnreadable:
        return {}, ""


def _mode_of(network) -> dict:
    """`mode`'s read, always with ``source``."""
    from modules.config import SettingsUnreadable
    from modules.settings_schema import get_setting

    own, why = _own(network)
    if why:
        return {"state": "unreadable", "mode": "", "error": why, "source": "network"}
    if "mode" in own:
        if own["mode"] not in MODES:
            return {"state": "unreadable", "mode": "", "source": "network",
                    "error": (f"{network}'s AI troubleshooting mode holds {own['mode']!r}, and "
                              f"the modes are {' and '.join(MODE_WORDS[m] for m in MODES)}")}
        return {"state": "ok", "mode": own["mode"], "error": "", "source": "network"}
    try:
        raw = get_setting("ai_troubleshoot_mode", DEFAULT_MODE)     # MODE_KEY, by name (a scan)
    except SettingsUnreadable as exc:
        return {"state": "unreadable", "mode": "", "source": "installation",
                "error": f"the AI troubleshooting mode cannot be read ({exc})"}
    if raw not in MODES:
        return {"state": "unreadable", "mode": "", "source": "installation",
                "error": (f"the AI troubleshooting mode holds {raw!r}, and the modes are "
                          f"{' and '.join(MODE_WORDS[m] for m in MODES)}")}
    return {"state": "ok", "mode": raw, "error": "", "source": "installation"}


def _shaped(got: dict, network) -> dict:
    """*got* as every release before C3769 answered it when no *network* is named (no
    ``source``: the installation's is the only one), else with *source*."""
    return got if network else {k: v for k, v in got.items() if k != "source"}


def mode(network: str = None) -> dict:
    """``{"state": "ok"|"unreadable", "mode", "error"}``, and ``source`` when *network* is
    named: AI troubleshooting's mode for *network* (C3769), its own (``network``), else the
    installation's (``installation``), `DEFAULT_MODE` when neither was set. With no
    *network*, the installation's alone, every network's default. A stored value this release
    does not know (a hand-edited file) is unreadable, never read as either mode."""
    return _shaped(_mode_of(network), network)


def cap_usd(network: str = None) -> dict:
    """``{"state": "ok"|"unreadable", "usd", "error"}``, and ``source`` when *network* is
    named: the per-incident cap, a positive amount, *network*'s own limit (C3769, set with its
    other limits in Settings › AI, ``network``), else the installation's (``installation``).
    Never set reads as the operator's $1.00; anything stored that is not a positive amount
    (null, zero, a negative, text, true or false) is unreadable, never "no cap"."""
    return _shaped(_cap_of(network), network)


def ai_refusal(network: str = None) -> str:
    """Why no AI troubleshoot may be offered or run now on *network*, or ``""``: its mode
    (`mode`) is off, or cannot be read. Manual allows a person's press, and Automatic the
    network's switch too. With no *network*, the installation's mode alone."""
    got = mode(network)
    if got["state"] != "ok":
        return f"AI troubleshooting is not offered: {got['error']}"
    if got["mode"] == "off":
        if got.get("source") == "network":
            return (f"AI troubleshooting is off for {network} (its mode is "
                    f"{MODE_WORDS['off']}): Mercury's own diagnosis still proposes a fix")
        return ("AI troubleshooting is off for this installation (its mode is "
                f"{MODE_WORDS['off']}): Mercury's own diagnosis still proposes a fix")
    return ""


def _positive(raw) -> bool:
    return not (isinstance(raw, bool) or not isinstance(raw, (int, float))
                or not math.isfinite(raw) or raw <= 0)


def _cap_of(network) -> dict:
    """`cap_usd`'s read, always with ``source``."""
    from modules.config import SettingsUnreadable
    from modules.settings_schema import get_setting

    own, why = _own(network)
    if why:
        return {"state": "unreadable", "usd": None, "error": why, "source": "network"}
    if "incident_cap_usd" in own:
        raw = own["incident_cap_usd"]
        if not _positive(raw):
            return {"state": "unreadable", "usd": None, "source": "network",
                    "error": (f"{network}'s per-incident AI cap holds {raw!r}, and it is a "
                              "positive amount of US dollars: this cap has no \"no cap\"")}
        return {"state": "ok", "usd": float(raw), "error": "", "source": "network"}
    try:
        raw = get_setting("ai_cap_usd_per_incident", DEFAULT_CAP_USD)  # CAP_KEY, by name
    except SettingsUnreadable as exc:
        return {"state": "unreadable", "usd": None, "source": "installation",
                "error": f"the per-incident AI cap cannot be read ({exc})"}
    if not _positive(raw):
        return {"state": "unreadable", "usd": None, "source": "installation",
                "error": (f"the per-incident AI cap holds {raw!r}, and it is a positive amount "
                          "of US dollars: this cap has no \"no cap\"")}
    return {"state": "ok", "usd": float(raw), "error": "", "source": "installation"}


def cap_state(incident, worst_usd) -> dict:
    """The comparison the cap makes for *incident*'s next attempt, whose worst case is
    *worst_usd* (US dollars, a positive amount: the next call's per-call cap from its pin,
    times its calls): ``{"state": "allowed"|"refused", "spent", "worst", "total", "cap",
    "words"}``, *spent* None when it is not known. Reads the settings and the incident's
    records; asks nothing else."""
    from modules.fixit import incident as F

    out = {"state": "refused", "spent": None, "worst": None, "total": None, "cap": None,
           "words": ""}
    if (isinstance(worst_usd, bool) or not isinstance(worst_usd, (int, float))
            or not math.isfinite(worst_usd) or worst_usd <= 0):
        out["words"] = (f"Retry isn't available: the next attempt's worst case was given as "
                        f"{worst_usd!r}, and it is a positive amount of US dollars, so it "
                        "cannot be compared with this incident's cap")
        return out
    worst = float(worst_usd)
    out["worst"] = worst
    # The incident's own network's limit (C3769), else the installation's.
    cap = cap_usd(getattr(incident, "network", None))
    if cap["state"] != "ok":
        out["words"] = (f"Retry isn't available: {cap['error']}, so the next attempt's worst "
                        f"case of {money(worst)} cannot be compared with it")
        return out
    out["cap"] = cap["usd"]
    cost = F.cost_so_far(incident)
    if cost["state"] != "ok":
        out["words"] = (f"Retry isn't available: what this incident's AI calls cost is not "
                        f"known ({cost['error']}), so spent plus the next attempt's worst case "
                        f"of {money(worst)} cannot be compared with the cap of "
                        f"{money(cap['usd'])}")
        return out
    spent = float(cost["usd"])
    total = round(spent + worst, PRECISION)
    out.update(spent=spent, total=total)
    if total > round(cap["usd"], PRECISION):
        out["words"] = (f"Retry isn't available: this incident's AI spend would pass its cap. "
                        f"Spent {money(spent)} in this incident; the next attempt costs at most "
                        f"{money(worst)}, which would make {money(total)} against the cap of "
                        f"{money(cap['usd'])}. Mercury never raises the cap")
        return out
    out["state"] = "allowed"
    return out


def cap_refusal(incident, worst_usd) -> str:
    """Why *incident*'s next attempt, whose worst case is *worst_usd*, is refused by the
    per-incident cap, naming spent, the worst case, their sum and the cap; or ``""``
    (`cap_state`). A refusal is logged; the caller records it with the press it refused."""
    got = cap_state(incident, worst_usd)
    if got["state"] == "allowed":
        return ""
    log.info("fixit: %s: the cap refused: %s", getattr(incident, "id", "?"), got["words"])
    return got["words"]
