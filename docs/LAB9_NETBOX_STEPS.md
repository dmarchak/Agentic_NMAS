# Lab 9: the operator's NetBox steps for the inventory entry (P1b)

These are the NetBox writes the SDN platform design (revision 4, section 9a, and decisions 5 and
6 of section 17) leaves to the operator, given with P1b. They are made in NetBox's own web UI,
with the operator's own login: Mercury's NetBox token does not edit roles, custom fields or a
device's local config context, and is not widened for this. Each step ends with a **PASS**
line; stop at the first that does not pass and say which.

Names here are roles, not the lab's device names: **the router**, **the 2960** (the management
switch), **the controller** (the Linux host that runs the SDN controller), and **lab9** (the
network in Mercury that reads them from NetBox). The menus are NetBox 4's.

**Order.** Steps 1 and 2 (observe-only) can be made at any time after P1b is deployed. Steps 3 to
6 (the `host` kind) go in order: the field accepts `host` before a role is given it.

**Why each is LABOUR, not a decision:** docs/MANUAL_STEPS.md, rows M36 and M37.

## 1. The router: observe-only, in its local config context

The router already carries local config context data (from the operator's earlier NetBox
steps for Lab 9), so it gains one key and keeps everything it has.

1. **Devices › Devices**, search for the router, open it.
2. Open its **Config Context** tab and copy what **Local Context** shows (the data it carries
   now), so it can be compared after the save.
3. Press **Edit** (top right). Scroll to **Config Context** and find **Local config context
   data**.
4. Add a top-level key `mercury` holding `{"management": "observe"}`. If the data already has a
   `mercury` key, add `"management": "observe"` inside it instead; change nothing else. For
   example, data that was `{"a": 1}` becomes `{"a": 1, "mercury": {"management": "observe"}}`.
5. Press **Save**.

- **PASS:** the device's **Config Context** tab shows, under **Rendered Context**,
  `"mercury": {"management": "observe"}`, and **Local Context** shows every key it showed in
  sub-step 2, unchanged, plus `mercury`.
- **PASS (in Mercury, after lab9's next read of NetBox):** Settings › lab9 › Network, **Refresh
  now**; then the router's device page, **Actions**: the menu's note says "observe (the device's
  local config context): nothing that changes it is offered", and Plan a deploy…, Restore
  from…, Remove lines (Mode B)…, Rotate credential…, Persist and Run a privileged command… are
  greyed, each saying why on hover. Capture is still offered.

## 2. The 2960: observe-only, its first local config context

1. **Devices › Devices**, search for the 2960, open it, press **Edit**.
2. Under **Config Context**, **Local config context data**, type exactly:
   `{"mercury": {"management": "observe"}}`
3. Press **Save**.

- **PASS:** its **Config Context** tab's **Rendered Context** shows
  `"mercury": {"management": "observe"}`.
- **PASS (in Mercury, after Refresh now):** the 2960's Actions menu reads as the router's does
  in step 1.

A context assigned by tag or role (**Provisioning › Config Contexts**) would mark many devices at
once; it is not needed for these two. Mercury reads the RENDERED context, so a device's own local
data wins over an assigned one, as NetBox merges them.

## 3. The `host` value in `mercury_kind`'s validation (decision 5)

1. **Customization › Custom Fields**, open **mercury_kind** (label "Mercury kind").
2. Press **Edit**. Under **Validation**, set **Validation regex** to exactly:
   `^(router|switch|firewall|host)$`
3. Leave every other field as it is. Press **Save**.

- **PASS:** the custom field's page shows the validation regex
  `^(router|switch|firewall|host)$`.

## 4. The `linux` platform

1. **Devices › Platforms**, press **Add**.
2. **Name:** `Linux`. **Slug:** `linux` (NetBox fills it from the name; check it reads exactly
   `linux`). Leave the manufacturer and the config template empty.
3. Press **Create**.

- **PASS:** **Devices › Platforms** lists `Linux` with the slug `linux`.

## 5. The controller's role: `mercury_kind` = `host`

First check that the role is the controller's alone: a role's kind applies to every device that
has the role.

1. **Devices › Device Roles**, open the controller's role.
2. Read its **Devices** count.
   - **PASS:** the count is 1 (the controller), or every device it counts is a Linux host
     Mercury should manage services on. If any is a network device or an end host, stop and
     tell the agent: the controller needs a role of its own first.
3. Press **Edit**. Under **Custom Fields**, set **Mercury kind** to `host`. Press **Save**.

- **PASS:** the role's page shows **Mercury kind** `host`, and NetBox saved it without a
  validation error (step 3's regex accepted it).

## 6. The controller's platform

1. **Devices › Devices**, search for the controller, open it, press **Edit**.
2. Set **Platform** to `Linux`. Press **Save**.

- **PASS:** the device's page shows **Platform** `Linux`.

## 7. In Mercury: the platform map, the profiles, and the read

These are Mercury's own screens, not NetBox's, listed so the steps above end in their result.

1. **Settings › Installation › Platforms and roles**: add the platform `linux` with the driver
   `linux` and no config dialect; **Preview changes**, then **Test** on the controller (one
   read-only session asking `cat /etc/os-release`), then confirm.
   - **PASS:** the Test answers with the controller's `os-release`; the preview names the
     controller as moving from skipped to the driver `linux`.
2. **Credentials › Profiles**, **Add a profile…** for each platform, choosing "every device on a
   platform" and typing the platform's NetBox slug; the operator types each login (never the
   agent).
   - **PASS:** each profile's row says "every device on the platform <slug>".
