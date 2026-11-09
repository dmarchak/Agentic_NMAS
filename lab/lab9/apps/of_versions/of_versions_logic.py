"""of_versions' logic over plain data, apart from Ryu (C2670): the OpenFlow versions the app pins
and what its `/health` says of the switches that connected. Python 3.5 (C2646): no f-strings,
no variable annotations, every answer sorted.

**Why the pin.** Ryu offers the INTERSECTION of its loaded apps' `OFP_VERSIONS` (C2593), and
its own `ofctl_rest` and `rest_topology` speak 1.0 to 1.5, so a controller loading nothing
narrower sends a 1.5 hello, which EOS 4.17 refuses (C2598). This app does nothing but narrow
the set to 1.0 and 1.3, the versions every switch's platform profile offers, so every switch
negotiates 1.3 (the bring-up, 2026-11-06). It installs no flow and takes no config.
"""

#: The pin, as OpenFlow's wire versions (1.0 is 0x01, 1.3 is 0x04).
PINNED = (0x01, 0x04)
#: Each wire version's name.
TEXT = {0x01: "1.0", 0x02: "1.1", 0x03: "1.2", 0x04: "1.3", 0x05: "1.4", 0x06: "1.5"}


def version_text(wire):
    """The OpenFlow version *wire* names, such as "1.3", or "0x07 (not a version known)"."""
    return TEXT.get(wire, "0x%02x (not a version known)" % (wire,))


def health(negotiated):
    """`/health`'s answer for *negotiated* (`{dpid: wire version}`, each connected switch's):
    ``{"ok", "offers", "switches": {dpid in decimal: version}, "problems"}``. A switch on a
    version outside the pin is a problem, naming it and the pin: another app loaded beside
    this one has widened nothing (Ryu intersects), so it means the pin is not in force."""
    offers = [TEXT[w] for w in PINNED]
    problems = ["switch %d negotiated OpenFlow %s, outside the pin (%s)"
                % (dpid, version_text(wire), ", ".join(offers))
                for dpid, wire in sorted(negotiated.items()) if wire not in PINNED]
    return {"ok": not problems, "offers": offers, "problems": problems,
            "switches": dict((str(dpid), version_text(wire))
                             for dpid, wire in sorted(negotiated.items()))}
