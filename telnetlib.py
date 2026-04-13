# telnetlib compatibility shim for Python 3.13+
# The telnetlib module was removed from Python 3.13's standard library
# This provides a minimal implementation for netmiko compatibility
# Note: Actual telnet functionality is not supported - use SSH instead

import socket
import selectors
import warnings

__all__ = ["Telnet", "TELNET_PORT"]

TELNET_PORT = 23

# Telnet protocol characters
IAC  = bytes([255])  # Interpret As Command
DONT = bytes([254])
DO   = bytes([253])
WONT = bytes([252])
WILL = bytes([251])
SB   = bytes([250])  # Sub-negotiation Begin
SE   = bytes([240])  # Sub-negotiation End

# Telnet protocol options
ECHO = bytes([1])
SGA = bytes([3])  # Suppress Go Ahead
TTYPE = bytes([24])  # Terminal Type
NAWS = bytes([31])  # Window Size
LINEMODE = bytes([34])


class Telnet:
    """Telnet interface class - minimal implementation for compatibility."""

    def __init__(self, host=None, port=0, timeout=None):
        self.debuglevel = 0
        self.host = host
        self.port = port or TELNET_PORT
        self.timeout = timeout
        self.sock = None
        self.rawq = b''
        self.irawq = 0
        self.cookedq = b''
        self.eof = False
        self.option_callback = None

        if host is not None:
            self.open(host, port, timeout)

    def open(self, host, port=0, timeout=None):
        """Connect to a host."""
        self.eof = False
        if not port:
            port = TELNET_PORT
        self.host = host
        self.port = port
        self.timeout = timeout
        self.sock = socket.create_connection((host, port), timeout)

    def close(self):
        """Close the connection."""
        sock = self.sock
        self.sock = None
        self.eof = True
        if sock:
            sock.close()

    def __del__(self):
        self.close()

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.close()

    def read_until(self, match, timeout=None):
        """Read until a given string is encountered or until timeout."""
        if timeout is None:
            timeout = self.timeout

        deadline = None
        if timeout is not None:
            import time
            deadline = time.monotonic() + timeout

        while True:
            i = self.cookedq.find(match)
            if i >= 0:
                i += len(match)
                buf = self.cookedq[:i]
                self.cookedq = self.cookedq[i:]
                return buf

            if self.eof:
                break

            if deadline is not None:
                import time
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                timeout = remaining

            self.fill_rawq()
            self.process_rawq()

        return self.read_very_lazy()

    def read_all(self):
        """Read all data until EOF."""
        self.process_rawq()
        while not self.eof:
            self.fill_rawq()
            self.process_rawq()
        buf = self.cookedq
        self.cookedq = b''
        return buf

    def read_some(self):
        """Read at least one byte unless EOF is hit."""
        self.process_rawq()
        while not self.cookedq and not self.eof:
            self.fill_rawq()
            self.process_rawq()
        buf = self.cookedq
        self.cookedq = b''
        return buf

    def read_very_eager(self):
        """Read everything that can be read without blocking."""
        self.process_rawq()
        while not self.eof and self.sock_avail():
            self.fill_rawq()
            self.process_rawq()
        return self.read_very_lazy()

    def read_eager(self):
        """Read readily available data."""
        self.process_rawq()
        while not self.cookedq and not self.eof and self.sock_avail():
            self.fill_rawq()
            self.process_rawq()
        return self.read_very_lazy()

    def read_lazy(self):
        """Process and return data already in the queues."""
        self.process_rawq()
        return self.read_very_lazy()

    def read_very_lazy(self):
        """Return data in cooked queue."""
        buf = self.cookedq
        self.cookedq = b''
        return buf

    def read_sb_data(self):
        """Return any data available in the SB buffer."""
        return b''

    def set_option_negotiation_callback(self, callback):
        """Set callback for option negotiation."""
        self.option_callback = callback

    def process_rawq(self):
        """Transfer from raw queue to cooked queue."""
        buf = [b'', b'']
        try:
            while self.rawq:
                c = self.rawq_getchar()
                if c == IAC:
                    c2 = self.rawq_getchar()
                    if c2 == IAC:
                        buf[0] += c
                    elif c2 in (DO, DONT, WILL, WONT):
                        opt = self.rawq_getchar()
                        if self.option_callback:
                            self.option_callback(self.sock, c2, opt)
                    elif c2 == SB:
                        # Skip sub-negotiation
                        while True:
                            c3 = self.rawq_getchar()
                            if c3 == IAC:
                                c4 = self.rawq_getchar()
                                if c4 == SE:
                                    break
                else:
                    buf[0] += c
        except EOFError:
            self.eof = True
        self.cookedq += buf[0]

    def rawq_getchar(self):
        """Get one character from the raw queue."""
        if not self.rawq:
            self.fill_rawq()
            if self.eof:
                raise EOFError
        c = self.rawq[self.irawq:self.irawq+1]
        self.irawq += 1
        if self.irawq >= len(self.rawq):
            self.rawq = b''
            self.irawq = 0
        return c

    def fill_rawq(self):
        """Fill the raw queue by reading from the socket."""
        if self.irawq >= len(self.rawq):
            self.rawq = b''
            self.irawq = 0
        buf = self.sock.recv(50)
        self.eof = not buf
        self.rawq += buf

    def sock_avail(self):
        """Check if data is available on the socket."""
        with selectors.DefaultSelector() as selector:
            selector.register(self.sock, selectors.EVENT_READ)
            return bool(selector.select(0))

    def write(self, buffer):
        """Write a string to the socket."""
        if isinstance(buffer, str):
            buffer = buffer.encode('ascii')
        self.sock.sendall(buffer)

    def get_socket(self):
        """Return the socket object."""
        return self.sock

    def fileno(self):
        """Return the file descriptor of the socket."""
        return self.sock.fileno()

    def msg(self, msg, *args):
        """Print a debug message if debug level is > 0."""
        if self.debuglevel > 0:
            print('Telnet(%s,%s):' % (self.host, self.port), msg % args)

    def set_debuglevel(self, debuglevel):
        """Set the debug level."""
        self.debuglevel = debuglevel

    def expect(self, list, timeout=None):
        """Read until one of the expected strings or regex matches."""
        import re
        if timeout is None:
            timeout = self.timeout

        deadline = None
        if timeout is not None:
            import time
            deadline = time.monotonic() + timeout

        indices = range(len(list))
        compiled = []
        for s in list:
            if isinstance(s, (str, bytes)):
                compiled.append(re.compile(s if isinstance(s, bytes) else s.encode('ascii')))
            else:
                compiled.append(s)

        while True:
            self.process_rawq()
            for i in indices:
                m = compiled[i].search(self.cookedq)
                if m:
                    text = self.cookedq[:m.end()]
                    self.cookedq = self.cookedq[m.end():]
                    return (i, m, text)

            if self.eof:
                break

            if deadline is not None:
                import time
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                timeout = remaining

            self.fill_rawq()

        text = self.read_very_lazy()
        return (-1, None, text)

    def interact(self):
        """Interaction function (not fully implemented)."""
        warnings.warn("Telnet.interact() is not fully supported in this compatibility shim")
