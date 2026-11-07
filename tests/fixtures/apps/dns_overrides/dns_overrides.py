"""Decides a DNS query by the app's overrides: block wins over allow, and `*.` covers every
name under a zone, never the zone itself. A name neither decides is left to the verdict
service ("ask")."""


def matches(pattern, name):
    """Whether *name* is the domain *pattern*, or under it when it starts `*.`."""
    name = name.lower().rstrip(".")
    pattern = pattern.lower().rstrip(".")
    if pattern.startswith("*."):
        return name.endswith("." + pattern[2:])
    return name == pattern


def decide(config, name):
    """`block`, `allow` or `ask` for a query for *name*, by *config*'s overrides."""
    overrides = config.get("overrides", {})
    if any(matches(p, name) for p in overrides.get("block", [])):
        return "block"
    if any(matches(p, name) for p in overrides.get("allow", [])):
        return "allow"
    return "ask"
