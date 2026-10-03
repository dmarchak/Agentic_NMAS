# Credentials

The credentials the tool holds for each network, and the record that holds them all. On the
redesigned pages it opens on the break-glass record, the page's first part. The credential list
and each credential's expiry join it, as tabs beside the record, when the redesign builds them
(plan 7.6). Until then they open on today's view.

## The break-glass record {#breakglass-record}

The record is one file holding every device's credential in a network, and the key that opens
the tool's stored secrets, sealed with a passphrase you choose. It is the way back into the
devices when the tool cannot sign in to them, and the way back to the stored secrets if the host
loses its key. It belongs to the whole network, not to one device, so it lives here. Every way
in opens it here, for the network it names:

- the result of a rotation;
- Needs attention's break-glass row;
- the Settings line.

The card at the top answers one question: does the record you hold recover every device? It
reads one of these:

- **current:** every credential in use is in the last export;
- **not current:** it names the devices rotated since, which the record cannot recover;
- **not intact:** the last download did not arrive whole;
- **none exported:** nothing says a record exists.

Job health judges it every 5 minutes, comparing digests and never a value. An export made after
its last check is said as such: it held the credentials in use when it was made. The card also
gives the last export: when, by whom, how many devices, the key's fingerprint and the file's
sha256, and whether the browser confirmed the download arrived intact.

**Export the record…** opens the export on this page. How it works:
[Export the break-glass record](breakglass-export). **Check a break-glass file…** opens the
copy you keep, here, in memory, and says device by device whether it still recovers them:
[Check a break-glass file](breakglass-export#check).

## Where a credential comes from {#what-it-is-for}

A device's credential is found in this order, first match wins: its own override, the list's
designated credential list, a role profile, a site profile, the default profile. Every device
shows where its credential came from. Values are write-only: none is ever shown back.
