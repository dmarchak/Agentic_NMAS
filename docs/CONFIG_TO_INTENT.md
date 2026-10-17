# Config to intent: adding a configuration block a partner sends (a FUTURE design; not built)

**FUTURE, post-cutover (Phase 8 or later); not Phase 7 work.** Decided by the operator on
2026-10-17 and registered as C1146. Written that day from the operator's brief and from the code
at that date, in the form of the 2026-10-16 design notes ([BRINGUP_FROM_DOCUMENTS.md](BRINGUP_FROM_DOCUMENTS.md)
and the others). Documents only: nothing here is code. Under the charter
([MERCURY_CHARTER.md](MERCURY_CHARTER.md), "New findings") it is FUTURE: worth doing, not now.

## 1. The need

Agencies and partners that connect to this network send their side of the connection as
**configuration blocks**: a tunnel interface, BGP neighbours, crypto (IKE and IPsec), ACLs and
route maps, in their own device's syntax. An engineer then has to get those lines onto a device.

Mercury accepts no raw configuration. A device changes only by a deploy of rendered intent:
preview, confirm by hash, apply holding the device, verify, rollback, record. Today the only way
to carry a partner's block is for an engineer to translate it into a `host_vars` document by hand
in the Intent tab. That is slow, and every hand-typed value is a chance of error. The other route
an engineer would reach for is a terminal, which Mercury removed on purpose.

This feature closes that gap without opening a raw-config path. **The block becomes intent**:
it is parsed into the device's `host_vars` by the extractor Mercury already uses, then reviewed
and committed like any other intent edit. A deploy then sends it like any other change.

## 2. What exists today, and what this builds on

Read 2026-10-17, in this repository:

- **The extractor.** `modules/nsot/parsers/base.py` (`BaseParser`, with `cisco_ios.py` and
  `cisco_iosxe.py`) turns a running config into `host_vars`.
  - It splits the config into top-level blocks (`split_blocks`) and hands each to a handler.
    Handlers exist for interfaces, BGP, OSPF, static routes, named ACLs, users, SNMP and logging,
    among others.
  - Anything with no handler goes into `unmodeled`, verbatim and with its section context.
    Nothing is dropped. Crypto (IKE and IPsec) has no handler today, so it would land there.
  - Seeding uses this same extractor (`modules/nsot/seed.py`).
- **Unmodelled lines.**
  - They are carried in intent, rendered back by every template (`_common.j2`'s
    `unmodeled_block`) and passed through `resolve_secrets`.
  - They are gated by `unmodeled_ack`: a committed list that must equal the unmodelled set
    exactly (`render_artifact.acknowledgement_is_complete`).
  - A person acknowledges them with `intent_edit.acknowledge`. So "carried as reviewed extra
    lines" already exists, and it is content-bound and reviewable in git.
- **One path for intent edits** (`modules/nsot/intent_edit.py`):
  - `validate`, then `preview` (two diffs: against the committed render and against the device's
    capture), then `commit`.
  - `commit` holds the repository lock, is bound to the version opened, takes the person's
    summary as its reason, and makes one commit as that person.
  - The v2 Intent tab (`routes/intent_v2.py`) is its one caller.
- **Committed intent never holds a secret value.** `hostvars.write_committed_text` calls
  `assert_no_secret_values`.
  - That check matches stored values only, by whole token, and only values of 8 characters or
    more (`MIN_CHECKABLE_SECRET`).
  - A value the store has never seen (a partner's new pre-shared key) is NOT caught by it. The
    extractor must move it out first.
- **Secrets as references.** `hostvars.store_secrets` moves extracted secret values into the
  credential store under `credentials.template_secret_key(list, host, ref)`. Intent keeps only
  the reference, and the template's `resolve_secrets` puts the value back at render time.
- **Masking by position.** `modules/redact.py` (`redact_text`) masks secrets by their position
  in a line (keys, passwords, community strings, pre-shared keys), and also by value.
- **The render-and-reproduce check.** `modules/nsot/roundtrip.py` renders the template from
  `host_vars` and compares the result with the source configuration, section by section. Order
  within a section counts, because a reordered ACL is a different ACL.

## 3. The shape

**"Add from configuration…"**, a control in the device's Intent tab, beside the editor (one
device at a time). A person picks the device by opening its page; the block is never applied to
more than that device.

