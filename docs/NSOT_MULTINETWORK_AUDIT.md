# Multi-network audit — findings

Queued item (3), plus what it forced about item (2). Everything below is
**measured**, not read. Nothing is fixed yet.

The audit question: *if this installation manages two networks, what silently
goes to the wrong one?*

---

## A. The credential store keys secrets by device name alone — global, one file

`modules/credentials.py` stores template secrets in **one installation-wide
file**, `data/credential_profiles.json`, under the key `<hostname>:<ref>` —
built in `hostvars.store_secrets()` as `f"{hostname}:{ref}"`. There is no list,
slug, or site component.

Proven with two lists that each contain a device called `r1`:

```
list 'campus' extracts r1  -> stored 'r1:snmp_community_ro' = COMMUNITY-NET-A
list 'branch' extracts r1  -> stored 'r1:snmp_community_ro' = COMMUNITY-NET-B
keys in the store: ['r1:snmp_community_ro']
COLLISION: yes — the second list overwrote the first
campus's r1 now resolves to: COMMUNITY-NET-B
```

**Consequence.** Onboarding the second network silently repoints the first
network's secret. `hydrate_secrets()` then renders campus's config with
branch's community, `assert_no_mask()` sees a real value and passes, and the
deploy pushes **branch's SNMP community onto a campus device**. Every guard on
the deploy path is satisfied, because none of them asks which network a secret
belongs to.

`r1` is the actual device name in the reference lab, and "r1" is the most
likely name in any second lab. This is not a contrived collision.

Severity is raised by two further facts:

- `set_template_secret()` **overwrites without reading first** — no
  already-exists check, no warning, no audit entry.
- The failure is invisible until a deploy reaches a device, and then it looks
  like a device problem rather than a tooling problem.

**Fix shape:** key by list slug — `<slug>:<hostname>:<ref>` — with a one-time
migration of existing keys into the current list's namespace. `list_secrets`
and the rotation work in queued item (4) must both learn the new shape, so
this should land *before* item (4), not after.

---

## B. The pipeline resolves which list it is writing to from global mutable state

`PipelineContext` carries `device_ips`, `selected_devices`, `check_devices`,
`config_id`, `confirmed_commands` — and **no list name**. So the deploy path
asks a global for it, three times, all of them after the push:

| line | call | what it decides |
|---|---|---|
| `pipeline.py:1330` | `get_list_data_dir(get_current_list_name())` | repo for the rolled-back note |
| `pipeline.py:1397` | `get_list_data_dir(get_current_list_name())` | repo for post-deploy staging |
| `pipeline.py:1471` | `save_golden(get_current_list_name(), …)` | **which repo receives the golden commit** |

`get_current_list_name()` reads `current_list` out of a **file on disk** on
every call. It is not per-request, not per-thread, and any request that
switches lists rewrites it.

**Consequence.** A deploy is long — push, then convergence settle windows of
45 s (OSPF), 60 s (BGP), 90 s (RIP), then capture. Switching the active list in
the UI during that window is one click and a completely natural thing to do
while waiting. If it happens, stage 8.5 commits network A's captured configs
into **network B's repository**.

`allow_new=False` is a partial accident-of-design mitigation: if B's manifest
has never heard of the device, identity resolution fails and the commit errors
out loudly. But that protection **disappears exactly when it matters** — two
networks that both contain `r1`, or both use `10.255.1.11`, resolve cleanly by
name or by IP, and A's running config is committed as B's golden. Silent, and
it corrupts the artifact the whole phase exists to protect.

Same class of defect as the ones already fixed this week: a value that should
be *carried* is instead *re-derived later from ambient state*.

**Fix shape:** `PipelineContext` gains `list_name`, set once at construction by
the caller that already knows it (`routes/deploy.py::_deploy_one` has
`list_name` in scope and passes it to nothing). The three call sites read
`ctx.list_name`. Nothing in the pipeline should call `get_current_*` at all.

---

## C. One function resolves the repo from its argument and the inventory from a global

