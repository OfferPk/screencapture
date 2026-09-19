# screencapture

Two related toolsets in one repo:

1. **Windows screen capture** (`screencap/`) — GDI BitBlt and DXGI Desktop Duplication to JPEG/PNG.
2. **Google Maps / Places scrapers** (`maps/`) — Playwright browser scrape with optional Places API (New) fallback, plus Docker scheduling.

---

## Repository layout

```
.
├── screencap/
│   └── screencap.cpp          # Windows GDI / DXGI capture CLI
├── maps/
│   ├── maps_runner.py         # Primary: browser scrape → Places API top-up
│   ├── places_scraper.py      # Places API (New) only
│   ├── gmaps_browser_scraper.py  # Simple Playwright-only scraper
│   └── proxy_rotation.py      # Optional residential proxy helpers
├── Dockerfile                 # Playwright + cron image for maps_runner
├── docker-compose.yml
├── crontab                    # Daily 03:00 job inside the container
├── requirements.txt
└── README.md
```

---

## Part A — Windows screen capture

### Requirements

- Windows 10/11
- MSVC (x64) with Windows SDK (GDI+, D3D11, DXGI)

### Build

From `screencap/` (Developer Command Prompt for VS):

```bat
cl /std:c++17 /EHsc /O2 screencap.cpp gdiplus.lib d3d11.lib dxgi.lib ole32.lib
```

### Run

```bat
screencap.exe gdi  screen.jpg
screencap.exe dxgi screen_dxgi.jpg
screencap.exe live frame_ 10 500
```

| Mode   | Meaning                                      |
|--------|----------------------------------------------|
| `gdi`  | Full virtual desktop via BitBlt → JPEG       |
| `dxgi` | Single frame via Desktop Duplication → JPEG  |
| `live` | N frames at interval_ms with filename prefix |

---

## Part B — Maps / Places scrapers

### Requirements

- Python 3.11+
- Chromium for Playwright
- Optional: `GOOGLE_MAPS_API_KEY` with **Places API (New)** enabled (GCP)

### Install (local)

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

### Run — hybrid runner (recommended)

Browser first; tops up via Places API if blocked or short of `MAX_RESULTS`.

```bash
# Browser only (no API key)
export QUERY="dentists in Lahore"
export MAX_RESULTS=200
export OUTFILE="./out/businesses.csv"
python maps/maps_runner.py

# Hybrid (recommended)
export GOOGLE_MAPS_API_KEY="your_key"
export QUERY="dentists in Lahore"
export MAX_RESULTS=300
export OUTFILE="./out/businesses.csv"
python maps/maps_runner.py
```

CSV columns: `name`, `phone`, `address`, `rating`, `reviews`, `website`, `maps_url`, `type`, `source`.

### Run — Places API only

```bash
export GOOGLE_MAPS_API_KEY="your_key"
export QUERY="coffee shops in Austin"
export MAX_RESULTS=60
python maps/places_scraper.py
```

Text Search returns at most **60** results per query (20 per page). Split by neighborhood/postal and union if you need more; `maps_runner` dedupes overlaps.

### Run — simple browser scraper

Edit `QUERY` / `MAX_RESULTS` / `OUTFILE` at the top of `maps/gmaps_browser_scraper.py`, then:

```bash
python maps/gmaps_browser_scraper.py
```

### Proxies

- `maps_runner.py` has an in-file `PROXY_POOL` (commented examples).
- Standalone helpers live in `maps/proxy_rotation.py` if you want to wire rotation into another launch path.

### Docker

```bash
mkdir -p out
docker compose up -d --build
# CSV / logs land in ./out
```

Env knobs (see `docker-compose.yml`): `QUERY`, `MAX_RESULTS`, `GOOGLE_MAPS_API_KEY`, `ROTATE_EVERY`, `OUTFILE`, `TZ`.

One-shot without cron:

```bash
docker build -t gmaps-scraper .
docker run --rm -e QUERY="dentists in Lahore" -e MAX_RESULTS=50 \
  -e OUTFILE=/app/out/businesses.csv -v "$(pwd)/out:/app/out" \
  --entrypoint python gmaps-scraper maps/maps_runner.py
```

### Cost / behavior notes

| Scenario                         | Browser | API   | Approx. cost |
|----------------------------------|---------|-------|--------------|
| Clean run, 300 results           | all     | none  | $0           |
| Blocked at landing, 300 wanted   | 0       | ≤60*  | API fees     |
| Blocked at card 120, 300 wanted  | 120     | top-up| API fees     |
| No API key, blocked              | partial | none  | $0           |

\*Places Text Search caps at 60 per query without further query splitting.

---

## Legal / operational limits

- Automated scraping of Google Maps can conflict with Google’s Terms of Service. Treat IPs as burnable; prefer Places API for production/commercial use.
- Personal data (names/phones) may trigger GDPR/other privacy duties if you store it — keep only what you need.
- Official API: [Places API (New) Text Search](https://developers.google.com/maps/documentation/places/web-service/text-search).

---

## Quick verification checklist

1. **Screencap:** build with MSVC → `screencap.exe gdi test.jpg` → image created.
2. **Maps local:** `pip install -r requirements.txt && playwright install chromium` → `OUTFILE=./out/t.csv MAX_RESULTS=5 python maps/maps_runner.py`.
3. **Places only:** set `GOOGLE_MAPS_API_KEY` → `python maps/places_scraper.py`.
4. **Docker:** `docker compose up -d --build` → check `./out` and container logs.
