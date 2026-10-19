# Third-party components and their licences

{{product}} is built on other people's work. Every component it ships or depends on is listed
here with its version and licence, read from the repository's own inventory
(`docs/THIRD_PARTY.json`) each time this page opens, so the list is never a copy that drifts.
A check in the repository's tests holds that inventory to the files themselves: a file nobody
claims, or a component with a licence nobody has reviewed, fails it.

The interface's libraries and fonts are kept in the repository, never loaded from the
internet, so the tool works on a network with no outside access. Each one's licence file sits
beside it. Alpine's published package carries none, so the file beside it holds the text from
Alpine's own repository, at the release's tag. The first list also names a file the tool
generates and ships for its monitoring (the SNMP exporter's routing modules, built from
standard and Cisco MIBs), whose terms are its own entry in the inventory.

{{third_party}}
