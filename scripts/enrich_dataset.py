"""
enrich_dataset.py — Pull extra TMDB fields per movie.

Reads:  scripts/data/movies_dataset.json
Writes: scripts/data/movies_enriched.json

Extra fields: tagline, runtime, spoken_languages, production_companies,
belongs_to_collection, directors. These improve embedding quality for semantic search.
"""

import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ── Load environment ──────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

TMDB_API_KEY = os.getenv("TMDB_API_KEY")
if not TMDB_API_KEY:
    sys.exit("TMDB_API_KEY not set. Add it to .env at project root.")

BASE_URL = "https://api.tmdb.org/3"
DATA_DIR = Path(__file__).resolve().parent / "data"
INPUT_FILE = DATA_DIR / "movies_dataset.json"
OUTPUT_FILE = DATA_DIR / "movies_enriched.json"


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Accept": "application/json"
}

# Configure session with retries for robustness against ConnectionResetError
session = requests.Session()
retries = Retry(
    total=5,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET"]
)
session.mount("https://", HTTPAdapter(max_retries=retries))


def get_movie_credits(movie_id: int) -> dict:
    """Fetch /movie/{id}/credits for director names."""
    try:
        r = session.get(
            f"{BASE_URL}/movie/{movie_id}/credits",
            params={"api_key": TMDB_API_KEY},
            headers=HEADERS,
            timeout=10,
        )
        r.raise_for_status()
    except requests.exceptions.ConnectionError:
        print(f"ConnectionError for credits {movie_id}, retrying in 2 seconds...")
        time.sleep(2)
        r = session.get(
            f"{BASE_URL}/movie/{movie_id}/credits",
            params={"api_key": TMDB_API_KEY},
            headers=HEADERS,
            timeout=15,
        )
        r.raise_for_status()
    data = r.json()

    directors = [
        c.get("name", "")
        for c in data.get("crew", [])
        if c.get("job") == "Director" and c.get("name")
    ]
    return {"directors": directors}


def get_movie_details(movie_id: int) -> dict:
    """Fetch /movie/{id} for enrichment fields."""
    try:
        r = session.get(
            f"{BASE_URL}/movie/{movie_id}",
            params={"api_key": TMDB_API_KEY},
            headers=HEADERS,
            timeout=10,
        )
        r.raise_for_status()
    except requests.exceptions.ConnectionError as e:
        print(f"ConnectionError for movie {movie_id}, retrying in 2 seconds...")
        time.sleep(2)
        r = session.get(
            f"{BASE_URL}/movie/{movie_id}",
            params={"api_key": TMDB_API_KEY},
            headers=HEADERS,
            timeout=15,
        )
        r.raise_for_status()
    data = r.json()

    return {
        "tagline": data.get("tagline", ""),
        "runtime": data.get("runtime"),
        "spoken_languages": [
            lang.get("english_name", lang.get("name", ""))
            for lang in data.get("spoken_languages", [])
        ],
        "production_companies": [
            c["name"] for c in data.get("production_companies", [])
        ],
        "belongs_to_collection": (
            data["belongs_to_collection"]["name"]
            if data.get("belongs_to_collection")
            else None
        ),
    }


def enrich(movies: list[dict]) -> list[dict]:
    total = len(movies)
    enriched = []

    for i, movie in enumerate(movies, 1):
        movie_id = movie["id"]
        try:
            details = get_movie_details(movie_id)
            movie.update(details)
        except requests.RequestException as e:
            print(f"  ⚠ Failed to enrich {movie.get('title', movie_id)}: {e}")
        try:
            credits = get_movie_credits(movie_id)
            movie.update(credits)
        except requests.RequestException as e:
            print(f"  ⚠ Failed to fetch credits {movie.get('title', movie_id)}: {e}")
            movie.setdefault("directors", [])

        enriched.append(movie)

        if i % 50 == 0 or i == total:
            print(f"Enriched {i}/{total}")

        time.sleep(0.5)  # ~2 req/s, two calls per movie (details + credits)

    return enriched


if __name__ == "__main__":
    if not INPUT_FILE.exists():
        sys.exit(f"Dataset not found: {INPUT_FILE}\nRun fetch_movies.py first.")

    print(f"Loading {INPUT_FILE}...")
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        movies = json.load(f)

    print(f"Enriching {len(movies)} movies...\n")
    enriched = enrich(movies)

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(enriched, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Saved enriched dataset to {OUTPUT_FILE}")
    print("Next: re-run embed_movies.py to re-embed with richer text.")
