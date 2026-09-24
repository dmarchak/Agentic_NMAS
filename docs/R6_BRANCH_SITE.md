# r6, the branch site — the first configuration this tool AUTHORS

**Plan. Nothing built.** Post-and-agree before any step runs.

---

## What this proves, and what the probe and phase 1 did not

The Stage 4C probe and r6's phase 1 proved the tool can **onboard** a device:
reach it, rotate its credential, record it in the manifest, NetBox and the
CSV, and capture what it holds. Real work, and all of it *observational* —
**every golden in this repository was extracted from a device somebody
configured by hand.** The repo has been a recorder.

This proves the tool can **configure** one:

> a configuration that exists **first** as committed intent in git, is
> rendered by an approved template, previewed as an exact command list,
> confirmed, sent merge-only, verified by protocol convergence, and captured
> back — with the device's running state matching what the repository said
> **before the device had ever held it**.

That is the claim the intent editor, `build_artifact()`, the confirm hash and
the deploy contract were all built for, and **it has never been exercised end
to end.** Phase 3c's machinery has only ever been pointed at devices whose
intent was seeded from their own capture, which makes the diff empty by
construction — the failure that rule exists to prevent, never yet avoided in
anger because no change has been authored.

**The acceptance that makes it unambiguous is a device the tool did not
touch**: r1 learning `10.255.1.16` in its routing table. Nobody edited r1.

### What it will not prove

* One device, one platform, **additive only** — merge-only cannot remove, and
  Mode B removals are still unbuilt.
* It does not test the tool against a wrong value at the source. *IaC
  guarantees you did what you said; it cannot know that what you said was
  wrong.*

---

## 0. What was measured for this plan, and what could not be

Measured locally, in this checkout:

| fact | how |
|---|---|
| the IOS-XE template renders a hand-authored branch intent, **0 unmodeled constructs, 0 unsendable bytes**, 98 lines | authored `host_vars` in the parser's own shape, rendered through the unmodified `cisco_iosxe/base.j2` |
| VLAN 100 is the CORE segment, `10.255.3.0/24`, OSPF area 0, on s3 and s4 with r1–r4 as access ports | `tests/fixtures/configs/fleet/{s3,s4}.cfg` |
| **s4 `GigabitEthernet0/1` is free** — no description, no switchport config, no address | `s4.cfg` |
| **s3 `Vlan99` is `10.255.0.1/24` and is `passive-interface` inside `network 10.255.0.0 0.0.255.255 area 0`** | `s3.cfg` — the finding that adds option C |
| r5 is the eBGP edge (AS 65002 → 65001 on r3/r4) with Gi1–Gi4 and **no spare NIC** | `r5.cfg` |
| `write_committed()` refuses a resolved secret and any non-ASCII byte | `modules/nsot/hostvars.py` |

**Not measurable from here, and the plan says so rather than guessing.** This
machine pings `10.0.0.211` but port 5000 times out (the firewall is closed,
by design), `ssh dmarchak@10.0.0.210` is refused for want of a key, and this
checkout's `data/lists/default/devices.csv` holds **one line — the header**.
So every fact about the *live* lab in this document comes from the sanitized
fleet fixtures or from `R6_PHASE1.md`, and **each step below that depends on
a live fact names the command that establishes it.** The fixtures preserve
the `10.255.x` plan and rewrite the core link addressing, so VLAN/port/area
facts carry over and per-link host addresses do not.

---

## 1. Where r6 attaches

r6 is on `br-mgmt` with no data plane. Three options, and **the cheapest one
only became visible by reading s3's config.**

### The thing common to A and B: a link between two labs does not exist

r6 lives in its own `r6.clab.yml`; the fleet lives in `rcn-lab1.clab.yml`. A
containerlab link is declared inside one topology and **cannot span two**. So
any real data link is either "move r6 into rcn-lab1" (A) or "meet on a Linux
bridge neither lab owns" (B) — the `br-mgmt` pattern, already proven by
`nmas-onboard-c.clab.yml` and documented in `R6_PHASE1.md` §0c.

