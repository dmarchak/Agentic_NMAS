# Ryu 4.34 fixtures (`ryu.app.ofctl_rest`)

The Ryu driver's tests (tests/test_sdn_ryu.py) read these. Every one came from Ryu 4.34's own
code, in the image `mercury-ryu-trial:4.34` (lab/sdn/ryu/Dockerfile: `ryu.app.ofctl_rest` and
the lab's L4 application), on the development laptop, 2026-10-26. None is typed.

| File | How it was made | What is real, what was chosen |
|---|---|---|
| `rest_no_switch.json` | Captured ~23:19 UTC with `curl -i` against the image running alone (no switch connected): `GET /stats/switches`, `GET /stats/flow/1`, `GET /stats/flow/abc`, `POST /stats/flowentry/add` (a switch that is not there; a body with JSON's `true`), `GET /v1.0/topology/links`, `POST /stats/flowentry/bogus`. The one edit: the `Date` header dropped. | All of it: Ryu's own answers. |
| `rest_with_peer.json` | Captured ~23:35 UTC: the Ryu driver itself (real `requests`, a recording session) against the image, with `peer_switch.py` connected as datapath 1 (a scripted OpenFlow 1.3 peer, since Mininet needs root). Sixteen answers, raw: every read, each write (meter add, three flow adds, a strict delete, a meter delete), a switch that is not there, and a body with JSON's `true`. | The HTTP answers, the JSON shapes and every conversion (`dl_src` for eth_src, `tp_dst` for tcp_dst and udp_dst alike, `OUTPUT:CONTROLLER`, `METER:1`, `{"WRITE_ACTIONS": [...]}`, an empty action list for a drop, `LOCAL` for the local port, a VLAN as a decimal string) are Ryu's. The flows, ports, meters and description the peer served are the author's choice of what the lab's application and Mercury's responses would install (`render_with_ryu.py`'s functions); addresses are documentation ranges (192.0.2.0/24, 2001:db8::/32). |
| `peer_log.json` | Written by `peer_switch.py` during the same run: every FLOW_MOD (decoded by Ryu's own parser) and METER_MOD (by its pack strings) that reached the peer. | All of it: what Ryu put on the wire. The first FLOW_MOD is the application's table-miss on connect; the rest are the driver's writes, so the tests can hold that each rendered body became the message it meant (a DELETE_STRICT with the whole cookie masked; meter flags 13 = KBPS, BURST, STATS). |
| `flow_stats_empty.json`, `meter_stats_empty.json`, `meter_config_empty.json` | **Rendered by Ryu 4.34's own ofctl_v1_3 serialisers, no switch connected; to be replaced by a capture from the operator's first Mininet run.** `render_with_ryu.py`: an empty multipart reply built as wire bytes, parsed by Ryu's `ofproto_parser.msg`, handed to `ofctl_v1_3.get_flow_stats` / `get_meter_stats` / `get_meter_config` through a dummy datapath as Ryu's own tests do, and `json.dumps` of the result, as `ofctl_rest` answers. | The shape is Ryu's; there are no entries to choose. |

| `topology_rest.json` | **Captured 2026-10-27 ~09:35 UTC from the lab's controller on the NMAS host** (container `ryu`, Ryu 4.34 with `--observe-links`, `ryu.app.rest_topology`, `ofctl_rest` and the L4 application; lab/sdn/ryu/Dockerfile), read-only over its loopback REST through `scripts/nmas-host nmas -- curl -s -i`, while a Mininet fabric of two OpenFlow 1.3 switches was attached: `GET /stats/switches`, `/v1.0/topology/switches`, `/links`, `/hosts`. The one edit: the `Date` and `Content-Length` headers dropped. | All of it: Ryu's answers. The switches' port names and hardware addresses are Mininet's and Open vSwitch's; the hosts' addresses were the lab run's own choice of documentation ranges (192.0.2.0/24, 2001:db8:8::/64). Six hosts on two switches: Ryu keeps a host until it restarts, so two of them (random MACs, link-local IPv6 only) were left by earlier runs, and a host's port hardware address is the one it was learned on (Ryu compares ports by switch and number alone). |
| `lldp_from_ryu.json` | **Rendered by Ryu 4.34's own code**, `render_lldp_with_ryu.py` (run in the image as below): the LLDP frame Ryu's link discovery sends out of a port (`ryu.topology.switches.LLDPPacket.lldp_packet`) for two DPIDs and ports, parsed back by Ryu's own `ryu.lib.packet` and `LLDPPacket.lldp_parse`. | The frame and every field are Ryu's: chassis id subtype 7 (locally assigned) `dpid:<16 hex>`, port id subtype 2 (port component) the port number in four bytes, TTL, end, and no system name TLV. The DPIDs and ports are the author's choice. |

**To be replaced by a capture from the operator's first Mininet run:** `rest_with_peer.json`
and `peer_log.json` too, since a scripted peer is not a switch. What a real Open vSwitch will
differ in: its own counters, its description, its port names and numbers, and its meter
features (whether this Open vSwitch supports meters is the operator's check, PHASE8_PLAN 17.3).

**How each was made, to make it again** (from the repository's root, the image built):

```bash
# rest_no_switch.json: the image alone, then curl -i each request above
docker run -d --rm --name ryu-cap --network host mercury-ryu-trial:4.34
# the empty renders
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD/tests/fixtures/sdn/ryu:/out" \
    --entrypoint python mercury-ryu-trial:4.34 -B /out/render_with_ryu.py /out
# rest_with_peer.json and peer_log.json: the peer beside the running controller, then the
# driver's calls against http://127.0.0.1:8080 through a session recording each answer
docker run --rm --network host --user "$(id -u):$(id -g)" -v "$PWD/tests/fixtures/sdn/ryu:/out" \
    --entrypoint python mercury-ryu-trial:4.34 -B /out/peer_switch.py 127.0.0.1 6653 \
    /out/peer_log.json 25
docker stop ryu-cap
# lldp_from_ryu.json: Ryu's own LLDP frame, rendered in the image
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD/tests/fixtures/sdn/ryu:/out" \
    --entrypoint python mercury-ryu-trial:4.34 -B /out/render_lldp_with_ryu.py /out
# topology_rest.json: read-only from the controller on the NMAS host, a Mininet fabric attached
for p in /stats/switches /v1.0/topology/switches /v1.0/topology/links /v1.0/topology/hosts; do
    scripts/nmas-host nmas -- curl -s -i "http://127.0.0.1:8080$p"
done
```

`render_with_ryu.py`, `render_lldp_with_ryu.py` and `peer_switch.py` import `ryu`, which Mercury
does not install: they run only inside the image, never in the suite.
