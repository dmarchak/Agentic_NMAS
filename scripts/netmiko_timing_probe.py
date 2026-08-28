"""
Standalone Netmiko timing probe — no app code involved.

Diagnostic tool for tracking down where SSH command latency is coming from
(TCP/SSH connect vs enable() vs prompt-based send_command vs timing-based
send_command_timing), independent of anything in modules/connection.py or
modules/commands.py.

Usage:
    python3 scripts/netmiko_timing_probe.py <ip> <username> <password> [secret]

Prints wall-clock time for each phase, once with fast_cli=True and once with
fast_cli=False, so the two modes can be compared directly.
"""
import sys
import time
from netmiko import ConnectHandler


def main():
    ip = sys.argv[1]
    username = sys.argv[2]
    password = sys.argv[3]
    secret = sys.argv[4] if len(sys.argv) > 4 else password

    for fast_cli in (True, False):
        print(f"\n=== fast_cli={fast_cli} ===")
        t0 = time.perf_counter()
        conn = ConnectHandler(
            device_type="cisco_ios",
            ip=ip,
            username=username,
            password=password,
            secret=secret,
            port=22,
            fast_cli=fast_cli,
        )
        t1 = time.perf_counter()
        print(f"connect:            {t1 - t0:.2f}s")

        conn.enable()
        t2 = time.perf_counter()
        print(f"enable():           {t2 - t1:.2f}s")

        out1 = conn.send_command("show version", read_timeout=60)
        t3 = time.perf_counter()
        print(f"send_command #1:    {t3 - t2:.2f}s  ({len(out1)} chars)")

        out2 = conn.send_command("show version", read_timeout=60)
        t4 = time.perf_counter()
        print(f"send_command #2:    {t4 - t3:.2f}s  ({len(out2)} chars)")

        out3 = conn.send_command_timing("show version", read_timeout=60)
        t5 = time.perf_counter()
        print(f"send_command_timing:{t5 - t4:.2f}s  ({len(out3)} chars)")

        conn.disconnect()
        t6 = time.perf_counter()
        print(f"disconnect:         {t6 - t5:.2f}s")


if __name__ == "__main__":
    main()
