# language: Python 3.11, file: maps_runner.py
# target: Google Maps via Playwright (primary) → Places API (fallback)
# requires: playwright, httpx; GOOGLE_MAPS_API_KEY env var for fallback
# note: browser path uses residential proxy pool; API path is ToS-clean.

import asyncio
import csv
import os
import random
import time
from datetime import datetime

import httpx
from playwright.async_api import async_playwright

# ---------------- config ----------------
QUERY = os.getenv("QUERY", "coffee shops in Austin, TX")
MAX_RESULTS = int(os.getenv("MAX_RESULTS", "200"))
OUTFILE = os.getenv(
    "OUTFILE",
    f"/app/out/businesses_{datetime.now():%Y%m%d_%H%M}.csv",
)
API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")
ROTATE_EVERY = int(os.getenv("ROTATE_EVERY", "150"))
BLOCK_MARKERS = (
    "unusual traffic",
    "our systems have detected",
    "captcha",
    "sorry, you have been blocked",
    "detected unusual",
)

PROXY_POOL = [
    # {"server": "http://resi1.provider:8000", "username": "u1", "password": "p1"},
    # {"server": "http://resi2.provider:8000", "username": "u2", "password": "p2"},
]

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

FIELDS = ",".join([
    "places.displayName",
    "places.formattedAddress",
    "places.internationalPhoneNumber",
    "places.rating",
    "places.userRatingCount",
    "places.websiteUri",
    "places.googleMapsUri",
    "places.primaryType",
    "nextPageToken",
])


# ---------------- proxy helpers ----------------
def pick_proxy():
    if not PROXY_POOL:
        return None
    pool = PROXY_POOL[:]
    random.shuffle(pool)
    for px in pool:
        try:
            r = httpx.get(
                "https://api.ipify.org",
                proxies={"http://": px["server"], "https://": px["server"]},
                auth=(px["username"], px["password"]),
                timeout=6,
            )
            if r.status_code == 200:
                return px
        except Exception:
            continue
    return None


async def launch_browser(p):
    kwargs = {"headless": True}
    px = pick_proxy()
    if px:
        kwargs["proxy"] = px
    return await p.chromium.launch(**kwargs)


def is_blocked(html: str) -> bool:
    low = html.lower()
    return any(m in low for m in BLOCK_MARKERS)


# ---------------- browser engine ----------------
async def scrape_browser():
    """Returns list of row dicts, or None if blocked/failed."""
    rows = []
    async with async_playwright() as p:
        browser = await launch_browser(p)
        page = await browser.new_page(user_agent=UA)

        url = f"https://www.google.com/maps/search/{QUERY.replace(' ', '+')}"
        await page.goto(url, wait_until="domcontentloaded")

        # consent wall
        for sel in ['button:has-text("Accept all")', 'button:has-text("I agree")']:
            try:
                await page.click(sel, timeout=3000)
                break
            except Exception:
                pass

        # block check
        try:
            body = await page.content()
            if is_blocked(body):
                print("[browser] blocked at landing — falling back")
                await browser.close()
                return None
        except Exception:
            pass

        try:
            await page.wait_for_selector('div[role="feed"]', timeout=15000)
        except Exception:
            print("[browser] no feed — falling back")
            await browser.close()
            return None

        feed = page.locator('div[role="feed"]')
        last_count, stall = 0, 0
        while stall < 3 and len(rows) + await _card_count(page) < MAX_RESULTS:
            cards = await _card_count(page)
            if cards == last_count:
                stall += 1
            else:
                stall = 0
            last_count = cards
            await feed.evaluate("el => el.scrollBy(0, 3000)")
            await asyncio.sleep(1.2)

        cards = page.locator('div[role="feed"] > div > div[role="article"]')
        total = min(await cards.count(), MAX_RESULTS)

        for i in range(total):
            # rotate proxy mid-run
            if PROXY_POOL and i > 0 and i % ROTATE_EVERY == 0:
                await browser.close()
                browser = await launch_browser(p)
                page = await browser.new_page(user_agent=UA)
                await page.goto(url, wait_until="domcontentloaded")
                await page.wait_for_selector('div[role="feed"]', timeout=15000)
                feed = page.locator('div[role="feed"]')
                cards = page.locator('div[role="feed"] > div > div[role="article"]')

            try:
                card = cards.nth(i)
                await card.click()
                await page.wait_for_selector("h1", timeout=5000)
                await asyncio.sleep(0.4)
            except Exception:
                continue

            # block check per card — Google flips mid-scroll
            try:
                body = await page.content()
                if is_blocked(body):
                    print(f"[browser] blocked at card {i} — falling back")
                    await browser.close()
                    return rows or None
            except Exception:
                pass

            rows.append({
                "name": await _text(page, "h1"),
                "phone": _clean(await _attr(page, 'button[data-item-id^="phone:tel:"]', "aria-label"), "Phone: "),
                "address": _clean(await _attr(page, 'button[data-item-id="address"]', "aria-label"), "Address: "),
                "rating": await _attr(page, 'div[role="img"][aria-label*="stars"]', "aria-label"),
                "reviews": "",
                "website": await _attr(page, 'a[data-item-id="authority"]', "href"),
                "maps_url": page.url,
                "type": "",
                "source": "browser",
            })
            await asyncio.sleep(0.3)

        await browser.close()

    return rows if rows else None


