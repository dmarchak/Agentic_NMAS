# Third-party components and their licences

{{product}} is built on other people's work. Every component it ships or depends on is listed
here with its version and licence, read from the repository's own inventory
(`docs/THIRD_PARTY.json`) each time this page opens, so the list is never a copy that drifts.
A check in the repository's tests holds that inventory to the files themselves: a file nobody
claims, or a component with a licence nobody has reviewed, fails it.

The interface's libraries are kept in the repository, never loaded from the internet, so the
tool works on a network with no outside access. Each one's licence file sits beside it, except
Alpine's, whose published package carries none: its text comes from its own repository.

{{third_party}}
