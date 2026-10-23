# Settings

The tool's configuration, in three scopes of one page: **Installation** (what every network shares: sign-in, the central NetBox connection, this host), **Default** (the base layer the networks that inherit take their values from) and **a network** (its own settings). The scope bar at the top moves between them; its network picker leads with the networks that differ from Default, standalone ones first.

## A network's page {#network}

- **Its mode**, on the banner: it inherits from Default, or it is standalone and takes nothing from Default, with who made it so and when. The banner's button opens the switch's preview (see [Inherit or stand alone](settings-switch)).
- **One card per group**, on two tabs (Integrations: Grafana, Grafana dashboards, Prometheus, Loki, Kea, Monitoring profile and S3 archive; Network: Verify settle windows, Deploy workers, Deploy failure limit, Golden tags kept, Configuration read timeout, NetBox excluded VRFs, the three Show commands settings (answer cap in KiB, devices read at once, answers kept in days), and the Inventory source card). Each card says where its values come from: *set here*, *inherited from Default*, *not configured for this network*, *not applicable here*, or *unset everywhere*; and every field shows its value with where it came from. A secret shows as "set", never its value.
- **The S3 archive** is Mercury's connection to MinIO: Default's values are every network's
  unless a network sets its own. It holds each network's goldens, masked (a community, a
  password hash or a key reads `<redacted:…>`, so a copy there restores no secret; the
  repository keeps the golden whole), at `goldens/<network>/<device>/<stamp>.masked.cfg`, and
  Show commands answers past their retention at
  `reads/<network>/<run>.json`, under its prefix. Its key can read and write the bucket and
  never delete. The top bar's integrations and Needs attention ask only whether its bucket answers, and
  write nothing; its full test writes a probe object, reads it back byte for byte and states its
  size, naming the first step that fails with what the server answered.
- **Prometheus** (Integrations tab): where its API answers, and its **Targets dir** (the
  targets directory): where Mercury writes the scrape-target files for the devices this Prometheus serves. Each
  Prometheus has its own: a network that inherits Default's Prometheus is in Default's files,
  and a network with its own Prometheus names its own directory and gets its own files, its
  own record of each regeneration, and its own job-health row comparing what that Prometheus
  scrapes with what its networks' inventories hold ("…, for <network>'s Prometheus"). A
  directory two Prometheus owners both name is refused for both, each naming the other, so
  one network is never scraped as another's. With no directory named, Mercury writes nothing
  for that Prometheus, and its row says to name one.
