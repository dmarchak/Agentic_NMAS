# Update the app

The app updates itself from Help > About or Needs attention, to the newest release CI has
passed, without holding any privilege itself.

## The preview

The preview shows the commits between the running version and the newest one, the release's
CI verdict, any step the host needs before or after (`Host-Step:`), and whether the checkout
on the host is clean. Each is a gate; any failing refuses the update.

## The steps, in order

The app writes a request and nothing else; a root-owned updater on the host does the rest,
and the Update page draws each step as it records it:

1. `request`: the app writes the update request, bound to the preview you confirmed.
2. `started`: the root-owned updater picks it up and checks its own programs.
3. `checkout`: the checkout has no local changes.
4. `fetch`: fetches the remote.
5. `ci`: re-checks CI for the target itself, never trusting the app's answer.
6. `move`: moves the checkout to the target, as the service user.
7. `restart`: restarts the app.
8. `wait`: waits for the new version to answer, by identity (the new process, the target
   commit), never by time.
9. `running`: the target is running.

A version that does not come up within its bound is rolled back to the commit it ran, and
the page says so.

## Update when CI passes

If CI is still checking the newest release, you can choose to update when it passes; the
app then writes the request itself when the verdict arrives, as you, and never installs a
newer release in its place.
