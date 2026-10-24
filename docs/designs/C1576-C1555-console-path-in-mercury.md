# C1576 and C1555: making a device's console path in Mercury (design note, not built)

The register's rows C1576 and C1555: setting up out-of-band ZTP still means opening NetBox's
UI twice. Once to make the console-server device (C1555), and once to make the device's
console port and the cable to the server's port (C1576). Under the one-interface rule
(C1445), both are tasks a Mercury workflow needs. Written 2026-10-24 by the overnight run,
for the operator's review.

## What already exists

- `console_path.plan_console_path` and `ensure_console_path` build the device's side, the
  console port and the cable, behind NetBox's write gate. Each has a dry-run plan and a hash,
  and the authority is `console_path.authority_for`. No screen calls them.
- The Console servers tab lists console servers. It says "A console server's own device and
  port are made in NetBox first".

## The design: two previews over the existing writers

1. **The console server (C1555), on the Console servers tab:** an **Add a console server…**
   preview names the device NetBox will get, the ports Mercury will make, and the tag and
   created-object record each will carry. A confirm by hash then writes through NetBox's three
   write chokepoints, under the master switch and a declared authority. Each object is tagged
   and recorded as made, so Retire (and C1597's scoping) can tell it is Mercury's.
2. **The device's console path (C1576), on Add device's console offer:** **Cable its
   console…** runs `plan_console_path` for the device and the server port the person picks
   (the free ports listed, read from NetBox), shows the plan and its hash, and confirms through
   `ensure_console_path`. The offer already knows the device and the server.
3. **Removal:** Retire's existing NetBox step removes the device's port and cable only when
   recorded as made (provenance). A console server's own removal is its own preview, refused
   while any device's cable lands on it.

## Rules it follows

- **A preview writes nothing**, the created-object record included (C1596, in code
  2026-10-24).
- **IPv6:** no address is involved; the console server's management address, if asked, is
  validated like any other, with its IPv6 case.
- **New screens and controls need a mockup and the operator's sign-off first.** Both previews
  are new controls.

## Size

- **M.** The two previews and their routes (declared in `route_gates` and `invalidation`),
  about a day and a half with tests on the fake NetBox; the boards and their fidelity
  comparisons, about a day; the manual's sections and a walk on a throwaway, half a day.
