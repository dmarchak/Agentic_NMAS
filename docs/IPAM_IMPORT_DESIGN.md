# IPAM import from a spreadsheet, staged at headquarters (a FUTURE design)

**FUTURE: post-cutover, not Phase 7 work. Nothing here is built.** This note designs a one-way,
one-time import of an organisation's IPAM spreadsheet into a network's NetBox, run by
headquarters NetOps while a fly-away kit is staged, so the kit arrives knowing its own
addressing and its operator never sees the sheet or maps a column. It is one of six design notes
written from the operator's brief of 2026-10-16: `docs/SITES_DESIGN.md`, `docs/FLOWS_DESIGN.md`,
`docs/EDGE_ARCHITECTURE.md`, `docs/BRINGUP_FROM_DOCUMENTS.md` and `docs/OFFLINE_OPERATION.md`
are the others. Every statement about Mercury below was read in the code on 2026-10-16 and names
its file and function; every statement about an outside product that could not be checked here is
marked **(to confirm)**.

**The classified-documents constraint governs everything here.** In the operator's setting the
spreadsheet, and every value taken from it, may be classified. No real spreadsheet is ever given
to a developer, an AI service or this project, and none is reconstructed from memory. The
examples and the test corpus are synthetic, use only the documentation ranges (192.0.2.0/24,
198.51.100.0/24, 203.0.113.0/24, 2001:db8::/32), and are deliberately messy. Real templates are
taught to Mercury inside the secure environment, by headquarters NetOps, as mapping profiles.

## 1. The case

- The organisation keeps its IPAM in an Excel workbook. Each fly-away kit (a switch, a C8000v, a
  firewall and a satellite uplink) is identified by a node number, and the workbook holds rows for
  many nodes.
- Each kit is its own network on its own Mercury instance, under a headquarters manager
  (`docs/EDGE_ARCHITECTURE.md`). Its NetBox is the kit instance's.
- Kit operators are minimally trained. Every hard decision is made in advance by headquarters.
- Once imported and accepted, NetBox is the IPAM and the spreadsheet is retired for that network.
  This matches the charter's table (docs/MERCURY_CHARTER.md, "The sources of truth"): NetBox owns
  "IPAM as decided", and Mercury "writes only as the first step of a confirmed operation".

## 2. What exists today, measured in the code

The import is built on what Mercury already does when it writes NetBox. Each piece below was
read, not assumed.

**The three write chokepoints.** `modules/netbox_client.py`'s `_nb_post`, `_nb_patch` and
`_nb_delete` are the only write paths (`modules/netbox_guard.py`'s module docstring, item 1).
Each one:
- calls `netbox_guard.assert_writes_allowed`, which refuses unless the master switch
  `netbox_allow_writes` is on AND the block declares an authority (`for_list(..., authority=...)`;
  C155). A write that names no confirmation is refused at the write, not at the route;
- inside `netbox_guard.dry_run()`, records the operation it would have made
  (`record_intent`) instead of writing, with reads still reaching NetBox, so the same code
  produces the preview (`_DryRunPlan`, with a virtual store so a get-or-create does not plan a
  duplicate);
- `_nb_post` adds the `nmas-managed` tag through `_with_managed_tag`, failing closed (a create
  that cannot be tagged is refused, C59), and records the new id with
  `netbox_guard.record_created` (list, endpoint, id, name, actor, authority);
- `_nb_patch` reads the before-state itself and records what changed with
  `netbox_guard.record_modified`, in a separate file so an update never makes a person's object
  removable;
- `_nb_delete` reads a 404 back (C466) and forgets the record entry only when the object is gone.

**Which endpoints get the tag.** `netbox_guard.TAGGABLE_ENDPOINTS` lists regions, sites,
devices, interfaces, VRFs, prefixes, VLANs, IP addresses and VPN tunnels. **It does not list
`ipam/ip-ranges` or `ipam/vlan-groups`**, and nothing in `modules/`, `routes/` or `scripts/`
writes either endpoint today (searched 2026-10-16). An import that creates ranges or VLAN groups
through `_nb_post` today would create them untagged, which is the C59 defect: objects Remove can
never act on. Adding both endpoints is part of this design.

**Today's removal rule.** `netbox_client.remove_list_from_netbox` deletes an object only when
Mercury's created record holds it for the list AND it still carries `nmas-managed`, walking
`_REMOVAL_ORDER` (an allowlist; `extras/` endpoints are never walked,
`tests/test_netbox_write_gate.py`). The removal preview asks NetBox what a delete takes beyond
the list (`_cascade_preview`, `modules/netbox_cascade.py`'s `collateral`). **The rule does not
check whether anyone changed an object after Mercury created it.** The import's undo needs that
check ("removes only objects that import created and nobody has since changed"), so it is new
here, not inherited.

**What the created record cannot say.** `record_created` keys entries by list and endpoint and
stores id, name, actor and authority. It holds no import identifier, so "the objects this import
created" is not answerable today, only "the objects Mercury created for this list".

**Adoption, a third record.** `netbox_guard.record_adopted` records objects that existed before
an adoption, never in the created record, "so nothing here can make an object deletable". The
import's "adopt" decision for a collision reuses that idea (section 7).

**One writer per network.** `netbox_guard.list_writer` takes an exclusive lock per list across
processes and refuses a second writer by name (`NetBoxBusy`), never queues
(CONCURRENCY_AUDIT R21).

**Preview, confirm by hash.** `modules/netbox_authz.py`: `compute_plan_hash` is a SHA-256 over the
plan's creates, updates and deletes (endpoint, name, id, payload; order-insensitive, synthetic
ids collapsed). `issue_token` binds a one-shot token to that hash (300 s by default);
`consume_token` removes it whether or not it validates; `verify_plan_unchanged` refuses when the
recomputed plan's hash differs. `modules/netbox_ops.py`'s `authorize` runs these in order and
turns the master switch on only after both pass (C330). Two limits are inherited as they are:
the token store is **in-process** (its docstring: a restart means preview again), and the plan
hash covers the NetBox operations only, nothing about where they came from.

**The preview's shape.** `modules/preview_confirm.py`'s `build` is the one preview: six parts
(what, what_not, program, operands, gates, confirm), and it refuses a part that is empty without
saying so. `netbox_import_preview` and `_nb_gates` are today's NetBox instance of it.
`modules/netbox_jobs.py` runs a preview as a job whose answer is stored on disk and announced on
the `netbox` key, so no request waits on it.

**Verify is missing for NetBox writes today.** `modules/operation_stages.py` declares today's
NetBox import with verify `MISSING: NetBox is not read back after an import`, and the gaps are
counted and only shrink (`MISSING_CEILING`). A new import must declare a real verify, never a new
MISSING.

**Masking.** `modules/redact.py`'s `redact_text` masks values this installation knows (its
docstring: "What it cannot do": a secret it has never stored is not matched).
`modules/outbound.py`'s `mask_payload` runs every string of a response through it, and masks a
string under a key in `SECRET_FIELDS` by its key, after every hash is computed from the
truthful plan.

