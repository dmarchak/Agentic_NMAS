# Bring-up from provider documents (a FUTURE design; not built)

**FUTURE, post-cutover; not Phase 7 work.** Written 2026-10-16 from the operator's brief, as one
of five design notes (with [SITES_DESIGN.md](SITES_DESIGN.md), [FLOWS_DESIGN.md](FLOWS_DESIGN.md),
[EDGE_ARCHITECTURE.md](EDGE_ARCHITECTURE.md) and [IPAM_IMPORT_DESIGN.md](IPAM_IMPORT_DESIGN.md);
[OFFLINE_OPERATION.md](OFFLINE_OPERATION.md) joined them the same day). It is the last of them to
be built: it needs the edge design (a kit's own Mercury instance, its signed node number, the
build standard, standard and emergency changes, the guided bring-up), the IPAM import (the staged
plan for each node) and Phase 8's built-in local model ([PHASE8_PLAN.md](PHASE8_PLAN.md) section
10), none of which exists yet. Documents only: nothing here is code, nothing was downloaded and
no device was touched. Under the charter ([MERCURY_CHARTER.md](MERCURY_CHARTER.md), "New
findings") it is FUTURE: worth doing, not now.

**The one measurement the local model needs before anything else** (section 6.1): on a
representative kit's compute unit, at headquarters staging, with the kit's whole stack running
(and its C8000v, if that runs on the same hardware), run PHASE8_PLAN 10.5's hardware check (free
RAM as MemAvailable, the CPU's features, a 30-second prompt and generation speed test), then time
the extraction of a node region from the synthetic corpus. Until that is measured, whether a kit
can run the model at all is UNKNOWN.

Words used here: the **kit operator** is the person on site with the kit; **headquarters
NetOps** builds the standard every kit runs; **the operator** is this project's, whose decisions
are cited by date.

## 1. The problem

Each fly-away kit (a Cisco switch, a Cisco 8000v, a Palo Alto firewall and a geostationary
satellite uplink) receives a **provider data sheet** for its first connection: the satellite
connection's and the ISP network's settings, in the provider's own format (PDF, Word, sometimes a
scan). One document holds the values for many sites, each identified by a **node number**. Today
a person reads the sheet and types the values. The kit operator is minimally trained, so every
typed value is a chance to bring up the wrong link, and a wrong WAN setting on a satellite link
cuts the kit off from the help it would need to correct it.

This note turns that sheet into a **proposed configuration the kit operator only confirms**,
value by value, against the highlighted line it came from.

**The classified-documents constraint governs everything below.** The provider documents, and
the values taken from them, may be classified. No real document is given to a developer, an AI
service or this project, and none is reconstructed from memory. Every format, value and example
here is invented: addresses from the documentation ranges (192.0.2.0/24, 198.51.100.0/24,
203.0.113.0/24, 2001:db8::/32), ASNs from 64496 to 64511. Real formats are taught to Mercury
inside the secure environment, by headquarters NetOps (section 3).

## 2. What exists today, and what this builds on

Read 2026-10-16, in this repository:

- **Intent is two stores** (`modules/nsot/hostvars.py`, the module docstring):
  `config_repo/.nsot/staging/host_vars/` is gitignored scratch, a proposal (`STAGING_REL`);
  `config_repo/host_vars/` is committed intent, the only intent on the deploy path
  (`COMMITTED_REL`). Extracted values are a proposal until a person commits them; this note keeps
  that split.
- **Committed intent never holds a secret value.** `hostvars.write_committed()` and
  `write_committed_text()` call `assert_no_secret_values()`, which refuses a `secrets:` mapping
  structurally and a stored value by whole-token match, but only for values of at least
  `MIN_CHECKABLE_SECRET` (8) characters; its docstring says the shorter ones are covered only by
  the structure and by extraction substituting references. `assert_printable()` refuses anything
  an IOS CLI cannot accept.
- **Secrets are references.** `modules/credentials.py` `template_secret_key(list_name, hostname,
  ref)` is the one builder of a secret's key, `<slug>:<host>:<ref>`;
  `set_template_secret()` stores the value Fernet-encrypted (through
  `modules/secrets_store.py` `encrypt_value()`, the `enc:v1:` format over `data/key.key`) and
  refuses to overwrite a secret another list owns. Templates read values only through the
  render's `secret()` global (`modules/nsot/roundtrip.py`), which renders an unknown reference
  as `<missing-secret:<ref>>`.
