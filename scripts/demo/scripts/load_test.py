#!/usr/bin/env python3
"""Local concurrent load generator for Lear investor demo."""

import argparse
import concurrent.futures
import json
import random
import sys
import time
import urllib.request
import urllib.error

DEFAULT_ELB = "http://a4131978a1f9447f29e142dc50cba962-1618812194.ap-south-1.elb.amazonaws.com"

SUCCESS = 0
FAILURE = 0
LATENCIES = []

def send_request(base_url: str):
    global SUCCESS, FAILURE
    url = f"{base_url}/api/checkout"
    payload = json.dumps({
        "item": random.choice(["Enterprise License", "AI Agent SLA", "DevOps Cloud Unit"]),
        "price": round(random.uniform(49.99, 499.99), 2),
        "timestamp": time.time()
    }).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")

    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            elapsed = (time.time() - t0) * 1000
            if resp.status == 200:
                SUCCESS += 1
                LATENCIES.append(elapsed)
            else:
                FAILURE += 1
    except Exception:
        FAILURE += 1

def main():
    parser = argparse.ArgumentParser(description="Lear Demo Traffic Generator")
    parser.add_argument("--url", default=DEFAULT_ELB, help="Target URL (default: live AWS ELB)")
    parser.add_argument("--concurrency", "-c", type=int, default=10, help="Concurrent workers (default: 10)")
    parser.add_argument("--duration", "-d", type=int, default=300, help="Duration in seconds (default: 300)")
    parser.add_argument("--delay", type=float, default=0.05, help="Delay between requests per worker (default: 0.05s)")
    args = parser.parse_args()

    print("=" * 65)
    print("LEAR INVESTOR DEMO — TRAFFIC GENERATOR")
    print("=" * 65)
    print(f"Target URL   : {args.url}")
    print(f"Concurrency  : {args.concurrency} concurrent threads")
    print(f"Duration     : {args.duration}s")
    print("=" * 65)

    stop_time = time.time() + args.duration

    def worker():
        while time.time() < stop_time:
            send_request(args.url)
            if args.delay > 0:
                time.sleep(args.delay)

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency)
    for _ in range(args.concurrency):
        executor.submit(worker)

    last_s = 0
    last_f = 0
    t_start = time.time()

    try:
        while time.time() < stop_time:
            time.sleep(2)
            now = time.time()
            dt = 2.0
            cur_s = SUCCESS
            cur_f = FAILURE
            rate_s = (cur_s - last_s) / dt
            rate_f = (cur_f - last_f) / dt
            recent_lats = LATENCIES[-50:] if LATENCIES else [0]
            avg_lat = sum(recent_lats) / len(recent_lats) if recent_lats else 0

            status_color = "\033[92m" if rate_f == 0 else "\033[91m"
            reset_color = "\033[0m"

            print(
                f"{status_color}[TRAFFIC]{reset_color} "
                f"Rate: {rate_s:.1f} req/s | "
                f"Total Orders: {cur_s} | "
                f"Errors: {cur_f} ({rate_f:.1f}/s) | "
                f"Avg Latency: {avg_lat:.1f}ms"
            )
            last_s = cur_s
            last_f = cur_f
    except KeyboardInterrupt:
        print("\nStopping traffic generator...")
    finally:
        executor.shutdown(wait=False)
        print("\nTraffic session ended.")

if __name__ == "__main__":
    main()
