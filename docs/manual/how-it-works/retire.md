# Retire a device

Retiring takes a device out of management completely, in one recorded act, keeping its
history. It is the only way a device leaves: deleting a row would leave it half-managed.

## The preview

The preview lists every step and every refusal at once, and what retiring does NOT do:

- **The credential must be safe to drop.** The latest break-glass export must hold the
  device's current credential, because after retiring, the tool no longer holds it.
- **NetBox's stored credentials**: if NetBox holds the device's credential lines and NMAS
  wrote them, they are masked first and read back; if writes are off, retiring is refused,
  naming it.
- **What else still points at it**, each said as read: a heartbeat alert rule, Prometheus
  still scraping its address.

## The apply

One commit, as you, with your reason: the device's golden and intent removed from the
current tree (they stay in history), its manifest entry and inventory row removed, its
credentials dropped, and a `Not-Done:` line for each thing deliberately kept: the NetBox
record, Oxidized still polling, the startup file frozen.

## Two ways in, two kinds of evidence

The Device page's Retire trusts the break-glass EXPORT LOG, because it cannot reach a file
on your laptop, and says so. The command on the host (`nmas-retire`) opens the record itself.