**The record in git.** `modules/nsot/repo.py`'s `commit` is the one commit in a network's
repository: it runs `config_check.precommit` first, then commits, then publishes (the post-commit
push and archive, `publish`). `config_check.GOVERNED` is `golden/`, `host_vars/`, `templates/`,
`profiles/` and `dhcp/`; a new folder for import records is outside it today.

**At-rest encryption.** `modules/secrets_store.py`'s `encrypt_value` is Fernet under
`data/key.key`; `modules/config.py`'s `open_secure` creates a file owner-only before anything is
written.

**The approved direction of data.** docs/NSOT_OWNERSHIP.md, part 4 (APPROVED 2026-10-07): design
data (interfaces, addresses, VLANs, VRFs) moves to NetBox in Phase 2, and **"Branching is
REQUIRED for Phase 2's design-data writes"**; a direct write with its recorded before is
acceptable only for single-field status transitions. An IPAM import is a design-data write. The
branching spike that part 4 names ("Before Phase 2: a measured spike of the branching plugin")
has not run. Section 7 designs the import to write in a branch and names what changes if the
spike says otherwise.

## 3. The two paths, and the one-time rule

### 3.1 Primary: staging at headquarters

NetOps runs the import on the kit's own instance while the kit is on the bench at headquarters,
before it ships. The kit's node number comes from its signed identity
(`docs/EDGE_ARCHITECTURE.md`), never typed. The import reads only the rows belonging to that node
(section 4.3), validates them, previews the NetBox change, and NetOps confirms it. The kit ships
with its addressing in its NetBox and the import's record in its repository.

A fleet staging can prepare every node's import from one workbook in one pass at headquarters:
one validation report for the whole workbook, then one preview per kit, each confirmed on that
kit's instance. Headquarters' copy of the workbook stays at headquarters (section 10).

### 3.2 Fallback: "Load the sheet you were given"

For a sheet that must be loaded in the field, the kit operator gets one action, **Load the sheet
you were given**, on the reduced plain-language screens `docs/EDGE_ARCHITECTURE.md` defines. It
runs against a mapping profile headquarters already built and signed for that template; the
operator chooses nothing.

- **Ready:** "Ready: 4 networks, 2 VLANs, 9 addresses for node 7. Nothing is written until you
  press Load." The button names the work it does.
- **A problem:** one plain sentence per problem with a code to call in: "Row 12: the gateway is
  not inside its network. Call headquarters with code R12-GW." A workbook whose profile maps more
  than one sheet prefixes the sheet's number: S2-R12-GW.
- **Anything needing a decision is a refusal with a code,** never a question: an unknown column, a
  colour the profile does not map, a collision with NetBox that is not identical (section 7). The
  field path writes only when validation finds nothing and every collision is one the profile
  decided in advance.

The confirm needs a verified person. Identity today is the access proxy's assertion
(`modules/identity.py`), which needs the network; local authentication on a disconnected kit is
designed in `docs/OFFLINE_OPERATION.md` and is a prerequisite of this path.

