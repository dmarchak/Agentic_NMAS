# Templates

The network's configuration templates, one per platform, and their approvals. The sidebar item
opens today's Templates tab until the redesign builds it (plan 7.6).

## What it is for {#what-it-is-for}

- **The library**: each template, and every file it imports, with what editing one revokes.
- **Approval**: an approval is a claim about the TEMPLATE (its files' combined hash, and who
  approved it), validated against the devices bound to it. It says what it covers and what it
  does not. A deploy needs the device's template approved, and each device's own plan says
  whether the template reproduces it.
- **Revoking** an approval records the reason.