1. **Paste.** The person pastes the block, and Mercury checks it before anything else:
   - printable ASCII only (`assert_printable`'s rule);
   - a bounded size;
   - and the device's dialect is the one the paste is parsed as.

   The paste itself is never stored. Only what the person commits is, and that holds no secret
   value (step 4).
2. **Parse with the existing extractor.** The block is split and parsed by the device's own
   parser into a partial `host_vars`. That is merged into the device's committed intent, with
   the same merge rules seeding uses: a new interface, neighbour or ACL is added; an existing one
   with the same key is a CONFLICT, shown and never overwritten in silence.
3. **Show the intent diff, and every line the template cannot render back.** The preview has
   three parts:
   - **What intent gains:** the `host_vars` diff, as the Intent tab draws it now.
   - **Not modelled:** each line the parser put in `unmodeled`, with its section. For each, the
     person chooses:
     - **refuse** it, so it is left out and named in the record;
     - or **carry it** as a reviewed extra line, which adds it to `unmodeled_ack` with the
       person's reason, the mechanism C481 built.
     Nothing is carried by default.
   - **What a deploy would send:** the render of the merged intent against the device's capture
     (`intent_edit.preview`'s `vs_device`), so the person sees the exact program before
     committing.
4. **Detect secrets, mask them, offer them to the credential store; never commit them.**
   - Every line goes through `redact_text`'s positional rules before it is drawn. The preview
     shows each secret masked, with its kind (pre-shared key, key string, password, community).
   - Each detected secret is offered to the credential store as a template secret for this
     device: Mercury makes its reference, and intent keeps only the reference.
   - A secret the person does not store is a refusal at commit, naming the line. It is never
     committed in the clear.
   - The positional rules decide what is a secret. A line the rules do not recognise but which
     resembles a key (a long high-entropy token after `key`, `secret`, `password` or
     `pre-shared`) is REFUSED with its line named, never allowed by resemblance.
5. **Render and reproduce.** The merged intent is rendered and compared with the pasted block's
   own lines, section by section, using `roundtrip`. Each pasted line is either reproduced by the
   render, or listed under not modelled with the person's choice, or refused. A pasted line that
   is none of these is a refusal: the feature never drops a line in silence.
6. **Commit through the normal intent path.** `intent_edit.commit`:
   - bound to the version opened;
   - the person's reason (the agency and the change reference) as the summary;
   - one commit as the person, with a trailer naming the source (`Source: config-to-intent`);
   - the approval gate where the network's template or change policy requires one.

   **The commit changes intent only. Nothing reaches the device.**
7. **The deploy sends it.** A normal deploy, with its preview of the exact program (masked),
   confirm by hash, hold, verify scaled to what the program touches, rollback on failure and
   record. Nothing about deploying changes.

## 4. What it must never do (stated as what makes it visible)

- **Never a raw-config path.** The pasted text reaches the device only as rendered intent. A test
  can hold this: no route that takes the paste calls the sender, and the feature's only write is
  `intent_edit.commit`.
- **Never a secret in git.** Covered by step 4. A planted pre-shared key in a test paste must end
  as a reference in the commit, and a key the store does not take must refuse the commit.
- **Never a silent drop.** Covered by step 5. The count of lines pasted equals the lines
  reproduced plus the lines carried plus the lines refused, and the preview shows all three
  counts.
- **Never another device.** The block is for the device whose page it was pasted on, and its
  hostname and interfaces are checked against that device's intent. A block naming another
  hostname is refused.
- **Never a change to an account.** A `username` line in a paste follows the deploy rule that a
  deploy may add an account and never change one.

## 5. Open questions, decided before building

1. **Modelling crypto.** IKE and IPsec have no handler today, so a partner's crypto would only
   ever be carried, not modelled. Should the parsers gain crypto handlers (keyring, IKEv2
   profile and proposal, IPsec profile, tunnel protection) first, so that intent models what
   partners send most? Measure first: in the configurations partners actually send, what share of
   the lines fall into `unmodeled`?
2. **Another vendor's syntax.** A partner may send non-Cisco configuration. The first version
   accepts only the device's own dialect and refuses anything else by name. Translating another
   vendor's syntax is out of scope.
3. **Approval.** Should a configuration added this way always need a second person (the approval
   queue), whatever the network's policy, because it comes from outside the organisation?

## 6. Size, and where it fits

**Size: about M.** One preview card and one commit path on top of `intent_edit`. Most of the
risk is in step 4's secret detection and step 5's accounting, so both are tested with planted
partner blocks (documentation addresses, invented keys).

**Dependencies:**
- Phase 7's cutover, since the Intent tab is v2's.
- None from Phase 8. The responder of [PHASE8_PLAN.md](PHASE8_PLAN.md) may later propose a block
  this way, but it can never confirm one.

Register: C1146 (FUTURE, the operator's decision, 2026-10-17). docs/PHASE7_BURNDOWN.md section
4 lists it.
