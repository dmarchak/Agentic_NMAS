# The NMAS's own accounts in NetBox and Grafana: the one-time steps

The operator's steps, written 2026-09-30. Each service gets an account that is the
NMAS's alone, with the least permission the NMAS's own code needs. The stored token is then
switched, and each switch is checked by measurement, never by the absence of an error.

**Why:**
- **NetBox (C100).** The NMAS's token belongs to the operator's own account, so NetBox's
  change log cannot tell the NMAS's writes from a person's. Drift in NetBox is to be EXACT
  (the operator, 2026-09-30): any change-log entry made by another account is drift. That
  needs the NMAS to have its own account. The change log then also attributes every NMAS
  write, which adopt's records and C149's attribution both want.
- **Grafana (C230).** The NMAS's token holds an Editor's permissions (measured on 13.2.0:
  45 of its 75 permissions change something, including creating silences and writing and
  deleting alert rules). The NMAS only reads Grafana, so its token should be a Viewer's.

**What was measured before writing this** (read-only, on the host, 2026-09-30):
- NetBox **4.6.9**; the stored token acts as user id 1, the operator's own account;
  `Bearer` authentication.
- Grafana **13.2.0 Open Source**; `auth.proxy` off; the stored token has an Editor's
  permissions.
- `scripts/nmas-integration-accounts` prints both answers. Run on the host before the
  switch, it exits 1 ("it can CHANGE Grafana") and names the operator's NetBox account.

Nothing here touches a device. Every step is the operator's, in NetBox's or Grafana's own
interface and in the NMAS's Settings page.

---

## Part 1. NetBox: the account `nmas`

### 1.1 Before switching: take the baseline

On the NMAS host, in the checkout, with the CURRENT token still stored:

```
scripts/nmas-integration-accounts
scripts/nmas-netbox-census --out /tmp/census-before-switch.json
```

The census records every object per type, by identity, as the current account sees it. It is
what proves, after the switch, that the new account sees everything. Two shapes, from
NetBox's source and not measured on this instance (2026-10-05):
- a view permission that is MISSING for a type is refused (403, "You do not have permission
  to perform this action"). Settings › NetBox › Test now names such a type (C468), and the
  census exits 2 naming it (C467);
- a view permission that is CONSTRAINED, or objects the account may not see, answer 200 with
  fewer items, which looks exactly like a smaller type. Only a comparison catches that, so
  view is never constrained here.

### 1.2 Create the user

NetBox > **Admin** > Authentication > **Users** > **Add**:
- **Username:** `nmas`
- **Password:** a long random one, recorded nowhere. The account signs in by token only.
- **Active:** yes. **Staff:** no. **Superuser:** no.

### 1.3 Give it the least permission the NMAS's writes need

NetBox > **Admin** > Authentication > **Permissions** > **Add**, four times. Each lists its
object types; assign each to the user `nmas`.

The object types come from the code: every path the NMAS passes to `_nb_post`, `_nb_patch` or
`_nb_delete` (`modules/netbox_client.py`, `modules/netbox_context_mask.py`,
`scripts/nmas-netbox-status-reset`, `scripts/nmas-netbox-repair-addresses`), and every path it
reads.

1. **`nmas-view`**. Actions: **view**. Object types:
   - DCIM: cable, device, device role, device type, interface, manufacturer, platform,
     region, site;
   - IPAM: IP address, prefix, role, VLAN, VRF;
   - Extras: config template, custom field, tag;
   - VPN: tunnel, tunnel termination;
   - Core: **object change** (the change log: the drift reader's source, and what
     `nmas-netbox-untagged` and `nmas-netbox-deletions` read);
   - Users: **token** (view only: the credential-health reader reads the token's own row,
     `GET /api/users/tokens/`, for its expiry; added 2026-10-05 by the C100 survey).
2. **`nmas-add`**. Actions: **add**. Object types:
   - DCIM: cable, device, device role, device type, interface, manufacturer, platform,
     region, site;
   - IPAM: IP address, prefix, role, VLAN, VRF;
   - Extras: config template, custom field, tag;
   - VPN: tunnel, tunnel termination.
3. **`nmas-change`**. Actions: **change**. Object types, the six the NMAS updates:
   - DCIM: device, interface, site;
   - IPAM: IP address, prefix;
   - Extras: config template.
4. **`nmas-delete`**. Actions: **delete**. Object types, Remove's order
   (`_REMOVAL_ORDER`): VPN tunnel; IPAM IP address, prefix, VLAN, VRF; DCIM interface,
   device, site, region.
   - **Constraints:** `{"tags__slug": "nmas-managed"}`, added ONLY once the host runs a
     commit with C466's fix (2026-10-05). NetBox answers a delete its constraint refuses with
     404. Before the fix, `_nb_delete` read every 404 as "already gone" and forgot the record,
     so a refusal read as a success. Since the fix, a 404 is read back by id: an object still
     there is a REFUSED delete, kept, recorded and named.
   - This makes NetBox itself refuse to delete an object the NMAS did not tag. Remove already
     deletes only tagged AND recorded objects, so this is a second, independent layer.
   - Never constrain a VIEW permission: a hidden object reads as gone.

   **The step (after deploying the C466 fix):** NetBox > Admin > Authentication >
   Permissions > `nmas-delete` > Constraints: `{"tags__slug": "nmas-managed"}` > Save.
   **The check that it holds** (on the NMAS host). It creates one untagged scratch region as
   `nmas`, asks to delete it, and reads it back:

       cd <home>/python/Agentic_NMAS && PYTHONDONTWRITEBYTECODE=1 python3 - <<'EOF'
       from modules.netbox_client import get_netbox_config, _session_from_config
       c = get_netbox_config(); s = _session_from_config(c); u = c["url"] + "/api/dcim/regions/"
       r = s.post(u, json={"name": "c466-probe", "slug": "c466-probe"}); print("create", r.status_code)
       i = r.json()["id"]
       print("delete", s.delete(f"{u}{i}/").status_code, "| read back", s.get(f"{u}{i}/").status_code)
       EOF

   Expect `create 201`, then `delete 404 | read back 200`: the constraint refused it, and the
   region is still there. Then delete `c466-probe` by hand in NetBox's interface (Organization
   > Regions). `delete 204` would mean the constraint is not applied.

