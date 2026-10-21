# Adopting the predecessor's NetBox objects (C1517, under C556): a plan for the operator

**Status: a draft for the operator's decision, written 2026-10-21. Nothing in it is built.** The
operator's direction (2026-10-21): adopt after Saturday's Lab 8 recording and before Lab 9; a
dry-run census lists every object and what Mercury would then change; anything a person has
edited since is excluded; adoption itself changes nothing; the changes follow as ordinary
previewed operations. Then C1519 (static routes as prefixes), C1518 (a prefix's VLAN) and
C1515 (the scope rule), in that order.

## 1. Why

Mercury edits or deletes a NetBox object only when it is Mercury's: edits need the
`nmas-managed` tag OR Mercury's created-object record (`netbox_client._mercury_may_edit`),
deletes need both (`netbox_guard`). Most of this network's NetBox objects were written before
either existed, by Mercury's predecessor ("Network Device Manager": the RD `ndm:default`, the
role "Network Device"). So Mercury cannot correct them:
- the 18 host prefixes per loopback (C1516) and the static-route prefixes (C1519) cannot be
  removed by Mercury;
- 27 SVI and link prefixes carry no scope and no VLAN, and the scope backfill and the VLAN fill
  (C1515, C1518) skip them;
- the Global duplicates stay.

What the ownership rule already lets the import do to anyone's object, adopted or not: update a
device's, an interface's and an address's own fields. Adoption changes what is gated:
- **edits** (tagged OR recorded): a prefix's scope (C1010's backfill), a site's region, a
  prefix's VLAN once C1518 is built;
- **deletes and C1506's platform correction** (tagged AND recorded).

## 2. The census, read-only on the host, 2026-10-21 ~17:00 UTC

NetBox 4.6.9. Owner: **Mercury's** is tagged or recorded; everything else is "not Mercury's".

| Endpoint | Objects | Mercury's | Not Mercury's |
|---|---|---|---|
| dcim/devices | 12 | 3 | 9 (r1 to r5, s1 to s4) |
| dcim/interfaces | 73 | 14 | 59 |
| dcim/cables | 13 | 2 | 11 |
| ipam/prefixes | 65 | 10 | 55 |
| ipam/ip-addresses | 88 | 12 | 76 |
| ipam/vlans | 6 | 0 | 6 |
| ipam/vrfs | 2 | 0 | 2 (`Default` ndm:default, `clab-mgmt`) |
| dcim/sites, dcim/regions | 2, 2 | 0 | 2, 2 |
| roles, platforms, device types, manufacturer, tags | 2, 3, 3, 1, 7 | 1 role | the rest |