Both edit `rcn-lab1.clab.yml`, and **both therefore cost a destroy/deploy of
all nine nodes** with the whole of Stage 2.4's checklist. Containerlab cannot
add a NIC to a running vrnetlab node. A hand-made veth would work *today* and
vanish at the next redeploy — coverage inherited, not designed, which is the
exact shape this project keeps removing. Not offered.

### A. Move r6 into `rcn-lab1.clab.yml`

Most realistic, **most expensive, and not just for the redeploy**: r6 changes
labs, which invalidates its `manifest.clab_lab` entry, its own git repo at
`~/labs/r6`, its startup-file path and its launch-patch path. That is a
migration of the device → lab map, not an edit of it — against the map that
was built three days ago precisely so a device's four `clab_*` values move
together. **Not recommended.**

### B. A shared bridge, s4 `Gi0/1` → VLAN 100

Declare a `kind: bridge` node (`br-core`) in **both** topologies. s4's free
`Gi0/1` becomes an access port in VLAN 100; r6 gains a NIC onto the same
bridge and an address in `10.255.3.0/24`. r6 lands directly in the existing
area-0 broadcast domain with r1–r4, s3 and s4.

r6 keeps its lab, its map entry, its repo and its startup file.

### The comparison you asked for: s4's free port is cheaper than a fifth NIC on r5

Both need the same `rcn-lab1` edit and the same redeploy, so **the redeploy
cost is identical and the difference is entirely in intent**:

| | s4 free port | eBGP to r5 |
|---|---|---|
| does the port exist today | **yes** — `Gi0/1`, measured unused | **no** — r5 runs Gi1–Gi4; Gi5 must be added |
| second device's intent change | 3 lines on s4 (`switchport mode access`, `switchport access vlan 100`, description) | a new interface **and** a new BGP neighbour on the eBGP edge |
| addressing | none new — VLAN 100 / `10.255.3.0/24` already exists | a new link subnet **and** an AS number for r6 |
| blast radius if wrong | an access port in an existing VLAN | the fleet's only external BGP edge |

**s4 is cheaper on every axis**, and it is the option where the second
device's change is small enough to be reviewed at a glance — which matters,
because that change is also authored by this tool.

### C. OSPF over the segment that already exists — no topology change at all

**r6 is already L2-adjacent to s3.** `br-mgmt` carries `10.255.0.0/24`, s3's
`Vlan99` is `10.255.0.1` on it, and s3's `router ospf 1` already contains
`network 10.255.0.0 0.0.255.255 area 0` — so the prefix is **already
advertised into area 0**. The only thing stopping an adjacency is one line:

```
 passive-interface Vlan99
```

Remove it from s3's intent, give r6 `Loopback0 10.255.1.16/32` and OSPF on
its existing `Gi2`, and r6 is a routed member of area 0. **No topology file
edit, no redeploy, no new NIC, no bridge**, and the proof runs on **two**
devices' authored intent instead of one.

**And it is not a branch site.** Say it plainly: this makes the management
LAN a routed transit segment. r6's "uplink" would be the network the manager
sits on. As topology it is wrong; as a proof of the authoring path it is
complete, cheap and reversible in one line.

One risk to state rather than discover: **s3's `Vlan99` is the NMAS's own
default gateway to the fleet.** Removing `passive-interface` does not touch
the address and does not change reachability — it adds hellos on a segment
that already carries the traffic — but it is a change to the path every other
change travels over, and it should be deployed **alone**, with r6 already
done, never bundled.

### C, priced — and it does not survive the pricing

Three questions were put to option C before step 1. The answers are below,
and the third one ends it.

#### What r6 advertises, and whether s3 could prefer a path through it

Two things, and only two: its `Loopback0` as a stub host route
`10.255.1.16/32`, and its connected `10.255.0.0/24` — **which s3 already
advertises**, because `passive-interface` suppresses hellos and not the
prefix.

**s3 cannot prefer a path through r6 to anything, and that is structural
rather than a matter of cost.** For SPF to route through r6, r6 would need a
second link to somewhere. It has one: `Gi1` is in the `clab-mgmt` VRF and
therefore not in the global OSPF process at all, and `Loopback0` is passive.
A router with one link in the domain is a leaf of the shortest-path tree, and
no cost, tuning or metric can make a leaf a transit path.

