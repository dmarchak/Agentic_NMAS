# Drained: intended in NetBox, observed by measurement, done by a runbook (design, for sign-off)

The operator, 2026-10-06 and 07, after the class challenge (C550 to C552). Status: **a design
for sign-off, with its mockup; then the measurements in section 10; then the build.** Nothing
here is built. Register: C551 (the measurement), C552 (the interface-counter version,
switched off), C531 (revert as one action, which Return to service uses), C553 (a job starts
when an operation creates its work). The ownership of every piece of device state is in
[NSOT_OWNERSHIP](NSOT_OWNERSHIP.md).

## 1. The shape, in one paragraph

**NetBox's device status is the INTENDED state** ("drained", a custom status). A person sets
it in NetBox, or the Drain runbook sets it through a confirmed operation. **Mercury's
measurement is the OBSERVED state**: no customer traffic crosses the device while it is
reachable, counted by address. Mercury compares the two the way it compares intent with the
golden. Agreement is shown as evidence beside NetBox's status ("NetBox: Drained · Measured: no
customer traffic since 21:58 UTC"); disagreement is a Needs attention row. Draining a device is
the first BUILT-IN RUNBOOK: ordered, vetted steps on the existing pipeline, which succeeds only
when the measurement agrees. Mercury never keeps a drained state of its own. The manual mark
(C550) and the measured "Drained" label (C551's interface-counter version) retire.

## 2. Why interface counters failed here, and why by address

C551's fast version judged every interface but the management path by its unicast packet rate.
It could not work on this lab (measured on the host's Prometheus, 2026-10-06):

- **Management is in band.** s2's loopback is reachable only through r2, so the manager's
  polling of s2 crosses r2's Gi3, a data interface, at about 5.9 unicast pkt/s. At a floor of
  0.5 pkt/s that read as customer traffic.
- **Customer traffic in a lab runs at about that rate.** At a floor of 10 pkt/s nearly every
  device read drained (C552), and Needs attention held back their alerts.

A rate does not say whose packets they are; an address does. In production, out-of-band
management keeps data-interface counters cleaner, but routing protocols' unicast, BFD and the
device's own traffic still cross data interfaces. So the count is by address everywhere.

## 3. Ownership

| Piece | Owner | Who may write it | Mercury shows it as |
|---|---|---|---|
| The device's **status** (Active, Drained, Planned, …) | **NetBox** | a person in NetBox; Mercury only inside a confirmed runbook step, through the NetBox write chokepoints, the before recorded | NetBox's value, with its source and its age |
| The **drain configuration** (section 5) | **Mercury's intent git** | a deploy (preview, confirm, verify, rollback, record) | the EXPLANATION beside the state |
| **Customer traffic** across the device | **Mercury's measurement** (a reader) | nobody: it is read | the EVIDENCE beside NetBox's status |
| The **customer prefixes** | **NetBox** (a prefix role) | a person in NetBox | the count found, in Settings |

## 4. The comparison

NetBox's status is compared with the measurement, and the drain configuration is shown as
the explanation:

| NetBox status | Measured customer traffic | Mercury draws | Needs attention |
|---|---|---|---|
| Drained | under the floor for W | **Drained ✓** ("NetBox: Drained · Measured: none since 21:58 UTC") | nothing; traffic alerts held back |
| Drained | falling, within T of the status change | **Draining** (n pkt/s, since HH:MM) | nothing; traffic alerts held back |
| Drained | above the floor beyond T | **Drain incomplete** | **a row**: what still crosses it (later, IPFIX names it), and the action |
| Active | above the floor | **In service ✓** (no badge) | nothing |
| Active | under the floor for W, and no drain configuration | **Idle** (muted: night, a new site) | nothing |
| Active | under the floor for W, with drain configuration present | **Drained, not in NetBox** | **a row**: set NetBox's status, or take the drain back |
| Active, after Drained | above the floor again | **Back in service** for an hour | nothing |
| any | not measured (no prefix role, no counting ACL on the device, counters unread) | NetBox's status alone, with "Not measured: <why>" | nothing |
| NetBox unreadable | any | "NetBox unreadable" and the measurement alone, never a guess | the NetBox source's own row |

W (how long under the floor) and T (how long a drain may take) are measured on the lab's
drains (section 10), not chosen.

## 5. The drain configuration (explanation, and the runbook's profile)

Read from the committed golden (never the device):

| Mechanism | Form | Platforms |
|---|---|---|
| OSPF stub router | `max-metric router-lsa` (all forms), `router ospf` and OSPFv3 | IOS, IOS-XE |
| IS-IS overload | `set-overload-bit` | IOS-XE |
| BGP graceful shutdown (RFC 8326) | `bgp graceful-shutdown all neighbors` (the GRACEFUL_SHUTDOWN community, local preference 0 at the receiver) | IOS-XE |
| RIP / RIPng metric | `offset-list … out <n> <interface>`; `ipv6 rip <name> default-information originate metric <n>` | IOS, IOS-XE |
| OSPF cost | `ip ospf cost` / `ipv6 ospf cost` raised on data interfaces | IOS, IOS-XE |
| Native maintenance modes | none on IOS and IOS-XE; NX-OS GIR, EOS maintenance mode and IOS XR BGP graceful maintenance where a later platform has them | later |

A line is a drain only if it was added after the last In service. A line that has always been
there is configuration. Each needs a measured removal shape (C531 part 1, `8565f97`) before
Return to service can take it back.

## 6. The measurement, by address

**Customer prefixes come from the source of truth:** the NetBox prefixes carrying one prefix
role, IPv4 and IPv6. The role is named by a setting, `drained_customer_prefix_role`, empty by
default. While it is empty, or the role holds no prefixes, every device is "Not measured",
saying which.

**The ACL counts and never blocks.** Mercury generates one per address family from those
prefixes. It is rendered into intent by a template section and deployed through the normal
pipeline:

```
ip access-list extended NMAS-CUST-V4
 10 remark NMAS: counts customer traffic; permits everything
 20 permit ip 198.51.100.0 0.0.0.255 any
 30 permit ip any 198.51.100.0 0.0.0.255
 ...
 1000 permit ip any any
ipv6 access-list NMAS-CUST-V6
 20 permit ipv6 2001:DB8:100::/48 any
 30 permit ipv6 any 2001:DB8:100::/48
 ...
 1000 permit ipv6 any any
```

- **It never blocks.** Every entry permits, and verify refuses a deploy whose running ACL does
  not end in `permit … any any`.
- **It is applied inbound on every data interface:** up, not a loopback, not in the
  management VRF. Every crossing packet enters once, so inbound counts each packet once.
- **When the prefixes change,** its entries change through Mode B's `named-acl.entry`, which is
  measured exact for IPv4 on both platforms. IPv6 needs C554 first: the context check misses
  `ipv6 access-list`.
- **The count** is the sum of the customer entries' hits, never the final `permit any`, as a
  rate over the window. The floor is measured during a known drain, and is expected near zero,
  because a management packet never matches a customer prefix.

**Reading the hit counts:**

| Platform | How | To measure first |
|---|---|---|
| IOS-XE (C8000v) | model-driven telemetry: a periodic dial-out of `Cisco-IOS-XE-acl-oper` (`access-lists/access-list/access-list-entries/access-list-entry/state/match-counter`) to the Telegraf receiver already in Settings, into Prometheus | whether the C8000v streams per-entry counters, at what period, whether they count what the data plane forwards, and the series' labels |
| IOS (vIOS) | no model-driven telemetry: a reader job running `show ip access-lists NMAS-CUST-V4` (and the IPv6 one) through the read-only allowlist, or SNMP if a MIB exposes per-entry hits | whether any vIOS MIB answers per-entry hits; if none, the CLI read's cost per device per minute |

A per-device CLI read is a job, never per request (the scale rule), and its interval is
measured.

## 7. The record

- **The badge**, on the Devices list (in the name cell, its words on hover) and in the device
  page header: NetBox's status with the comparison's mark ("Drained ✓", "Drain incomplete",
  "Drained, not in NetBox"). The hover names both sources and their ages.
- **Overview's Service panel:** NetBox's status (with a link to it, its age, who changed it and
  when, from NetBox's change log), the measurement (rate now, window, read age, how it is
  measured), the drain configuration, what is held back, and the runbook run that did it.
- **History:** NetBox's status changes (from its change log: who and when) and the
  measurement's transitions (from the reader) on the device's timeline. A filter group,
  "Drains".
- **The hold-back is narrowed.** C550 to C552 held back every Grafana alert on a drained
  device, which would hide "Interface output discards". Now only traffic alerts are held back
  (rules labelled `nmas_traffic="1"`, declared on the rule, never guessed from its name), and
  only while NetBox says Drained and the measurement is not Drain incomplete. Each held-back
  alert is listed under What was checked, naming the state.
- **Needs attention has two drain rows:** Drain incomplete, and Drained, not in NetBox. Each
  names what is wrong and the action, and clears when the comparison agrees.

## 8. NetBox: the custom status

NetBox has no stock Drained status. `FIELD_CHOICES` with `dcim.Device.status+` ADDS one. The
running NetBox is **4.6.9**, read on the host on 2026-10-07, so it takes the tuple form
`(value, label, colour)`. The dict form with a description is NetBox 4.7's.

**The host step (the operator's; netbox-docker in `~/netbox-docker` on the NMAS host, its
`configuration/` mounted read-only into the containers):**

```bash
cd ~/netbox-docker
cp configuration/extra.py "configuration/extra.py.bak-$(date -u +%Y%m%dT%H%M%SZ)"
cat >> configuration/extra.py <<'EOF'

# Mercury (C551): a device status for a drained device. Set by the drain runbook or a person
# in NetBox; Mercury compares it with its customer-traffic measurement. NetBox 4.6: tuples.
FIELD_CHOICES = {
    "dcim.Device.status+": (
        ("drained", "Drained", "orange"),
    ),
}
EOF
python3 -c "import ast; ast.parse(open('configuration/extra.py').read())" \
  && docker compose restart netbox netbox-worker
```

It is proved by its result, a read the agent may make: the device endpoint's OPTIONS then
lists `drained` among the status choices. On 2026-10-07 it listed the stock seven: offline,
active, planned, staged, failed, inventory, decommissioning.

**What Mercury's `nmas` account needs.** NetBox has no field-level permissions: a `change`
permission on `dcim.device` covers every field, status included, limited only by its
constraints. Measured read-only on 2026-10-07:
- the token is `nmas`'s and is write-enabled (expires 2027-10-05);
- OPTIONS on r2's endpoint offers `PUT` with `status` writable, so `nmas` may change r2;
- `nmas` cannot list its own permissions (403), so whether a constraint limits which devices
  it may change is not measured. The measurement is one OPTIONS per device, made by the
  runbook's preview, which says which devices it may not change.

On Mercury's side, a status write also needs the master switch (`netbox_allow_writes`) and a
declared authority for `dcim.device` `status` (`modules/netbox_authz.py`), and records its
before (the NetBox rules).

**Never `offline`.** That says the device is out of service for any reason. `drained` says
it is drained on purpose and is a promise the measurement checks.

## 9. Runbooks: the drain is the first built-in one

Industry treats a drain as both a built-in action and an instance of custom procedures:
- **Vendors ship maintenance modes:** NX-OS GIR, EOS maintenance mode, IOS XR BGP graceful
  maintenance, IS-IS overload, BGP graceful-shutdown (RFC 8326).
- **Platforms wrap them as verified workflows:** Apstra's Drain state, CloudVision Change
  Control with built-in and custom actions, Nautobot Jobs, NetBox scripts, AWX job templates.

Mercury's shape, in order:

1. **A runbook engine on the existing pipeline.** A runbook is ordered, vetted steps, and
   nothing a person could not do step by step:
   - an intent change and its deploy (preview, confirm by hash, apply, verify, rollback,
     record);
   - wait for a measurement, bounded, naming what it waits for;
   - check a condition;
   - set a NetBox status, through the chokepoints;
   - record;
   - notify.

   A run plans across devices as one CHANGE SET (C531 part 3): one preview, one confirm, steps
   in order, the change set reverted as one (C531 part 2). It shows on the run's stepper, the
   device's History and In progress (C537).
2. **Drain and Return to service, the first BUILT-IN runbook.**
   - **Drain:** for each device, the drain profile of its platform (section 5: OSPF max-metric,
     IS-IS overload, BGP graceful-shutdown, a native maintenance mode where one exists), and
     the neighbour-side steps the topology or a declaration names (RIP offset on the
     neighbour, for example). The preview reads NetBox (the `PUT` check, the current status)
     and the measurement now. The apply deploys the change set, sets NetBox's status to
     drained, and WAITS for the measurement. It succeeds only when every device reads Drained
     ✓, and names each one still Draining when its wait ends.
   - **Return to service:** the drain's change set reverted as one, NetBox's status set back to
     the before it recorded, then waiting for In service ✓.
3. **Custom runbooks per network.** Declarative YAML of those step types, in the network's
   repository (`runbooks/<name>.yml`), APPROVED before use the way templates are (approval
   keyed on the file's content). Arbitrary scripts come later if ever, and only through the
   pipeline. Stage 8's agent may DRAFT a runbook for a person's approval, and never approves
   one.

**The measured state is the runbook's verification step.** A drain that deploys and never
drains fails as a drain, the way a deploy whose verify fails rolls back.

**Where it goes in the plan (proposed):** a new item, **P.22 Runbooks**, after Stage 7 (it
needs the v2 stepper, History, In progress and the device page's Actions), with C531 parts 1
to 3 and C553 as its prerequisites. It sits alongside P.16's evaluation of the job machinery:
the OPERATIONS stay Mercury's, and the queueing and survival of a run across a restart use
whatever P.16 decides. It comes before Stage 8's agent drafts runbooks.

**Its first mockup covers:**
- the Drain runbook started from a device's Actions menu, and from a selection on Devices;
- its preview: per device, the platform profile and the neighbour-side steps, the change set's
  program, NetBox's status change and the `PUT` check, the measurement now;
- the confirm;
- the run's stepper, including the "waiting for Drained ✓" step with its bound and what it
  waits on;
- the result: success, or the devices still Draining;
- Return to service from the run's record and from History;
- a later board: the Runbooks library, built-ins and the network's custom ones with their
  approval state.

## 10. To measure first (the operator's runs; the agent's read-only reads)

1. **C8000v telemetry:** does `Cisco-IOS-XE-acl-oper` stream per-entry `match-counter` on a
   periodic subscription, at what minimum period, counting what the data plane forwards? On
   r2: a test ACL with a permit entry for a host prefix, inbound on Gi3; known traffic across
   it; `show ip access-lists` against the streamed value.
2. **vIOS:** does any MIB answer per-entry ACL hits? If none, the time `show ip access-lists
   <name>` takes on s1 (never s3).
3. **The ACL's cost:** forwarding before and after a 50-entry ACL inbound on one interface of
   each platform, under the same load.
4. **The floor, W and T:** customer pkt/s on r2 during a known drain and after it.
5. **The removal shapes** (C531 part 1): the probe runs on each platform, so Return to service
   can take each drain line back.

## 11. Screens (drawn in the mockup for sign-off)

- The device page header: NetBox's status with the comparison's mark.
- Overview's Service panel in every row of section 4.
- History's drain entries.
- The Devices list: the status in the name cell, service counts, a filter.
- Needs attention: the two drain rows, and a held-back traffic alert under What was checked.
- Settings › NetBox: the customer prefix role with the prefixes it finds, and whether NetBox
  has the `drained` status.

## 12. Questions for the operator

1. The prefix role: one setting per network, or one for the installation?
2. Inbound-only counting on data interfaces: agreed?
3. The hold-back narrowed to rules labelled `nmas_traffic="1"`: agreed, with the monitoring
   templates labelling the traffic rules?
4. ~~NetBox's status~~: answered 2026-10-07 (section 8): a custom `drained`, never `offline`.
5. P.22 Runbooks: placed as proposed in section 9?
