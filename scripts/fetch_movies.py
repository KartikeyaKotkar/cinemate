"""
fetch_movies.py — Fetch movies from TMDB discover endpoint.

Loads TMDB_API_KEY from the project root .env file.
Outputs: movies_dataset.json (default: ./data/movies_dataset.json)
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
# Walk up from scripts/ to project root to find .env
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

TMDB_API_KEY = os.getenv("TMDB_API_KEY")
if not TMDB_API_KEY:
    sys.exit("TMDB_API_KEY not set. Add it to .env at project root.")

BASE_URL = "https://api.tmdb.org/3"
OUTPUT_DIR = Path(__file__).resolve().parent / "data"
OUTPUT_FILE = OUTPUT_DIR / "movies_dataset.json"

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


def get_genres() -> dict[int, str]:
    """Fetch genre id → name mapping."""
    r = session.get(
        f"{BASE_URL}/genre/movie/list",
        params={"api_key": TMDB_API_KEY},
        headers=HEADERS,
        timeout=10,
    )
    r.raise_for_status()
    return {g["id"]: g["name"] for g in r.json().get("genres", [])}


def get_keywords(movie_id: int) -> list[str]:
    """Fetch keywords for a single movie."""
    r = session.get(
        f"{BASE_URL}/movie/{movie_id}/keywords",
        params={"api_key": TMDB_API_KEY},
        headers=HEADERS,
        timeout=10,
    )
    r.raise_for_status()
    return [k["name"] for k in r.json().get("keywords", [])]


def fetch_movies(total_pages: int = 50) -> list[dict]:
    """
    Fetch movies from TMDB /discover/movie.
    50 pages × 20 results = ~1000 movies.
    """
    genre_map = get_genres()
    movies = []

    for page in range(1, total_pages + 1):
        try:
            r = session.get(
                f"{BASE_URL}/discover/movie",
                params={
                    "api_key": TMDB_API_KEY,
                    "sort_by": "popularity.desc",
                    "vote_count.gte": 100,
                    "with_original_language": "en",
                    "page": page,
                },
                headers=HEADERS,
                timeout=10,
            )
            r.raise_for_status()
        except requests.exceptions.ConnectionError as e:
            print(f"ConnectionError on page {page}, retrying in 2 seconds...")
            time.sleep(2)
            # Try once more manually for the connection error
            r = session.get(
                f"{BASE_URL}/discover/movie",
                params={
                    "api_key": TMDB_API_KEY,
                    "sort_by": "popularity.desc",
                    "vote_count.gte": 100,
                    "with_original_language": "en",
                    "page": page,
                },
                headers=HEADERS,
                timeout=15,
            )
            r.raise_for_status()
        results = r.json().get("results", [])

        for movie in results:
            overview = movie.get("overview", "").strip()
            if not overview:
                continue

            movie_id = movie["id"]
            genre_names = [
                genre_map.get(gid, "Unknown")
                for gid in movie.get("genre_ids", [])
            ]
            keywords = get_keywords(movie_id)

            movies.append({
                "id": movie_id,
                "title": movie.get("title", ""),
                "overview": overview,
                "genres": genre_names,
                "keywords": keywords,
                "release_year": movie.get("release_date", "")[:4],
                "rating": movie.get("vote_average", 0),
                "vote_count": movie.get("vote_count", 0),
                "popularity": movie.get("popularity", 0),
                "poster_path": movie.get("poster_path", ""),
            })

        print(f"Page {page}/{total_pages} — {len(movies)} movies collected")
        time.sleep(0.3)

    return movies


def save_movies(movies: list[dict], path: Path = OUTPUT_FILE):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(movies, f, indent=2, ensure_ascii=False)
    print(f"\n✅ Saved {len(movies)} movies to {path}")


if __name__ == "__main__":
    print("🎬 Starting TMDB fetch...\n")
    movies = fetch_movies(total_pages=50)
    save_movies(movies)
    print("\nSample entry:")
    print(json.dumps(movies[0], indent=2))
