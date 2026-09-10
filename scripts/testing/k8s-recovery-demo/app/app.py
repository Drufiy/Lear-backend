#!/usr/bin/env python3
"""checkout-api demo app.

On startup, tries to open a TCP connection to DATABASE_HOST:5432. If it
succeeds, serves a /healthz endpoint on :8080 and stays up. If it fails,
logs a clear error to stdout (visible via `kubectl logs`) and exits
non-zero, which causes CrashLoopBackOff under a Deployment -- the
intended failure mode for this demo.
"""
import http.server
import os
import socket
import sys
import time

DATABASE_HOST = os.environ.get("DATABASE_HOST", "")
DATABASE_PORT = int(os.environ.get("DATABASE_PORT", "5432"))
CONNECT_TIMEOUT = float(os.environ.get("DB_CONNECT_TIMEOUT", "3"))


RETRIES = int(os.environ.get("DB_CONNECT_RETRIES", "8"))
RETRY_DELAY = float(os.environ.get("DB_RETRY_DELAY", "1.5"))


def check_database():
    print(f"[checkout-api] starting up, DATABASE_HOST={DATABASE_HOST!r} DATABASE_PORT={DATABASE_PORT}", flush=True)
    last_err = None
    for attempt in range(1, RETRIES + 1):
        try:
            with socket.create_connection((DATABASE_HOST, DATABASE_PORT), timeout=CONNECT_TIMEOUT):
                print(f"[checkout-api] connected to {DATABASE_HOST}:{DATABASE_PORT} OK (attempt {attempt})", flush=True)
                return True
        except Exception as e:
            last_err = e
            print(f"[checkout-api] attempt {attempt}/{RETRIES}: could not reach {DATABASE_HOST}:{DATABASE_PORT} -- {type(e).__name__}: {e}", flush=True)
            if attempt < RETRIES:
                time.sleep(RETRY_DELAY)
    print(f"[checkout-api] FATAL: could not connect to database at {DATABASE_HOST}:{DATABASE_PORT} after {RETRIES} attempts -- {type(last_err).__name__}: {last_err}", flush=True)
    print(f"[checkout-api] check configmap/checkout-api-config key DATABASE_HOST -- current value is {DATABASE_HOST!r}", flush=True)
    return False


class Health(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/healthz":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt, *args):
        pass


def main():
    if not check_database():
        time.sleep(1)
        sys.exit(1)
    print("[checkout-api] healthy, serving on :8080/healthz", flush=True)
    http.server.HTTPServer(("0.0.0.0", 8080), Health).serve_forever()


if __name__ == "__main__":
    main()
