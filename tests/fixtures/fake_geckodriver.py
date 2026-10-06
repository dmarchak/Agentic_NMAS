"""A stand-in geckodriver for tests/test_home_untouched.py (C521): it answers /status, and on a
new-session request starts a child (its "Firefox") that keeps writing into TMPDIR, the
session's folder, and never answers. The shape CI #473 had: a Firefox whose session never
started, orphaned when only geckodriver was stopped."""
import os
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

CHILD = ("import os, time\n"
         "d = os.environ['TMPDIR']\n"
         "while True:\n"
         "    open(os.path.join(d, 'profile-%d' % (time.time() * 1000)), 'w').write('x')\n"
         "    time.sleep(0.05)\n")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        body = b'{"value": {"ready": true}}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        child = subprocess.Popen([sys.executable, "-c", CHILD])
        # Its pid, where the test reads it: the test checks it is gone and stops it if not.
        with open(os.environ["FAKE_GECKO_PIDFILE"], "w") as fh:
            fh.write(str(child.pid))
        time.sleep(3600)


if __name__ == "__main__":
    port = int(sys.argv[sys.argv.index("--port") + 1])
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