async def _card_count(page):
    return await page.locator('div[role="feed"] > div > div[role="article"]').count()


async def _text(page, sel):
    try:
        return (await page.locator(sel).first.inner_text(timeout=3000)).strip()
    except Exception:
        return ""


async def _attr(page, sel, attr):
    try:
        return (await page.locator(sel).first.get_attribute(attr, timeout=3000)) or ""
    except Exception:
        return ""


def _clean(raw, prefix):
    raw = raw or ""
    if raw.startswith(prefix):
        raw = raw[len(prefix):]
    return raw.strip()


# ---------------- API engine ----------------
def scrape_api():
    """Places API (New). Returns list of row dicts, or None on failure."""
    if not API_KEY:
        print("[api] no GOOGLE_MAPS_API_KEY — cannot fall back")
        return None

    rows = []
    url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": API_KEY,
        "X-Goog-FieldMask": FIELDS,
    }
    try:
        with httpx.Client() as client:
            token = None
            while len(rows) < MAX_RESULTS:
                body = {"textQuery": QUERY, "pageSize": 20}
                if token:
                    body["pageToken"] = token
                r = client.post(url, headers=headers, json=body, timeout=20)
                if r.status_code != 200:
                    print(f"[api] HTTP {r.status_code} — aborting")
                    return rows or None
                data = r.json()
                places = data.get("places", [])
                if not places:
                    break
                for p in places:
                    rows.append({
                        "name": p.get("displayName", {}).get("text", ""),
                        "phone": p.get("internationalPhoneNumber", ""),
                        "address": p.get("formattedAddress", ""),
                        "rating": p.get("rating", ""),
                        "reviews": p.get("userRatingCount", ""),
                        "website": p.get("websiteUri", ""),
                        "maps_url": p.get("googleMapsUri", ""),
                        "type": p.get("primaryType", ""),
                        "source": "api",
                    })
                    if len(rows) >= MAX_RESULTS:
                        break
                token = data.get("nextPageToken")
                if not token:
                    break
                time.sleep(2)
    except Exception as e:
        print(f"[api] error: {e} — returning partial")
        return rows or None

    return rows or None


# ---------------- orchestrator ----------------
def dedupe(rows):
    seen, out = set(), []
    for r in rows:
        key = (r["name"].lower(), r["phone"], r["address"].lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def write_csv(rows):
    if not rows:
        print("no rows to write")
        return
    os.makedirs(os.path.dirname(OUTFILE) or ".", exist_ok=True)
    fields = ["name", "phone", "address", "rating", "reviews", "website", "maps_url", "type", "source"]
    with open(OUTFILE, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows -> {OUTFILE}")


async def main():
    print(f"[run] query={QUERY!r} max={MAX_RESULTS}")
    rows = await scrape_browser()
    source = "browser"

    if rows is None:
        rows = []
    if len(rows) < MAX_RESULTS:
        print(f"[run] browser yielded {len(rows)}/{MAX_RESULTS} — topping up via API")
        api_rows = scrape_api() or []
        rows.extend(api_rows)
        source = "browser+api" if rows else "api"

    rows = dedupe(rows)[:MAX_RESULTS]
    print(f"[run] final {len(rows)} rows via {source}")
    write_csv(rows)


if __name__ == "__main__":
    asyncio.run(main())
