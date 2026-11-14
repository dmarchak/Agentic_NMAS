# Settings

The tool's configuration, in three scopes of one page: **Installation** (what every network shares: sign-in, the central NetBox connection, this host), **Default** (the base layer the networks that inherit take their values from) and **a network** (its own settings). The scope bar at the top moves between them; its network picker, **Choose a network**, leads with the networks that differ from Default, standalone ones first.

## A network's page {#network}

- **Its mode**, on the banner: it inherits from Default, or it is standalone and takes nothing from Default, with who made it so and when. The banner's button opens the switch's preview (see [Inherit or stand alone](settings-switch)).
- **Self-healing**, a third tab, is the network's own heal policy and who is told about it (see [Self-healing](#self-healing)).
- **One card per group**, on two tabs (Integrations: Grafana, Grafana dashboards, Prometheus, Loki, Kea, Monitoring profile and S3 archive; Network: Verify settle windows, Deploy workers, Deploy failure limit, Golden tags kept, Configuration read timeout, NetBox excluded VRFs, the three Show commands settings (answer cap in KiB, devices read at once, answers kept in days), SDN: escalate an unanswered incident after (minutes) (15 unless set; see [SDN](sdn#responses)), and the Inventory source card). Each card says where its values come from: *set here*, *inherited from Default*, *not configured for this network*, *not applicable here*, or *unset everywhere*; and every field shows its value with where it came from. A secret shows as "set", never its value.
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
- **Code repository** (Network tab): where the network's jobs and apps live, apart from its configuration repository, a local path or an https URL and a branch, each network's own; the last fetch, what it registered and what it could not; **Fetch now** fetches it into Mercury's read-only copy and registers each app folder at the fetched commit as a Draft (see [A network's code repository](code-repository)).
- **What AI may send** (Network tab): the network's AI data classes, each with its state (see [What AI may send](#ai-classes)).
- **SDN controllers** (Integrations tab): the network's own controller connections, on their
  own card, never inherited from Default (see [SDN controllers](#sdn-controllers)).
- **Each group's own choice**: inherit from Default, its own, or not applicable. Choosing another opens that switch's preview in place of the card; nothing is saved by the choice itself. A group not configured has **Configure <group>…**, which takes its values in the card; a group that is its own takes its fields in place, with **Save** and **Test** (see [Save a card](settings-switch#save) and [Test a connection](settings-switch#test)).

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

What every network shares, standalone ones included: these are the installation's own, never a network's or Default's, so a change here changes all of them. Its tabs are Connections, Access and identity, Platforms and roles, Console servers, Diagnostics, AI and Notifications (see [Notifications](#notifications); the Server card is on Connections; AI and workflow left with the AI family, 2026-10-14, and AI came back as each network's background AI features, 2026-10-27).

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
- **Access and identity**: read-only by design. **The gates**: for each action (reveal, approve, confirm, configure, publish, break-glass), whether it needs a verified identity and whether it needs a person, with each one's origin (defaulted, recorded or chosen). **Cloudflare Access**: the team domain, audience, trusted peers (shown to a verified person only) and the key cache, 5 minutes to a day. **Service tokens**: what a service may run, and the labels that name them in the audit. **You**: who this request is, by display name, and which gated actions it may take. The one control on those cards is **Record this decision**, which writes the value already in force and records who and when; the operator changes a value in the settings file on the host. **Display names**: how each person is named on every screen, record summary and export. With nothing set it is the part of the identity before the "@"; **Change…** opens a row's form, **Save** sets a name and **Use the default** returns to it. You set your own, an admin anyone's; the verified identity is under each row, closed until opened, and every record keeps it. **Time zone**: the zone every screen draws your times in, set from your browser on your first visit; **Change…** opens its form and **Save** keeps the zone you type, refused naming it when the time zone database does not know it ([Time zone](installation-settings#time-zone)).
- **Platforms and roles**: the platform map (a NetBox platform → its driver, config dialect, delivery and NETCONF, with a default driver), a table with Remove, Add and **Preview changes**; and where roles live: a device's kind is its NetBox Device Role's `mercury_kind` field, set in NetBox ("not classified in NetBox" without one, never a guess). The preview names every device whose driver the change moves; **Test** reads one of them through its new driver; **Save** is bound to the preview and refreshes each NetBox network. A platform Mercury has no driver for yet (Arista EOS, HP ProCurve and ArubaOS-Switch, Aruba) takes a **discovery driver** (`arista_eos`, `hp_procurve`, `aruba_osswitch`, `aruba_procurve`, `aruba_os`) with the config dialect **none: read only**: its devices load and are read only, by that family's capture list on **Ask the device** and **Show commands**, and every device-changing operation is refused naming the driver (its row says so). A discovery driver with a dialect, or a Cisco driver without one, is refused.
- **Diagnostics**: is Mercury itself healthy, and what is it doing. **Redaction**: whether every log handler masks secrets, measured now (not healthy, it is also a Needs attention row). **Drift checks**: one schedule for every network, and each network's on or off, last and next run, with **Check now**. **In flight**: every network's running operations and what finished in the last half hour. **The app's log**: its last lines, filtered, read when asked (see [The installation's settings](installation-settings)).
- **Console servers**: see [below](#console-servers).
- **AI**: each network's background AI features, turned on only here after their estimate, with their caps and Turn off: see [Settings › AI](settings-ai).
- **AI (hosted)** (AI; Connections keeps one line linking to it): the key, the cap per day (yours to set, with no ceiling of the tool's own; a large increase shows what it means before it saves, and **No cap** needs `no cap` typed and a reason to confirm, the reason kept and drawn on History, with a standing Needs attention row while it is set: see [The day cap](installation-settings#ai-cap)), whether hosted AI is allowed (**Allow** with a reason, **Turn off**), today's spend, and each task's pinned model, prices and cap per call. Its **Test** is one small, recorded call; it carries the **AI** mark, every control that needs AI does, and is drawn disabled with the reason while hosted AI cannot answer, while **Save**, **Replace…** and **Allow** stay usable (see [The AI mark](installation-settings#ai-mark)).
- **Server** (Connections): the address and port Mercury listens on. They are read when Mercury starts, so a Save says the change waits for the next restart.
- Every **Save**, **Replace** and **Turn off** is recorded in the installation's settings record with who, when and the names of what changed, never the values (see [The installation's settings](installation-settings)).

## Console servers {#console-servers}

The installation's console servers, for out-of-band ZTP ([how it works](onboard#out-of-band-ztp)): how Mercury reaches each console-server port NetBox holds, the console servers' keys, and their SSH host keys. Every card opens above the tab's three cards, and the cards below read themselves again when anything here changes, in any tab.

- **Console-server ports**: one row per port Mercury has a record for: its NetBox port (the console server and the port's name, or "not in NetBox", or "not read" when NetBox could not be read, said once above the table with why), the driver, the host (with its jump host and SSH port), the console (a container name, or a TCP port), the key's name (with its user, or **no key stored** when the name holds none), the SSH host key held (its key type and its whole fingerprint, monospace and selected in one click, to compare with the server's own; **refused** when a session was refused, or "kept on first contact" before the first session), and who changed it and when. Each row has **Edit…** and **Remove…**, and **Re-key…** where a host key is held ([how it works](rekey#console-server)). NetBox's console-server ports with no record are listed under it, each with **Set up…**; **Add a port record…** opens an empty form (a port's NetBox id is chosen from NetBox's ports, or typed when NetBox cannot be read). Saving is checked by the store and refused, naming every field, with nothing written ([how it works](installation-settings#console-servers)).
- **Keys**: each console-server key stored (its name, user, fingerprint and when it was made, and whether a port uses it), and **Generate a key…**, which shows only the public key and its `authorized_keys` line, never the private half ([how it works](installation-settings#console-server-keys)).
- **Changes**: the store's own log, the last ten records added, replaced or removed, with who and when.

## SDN controllers {#sdn-controllers}

A network's SDN controllers, on its own card at the foot of a network's **Integrations** tab
(Default's and every other network's). Each network's list is its own: a network never takes
Default's controllers, whatever its mode, and a network that sets none has none (the operator's
decision, 2026-10-27). The card is how a controller is added, changed, tested and removed; what
each controller is doing is on [SDN](sdn).

- **Stage**, first: whether the network is marked **lab**, **pilot** or **production**, or **not
  marked** (the default), each network's own and never inherited from Default. Until the AUTO
  production-readiness gate is complete, SDN responses' AUTO is turned on only on a network
  marked lab ([SDN › Responses](sdn#responses)): on any other network **Turn AUTO on** is drawn
  disabled and refused, and AUTO that was turned on before the network was marked otherwise runs
  nothing unattended (the Mode card says it is suspended). A stage that cannot be read is said,
  and is never read as lab. To change it, choose the stage, give a **Reason** and press
  **Save**: you must be a verified person; the answer is drawn in the card (**Marked <network>
  <stage>** with what it was before, or **Not done:** with why). Save is refused without a
  reason, for a value that is not a stage, and when another person changed the stage since the
  card was drawn, naming both. Each change is recorded in the network's settings record with
  who, when, the stage before and after, and the reason. It clears by marking the network lab,
  or, for a network that carries real traffic, by the gate being complete.
- **The saved connections**, one row each: its name, whether Mercury's last read found it
  **connected**, **partly read**, **not answering** or **not read yet**, its driver, its
  northbound URL, whether a credential is set (**a user and password set**, **a token set** or
  **no credential**, never the credential itself) and whether TLS is used and verified. Each
  row has three controls:
  - **Test connection** asks the controller now, with what is saved, and answers on the row:
    "Answered: N switches connected" (with its version where the controller reports one) or
    "Couldn't connect: <the reason>". It changes nothing.
  - **Edit** opens the form below with the connection's values. Its name stays (remove it and
    add another to rename it); its credential is never drawn back, and a blank keeps it.
  - **Remove…** says first what removing does: Mercury stops reading it and its stored
    credential is erased; the flow-intent records naming it are kept, as a history; nothing on
    the controller or its switches changes. **Remove <name>** does it; **Cancel** leaves it.
- **Add a controller** (or **Edit <name>**): the form.
  - **Name**: one you choose, unique on the network.
  - **Driver**: each driver Mercury knows, with its status. Only a built driver can be chosen
    (Ryu, through its `ofctl_rest` application); the later ones (ONOS; OpenDaylight and the
    fabric managers, read-first) and the unmaintained one (Floodlight) are listed and not
    selectable. Each driver declares what it can do, and Mercury offers only that.
  - **Northbound URL**: where Mercury reads and writes, http or https, an IPv4 address, an IPv6
    address in brackets (`http://[2001:db8::10]:8080`) or a name.
  - **Username** and **Password**: only if the controller asks for them. They are stored
    encrypted, as device credentials are, and are never shown or read back; a blank keeps the
    one stored.
  - **Verify TLS**, for an https URL.
  - **Southbound address**: where the switches connect to the controller. Informational: drawn
    on SDN › Controllers, never used to connect.
  - **The controller application's own cookies**: a flow carrying one of these is the
    controller's own (`0` by default, a learning switch's); any other cookie that is not
    Mercury's makes a flow unauthorised on [SDN › Flows](sdn#flows).
- **Test connection** reads the controller's switches and version with what is typed, before
  anything is saved, and answers in place, naming the URL it asked. **Save** is refused until a
  Test has answered for the URL as typed, with the same driver and TLS choice: change the URL
  after a Test and Save says so, naming it. A Test's answer stands for 30 minutes. Save is also
  refused when another person changed the same connection since the form was drawn, naming each
  field and both values. A save or a removal is recorded in the network's settings record with
  who, when and the names of what changed, never a credential.

## What AI may send {#ai-classes}

The **What AI may send** card, on a network's Network tab, lists what a hosted AI call about
the network may carry, by class, each with its state:

- **Allowed**: alert labels, metric series, masked log lines and intent diffs, on wherever
  hosted AI is on.
- **Topology**: the network model's slice (devices, links, adjacencies), on unless an admin
  turned it off.
- **Device state**: the answers to the AI read set's show commands (operational state, never
  configuration), masked, a line with a secret's shape dropped whole. **Off by default on
  every network**, and each network's own: turning it on for Default turns it on for Default
  alone. With it off, the AI analysis asks for no reads, and its first pass is the whole
  analysis.
- **Configuration**: configuration lines, through the configuration masking; off on every
  network until the classification marking is built.

**Turn on…** on the device state row opens a reason in place. Type why, in at least three
words, and **Turn device state on for <network>** turns it on for that network: an admin's
decision, so only a verified person may, and it is recorded in the network's settings record
with who, how they were verified, when and the reason; the row then says who turned it on, when
and why. A reason of fewer than three words, or a request that is not a verified person's, is
refused, naming why, and nothing changes. **Cancel** closes the reason with nothing changed.
**Turn off** is one press, no confirm, and stops new sends at once; it is recorded with who and
when. Device state is on only while both its switch and the record of who turned it on with a
reason are in place, so a switch set any other way reads as off; a setting that cannot be read
is off, and a network carrying a classification marking has every class off.

## Self-healing {#self-healing}

A network's own heal policy, on its **Self-healing** tab beside Integrations and Network
(Default's and every other network's). It is each network's own and never inherited from
Default: turning healing on for Default turns it on for no other network. Self-healing restores
a device to its committed intent; nothing on this tab contacts a device.

- **Self-healing on <network>**: the mode now (**Off**, **Dry run**: every step but the apply,
  each record saying what it would have done, or **Auto**: the Tier 1 kinds allowed below heal
  without a person until the expiry, then dry run), with why in words ("dry run: AUTO … expired",
  "off: self-healing is stopped everywhere"); who set it, when and their reason; the network's
  stage (Auto is allowed only on a network marked lab, until the AUTO production-readiness
  gate); production's bar (30 days and 100 dry-run events at 1% wrong or fewer; lab drills never
  count); and the policy's fingerprint. Values a person did not confirm are not in force, and
  the chip says **not in force: off**. **History of this policy** opens the network's own
  records of it: each confirmed change, each Turn off, an Auto that reached its expiry, and Who
  is told's saves.
- **Mode** is a dropdown, the mode in force chosen: choosing **Off**, **Dry run** or **Auto**
  (Auto offered only on a network marked lab; elsewhere it is drawn disabled, saying why) opens
  that change as a window over the page, beside the dropdown, with the focus inside it. Every
  change on this tab opens the same way, and nothing changes until you confirm: **Cancel** or
  Escape closes it, the dropdown back on the mode in force and the focus back on what you
  pressed. While Auto is in force, **Change Auto's expiry…** opens Auto's change again. Off and
  Dry run are previewed as they open. For Auto, **Auto until** is a quick choice, **1 h**,
  **2 h**, **4 h**, **8 h**, **24 h** or **7 days** from the preview, or **a time** in the
  date-time picker, in your own time zone (the one every time on the screens is drawn in,
  named beside the picker), with its UTC drawn beside it; at most 7 days away. A quick choice's
  time is drawn into the picker when it is previewed, and that time is the one confirmed,
  however long after you press. Each choice is previewed in the window, writing nothing:
  **What this changes** (the mode, the kinds that heal without a person, the kinds proposed,
  each hard stop that moves; now and after the confirm), each check that refuses it, and the
  preview's six parts one level down. The confirm names the work: **Turn on Auto for
  <network> until <time> (<your time zone>)**, **Set <network> to dry run** or **Turn
  self-healing off for <network>** (and, for the changes below, **Save the fix kinds for
  <network>** or **Set “<guard>” for <network>**). It needs a verified person and a
  **Reason**. It is bound to the preview's fingerprint: if the policy, the network's stage or
  the kill switch moved since, it is refused naming what moved, and nothing is saved; the
  window opens again with the refusal, what you chose and your reason kept, previewed again.
  Its steps are `check`, `re-plan`, `compare`, `write` and `record`. The answer is drawn in
  the policy's card.
- **Turn off**: one press, no confirm, effective at once, recorded with who and when (its steps
  `write` and `record`). Nothing new starts; a heal already applying finishes its own verify and
  rollback. Turning a network back on is a change, previewed and confirmed as above.
- **Fix kinds**: each kind's tier, fixed by Mercury (1 heals in Auto, 2 is proposed to a person,
  3 only alerts, 4 is never automatic). Each Tier 1 kind's toggle (**Heal** or **Dry run only**)
  and each Tier 2 kind's (**Propose** or **Alert only**) is the control: the setting in force is
  drawn pressed, and pressing the other opens that one change, previewed as it opens and
  confirmed with a reason as a mode change is. **Change fix kinds…** chooses several at once:
  which Tier 1 kinds heal in Auto (one more at a time, each after its lab scenario passed) and
  which Tier 2 kinds are proposed. A proposal waits on **Needs
  attention** as a Critical row naming what changed and that the fix needs your decision:
  **Review the fix…** opens its card, with **Approve and run on <device>** (by its hash, a
  reason optional unless a line needs one) and **Decline** (with a reason; nothing is sent)
  ([Approve or decline a self-healing proposal](heal-proposal)).
- **Hard stops and guards**: each value, where it comes from (set, lab default or default) and
  its default, with **Edit…**, which opens its change beside it, previewed and confirmed as a
  mode change is. On a network marked
  lab the grace period and the hold after a nearby change read 120 s and 60 minutes unless set.
  Planned work, held devices and no-change windows always stop a heal; a rolled-back heal always
  halts the policy until a person lifts it. **A flap: transitions of one interface within** (3 in
  10 minutes by default) is how Mercury measures a flapping port from the syslog it receives, and
  **A port is bounced at most** (once an hour) is the limit on a port bounce; a second need
  within the repeat window is a dampening proposal for a person ([The port
  bounce](heal#bounce)).
- **Who is told**: the team told about this network's healing (its addresses and webhooks are on
  [Notifications](#notifications)) and the events that tell it: can't fix, a fix waiting for a
  person, halted or held, every automatic heal, and cleared. **Save** is refused when the team
  no longer exists or another person changed it since the card was drawn, naming both; its steps
  are `check`, `write` and `record`. The AI analysis of a can't-fix is its own background
  feature, off until an admin turns it on for the network in Settings › Installation › AI; the
  card draws its state from that switch (off, on with who turned it on and its caps, approval
  ended, on with hosted AI off, stopped at its cap).
- **Stop self-healing everywhere…** (the installation's kill switch) says what stopping does,
  asks why (never required) and stops every network at once with **Stop self-healing
  everywhere**: one press, no confirm, recorded with who, when and why. While stopped, every
  network's tab says so, and **Resume self-healing…** previews each network's mode once resumed;
  **Resume self-healing everywhere** needs a verified person and a reason, and is refused if what
  resuming does moved since the preview.

## Notifications {#notifications}

Settings › Installation › **Notifications**: who Mercury tells, for every network. Each network's
Self-healing tab chooses which team it tells.

- **Email relay**: the relay host (empty: no email is sent), its port, **Security** (STARTTLS,
  required; TLS from the start; or none, only to a relay on this host's loopback), the username,
  the sender (**From**) and Mercury's address for links (what people open Mercury by, so a
  message's link opens; empty, a message's link is the page's path alone and says so). **Save**
  writes what you changed, recorded old and new and drawn on History; it is refused when another
  person changed a field since the card was drawn, naming both values. The password shows only
  as set, by whom and when; **Replace…** takes a new one, and **Store it** stores it encrypted,
  never shown. **Test send to…** asks which of the teams' addresses, and **Send the test** sends
  a test message there through the relay as saved, saying in the card whether it was sent; its
  head says when mail was last sent. **The first time, add the team first:** Test send to… offers
  only a team's addresses, so save the relay, then add a team and its address (**Add a team…**,
  then **Add and send a code**). The code arriving is the relay's first test, and typing it back
  verifies the address; **Test send to…** then checks the relay again whenever it changes.
- **Webhooks**: each with its team, its URL drawn as its scheme and host only (the rest may be the
  receiver's token), its format and its last delivery. **Add a webhook…** takes the team, a
  name, the URL (https, or http only to this host's loopback; IPv4 or IPv6), the format
  (Generic, signed: JSON with an HMAC-SHA256 signature over its timestamp and body; Slack's,
  Teams' and PagerDuty's come later) and the signing secret, typed once and never shown; **Add
  and send a code** adds it unverified and off and sends it a verification code, which you read
  where it posts and type in its team. **Test send** sends it one message now; **Edit…** changes
  its name, URL or secret (a new URL is a new receiver, off until its code is typed back);
  **Remove…** says what removing does first.
- **Teams**: **Add a team…** and **Add the team**, then each team's addresses and webhooks.
  **Send a code** sends one to a destination that has none waiting. **Add and send a code**
  adds an address unverified and off and emails it a code, which expires after 15 minutes; type
  it and press **Verify**, which verifies the address and turns it on (a wrong code spends one of
  five tries). **Send again** sends a new code. A verified destination has **Turn off** (it then
  receives nothing) or **Turn on**. **Remove…** asks first, and says that its delivery log rows
  stay: press **Remove** to remove it, or **Keep it**. **Told about** names the networks whose Self-healing tab chose the team.
- **Delivery log**: every attempt is a row in [History](history), kind notification, with its
  channel, its recipient masked to its domain (a webhook its host), its outcome and error. A
  failed delivery is tried three times and then raised under Needs attention, with its error. A
  message carries no configuration line and no secret.

## What is not here yet {#not-yet}

- Nothing: **creating a network** is **New network…**, at the foot of the scope bar's network menu; a new network starts as inheriting from Default, and its page here offers the switch at once (see [Create a network](settings-switch#create)).
