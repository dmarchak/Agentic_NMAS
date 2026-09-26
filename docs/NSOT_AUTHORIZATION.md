# Authorization: who may do what

**DECIDED 2026-09-26. Not built.** Recorded now because it shapes Stage 7.
Every screen that draws a gated control has to know who may press it, and
retrofitting that after the screens exist means redrawing them.

The operator asked for the roles to be argued rather than taken from their
first sketch. They differ from it in four places, each marked **(differs)**.

## 1. Where we are (measured 2026-09-26)

- **Authentication.** Cloudflare Access issues a signed JWT, and
  `modules/identity.py` verifies it: RS256, audience, issuer, and a trusted
  raw-socket peer. Nothing else is believed.
- **Attribution.** Since P.3 step 1, every mutating endpoint declares a gate
  kind in `modules/route_gates.py`, and routes record the verified actor.
- **Authorization is two answers today:**
  - **a person may do every kind;**
  - **a service may do none** of the person-required kinds, except the
    operations named in `service_allowed_operations`, which starts empty.
- **The gates themselves are host-side only.** Measured: none of the five
  web paths that write settings can write a `require_*`, `cf_access_*` or
  `service_allowed_operations` key.
  - `/settings/integrations/general` and `POST /settings` are allowlists.
  - `save_integration` writes only the integration's declared keys; its
    `candidate.update(...)` is validation only.
  - The NetBox master switch and `tftp_server_ip` are single named keys.

  This matters for where a role map lives (section 6).
- **Without Cloudflare, the tool is read-only.** Verification fetches keys
  from `https://<team>.cloudflareaccess.com/cdn-cgi/access/certs`. On an
  air-gapped network that fails, the outcome is `verifier_unavailable`, and
  every gated route refuses. That is fail-closed and correct. It is also why
  option (b) below is not hypothetical for the operator's coursework.

## 2. The mechanism

**Design against one interface: a verified identity carrying a set of GROUP
names.** Where the groups come from is a separate, replaceable part.

- **(a) Cloudflare Access groups, first.** No new service and no user store.
  The gate table is already the enforcement point.
  **Unverified, and to be measured before building:** whether the
  application token for a self-hosted app actually carries group claims. My
  understanding is that it does not by default, and that groups come from
  Access's identity endpoint or from configured custom claims. Measure it by
  decoding the operator's own assertion and printing its claim KEYS, never
  their values. If groups are absent from the token, (a) needs one identity
  lookup per session, cached, which is a design point and not a blocker.
- **(b) OIDC against an IdP we run** (Authentik or Keycloak) for a network
  without Cloudflare. The app becomes a relying party and validates tokens
  itself. Same interface: verified identity plus groups. Nothing in the role
  model changes.
- **(c) A user table in the app: REJECTED.** It means owning passwords,
  resets, sessions and MFA, all solved worse than an IdP solves them. It is
  also a second identity source that will disagree with Access. That is the
  project's two-owners-of-one-fact rule, applied to people.
- **Also rejected: authorization as per-path Access policies at the edge.**
  It would be a second copy of the gate table, kept in Cloudflare, that
  drifts from the code. The app could not draw screens from it. And it cannot
  express separation of duties, which is per artifact (section 5).

## 3. The finding that changes the mapping: `approve` is two acts

The gate kinds were chosen for AUDIT meaning, and `approve` covers both
AUTHORING and APPROVING. Measured from the table: 23 endpoints, including
`templates.write_template` (editing a template) and `templates.approve`
(approving it). **Any role granted `approve` could edit a template and
approve its own edit.** No role map built on the current kinds can express
separation of duties.

**So the kind splits** (a gate-table change, cheap, whenever this is built):

