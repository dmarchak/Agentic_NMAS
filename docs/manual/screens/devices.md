# Devices

Every device in the network, searchable and filterable.

## The list {#the-list}

Each row: the device's status (answering or not, from the reachability reader), its address
and platform, whether it was at its committed intent when it was last MEASURED and by
what, and when that was. Hover the time to see when its golden last changed. Onboardings
still pending are rows too, and open their own page.

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