So the specific fear — *the NMAS's route to the fleet goes through the device
the tool just configured* — **does not arise.** The NMAS is not an OSPF
speaker; it reaches the fleet through its gateway `10.255.0.1`, which is
s3's own SVI, and s3 reaches r1–r5 over `Vlan100` exactly as it does today.

#### The blast radius of a bad r6 deploy

**Bounded to r6, even under C.** r6 has no protocol relationship that can
propagate a mistake: no redistribution, no default origination, no second
area, no summarisation, and one interface. The worst credible outcomes are an
adjacency that fails to form (MTU or timers) and a `10.255.1.16/32` that
nobody learns. Neither touches the management plane.

**The dangerous half was never r6. It is the change to s3** — one line, on
the device that is the manager's only gateway to every other device.

#### Is there an adjacency without transit? Yes and no, and neither matters

* **In the link-state database**, no: two adjacent routers reclassify the
  segment from a stub network to a transit network in the Router-LSA. That is
  inherent to the adjacency and no cost or filter avoids it.
* **In forwarding**, it was never possible, per the first answer.

So the distinction the question reaches for is real but inert here: the LSDB
changes shape and no packet changes path. `ip ospf priority 0` on r6's `Gi2`
is worth having anyway — it keeps r6 out of the DR election, and it is the
fleet's existing idiom (`s3`/`s4` both carry it on `Vlan100`) — but it is
hardening, not the answer.

#### The answer that ends option C: **this tool cannot make s3's change**

`passive-interface Vlan99` has to be **removed**, and the deploy path is
merge-only. `assert_merge_only()` requires every pushed command to appear
verbatim in the intended config; a line the render omits and the device holds
is a **removal warning**, never a negation. Mode B removals are not built.

So C's s3 half reaches step 5, produces a removal warning, and sends nothing.
**The option chosen to prove that the tool can author configuration contains
a change the tool cannot author.**

The obvious escape does not work either. Authoring `no passive-interface
Vlan99` into s3's OSPF settings *would* pass `assert_merge_only` — it is in
the intended config, and the guard checks provenance rather than grepping for
`no`, correctly. But `passive-interface` is a non-default setting: negating it
returns the device to default, and the running config then shows **neither**
line. The intent would permanently name a line the device can never echo, so
every future plan re-proposes it and the device is permanently drifted. That
trades a one-off refusal for a standing lie in the repository.

**C is out on capability grounds, not on risk grounds** — which is a better
outcome than the risk trade, because it would otherwise have been discovered
at the preview with the change half-made.

### C′ — the option the fleet already uses, and s3 proves it

Reading s3's `static_routes` turned up this, which changes the recommendation:

```
ip route 10.255.1.10 255.255.255.255 10.255.0.10
```

s3 **already** carries a static /32 pointing at an address on `Vlan99` — the
NMAS's own `dummy0` identity — and `redistribute static subnets` is already in
its OSPF process. **The fleet's existing answer to "how does something on the
management segment get a routed /32 into area 0" is a static route plus
redistribution, not an adjacency**, and it is in production and working.

So:

| device | change | properties |
|---|---|---|
| **s3** | `+ ip route 10.255.1.16 255.255.255.255 10.255.0.32` | **one added line**, `static_routes` is a modelled host_vars field, merge-only compatible, round-trips cleanly, identical in form to a line s3 already has |
| **r6** | `Loopback0 10.255.1.16/32`, `+ ip route 10.255.0.0 255.255.0.0 10.255.0.1` | no OSPF process at all |

What that buys, against every objection raised:

* **`Vlan99` stays a stub network.** No adjacency, no DR election, no LSDB
  reshaping, no hellos on the wire the manager depends on.
* **Nothing is removed**, so the tool can author the whole of it.
* **Blast radius of the s3 change is one /32.** If it is wrong,
  `10.255.1.16` is unreachable and nothing else moves — against C, where the
  change alters how a routing protocol behaves on the management segment.
* **Step 7's acceptance survives intact**: r1 learns `10.255.1.16`, nobody
  touched r1. It arrives as an OSPF **external** (E2) rather than an
  intra-area route, which is if anything a sharper test — it proves the
  redistribution path end to end.
