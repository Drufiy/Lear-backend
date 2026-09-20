import http.server
import json
import os
import random
import time

PORT = int(os.environ.get("PORT", "4000"))

class ShippingHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/healthz":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "service": "shipping-service", "healthy": True}).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/calculate":
            delay = random.uniform(0.05, 0.20)
            time.sleep(delay)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "service": "shipping-service",
                "cost": 5.99,
                "currency": "USD",
                "estimated_days": 3,
                "carrier": "Standard Express"
            }).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt, *args):
        pass

def run():
    print(f"[shipping-service] Listening on port {PORT}", flush=True)
    http.server.HTTPServer(("0.0.0.0", PORT), ShippingHandler).serve_forever()

if __name__ == "__main__":
    run()
