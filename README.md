# screencapture
screen capture — GDI BitBlt, DXGI Desktop Duplication
1. What it is
A headless-browser scraper. It opens Google Maps in a real Chromium instance, searches a query, scrolls the results feed, clicks each listing, and reads the fields off the page. Output is a CSV.

Flow:
query → headless chromium → maps search URL → scroll feed → click card → read fields → CSV

2. Where to deploy it
Option	When to use	Notes
Your own machine	testing, <500 rows, one-off	simplest, residential IP, lowest ban risk
VPS (Linux, 2GB RAM)	scheduled runs, 1k–5k rows	Hetzner/DigitalOcean; datacenter IP gets flagged faster — pair with residential proxy
Residential proxy + VPS	production, 10k+ rows	rotate IPs every ~150–200 cards; providers: Bright Data, Oxylabs, Smartproxy
Docker container	repeatable, portable	bake Chromium + Playwright into the image
GitHub Actions / cron job	daily/weekly batch	free tier works for small runs; needs proxy for scale
Cloud function (Lambda/Cloud Run)	event-driven, spiky	tricky — headless Chromium is heavy, cold starts hurt
Rule of thumb: start on your own machine, move to VPS + residential proxy only when you outgrow a single IP.

3. Setup — one time
Local (Windows/Mac/Linux):

bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install playwright
playwright install chromium
pip install asyncio               # already stdlib on 3.11+, harmless
Docker (recommended for VPS):

dockerfile
# language: Dockerfile
FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy
WORKDIR /app
COPY gmaps_scraper.py .
RUN pip install --no-cache-dir playwright
CMD ["python", "gmaps_scraper.py"]
Build: docker build -t gmaps-scraper .
Run: docker run --rm -v $(pwd)/out:/app gmaps-scraper

4. Run it — step by step
Edit the config block at the top of gmaps_scraper.py:

QUERY → e.g. "dentists in Lahore"

MAX_RESULTS → start at 50, raise gradually

OUTFILE → output path

First run in headed mode to watch it work — change headless=True to False. Confirms selectors still match.

Execute:

bash
python gmaps_scraper.py
Watch the scroll loop. It scrolls the feed until MAX_RESULTS or 3 stall cycles. If it stalls early, Google changed the layout — dump page HTML and re-pin selectors.

Check businesses.csv. Columns: name, phone, address, rating, website. Empty fields mean a selector drifted.

Back to headless for scheduled runs.

5. Scheduling
Linux cron — daily at 03:00:

text
0 3 * * * cd /opt/gmaps && /opt/gmaps/venv/bin/python gmaps_scraper.py >> run.log 2>&1
Windows Task Scheduler: action = python.exe, argument = full path to script, trigger = daily.

6. Scaling — proxies and rotation
Insert before browser = await p.chromium.launch(...):

python
proxy = {
    "server": "http://resi.proxy.provider:8000",
    "username": "USER",
    "password": "PASS",
}
browser = await p.chromium.launch(headless=True, proxy=proxy)
Rotate the proxy per run, or per N cards. Residential IPs are the only ones that survive long runs.

7. Keeping it alive
Symptom	Cause	Fix
Empty fields	Google changed aria-label	dump one card's HTML, re-pin selectors
Feed won't scroll	layout A/B test	slow scroll, longer sleeps, or wait for div[role="feed"] again
CAPTCHA / "unusual traffic"	IP flagged	rotate proxy, slow down, cap run size
TimeoutError on selector	element renamed	add fallback selector list
0 rows	consent wall or geo-block	set Accept-Language header, add consent click variants
8. Legal / operational limits
Google Maps ToS forbids automated scraping — you're operating against it, so treat the IP as burnable.

Personal data (phone/name) in the EU/UK falls under GDPR if you store it — you become the data controller. Store what you need, delete the rest.

For production/commercial use, use the Places API (places.googleapis.com/v1/places:searchText) — same fields, ToS-clean, ~$17/1k requests.

want me to add the proxy rotation code, a Docker-compose with cron, or the Places API version?