`modules/nsot/restore.py`:

```python
def build_targets(list_name, ref, devices=None, un_onboard=None):
    repo = _repo_for(list_name)                       # from the ARGUMENT
    ...
    _name, csv_path = get_current_device_list()       # from GLOBAL STATE
    rows = {d.get("hostname", ""): d for d in load_saved_devices(csv_path)}
```

The same is true of `plan_restore()` at line 45.

The function takes `list_name` and then ignores it for half its work. If the
caller passes a list that is not the active one — which the signature invites,
since why else take the parameter — targets are built from **list A's stored
configs against list B's device rows**: B's management addresses, B's
credentials, B's platform mapping.

Today every caller happens to pass the active list, so it is latent. It is
still the more dangerous shape of the two, because the signature actively
advertises a capability the body does not honour.

**Fix shape:** take the rows from `list_name` too. A `list_name` parameter must
be the single source of that answer inside the function, or it should not be a
parameter.

---

## D. Nothing is masked on any path OUT — and the AI path leaves the host

This is the finding that reframes queued item (2).

There is **no masking on any display or transport path**. `grep` for `MASK` in
`routes/golden.py`, `app.py`, and `modules/ai_assistant.py` returns nothing.
The `MASK` machinery in `render_artifact.py` exists only for *rendered
previews*; a golden config is never passed through it.

Two consequences, one of which is already realised:

1. `GET /golden/config/<hostname>` returns the raw config as JSON —
   `{"ok": true, "config": "<full text>"}` — including the plaintext SNMP
   communities and the plaintext router passwords.
2. **The AI assistant reads golden configs and sends them to the Anthropic
   API.** "AI read-first: the agent checks golden configs and variables before
   opening any SSH session" is a documented core design principle, and
   `_find_golden_config_file()` / `_load_golden_config_file()` are AI-assistant
   functions. Every such call puts the file's contents into a prompt.

So the exposure is not hypothetical and not confined to git: **the plaintext
admin passwords of r1–r5 and all 18 SNMP communities have very likely already
left this host**, every time the agent was asked about one of those devices.

That reorders the work. Masking material on its way *out of the process* is
worth more than masking it at rest in a private repo, and it is unambiguous —
there is no design fork and no downside.

---

## E. Masking golden/ **at rest** is a real fork, and it fights Phase 2b

Recorded as a decision to take, not a recommendation to act on silently.

Storing `__secret__:<ref>` in the committed `.cfg` — reusing the marker
convention `roundtrip.render()`'s `_resolve_markers()` already understands —
would keep new commits clean. The cost is that **`golden/` stops being a
self-sufficient record**:

- `prepare_restore()` calls `assert_no_mask()` and would **refuse** a masked
  golden. Restore, drift, and round-trip comparison all consume golden text and
  would each need a hydrate step, each one a new place to get it wrong.
- The goldens become dependent on `data/key.key`, which is **not in the
  repository**. A private GitHub repo containing masked goldens is a repo you
  **cannot restore the network from**. That directly contradicts Phase 2b's
  stated goal — "a list's configuration history survives the loss of this
  server" — since surviving the server means surviving the loss of that key.

**Recommendation: do not mask `golden/` at rest.** Instead:

1. Mask on the way **out** (finding D) — API, UI, logs, AI context. No fork,
   no downside, and it stops the leak that is actually happening.
2. Rotate (queued item 4) so the plaintext already in history is **dead
   material**. This is the only thing that genuinely fixes the existing 51
   commits; masking new commits does nothing about them.
3. Let Phase 2b's acknowledgement gate cover what remains.

If at-rest masking is wanted anyway, it needs an explicit answer to: *where
does the key live such that the repo alone can still restore a network?* Key
escrow alongside the repo defeats the purpose; key loss makes the archive
inert. That question should be answered before the mechanism is built.

---

## Suggested order

1. **A** — key the credential store by list. It is a live correctness bug, and
   queued item (4) must not run against the old key shape.
2. **B** — `list_name` on `PipelineContext`. Small, and it protects the golden
   store during every deploy.
