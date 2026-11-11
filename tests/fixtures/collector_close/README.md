# `ss` listings for the collector's close helper (C3078)

Real output of `ss` (iproute2 6.19.0, kernel 7.0, x86-64) on the development laptop on
2026-11-11, each file exactly as `ss` printed it: no edit. The sessions were made on
documentation addresses, so nothing had to be rewritten for the publication scan.
`deploy/collector/mercury-collector-close` reads this output; tests/test_collector_close.py
stands in for `ss` over these rows.

**Only listings.** `ss -K` (the close) was never run to make a fixture, here or anywhere: the
helper judges a close by reading the listing back, and its own tests stand in for the close.

## How they were made

A throwaway script run as `unshare -rn python3 <script>`: a private network namespace of its
own, loopback only, nothing of the laptop's network in it. In that namespace it:

1. added 192.0.2.10, 192.0.2.6, 192.0.2.7 and 198.51.100.10 (each /32) and 2001:db8::10 and
   2001:db8:4::6 (each /128) to `lo`, and brought `lo` up;
2. opened three IPv4 listeners with Python sockets: 192.0.2.10 port 57000 (the collector's
   listener), 192.0.2.10 port 57001 (another port on the same address) and 198.51.100.10 port
   57000 (the same port on another address);
3. connected to them, each client bound to its source address and port first: 192.0.2.6 port
   56221 to all three listeners, and 192.0.2.7 port 51522 to 192.0.2.10 port 57000;
4. opened one dual-stack IPv6 listener on `::` port 57002, and connected to it from 192.0.2.6
   port 56222 over IPv4 (the kernel holds that session on an IPv6 socket, printed
   `[::ffff:...]`) and from 2001:db8:4::6 port 41714 over IPv6;
5. ran each listing below while every session stood.

Both ends of every session are in one namespace, so each session is listed twice: once from
the listener's side (the row a collector host holds) and once from the client's.

## The files

| File | The command |
|---|---|
| `established_all_4.txt` | `ss -H -4 -t -n state established`: the IPv4 sockets' table, nine rows |
| `established_all.txt` | `ss -H -t -n state established`: every socket's, twelve rows; the three more are the dual-stack listener's |
| `one_session.txt` | `ss -H -4 -t -n state established src 192.0.2.10 and sport = :57000 and dst 192.0.2.6 and dport = :56221`: the helper's find, one row |
| `no_session.txt` | `ss -H -4 -t -n state established src 192.0.2.10 and sport = :57000 and dst 192.0.2.6 and dport = :56222`: no session there, so empty |
| `dual_stack.txt` | `ss -H -t -n state established src 192.0.2.10 and sport = :57002 and dst 192.0.2.6 and dport = :56222`: the same filter without `-4` lists the IPv4 session the IPv6 socket holds; with `-4` it lists nothing |

## What they show

- With `state established` named, `ss` prints no State column: a row is `Recv-Q Send-Q
  Local-Address:Port Peer-Address:Port`, the local end third and the peer fourth. With `-H`
  there is no heading line.
- The four-ended filter lists exactly the one session: neither the same peer's session to
  another port of the listener's address nor its session to the same port of another address.
- `-4` keeps the listing to IPv4 sockets. A dual-stack listener's IPv4 session is on an IPv6
  socket and is not in it, which is why the helper says so by name instead of "no session".
- Each listing took 6 to 15 ms.
