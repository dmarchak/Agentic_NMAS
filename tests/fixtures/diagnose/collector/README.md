# The collector's side of a telemetry stream (C2828)

Real rows of a Linux kernel's socket and address tables, read on the development laptop on
2026-11-08 (kernel 7.0, x86-64, little-endian, `net.ipv6.bindv6only` 0), with the addresses
moved to the documentation ranges for the publication scan. The lost-stream runbook
(`modules/heal/diagnose_stream.py`, `read_collector`) reads the same four files under
`/proc` on Mercury's host, where Telegraf listens.

**How they were made.** A throwaway script on the laptop, loopback only: an IPv4 listener bound
to 127.0.0.1 port 57000 with a session to it from 127.0.0.2; a dual-stack IPv6 listener on `::`
port 57001 with one session from 127.0.0.2 over IPv4 (which the kernel prints in `tcp6` as
`::ffff:127.0.0.2`) and one from `::1`. Each table was read while the sessions stood, and its
rows naming either port kept.

**The edits, and nothing else:**
Each file is named as its table is under `/proc/net/`.

- `tcp`: 127.0.0.1 (the listener's and the server side's local address) written
  as 192.0.2.10 (the collector), the session's far end 127.0.0.2 port 33615 as 192.0.2.6 port
  60235 (the device; the port r7's session used in H11 W8). The server-side row copied once,
  its far end written as 192.0.2.7 port 51522: a session from another device. The client-side
  rows dropped (on the collector, a device's own socket is not there).
- `tcp6`: the listener's port 57001 written as 57000; the IPv4 session's
  `::ffff:127.0.0.1` and `::ffff:127.0.0.2` port 46547 as `::ffff:192.0.2.10` and
  `::ffff:192.0.2.6` port 60235; the IPv6 session's `::1` (local) as 2001:db8::10 and `::1`
  (far end) as 2001:db8:4::6, its far port kept. The client-side row dropped.
- `if_inet6`: the loopback line as read, and one global address line of the
  laptop's wireless interface, its address written as 2001:db8::10; the other lines (link-local
  and bridge addresses) dropped.
- `fib_trie`: the whole trie, each address outside 127/8 and 0.0.0.0 written as a
  documentation address: the wireless segment's network, the laptop's own address and the
  broadcast as 192.0.2.0, 192.0.2.10 and 192.0.2.255, and the container bridges' as
  198.51.100.x. The structure (which leaf is `/32 host LOCAL`) is as read.

Each table's address words are as the kernel prints them: four bytes in host byte order per
32-bit word, so 192.0.2.10 is `0A0200C0` on this little-endian machine.

## Each session's last receive: the kernel's socket diagnostics (C2892)

`/proc/net/tcp` carries no time of the last data received, so a session standing ESTABLISHED
cannot be told from one carrying data. The kernel's socket diagnostics (inet_diag) carry it, as
`ss -tni state established "( sport = :<port> )"` prints them: each session's `bytes_received`
and `lastrcv` (milliseconds since the last segment received). Measured read-only on Mercury's
host on 2026-11-10 at 17:12 UTC (the coordinator's read): the one session of the router whose
stream was lost read `bytes_received:828` and `lastrcv:5966281` (nothing for 99 minutes), while
the six streaming devices' read 172 to 766 KB and `lastrcv` at or under 8069 ms.

- `ss_tni_4.txt` and `ss_tni_6.txt`: `ss -tni` (iproute2 6.19.0) on the development laptop on
  2026-11-10, loopback only, from a throwaway script: an IPv4 listener on 127.0.0.1 port 57000
  with two sessions from 127.0.0.2 (one sent 20 x 8000 bytes just before the read, one sent
  828 bytes once and went quiet), and a dual-stack IPv6 listener on `::` port 57001 with one
  session over IPv4 (printed `[::ffff:127.0.0.2]`) and one from `::1`, each sending 1500 bytes.
  **The edits, and nothing else:** the heading lines' trailing padding removed; 127.0.0.1 as
  192.0.2.10 (the collector); the busy session's far end 127.0.0.2 port 51377 as 192.0.2.7
  port 51522 (another device, as `tcp`'s), the quiet one's 127.0.0.2 port 45025 as 192.0.2.6
  port 60235 (the device, as `tcp`'s) and its `lastrcv` 4245 as 5966281, the host's measured
  value above (the script waited seconds, not 99 minutes); in `ss_tni_6.txt` the port 57001 as
  57000, `::1` (local) as 2001:db8::10 and `::1` port 52555 (far end) as 2001:db8:4::6 port
  41714, and `::ffff:127.0.0.1` and `::ffff:127.0.0.2` port 37373 as `::ffff:192.0.2.10` and
  `::ffff:192.0.2.6` port 60235. Every other word as `ss` printed it.
