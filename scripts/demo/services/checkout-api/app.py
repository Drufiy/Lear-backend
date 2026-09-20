#!/usr/bin/env python3
"""Checkout API microservice for Lear demo."""

import http.server
import json
import os
import socket
import sys
import time
import urllib.request
import urllib.error

DATABASE_HOST = os.environ.get("DATABASE_HOST", "postgres")
DATABASE_PORT = int(os.environ.get("DATABASE_PORT", "5432"))
PAYMENT_URL = os.environ.get("PAYMENT_SERVICE_URL", "http://payment-service:3000")
SHIPPING_URL = os.environ.get("SHIPPING_SERVICE_URL", "http://shipping-service:4000")
CONNECT_TIMEOUT = float(os.environ.get("DB_CONNECT_TIMEOUT", "3"))
RETRIES = int(os.environ.get("DB_CONNECT_RETRIES", "5"))
RETRY_DELAY = float(os.environ.get("DB_RETRY_DELAY", "1.0"))

REQUEST_COUNT = 0
ERROR_COUNT = 0
START_TIME = time.time()

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

def call_service(url, path, method="GET", payload=None):
    full_url = f"{url}{path}"
    data = json.dumps(payload).encode("utf-8") if payload else None
    headers = {"Content-Type": "application/json"} if payload else {}
    req = urllib.request.Request(full_url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        return {"error": str(exc), "healthy": False}

class CheckoutHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        global REQUEST_COUNT
        REQUEST_COUNT += 1
        if self.path == "/healthz":
            try:
                with socket.create_connection((DATABASE_HOST, DATABASE_PORT), timeout=1.5):
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "ok", "service": "checkout-api", "db": "connected"}).encode("utf-8"))
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "service": "checkout-api", "db_error": str(e)}).encode("utf-8"))
        elif self.path == "/metrics":
            uptime = int(time.time() - START_TIME)
            metrics = {
                "checkout_requests_total": REQUEST_COUNT,
                "checkout_errors_total": ERROR_COUNT,
                "uptime_seconds": uptime,
                "db_host": DATABASE_HOST
            }
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(metrics, indent=2).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        global REQUEST_COUNT, ERROR_COUNT
        REQUEST_COUNT += 1
        if self.path == "/checkout":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length) if length > 0 else b"{}"
            try:
                cart_data = json.loads(body.decode("utf-8")) if body else {}
            except Exception:
                cart_data = {}

            pay_res = call_service(PAYMENT_URL, "/charge", method="POST", payload={"amount": 49.99})
            ship_res = call_service(SHIPPING_URL, "/calculate", method="POST", payload={"destination": "Demo Corp"})

            order_id = f"ord_{int(time.time()*1000)}"
            response = {
                "order_id": order_id,
                "status": "COMPLETED",
                "payment": pay_res,
                "shipping": ship_res,
                "timestamp": time.time()
            }

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(response).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt, *args):
        pass

def main():
    if not check_database():
        time.sleep(1)
        sys.exit(1)
    print("[checkout-api] healthy, serving on :8080", flush=True)
    http.server.HTTPServer(("0.0.0.0", 8080), CheckoutHandler).serve_forever()

if __name__ == "__main__":
    main()