* A `/16` static on r6 rather than a default route, because r6 is not a
  default gateway for anything and a `0.0.0.0/0` would claim it is.

**It proves exactly the same thing about the tool.** Both devices' changes are
authored by hand, committed to git, rendered by an approved template,
previewed as an exact command list, confirmed, sent and verified. Only the
*networking* is simpler, and the simplification is in the direction of not
performing a first-ever exercise on the one wire that must survive it.

### Recommendation

**C′ now, B when a redeploy is next scheduled anyway. C is withdrawn.**

C was chosen as the cheap proof and priced out: its s3 half is a *removal*,
and the deploy path is merge-only, so the tool cannot author it. C′ replaces
it with the mechanism s3 already uses for this exact problem — a static /32
redistributed into area 0 — which is additive, modelled, and leaves the
management segment a stub network with no adjacency on it.

B remains the right **topology** and should ride along with the next
`rcn-lab1` redeploy rather than causing one: an outage of nine devices to give
the tenth a more honest-looking link is a poor trade while the claim under
test is about the software.

If the answer is *"the branch site has to be a real branch site now"*, it is
**B**, and §3's order changes as marked.

---

## 2. What the intent says

### The template needs nothing it does not already have — measured, not assumed

A hand-authored `host_vars` for r6, rendered through the **unmodified**
`modules/nsot/templates/cisco_iosxe/base.j2`:

```
service timestamps debug datetime msec
service timestamps log datetime msec show-timezone
hostname r6
ip domain name example.com
...
interface Loopback0
 description branch identity
 ip address 10.255.1.16 255.255.255.255
interface GigabitEthernet2
 description branch uplink - OSPF area 0
 ip address 10.255.0.32 255.255.255.0
 negotiation auto
router ospf 1
 router-id 10.255.1.16
 passive-interface Loopback0
 network 10.255.0.0 0.0.255.255 area 0
...
end
```

**98 lines, `unmodeled_lines()` → 0, `_unsendable_lines()` → 0.** So
`build_artifact()` yields `deployable: True`, and the answer to *"what does
the template need that it doesn't already have"* is **nothing**.

Why that is unsurprising once measured: the `interface` macro already takes
`ipv4`, `description`, `negotiation` and a list of `ip ospf …` lines, and
`routing.ospf` is `[{process, settings, networks}]` whose settings and
networks are raw lines. **A branch router is the same construct set as
r1–r4**, which is what the template round-trips. The template being built
from extractions does not make it an extraction-only template.

Corroboration from the repo's own record rather than from me: `R6_PHASE1.md`
states `cisco_iosxe/base.j2` is **approved against six devices**, and
approval requires a clean round-trip against **every** bound device — so
r6's capture already round-trips. Seeding intent from it will produce a
deployable artifact before a single edit.

### What the intent actually contains

| | value | note |
|---|---|---|
| `Loopback0` | `10.255.1.16 255.255.255.255` | the address `R6_PHASE1.md` §0d reserved for exactly this |
| uplink (**C′**) | the existing `Gi2`, `10.255.0.32/24`, **no OSPF** | no new interface, no adjacency |
| uplink (**B**) | new NIC, `10.255.3.26 255.255.255.0` in VLAN 100 | replaces the line above |
| routing (**C′**) | none on r6; `ip route 10.255.0.0 255.255.0.0 10.255.0.1` | r6 speaks no routing protocol |
| routing (**B**) | `router ospf 1`, `router-id 10.255.1.16`, `passive-interface Loopback0`, `network 10.255.0.0 0.0.255.255 area 0` | the same one-line network statement every other device uses |
| s3 (**C′** only) | `+ ip route 10.255.1.16 255.255.255.255 10.255.0.32` | one **added** line, deployed separately |
| s4 (**B** only) | `Gi0/1`: description, `switchport mode access`, `switchport access vlan 100` | three lines |

Deliberately **not** in it: no static routes, no NAT, no ACLs, no second
protocol. The branch site demonstrates that a config can be authored — every
construct added beyond that is a construct whose failure has to be diagnosed
during the first run of a path that has never run.