- **Masking on the way out** is `modules/redact.py` `redact_text()`: by syntactic position
  (`redact_positional()`, the `_POSITIONAL` table) and by known value (`known_secret_values()`,
  values of at least `MIN_REDACTABLE`, 8, characters). `transient_secret` redacts a value held
  for one operation and never stored. **Its positional shapes are IOS configuration lines**
  (`ppp chap password`, `pre-shared-key`, `key-string` and so on): a provider sheet's
  "PPP Password: <value>" line matches none of them. Section 12 designs for that.
- **Templates are per platform** (`modules/nsot/templates_repo.py`): `bindings.yml` maps a
  platform to its template, with per-device overrides; `render_source()` is the one answer to
  which template renders a device. An approval is bound to the template's import closure
  (`modules/nsot/approval.py` `template_fingerprint()`). **No template declares bounds on its
  inputs today**; the bring-up template's bounds (section 10) are new.
- **Every device operation is previewed, confirmed by hash, applied, verified, rolled back and
  recorded** (`modules/preview_confirm.py`, the six parts of `build()`; the five stages declared
  per route in `modules/operation_stages.py`). The bring-up's deploy is one more such operation.
- **Reads that touch a device are allowlisted:** `modules/readonly_commands.py`
  (`READ_ONLY_VERBS`: show, ping, traceroute, dir, more; ping and traceroute with bounded
  options). The bring-up's checks (section 11) are such reads.
- **Nothing in the repository manages a satellite modem, reads a PDF, Word file or scan, or runs
  OCR.** `requirements.txt` holds no such library; adding one is a new third-party licence, which
  is the operator's decision (`docs/THIRD_PARTY.json`'s approved list governs).

## 3. A generic engine, taught at headquarters

Mercury ships an extraction engine that **knows no provider**. Headquarters NetOps teaches it
each provider's format inside the secure environment, with a no-code screen (a board first, as
every new screen needs):

1. **Open a sample sheet.** It is read on the headquarters instance and never leaves it.
2. **Mark where each value sits**, as one of a fixed set of anchors:
   - a label: "the value after 'Default Gateway:'", on the same line or the next;
   - a table cell: the column headed 'Gateway', in the row of this node;
   - a region of a page: a box on page 2, for a scan or a fixed form.
3. **Mark where node numbers appear:** a table column, a section heading or a row label, and the
   written forms this provider uses (section 5).
4. **Run it** on the open sample and on every other sample in the folder, and read the result
   (section 14's "Test this profile").
5. **Save a provider parser profile**: data, not code, versioned, signed by headquarters and
   distributed with the build standard ([EDGE_ARCHITECTURE.md](EDGE_ARCHITECTURE.md)), beside
   the IPAM mapping profiles ([IPAM_IMPORT_DESIGN.md](IPAM_IMPORT_DESIGN.md)).

A profile names the anchors and the node locator only. It holds no value and no sample text, so a
profile carries the shape of a format, not its content. Whether a format's shape is itself
classified is the organisation's question, not this design's; a profile inherits the marking of
the samples it was built from, and a marked profile travels only inside the enclave
([EDGE_ARCHITECTURE.md](EDGE_ARCHITECTURE.md), classified networks).

**Deterministic first** (PHASE8_PLAN section 2, rule 2): the parser profile is the primary path,
and needs no model. The model (section 6) is the fallback for a format with no profile.

**Reading the file, deterministically, before either path.** Each document becomes a text layer
with coordinates: page, line, and for a table its row and column. A PDF's text layer, a Word
file's paragraphs and tables, and for a scan an OCR pass, each by a library chosen with its
licence measured (the operator's decision). Every value later cites a coordinate in this layer,
so the same layer is what the kit operator's highlight draws (section 9). A scan's OCR confidence
per word is kept, and a value read from a word below a floor is never proposed, only shown as
"could not read this clearly".

## 4. The fixed schema

Headquarters defines the schema once, in the build standard; providers vary, the schema does
not. Each field has a type, a validator (section 8) and a flag for whether it is a secret:

| Field | Type | Secret | Example (invented) |
|---|---|---|---|
| WAN address and mask | an interface address | no | 203.0.113.10/29 |
| WAN gateway | an address | no | 203.0.113.9 |
| DNS servers | one or more addresses | no | 198.51.100.53 |
| VLAN tag | 1 to 4094, or none | no | 210 |
| BGP ASN and neighbour, where used | an ASN, an address | no | 64500, 203.0.113.9 |
| PPP or tunnel credentials, where used | a user name; a password or pre-shared key | the password or key | user `node7-wan`, a password |
| The modem's settings | the fields headquarters lists for its modem model (section 13) | per field | a frequency, a symbol rate, a satellite name |

A field the provider's format does not carry is absent, never guessed: "This sheet does not give
a DNS server" is a result. Whether an absent field blocks the bring-up is the bring-up template's
declaration (section 10), decided by headquarters in advance.

## 5. Node-scoped extraction

One document holds many nodes. The kit must take its own node's values and nothing else.

- **The node number comes from the kit's signed identity**, set at staging
  ([EDGE_ARCHITECTURE.md](EDGE_ARCHITECTURE.md)), never typed by the kit operator.
- **The parser profile states where node numbers appear** (a table column, a section heading, a
  row label). Extraction is confined to the **region** that belongs to this node: the row, or
  the section from its heading to the next node's heading.
- **Written forms are normalised to one form before matching.** First PHASE8_PLAN 11.7's
  Unicode step (NFKC, which folds fullwidth digits to ASCII, then the strip of Cf and Cc
  characters, each removal audited); then the profile's declared node forms (`7`, `07`, `N-007`,
  `Node 7`) reduced to one integer. **PHASE8_PLAN 11.7 does not state the second step**: it
  normalises characters, not values. That step is this note's (section 16, gap 2).
- **Matching is exact, with whole-number boundaries.** Node 7 never matches 17, 70, 7.1 or 107:
  after the declared prefix and leading zeros, the digits must equal the node number with no
  digit, decimal point or digit-continuing character on either side.
- **Zero matching regions, or more than one, is a refusal**, in plain words with a code to call
  in, never a guess: "This sheet has no section for node 7. Call headquarters with code
  BU-NODE-0." and "This sheet lists node 7 twice (pages 2 and 5). Call headquarters with code
  BU-NODE-2." This applies PHASE8_PLAN 11.2's rule (zero or several matches, code decides,
  whatever any model returned) to a document region; 11.2 itself names references resolved
  against NetBox and intent, and has code ask a clarifying question. On a kit the question is
  not the kit operator's to answer, so it becomes a refusal with a call-in code (section 16,
  gap 3).