**The changelog cannot use "user ≠ nmas".** NetBox holds 875 changelog entries: 718 by
`<user>` (the operator's account) and 157 by `nmas`. The predecessor wrote with the operator's
token, so its writes and the operator's own edits carry the same user. What does separate them:
- **Mercury's first `nmas` entry is 2026-10-05 17:53:26 UTC.** From then on Mercury writes only
  as `nmas`, so every `<user>` entry after it is a person: 83 entries (for example the
  2026-10-07 platform, device-type and tag fixes on r1 to s4, today's Branch site, VLAN group,
  VLAN and prefixes).
- **Before it, the `<user>` entries are mixed.** 529 of the 718 sit in 17 minutes holding ten
  or more writes each (a program's run: 2026-08-28 23:53, 2026-08-30 03:4x, and the
  2026-09-24 to 28 re-imports). The rest are single writes that could be either.

## 3. Which objects would be adopted

An object is **adopted** when all of these hold:
1. it is not Mercury's today;
2. its `create` entry is by `<user>` before 2026-10-05 17:53:26, inside a run minute (ten or
   more writes in that minute);
3. every later entry is by `nmas`, or by `<user>` before the switch inside a run minute;
4. it carries the import's fingerprint: a prefix described "Seen on <device> <interface>" or
   "Static via …", an address described "<device> <interface>", a device whose comments read
   "Platform: … | Version: … | Mgmt IP: …", an interface on such a device.

**Excluded, and listed for the operator one by one:** any object with a `<user>` entry after
the switch (a person edited it; the census already counts the nine core devices among these,
from the 2026-10-07 fixes), any single pre-switch `<user>` write outside a run, anything
without the fingerprint (sites, regions, VRFs, roles, platforms, device types, tags, VLANs, the
operator's Branch objects). Those stay the operator's.

**The census tool** (to build, read-only): for each endpoint above, every not-Mercury object
with its class (adopt, or excluded and the entry that excluded it: who, when, which fields),
then a **dry-run import with the adopted set treated as Mercury's**, its planned writes diffed
against today's dry run: exactly what adoption would let Mercury change. Nothing is written by
it; the dry run plans in memory and records no sync status.

## 4. What adoption does, and what it does not

**Adoption writes only Mercury's own record:** each adopted object goes into the created-object
record for its network, marked `adopted` with the census's evidence (its create entry and the
run minute). Nothing is written to NetBox. One preview lists every object and its evidence; one
confirm by hash, as a verified person; one record. Undo is removing those entries, also
recorded.

**What that allows:** edits only (the OR rule). Deletes still need the `nmas-managed` tag too,
which IS a NetBox write: tagging an adopted object is its own previewed operation, done only for
the objects a later deletion needs (the stray prefixes), never in bulk.

## 5. What would then change, each an ordinary previewed operation

1. **The Global duplicates** (no address sits in Global: 0, read 2026-10-21):

   | Prefix | Copies | Survives | Removed |
   |---|---|---|---|
   | 2001:db8::/64 | 20 Global, 33 clab-mgmt | 33 (r1's Gi1 is the emulator's management VRF, which the import leaves out by design) | 20 |
   | 2001:db8:30::/64 | 5 Global, 31 Default | 31 | 5 |
   | 2001:db8:255::/64 | 13 Global, 32 Default | 32 | 13 |
   | 10.255.1.16/32 | 55 Global (s3's static, Mercury's), 56 Default (r6's loopback, Mercury's) | neither: the loopback pool 10.255.1.0/24 holds the address | 55 (C1519), 56 (C1516) |

2. **C1519, static routes as prefixes:** the writer stops; 8.8.8.8/32 (29), 10.255.1.10/32 (14),
   r3's Null0 summary route (24), 10.255.0.0/16 (57) and 55 removed.
3. **C1516's host prefixes:** the 18 adopted "Seen on <device> Loopback0" /32 and /128 removed
   (the operator removes them by hand today, so this may be empty by then).
4. **C1518, a prefix's VLAN:** each SVI prefix given its VLAN (10.10.10.0/24, 10.10.20.0/24,
   10.255.0.0/24, 10.255.3.0/24, 2001:db8:10::/64, 2001:db8:20::/64, 2001:db8:30::/64,
   2001:db8:3::/64, 2001:db8:255::/64).
5. **C1515, the scope rule:** each adopted unscoped prefix scoped to the site of the device it is
   seen on (Default for every core device).

**Not changed by adoption or these steps:** devices, interfaces and addresses (the import already
updates their fields); cables (made only from both ends' LLDP); every excluded object.

## 6. Cost and risks

**Cost:**
- the census tool and its tests: about half a day;
- adoption's preview, confirm and record: about half a day, including the board for its card
  (the NetBox page);
- steps 1 to 5: C1519 about 45 minutes, C1518 a little over two hours, C1515 about 45 minutes,
  and a narrow "remove these prefixes" operation, about half a day (no Mercury removal is that
  narrow today).
- About three working days in all, with the walks.

**Risks:**
- **Misattribution, the main one.** A person's pre-switch single write inside a run minute
  would be read as the predecessor's. The fingerprint rule narrows it, and the preview lists the
  evidence for every object. The operator reads the excluded list and any doubtful one stays
  theirs.
- **Edits on adopted objects are not reversible by adoption's undo.** Undoing adoption stops
  further edits, but a scope or VLAN already written stays (each was recorded with its before,
  so each can be put back by hand).
- **The run-minute threshold is a measured proxy (ten writes a minute), not a property.** A
  short predecessor run below it leaves its objects excluded. That errs toward the operator
  keeping them.
- **Later imports widen.** Once adopted, the import's prefix-scope backfill and (with C1518) VLAN
  fill reach those prefixes on every import. That is the point of adopting them, and each import
  is still a preview and a confirm.

## 7. The operator's decisions

1. Adopt at all (C1517), after Saturday's recording and before Lab 9.
2. The discriminator: the `nmas` switch time plus run minutes plus the fingerprint (section 3),
   or another the operator prefers.
3. Which Global copy survives (section 5, table): as proposed, or otherwise.