### Three authoring constraints, measured at the commit path

1. **`write_committed()` refuses a resolved secret**, structurally and by
   value, and `assert_no_secret_values()` scans *every* list's secrets. The
   file carries `enable_secret_ref`, `users[].secret_ref` and
   `snmp.communities[].ref` — names only.
2. **`secret_kind: hash` for r6's `secret 9`.** A `$9$` hash carries a
   per-hash salt and cannot be regenerated. r6's came from the device during
   phase 2's rotation; the intent must **reference the stored hash**, or the
   render emits a different secret and the deploy changes the credential NMAS
   holds — a lockout dressed as a branch site.

   **This now has a control, and it runs before the preview is shown.**
   `deploy.assert_credentials_unchanged()` compares every credential-bearing
   line in the truthful render against the same line in the capture, **byte
   for byte**, keyed on the account. A deploy may *add* an account and may
   never *change* one — deliberate credential change has its own path, which
   rotates and records atomically, so nothing legitimate changes a credential
   through a deploy and this refuses rather than warns.

   It lives in `prepare_device()`, **after** `assert_no_mask()` (the masked
   render differs from the capture by construction and would refuse
   everything) and **before** anything connects. The capture's credential
   lines are carried **on the artifact**, not passed as an argument, because
   an optional argument is how a caller bypasses a guard by omission — twice
   measured in this project. And the refusal **names the form and never the
   value**: `secret 9 <value>`, because a guard against a credential must not
   become a second place the credential lives.

   `tests/test_credential_never_changes_on_deploy.py`, 18 tests, four
   negative controls.
3. **ASCII only**, `assert_printable()` at commit and `assert_sendable()`
   before the socket. No em dash in a description. This has bitten twice.

---

## 3. The order — C′, as agreed

### One plan or two, and which way round

**Two plans, two confirms, r6 first.** The instinct is right and the reason is
sharper than the one it was offered with.

*"r6's loopback must exist before s3 points a static at it"* is not
mechanically true: `ip route 10.255.1.16 255.255.255.255 10.255.0.32` installs
as soon as its **next hop** resolves, and `10.255.0.32` is on s3's connected
`Vlan99` and live today. The destination need not exist.

The real reason is worse than a prerequisite. **s3-first makes step 7's
acceptance pass vacuously**: s3 installs the static, redistributes it, and r1
learns `10.255.1.16` as an E2 — pointing at an address nothing answers. The
criterion *"r1 learns 10.255.1.16, nobody touched r1"* would be **satisfied by
a route to nowhere**, with traffic reaching r6 and being dropped. So r6-first
is not a convenience; it is what stops the acceptance being a wrong thing that
looks like a working thing.

**Two plans rather than one batch**, for three reasons:

1. **The confirm hash covers the whole program.** One plan means r6's half
   changing between plan and apply refuses s3's confirmed line too — coupling
   two independent changes so that either one's failure is the other's.
2. **s3 is the manager's only gateway.** Its one line deserves its own
   confirm, read on its own, not under a summary that also covers r6.
3. **The intent commits must match the deploy boundary.**
   `.nsot/rolled_back.json` keys on the device's *current intent commit*, and
   "Revert intent" applies the inverse of **that commit's own diff**. A shared
   commit would mean reverting r6's rollback also reverts s3's change.

So the boundary is the same all the way down: **one device → one intent commit
→ one plan → one confirm → one deploy → one golden commit.**

**Predicted, so it is not read as a failure:** neither deploy earns a
`baseline/` tag. Coverage governs, and a batch targeting one device out of ten
is denied the tag with the other nine named. That is correct behaviour.

---

### 0. Before anything is changed