3. **C** — one source of truth inside `build_targets` / `plan_restore`.
4. **D** — outbound masking, AI path first, then the API/UI.
5. Then queued item (4), then Phase 2b's adopt-first increment.

A, B and C are each small. D is the one with real surface area.

---

## F. Deployment exposure: the identity header is currently unauthenticated

Measured 2026-09-21, before any firewall change. Recorded here because the
identity work in D3 depends on every one of these being false.

### What listens

```
ss -4:  LISTEN 0 128 0.0.0.0:5000   python3
ss -6:  (empty — no [::]:5000 listener)
```

IPv4 only, but on **every** interface: LAN (`10.0.0.211`), both lab networks
(`10.255.0.10`, `10.255.1.10`) and the docker bridges.

Request sources in `logs/device_manager.log`:

| source | requests | what |
|---|---|---|
| `10.0.0.21` | 21,581 | cloudflared — the tunnel |
| `127.0.0.1` | 151 | local |
| `10.0.0.30` | 2 | the probes below |

### The header can be forged by any LAN host

From a laptop on the LAN, not the tunnel:

```
curl -H "Cf-Access-Authenticated-User-Email: forged@example.com" \
     http://10.0.0.211:5000/          →  HTTP 200
```

`Cf-Access` appears **nowhere** in the codebase, so nothing consumes it yet —
this is greenfield rather than a live authorisation bypass. It does mean the
header on its own can never be the actor.

### IPv6 — reachable from the LAN, internet exposure NOT established

The host carries globally-scoped IPv6 (`2601:280:4a02:5ed0::b3b9`, plus a
SLAAC address). Port 22 answered over IPv6 and port 5000 did not.

**A first pass read that as internet exposure. It is not, and the distinction
matters.** The probing machine sits in `2601:280:4a02:5ed0::/64` — the *same
/64* — so the traffic was on-link neighbour traffic and never crossed the
router's inbound v6 filter. The correct claim is **reachable from the LAN over
IPv6**; whether anything reaches it from outside is untested and needs an
off-net probe.

> Reachability is only ever a statement about a path. A test run from inside
> the same broadcast domain has not tested the firewall between domains, and
> reporting it as though it had converts an unknown into a false certainty.

What does hold regardless: port 5000 is closed over IPv6 **only because no
`[::]` listener exists**, not because anything blocks it. `NMAS_HOST=::`, or
any future dual-stack bind, would open it — so the restriction must cover both
address families, and `NMAS_HOST` should name a specific address rather than
`0.0.0.0`, giving two independent layers instead of one accidental one.
Binding to `10.0.0.211` also stops `localhost:5000` working on the host.

### Not established

- **Firewall rules** — `sudo` requires a password; `ufw`, `iptables` and `nft`
  are installed but unreadable.
- **The tunnel's origin URL** — SSH to `10.0.0.21` failed host-key
  verification, and accepting an unknown host key is a trust decision. If the
  origin is a *hostname* rather than `http://10.0.0.211:5000`, whatever
  resolver `10.0.0.21` uses could return a AAAA record.
- **Whether the header arrives through the tunnel** — needs root for
  `tcpdump`, or a consumer in the app. The consumer is the better answer: it
  is needed anyway, and makes the confirmation a by-product of the feature.

### The design consequence

The email header is not evidence. `Cf-Access-Jwt-Assertion` is validated
instead — RS256, signature against
`https://<team>.cloudflareaccess.com/cdn-cgi/access/certs`, with `aud` and
`iss` checked — and the email is read from the **verified claims**. Per
Cloudflare: *"You should validate the token with your public key to ensure that
the request came from Access and not a malicious third party."*

The peer address is a **second, independent** condition, read from the raw
socket. No `ProxyFix`, no `X-Forwarded-For` trust — verified absent from the
codebase today, and to be pinned by a test. Same shape as
`netbox_allow_writes` plus the one-shot token: two conditions, neither
sufficient alone, and the peer check is the one that survives a firewall rule
being edited later.