### 3.3 One-way and one-time

- An import is **accepted** by a person after its verify passes. Acceptance is recorded in the
  network's repository (section 8) and retires the spreadsheet for that network: from then on
  NetBox is the IPAM, edited in NetBox or through Mercury's confirmed operations.
- **A later load of a sheet for an accepted network compares and writes nothing.** It shows the
  differences between the sheet and NetBox (in NetBox, not in the sheet; in the sheet, not in
  NetBox; different), with no confirm control and no token issued. It is a read, held to the rule
  that a read writes nothing (`tests/test_reads_write_nothing.py`).
- Nothing flows back to the spreadsheet. Mercury never writes an `.xlsx`.

## 4. Reading the workbook

### 4.1 The library

The brief asks for a permissively licensed reader, openpyxl or a measured alternative.

- **openpyxl is not a dependency today.** It is absent from `requirements.txt` and
  `requirements.lock`, and the CI interpreter's site-packages
  (`<home>/.local/share/nmas-py312`) holds no copy. **Its licence, read from its own terms on
  2026-10-16:** MIT (openpyxl 3.1.5's `LICENCE.rst`), and its one dependency et_xmlfile 2.0.0
  is MIT and includes Python standard-library code under the PSF licence; both read from the
  published wheels and recorded in `docs/STANDING_APPROVAL_LOG.md`. A new third-party licence is
  still the operator's decision to adopt (CLAUDE.md, Phase
  7 operating mode, stop 3). A new dependency enters as one line in `requirements.txt`, compiled
  into `requirements.lock` with hashes by the command in its header, and gets an entry in
  `docs/THIRD_PARTY.json`, which `tests/test_third_party_inventory.py` holds to the lock (its
  licence must be on the approved list or reviewed). The NetworkX row of 2026-10-10 in
  `docs/STANDING_APPROVAL_LOG.md` is the precedent.