- **Provenance is checked against the region:** every value's page and line must lie inside this
  node's region, or the value is refused. This binds the model fallback especially (section 6).
- **Extracted values are compared with the staged plan for this node** (the IPAM import's,
  [IPAM_IMPORT_DESIGN.md](IPAM_IMPORT_DESIGN.md)), and a mismatch is flagged before the kit
  operator is asked to confirm anything: "The sheet gives WAN gateway 203.0.113.9; headquarters
  planned 203.0.113.1. Call headquarters with code BU-PLAN-GW." Which source governs each field
  (the provider's sheet, or headquarters' plan) is declared per field in the bring-up template;
  a mismatch on a field the plan governs stops the standard change (section 10).
- **Headquarters runs the whole fleet in one pass:** at staging, NetOps loads one multi-node
  document and produces each node's proposed bring-up, each node's region found and checked the
  same way, for each kit to carry.
- **A kit keeps only its own node's confirmed values** and the source document's sha256, never
  the full multi-node document, so a lost kit exposes one node, not the fleet. Where a kit must
  load the multi-node document itself (a sheet issued in the field), the file is held encrypted
  for the bring-up only, under a key made for that bring-up, and the key is destroyed at confirm
  or abandon (erasing flash storage is not reliable; destroying the key is). The record keeps the
  sha256.

**The wrong thing that looks right here** is node 17's gateway proposed for node 7: every
validator passes, because node 17's values are as valid as node 7's. What makes it visible is
the whole-number match, the region check on every value, the plan comparison, and the highlight
in section 9 naming the node the region belongs to.

## 6. The local model as the fallback

