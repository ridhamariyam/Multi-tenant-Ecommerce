"""Storefront load test: concurrent shoppers browsing and building guest carts.

    python loadtest/storefront_load.py --base http://localhost:58000 --host localhost \
        --users 30 --seconds 60

Each virtual shopper loops: resolve the store, list products, open a product,
create a guest cart, add an item, price the checkout. No orders are placed, so
it is safe on staging (never run it against production without agreement).
Prints p50/p95/p99 latency and errors per step and overall.
"""

from __future__ import annotations

import argparse
import asyncio
import random
import statistics
import time
from collections import defaultdict

import httpx


def pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    return values[min(len(values) - 1, int(round(p / 100 * (len(values) - 1))))]


async def shopper(client: httpx.AsyncClient, stop_at: float, stats, errors, limited, host: str) -> None:
    headers = {"X-Forwarded-Host": host}

    async def step(name: str, method: str, url: str, **kw):
        started = time.perf_counter()
        try:
            response = await client.request(method, url, headers={**headers, **kw.pop("headers", {})}, **kw)
            ok = response.status_code < 500
            if response.status_code == 429:
                limited[name] += 1  # per-IP limits: one machine looks like one shopper
        except httpx.HTTPError:
            response, ok = None, False
        stats[name].append((time.perf_counter() - started) * 1000)
        if not ok:
            errors[name] += 1
        return response

    while time.monotonic() < stop_at:
        await step("resolve", "GET", "/api/v1/storefront/resolve")
        listing = await step("products", "GET", "/api/v1/storefront/products", params={"page_size": 12})
        products = (listing.json().get("data") or []) if listing is not None and listing.status_code == 200 else []
        if not products:
            continue
        product = random.choice(products)
        detail = await step("product", "GET", f"/api/v1/storefront/products/{product['id']}")
        variants = (detail.json()["data"].get("variants") or []) if detail is not None and detail.status_code == 200 else []
        in_stock = [v for v in variants if v.get("in_stock")]
        cart = await step("cart", "POST", "/api/v1/cart/guest")
        if not in_stock or cart is None or cart.status_code != 201:
            continue
        token = {"X-Cart-Token": cart.json()["data"]["guest_token"]}
        await step("add", "POST", "/api/v1/cart/items", json={"variant_id": in_stock[0]["id"], "quantity": 1}, headers=token)
        await step("preview", "POST", "/api/v1/checkout/guest/preview", json={"pincode": "682001"}, headers=token)
        await asyncio.sleep(random.uniform(0.2, 1.0))  # think time


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:58000")
    parser.add_argument("--host", default="localhost", help="store host to act as (X-Forwarded-Host)")
    parser.add_argument("--users", type=int, default=20)
    parser.add_argument("--seconds", type=int, default=60)
    args = parser.parse_args()

    stats: dict[str, list[float]] = defaultdict(list)
    errors: dict[str, int] = defaultdict(int)
    limited: dict[str, int] = defaultdict(int)
    limits = httpx.Limits(max_connections=args.users * 2)
    started = time.monotonic()
    async with httpx.AsyncClient(base_url=args.base, timeout=30, limits=limits) as client:
        stop_at = time.monotonic() + args.seconds
        await asyncio.gather(*(shopper(client, stop_at, stats, errors, limited, args.host) for _ in range(args.users)))
    elapsed = time.monotonic() - started

    total = sum(len(v) for v in stats.values())
    print(f"{args.users} shoppers, {elapsed:.0f}s, {total} requests, {total / elapsed:.1f} req/s")
    print(f"{'step':10} {'count':>7} {'p50 ms':>8} {'p95 ms':>8} {'p99 ms':>8} {'errors':>7} {'429s':>6}")
    every: list[float] = []
    for name, values in stats.items():
        every += values
        print(f"{name:10} {len(values):7d} {pct(values, 50):8.0f} {pct(values, 95):8.0f} {pct(values, 99):8.0f} {errors[name]:7d} {limited[name]:6d}")
    err = sum(errors.values())
    print(f"{'all':10} {total:7d} {pct(every, 50):8.0f} {pct(every, 95):8.0f} {pct(every, 99):8.0f} {err:7d}"
          f"  ({100 * err / max(total, 1):.2f}% errors, mean {statistics.fmean(every) if every else 0:.0f} ms)")


if __name__ == "__main__":
    asyncio.run(main())