- **Alternatives to measure, not to assume:**
  1. openpyxl in read mode (cell values, merged ranges, hidden rows and columns, fills, number
     formats; whether it reports a fill set by conditional formatting is to confirm);
  2. a reader for the Office Open XML parts built on Python's `zipfile` and `xml.etree`, or on
     lxml, which is already in the lock (5.2.1, BSD-3-Clause in `docs/THIRD_PARTY.json`): no new
     licence, but shared strings, styles, theme colours with tints, merged ranges and hidden rows
     are each code Mercury would own;
  3. python-calamine (licence to confirm; whether it exposes fills at all is to confirm, and
     without fills it cannot meet section 4.2's colour rule).
- **Only `.xlsx` is read.** A legacy `.xls`, a `.xlsm` or anything else is refused naming its
  format; no macro is ever run.
- **The file is untrusted input.** A workbook is a zip of XML parts: the reader bounds the
  uncompressed size and part count before parsing, and parses XML with entity expansion off
  (whether openpyxl does so by itself is to confirm). The bounds come from measuring the synthetic
  corpus, at about 2.5 times the largest, written beside the number.

### 4.2 What real sheets hold, and how each is read

| What the sheet does | How it is read | When it is a problem |
|---|---|---|
| Several sheets, or several tables on one sheet | the profile names each sheet and the header row (by its text) of each table | a named sheet or header missing (COL) |
| Merged cells | the value is taken from the merged range's top-left cell and applies to every row the range spans, only when the profile says that column carries down | a merge across mapped columns, or one the profile does not expect (MRG) |
| Hidden rows and columns | read and counted, drawn as hidden; the profile says whether hidden rows are imported or skipped | a hidden row the profile does not decide (HID) |
| Masks as 255.255.255.0 or /24 | the profile states the column's form; Python's `ipaddress` turns a dotted mask into a length | see the wildcard trap below (MASK) |
| Ranges written `.10-.20` | expanded against the row's own prefix into a start and an end address | an end before its start, or outside the prefix (RNG) |
| Notes in cells | kept as text; mapped to a description only where the profile says so, never parsed for values | none by themselves |
| Status shown by cell colour | the raw fill is read and shown (an RGB value, or a theme index with its tint), and the profile maps each exact fill to a status | a fill the profile does not map (FILL); never a nearest-colour match |
| A spreadsheet's own type coercion | the stored cell type and number format are read beside the value | a date or number where the profile expects an address or a range, the classic `1/24` or `10-20` turned into a date (TYPE) |
| Formulas | the cached value is read | a formula with no cached value (FORM) |

**The wildcard trap, measured here.** Python 3.12.3's `ipaddress.ip_network("192.0.2.0/0.0.0.255")`
returns `192.0.2.0/24`: it reads 0.0.0.255 as a host mask without saying so. A sheet that mixes
netmasks and wildcard masks would therefore import silently. The profile declares each mask
column as `netmask`, `wildcard` or `length`, and a value in the other form is a MASK problem,
never converted.

### 4.3 Never guess silently

- An unknown column is listed and refused until the profile says to ignore it; an expected column
  that is missing is refused.
- **Rows for other nodes.** The profile names the column (or section heading) holding the node
  number. Written forms (7, 07, N-007, Node 7) are normalised to one form first, and matching is
  exact with whole-number boundaries: node 7 never matches 17, 70, 7.1 or 107. Zero rows for the
  kit's node, or two blocks claiming it, is a refusal with a code. Rows for other nodes are
  counted ("412 rows belong to other nodes and were not read further") and never stored on the
  kit. This is the same rule `docs/BRINGUP_FROM_DOCUMENTS.md` applies to provider documents.
- Every refusal names the comparison and both operands: "column D ('Gateway'), row 12: 198.51.100.1
  is not inside 192.0.2.0/24 (column C)".

## 5. The mapping profile

Built by headquarters NetOps once per spreadsheet template, inside the secure environment, saved
as a named, versioned file and distributed with the build standard (`docs/EDGE_ARCHITECTURE.md`
owns the build standard's repository and the signature a kit verifies).

A profile holds:
- the template's identity: which sheets, which header rows, the expected header texts;
- **columns to NetBox fields:** node number, site, VRF, VLAN ID and name, VLAN group, prefix,
  gateway, IP range, IP address, status, role, tenant, description, and device and interface where
  the template has them;
- each mask column's form (netmask, wildcard or length) and each range column's form;
- the fill map (exact fill to status) and the hidden-row and merged-cell decisions;
- the collision policy the field path may apply on its own (normally: an identical object is
  adopted, anything else refused);
- columns that are ignored, named one by one.

**No profile maps a column to a secret.** NetBox holds no credentials (the charter's
"Credentials: the one accepted exception"; `tests/test_netbox_holds_no_secret.py` for the
existing import). A column whose header or content looks like a credential is refused when the
profile is built. Cells drawn on NetOps' screens go through `redact_text`, which masks only values
the installation already holds; an unknown secret typed into a note is not caught, which is one
more reason notes are kept as text and never parsed.

A profile is YAML (PyYAML is already in the lock) and is hashed; the hash appears in every preview
and record. The format is generic: a profile names fields, never a lab or an organisation, so the
product stays network-agnostic (`tests/test_lab_specifics.py`). The public repository holds only
synthetic profiles for the synthetic corpus. The optional proposal of a mapping for an unfamiliar
template by the document-extraction engine is `docs/BRINGUP_FROM_DOCUMENTS.md`'s; a proposed
mapping is only ever confirmed by NetOps.

## 6. Validation, before any write

All of it runs on the parsed rows, in code, with Python's `ipaddress`, before NetBox is asked
anything. Nothing is written while any problem stands, on either path.

| Code | Check |
|---|---|
| HB | host bits set on a prefix (`ip_network(..., strict=True)` raises) |
| OUT | an address, gateway or range outside its stated prefix |
| GW | a gateway outside its network, or (IPv4, length below 31) the network or broadcast address |
| OVL, DUP | overlapping or duplicate prefixes; allowed only across VRFs or sites, by the rule `docs/SITES_DESIGN.md` sets for repeated kit addressing |
| IP2 | the same address given to two devices or interfaces in one VRF |
| VID | a VLAN ID outside 1 to 4094 |
| SITE | an unknown site or node number (against the network's sites, `docs/SITES_DESIGN.md`, and the kit's signed identity) |
| CON | rows that contradict each other: one prefix with two VLANs, one VLAN ID with two names in one site or group, one address with two statuses |
| MASK, RNG, TYPE, FILL, FORM, MRG, HID, COL | the reading problems of section 4.2 |

**Each problem has two voices.** For NetOps: sheet, row, column, the value as read (masked where
`redact_text` masks it), the comparison and both operands. For the operator: one plain sentence
and the code (R12-GW). The code is deterministic, built from row and check, so the person at
headquarters who takes the call can find the same row in their own copy.

**Large workbooks.** The report leads with counts by problem and by sheet, groups and collapses,
and offers search; a row's detail opens on expand (CLAUDE.md, "Built for large fleets").

## 7. Preview, confirm, write

**The preview** is a dry run of the import's real writer against the real NetBox inside
`netbox_guard.dry_run()`, so creates, updates and adoptions are exactly what the write would do,
drawn through `preview_confirm.build`:
- **what:** counts by object type in creation order: sites (only those the network's site owner
  allows the import to create, `docs/SITES_DESIGN.md`), VRFs, VLAN groups and VLANs, prefixes
  (parent before child), IP ranges, addresses;
- **what_not:** rows for other nodes, ignored columns, skipped hidden rows, objects adopted rather
  than created, and that nothing is deleted;
- **program:** each object and its fields, as NetBox will be told;
- **operands:** the file's sha256, the profile's name, version and hash, the node, the counts, the
  plan hash;
- **gates:** today's `_nb_gates` plus "validation found nothing", "the stored file still has this
  hash" and "the profile is the one previewed";
- **confirm:** who may confirm (`confirm_part`).

**Collisions with what NetBox already holds,** each shown and decided before the confirm:
- identical (same key, same fields): **adopted**, recorded in an adoption record like
  `netbox_guard.record_adopted`'s, never in the created record, so it never becomes removable;
- same key, different fields: NetOps chooses **adopt as it is** (skip), **update** (a PATCH
  through `_nb_patch`, its before recorded by `record_modified`, never tagged), or **refuse** the
  import; the field path refuses with a code unless the profile decided it;
- held by another network or untagged by a person: never deleted, never re-owned.

**The confirm is bound to one hash** over the file's sha256, the profile's hash, the collision
decisions and `compute_plan_hash` of the dry run's plan, because the plan hash alone says nothing
about where the plan came from. At confirm, the stored file is re-read and re-hashed, re-parsed
with the same profile, re-validated and re-planned; any difference refuses, naming what moved
(the file, the profile, or NetBox) and both values. Today's `netbox_ops.authorize` does the
NetBox half; the import adds the other three. Its token lives in memory as today's does
(`netbox_authz`'s docstring).

**The write** runs in a job (`netbox_jobs`' pattern: stored state, announced on the `netbox`
key), under `list_writer` for the network and `for_list(..., actor=..., authority="the IPAM
import <id>, confirmed by <person>")`, through the three chokepoints only. Per
docs/NSOT_OWNERSHIP.md part 4 it writes **in a NetBox Branching branch**: verify reads the
branch, and the branch is merged only when verify passes; a failed or abandoned import leaves the
branch unmerged and main untouched. How Mercury's session writes into a branch (a request header
on the session; to confirm), whether the dry run can plan against a branch, and what a merge
leaves in NetBox's change log are the branching spike's questions. If the spike finds branching
unusable, a direct write with recorded provenance is a change to the operator's 2026-10-07
decision, to be put to the operator, not assumed.

**Verify** re-reads every created and updated object by id (`_nb_read_by_id`, which keeps gone
and unreadable apart) and compares each field with the plan, NetBox's normalisation (a prefix's
canonical form, an address's length) applied to both sides. An unreadable object neither passes
nor fails. This gives the import the read-back today's import lacks in `operation_stages.py`.

**A failure part-way** is reported as partial, naming what landed. Before a merge, the branch is
abandoned. Without a branch, the import's own undo (section 8) is offered for what landed.

## 8. Provenance and undo

- **Tagged as Mercury's.** Every created object carries `nmas-managed` through `_nb_post`. This
  needs `ipam/ip-ranges` and `ipam/vlan-groups` added to `TAGGABLE_ENDPOINTS` (whether both accept
  tags on the deployed NetBox is to confirm) and to `_REMOVAL_ORDER` in dependency order.
- **The import's id on the record.** `record_created` gains an `import` field, so one import's
  objects are answerable. Each entry also keeps the object's `last_updated` as NetBox returned it at
  creation (whether a POST's answer carries it is to confirm).
- **Source on the object.** Each object carries the file's sha256, the sheet and the row in a
  custom field (`mercury_import`, text), created through the existing `_CUSTOM_FIELDS` and
  `_ensure_custom_field` pattern. A journal entry was considered and not chosen: journal entries
  live under `extras/`, which no remover walks (`tests/test_netbox_write_gate.py`), and a custom
  field can be filtered on.
- **The record in git.** The import, its profile (by name, version and hash), the file's sha256,
  the node, the counts, the decisions, the verify result and, later, the acceptance are committed
  through `repo.commit()` to the network's repository, under a new `imports/` folder with
  `Actor:` and `Actor-Verified:` trailers. The record holds object ids, sheets and row numbers,
  **never cell values**, and a new check for `imports/` (added to `config_check.GOVERNED`)
  refuses a record carrying an address or a cell's text. **The spreadsheet itself is never
  committed.**
- **Undo of one import** is its own preview and confirm. It removes an object only when all three
  hold: Mercury's created record holds it **for this import**, it still carries `nmas-managed`
  (today's rule, `remove_list_from_netbox`), and **nobody has changed it since**: its
  `last_updated` equals the one recorded at creation. Whether `last_updated` moves on a PATCH that
  changes nothing, or on a tag or journal change, is to confirm on the deployed NetBox before this
  test is trusted. Anything changed since is listed and kept. The cascade preview
  (`netbox_cascade.collateral`) runs as it does for Remove. Adopted and updated objects are never
  deleted. After acceptance, an undo needs a stated reason, recorded with it.

## 9. The writing back end: three options evaluated

The brief asks whether NetBox Labs' Diode, or NetBox's own bulk import, should write, instead of
a writer built on Mercury's chokepoints. Diode and NetBox facts below are from their public
documentation as known at the time of writing, none verified in this repository; each is marked.

### 9.1 NetBox Labs' Diode

What it is (to confirm): an ingestion service for discovered data. Producers (Python or Go SDKs,
the Orb agent) send entities to a Diode server over gRPC; a reconciler compares them with NetBox
and applies creates and updates through a Diode NetBox plugin, under the plugin's own account.
It runs as its own services beside NetBox, with an authentication service for its clients (to
confirm). docs/NSOT_OWNERSHIP.md part 4 already places "Diode-style ingestion into a branch or
changeset" at Phase 3, discovery as proposal.

Against this import's requirements:
- **Preview bound to a hash before any write:** Diode reconciles after ingestion; whether it
  offers a pre-write plan that Mercury could bind a confirm to is to confirm. Without one, the
  rule "what is confirmed is what is sent" cannot hold.
- **Provenance and undo:** the writes are the plugin's, not Mercury's chokepoints, so the
  `nmas-managed` tag, `record_created`, `record_modified` and the authority gate would all be
  bypassed. Whether Diode returns the NetBox ids it created is to confirm; without them, undo by
  record is impossible.
- **Deletes:** Diode is oriented to create and update; deletion is to confirm.
- **Cost:** more services per instance, which matters for a kit; a licence for the server to
  confirm (a new third-party licence is the operator's decision).

**Verdict: not for this import.** Its fit is Phase 3, where discovery proposes and a person
approves, and that evaluation belongs there.

### 9.2 NetBox's own bulk import

Two different things share the name (both to confirm in detail):
- **The web interface's bulk import** (per object type, CSV, JSON or YAML with NetBox's field
  names as headers). It would make NetOps map columns into NetBox's own names by hand per object
  type, run no cross-row validation (a gateway inside its prefix, contradictory rows), bypass
  Mercury's master switch, authority, tag and records, and has no plain-language field path. It
  remains the operator's manual tool in NetBox; it is not the back end.
- **The REST API's bulk create** (a list of objects in one POST to one endpoint, applied in one
  database transaction: to confirm). This is not a rival back end but a possible optimisation
  INSIDE the chokepoint: a `_nb_post` that accepts a list would keep the gate, the tag and the
  record per returned id. It is adopted only if the write's cost (Measurements still owed,
  item 5) shows the one-object path too slow.

### 9.3 Building the writer on Mercury's chokepoints

Everything section 2 lists is already in place and tested: the master switch and declared
authority, the dry run that runs the real code, the plan hash and one-shot token, fail-closed
tagging, the created, modified and adopted records, one writer per network, the cascade preview,
the stored, announced job, masking on the way out, and the commit path. What it lacks is named
in sections 7 and 8: two taggable endpoints, the import id on the record, the
unchanged-since test, the source custom field, verify by read-back, the composite hash, the
`imports/` record and its check, and the branch.

### 9.4 Recommendation

**Build the writer on Mercury's existing chokepoints, writing in a NetBox Branching branch.**
Why:
1. It is the only option of the three in which the confirm is bound by hash to exactly what is
   written, which is a standing rule, not a preference.
2. Provenance and undo depend on every write passing through `_nb_post`, `_nb_patch` and
   `_nb_delete`. Diode and the web bulk import write around them.
3. No new service and no new licence for the writer; the only new licence in the design is the
   workbook reader's (section 4.1).
4. A kit has to run it offline on its own instance; fewer moving parts is the safer kit.
5. Diode is kept for the job it was built for, Phase 3's discovery proposals, and the API's bulk
   create is kept as a measured optimisation inside the chokepoint.

## 10. The source file and its classification

- The uploaded file is hashed (sha256) on arrival and stored encrypted with Fernet
  (`secrets_store`'s key) in a file created owner-only (`config.open_secure`), under the data
  directory, never in a repository and never served back by any route: records and screens name it
  only by its hash. The re-read at confirm (section 7) decrypts it in memory.
- **What that encryption does and does not protect.** It protects against a copy of the stored
  file alone. It does not protect against a copy of the whole data directory, because
  `data/key.key` sits beside it and is backed up with it. Encryption at rest of a kit, and remote
  wipe of one lost, are `docs/EDGE_ARCHITECTURE.md`'s offline prerequisites.
- **On a kit only its own node's rows are kept,** with the source file's sha256; the full
  multi-node workbook stays at headquarters, so a lost kit exposes one node, not the fleet.
- **Classification.** Values imported into NetBox inherit the workbook's classification; once
  they reach intent they are in goldens and commits. A network carrying a classification marking
  refuses any destination outside its enclave (`docs/EDGE_ARCHITECTURE.md`); the import adds no
  new path off the host, and its committed record holds no cell values.
- Deleting the stored workbook after acceptance is the organisation's records decision, offered
  as a confirmed action with its own record; nothing deletes it on a timer.

## 11. Wrong things that would look right

| Wrong, and looking right | What makes it visible |
|---|---|
| A wildcard mask read as a netmask, so every prefix is right-looking and wrong | the profile declares each mask column's form; the other form is a MASK problem (section 4.2) |
| A date the spreadsheet made out of `10-20` imported as nothing, or as a number | the cell's stored type is read and checked against the column (TYPE) |
| A hidden row carrying a contradicting prefix, skipped unseen | hidden rows are counted and drawn, and the profile decides them (HID) |
| A status colour matched to the nearest known colour | exact fills only; an unmapped fill is FILL, and the raw fill is shown |
| Ready shown while the file changed between preview and confirm | the file is re-hashed at confirm and the composite hash refuses, naming both hashes |
| Undo removes an object NetOps edited after the import | the unchanged-since test keeps it and lists it |
| An import with created ranges that Remove can never clean up | the two endpoints are taggable before the first range is written, pinned by a test |
| Verify passes because nothing could be read | unreadable is neither pass nor fail, and the result says how many |
| Rows for node 17 imported into node 7's kit | exact, normalised, whole-number node matching, with planted near-miss nodes in the corpus |

## What it touches

- `modules/netbox_client.py`: `_REMOVAL_ORDER` (ranges, VLAN groups), new get-or-create helpers
  for ranges and VLAN groups, `_CUSTOM_FIELDS` (`mercury_import`), and, only if measured, a list
  form of `_nb_post`.
- `modules/netbox_guard.py`: `TAGGABLE_ENDPOINTS`, `record_created`'s import id and
  `last_updated`, an adoption record keyed by import.
- `modules/netbox_ops.py` (`OPERATIONS` gains the import and its undo), `modules/netbox_authz.py`
  (the composite hash), `modules/netbox_jobs.py` (the import as a job).
- `modules/preview_confirm.py`: the import's preview and result, and the undo's.
- A new package for the workbook (read, profile, validate, plan), its name chosen when built.
- `modules/nsot/repo.py` callers and `modules/nsot/config_check.py` (`GOVERNED` gains `imports/`,
  with its check).
- `modules/route_gates.py`, `modules/invalidation.py`, `modules/operation_stages.py`: the new
  routes and their five stages, with no new MISSING.
- `routes/` (a v2 blueprint), `templates/v2/` after a signed-off board, `docs/manual/` pages
  (screen and How it works).
- `requirements.txt`, `requirements.lock`, `docs/THIRD_PARTY.json`, once the operator approves a
  reader's licence.

## Tests it needs

- **A synthetic corpus, deliberately messy,** in `tests/fixtures/` under a new folder: several
  sheets and tables, merged and hidden cells, both mask forms and wildcard masks, `.10-.20`
  ranges, notes, colour-coded status (RGB and theme fills with tints), date-coerced cells, cached
  and uncached formulas, near-miss nodes side by side (7, 17, 70, 107), a node listed twice, a node
  missing, every validation problem at least once. Documentation ranges only. **Saved by real
  spreadsheet applications** (at least one Excel and one LibreOffice save), because a corpus
  generated by the same library the reader uses would test the library against itself; the
  generator's input and each saved file's sha256 are committed beside it.
- **Expected results written by hand,** per fixture (sheet, row, code), never derived from the
  reader: a control's expectation comes by a path independent of the code it checks.
- **Reader tests:** each row of section 4.2, including the wildcard trap and a refused `.xls`.
- **Validation tests:** one per code, each shown able to fail by removing its check.
- **Node scoping:** the near-miss and duplicate-node fixtures, with nothing from other nodes kept.
- **Writer tests** with a stand-in session, in the style of `tests/test_netbox_write_gate.py`
  (whose `ExplodingSession` fails any request that reaches it): a dry run plans exactly what the
  write makes; every create is tagged and recorded with its import id; ranges and VLAN groups are
  taggable; a collision is adopted, updated or refused as decided; a changed file, profile or
  NetBox refuses at confirm naming both values.
- **Undo tests:** removes only this import's unchanged, tagged, recorded objects; keeps an edited
  one, an adopted one and an updated one; the cascade preview runs.
- **Compare mode** writes nothing and issues no token (`tests/test_reads_write_nothing.py`'s
  population).
- **The record:** `imports/` commits hold no cell value (a planted address is refused); the file is
  never committed; the stored file is owner-only (`tests/test_secret_file_modes.py`'s pattern).
- **The plain-language voice:** every code has a sentence, and no operator-facing sentence names a
  NetBox field.
- The standing suites: `tests/test_route_gates.py`, `tests/test_invalidation_map.py`,
  `tests/test_operation_stages.py`, `tests/test_signed_off_screens.py`, `tests/test_manual.py`,
  `tests/test_third_party_inventory.py`, `tests/test_large_fleets.py`.

## What it must not break

- The three chokepoints stay the only NetBox write paths, gated and attributed
  (`tests/test_netbox_write_gate.py`, `tests/test_netbox_write_authority.py`,
  `tests/test_netbox_writes_name_the_actor.py`).
- Remove's rule, tagged AND recorded, and its allowlist that never walks `extras/`
  (`tests/test_netbox_write_gate.py`); an update or adoption never becomes removable
  (`tests/test_netbox_update_provenance.py`).
- Deleting a list never deletes NetBox objects (`tests/test_list_delete_never_touches_netbox.py`).
- One writer per network (`tests/test_netbox_one_writer.py`).
- **Today's golden-driven sync** (`sync_list_to_netbox`) finds the imported objects instead of
  creating duplicates: it looks VRFs up by name and prefixes by prefix and VRF
  (`_ensure_vrf`, `_ensure_prefix`), under the network's list-level VRF, so the import's VRF and
  site keying must match what `docs/SITES_DESIGN.md` makes the sync use. A test runs the sync after
  an import and asserts no duplicate.
- Masking on the way out (`tests/test_no_post_returns_a_stored_secret.py`) and NetBox holding no
  secret (`tests/test_netbox_holds_no_secret.py`).
- Every commit through `repo.commit()` and published (`tests/test_every_commit_publishes.py`,
  `tests/test_commits_stage_what_they_wrote.py`).
- Nothing personal or installation-specific in the public corpus
  (`tests/test_nothing_personal_is_published.py`), and nothing lab-specific in the product
  (`tests/test_lab_specifics.py`).

## Measurements still owed

None is taken now. Each names its method and where it runs.

1. **The reader's licence.** openpyxl's and et_xmlfile's licences from each distribution's own
   licence file and metadata; python-calamine's likewise. Method: read the wheel's files after the
   operator approves the download; record in `docs/STANDING_APPROVAL_LOG.md`. Where: the laptop.
2. **The reader's capability.** Each row of section 4.2 against the corpus, for openpyxl and for
   the standard-library reader: what each reports for merged ranges, hidden rows, theme fills
   with tints, conditional-formatting fills, number formats and uncached formulas. Where: the
   laptop, in the suite, confined.
3. **The reader's bounds.** Peak memory and seconds for the largest corpus workbook and for a
   synthetic workbook of the size headquarters names (rows and sheets as a number, never a real
   file); the bounds are set at about 2.5 times the measured values. Where: the laptop, then the
   NMAS host.
4. **NetBox behaviour on the deployed version (4.6.9, docs/NSOT_OWNERSHIP.md part 4):** tags on
   `ipam/ip-ranges` and `ipam/vlan-groups`; `last_updated` in a POST's answer and whether a no-op
   PATCH, a tag change or a journal entry moves it; how prefixes and VLAN groups are scoped to a
   site; the API bulk create's atomicity. Method: read-only API reads (the schema and a few
   objects, counts and names only) through `scripts/nmas-host`; every write only against a scratch
   copy of NetBox built from the newest backup (`docs/NETBOX_BACKUP.md` already restores one into
   a scratch postgres for its restore test; a running NetBox on it is this measurement's setup),
   never the live one. Where: the NMAS host, outside 08:30 to 09:10 UTC.
5. **The write's cost.** Requests and seconds per row for the dry run and the write through the
   chokepoints, for the corpus and for a synthetic fleet-sized workbook, against the scratch copy.
   The reference is today's import: about 300 requests for a nine-device preview
   (`sync_list_to_netbox`'s docstring) and about a minute (`netbox_jobs`' docstring). This decides
   whether the API's bulk create is needed. Where: the NMAS host, against the scratch copy.
6. **The branching spike** of docs/NSOT_OWNERSHIP.md part 4, with the import's questions added:
   writing through Mercury's session into a branch, whether `dry_run()` can plan against one,
   verify reading the branch, merge, abandon, and what each leaves in the change log. Where: the
   scratch copy on the NMAS host.
7. **Diode's facts** marked to confirm in section 9.1 (a pre-write plan, returned ids, deletes,
   services, licence), from its own documentation, read only, nothing installed. Where: the
   laptop. Needed only to close section 9.1; the recommendation does not wait on it.
8. **The field path on kit hardware:** seconds from Load to the plain-language result for the
   corpus's largest single-node sheet. Where: a staged kit instance (`docs/EDGE_ARCHITECTURE.md`).

## Dependencies on the other four notes

- **`docs/SITES_DESIGN.md` comes first.** The import's site and VRF mapping (a network as a region
  or tenant, site per device, a VRF per site or site-scoped prefixes where identical kits repeat
  addressing) and the rule that makes a duplicate prefix legal across VRFs or sites are its. So is
  the one owner of site membership, which decides whether an import may create a site.
- **`docs/EDGE_ARCHITECTURE.md`:** the kit's signed node number (never typed), the build standard
  that distributes signed mapping profiles and headquarters' key that verifies them, the kit
  operator's plain-language mode and its "call headquarters with code" rule, the classification
  marking, and encryption at rest and remote wipe for a lost kit.
- **`docs/BRINGUP_FROM_DOCUMENTS.md` depends on this note:** its extracted provider values are
  compared with the staged plan this import leaves in NetBox, and its node-scoping rule is the one
  section 4.3 shares. Its engine may optionally propose a column mapping for NetOps to confirm.
- **`docs/FLOWS_DESIGN.md`** has no dependency in either direction for building; once built, the
  prefixes and sites this import writes are what its NetBox enrichment of flows reads.
- **`docs/OFFLINE_OPERATION.md`** (the sixth note): local authentication for the field path's
  confirm, and how the reader's package reaches an offline installation (an internal mirror or a
  wheel bundle checked against the lock's hashes).
