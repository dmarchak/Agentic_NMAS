# Intent authoring: the model, the editor and actions (design, for review)

**Status:** a design for the operator's review (2026-10-20). Nothing in it is built, and nothing
is built from it before that review. It delays nothing in Lab 8.

**Why now.** In Lab 8's step 4 (r4 Gi5, 2026-10-20), one decision ("Gi5 up, addressed, in area
10") took eight hand edits in two sections of the YAML, and two of them were traps:
- `shutdown` against `no_shutdown`;
- `no_ip_address` beside a new `ipv4`.

The editor's preview then disagreed with the planner (C1426). Its checks passed both contradictory
pairs (C1429), and finding the interface and `routing.ospf` meant scrolling (C1428). This document
is about the three layers under that experience:
- **the model:** what intent says;
- **the editor:** how a person changes it;
- **actions:** one decision, one change.

**The invariant (the operator's), held by every proposal below:** every action, form and wizard
produces an ordinary intent commit. That commit goes through the same preview, the exact program
confirmed by hash, merge-only deploy, Verify, rollback and record. Each action is a pure function
from intent to intent, with unit tests. Nothing here adds a second way to change a device.

Contents:
1. What the code does today (measured)
2. The model
3. The editor
4. Actions
5. Arguments against
6. The items, sized
7. The order
8. Lab 9's video

---

## 1. What the code does today (measured 2026-10-20)

**The fleet's intent** (8 devices after r6's retirement, read from the committed `host_vars` on
the host, no values printed but addresses and keys):

- **The documents are dense.** Every one of the 56 interfaces carries all 30 interface keys
  (`hostvars.INTERFACE_DEFAULTS`), and only 339 of the 1680 are set (20%, about 6 per interface).
  A person editing r4 scrolls through 80% empty keys.
- **Interface state is mostly unmanaged.** 54 of 56 interfaces set neither `shutdown` nor
  `no_shutdown`, so Mercury leaves their admin state as the device has it. One sets `shutdown`
  and one, r4 Gi5 since step 4, sets `no_shutdown`.
- **Intent holds IOS line fragments, not concepts:**
  - `ospf: ["priority 100"]` (6 interfaces);
  - `ospfv3: ["1 area 0"]` (11);
  - `ip_nat: ["inside"]` (9);
  - `mop: ["no mop enabled", "no mop sysid"]` (16, the C8000v's printed default);
  - `negotiation: "auto"` (39, also a printed default);
  - `static_routes[].spec` (a raw route string);
  - `routing.ospf[].networks` (raw `network … area …` lines).
- **OSPFv3 is already interface-shaped and OSPFv2 is not.** The same decision, "this interface is
  in area 10", is one interface key for IPv6 (`ospfv3: ["1 area 10"]`) and a `network` line under
  `routing.ospf` for IPv4. That asymmetry is the second section in step 4's eight edits.
- **The OSPF network statements, classified against each device's interface addresses:**

  | Shape | Count | Where |
  |---|---|---|
  | Equals exactly one interface's subnet (a loopback's /32, a link's /30, /31 or /24) | 11 of 13 | r1 to r4: every statement, r4's four included (Lo0, Gi3, Gi4, Gi5) |
  | One summary-shaped statement covering several interfaces (`10.255.0.0 0.0.255.255 area 0`) | 2 of 13 | s3 (3 interfaces), s4 (2) |

  Within each device, the statements are already in ascending address order. So a derivation
  that sorts by address reproduces today's order.
- **RIP:** 4 devices (s1, s2, r1, r2), each with one classful `network` line that covers all of
  the device's addressed interfaces. A derivation ("the classful network of each RIP interface,
  de-duplicated") reproduces each one.
- **No contradictory pair is committed now** (shutdown with no_shutdown, or no_ip_address with
  ipv4).

**The code** (file and line references as of 2026-10-20):

- **No intent schema** beyond three key tables:
  - `hostvars.INTERFACE_DEFAULTS` and `INTENT_SECTIONS`;
  - `parsers/base.py`'s `SCHEMA_DEFAULTS`;
  - and the feature packs' specs (`modules/nsot/features/`; docs/FEATURE_PACKS.md).
- **One validation function**, `intent_edit.validate`: the editor's check and commit, and
  `nmas-config-check` in CI. It checks:
  - unknown keys;
  - misplaced keys;
  - the syslog block;
  - printable characters and no secret values;
  - the packs' checks (area ids, area types, `ospf_interface` process and area together).

  It compares no pair of keys, and it never parses `ipv4`, `helper_addresses` or a route's
  `spec`.
- **The OSPF pack already has the interface field the operator proposes.**
  `features/ospf.py`'s INTERFACE spec is {process, area, cost, network_type, priority,
  hello_interval, dead_interval}, rendered as `ip ospf N area A`. Nothing derives a `network`
  statement from it; the pack's areas hold their networks separately.
