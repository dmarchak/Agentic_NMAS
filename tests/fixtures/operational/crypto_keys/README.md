# `show crypto key mypubkey rsa`, three devices (C2239)

Each file is one device's answer as Mercury's Show commands recorded it on 2026-11-01 at
09:18 UTC (run 20261101T091840…, by the overnight run for the operator, read-only), masked by
the run (each key's non-exportable line reads `Key <redacted:server_key>`). The public key data
is the devices' own.

| File | Device | What it shows |
|---|---|---|
| `r1.txt` | a C8000v (IOS-XE 17.6) | two general-purpose key pairs, the host-named one and a self-signed one, both `Storage Device: private-config`; an encryption key pair |
| `r8.txt` | a C8000v | the same shape: two saved general-purpose key pairs. It came back from a planned Reload on 2026-10-30 serving another SSH host key (C2239) |
| `s1.txt` | a vIOS-L2 switch (15.2) | one general-purpose key pair, `Storage Device: not specified`: not saved, as every vIOS-L2 switch read that day |

**The one edit:** the lab's domain name replaced by `example.com` in each key's name.
