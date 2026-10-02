# Credentials

How the tool finds the credential for each device. The sidebar item opens today's view until
the redesign builds it (plan 7.6).

## What it is for {#what-it-is-for}

A device's credential is found in this order, first match wins: its own override, the list's
designated credential list, a role profile, a site profile, the default profile. Every device
shows where its credential came from. Values are write-only: none is ever shown back.