For a provider format with no parser profile, a local model proposes where each value sits. It
is **local by necessity** (an offline kit has no route to a hosted model) and **by rule**
(classified content never reaches a cloud model; [EDGE_ARCHITECTURE.md](EDGE_ARCHITECTURE.md)
refuses any destination outside a marked network's enclave).

It is Phase 8's built-in model, under every Phase 8 rule:
- **US-origin only** (PHASE8_PLAN 10.2, DECIDED 2026-10-14): gpt-oss-20b, Gemma 4 26B MoE and
  E4B, Granite 4.0-H-Tiny and H-Small; no other origin, and no setting to add one.
- **llama.cpp's `llama-server`**, bound to 127.0.0.1 with no egress, reached through the
  OpenAI-compatible adapter (PHASE8_PLAN 10.3, DECIDED; 10.4's engine and delivery are still
  PROPOSED, pending the operator's decision 12).
- **The model file is imported at staging** (10.4's air-gapped path: a supplied file, its sha256
  and, for Granite, the publisher's signature checked), never downloaded by a kit.
- **One request at a time, CPU and memory capped, unloaded when idle** (10.6, PROPOSED). On a kit
  it is loaded for the extraction and unloaded before the deploy and the checks, so it never
  competes with the bring-up itself.
- **The model's files, and Mercury itself, need the organisation's authorisation** before use on
  such a network. That authorisation is the organisation's, outside this project.

### 6.1 Where it runs, and the kit hardware it needs

It runs **on the kit**, inside the kit's own Mercury instance; PHASE8_PLAN 10.1 places the model
on the NMAS host, and a kit's instance is its own NMAS host. The kit's hardware is therefore
sized for it, and **nothing about that hardware is measured yet.** The lab's host (PHASE8_PLAN
10.8) fits the small tier only, with speed unmeasured; a kit is a different machine.

**The measurement**, owed before any tier is offered on a kit (and listed under "Measurements
still owed"):
1. **Where:** a representative kit compute unit at headquarters staging, never a deployed kit;
   the lab may rehearse the method, and its numbers are never the kit's.
2. **The load:** the kit's whole stack running (Mercury, its NetBox, Prometheus, Loki, Grafana,
   as the edge design sizes them), and **the C8000v, if it runs on the same hardware**.
   PHASE8_PLAN 10.8 found a C8000v twin and a small-tier model do not both fit in 16 GiB; a kit
   whose router is a VM on the same unit has that collision permanently, and whether the kit's
   C8000v shares the unit is itself unmeasured.
3. **The method:** PHASE8_PLAN 10.5's hardware check: MemAvailable with the stack running,
   sampled over at least a day (10.8 used sysstat's 10-minute samples over nine days); the CPU's
   features (AVX2, AVX-512, AMX); its 30-second prompt and generation speed test. Then the
   extraction itself, timed, on each node region of the synthetic corpus at the profile's
   context, recording prompt tokens per region.
4. **The admission rule:** section 7's (PROPOSED): a tier is admitted only if MemAvailable stays
   at or above 20% of the unit's RAM with the model loaded; if no tier fits, the kit's model is
   "AI off" with the measured numbers shown, and every bring-up uses parser profiles or hand entry.

### 6.2 What it is given, and what it returns

- **It is given only text code has already scoped.** In the field, the fallback runs only on a
  document in which code finds exactly one region for this node and no other node's marker, by
  the organisation's node forms declared in the build standard. A multi-node document with no
  profile is refused on the kit ("This sheet covers several sites and headquarters has not set it
  up yet. Call headquarters with code BU-PROF-0."), because a model choosing a region in a
  document holding other nodes' values is the very error section 5 exists to prevent. At
  headquarters NetOps may run the model over a whole multi-node sample to **draft** a parser
  profile, accepted only by section 14's test, as PHASE8_PLAN's feature 10 drafts a template
  accepted only by round trip.
- **It is never asked for a secret field.** A secret field in a document with no profile is
  entered by the kit operator from the sheet in hand, masked as typed (section 12). The model
  never sees a value it would have to be trusted not to repeat.
- **Its output is locations, not trusted values:** for each schema field, the page and line (or
  table cell) where it reads the value, and the value it reads there, in a schema-constrained
  structure (PHASE8_PLAN 10.6's constrained decoding). **Code reads the value at the cited
  location from the text layer and compares it**; a value not found there, or a location outside
  the node's region, is refused. So the model's provenance is checked, never believed, which is
  11.3's PROPOSED detail (a `stated` field's words must occur in the source) made a requirement
  here.
- **The error contract** (PHASE8_PLAN section 4 and 11.4): `{"error": "could not parse"}` and
  `{"error": "ambiguous", "clarification_needed": ...}`, shown as plain sentences with a call-in
  code; code's own checks run whatever the model returned (11.2).

### 6.3 Its feature card (PROPOSED; PHASE8_PLAN section 3)

A feature without a complete card is not built (PHASE8_PLAN section 3). This one is not among
section 6's ten candidates, so it needs the operator's decision to join them:

| Field | Proposed |
|---|---|
| Problem | the time from a kit's arrival to its first verified link, and the typed-value errors, measured in a headquarters exercise with the synthetic corpus, without and with parser profiles |
| Deterministic alternative | the parser profile (section 3), which handles every format headquarters has taught; it falls short only for a format first seen in the field |
| Inputs | one node's region of the text layer, the schema, and its error contract; tokens measured on the corpus (section 4's minimum context times 1.5) |
| Pattern and compared fields | **Translator, floor 95%** (PHASE8_PLAN 11.1, 11.12): words in a document become a structure code checks. Compared over N=5 runs: every non-secret field's canonical value **and** its cited location, and the error contract's kind |
| Success metric | per-field exact match against the corpus's labelled values, and against real samples inside the secure environment (section 14); zero values outside the node's region reaching the confirm |
| Budgets | zero cost per token; the latency budget from the kit measurement (section 6.1), not section 6's 3 to 5 s, which are for interactive features |
| Observe mode | at headquarters, on formats that have a profile: the model runs beside the profile and agreement is measured against the deterministic answer |
| Kill criteria | per-field accuracy below target after the card's uses, or **one value from another node's region reaching the confirm** (zero tolerance, as features 4 and 7) |
| Owner | headquarters NetOps (the operator's decision 9 names owners) |

## 7. Phase 8's rules, applied

Each rule the brief names, with where PHASE8_PLAN states it. A rule PHASE8_PLAN does not state is
said so, and listed in section 16.

| Rule | PHASE8_PLAN | Applied here |
|---|---|---|
| The Translator pattern and its floor | 11.12 (patterns), 11.1 and section 7 (95%) | the card's pattern (6.3) |
| The consistency eval, N=5 | 11.1 (N a profile setting, default 5; structured fields only) | compared fields: every non-secret value and its location |
| Field provenance | 11.3: `stated` or `inferred`, with `source_words` from **the operator's request** | every value carries page and line (and region) in a **document**; a value with no location is not proposed. 11.3 does not state document locations (gap 1) |
| Input normalisation | 11.7: NFKC, Cf and Cc stripped, a cap per block, each removal audited | applied to the text layer before any prompt and before node matching; the value-level node forms are this note's (gap 2) |
| Deterministic ambiguity | 11.2: zero or several matches, code asks | applied to node regions, as a refusal with a call-in code (gap 3) |
| Deterministic validation by code, not the model | 2.1 (AI proposes, deterministic code decides; every output passes a person's gates) | section 8's validators |
| No model approves anything | 2.5 (approval only the GUI's confirm by hash), 2.6, 11.6, 11.12's departures | the kit operator's confirmation and the deploy's confirm by hash (sections 9, 10) |
| Masking before every prompt | section 4 (IBN_DESIGN section 10's standards) | secret fields never reach the model (6.2); `redact.py`'s shapes are configuration lines, not documents (section 12) |
| Every prompt and response recorded | section 4 | recorded in the kit's History, inheriting the document's marking; on a marked network those records never leave the enclave |
| Context freshness | 11.10 | at confirm: the document's sha256, the parser profile's version and the staged plan's commit re-checked; any moved, validation re-runs |
| The local model and its origin | 10.2 (DECIDED), 10.4 (PROPOSED) | section 6 |

## 8. Deterministic validation

Every proposed value, from a profile, the model or the kit operator's hand, passes the same
validators, in code, with Python's `ipaddress`, before it is shown as ready:

- the WAN address is a host address, not the network or broadcast address of its prefix;
- the gateway lies inside the WAN subnet and is not the WAN address itself;
- the mask is among those headquarters permits for this provider (for example /29 or /30);
- the VLAN tag is within the bring-up template's allowed set;
- the BGP ASN, where used, is the one headquarters lists for this provider, and the neighbour is
  the gateway or inside the WAN subnet, as the template declares;
- DNS servers are addresses, and where the template lists permitted resolvers, among them;
- every value is printable ASCII (the rule `hostvars.assert_printable()` holds for intent).

Each refusal names the comparison and both operands, in plain words for the kit operator and
exactly for headquarters: "The gateway 203.0.113.17 is not inside the WAN network
203.0.113.8/29. Check the sheet, or call headquarters with code BU-GW-NET."

## 9. The kit operator's confirmation

The kit operator confirms each value against its highlighted source, side by side, in plain words:

> **WAN gateway 203.0.113.9**, read from page 2, the line "Default Gateway", in the section for
> node 7. Does that match your sheet?  **Yes** / **No, type it in**

- The left pane is the document's page with the line highlighted and the node's region outlined
  and labelled ("Node 7"); the right pane is the value and its check results.
- A value the kit operator rejects is typed by hand and validated the same way (section 8); the
  record says it was typed, by whom, and that the sheet's reading was rejected.
- A secret value is never drawn: its line is highlighted with the value masked, in the text layer
  and, for a scan, by blacking out its box (section 12). The kit operator confirms that it was
  found where they see it on their own sheet.
- Every value is shown, inferred or not; there is no "accept all". A value from the model
  fallback is drawn as such ("read without a headquarters set-up for this sheet").

This is a confirmation of facts, not an approval of a change: the change is confirmed by hash at
its own preview (section 10), as a verified person (PHASE8_PLAN 2.5). On an offline kit, "a
verified person" needs the local authentication [EDGE_ARCHITECTURE.md](EDGE_ARCHITECTURE.md) and
[OFFLINE_OPERATION.md](OFFLINE_OPERATION.md) design; today `modules/identity.py` `identify()`
verifies an access proxy's assertion, which an offline kit cannot reach.

## 10. From values to a change

The confirmed values fill **headquarters' signed bring-up template**, producing a proposed intent
change: staged host_vars (`hostvars.STAGING_REL`) for the devices the template names, committed
only through the change's confirm, through `hostvars.write_committed()` and its secret refusal.
The template declares, per field, its bounds and which source governs (the sheet or the plan).

- **Inside the template's bounds, it is a standard change:** headquarters-signed, bounded inputs,
  runnable offline ([EDGE_ARCHITECTURE.md](EDGE_ARCHITECTURE.md), change kinds).
- **Outside them, it becomes an emergency change:** the kit operator states a reason, it runs with
  local verify and rollback, and it is marked for headquarters review on reconnect.

The template's approval is today's (`approval.template_fingerprint()`, the import closure) plus
headquarters' signature on the build standard, verified offline with headquarters' public key (an
offline prerequisite in the edge design). Neither the model nor the extraction can change the
template or its bounds; they supply values into it.

Which device carries the WAN (the C8000v, or the firewall) is the bring-up template's statement,
made by headquarters, not this design's. PAN-OS is not a Mercury platform today; until the edge
design adds it, a value bound for the firewall is shown on the checklist (as the modem's are,
section 13).

## 11. Then the guided bring-up applies it

The edge design's guided bring-up (power, modem lock, link, routing, tunnel to headquarters)
runs the change:

1. **A plain-language preview** built on `preview_confirm.build()`'s six parts: what will happen
   ("Set the WAN on the router to 203.0.113.10, gateway 203.0.113.9"), what will not, the exact
   program masked, and the confirm.
2. **The deploy**, through the pipeline every deploy runs, verified, with rollback that runs on
   the kit (the edge design's device-side rollback, since the link being configured is the only
   route out).
3. **Checks that read the real network**, each through an allowlisted read
   (`readonly_commands.py`): ping the gateway; resolve a name through the configured DNS; reach
   headquarters. Each is a **PASS** line or a plain next step ("The router cannot reach the
   gateway. Check the modem shows LOCK, then press Check again. If it still fails, call
   headquarters with code BU-PING-GW.").

## 12. Secrets and source documents

- **Secrets in provider sheets** (PPP passwords, pre-shared keys) are stored as references and
  masked everywhere, as device credentials are: the value goes to
  `credentials.set_template_secret(credentials.template_secret_key(list_name, hostname, ref),
  value)`, intent carries the reference in `secret_refs`, and the template reads it through
  `secret()`. `hostvars.assert_no_secret_values()` refuses a value that reaches intent.
- **Masking a document needs document-shaped positions.** `redact.py`'s positional table knows
  configuration lines, and value matching stops below 8 characters (`MIN_REDACTABLE`), so a
  short pre-shared key on a sheet would be masked by neither. A parser profile's field marked
  secret **is** a position: the engine masks that span in every text layer, preview, highlight
  and record it draws. While the operation holds a value of 8 characters or more, it runs inside
  `redact.transient_secret`, so a log line or error that echoes it is masked too. A short value
  is protected only by no path formatting it into a message, the limit `transient_secret`'s own
  comment states.
- **The model never extracts a secret field** (section 6.2).
- **Source documents are never committed.** They are stored encrypted with restricted access at
  headquarters, held on a kit only as section 5 says, and appear in records and commits only by
  sha256. The commit that records a bring-up names the document's sha256, the parser profile's
  version, and the node; never a value from another node.
- **Extracted values inherit the document's classification** (the edge design's rule): once in
  intent they are in goldens and commits, so a marked network's repository stays in its enclave.

## 13. The modem

The satellite modem is not a Mercury platform. Its values (the schema's modem fields, which
headquarters lists for its modem model) are shown as a **checklist** for the kit operator to
enter on the modem, each with its source highlight, and ticked off one by one. The guided
bring-up's "modem lock" step then asks a plain question ("Does the modem show LOCK?") until the
modem can be read.

Managing modems directly is a later platform. The likely candidates are **vendor APIs or SNMP
where the modem offers them**; a modem with only a web page or a front panel stays a checklist.
The repository names no modem product, and this design does not either: which modems the kits
carry, and which interface each offers, is a measurement owed at headquarters.

## 14. Testing without real documents

- **A synthetic corpus in this public repository:** invented multi-node sheets with invented
  values (documentation addresses and ASNs only), modelled on public formats such as commercial
  ISP handoff letters and published VSAT activation forms, in general terms only. It includes:
  - scans (rendered and degraded), odd layouts, and missing fields;
  - near-miss nodes side by side (7, 17, 70, 107), and written forms (7, 07, N-007, Node 7);
  - a node listed twice, and a missing node;
  - a secret field shorter than 8 characters;
  - planted hidden-instruction text (PHASE8_PLAN 11.7's cases) inside a document.
- **In CI, recorded responses only** (PHASE8_PLAN section 4): the parser engine on the corpus, and
  the model fallback's recorded N runs per case, scored for accuracy, region and consistency.
- **"Test this profile"**, an action on a parser profile's page at headquarters, run inside the
  secure environment against a local folder of real samples, as a job. It reports per-field
  accuracy, node-scoping correctness and the consistency eval, and records **only the numbers
  and the files' sha256**, never a document, a value or a line of text.
- **PHASE8_PLAN's eval rules meet the constraint here** (section 16, gaps 5 and 6): section 7
  asks for at least 10 real cases per feature, and 11.4 for few-shot examples from real history.
  Real cases exist only inside the secure environment; this note proposes that the real-case
  minimum is met by "Test this profile" there, its numbers recorded, and that shipped prompts
  carry synthetic examples only.

## 15. Optional: proposing an IPAM column mapping

At headquarters the same engine may **propose** a column mapping for an unfamiliar IPAM
spreadsheet ([IPAM_IMPORT_DESIGN.md](IPAM_IMPORT_DESIGN.md)), for NetOps to confirm column by
column. A proposal only: the import's own validation and preview decide, and the mapping profile
is signed by a person.

## 16. Gaps in PHASE8_PLAN this design depends on

Rules the brief names, or this design needs, that PHASE8_PLAN does not state:

1. **Document provenance.** 11.3's provenance is `stated` or `inferred` with words from the
   operator's request; it says nothing of a page, a line or a region in a document.
2. **Value-level normalisation.** 11.7 normalises characters (NFKC, Cf and Cc, caps); it does not
   normalise written forms of a value such as a node number.
3. **Ambiguity in a document.** 11.2 resolves references against NetBox and committed intent, and
   code asks a question; a region in a document, and a refusal with a call-in code for a person
   who may not decide, are not stated.
4. **A card for this feature.** It is not among section 6's candidates; its pattern (Translator)
   is this note's proposal, not a placement the operator has made.
5. **Real cases that may not leave a secure environment.** Section 7's "at least 10 real cases per
   feature" and section 4's recorded responses in CI assume real cases can be recorded in the
   repository.
6. **Few-shot from real history.** Section 4 and 11.4 take examples from the config repository's
   history; for this feature they would be classified.
7. **Document and image input.** PHASE8_PLAN names no document, scan or OCR input.
8. **A kit's hardware and latency.** 10.5's tiers and 10.8's measurement are the lab's NMAS host;
   section 6's latency budgets are for interactive features.
9. **Approval by a verified person offline.** 2.6 takes identity only from the verified access
   assertion, which an offline kit cannot reach ([OFFLINE_OPERATION.md](OFFLINE_OPERATION.md)).

## What it touches

Proposed; none of it exists.

- **New:** the extraction engine (text layer with coordinates, the anchor kinds, the node locator,
  node-form normalisation, the region check); the parser profile format and its signing; the
  schema in the build standard; the teaching screen and "Test this profile" (boards first, each
  with its manual page under `docs/manual/`); the bring-up template's per-field bounds and
  governing source; the confirmation screen (section 9); the modem checklist; the Phase 8 card
  and its eval set; the synthetic corpus.
- **Existing, extended:** `modules/redact.py` (a document-position mask beside `_POSITIONAL`);
  `modules/credentials.py` (`set_template_secret` for extracted secrets, unchanged in shape);
  `modules/nsot/hostvars.py` (staged then committed intent, unchanged rules);
  `modules/nsot/templates_repo.py` and `modules/nsot/approval.py` (the bring-up template, its
  bounds beside the closure); `modules/preview_confirm.py` (a bring-up preview);
  `modules/route_gates.py` and `modules/invalidation.py` (each new mutating route);
  `modules/operation_stages.py` (the bring-up's five stages); `modules/nsot/repo.py` `commit()`
  (the record, with the document's sha256); `tests/signed_off_screens.py` (each new screen).
- **Dependencies to add:** a PDF reader, a Word reader and an OCR engine, each a new third-party
  licence and so the operator's decision.

## Tests it needs

Each shown able to fail, with a planted case:

- **Whole-number node matching:** 7 against 17, 70, 7.1, 107, 07, N-007, Node 7 and fullwidth ７;
  planted: a substring matcher passes 17 and fails the test.
- **Zero or two regions refuse**, naming the code, whatever a recorded model output says;
  planted: a resolver that takes the first region.
- **Every value's location lies inside the node's region, and the value occurs there;** planted:
  a recorded model output citing node 17's line.
- **The plan comparison** flags a mismatch before the confirmation screen is drawn.
- **Validators:** the gateway outside the subnet, a disallowed mask, a VLAN outside the set, the
  network address as WAN address; each refused naming both operands.
- **Secrets:** a secret field never appears in a prompt, a preview, a highlight, a record or a
  log, including one shorter than 8 characters; committed intent holds only the reference.
- **The model is never asked for a secret field,** and a multi-node document with no profile is
  refused on a kit.
- **Consistency:** the card's compared fields over N recorded runs, with PHASE8_PLAN 11.1's
  planted cases.
- **Context freshness:** a document, profile or plan changed between preview and confirm makes
  validation re-run.
- **A kit keeps no multi-node document:** after confirm, no file and no key remain; the record
  holds the sha256.
- **"Test this profile" records no text:** its stored result holds numbers and hashes only;
  planted: a result carrying a line of a sample.
- **Publication:** the corpus holds only documentation addresses and ASNs
  (`tests/test_nothing_personal_is_published.py` already scans every tracked file).

## What it must not break

- **Merge-only deploys, preview and confirm by hash, verify and rollback** for every other
  operation; the bring-up is one more operation through the same pipeline, never a side path.
- **Committed intent holds no secret value** (`hostvars.assert_no_secret_values()`); secret keys
  are built only by `template_secret_key()`.
- **Offline parity** (PHASE8_PLAN 2.3): with the model off or absent, bring-up works through
  parser profiles or hand entry, and says the model is off.
- **A headquarters network, and the lab, behave as now:** no provider document, no node number,
  no change.
- **Masking:** the document-position mask is added beside `redact.py`'s existing shapes, never
  replacing or narrowing them.
- **The charter's sources of truth:** the confirmed WAN values reach NetBox only through the IPAM
  import's write path, never a second writer.

## Measurements still owed

None taken now. Each with its method and where it runs:

1. **Kit hardware for the local model** (section 6.1): PHASE8_PLAN 10.5's check (MemAvailable with
   the kit's whole stack and, if co-hosted, its C8000v running, sampled over at least a day; CPU
   features; the 30-second speed test), then the timed extraction of the corpus's node regions;
   on a representative kit compute unit at headquarters staging.
2. **Whether a kit's C8000v runs on the same unit as its Mercury:** read from the kit's build at
   headquarters.
3. **Tokens per node region,** for the card's context budget (PHASE8_PLAN section 4, the minimum
   context times 1.5) against section 7's 8k profile context (PROPOSED): the eval's context-removal run on the
   synthetic corpus, in CI's recorded form and live on headquarters' host.
4. **Per-field accuracy, node-scoping correctness and consistency on real documents:** "Test this
   profile" inside the secure environment, numbers and hashes only.
5. **OCR accuracy on scans:** on the corpus's degraded scans in CI; on real scans inside the
   secure environment by the same action.
6. **Today's bring-up time and typed-value errors without this** (the card's Problem): a timed
   headquarters exercise with the synthetic corpus.
7. **Which modems the kits carry, and whether each offers a vendor API or SNMP:** read at
   headquarters from the kits' build and the modems' own documentation.

## Dependencies on the other four notes

- **[EDGE_ARCHITECTURE.md](EDGE_ARCHITECTURE.md), required:** the kit's own Mercury instance; its
  signed node number; the build standard and its distribution (parser profiles, the schema, the
  bring-up template, the model file); standard and emergency changes; the guided bring-up and the
  kit operator's plain-language mode with call-in codes; device-side rollback; classification
  marking and the enclave rule; the offline prerequisites (signature verification, local
  authentication).
- **[IPAM_IMPORT_DESIGN.md](IPAM_IMPORT_DESIGN.md), required:** the staged plan per node that
  extracted values are compared with; the write path by which confirmed values reach NetBox; the
  mapping profiles section 15 may propose.
- **[SITES_DESIGN.md](SITES_DESIGN.md), indirect:** the headquarters instance that stages many
  kits uses sites (and per-site VRFs where identical kits repeat addressing); a kit's own instance
  is one network.
- **[FLOWS_DESIGN.md](FLOWS_DESIGN.md), none required:** if the build standard's bring-up
  template carries sampled flow export for satellite sites, it arrives through the template, not
  this design.
- **[OFFLINE_OPERATION.md](OFFLINE_OPERATION.md)** (the sixth note): local identity for a verified
  person on a kit, and installing the model file and the release with no internet.
- **Phase 8 ([PHASE8_PLAN.md](PHASE8_PLAN.md)):** the gateway, the built-in local model (section
  10), the eval harness and the card (sections 3 and 4), and section 11's rules, with the gaps in
  section 16 decided first.