| # | step | why |
|---|---|---|
| 0a | **`cisco_ios/base.j2` is approved.** C′ puts s3 on the deploy path, and approval is per platform: `routes/deploy.py` computes it per template and `deployable` requires it. | If it is not approved, approving it needs a clean round-trip against **every bound device** (s1–s4) and **refuses naming any that lack a capture** — a refusal that is load-bearing, not an obstacle to route around |
| 0b | **`10.255.1.16` is free, three ways** — NetBox holds nothing on it, nothing answers a ping, and no golden in the repo mentions it (`grep -rl 10.255.1.16 config_repo/golden/`). | the convention `R6_PHASE1.md` §0d used for `.32`, and `.31` before it |
| 0c | **Prove the mechanism works TODAY.** On r1: `show ip route 10.255.1.10` must show `O E2 … [110/20]`. | s3 already redistributes that /32 by exactly this route. **If it is absent, C′'s premise is wrong and nothing should be deployed.** It also gives step 7 a known-good comparator rather than a bare expectation |
| 0d | **Freshness + Save All.** `oxidized-to-config.sh --no-deploy`, require **10 of 10 approved**, then Save All. | the pre-change comparison point, and the gate says the fleet is at its approved state before anything moves |

### 1–5. r6: author, preview, deploy

| # | step | check |
|---|---|---|
| 1 | **Seed r6's intent** — `POST /templatize/extract/r6`, review, `POST /templatize/commit/r6` (`host_vars: r6 seed from capture`). | r6 has **no committed intent**: it is `bootstrap` and not deployable by design |
| 2 | **Control: the preview is empty.** `POST /templatize/committed/r6/preview`. | if the seed is not faithful, every later diff is measuring the seed rather than the change |
| 3 | **Author r6's branch intent** and commit (`host_vars: r6 branch site`). **Exactly two things and no OSPF** — see the YAML below. | a `/16` rather than a default route: r6 is not a default gateway for anything and `0.0.0.0/0` would claim it is |

**r6's intent is two additions. There is no `router ospf` on r6 at all** —
every bit of the reachability comes from s3's static plus its existing
`redistribute static subnets`.

**A hand-written interface dict will not render.** `roundtrip.render()` uses
`StrictUndefined` and the interface macro reads about thirty keys; a parser
always emits all of them, so a minimal `{name, description, ipv4}` fails with
`'dict object' has no attribute 'no_switchport'`. Measured. Paste this
complete block rather than writing one:

```yaml
interfaces:
- name: Loopback0
  description: branch site identity
  ipv4: 10.255.1.16 255.255.255.255
  channel_group: ''
  dhcpv6_relay: []
  encapsulation: ''
  helper_addresses: []
  ip_nat: []
  ipv6: []
  ipv6_enable: false
  ipv6_nd: []
  mop: []
  mtu: ''
  negotiation: ''
  no_ip_address: false
  no_shutdown: false
  no_switchport: false
  ospf: []
  ospfv3: []
  ripng: []
  shutdown: false
  switchport: []
  switchport_access_vlan: ''
  switchport_mode: ''
  switchport_trunk_encapsulation: ''
  switchport_trunk_vlans: []
  unmodeled: []
  vrf: ''
  vrrp: []
  vrrp_groups: []
# ... the existing GigabitEthernet1 and GigabitEthernet2 entries stay as they are

static_routes:
- family: ipv4
  spec: 10.255.0.0 255.255.0.0 10.255.0.1
```

Verified locally against the unmodified template: **122 lines, 0 unmodeled,
0 unsendable, and `router ospf` absent from the render.**
| 4 | **Preview.** `from_this_edit` must be **exactly** the loopback stanza and the one static; `pre_existing` empty. | the first time this split has had non-trivial content |
| 5 | **Deploy r6** — `POST /deploy/plan`, read the exact program, confirm, `POST /deploy/apply`. | expect **no dangerous lines** and **no credential lines at all**; `assert_credentials_unchanged()` runs before the preview is shown |

### 6. r6's own acceptance, before s3 is touched

- [ ] `10.255.1.16` answers from r6 itself
- [ ] r1 does **not** yet have a route to it — *nothing has advertised it, and this is the state step 8's check must move*
- [ ] `nmas-check-credential r6 --expect accepted` — the credential is unchanged, which is what the new guard exists to make true

### 7. s3: one added line, deployed alone

