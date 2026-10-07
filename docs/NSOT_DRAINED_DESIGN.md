# Drained: no customer traffic while reachable (design, for sign-off)

The operator, 2026-10-06, after the class challenge (C550 to C552). Status: **a design for
sign-off, with its mockup; then the measurements in section 9; then the build.** Nothing
here is built. Register: C551 (the measurement), C552 (the interface-counter version,
switched off), C531 (revert as one action, which Return to service will use).

## 1. The definition

A device is **drained** when **no customer traffic crosses it while it is reachable**. Traffic
to or from the device itself (management, routing protocols) and traffic between management
addresses does not count. A device that does not answer is not drained; it is down, and
reachability already says so.

Drained is **measured**. A person never sets it, and configuration alone never makes it so. The
configuration that drains a device (section 4) is the **explanation** of a measurement, shown
beside it, never the measurement.

## 2. Why interface counters failed here

C551's fast version judged every interface but the management path by its unicast packet rate.
On this lab it could not work, measured on the host's Prometheus on 2026-10-06:

- **Management is in band.** s2's loopback is reachable only through r2, so the manager's
  polling of s2 crosses r2's Gi3, a data interface, at about 5.9 unicast pkt/s. At a floor of
  0.5 pkt/s that read as customer traffic, so r2 never read drained.
- **Customer traffic in a lab is about that rate.** At a floor of 10 pkt/s nearly every device
  read drained (C552), and Needs attention held back their alerts.

No floor separates the two, because a packet's rate does not say whose it is. Its **address**
does. In production, out-of-band management keeps data-interface counters clean, but not
clean enough to rely on: routing protocols' unicast, BFD and the device's own traffic still
cross data interfaces. So the design counts by address everywhere, in band or not.

## 3. Three parts

| Part | What it is | Owner | Drawn as |
|---|---|---|---|
| **Intent** | the configuration that drains a device (section 4), in its committed intent and golden | the deploy that put it there | the EXPLANATION beside the state ("max-metric router-lsa since commit abc1234 by `<operator>`") |
| **Measurement** | customer packets crossing the device, counted by address (section 5) | a reader job | the STATE (section 6), the source of truth |
| **Record** | the state's changes over time | the reader, writing transitions | the badge, History, the Needs attention hold-back and its one row, optionally NetBox's status |

## 4. Intent: the drain signatures

Read from the committed golden (never the device). Each is shown as the explanation when present:

| Signature | Form |
|---|---|
| OSPF stub router | `max-metric router-lsa` (all forms: `on-startup`, `external-lsa`, `summary-lsa`, `include-stub`), under `router ospf` and `router ospfv3` |
| RIP / RIPng metric | `offset-list ... out <n> <interface>`; `ipv6 rip <name> default-information originate metric <n>` |
| OSPF cost | `ip ospf cost` / `ipv6 ospf cost` / `ospfv3 cost` raised on data interfaces |
| BGP | `bgp graceful-shutdown all neighbors`; a route-map lowering local preference or prepending the AS path, applied out |
| IS-IS | `set-overload-bit` |
| Interfaces | `shutdown` on data interfaces |

Each line drains only if it was added after the last In service state. A signature that has
always been there is configuration, not a drain. Each needs a measured removal shape (C531 part
1) before Return to service can undo it.

## 5. The measurement, by address

**Customer prefixes come from the source of truth.** In NetBox, each network's customer
prefixes are the prefixes carrying one **prefix role**, IPv4 and IPv6. The role is named by a
setting, `drained_customer_prefix_role`, empty by default. While it is empty, or names a role
with no prefixes, Drained is **Not measured**, and the page says which. A role is a
declaration, not a measurement, because only the network's owner knows which addresses are
customers'.

**The ACL is counting only.** Mercury generates one ACL per address family from those
prefixes, rendered into intent by a template section and deployed through the normal
pipeline: preview, confirm by hash, apply, verify, record.

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

- **It never blocks.** Every entry permits, and the last permits everything. Verify checks that
  the device's running ACL ends in `permit ... any any`, and refuses the deploy otherwise.
- **It is applied inbound on every data interface:** up, not a loopback, not in the
  management VRF (`ip access-group NMAS-CUST-V4 in`, `ipv6 traffic-filter NMAS-CUST-V6 in`).
  Inbound only: every crossing packet enters on one interface, so counting in AND out would
  count it twice.
- **When the prefixes change,** the entries change through Mode B's measured shape
  `named-acl.entry`, which is exact on both platforms. An entry is never rewritten in place.
- **The count** is the sum of the customer entries' hits, never the final `permit any`, as a
  rate over the window. The judgement uses a floor measured during a known drain (section 9),
  expected near zero, because a management packet never matches a customer prefix.

**Reading the hit counts:**

| Platform | How | To measure first |
|---|---|---|
| IOS-XE (C8000v) | model-driven telemetry, periodic dial-out of `Cisco-IOS-XE-acl-oper` (`access-lists/access-list/access-list-entries/access-list-entry/state/match-counter`) to the Telegraf receiver already in Settings, then into Prometheus | whether the C8000v streams the per-entry counters; at what period; whether they count packets the data plane forwards; the series' labels |
| IOS (vIOS) | no model-driven telemetry. Either a reader job running `show ip access-lists NMAS-CUST-V4` (and the IPv6 one) through the read-only allowlist every few minutes, or SNMP if a MIB exposes per-entry hits | whether any MIB on vIOS answers per-entry hit counts; if none, the CLI read's cost per device per minute |

