# Lab 9: the NSoT-driven OpenFlow configuration

**For the final SDN lab (requirement A2, docs/LAB9_SDN_GAP.md section 1).** The operator's team
builds the hardware and its base setup by hand (A1). Mercury's part starts after that:
- ZTP, where a switch supports it (section 4, piece 3);
- the OpenFlow configuration, rendered from NetBox, in every case.

**Open vSwitch comes first** (the operator's decision 7, 2026-11-05). Its configuration works end
to end on the servers' Open vSwitch before the vendor templates are added to it. OVS's checkpoint
is 2026-11-12.

The vendor templates are **drafts**. No driver can send them yet: each vendor is a discovery
driver, which refuses every write (docs/LAB9_DISCOVERY.md).

## 1. The values, from NetBox

NetBox holds them in the places docs/LAB9_SDN_GAP.md section 2.2 decided. Mercury reads them
through its NetBox client and writes nothing back (`modules/sdn/openflow_values.py`).

| Value | Where in NetBox |
|---|---|
| The switch's management address | the device's primary IP: IPv4, else IPv6 |
| The controller's address and port | the Service named `openflow` (TCP), on the controller's device: the Service's first port, and its own IP address, else its device's primary IP |
| Which controller | the only `openflow` Service; with more than one, the config context's `openflow.controller` names its device |
| The OpenFlow version, transport and fail mode | the config context's `openflow` key (`version`, `transport`, `fail_mode`), set on a role, site or platform, or per device |
| The OpenFlow instance (OVS's bridge) | the device's custom field `openflow_instance`, else the config context's `openflow.instance` |
| The datapath id (optional) | the device's custom field `openflow_datapath_id`, 16 hex digits |
| The OpenFlow ports | the device's interfaces tagged `openflow` |
| Each OpenFlow port's number | the interface's custom field `openflow_port` (C2603): required where the platform numbers ports in the order they are added (Open vSwitch, whose bridge requests it with `ofport_request`); elsewhere checked against the switch's own numbering (an Arista's interface number, a ProCurve's port number), and refused naming both when they differ |
| The OpenFlow VLAN (ArubaOS-Switch, Comware) | the untagged VLAN those interfaces share |
| The management VLAN | the VLAN of the interface holding the primary IP, else of another management interface (below) |

**The management interface is never OpenFlow** (the operator, 2026-11-05: Lab 9's management
network is separate and non-OpenFlow). An interface is the management interface when any of
these holds:
- NetBox marks it `mgmt_only`;
- it holds the device's primary IP (IPv4 or IPv6);
- it holds the device's OOB IP (`oob_ip`).

What follows from that, on a switch and an OVS server alike:
- **It is never an OpenFlow port,** even when tagged `openflow`. The preview says so by name:
  "<interface> is the management interface (mgmt_only / primary IP / OOB IP): excluded from
  OpenFlow".
- **A device whose only tagged interfaces are management ones is refused,** naming each one and
  why.
- **An OpenFlow VLAN equal to the management VLAN is refused,** naming both.

**Defaults, each named in the preview when used:** version `1.3`, transport `tcp`, fail mode
`secure`. Lab 8's switches were secure: Mininet's `OVSSwitch` is secure by default, and in this
lab only the controller forwards.

**A missing value refuses the render.** The refusal names the value and where it comes from.

**A value of the wrong shape is refused too.** Each one is checked before any template sees it:
- an address, by `ipaddress`;
- a port, 1 to 65535;
- a name, one token;
- a VLAN, 1 to 4094;
- a datapath id, 16 hex digits and not all zero;
- an OpenFlow port number, 1 to 65279, and no number given to two ports of one switch.

**From NetBox, or from the network's NSOT export.** `openflow_values.from_export` reads the same
values from the committed export (`modules/nsot/export.py`: deterministic JSON in the network's
repository at `nsot/export.json`, hashed, committed as the person who exported it), so a plan can
read NetBox's state offline and name the export's hash.

## 2. The templates

Each template is a file in `modules/sdn/openflow_templates/`. A template states:
- the drivers it is for;
- the transports its vendor's document supports;
- whether its controller may be an IPv6 address;
- its lines.

**The platform profile states what a release needs** (`modules/platforms/profiles/`, chosen by
the switch's own OS version): the OpenFlow versions it offers (a version outside them is
refused, naming both; EOS 4.17 offers 1.0 and 1.3, C2598), whether a change to the bound ports
needs the OpenFlow agent restarted (`bind_change_requires`, C2599), what each OpenFlow port needs
(`openflow_ports_require: [lldp_off]`, C2600), and how ports are numbered (`port_numbering`,
C2603). A template reads these as `profile.openflow.<key>`, and one reading a key its profile's
entry does not hold is refused, naming it.

**Every line cites its source and says why.** A citation is the vendor's document (the
document, the section or command entry, the release, the URL and the date it was read) or a
**measurement** (the register row, the masked capture or harness run in this repository that
shows the release accepting the line, the release and the date). Every line also carries its
`why`: a fixed sentence naming the concept and the NetBox input it comes from, carried with each
rendered line (the SDN design's rule 11b(e)). `openflow_templates.problems` checks both, and a
template with a problem is never rendered.

| Template | Status | Lines | Citations (verified; measured) | What it covers |
|---|---|---|---|---|
| `ovs` (Open vSwitch) | draft until confirmed (section 3) | 7 | 9 (8; 1): ovs-vsctl(8) and ovs-vswitchd.conf.db(5), Open vSwitch 4.0.0; `ofport_request` measured in the container harness | the bridge, `protocols`, the datapath id when given, the fail mode, the controller (IPv4 or IPv6), the OpenFlow ports, and each port's number requested as NetBox's (`set interface <port> ofport_request=<openflow_port>`, C2603). All in one `sudo -n ovs-vsctl` transaction, which OVSDB keeps, so there is no save |
| `arista_eos` | draft | 7 | 8 (6; 2): the EOS 4.20.1F User Guide, chapter 45; LLDP off and the restart measured on 4.17.0F | `no lldp transmit` and `no lldp receive` under each OpenFlow port (C2600), `openflow` mode, `controller tcp:<ip>:<port>`, `bind mode interface`, one `bind interface` per OpenFlow port, `shutdown` before `no shutdown` when the bound ports differ from the running agent's (C2599), `no shutdown`. The versions are the profile's (1.0 and 1.3 on 4.17, so the Aristas render at 1.3: M2). TCP only. The management interface is left unbound |
| `aruba_os_switch` | draft | 9 | 8 (6; 2): the ArubaOS-Switch OpenFlow v1.3 Administrator Guide for 16.03; the VLAN membership and LLDP measured on K.16.02 | each OpenFlow port untagged in the member VLAN (`vlan <v> untagged <port>`), `lldp admin-status <port> disable` (C2600), the controller on the management VLAN (`controller-interface vlan`), one instance with `member vlan`, `version 1.3` (as the lab's K.16.02 switch runs it; the default is 1.0), `connection-interruption-mode`, `enable`. The management VLAN cannot be a member. The one-line forms on K.16.02 are unconfirmed (C2590) |
| `hp_comware` | draft | 5 | 5 (5; 0): H3C's Comware 7 OpenFlow command reference (R612x-6W103); no HPE-branded page could be read | a numbered instance, `classification vlan`, `controller <id> address ip|ipv6 <addr> port <p>`, `fail-open mode`, `active instance`. Comware has no version command; its profile (Comware 7.1, from the reference) offers 1.3 |
| `aruba_aoscx` | **support UNKNOWN** | 0 | 0 | nothing renders. No AOS-CX document read on 2026-11-05 says whether AOS-CX supports OpenFlow |

**Compared as parsed models** (`modules/sdn/openflow_state.py`): a switch's own configuration
(EOS's and ArubaOS-Switch's running configuration, ranges expanded and hidden defaults supplied;
OVS's `ovs-vsctl show` and interface list) and a rendered program parse into one model per
template, and `render_against` decides `state.bind_changed` from the switch's model before
rendering. Rendered from the Lab 9 export and its switches' own versions, all five switches
render to exactly the OpenFlow layer their 2026-11-06 captures show (tests/test_openflow_golden.py).

The traditional router's pieces belong to section 4 (piece 3): its DHCP pools and options for
ZTP, and the inter-VLAN and management lines. The router is a Cisco IOS device Mercury already
deploys through intent.

## 3. Draft until confirmed, and only a confirmed template is sent

- **A template is `draft` on a network** until a verified person confirms it against a saved
  capture of one of its devices: the capture of a discovery read (docs/LAB9_DISCOVERY.md
  section 5).
- **The confirmation is committed** to the network's repository as that person
  (`openflow_confirmations/<template>.yml`). It names the capture, the capture's SHA-256 and the
  template's SHA-256. If the template changes, it is a draft again.
- **Only a confirmed template is ever sent.** `openflow_templates.push_refusal` is the one
  rule, and every path that sends a template's lines asks it first:
  - today that is the OVS operation;
  - a vendor driver will have to ask it too, when one exists;
  - the discovery drivers refuse every write at the session as well.
- **Confirming is a decision, not labour.** The person reads the capture and judges that the
  template's syntax fits the device's release.

## 4. Open vSwitch end to end (`modules/sdn/ovs_config.py`)

1. **Values** are read from NetBox (section 1).
2. **Render:** the `ovs` template, one transaction.
3. **Read before:** the bridge as it is now, by OVS's reads only. From that comes the **undo**,
   one transaction that puts back exactly what this one changes. If the bridge did not exist,
   the undo deletes it. A setting Mercury could not put back is refused here, before anything is
   sent (a `ptcp:` or `unix:` controller target, say).
4. **Hash:** over the program, the undo and the before. The preview shows all three, with each
   value and where it came from, and the template's status.
5. **Apply:**
   - refused unless the template is confirmed;
   - planned again, and refused, naming both hashes, if anything moved;
   - **the server held**, across processes, while the transaction is sent.
6. **Verify:**
   - the bridge is read back: its controller, protocols, fail mode, ports and datapath id,
     and each OpenFlow port's number as OVS gave it against NetBox's (a request OVS could not
     honour fails verify by name, C2603);
   - then the **controller's switch list** (the Mercury connection the config context's
     `openflow.connection` names, or the network's only one) is read up to 6 times, 2 s apart,
     until the bridge's datapath id is in it.
7. **Rollback:** on a failed send or check, the undo is sent and the bridge is read again.
   The result says whether it reads as it did before.
8. **Record:** the whole run goes into the network's SDN operation record. History shows it as
   "OpenFlow configuration on <server>".

**What the session to an OVS server may carry** (`modules/sdn/ovs.py`, driver `ovs_linux`):
- **reads:** `ovs-vsctl --version`; `sudo -n ovs-vsctl` `show`, `list-br`, `list controller`
  (target and is_connected), and per bridge `get-controller`, `get-fail-mode`, `list-ports`,
  `get bridge … protocols` or `datapath_id`, and per port `get interface … ofport_request` or
  `ofport`; `sudo -n ovs-ofctl -O OpenFlow13 show <bridge>`;
- **one write, only while held:** the transaction's shapes, with every argument one token of
  its shape and no shell character;
- **never Linux's `enable()`:** that is `sudo -s`, a root shell.

An IOS session refuses every one of these commands, held or not.

**The server's base setup** (A1, by hand): a login for Mercury, and a sudoers line that lets it
run `ovs-vsctl` and `ovs-ofctl` with no password (`sudo -n` never prompts). In NetBox the server
needs:
- a platform mapped to `ovs_linux` on Settings › Installation › Platforms and roles;
- the custom field `openflow_instance` (the bridge);
- its OpenFlow interfaces tagged `openflow`, each with its `openflow_port`.

## 5. What tomorrow's sitting can use, and what it cannot

- **It can:**
  - read every switch and server with its capture list, including each vendor's ZTP status
    (docs/LAB9_DISCOVERY.md); OVS servers are read through `ovs_linux`;
  - keep the answers as named captures, the input to the confirm step.
- **It cannot yet:**
  - **preview, confirm or apply from a screen.** The operation and the confirm step exist as
    code with their tests. Their controls are new controls, so each needs a board first (the
    Phase 7 mode), and the board is still to be drawn, before OVS's checkpoint on 2026-11-12.
    There is no terminal route around it;
  - send a vendor template: there is no driver for any vendor.