| # | step | check |
|---|---|---|
| 7a | **Seed s3's intent if it has none**, then the empty-preview control, as steps 1–2. | s3 may already be `bootstrap` like r6 |
| 7b | **Author the one line** and commit (`host_vars: s3 route to r6 loopback`): `static_routes` gains `{family: ipv4, spec: "10.255.1.16 255.255.255.255 10.255.0.32"}`. | the same shape as the `10.255.1.10` route s3 already carries |
| 7c | **Preview.** `from_this_edit` must be **one line**. | anything else on the manager's gateway is a stop |
| 7d | **Deploy s3 alone.** | its own confirm, read on its own |

### 8. The acceptance — and it is stronger than "a route appears"

- [ ] **r1 learns `10.255.1.16` as `O E2 … [110/20]`** — the **same form** in which it already shows `10.255.1.10`, verified at step 0c. Nobody edited r1.

  This proves three things at once, which is why the E2 framing is kept
  rather than just the route appearing:

  1. **reachability without an adjacency** — `Vlan99` is still a stub network,
     no hellos, no DR election;
  2. **the redistribution path end to end** — a static on s3 becoming an
     external LSA that a device two hops away installs;
  3. **that the tool authored both halves** — neither the route nor the
     loopback existed anywhere before it was written into git.

- [ ] `10.255.1.16` answers from **r1**, not only from r6
- [ ] `Vlan99` shows **no OSPF neighbour** — the property C′ was chosen for, asserted rather than assumed
- [ ] s3's other routes unchanged; the NMAS still reaches every device

### 9. Persistence and capture

- [ ] Stage 8.5 saved a golden for each device — **two commits, two events**
- [ ] Neither earned a `baseline/` tag, with the other nine named (predicted above)
- [ ] Run the sync. **Expect a `poll_race` on r6 and s3** — their goldens are newer than Oxidized's copies until it polls — which does **not** block, by design. **If it blocks, that is a finding.** Re-run after the next poll and require `match`
- [ ] `nmas-check-startup-applies r6` → **SAFE**; the branch config is only durable once it is in the startup file

### Option B only — the redeploy, and the checklist that applies

B's topology edit comes **first**, because IOS will not accept an interface
stanza for a NIC that does not exist. So: edit both topology files → redeploy
→ then the steps above, with r6's uplink becoming `10.255.3.26/24` in VLAN 100
and OSPF replacing the statics.

From Stage 2.4's **Before** list, still applicable:

- [ ] `config_repo` clean and pushed — `git status` clean, local HEAD == remote main
- [ ] A **Save All** run now, so the pre-redeploy goldens are the comparison point
- [ ] `~/labs/lab/configs/r1–r5.cfg` still carry `secret 9` (`grep -c 'secret 9'` → 5)
- [ ] You are at the machine and have time to finish

**Already satisfied and not re-run**: 2.1 (patch adopted), 2.2a, 2.2b (the
break-glass record, re-exported for **ten** and verified `complete: True`),
2.3, 2.3b. The ban was lifted on 2026-09-22 by a successful redeploy.

**One new item, and it did not exist when that checklist was written:**

- [ ] **The freshness gate reports 10 of 10 approved before the destroy.**
      The nodes boot what the sanitiser wrote, and as of `ac40401` that is
      gate-checked. Skipping it means booting configs nobody compared — the
      hazard the gate was built for, met at the one moment it is irreversible.

From the **After** list, every item applies unchanged (nine nodes reach
`Startup complete`; no `%CVAC-4-CLI_FAILURE`; the skip fired; `secret 9` on
all five; `nmas-check-credential` for all nine plus `admin`/`admin` **refused**
on the routers, where **`INCONCLUSIVE` is not a pass**; Oxidized fetches all
nine; Save All shows no unexpected diff; drift; the Remote card).

**Plus three r6-specific items:**

- [ ] `--cleanup` on rcn-lab1 **did not disturb `br-mgmt`, `br-core` or r6**
- [ ] r6's own lab redeployed for its new NIC — **the first test of r6's
      startup file**, which has never booted
- [ ] `nmas-check-startup-applies r6` → **SAFE** afterwards, and the
      credential NMAS holds still accepted

### If any step fails

Stop and measure. The rollback path exists and is computed rather than
replayed, but **it has never run on a change this tool authored**, so a
failure here is also the first exercise of that. Do not re-deploy to "try it
clean" — a second attempt destroys the evidence of why the first failed.
