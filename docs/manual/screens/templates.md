# Templates

The network's configuration templates, one per platform, each with its approval, the devices
bound to it, and the one action it needs: **Approve…** or **Revoke…**. The page names its
network (`/v2/templates?list=<network>`). Editing a template and changing which template a
device renders through stay on today's Templates tab until the redesign builds them.

## What an approval covers {#what-it-is-for}

A deploy renders a device's intent through its template, and only through an APPROVED one. An
approval is a claim about the TEMPLATE: its text and every macro file it imports, as they are
now (their combined fingerprint), and the person who approved it. Editing the template or any
file it imports revokes it at once.

It does not say every device renders faithfully. Each device is checked at its own deploy, and
a device the template cannot reproduce is blocked there alone, with the lines named.

## The table {#table}

The counts come first: approved, not approved, revoked, and how many files are behind the
shipped version. Then one row per template:

- **Template**: its path, and how many files it imports. A shared macro file (`_common.j2`) has
  a row of its own too, since it is the file a shipped fix most often changes; it has no
  approval of its own, and the templates that import it carry the approval that covers it.
- **Devices bound**: the devices it renders, each a link to its page; more than three collapse.
- **Against the shipped version**: current; behind (an older shipped version, unedited), with
  **Bring in the shipped version…** on its row (see
  [Bring in a shipped template](bring-template)); edited here on purpose; or edited and
  behind, a merge a person makes. A file the tool does not ship is the network's own.
- **Approval**: approved (by whom, when); revoked (the reason, and who); or not approved, with
  why: never approved, stale because the template was edited, or approved in the record but
  not yet committed. A template no device is bound to cannot be approved: nothing can validate
  it.

The table redraws itself whenever anyone approves, revokes, edits a template or changes a
binding, here, in another tab or on today's Templates tab. A card you have open below it stays
as it is; its confirm checks again.

## Approve… {#approve}

Opens the check below the table: every bound device's captured configuration, parsed into
intent and rendered back through the template, compared line by line. Approval needs at
least one device that reproduces exactly. Each device says what was compared and every line
that failed: lines the render misses, lines it invents, sections it reorders, and lines the
parser does not model that the device's committed intent has not acknowledged, with a link to
acknowledge them on that device's Intent tab. A device's own lines (certificates, the licence
UDI, its self-signed trustpoint, AutoInstall's DHCP client-id) are listed apart and never
count. See [Approve a template](approve-template).

The confirm is bound to the fingerprint and the check you read: if either moved before you
confirm, nothing is approved and the card says what moved. The result replaces the card, and
the row says approved.

## Revoke… {#revoke}

Asks why. The reason is recorded with the revocation, committed, and shown on the row. Every
deploy through the template is refused until it is approved again.
