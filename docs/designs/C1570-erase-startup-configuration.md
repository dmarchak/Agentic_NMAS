# C1570: an "Erase startup configuration" operation (design note, not built)

The register's row C1570: Mercury has no operation that erases a device's startup
configuration. A redo after Verify therefore cannot return a device to configless without a
person at its console, and that person needs the rotated credential. Today the only
hands-off way back is the lab's full redeploy, which restarts every device. Written
2026-10-24 by the overnight run, for the operator's review.

## What it would be

A device operation on the device page's Actions menu: **Erase startup configuration…**. It
follows the five stages every device-changing operation follows (CLAUDE.md).

1. **Preview, the exact program, masked:** `write erase` and its confirmation answer, then
   (optionally, in the same operation) the Reload, which follows Mercury's Reload preview
   (P.14). The preview says what is lost (the startup configuration, and the running one at
   the reload), and where it is kept: the device's last golden, by commit and date, and its
   committed intent.
2. **Confirm by hash as a verified person, with a reason.** The reload is inside a
   planned-restart window declared before it acts (`POST /restarts/planned`), as the Reload
   does today.
3. **Apply holding the device.** The device hold, one operation per device. The confirm
   prompt is answered only in reply to the prompt that asks it (send, read, decide).
4. **Verify.** Read back that `show startup-config` says it is not present. After a reload,
   the device is expected configless and answers only on its console; the result says so.
   It does not count that as a failure to reach it.
5. **Record.** A receipt with the sent lines and both reads. The device's page then offers
   **Retire** or a fresh **Add device**: the device is no longer what its golden and intent
   describe.

## Refusals

- A device that carries the management path to others is refused unless a repair route
  exists (CLAUDE.md, changing the path to a device), naming that path. In the lab, that is s3.
- Refused without a fresh golden, and the refusal names the golden's age. The erase must
  never be the only copy of the configuration.
- It is not in Run a privileged command. That menu holds only commands whose effect is read
  back and harmless (`privileged.COMMANDS`), and this one is neither.

## Size and dependencies

- **M.** The operation module modelled on `reload_op` and `privileged`, about a day; the
  screen (a new control: a mockup and sign-off first), about a day; the manual's How it works
  page and a walk on a throwaway device (never s3), half a day.
- Measure first: vIOS's and C8000v's exact `write erase` prompts and answers, read through a
  probe. Those prompts are what the session's state machine matches.