3. **Settings › lab9 › Network**, **Refresh now**.
   - **PASS (S1's goal 1):** lab9 lists the managed devices with no "No login" status, the
     controller with the kind `host`, and one skip, the end host with no primary IPv4; Needs
     attention has no "have no login" row for lab9.

## 8. The end hosts: tagged, never managed (C2776)

Each end host on the OpenFlow fabric (each PC or server a switch port serves) is a NetBox
device tagged `mercury-end-host`. The NSOT export reads every device with that tag at the
network's sites as a **host**, never as a managed device: Mercury neither logs in to it nor
polls or protects it. The trace (A4), DHCP (A3), the DNS app (A2) and the intent checks (B2)
read each host's MAC, addresses and switch port from it. Steps 8.1 and 8.2 are made once; steps
8.3 to 8.6 are made for each host.

1. **Customization › Tags › Add.** Name `mercury-end-host`, slug `mercury-end-host` (check that
   it reads exactly that), any colour. **Create**.
   - **PASS:** **Customization › Tags** lists `mercury-end-host`.
2. **Devices › Device Roles › Add** (once). Name `End host`, slug `end-host`. Leave **Mercury
   kind** empty: an end host is none of Mercury's kinds. **Create**.
3. **Devices › Devices › Add**, for each host:
   - **Name:** the host's name.
   - **Role:** `End host`.
   - **Device type:** any generic type (for example a `Generic host` type of one interface).
   - **Site:** the network's site.
   - **Platform:** leave it empty.
   - **Tags:** `mercury-end-host`.

   Press **Create**. With no platform and no primary IPv4, Mercury's inventory skips the host
   by name (step 7's "one skip"); the export reads it by its tag.
4. **The host's interface.** On the host's **Interfaces** tab, add the NIC (for example `eth0`,
   type `1000BASE-T`) if the device type gave it none.
5. **Its MAC** (NetBox 4.2 and later: **Devices › MAC Addresses › Add**). Type the NIC's MAC and
   assign it to the host's interface. Then edit the interface and choose that MAC as its
   **Primary MAC address**. (Before 4.2, type it in the interface's **MAC address** field.)
6. **Its addresses.** **IPAM › IP Addresses › Add**: the host's IPv4 address with its prefix
   length (and its IPv6 address, if it has one), each assigned to the host's interface. Leave
   **Primary IP** unset on the device, so Mercury never tries to reach the host.
7. **Its cable.** On the host's interface, **Connect › Interface**: the switch and the switch
   port it plugs into, status Connected. That port is one of the switch's OpenFlow ports, with
   its `openflow_port` number set (P1b).

- **PASS (in Mercury, after the steps):** SDN › Apps, the **NSOT export** card, **Export from
  NetBox…**: the
  changes name each host under **End hosts** as added, and none of them under Devices; then
  **Commit the export**. A host whose switch has no datapath id, or whose port has no
  `openflow_port`, is named with the value that is missing wherever a host's port is read (the
  trace, DHCP); the card itself lists hosts by name.

## 9. The protected DNS and DHCP flows (C2776)

Management traffic is protected with nothing to enter. It is derived from every management
interface and prefix (B, `modules/protected.py`), so check only that each management interface
is marked **Management only** or holds the device's primary address.

DNS and DHCP are declared once, as a config context assigned to the network's site. Each class
names its **owners**, the one writer that may install flows meeting it; every other writer is
refused, naming the class.

1. **Provisioning › Config Contexts › Add.**
   - **Name:** `Mercury protected flows`.
   - **Weight:** `1000`.
   - **Sites:** the network's site.
   - **Data:** exactly this:

   ```json
   {"mercury": {"protected_flows": [
     {"name": "dns", "invariant": "must_reach dns", "owners": ["app:dns_blacklist"],
      "reason": "every host's DNS: the blacklist app answers or forwards each query",
      "match": {"eth_type": "0x0800", "ip_proto": 17, "udp_dst": 53}},
     {"name": "dns-ipv6", "invariant": "must_reach dns", "owners": ["app:dns_blacklist"],
      "reason": "every host's DNS over IPv6",
      "match": {"eth_type": "0x86dd", "ip_proto": 17, "udp_dst": 53}},
     {"name": "dhcp", "invariant": "must_reach dhcp", "owners": ["feature:dhcp-unicast"],
      "reason": "every host's lease: requests are steered to the router as unicast (A3)",
      "match": {"eth_type": "0x0800", "ip_proto": 17, "udp_dst": 67}},
     {"name": "dhcp-reply", "invariant": "must_reach dhcp", "owners": ["feature:dhcp-unicast"],
      "reason": "the router's replies to every host",
      "match": {"eth_type": "0x0800", "ip_proto": 17, "udp_src": 67, "udp_dst": 68}}
   ]}}
   ```

   Press **Create**. NetBox merges it into each device's rendered context beside the
   `mercury.management` key of steps 1 and 2. An entry of any other shape makes the whole
   protected set unreadable, and an unreadable set refuses every flow write, naming why.
2. **If the DNS server is a device in NetBox:** a Service on it named `dns`, protocol UDP,
   port 53, with the server's address chosen in **IP addresses**, and the tag
   `mercury-protected`, adds the server's own class (`must_reach dns`, owned by nobody).
   That Service is optional: the context entry already covers every host's queries.

- **PASS (in Mercury, after the export of step 8 is confirmed):** SDN › Flows, **Preview** a
  flow you write yourself matching UDP destination port 53 (drop): it is refused, naming the
  protected class `dns`, its owner `app:dns_blacklist` and the config context it came from.
  The same flow matching UDP port 5353 is not refused.
