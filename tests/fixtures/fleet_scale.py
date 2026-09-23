"""A fleet of any size, with a realistic spread of states. Not a test module.

**Nine devices will pass every test written at nine devices.** Every design
choice between now and Stage 7 is being made against an implicit picture of
the inventory, and that picture is currently nine. This exists so the scale
question is answerable *while* a choice is being made rather than afterwards.

**A uniform fleet hides exactly the cases that make a list unusable.** 900
identical healthy devices render fast and prove nothing: it is the *mixture*
that forces filtering, because a list where every row looks the same needs no
filter and a list where they differ is unreadable without one. So the
generator spreads devices across sites, platforms and roles, and — the part
that matters — across **states**: some with goldens, some without, some
drifted, some unreachable, some on an unapproved template, some overdue for
rotation.

It writes **nothing** into `data/lists/`. The conftest guard refuses that for
tests; this is the same rule for anything that builds a fleet.
"""

import random

#: Deterministic by default: a scale measurement that moves between runs
#: cannot be compared to the one recorded yesterday.
SEED = 20260923

#: The two dialects this program speaks. Slugs and Netmiko drivers are
#: inputs; see `modules/nsot/platform.py`.
PLATFORMS = (
    ("cisco_iosxe", "cisco_xe"),
    ("cisco_ios", "cisco_ios"),
)

ROLES = ("core-router", "edge-router", "access-switch", "distribution-switch")

#: Proportions, chosen so every state has enough members to be filterable and
#: none dominates. A fleet that is 90% healthy makes the unhealthy rows hard
#: to find, which is the realistic case and the one a filter exists for.
STATE_MIX = {
    "healthy":            0.55,
    "no_golden":          0.10,
    "drifted":            0.08,
    "unreachable":        0.05,
    "unapproved_template": 0.07,
    "rotation_overdue":   0.15,
}


def _sites(count: int) -> list:
    """Enough sites that site is a useful filter, not so many it is a list."""
    return [f"site-{i:02d}" for i in range(1, max(2, count // 30) + 1)]


def build_fleet(count: int = 900, seed: int = SEED) -> list:
    """*count* device dicts shaped like `load_saved_devices()` output.

    Credentials are placeholders and are never real: this fixture is read by
    renderers and counters, never by anything that opens a session.
    """
    rng = random.Random(seed)
    sites = _sites(count)

    states = []
    for name, share in STATE_MIX.items():
        states.extend([name] * int(round(count * share)))
    while len(states) < count:
        states.append("healthy")
    states = states[:count]
    rng.shuffle(states)

    fleet = []
    for i in range(count):
        dialect, driver = PLATFORMS[i % len(PLATFORMS)]
        site = sites[i % len(sites)]
        role = ROLES[i % len(ROLES)]
        # 198.51.100.0/24 and 203.0.113.0/24 are TEST-NET ranges; the third
        # octet walks so the addresses stay distinct past 254 devices.
        octet3, octet4 = divmod(i, 254)
        fleet.append({
            "hostname":    f"{role.split('-')[0][:3]}{i:04d}",
            "ip":          f"198.51.{100 + octet3}.{octet4 + 1}",
            "device_type": driver,
            "platform":    dialect,
            "role":        role,
            "site":        site,
            "username":    "placeholder",
            "password":    "placeholder",
            "secret":      "placeholder",
            "_cred_source": "default profile",
            # The state is carried so a counter can be written and tested
            # against a known answer, rather than inferred from other stores
            # the fixture does not build.
            "_scale_state": states[i],
        })
    return fleet


def expected_counts(fleet: list) -> dict:
    """The landing view's six numbers, computed the slow, obvious way.

    **This is the oracle, not the implementation.** A bounded counter is
    tested against this; if the two disagree, one of them is wrong and the
    slow one is easier to be sure about.
    """
    counts = {name: 0 for name in STATE_MIX}
    for device in fleet:
        counts[device.get("_scale_state", "healthy")] += 1
    counts["total"] = len(fleet)
    return counts


def write_csv(path: str, fleet: list) -> str:
    """Write *fleet* as a devices.csv. **Never under `data/lists/`.**

    Refuses rather than trusting the caller: a fixture that can write into
    the live data directory is one `tmp_path` typo from doing it.
    """
    import csv
    import os

    from modules.config import LISTS_DIR

    resolved = os.path.abspath(path)
    if resolved.startswith(os.path.abspath(LISTS_DIR) + os.sep):
        raise ValueError(
            f"refusing to write a scale fixture into the live data directory "
            f"({LISTS_DIR}). Build it under tmp_path.")

    os.makedirs(os.path.dirname(resolved), exist_ok=True)
    columns = ("hostname", "device_type", "ip", "username", "password",
               "secret", "role")
    with open(resolved, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()
        for device in fleet:
            writer.writerow({c: device.get(c, "") for c in columns})
    return resolved