| New kind | Endpoints (today's `approve`) | The act |
|---|---|---|
| **`author`** | template write, bindings, intent commit, edit, revert and bulk apply, onboarding create, the three NetBox import/remove applies, git commit, refresh hostnames | proposes what the network or the source of truth should be |
| **`approve`** | the approval queue (approve, approve all, reject), template approve and revoke, freshness authorisation, rollback retry, golden baselines (Save All, auto-create), the two Jenkins callbacks until P.4 | accepts something as correct, or lets it past a gate |

Golden baselines sit under `approve` because a golden is the approved record:
Save All declares the device's observed state the standard that a restore
re-applies.

## 4. The roles

A person's permitted kinds are the union of their roles, plus their grants.

| Role | Kinds | Who it is for |
|---|---|---|
| **viewer** | none (GETs and `not_device`) | anyone who needs to see; a reviewer |
| **operator** | `author` + `confirm` | the network engineer (NSOT_TASKS.md's user) |
| **approver** | `approve` | whoever signs off templates, queue items, exceptions |
| **administrator** | `configure` | whoever runs the tool itself |

**Grants, per named person, never part of a role:** `reveal`, `break_glass`,
`publish_remote`.

The reasoning:

- **viewer includes previews and plans.** A plan sends nothing, and reading
  what a change would do is how a reviewer reviews. Everything is masked. The
  `not_device` routes also include checks the schedule runs anyway (drift
  now, an inventory refresh), and those pass the autonomy test: the worst
  outcome is that it happened earlier than scheduled.
- **operator is `author` AND `confirm`. (differs: the sketch had `confirm`
  only.)** In this model a change IS an intent commit followed by a confirmed
  deploy. An operator who could confirm but not author could only deploy
  what someone else wrote. That is maker-checker implemented by role, and
  section 5 argues it belongs per change, not per role. Splitting them by
  role would also make a one-person team unable to work at all.
- **approver is `approve` only**, and it does not include `author`. Holding
  both is two roles, granted deliberately.
- **administrator is `configure` only. (differs: an administrator does not
  implicitly deploy or approve.)** Running the tool and changing the network
  are different trusts. An administrator also **cannot** change gates or the
  role map, because those are host-side (section 6). Without that,
  `configure` would be root.
- **reveal, break_glass and publish_remote are grants. (differs:
  `publish_remote` added; the sketch did not place it.)**
  - `reveal` exposes a secret, and its blast radius is the credential.
  - `break_glass` bypasses every guard this tool has, and its use is an
    incident.
  - `publish_remote` decides that a third party holds the network's history,
    credential hashes included. It is a trust decision about somewhere else.

  Each belongs to named people rather than arriving with a job title.
- **Services keep operation-level grants** (`service_allowed_operations`),
  which are narrower than roles, and are never approvers
  (`require_person_for_approve`).
- **The AI agent is an author-only principal**, per decision 1 of the feature
  audit. It proposes as ordinary plans and never confirms or approves. Under
  section 5 it is a maker whose checker is always a person.

## 5. Separation of duties: yes, but per ARTIFACT, not by role

**The operator's question: should the person who confirms a deploy be able to
approve the template it uses?**

**That separation buys little. The one that matters is between the AUTHOR of
a revision and its APPROVER.**

- **Template approval (scheme 3, P.5) is a claim about template TEXT**,
  across a platform. The deploy confirm is a claim about ONE program on ONE
  device, computed from intent through that template, and shown line by line
  to the person confirming. The dangerous part, what reaches the device, is
  already in front of the confirmer. Forbidding approver-also-confirms adds
  nothing the author-versus-approver rule does not, and makes a
  single-operator install impossible.
- **Four eyes on the same artifact is what change control means.** The person
  who wrote template revision X may not approve revision X. That rule is
  per artifact, so it is enforced from ATTRIBUTION: the verified author of
  the commits that produced the revision, against the verified approver.
  Roles cannot express it, because the same person is rightly an author on
  Monday and an approver on Tuesday.
- **The classic maker-checker, intent author versus deploy confirmer, is a
  POLICY per install.** It is **off by default**, reproducing today and a
  one-person lab, and is turned on for a team. When on, a confirm refuses if
  the verified author of any intent commit being deployed is the confirmer,
  naming both.

**It depends on D10, and fails closed on unverified history.** A rule of
"author ≠ approver" checked against `Actor: dustin`, typed by hand, is
decoration. So separation of duties reads only `Actor-Verified: access` (P.3
step 10). A revision whose author is not verified cannot be shown to be
someone else's, so under the policy its approval REFUSES with that reason.
Its remedy is a re-commit by a verified author. Treating an unknown author
as "not you" would be the empty-allowlist-means-everyone error.

## 6. Defaults and where the map lives

- **`authorization_mode`: `any_person` (the default) or `roles`.**
  - `any_person` reproduces today, and the posture panel states it as a named
    state: *"every verified person may do every action"*, so the absence of
    roles is visible rather than implied.
  - In `roles` mode, a person with no mapped group is a viewer, and **an empty
    map means nobody mutates.** An empty allowlist must never mean everyone:
    the peer-list lesson, where a blank `cf_access_trusted_peers` trusted
    every peer.
- **The mode, the group-to-role map, the grants and the separation-of-duties
  policy are all HOST-SIDE**, file-only like the gates, and shown read-only on
  the posture panel with their origin. If a browser session with `configure`
  could edit them, administrator would be every role.

## 7. What Stage 7 must do NOW, so nothing is redrawn later

1. **Every gated control is drawn from `may`, the server's answer**, never
   from a client-side guess at a role. `GET /identity/status` already reports
   `may` per action, computed by the same function the gate calls. Stage 7
   adds the per-screen form of it to the payloads its controls render.
2. **A control the caller may not use is drawn DISABLED, WITH THE REASON AND
   WHO CAN**, never hidden. For example: *"Approving a template needs the
   approver role. You are an operator."*
   - Hiding makes a state unanswerable: a viewer on a deploy screen needs to
     see that Approve exists and has not been pressed.
   - A greyed control that does not say why is the defect the posture panel
     already names.
   - This includes the terminal: *"Break-glass: not granted to you."*
3. **Approval screens show the separation-of-duties state** when the policy
   is on: *"You authored this revision. Another person must approve it."*
4. **The status bar shows who you are, your roles and your grants.**
5. **Until this is built, the mode is `any_person`.** Every control is
   enabled for a person, and the drawing code is the same one that will draw
   the disabled state, so nothing is redrawn when roles arrive.

## 8. Build order (not scheduled)

1. Split `approve` into `author` and `approve` in the gate table. This is
   independent and cheap, and could land any time after P.3.
2. Measure whether Access tokens carry groups (section 2).
3. Build `authorization_mode`, the map and the grants, host-side; make `may()`
   consult them; show them on the posture panel.
4. Separation of duties, after D10's trailer has been written for long enough
   to cover the revisions it would judge.