- **Inventory source** (Network tab): where the network's devices come from, its own list on this host or NetBox through filters, and how fresh they are. For a NetBox network it counts the devices loaded, skipped, loaded with a warning and no longer in NetBox, and names each one in groups closed until opened: the skipped by cause with where to put it right, the warned by cause, and those NetBox no longer returns with since when (see [Where a network's devices come from](settings-switch#source)).
- **Each group's own choice**: inherit from Default, its own, or not applicable. Choosing another opens that switch's preview in place of the card; nothing is saved by the choice itself. A group not configured has **Configure…**, which takes its values in the card; a group that is its own takes its fields in place, with **Save** and **Test** (see [Save a card](settings-switch#save) and [Test a connection](settings-switch#test)).

## A deleted network's page {#deleted}

A link, a bookmark or a tab drawn before a network was deleted leads to its page, which says
only that: **"Branch was deleted"**, when (its time on hover) and by whom, and where its data
is (`lists_removed/<folder>-<UTC time>`, kept, never erased). It has no mode banner, no tabs, no
cards and no buttons; the scope bar above it leads to Installation, Default or another network.
A tab drawn before the delete keeps its cards on screen, but each Save, switch, preview or
Delete there answers in place, refused, naming the network and where its data went, and nothing
is written anywhere. Any other page whose address names the deleted network (a sidebar link,
a bookmark or a device's page drawn before the delete) opens the same page for Default instead,
a device's page opening Default's Devices, and the top bar says so: **"Default · Branch was
deleted"**; every link on it then names Default. A name that never was a network is still
refused, naming it. A folder that something left at the deleted network's path since does not
bring it back. To use the name again, create a network of that name (see
[Create a network](settings-switch#create)): it starts empty, inheriting from Default.

## Default's page {#default}

Default's cards show its values and, on each, who takes them: "inherited by 12 · own Grafana in 4 · not configured in 2 · not applicable in 1", counting only the networks that chose to inherit, with the names one click down. Each card takes its fields in place, with **Save** and **Test**; a secret shows only as set, with **Replace…**. A change to Default changes every network counted there, and the result says so.

## Installation {#installation}

What every network shares, standalone ones included: these are the installation's own, never a network's or Default's, so a change here changes all of them. Its tabs are Connections, Access and identity, Platforms and roles, Console servers, and Diagnostics (the Server card is on Connections; AI and workflow left with the AI family, 2026-10-14).

- **Records database** (Connections): the database Mercury's records move to, store by store (receipts first). With no host it is **off**: every store stays on its files, as today. Its card says whether it is **answering** (the last Test passed, with the server's version, when and by whom), **not answering** (the check that failed, named), or **not tested yet**, and when a Save or Replace came after the last Test. **Save** writes the host, port, database and role; it never opens the database, so it works with the database down or the password wrong, and the change is recorded in the installation's settings record. **Test** asks the database six things and names the first that fails: it signs in, the server is PostgreSQL 18, the role owns its database, the role is not a superuser, Mercury reaches it on a loopback address, and a temporary row written and read back is rolled back. The password shows only as set; **Replace…** opens the rotation order: change it on the server first, with the host step `scripts/host-steps/postgres-rotate.sh`, then enter the same password here, and its Test runs at once (see [The records database](records-database)).
- **Record stores** (Connections): the 24 stores that can move to the records database, its
  badge counting how many are on it ("N of 24 on the database"). They are Deploy receipts,
  Acknowledgements, Restarts seen, Planned-restart windows, Planned-restart windows ended
  early, Rotations and saves, the four break-glass logs (exports, download verdicts, checks,
  drills), Reveals, Host steps said done, Heartbeat window re-measures, NetBox removals,
  Network settings changes, Onboarding runs, Inventory edits, Approval queue, Rollback blocks,
  Retries authorised, NetBox objects created, modified and adopted, and Interrupted
  operations. Each row says **Where** it is (the records database, or its files, with each
  network's count) and its **Last check**: **matches** or **DOES NOT MATCH** (the database
  against what the files held), **does not answer**, or "not checked yet: the check runs
  every 5 minutes"; a store on its files has nothing to compare. **Move to the database…**
  and **Move back to files…** open a preview in place, each network's count beside what is
  in the table; the confirm reads **Move N lines** (or **Switch to the database (no lines to
  copy)**, or **Move back**), is bound to those counts, and is refused if a line was written
  before you confirm. A move copies, switches, checks and leaves the files read-only for a
  release; if its check fails, the store is switched straight back to its files and nothing
  is lost (see [The records database](records-database)).
- **NetBox connection** (Connections): the central NetBox every network reads, its address, auth scheme (Bearer for NetBox 4.x tokens, Token for older) and whether its certificate is verified. Its badge is NetBox's health as last read (reachable, not answering, refused, not configured), and **Test** asks it now. The API token shows only as set; **Replace…** takes a new one and tests it. **Writes allowed** is the master switch for every network's NetBox writes: on, it offers **Turn off**; off, it says who turned it off and when. Turning it on is never this card's: it is the confirm of an authorised NetBox write. Each network's NetBox scope (its region) is under that network.
- **Proxmox** (Connections): the hypervisor's address, node, whether its certificate is verified, the backup VMs and the backup storage, and the token's declared expiry (the token cannot read its own). The token shows as its id and set; **Replace…** takes the id and the secret together and tests them.
- **Commit author** (Connections): the name and email on the author line of Mercury's commits; the person who acted is in each commit's `Actor:` trailer.
- **Access and identity**: read-only by design. **The gates**: for each action (reveal, approve, confirm, configure, publish, break-glass), whether it needs a verified identity and whether it needs a person, with each one's origin (defaulted, recorded or chosen). **Cloudflare Access**: the team domain, audience, trusted peers (shown to a verified person only) and the key cache, 5 minutes to a day. **Service tokens**: what a service may run, and the labels that name them in the audit. **You**: who this request is, and which gated actions it may take. The one control is **Record this decision**, which writes the value already in force and records who and when; the operator changes a value in the settings file on the host.
- **Platforms and roles**: the platform map (a NetBox platform → its driver, config dialect, delivery and NETCONF, with a default driver), a table with Remove, Add and **Preview changes**; and where roles live: a device's kind is its NetBox Device Role's `mercury_kind` field, set in NetBox ("not classified in NetBox" without one, never a guess). The preview names every device whose driver the change moves; **Test** reads one of them through its new driver; **Save** is bound to the preview and refreshes each NetBox network.
- **Diagnostics**: is Mercury itself healthy, and what is it doing. **Redaction**: whether every log handler masks secrets, measured now (not healthy, it is also a Needs attention row). **Drift checks**: one schedule for every network, and each network's on or off, last and next run, with **Check now**. **In flight**: every network's running operations and what finished in the last half hour. **The app's log**: its last lines, filtered, read when asked (see [The installation's settings](installation-settings)).
- **Console servers**: see [below](#console-servers).
- **Server** (Connections): the address and port Mercury listens on. They are read when Mercury starts, so a Save says the change waits for the next restart.
- Every **Save**, **Replace** and **Turn off** is recorded in the installation's settings record with who, when and the names of what changed, never the values (see [The installation's settings](installation-settings)).

## Console servers {#console-servers}

The installation's console servers, for out-of-band ZTP ([how it works](onboard#out-of-band-ztp)): how Mercury reaches each console-server port NetBox holds, the console servers' keys, and their SSH host keys. Every card opens above the tab's three cards, and the cards below read themselves again when anything here changes, in any tab.

- **Console-server ports**: one row per port Mercury has a record for: its NetBox port (the console server and the port's name, or "not in NetBox", or "not read" when NetBox could not be read, said once above the table with why), the driver, the host (with its jump host and SSH port), the console (a container name, or a TCP port), the key's name (with its user, or **no key stored** when the name holds none), the SSH host key held (its fingerprint, **refused** when a session was refused, or "kept on first contact" before the first session), and who changed it and when. Each row has **Edit…** and **Remove…**, and **Re-key…** where a host key is held ([how it works](rekey#console-server)). NetBox's console-server ports with no record are listed under it, each with **Set up…**; **Add a port record…** opens an empty form (a port's NetBox id is chosen from NetBox's ports, or typed when NetBox cannot be read). Saving is checked by the store and refused, naming every field, with nothing written ([how it works](installation-settings#console-servers)).
- **Keys**: each console-server key stored (its name, user, fingerprint and when it was made, and whether a port uses it), and **Generate a key…**, which shows only the public key and its `authorized_keys` line, never the private half ([how it works](installation-settings#console-server-keys)).
- **Changes**: the store's own log, the last ten records added, replaced or removed, with who and when.

## What is not here yet {#not-yet}

- Nothing: **creating a network** is **New network…**, at the foot of the scope bar's network menu; a new network starts as inheriting from Default, and its page here offers the switch at once (see [Create a network](settings-switch#create)).