- **The editor and the planner are two diff engines (C1426's cause):**
  - The editor's preview (`intent_edit.preview`) diffs `roundtrip.canonical_lines`, which strip
    the hidden defaults (` no shutdown` under an interface) from both sides unconditionally.
  - The planner (`deploy.merge_diff`) skips a hidden default only when the device prints no
    counterpart (C1401).
  - So for Gi5, the editor said 7 lines and "shutdown stays". The planner sent 8 lines,
    ` no shutdown` among them, and that 8th line is what produced the plan's "Gi5 comes up".
- **Verify keys adjacencies by router-id, not by (neighbour, interface)** (C1427), and judges
  each protocol by its count. `up` is checked by name. The receipt records neighbour counts and
  the expected effects, not a verdict per check, which is why step 4's receipt never named
  "Gi5 comes up".
- **Generators that exist:**
  - `bulk_intent` (compare-and-set path steps across many devices);
  - onboarding's bootstrap intent;
  - `profile.py`, the per-network monitoring profile (snmp, syslog, ntp and the like, overlaid
    through `effective()`). It is not a role profile.

  Nothing generates interface or routing intent from parameters.
- **Cross-device checks that exist:**
  - `neighbours.expected` pairs a link's two ends by subnet, and never compares their areas;
  - the topology takes a link's area from the first end it reads, so a mismatch is never drawn;
  - ZTP's `relay_for` and `relay_agrees` (one interface on the prefix, its helper, Kea's subnet);
  - Kea's pool and subnet overlap checks.
- **The fidelity checks.** `roundtrip.compare` is set-based with an ordering policy:
  - OSPF, RIP and interface bodies are unordered;
  - ACLs and route-maps are ordered.

  The byte-equal checks are the fixed point (parse → render → parse gives identical YAML) and
  `test_intent_from_before_the_packs_renders_byte_for_byte_as_it_did`. That last test is the
  precedent for this design's migration test.

---

## 2. The model: intent-shaped fields, IOS derived

### 2.1 The principle

