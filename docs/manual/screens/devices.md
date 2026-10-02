# Devices

Every device in the network, searchable and filterable.

## The list {#the-list}

Each row: the device's status (answering or not, from the reachability reader), its address
and platform, whether it was at its committed intent at its last capture, and how old that
capture is. Onboardings still pending are rows too, and open their own page.

The intent state is AS OF THE LAST CAPTURE: it is read from that capture's commit, never by
reading the device. A capture (see [Capture and Save All](capture)) brings it up to date.

## Selecting devices {#selection}

Ticking devices opens a deploy for them, on today's page until the redesign's batch deploy
is built (plan 7.4).
