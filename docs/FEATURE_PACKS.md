# Feature packs

K7, register C764. The first packs are the routing ones Labs 8 and 9 need: OSPFv2 (areas, an
ABR's summary ranges), OSPFv3, RIPv2, RIPng and redistribution between them. Code and tests
only: nothing here has been deployed to a device. Tests: `tests/test_feature_packs_routing.py`.

## The design

1. **A pack is a schema, a partial, a parse and a round trip.** The schema is a feature's
   structured fields, vendor-neutral (OSPF's concepts, not IOS's words), with their empty values
   and the checks each value must pass (`modules/nsot/features/`). The partial is the Jinja
   macros that write the fields in a dialect's words. The parse fills the fields from a running
   configuration. The round trip of every captured configuration is the judge.
2. **The fields live where intent already held the feature:** `routing.ospf[]`, `routing.rip`,
   `routing.ospfv3[]`, `routing.ripng[]`, and three interface fields (`ospf_interface`,
   `ospfv3_interface`, `ripng_interface`).
3. **Intent from before the packs is unchanged.** The lines no pack models stay in the keys
   intent always had (`settings` and `networks`; `raw`; an interface's `ospf`, `ospfv3` and
   `ripng` lists), rendered after the pack's lines. An intent holding only those renders byte
   for byte as it did (the host's committed r2 and s1, against the templates of 5666edb5).
4. **The parser now emits the structured shape.** A routing line becomes a field only when the
   dialect's partial renders that field back as exactly that line (`features.reproduces`);
   every other line stays verbatim, in order, where it was. So every capture still round-trips
   and its parse is a fixed point.
5. **The partial is selected through the dialect.** The macros are a section of
   `templates/_common.j2`, which each `<platform>/base.j2` imports; the loader looks in the
   dialect's directory first, as it does for every template. Both Cisco dialects print these
   lines alike in every capture, so one copy serves both, and a dialect that differs overrides
   it there.
6. **One file, not two.** The partial is inside `_common.j2` rather than a file of its own so a
   network's library takes it in the one file "Bring in the shipped version" already brings
   (C566); a second file would have to be seeded before the first could render.
7. **A library from before the packs still renders them.** A network's `_common.j2` seeded
   before the packs reads none of their fields. The render measures that from the library's own
   templates (`features.library_reads_packs`: no template in the closure names a pack's
   fields) and then hands the fields over as the lines the SHIPPED partial writes for them
   (`features.for_library`), which such a library emits verbatim. A capture's structured parse
   round-trips through it, and authored structured intent renders the same lines.
8. **Readers see one shape.** The adjacency readers (Neighbours, the Topology map's routing
   layers, the RIP reader) judge from intent's lines; a pack's fields are read as the lines they
   render (`features.raw_view`), once per call over a fleet.
9. **A refused field stops the render and the editor**, naming the field, its value and what it
   was compared with (`features.problems`, run by `intent_edit.validate` and by the render).
   A capture's parse never carries one: a line whose field would be refused stays a line, and
   a field refused only beside another (an interface naming a process routing does not hold)
   goes back to its lines (`features.settle`).
10. **Order.** Each block's lines are written in the order IOS and IOS-XE print them where a
    capture shows it (OSPFv3's default route before its redistribution, RIP's
    `no auto-summary` last); an unmodelled line follows the modelled ones. The round trip
    compares a routing block as a set (IOS orders it), so order is a fidelity, not a gate.

## The fields

An absent field is its empty value, and renders nothing. Numbers may be written as numbers;
the render writes them as given.

### OSPFv2: `routing.ospf[]` (`router ospf <process>`)

| Field | Line | Notes |
|---|---|---|
| `process` | the header | 1 to 65535 |
| `router_id` | `router-id A.B.C.D` | an IPv4 address |
| `log_adjacency_changes` | `log-adjacency-changes [detail]`, `no log-adjacency-changes` | true, `detail`, false, or absent |
| `reference_bandwidth` | `auto-cost reference-bandwidth N` | Mbit/s |
| `areas[]` | see below | one entry per area; `10` and `0.0.0.10` are one area, refused twice |
| `redistribute[]` | `redistribute <protocol> [<process>] [metric N] [metric-type 1\|2] [subnets] [tag N] [route-map R]` | `protocol`: connected, static, rip, bgp, ospf, eigrp; `process` for bgp, ospf, eigrp |
| `passive_default`, `no_passive_interfaces`, `passive_interfaces` | `passive-interface default`, `no passive-interface X`, `passive-interface X` | the active list only with the default, the passive list only without it |
| `default_information` | `default-information originate [always] [metric N] [metric-type N] [route-map R]` | `originate`, `always`, `metric`, `metric_type`, `route_map` |
| `distance` | `distance N` | 1 to 255 |

An area (`areas[]`): `id`; `type` (`normal`, `stub` or `nssa`) and `no_summary`
(`area X stub no-summary`; refused on a normal area and on area 0); `default_cost`
(`area X default-cost N`); `networks[]` (`network A W area X`: `address` and `wildcard`, or an
authored `prefix` such as `192.0.2.0/26`, written out as both; a prefix with host bits is
refused); `ranges[]`, an ABR's summaries (`area X range A M [not-advertise] [cost N]`: `address`
and `mask`, or a `prefix`; `advertise` false is `not-advertise`; a range whose address is not
the network of its mask is refused, naming both).

### OSPFv3: `routing.ospfv3[]` (`ipv6 router ospf <process>`)

As OSPFv2 without network statements: an interface joins an area itself. A range is an IPv6
`prefix` (`area 10 range 2001:DB8:10::/48`), refused with host bits or as IPv4. `redistribute`
takes `include_connected` (`include-connected`) and names RIPng by its process name
(`redistribute rip <name>`). The router id is still an IPv4 address.

### RIPv2: `routing.rip` (`router rip`)

| Field | Line | Notes |
|---|---|---|
| `version` | `version 1\|2` | |
| `timers` | `timers basic U I H F` | `update`, `invalid`, `holddown`, `flush`, all four or none |
| `redistribute[]` | `redistribute <protocol> [<process>] [metric N] [route-map R]` | connected, static, ospf, bgp, eigrp; a metric 0 to 16 |
| `default_metric` | `default-metric N` | 1 to 16 |
| passive interfaces | as OSPF | |
| `classful_networks[]` | `network A.B.C.D` | classful only: `192.0.2.64` is refused, naming `192.0.2.0/24` and what to write |
| `default_information` | `default-information originate [route-map R]` | `originate`, `route_map` |
| `distance` | `distance N` | |
| `auto_summary` | `auto-summary`, `no auto-summary` | true, false, or absent |

### RIPng: `routing.ripng[]` (`ipv6 router rip <name>`)

`name`, and `redistribute[]` (connected, static, ospf, bgp; `metric`, `include_connected`,
`route_map`).

### An interface's own lines

- `ospf_interface` (`ip ospf ...`) and `ospfv3_interface` (`ipv6 ospf ...`): `process` and
  `area` together (`ip ospf 1 area 0`; a process routing does not declare is refused, since IOS
  would create one intent does not hold), `cost`, `network_type` (broadcast, non-broadcast,
  point-to-point, point-to-multipoint), `priority` (0 to 255), `hello_interval`,
  `dead_interval`.
- `ripng_interface[]`: one entry per RIPng process, `name`, `enable` (`ipv6 rip <name> enable`),
  `default_information` (`originate` or `only`); a name routing does not declare is refused.

## Modelled, and left as lines

Modelled: every routing line in the lab's captures except `max-metric router-lsa ...` (the
host's r2, in both families), which stays in `settings` and `raw`. Left as lines by design
(verbatim, rendered after the modelled ones): `max-metric`, `area X authentication`, an NSSA's
options beyond `no-summary`, `distribute-list`, `neighbor`, `offset-list`, `timers throttle`,
`bfd`, `redistribute` of any other protocol (`isis`, `lisp`) or with any other option
(`match`, `metric transparent`, `level-2`), `distance ospf ...`, an interface's OSPF
authentication and message-digest keys, and any line whose tokens the partial would write in
another order. A line left this way still round-trips; it is simply not a field yet.

## What is not measured

- **IOS-XE 17 and `subnets`.** The C8000v captures print `redistribute rip` and
  `redistribute static` with no `subnets`; the vIOS-L2 capture prints
  `redistribute static subnets`. The packs write `subnets` when the field says so, on both
  dialects. Whether IOS-XE 17.6 accepts it and prints it is unmeasured; if it hides it, an
  authored `subnets: true` would show as a difference against every capture. One measurement:
  a preview of `redistribute connected subnets` on the IOS-XE canary, and its capture.
- **Token and line order the captures do not show:** `metric-type`, `tag` and `route-map` within
  a `redistribute` line, RIPng's `include-connected` beside `metric`, the order of `area` lines,
  `log-adjacency-changes` and `auto-cost` against `router-id`. A capture holding one is the
  judge: until then the parser keeps such a line verbatim, and an authored field renders in the
  partial's order.

## Adding a pack

1. Its fields, their empty values and its checks, in `modules/nsot/features/<pack>.py`; each
   refusal names the field (`hostvars.dotted`), its value and the rule or the other operand.
2. Its macros in the partial (today the routing section of `templates/_common.j2`), reading
   only completed fields; the block macro writes the lines below a header, the unmodelled lines
   after it.
3. The parser hands each line to the pack (`claim_*`), which keeps a line only when the macro
   reproduces it; the lines it does not keep stay where intent held them.
4. The new keys in `hostvars.INTENT_SECTIONS` (and `INTERFACE_DEFAULTS`, with
   `BaseParser.INTERFACE_DEFAULTS`, for an interface field), and in `features.MARKERS` if the
   pack brings the first field a library from before it would not read.
5. Tests on the real captures that carry the feature: the round trip, parse to fields, the exact
   lines for each dialect, the refusals beside their control, IPv6 beside IPv4.

## Still to come (C764)

The device page's feature tiles, presets that write a feature's intent from NetBox selectors,
the catalog page, removal (a pack's negation, since deploy is merge-only), the pack format as
files (`feature.yml`, a capability matrix) and a NETCONF renderer remain, as the register row
sets out. No manual page: the operator's, 2026-10-19 (pages for Lab 8's steps come when they
land on devices).