A per-device CLI read is a job, never per request (the scale rule). Its interval is measured,
not chosen.

## 6. The states

Inputs: the drain signatures (section 4), the customer rate against its floor over the window
W, reachability, and how long each has held.

| State | When | Drawn |
|---|---|---|
| **Not measured** | no customer role or prefixes, no ACL on the device, or its counters unread | a muted "Not measured" naming why (absent is not drained) |
| **In service** | customer traffic above the floor | nothing (the normal state draws no badge) |
| **Draining** | a drain signature present, and customer traffic falling but not yet under the floor for W | a warning badge "Draining since HH:MM (n pkt/s)" |
| **Drained** | customer traffic under the floor for W, the device reachable, and a drain signature present | "Drained since HH:MM", the signature as its explanation |
| **Idle** | customer traffic under the floor for W with NO drain signature (a quiet device: night, a new site) | a muted "Idle"; nothing is held back |
| **Drain incomplete** | a drain signature present for longer than T, and customer traffic still above the floor | a danger badge, and ONE Needs attention row: what still crosses it (later, IPFIX names it), and the action |
| **Back in service** | after Drained, the signature removed and customer traffic above the floor again | "Back in service at HH:MM" for an hour, then In service |

W (how long under the floor) and T (how long a drain may take) are measured on the lab's
drains (section 9), not chosen. The floor is in customer pkt/s.

## 7. The record

- **The badge** on the Devices list (in the name cell, the state word, the words on hover) and
  in the device page header (the state and its words), re-read when the reader announces.
- **History:** each state change is one entry from the reader ("Drained", "Back in service",
  "Drain incomplete"), with the rate, the window and the signature present, and a filter
  group "Drains".
- **The hold-back is narrowed.** C550 to C552 held back EVERY Grafana alert on a drained
  device, which would hide "Interface output discards" and "Device unreachable". The new
  hold-back covers only alerts about traffic falling: rules labelled `nmas_traffic="1"`,
  declared on the rule, never guessed from its name. Every other alert is raised as usual.
  While a device is Draining or Drained, a held-back alert is listed under What was checked,
  naming the state.
- **Needs attention has ONE drain row:** Drain incomplete. It says what is wrong (the drain's
  signature has been present for T, and customer traffic continues at n pkt/s) and the action
  (read what still crosses it, or complete the drain). It clears when the state leaves Drain
  incomplete.
- **NetBox's device status is optional and off by default.** When the network's NetBox writes
  are on and an authority is declared, Drained may set the status to `offline` and Back in
  service set back the status it recorded as before. This goes through the three write
  chokepoints, with the before recorded (the NetBox rules).

## 8. Later

- **Flow export (IPFIX)** for "what is still on it": the prefixes and ports of the customer
  traffic still crossing a device that is Draining or Drain incomplete, drawn under that state.
- **The Drain and Return to service operation:** plans the drain signatures across the devices
  named (a change set, C531 part 3), previews them as one program, applies them, then WAITS for
  the measurement to read Drained on every device, naming each one still Draining. Return to
  service is the change set's revert (C531 part 2), confirmed when the measurement reads Back in
  service. It needs C531 part 1's measured shapes for every signature in section 4.
- **The interface-counter version retires** (C552, switched off) once this measurement is on.

## 9. To measure first (the operator's runs; the agent's read-only reads)

1. **C8000v telemetry:** does `Cisco-IOS-XE-acl-oper` stream per-entry `match-counter` on a
   periodic subscription, at what minimum period, and do the counters count packets the data
   plane forwards? Run on r2: a test ACL with a permit entry for a host prefix, applied inbound
   on Gi3; known traffic across it; compare `show ip access-lists` with the streamed value.
2. **vIOS:** do any of its MIBs answer per-entry ACL hits (an `snmpwalk` of the candidate
   tables)? If none, how long does `show ip access-lists <name>` take on s1 (never s3)?
3. **The ACL's cost:** forwarding before and after applying a 50-entry ACL inbound on one
   interface of each platform (the ping round-trip and the interface rate under the same load).
4. **The floor, W and T:** customer pkt/s on r2 during a known drain and after it, from the
   counters measured in step 1.

## 10. Screens (drawn in the mockup for sign-off)

The Devices list (the state in the name cell and a "Drains" filter); the device page header
(the state badge); the device Overview's **Service** panel (state, rate now, the window, the
signature as explanation, the measurement's age, and "How is this measured?"); Needs attention's
Drain incomplete row, and a held-back alert under What was checked; History's drain entries;
Settings > NetBox: the customer prefix role, with the count of prefixes it finds.

## 11. Questions for the operator

1. The prefix role's name: one setting per network, or one for the installation?
2. Inbound-only counting on data interfaces: agreed?
3. The hold-back narrowed to rules labelled `nmas_traffic="1"`: agreed, with those labels added
   to the traffic rules by the monitoring templates?
4. NetBox's `offline` for Drained: wanted at all, or left out?
