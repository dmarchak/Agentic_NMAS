# Settings

The tool's configuration, in three scopes of one page: **Installation** (what every network shares: sign-in, the central NetBox connection, this host), **Default** (the base layer the networks that inherit take their values from) and **a network** (its own settings). The scope bar at the top moves between them; its network picker leads with the networks that differ from Default, standalone ones first.

## A network's page {#network}

- **Its mode**, on the banner: it inherits from Default, or it is standalone and takes nothing from Default, with who made it so and when. The banner's button opens the switch's preview (see [Inherit or stand alone](settings-switch)).
- **One card per group**, on two tabs (Integrations: Grafana, its dashboards, Prometheus, Loki, Kea, the topology service, the monitoring profile, the S3 archive and the lab; Network: the deploy tuning, the TFTP server and NetBox's excluded VRFs). Each card says where its values come from: *set here*, *inherited from Default*, *not configured for this network*, *not applicable here*, or *unset everywhere*; and every field shows its value with where it came from. A secret shows as "set", never its value.
- **The S3 archive** is Mercury's connection to MinIO: Default's values are every network's
  unless a network sets its own. It holds each network's goldens at
  `goldens/<network>/<device>/<stamp>.cfg` and Show commands answers past their retention at
  `reads/<network>/<run>.json`, under its prefix. Its key can read and write the bucket and
  never delete. The status bar and Needs attention ask only whether its bucket answers, and
  write nothing; its full test writes a probe object, reads it back byte for byte and states its
  size, naming the first step that fails with what the server answered.
- **Each group's own choice**: inherit from Default, its own, or not applicable. Choosing another opens that switch's preview in place of the card; nothing is saved by the choice itself. A group not configured has **Configure…**, which takes its values in the card; a group that is its own takes its fields in place, with **Save** and **Test** (see [Save a card](settings-switch#save) and [Test a connection](settings-switch#test)).

## Default's page {#default}

Default's cards show its values and, on each, who takes them: "inherited by 12 · own Grafana in 4 · not configured in 2 · not applicable in 1", counting only the networks that chose to inherit, with the names one click down. Each card takes its fields in place, with **Save** and **Test**; a secret shows only as set, with **Replace…**. A change to Default changes every network counted there, and the result says so.

## Installation {#installation}

What every network shares, standalone ones included: these are the installation's own, never a network's or Default's, so a change here changes all of them. Its tabs are Connections, Access and identity, Platforms and roles, Server, AI and workflow, and Diagnostics.

- **Records database** (Connections): the database Mercury's records move to, store by store (receipts first). With no host it is **off**: every store stays on its files, as today. Its card says whether it is **answering** (the last Test passed, with the server's version, when and by whom), **not answering** (the check that failed, named), or **not tested yet**, and when a Save or Replace came after the last Test. **Save** writes the host, port, database and role; it never opens the database, so it works with the database down or the password wrong, and the change is recorded in the installation's settings record. **Test** asks the database six things and names the first that fails: it signs in, the server is PostgreSQL 18, the role owns its database, the role is not a superuser, Mercury reaches it on a loopback address, and a temporary row written and read back is rolled back. The password shows only as set; **Replace…** opens the rotation order: change it on the server first, with the host step `scripts/host-steps/postgres-rotate.sh`, then enter the same password here, and its Test runs at once (see [The records database](records-database)).
- **NetBox connection** (Connections): the central NetBox every network reads, its address, auth scheme (Bearer for NetBox 4.x tokens, Token for older) and whether its certificate is verified. Its badge is NetBox's health as last read (reachable, not answering, refused, not configured), and **Test** asks it now. The API token shows only as set; **Replace…** takes a new one and tests it. **Writes allowed** is the master switch for every network's NetBox writes: on, it offers **Turn off**; off, it says who turned it off and when. Turning it on is never this card's: it is the confirm of an authorised NetBox write. Each network's NetBox scope (its region) is under that network.
- **Proxmox** (Connections): the hypervisor's address, node, whether its certificate is verified, the backup VMs and the backup storage, and the token's declared expiry (the token cannot read its own). The token shows as its id and set; **Replace…** takes the id and the secret together and tests them.
- **Commit author** (Connections): the name and email on the author line of Mercury's commits; the person who acted is in each commit's `Actor:` trailer.
- **The assistant** (AI and workflow): the AI switch. Off, the chat answers that AI is off and makes no call to the model. On devices it is read-only: every command it sends is on the read-only allowlist. The workflow switches of today's page are not here: they change only the assistant's prompt text and leave with its rewrite.
- **Background agent** (AI and workflow): its state, never a switch: off until Stage 8, when it becomes a responder that proposes changes for a person to confirm. Set on in the installation's settings file, the card says so, and that it starts only when Mercury restarts.
- **Diagnostics**: is Mercury itself healthy, and what is it doing. **Redaction**: whether every log handler masks secrets, measured now (not healthy, it is also a Needs attention row). **Drift checks**: one schedule for every network, and each network's on or off, last and next run, with **Check now**. **In flight**: every network's running operations and what finished in the last half hour. **The app's log**: its last lines, filtered, read when asked (see [The installation's settings](installation-settings)).
- **Server** (Server): the address and port Mercury listens on. They are read when Mercury starts, so a Save says the change waits for the next restart.
- Every **Save**, **Replace** and **Turn off** is recorded in the installation's settings record with who, when and the names of what changed, never the values (see [The installation's settings](installation-settings)).
- **Not here yet**, each said on the page and linked to today's Settings page: the Access and identity, and Platforms and roles tabs.

## What is not here yet {#not-yet}

- **Installation's other tabs** are on today's Settings page, each linked from where it will be (above).
- **Creating a network** is on today's page; a new network starts as inheriting from Default, and its page here offers the switch at once.