A field names a decision the network makes, and the dialect derives the lines. A person never
types a line's negation, a hidden default, or a statement that restates an interface's address.
Raw lines stay as the escape hatch (`unmodeled`, a pack's `raw`), shown as such. They are never
the normal path.

### 2.2 The fields (the operator's list, and more)

| Decision | Field (vendor-neutral) | IOS dialect derives | Replaces |
|---|---|---|---|
| Admin state | `enabled: true \| false`, absent = not managed | `no shutdown` (a hidden default: sent, never printed) or ` shutdown` | `shutdown`, `no_shutdown` (the pair cannot contradict: one field) |
| Addressing | `ipv4: [prefix]`, `ipv6: [prefix]`, `addressing: none` for an explicit unnumbered or L2 interface, absent = not managed | ` ip address A M` (mask from the prefix), ` no ip address`, secondaries | `ipv4` string, `no_ip_address` (one field: an address and "none" cannot both be set) |
| OSPF membership | `ospf: {process, area, cost, network_type, priority, passive}` per family (`ospfv3` the same shape) | per the process's `area_style`: a `network <subnet> <wildcard> area A` under `router ospf` (today's lab), or ` ip ospf N area A` on the interface; OSPFv3's ` ospfv3 N ipv6 area A` | raw `ospf: ["priority …"]`, raw `ospfv3: ["1 area 0"]`, per-interface `routing.ospf[].networks` lines |
| RIP membership | `rip: true` on the interface (the process's version and redistribution under `routing.rip`) | the classful `network` lines, de-duplicated | `routing.rip.networks` raw lines |
| NAT role | `nat: inside \| outside` | ` ip nat inside/outside` | `ip_nat: ["inside"]` |
| DHCP relay | `relay: [kea]` or `relay: [address]` (`kea` resolves to the network's Kea address, from settings) | ` ip helper-address A`, `ipv6 dhcp relay destination A` | `helper_addresses`, `dhcpv6_relay` |
| Static route | `{prefix, next_hop, distance, name}` | ` ip route …` / ` ipv6 route …` | `static_routes[].spec` raw string |
| Printed platform defaults | none in intent | the dialect's printed-defaults table renders them (`negotiation auto`, `no mop enabled`, `no mop sysid` on the C8000v), as `platform_defaults` already does for hidden ones | `negotiation`, `mop` on 55 of 56 interface values |

**More fields than the operator listed, in the same spirit:**
- **`switchport: {mode, access_vlan, trunk_vlans, native_vlan}`:** one field for today's five
  `switchport_*` keys. Lab 9's switch needs it.
- **`description` derived from a link** (optional, never forced). When the topology knows the far
  end, the default is "to <device> <interface>". A person's own text always wins.
- **`role` on an interface** (`uplink`, `access`, `management`, `link`). It drives the semantic
  checks and the actions; it renders nothing.
- **`area_style` on an OSPF process** (`network` | `interface`). The one dialect choice that keeps
  today's renders byte for byte (section 2.4) while new devices can take the interface style.

### 2.3 Derivations, stated precisely

- **`network` statements (area_style `network`).** For each interface with `ospf.area` and an
  IPv4 address, emit the address's network and wildcard (`/32` → `0.0.0.0`, `/31` → `0.0.0.1`,
  `/30` → `0.0.0.3`, `/24` → `0.0.0.255`) with its area. Sort by address; de-duplicate (two
  interfaces on one subnet give one line).
- **An authored range stays authored.** A statement that covers several interfaces (s3's and s4's
  `10.255.0.0 0.0.255.255 area 0`) is a decision of its own: "everything in this block is in area
  0". It stays in the pack's `areas[].networks[]`, drawn as a range, and the interfaces it covers
  show "in area 0 by the range". A derivation that replaced it with three /32 and /24 lines would
  change s3's configuration, and a removal of the /16 is Mode B, so it is never done silently.
- **`enabled`.** `true` renders ` no shutdown`. That line is a hidden default (sent, never
  printed), so the dialect owns the C1401 rule in one place: send it when the device prints
  ` shutdown`; when the device prints nothing, the line is already true. `false` renders
  ` shutdown`. Absent renders nothing.
- **`addressing: none`.** It renders ` no ip address`. It is refused beside an address (the field
  cannot hold both).

### 2.4 Byte for byte: what the measurement supports, and the test that proves it

The operator asked that the new model reproduce every device's current render byte for byte. The
measurement says it can, with one honest qualification:
- **r1 to r4's OSPF:** all 11 statements derive from interface addresses and areas, in today's
  order. r4's four (Lo0, Gi3, Gi4, Gi5) are among them.
- **s3's and s4's OSPF:** their one range statement reproduces only as an authored range (2.3).
  That is the qualification: the model keeps ranges, and does not derive everything.
- **RIP:** the 4 devices' classful lines derive from their RIP interfaces.
- **Admin state:** 54 of 56 interfaces are absent (renders nothing, as today). The other two map
  to `enabled: false` and `enabled: true`.
- **Printed defaults:** `negotiation` and `mop` move to the dialect's printed-defaults table, keyed
  by platform image. They render the same lines in the same place in the stanza (today's
  `interface(i)` macro order), so the stanza is byte-equal.

The proof is a test, not this paragraph: `test_the_new_model_renders_every_captured_device_byte_for_byte`.
It takes every real capture in `tests/fixtures/` and each device's migrated intent, and renders
both old and new. A planted control (one interface's area changed) must fail it. This document
claims only what the measurement shows. "Byte for byte for all devices" is that test's to say.

There are eight devices today, not nine: r6 is retired. The new R6 and R7 are drafted in today's
model for Lab 8 (the operator's direction) and are migrated with the rest.

### 2.5 Migration

1. **A dual reader.** The renderer accepts both the old keys and the new ones for one release,
   and the check refuses a document that holds both for one decision (`shutdown` and `enabled`).
2. **One migration commit per network, previewed.** For each device, `migrate(intent) → intent`
   (a pure function) is applied, and the preview shows two things: the YAML diff, and the
   rendered program diff, which must be empty. A non-empty render diff refuses that device and
   names the line. It is never committed "close enough".
3. **The commit carries `Source: migrate-intent-model`.** Deploy plans after it send nothing
   (the same check as C1401's "the next plan sends nothing").
4. **The old keys are removed from the defaults table one release later,** when no committed
   intent uses them (a scan with a floor, as the register's checks have).

Each step is a release with its own CI. Intent at the version before stays readable by History
and by revert, through the dual reader kept for reading only.

### 2.6 Import (capture → intent)

`seed.py` and the parsers already have the right gate. A line becomes a pack field only when the
pack's partial reproduces it exactly (`features.reproduces`). The new model extends the same gate:
- **network statements:** a statement whose network equals exactly one interface's subnet becomes
  that interface's `ospf.area`, if and only if re-deriving gives the same line. Otherwise it stays
  an authored range;
- **admin state:** a printed ` shutdown` becomes `enabled: false`. A device that prints nothing
  becomes `enabled: true` only if the person asks to manage the state. Otherwise it stays absent.
  Import never manages more than the person chose;
- **printed defaults** matching the platform's table are dropped from intent, because the dialect
  renders them;
- **`ip helper-address`** pointing at the network's Kea address becomes `relay: [kea]`.

Coverage and fidelity stay as they are: `roundtrip.compare`, and the fixed point, which must hold
on the new model too.

### 2.7 The fidelity checks

They keep their meaning; the round trip simply runs through the new fields. Three additions:
1. **A semantic fixed point:** derive, then parse back, gives the same fields (a derived
   `network` line parses back to `ospf.area`, not to a range).
2. **The render-identical migration test** (2.4).
3. **The dialect's printed and hidden defaults as one table per platform image**, each entry
   with its measured capture, under the existing rule that fixtures are real captures.

### 2.8 The dialect contract (K47)

This model is the contract's input. K47's decision (2026-10-19): the contract designed after
Lab 8, IOS and IOS-XE moved onto it after Lab 9 (Core 1.0), EOS at Stage 10. This design makes
the contract concrete:

- **The fields are vendor-neutral** (2.2). Interface names stay device-native (`GigabitEthernet5`,
  `Ethernet5`): a name is the device's, and `ifnames` already normalises comparisons.
- **A dialect supplies:**
  - `render(fields) → lines`;
  - `parse(lines) → fields` (with the reproduces gate);
  - its hidden defaults (sent, never printed) and printed defaults (printed, never authored),
    per platform image;
  - a capability map: which fields it can render, and how. For example, `area_style`
    `interface` only, a dialect without RIP, or VRRP version 3 only;
  - its removal shapes (Mode B's measured `removal` table).
- **A field a dialect cannot render is refused at the check, by name.** It is never dropped.
  This mirrors the IPv6 parity rule: a capability that cannot serve says so.
- **IOS is the first dialect** (IOS and IOS-XE share `_common.j2` today and stay one dialect with
  two printed-defaults tables). EOS is next. Admin state is the motivating difference: an EOS
  Ethernet port and an IOS router's interface do not share a default, which is exactly why
  `enabled` is explicit in intent and the default belongs to the dialect. Whether EOS takes the
  `network` style or the interface style is a measurement on an image when EOS is sized.

---

## 3. The editor

### 3.1 The layout

**A Fields view and a YAML view of one document, kept in sync.** The YAML view sits under
Advanced, and its check is the same one. This is board J (signed off 2026-10-04, unbuilt: C907).
This design updates the board for the new model; a changed board is drawn and signed again
before it is built.

- **Only fields that are set are shown**, plus **Add setting…**, which lists the unset fields
  with a one-line description each. The measurement supports it: 80% of interface keys are empty.
- **An unset field that matters says so.** Admin state absent shows "Not managed: the device has
  it up" (or down), read from the last capture, with its age. Showing only set fields must never
  hide what the device is doing.
- **Typed widgets:**
  - `enabled`: a toggle with a third state, "not managed";
  - `area`: a dropdown of the areas the network's intent already uses, plus "New area…";
  - `vrf`: from intent's `vrfs`, and from NetBox's VRFs where the token can read them;
  - `nat`: inside, outside or none;
  - `relay`: Kea, or an address;
  - address fields parse as prefixes, IPv4 and IPv6 alike, and refuse a host bit or a mask the
    family cannot hold.

  NetBox has no OSPF areas (core NetBox models no routing), so areas come from intent alone.
- **Search and jump-to (C1428):** a section index built from the parsed document (interfaces by
  name, each routing process, static routes, ACLs), plus a filter box that narrows the Fields view
  as the person types (`gi5`, `area 10`). This needs no new library: the index is the parsed YAML.
  A code editor with folding (CodeMirror, for instance) would be a new third-party licence, which
  is the operator's decision. It is not needed for search.
- **One preview (C1426).** The editor's preview becomes the planner's own computation against the
  last capture, so the editor and the confirm cannot disagree. The cost is a planner run per check
  (bounded: one device, its stored capture, no device contact). The editor names that the capture
  may be stale, and the confirm re-plans against a fresh read as today.

### 3.2 Semantic checks

The existing within-device checks gain:
- **Contradictions (C1429).** By construction in the new model; until then, refused by name in
  `intent_edit.validate`.
- **An ABR without area 0:** a device with a non-zero area and no area-0 interface or virtual link.
- **A relay whose target is not Kea's address, or whose interface's prefix has no Kea subnet.**
  `relay_agrees` generalised from ZTP.
- **A static route's next hop on no connected subnet of the device.**

Cross-device checks, against an index of every device's committed interfaces and areas. The index
is rebuilt on commit and never read device by device per request (the enterprise-scale rule):
- **a link's two ends:**
  - in the same subnet and the same area;
  - with matching OSPF network type;
  - with matching MTU (the ExStart trap);
  - with matching hello and dead timers.

  The topology then draws a mismatch instead of taking the first end's area.
- **an address used twice in the fleet,** or overlapping a NetBox prefix assigned elsewhere;
- **a passive interface that is the only path to a neighbour** intent expects.

Each check names both operands, per the standing rule: "r4 Gi5 is in area 10; R6 Gi2 on the same
/30 is in area 0".

---

## 4. Actions: one decision, one change

### 4.1 The shape

An action is a pure function: `action(intents, params, facts) → {changes, reasons, implied}`.
- **`intents`:** the committed intent of the devices it touches.
- **`facts`:** what it reads elsewhere (NetBox's free prefixes, Kea's address), fetched before
  the call so the function stays pure and testable.
- **`changes`:** the new intent per device.
- **`implied`:** the lines the change leaves on the device that a person may remove (Mode B),
  each with a proposed reason. It is never pre-ticked: Mode B stays a person's choice, one unit
  at a time.

The result is one intent commit (several devices' files in one commit, `Source: action/<name>`,
the action and its parameters in the message). Then each device's ordinary preview, confirm,
deploy and Verify follows. A multi-device action names its order: the device whose management
path does not cross the change goes first, as Lab 8's R4 did. Each action's unit tests check:
- intent in, intent out;
- the rendered program's lines;
- a refusal for each precondition.

**Actions work on today's model as well as the new one.** An action writes whatever the current
model's keys are (`no_shutdown: true`, `shutdown` cleared, `no_ip_address` cleared). The knowledge
of the traps lives in the action, so the person never meets them. The model migration (2.5) later
changes only the actions' outputs, and their tests pin that the same decision renders the same
program. This decoupling is the main argument for the order in section 7.

### 4.2 The actions

| Action | Parameters | What it changes |
|---|---|---|
| Add interface | device, name, description, addresses (or "from a NetBox prefix") | one interface entry |
| Enable OSPF on… | device, interface(s), process, area, (cost, passive) | the interface's area, and the process if absent; the ABR note in the preview |
| Enable RIP on… | device, interface(s) | the interface's RIP membership; the process if absent |
| Shut / unshut | device, interface(s), reason | `enabled`, with the expected effects (adjacencies that drop) in the preview |
| Make ZTP relay | device, interface, (Kea) | `relay: kea`; the DHCP subnet named as the next step (the DHCP page's own operation) |
| Connect two devices | A and B, their interfaces, a prefix (a free /30 or /31 from a NetBox container, or typed), protocol and area | both ends' addresses, descriptions ("to B Gi2"), membership; NetBox's prefix and IPs reserved as a NetBox write behind the master switch, recorded |
| Add host VLAN | device (gateway), VLAN id, prefix, relay (Kea), (switch and its access ports) | the gateway's SVI or subinterface, its relay; the switch's VLAN and ports; the DHCP subnet named as the next step |
| Apply to many | an action plus a device selection (role, site, platform, name pattern) | the action run per device; at many devices, a job, each device's own preview (on `bulk_intent`, not a second engine) |

### 4.3 Role profiles (the operator's "R6 = role + a few variables")

A role profile is a function, not a template: `profile(role, variables) → intent`. For example,
`branch-abr`, given a loopback, an uplink interface and prefix, an area and a downstream relay,
produces a full intent.

**The ZTP story:** Add device › ZTP takes a role and its variables, so the device's full intent is
committed at onboarding. Phase two then deploys it through the ordinary preview and Verify, with
no hand-written intent. That is infrastructure as code for a new device.

It depends on the actions (a profile is a composition of them) and on the model (a profile in
today's keys would carry the traps forward). It is the largest piece here, and the most valuable
at fleet scale.

### 4.4 Actions from the Topology map

The map launches an action with its parameters pre-filled:
- drag from one node to another for **Connect two devices**;
- an interface's menu for **Enable OSPF on…** and **Shut**.

The action's own page holds the preview, so the map gains entry points, not a second flow. A new
control needs a board (signed under Phase 7's mode while it lasts).

### 4.5 Natural language for Phase 8

The actions' parameter schemas become the Phase 8 responder's tool schema. The model's job is
then to pick an action and fill its parameters (shape A, strict tools, the existing pydantic
ranges), and deterministic code runs the pure function. The person sees the ordinary preview and
confirms by hash. The AI proposes and never confirms (docs/PHASE8_PLAN.md's rule).

This narrows feature 7 ("natural language → intent", a 70% acceptance target) to a much smaller
and checkable problem. An action's parameter space is a few typed fields, each validated, where
whole-document intent is open-ended. **Recommendation:** re-scope feature 7 onto actions. It is
`propose_intent_change` (docs/IBN_DESIGN.md) with the action as its argument.

### 4.6 The parameters are the contract from day one (the operator, 2026-10-20)

An action's parameters are the vendor-neutral, decision-shaped interface from its first
version: `enabled`, `ospf.area`, `nat: inside|outside`, `relay: kea|<address>`, a prefix, a
peer. They are never today's IOS keys, even while the action's internals still write
`no_shutdown`, `routing.ospf[].networks` and `ip_nat`. Three things then use the same
parameters unchanged:
1. the person, on the action's form;
2. the dialect contract's input, once the model migrates (2.8);
3. Phase 8's tool schema (4.5).

Only the internals move. A test per action pins that one decision renders the same program
before and after the migration. Writing IOS keys into the parameters "for now" would make every
later step a breaking change to the form, the contract and the AI's tools at once.

### 4.7 Two more named actions

- **Remove a static route.** The device's routes are offered to pick from (intent's
  `static_routes` and the capture's, side by side). The action deletes the intent entry and
  names the device line for Mode B, with its reason. The planner's guard decides the box: a
  route to the manager, a default route, or a route to the next hop of one of those is refused,
  naming the address (C1422's guard, 08217992).
  - **Evidence (C1430):** on 2026-10-20 a hand edit of s3's intent deleted the route to the
    manager (`10.255.1.10/32`) instead of the stale route beside it (`10.255.1.16/32`), two
    look-alike lines in `static_routes`. It was put back 3.5 minutes later, and nothing was
    deployed between. Picking from a list that names each route's reach, and the guard refusing
    the manager's, removes that slip.
- **Connect two devices** (4.2), named here as an action of its own: both ends, a free prefix
  from NetBox, the protocol and area, one commit, each end's ordinary preview.

### 4.8 What the overnight run of 2026-10-20 changed here

- **E2 is built:** C1429 (5725b4ff) refuses the contradictory pairs by name, in the editor and
  in bulk intent.
- **E1 is blocked on C1432.** The planner reads a change to a multi-valued command (`ntp
  server`, `ip helper-address`, `ipv6 address`) as a replacement where IOS keeps both, and the
  editor's old one-setting list was right there. E1 waits for the planner's classification to
  be fixed (measured first). It is kept as a patch.
- **V1 is narrower than drawn:** Verify counts neighbour rows, so it does fail a lost parallel
  adjacency (C1427, re-sorted C). What remains is the checks table drawing one row per
  neighbour, and a planned drop of both parallel links failing Verify.

---

## 5. Arguments against (including against the operator's ideas)

1. **Model first, then the editor, is the wrong build order.** The layers are right, but building
   the model first puts an L item (migration across every device, the dual reader, the dialect
   tables) in front of the value. Actions on today's model remove the traps for the person now,
   and their tests then pin the migration. The order: actions and the one-preview fix, then the
   model, then the form on the new model. A form built on today's keys would draw a `shutdown`
   toggle beside a `no_shutdown` toggle, building the trap into the screen, so the form waits for
   the model.
2. **"Derive every network statement" would change s3 and s4.** The model keeps authored ranges
   (2.3). The derivation is the default for a statement equal to one interface's subnet, never a
   rewrite of a range.
3. **Derived lines make removals implicit.** Moving Gi5 from area 10 to area 20 changes a derived
   `network` line. Under merge-only, the old line stays on the device until a person removes it
   by Mode B. The model must not hide that. The preview's "Left on the device" already shows it,
   and an action names it under `implied` with a proposed reason. Making the derivation "clean up
   after itself" automatically would break merge-only, and is refused.
4. **A commit's YAML diff becomes less literal.** A reviewer sees `area: 10`, not the `network`
   line. The mitigation is already the rule: the preview is the exact program, and it is what is
   confirmed. The commit message names the action. This is a real cost, stated here.
5. **"Show only fields that are set" can hide what matters.** An absent field means "not managed",
   and the screen must say what the device is doing there (3.1), or a shut interface looks like a
   working one.
6. **Dropdowns of areas "from NetBox".** NetBox models no OSPF, so the areas come from intent's
   index. VRFs and prefixes can come from NetBox, within the token's reach (C1424: IP ranges and
   VLAN groups are unreadable today).
7. **A fully compact serialisation** (writing only the set keys to YAML) halves the documents, but
   it is a migration commit on every device for readability alone. It belongs with the model's
   migration (one commit, not two), and is not worth doing separately.
8. **"Apply to many devices" as a new feature** duplicates `bulk_intent`. It is an action run per
   device on `bulk_intent`'s compare-and-set, each device with its own preview, as a job at scale.
9. **Natural language straight to intent** (Phase 8 feature 7 as written) is the riskier path;
   4.5 argues for actions as the target.

---

## 6. The items, sized

Size: S under a day, M two to four days, L a week or more (each with its tests, manual page and
board where a screen changes). Risk is what goes wrong if it is built wrong.

| # | Item | Value | Size | Risk | Depends on |
|---|---|---|---|---|---|
| E1 | One preview: the editor runs the planner (C1426) | the editor cannot contradict the confirm | M | low: the planner is already the authority | none |
| E2 | Contradictory pairs refused by name (C1429) | a trap closed today, before the model | S | low | none |
| E3 | Search and jump-to in the YAML view (C1428) | finding a section in a long document | S | low | none |
| V1 | Verify: adjacencies keyed by (protocol, neighbour, interface), judged per row (C1427) | a lost parallel adjacency fails Verify | M | medium: Verify's tolerance and receipts change | none |
| V2 | The receipt names each expected effect's verdict ("Gi5 came up") | the receipt answers what the plan promised | S | low | none |
| A1 | Action framework: the pure-function shape, one commit, `Source: action/…`, the action's page with its parameters and the ordinary preview | the base of every action | M | medium: one more entry into commits (held by the one commit path) | E1 |
| A2 | Enable OSPF on… / Enable RIP on… / Shut-unshut / Add interface | step 4's eight edits become one | S each | low | A1 |
| A3 | Make ZTP relay | relays without hand-typed helpers | S | low | A1 |
| A4 | Connect two devices (both ends; a free prefix from NetBox) | Lab 8's R4–R6 and Lab 9's R2–R8 in one decision | M | medium: two devices, the order, NetBox writes behind the switch | A1, A2 |
| A5 | Add host VLAN (gateway, relay, switch VLAN and ports) | Lab 9's H6 and H7 in one decision | M | medium: the switch's model (switchport fields) | A1, A3 |
| S1 | Semantic checks within a device (ABR without area 0, relay to Kea, next hop connected) | errors caught at authoring | S to M | low | E2 |
| S2 | The fleet index and cross-device checks (link ends, overlaps, MTU and timers) | a link's mismatch caught before the deploy; the topology draws it | M | medium: index freshness (rebuilt on commit) | S1 |
| M1 | The model's fields and the IOS dialect's derivations, behind the dual reader | the traps gone by construction | L | high: every render; held by the byte-for-byte test | E2 |
| M2 | The migration (per network, render-identical, previewed) | every device on the new model | M | high: one commit per network; refused per device on any render diff | M1 |
| M3 | Import on the new model (the reproduces gate for areas, admin state, defaults, relay) | captured devices arrive in the new model | M | medium | M1 |
| F1 | Fields view (board J updated, signed), typed widgets, only-set fields with Add setting | editing without YAML | L | medium: a second view of one document, kept in sync | M1, E1, E3 |
| D1 | The dialect contract over the model (K47's design): the capability map, the defaults tables, refusal by name | multi-vendor on a real seam | M (design) | low as a design | M1 |
| P1 | Role profiles, and ZTP taking role and variables | full intent at onboarding | L | high: a wrong profile across many devices; held by previews per device | A2 to A5, M1 |
| T1 | Actions from the Topology map | discovery: act where the network is drawn | M | low | A4 |
| N1 | Phase 8: the actions as the responder's tool schema | natural language to a validated, previewed change | M (beyond Phase 8's base) | medium; the AI never confirms | A1 to A5, Phase 8 |

---

## 7. The order

**Before Lab 9 (11-04).** Lab 9's own build (0a and 0b, the classic-IOS ZTP, M to L) comes first,
and Lab 8 is due 10-26. That leaves a few working days after Lab 8 at most. Only what is small,
or what the video gains most from:
1. **E2** (S) and **E3** (S): the traps and the scrolling, gone.
2. **E1** (M): the editor stops contradicting the confirm. It is CORE correctness, and it is what
   the video shows when it previews.
3. **A1 with A2's "Enable OSPF on…"** (M, then S): step 4's decision in one action, on today's model.
4. **A4, Connect two devices** (M): Lab 9's R2–R8 link as one decision, if A1 lands by 10-28.
   If not, it moves to Core 1.0 and R8 is authored by hand, as R6 is.

**Core 1.0:**
- **V1** and **V2**;
- **the rest of A2 to A5**;
- **S1**, **S2**;
- **M1 to M3** (the model and its migration);
- **D1** (with K47's Cisco dialects moved onto it after Lab 9, already a Core 1.0 item);
- **F1** (the Fields view, on the new model).

**Later:**
- **P1** (role profiles; Stage 10, with the edge kit's onboarding at scale);
- **T1**;
- **N1** (Phase 8);
- EOS (Stage 10, sized against D1).

---

## 8. What makes Lab 9's video strongest

Lab 9 adds R8 by ZTP through R2's relay (area 20), the switch through R8's relay, and H6 and H7
on VLAN 10.

1. **Connect two devices (A4)** for R2–R8. One decision on screen ("R2 Gi5 to R8, a /30 from
   NetBox, OSPF area 20") becomes both ends' intent and one preview. The preview shows R2 becoming
   an ABR and the adjacency that may form. Verify then reads it. It is the clearest single
   demonstration of intent-based networking in the series.
2. **Enable OSPF on… (A2)**, shown beside the YAML it writes. Because it is on today's model, the
   video can show the eight-line YAML diff the action produced, which is the argument for the
   model made visibly.
3. **A semantic check catching a planted mismatch (S1 or S2)**, for instance area 20 on one end
   and area 0 on the other, refused by name before any device is touched. This is only if S2
   lands, which is unlikely before 11-04. The within-device ABR check (S1) is the fallback.
4. **E1's one preview**, which the video shows every time it previews.

Add host VLAN (A5) would make step 3 one decision too, but it depends on the switch's model,
which 0b is still sizing. It is Core 1.0.
