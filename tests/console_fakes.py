"""Fake console servers on loopback for the console transports' tests (out-of-band ZTP, O2).

- `Console`: a scripted console on any byte pipe (a socket, an SSH channel). It prints its
  telnet negotiation and greeting, then, for every CR it receives, its next answer; it records
  EVERY byte it receives (`received`), the measure of what a driver wrote.
- `RawServer`: a TCP console server (IPv4 or IPv6 loopback), each connection a new `Console`.
- `SshServer`: paramiko's own server side with one host key, accepting ONE public key for ONE
  user. It records every sign-in it was offered (`auth`), every exec command (`commands`),
  and every ``direct-tcpip`` destination (`destinations`). An exec command on its allowlist
  is served as a console (the forced command's bridge); any other is refused as the wrapper
  refuses (a line on stderr, exit 2, closed). A ``direct-tcpip`` channel is pumped to its
  destination (a `RawServer`), so the server is the jump host too.

Every thread is a daemon and every server is closed by its fixture; the accept loop is woken
by `shutdown()` and joined before the socket is freed (tests/test_host_keys.py, CI #848)."""

import socket
import threading
import time

import paramiko

LOOPBACK = {socket.AF_INET: "127.0.0.1", socket.AF_INET6: "::1"}


def _thread(target, *args, name="test-console"):
    t = threading.Thread(target=target, args=args, daemon=True, name=name)
    t.start()
    return t


class Console:
    """One scripted console session on *pipe* (recv/sendall/close)."""

    def __init__(self, greeting: bytes = b"", answers=(), negotiate: bytes = b""):
        self.greeting, self.answers, self.negotiate = greeting, list(answers), negotiate
        self.received = b""
        self.done = threading.Event()

    def serve(self, pipe) -> None:
        try:
            if self.negotiate or self.greeting:
                pipe.sendall(self.negotiate + self.greeting)
            while True:
                data = pipe.recv(4096)
                if not data:
                    return
                self.received += data
                for _ in range(data.count(b"\r")):
                    if self.answers:
                        pipe.sendall(self.answers.pop(0))
        except (OSError, EOFError):
            return
        finally:
            try:
                pipe.close()
            except (OSError, EOFError):
                pass
            self.done.set()


class _Listener:
    """A loopback listener whose accept loop hands each connection to `_handle`."""

    def __init__(self, family=socket.AF_INET):
        self.host = LOOPBACK[family]
        self.accepted = 0
        self.sock = socket.socket(family, socket.SOCK_STREAM)
        self.sock.bind((self.host, 0))
        self.sock.listen(8)
        self.port = self.sock.getsockname()[1]
        self.stopping = threading.Event()
        self.thread = _thread(self._serve, name=f"test-{type(self).__name__}")

    def _serve(self):
        while not self.stopping.is_set():
            try:
                client, _ = self.sock.accept()
            except OSError:
                return
            if self.stopping.is_set():
                client.close()
                return
            self.accepted += 1
            _thread(self._handle, client)

    def _handle(self, client):
        raise NotImplementedError

    def finished(self, index: int = 0, wait: float = 5.0) -> Console:
        """The *index*th console served, once its client has gone (its thread may still be
        starting when the client is already done: waited for, bounded)."""
        deadline = time.monotonic() + wait
        consoles = getattr(self, "consoles", [])
        while len(consoles) <= index and time.monotonic() < deadline:
            time.sleep(0.01)
        assert len(consoles) > index, f"no console {index} was served within {wait} s"
        assert consoles[index].done.wait(max(0.0, deadline - time.monotonic()) + 1.0), \
            f"console {index} was still being served after {wait} s"
        return consoles[index]

    def close(self):
        self.stopping.set()
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.thread.join(5)
        self.sock.close()
        assert not self.thread.is_alive(), "a fake console server outlived its test"


class RawServer(_Listener):
    """A TCP console server: each connection is served by `make()`'s Console."""

    def __init__(self, make, family=socket.AF_INET):
        self.make = make
        self.consoles = []
        self.clients = []
        super().__init__(family)

    def _handle(self, client):
        console = self.make()
        self.consoles.append(console)
        self.clients.append(client)
        console.serve(client)

    def close(self):
        super().close()
        for c in self.clients:
            try:
                c.close()
            except OSError:
                pass


