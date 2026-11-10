# dns_blacklist at the lab: the operator's test list

Lab 9 Objective 3. Run these once dns_blacklist 0.1.0 is Published and deployed through
Mercury (**SDN › Apps**, the app's row, choose **0.1.0**, **Preview deploying 0.1.0…**, then
confirm by hash; [Deploy apps to an SDN controller](../../../../docs/manual/how-it-works/controller-app-deploy.md)).
The deploy restarts the controller, so it declares its planned-restart window first. Keep
every step outside the nightly backup window (02:30 to 03:30 America/Denver), and run nothing
from s3.

**The demo's two names:** `malware.testcategory.com` (Cloudflare's documented test domain:
always bad) and `example.com` (always good).

## Before you start: two things that must hold, or the results mislead

1. **fabric_forwarding must leave this app's queries alone.** Both apps receive every
   packet-in. fabric_forwarding 0.2.0 forwards every packet-in it gets, so it would also
   forward each DNS query this app punts, blocked ones included: the host would then get the
   resolver's real answer, racing the block. Until fabric_forwarding ignores a packet-in whose
   cookie is not its own, a blocked name can still resolve. Check the version deployed beside
   this app before reading any result below.
2. **The bonus needs its config and a page.** The block page's address comes from the
   network's config for this app (`block_page.ipv4`, and `block_page.ipv6` for IPv6 hosts).
   No Mercury screen sets an app's network config yet; with none, a blocked name is
   dropped (the base objective), not answered. The page itself is a web server at that
   address that answers any request with a "blocked" page; this app does not serve it.

## The checks

Each check says where to look. **SDN › Apps** draws the app's `/health` as last read. The
decisions and counts are in the app's `/state` and `/health`, read from the controller's REST
API (`http://<controller>:8080/dns_blacklist/state` and `/health`) in a browser on the
management network: Mercury does not draw them yet, and that is a gap, not the intended way.

1. **The app is up and configured.**
   - Do: open **SDN › Apps** after the deploy's post-check finishes.
   - PASS: dns_blacklist is under **Running as recorded**, version 0.1.0, its /health ok.
     `/health` reads `"configured": true`, `"fail_mode": "open"`, `"served"` equal to
     `"switches"`, and `"problems": []`.
2. **DNS is steered on every switch, and only DNS.**
   - Do: **SDN › Flows**, each switch in turn.
   - PASS: on each switch, two flows per edge port with cookie `0x444e000000000001` (IPv4)
     and `0x444e000000000002` (IPv6), priority 1000, matching `in_port`, `ip_proto` 17 and `udp_dst`
     53, output CONTROLLER; on the ProCurve in table 100, elsewhere table 0. No flow of this
     cookie on an inter-switch link port, and none matching UDP 67 or 68. A host still gets
     its DHCP lease after the deploy.
3. **A good site is allowed.**
   - Do: on a lab host, open `http://example.com` in a browser.
   - PASS: the page loads. `/state`'s `decisions` holds `example.com`, verdict `good`,
     decision `allow`, source `lookup` (the first time) or `cache`; `last_answers.good.body`
     is the JSON verdict Cloudflare gave, with no `Comment`. `/health`'s counters: `queries`,
     `allowed` and `lookups` rose; `verdict_errors` did not.
4. **A bad site is blocked.**
   - Do: on the same host, open `http://malware.testcategory.com`.
   - PASS: the page does not load (no block page configured), or the block page shows (the
     bonus, check 6). `/state`'s `decisions` holds `malware.testcategory.com`, verdict `bad`,
     decision `drop` or `answer`; `last_answers.bad.body` carries `"data": "0.0.0.0"` and
     `"Comment": ["EDE(16): Censored"]`. `/health`'s `blocked` rose.
5. **The cache answers a repeat.**
   - Do: reload both pages within five minutes.
   - PASS: the same outcomes; `/health`'s `cache_hits` rose and `lookups` did not.
6. **Bonus: the browser shows the block page.**
   - Do: with `block_page` in the network's config and a page served at that address, open
     `http://malware.testcategory.com` in a browser on an IPv4 host, and on an IPv6 host if
     `block_page.ipv6` is set.
   - PASS: the browser shows the "blocked" page; `/state`'s decision is `answer`, and
     `/health`'s `answered` rose. A browser that tries HTTPS first shows a certificate warning
     before the page; that is expected, since the page cannot hold the blocked site's
     certificate.
7. **Both families.**
   - Do: checks 3 and 4 from a host with IPv6 only, or with IPv6 preferred.
   - PASS: the same outcomes; the decisions list the AAAA queries too.
8. **Hosts on every switch.**
   - Do: checks 3 and 4 from a host on each kind of switch (an Open vSwitch server, the
     Arista, the ProCurve).
   - PASS: the same outcomes on each. These read two behaviours not measured yet: whether the
     switch reports the flow's cookie in a packet-in, and whether it takes a packet-out to its
     own tables (output TABLE).
9. **The lookup's time, for its bound.**
   - Do: after the checks, read `/health`'s `verdict_service.lookup_seconds`.
   - PASS: `max` is under 0.8 s, so the 2 s bound is at least 2.5 times the slowest lookup.
     Send the number either way: the bound is set from it.

## On a FAIL, send

- the check's number, the host (and which switch it is on) and the UTC time;
- the app's `/health` and `/state`, copied whole from the browser;
- **SDN › Apps**' row for dns_blacklist, and the deploy's receipt (**Download the receipt
  (JSON)**);
- **SDN › Flows** for the switch the host is on: the flows with cookie `0x444e…`;
- what the browser showed.

What each failure usually means:

| What you see | Likely cause |
|---|---|
| A bad name sometimes resolves to a real address | fabric_forwarding is also forwarding the punted query (before you start, item 1) |
| No name resolves from one kind of switch; `queries` does not rise | that switch reports no cookie in its packet-ins, so the app does not take them as its own |
| No name resolves from one kind of switch; `allowed` rises | that switch refuses a packet-out to its own tables: set `upstream` to the port the resolver is on |
| Everything is allowed; `verdict_errors` rises; /health names the verdict service | the controller cannot reach `security.cloudflare-dns.com:443`, or its answer is not JSON (the app asks with `Accept: application/dns-json`, the one type the resolver answers; `application/json` gets a 405) |
| A blocked name is not answered with the block page | no `block_page` in the network's config (before you start, item 2) |
