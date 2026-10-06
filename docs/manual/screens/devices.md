# Devices

Every device in the network, searchable and filterable.

## The list {#the-list}

Each row: the device's status (answering or not, from the reachability reader), its address
and platform, whether it was at its committed intent when it was last MEASURED and by
what, and when that was. Hover the time to see when its golden last changed. Onboardings
still pending are rows too, and open their own page.

## Drained {#drained}

**Switched off for now:** in a network managed in band, the manager's own polling crosses data
interfaces at about the rate customer traffic does, so interface counters cannot tell a
drained device from a quiet one. No badge is drawn and no alert is held back until Drained is
measured from customer traffic by address. What follows is how it worked while it was on.

A **Drained** badge beside a device's name (and in its page's header) is MEASURED, never set
by hand: every interface that is up, not a loopback, not in a VRF, and not the device's
management path (the interface its golden gives the management address) carried less than
0.5 unicast packets a second, in and out, over the last 3 minutes, read from the interface
counters Prometheus already scrapes. Its words name each interface, its rates now and since
when it has been quiet. It goes when traffic rises again. A device with no golden, or whose
management address is on no interface in its golden (a loopback), is not judged, so it is
never drawn drained. Needs attention lists a Grafana alert on drained devices only under What
was checked instead of raising it as a row.

A measurement is any save that read the device and compared it with its golden: a capture,
a deploy's or restore's read after the push, and a Save All that found it unchanged (which
records its decision in a commit of its own, naming every device it read). The intent state
is the newest measurement's, read from that commit, never by reading the device now. A
capture or Save All (see [Capture and Save All](capture)) brings it up to date. The device
page's Overview compares the golden with intent live and says when it was last measured.

A Save All that changed some goldens before 2026-10-02 named only those devices, so an
unchanged device's read in it is not recoverable; its last measurement reads as the save
before.

## Selecting devices {#selection}

Ticking devices opens a deploy for them, on today's page until the redesign's batch deploy
is built (plan 7.4).