class Silent(_Listener):
    """Accepts a connection and never says anything (an SSH server whose banner never comes,
    or a console that never prints): the measure of a bound."""

    def __init__(self, family=socket.AF_INET):
        self.clients = []
        super().__init__(family)

    def _handle(self, client):
        self.clients.append(client)

    def close(self):
        super().close()
        for c in self.clients:
            c.close()


class _Answer(paramiko.ServerInterface):
    def __init__(self, server):
        self.server = server
        self.tcpip = {}

    def get_allowed_auths(self, username):
        return "publickey,password" if self.server.partial else "publickey"

    def check_auth_publickey(self, username, key):
        self.server.auth.append((username, key.get_name(), key.get_base64()))
        ok = username == self.server.user and key.get_base64() == self.server.client_b64
        if ok and self.server.partial:
            return paramiko.AUTH_PARTIALLY_SUCCESSFUL     # a second factor asked for
        return paramiko.AUTH_SUCCESSFUL if ok else paramiko.AUTH_FAILED

    def check_auth_password(self, username, password):
        self.server.auth.append((username, "password", password))
        return paramiko.AUTH_FAILED

    def check_channel_request(self, kind, chanid):
        if kind in ("session", "direct-tcpip"):
            return paramiko.OPEN_SUCCEEDED
        return paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

    def check_channel_direct_tcpip_request(self, chanid, origin, destination):
        self.server.destinations.append(tuple(destination))
        self.server.origins.append(tuple(origin))
        self.tcpip[chanid] = tuple(destination)
        return paramiko.OPEN_SUCCEEDED

    def check_channel_pty_request(self, *args):
        self.server.ptys += 1
        return False

    def check_channel_exec_request(self, channel, command):
        self.server.commands.append(command)
        _thread(self.server.exec_, channel, command, name="test-ssh-exec")
        return True


class SshServer(_Listener):
    """An SSH console server and jump host on loopback (see the module's docstring)."""

    def __init__(self, host_key, *, user: str, client_public: str, allow=(), make=None,
                 partial: bool = False,
                 family=socket.AF_INET):
        self.host_key, self.user = host_key, user
        self.client_b64 = client_public.split()[1]
        self.allow, self.make, self.partial = set(allow), make, partial
        self.auth, self.commands, self.destinations, self.origins = [], [], [], []
        self.ptys = 0
        self.consoles, self.transports = [], []
        super().__init__(family)

    def exec_(self, channel, command: bytes):
        name = command.decode("utf-8", "replace")
        if name not in self.allow:
            # sshd answers the exec request before its forced command runs; paramiko sends
            # the answer when `check_channel_exec_request` returns, so this thread lets it go
            # first (a close before the answer reads as "Channel closed" to the client).
            time.sleep(0.2)
            channel.sendall_stderr(f"nmas-console-bridge: refused: {name!r} is not on the "
                                   "allowlist\n".encode())
            channel.send_exit_status(2)
            channel.close()
            return
        console = self.make()
        self.consoles.append(console)
        console.serve(channel)

    def _handle(self, client):
        t = paramiko.Transport(client)
        t.add_server_key(self.host_key)
        self.transports.append(t)
        answer = _Answer(self)
        try:
            t.start_server(event=threading.Event(), server=answer)
        except Exception:                       # noqa: BLE001 - a client that left
            return
        while t.is_active() and not self.stopping.is_set():
            chan = t.accept(0.5)
            if chan is None:
                continue
            destination = answer.tcpip.get(chan.get_id())
            if destination:
                _thread(self._pump_to, chan, destination, name="test-ssh-tcpip")

    def _pump_to(self, chan, destination):
        try:
            far = socket.create_connection(destination, timeout=5)
        except OSError:
            chan.close()
            return
        far.settimeout(None)

        def copy(src, dst):
            try:
                while True:
                    data = src.recv(4096)
                    if not data:
                        break
                    dst.sendall(data)
            except (OSError, EOFError):
                pass
            finally:
                # shutdown first: a close() alone, while the other pump is blocked reading the
                # same socket, sends no FIN, and the console would never see its client go.
                for end in (src, dst):
                    try:
                        end.shutdown(socket.SHUT_RDWR)
                    except (OSError, EOFError):
                        pass
                    try:
                        end.close()
                    except (OSError, EOFError):
                        pass

        _thread(copy, chan, far, name="test-pump-out")
        _thread(copy, far, chan, name="test-pump-back")

    def close(self):
        super().close()
        for t in self.transports:
            t.close()
