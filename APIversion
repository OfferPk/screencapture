# language: Python 3.11, file: places_scraper.py
# target: Google Places API (New) — places.googleapis.com/v1/places:searchText
# requires: GOOGLE_MAPS_API_KEY env var, Places API (New) enabled in GCP
# note: Text Search returns max 20 per page, 60 total via pageToken.

import csv
import os
import time
from datetime import datetime

import httpx

API_KEY = os.environ["GOOGLE_MAPS_API_KEY"]
QUERY = os.getenv("QUERY", "dentists in Lahore")
MAX_RESULTS = int(os.getenv("MAX_RESULTS", "60"))
OUTFILE = os.getenv(
    "OUTFILE",
    f"places_{datetime.now():%Y%m%d_%H%M}.csv",
)

URL = "https://places.googleapis.com/v1/places:searchText"
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


def fetch_page(client, page_token=None):
    body = {"textQuery": QUERY, "pageSize": 20}
    if page_token:
        body["pageToken"] = page_token
    r = client.post(
        URL,
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": API_KEY,
            "X-Goog-FieldMask": FIELDS,
        },
        json=body,
        timeout=20,
    )
    r.raise_for_status()
    return r.json()


def main():
    rows = []
    with httpx.Client() as client:
        token = None
        while len(rows) < MAX_RESULTS:
            data = fetch_page(client, token)
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
                })
                if len(rows) >= MAX_RESULTS:
                    break
            token = data.get("nextPageToken")
            if not token:
                break
            time.sleep(2)  # token needs a beat before it's valid

    with open(OUTFILE, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else [])
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows -> {OUTFILE}")


if __name__ == "__main__":
    main()