**What it deliberately does NOT grant:** anything under Authentication (permissions,
users), anything under Users but token view, and any delete of a tag. Remove must never delete its own tag; that rule was
enforced only by omission, and now NetBox enforces it too.

### 1.4 Create the token

NetBox > **Admin** > Authentication > **API Tokens** > **Add**:
- **User:** `nmas`
- **Write enabled:** yes
- **Version:** 2 (the `nbt_…` form: the credential-health reader finds its own row by the v2
  key).
- **Allowed IPs:** EMPTY for now (2026-10-05). NetBox runs in docker on the NMAS host, so the
  source address it sees is not measured, and the tool's Test hides NetBox's refusal reason
  (C468): a wrong address would read only as "Authentication failed".
- **Expires:** a date to renew by. The tool reads it from NetBox (with the Users › token view
  above), so P.21 tracks it. NetBox has no "Token expires" field in Settings; Grafana and
  Proxmox do, because their tokens cannot read their own.
- **Description:** `NMAS (C100)`

The token is shown ONCE. Copy it straight into the next step.

### 1.5 Switch the stored token

NMAS > today's page > **Settings** (the modal) > **NetBox** section: paste the token into the
token field, **Save Settings**, then **Test Connection**. The field is write-only, so the old value is replaced and never
shown.

**Note the time (UTC).** Drift is measured from this moment. Every earlier change-log entry
was made by one account for both the NMAS and the operator, so it cannot be classified.

### 1.6 Check the switch, by measurement

On the NMAS host:

```
scripts/nmas-integration-accounts
scripts/nmas-netbox-census --compare /tmp/census-before-switch.json
```

- **The first** must read: `the stored token acts as 'nmas'`.
- **The second** must exit **0**. The new account sees every object, per type and by
  identity, that the old one saw. Exit 1 names the type that differs. Exit 2 names a type it
  could not read at all (a missing view). Since C467 it walks every type the tool reads, so a
  baseline must be taken by the same version of the script.
- **Then, at the next real NetBox write** (an import or an onboarding): C8's report names any
  refused write per device and per write. A 403 there names the object type whose add or
  change permission is missing. It is never silent.

### 1.7 Retire the old token

Once 1.6 passes: NetBox > Admin > API Tokens. Delete the token the NMAS used to hold (the
operator's own), unless something else uses it. The NMAS no longer does.

---

## Part 2. Grafana: a Viewer token

### 2.1 Create the service account and its token

Grafana > **Administration** > Users and access > **Service accounts** >
**Add service account**:
- **Display name:** `nmas-reader`
- **Role:** **Viewer**

Then **Add service account token**, with no expiry or a noted one. It is shown ONCE.

### 2.2 Switch the stored token

NMAS > **Settings** > Integrations > **Grafana**: paste it, fill **Token expires** (YYYY-MM-DD
or `never`: the token cannot read its own expiry, so P.21 tracks the date declared here and
warns 30 and 7 days ahead), **Save**, **Test**. Expect "Connected; the token is accepted".

**Viewer is enough** (the C230 survey, 2026-10-05): every Grafana call the tool makes is a read.
It reads dashboards, the datasource list, the alerts ruler and rules, alert instances and
silences, and queries datasources through `POST api/ds/query`, which is a read. It never creates
or expires a silence, writes an annotation, imports a dashboard or installs a rule: rules are
provisioned files, installed by a root host step. The full list of calls is in
`docs/FLEET_SESSION_1.md`, Part 2. Two ways a Viewer read silently returns less: a datasource
whose Query permission excludes Viewer, or a folder that does not give Viewer View.

### 2.3 Check the switch, by measurement

On the NMAS host:

```
scripts/nmas-integration-accounts
```

- **It must exit 0** and read `no create, write or delete: a reader's token`.
- **The `all:` line is the Viewer role on the installed version, measured.** Send it on, and
  it replaces the documentation's claim in the brief (section 15.3).
- **Within a minute, Needs attention must NOT show "device(s) have no heartbeat rule Grafana
  shows".** A Viewer that cannot see a rule reads as a missing rule. The reader's floor is
  the check that the new token still sees what it monitors.

### 2.4 Retire the old token

Grafana > Administration > Service accounts: delete the Editor token the NMAS held.

The ruler shows three hand-built rules last edited by an account named `nmas-automation`.
Whether that is the old token's service account is not visible to a token without admin
rights. If it is, and nothing else uses it, it can go too. P.7 retires the hand-built rules
anyway, and generates the new ones as provisioned files that no role can edit.

---

## After both

- **The NetBox drift reader** is built against the new account (brief section 15.2). Its
  first real run is the account's own acceptance: a hand edit in NetBox appears as a Needs
  attention row naming the object, the field, both values and who made it; an NMAS write
  does not.
- **Job health keeps both answers true** (brief section 15.3): the Grafana token holds no
  write, and the NetBox token acts as the NMAS's account.
