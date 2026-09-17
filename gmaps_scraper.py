# language: Python 3.11 — proxy rotation module
# add to gmaps_scraper.py, replace the browser launch block

import random
import httpx

# --- config ---
PROXY_POOL = [
    {"server": "http://resi1.provider:8000", "username": "u1", "password": "p1"},
    {"server": "http://resi2.provider:8000", "username": "u2", "password": "p2"},
    {"server": "http://resi3.provider:8000", "username": "u3", "password": "p3"},
]
ROTATE_EVERY = 150          # cards before forced rotation
CHECK_PROXY = True          # verify proxy liveness before use


def pick_proxy():
    """Return a random live proxy dict, or None for direct."""
    pool = PROXY_POOL[:]
    random.shuffle(pool)
    for px in pool:
        if not CHECK_PROXY:
            return px
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


async def launch_with_proxy(p):
    """Launch browser with a live proxy; caller retries on failure."""
    proxy = pick_proxy()
    kwargs = {"headless": True}
    if proxy:
        kwargs["proxy"] = proxy
    return await p.chromium.launch(**kwargs)
