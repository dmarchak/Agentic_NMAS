"""The preflight's two network checks for the dual-homed laptop (the operator, 2026-11-05;
docs/LAB9_LAPTOP_RUN.md section 7):

1. **The lab profile:** the NetworkManager profile (`LAB_PROFILE`, "lab9") is bound to the lab
   interface with never-default and ignore-auto-dns for IPv4 and IPv6. Once a cable is in, it
   must be the active connection on that interface; without carrier it is ready, not active.
2. **The default route stays on the Wi-Fi** (`WIFI_IF`): every IPv4 and IPv6 default route
   names it, and none names the lab interface.

    python3 -I kit_net_check.py profile|routes

The raw outputs come in the environment (the preflight runs the commands):
- `NM_PROFILE`: `nmcli -g connection.interface-name,ipv4.never-default,ipv6.never-default,ipv4.ignore-auto-dns,ipv6.ignore-auto-dns connection show <profile>`;
- `NM_ACTIVE`: `nmcli -t -f NAME,DEVICE connection show --active`;
- `CARRIER`: `1` when the lab interface has carrier;
- `ROUTE4` and `ROUTE6`: `ip route show default` and `ip -6 route show default`;
- `LAB_IF`, `WIFI_IF` and `LAB_PROFILE`.

One PASS or FAIL line; exit 0 or 1.
"""
import os
import sys

FIELDS = ("connection.interface-name", "ipv4.never-default", "ipv6.never-default",
          "ipv4.ignore-auto-dns", "ipv6.ignore-auto-dns")


def judge_profile(profile_out: str, active_out: str, carrier: bool, lab_if: str,
                  name: str) -> tuple:
    vals = [v.strip() for v in (profile_out or "").splitlines()]
    if len(vals) < len(FIELDS) or not vals[0]:
        return False, (f"the NetworkManager profile {name!r} was not found (nmcli connection "
                       f"show {name}); create it on {lab_if} as section 7 says")
    got = dict(zip(FIELDS, vals))
    if got["connection.interface-name"] != lab_if:
        return False, (f"the profile {name!r} is bound to "
                       f"{got['connection.interface-name']!r}, not the lab interface {lab_if!r}")
    off = [k for k in FIELDS[1:] if got[k] != "yes"]
    if off:
        return False, (f"the profile {name!r} has " + ", ".join(f"{k} {got[k]!r}" for k in off)
                       + ", where each must be 'yes' (the Wi-Fi keeps the default route and "
                       "the resolver)")
    active = {}
    for line in (active_out or "").splitlines():
        cname, _, dev = line.rpartition(":")
        if cname:
            active[dev] = cname.replace("\\:", ":")
    if not carrier:
        return True, (f"{name!r} is ready on {lab_if} (never-default and ignore-auto-dns, IPv4 "
                      "and IPv6), not active: no carrier; it activates when the cable is in")
    if active.get(lab_if) != name:
        return False, (f"{lab_if} has carrier but its active connection is "
                       f"{active.get(lab_if) or 'none'!r}, not {name!r} (nmcli con up {name})")
    return True, f"{name!r} is active on {lab_if}, never-default and ignore-auto-dns"


def _devs(routes: str) -> list:
    out = []
    for line in (routes or "").splitlines():
        words = line.split()
        if "dev" in words and words.index("dev") + 1 < len(words):
            out.append(words[words.index("dev") + 1])
    return out


def judge_routes(route4: str, route6: str, wifi_if: str, lab_if: str) -> tuple:
    d4, d6 = _devs(route4), _devs(route6)
    if not d4:
        return False, "no IPv4 default route"
    for fam, devs in (("IPv4", d4), ("IPv6", d6)):
        bad = [d for d in devs if d != wifi_if]
        if bad:
            on_lab = " (the lab interface)" if lab_if in bad else ""
            return False, (f"an {fam} default route via {', '.join(sorted(set(bad)))}{on_lab}, "
                           f"where it must stay on {wifi_if}")
    return True, (f"IPv4 via {wifi_if}" + (f", IPv6 via {wifi_if}" if d6 else ", no IPv6 "
                                            "default route"))


if __name__ == "__main__":
    e = os.environ.get
    what = sys.argv[1] if len(sys.argv) > 1 else ""
    if what == "profile":
        ok, words = judge_profile(e("NM_PROFILE", ""), e("NM_ACTIVE", ""), e("CARRIER") == "1",
                                  e("LAB_IF", ""), e("LAB_PROFILE", "lab9"))
        label = "lab profile"
    elif what == "routes":
        ok, words = judge_routes(e("ROUTE4", ""), e("ROUTE6", ""), e("WIFI_IF", ""),
                                 e("LAB_IF", ""))
        label = "default route stays on the Wi-Fi"
    else:
        sys.exit(__doc__)
    print(f"{'PASS' if ok else 'FAIL'} {label}: {words}")
    sys.exit(0 if ok else 1)
