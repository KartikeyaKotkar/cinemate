"""
expand_dataset.py — Expand dataset to 10k+ movies using TMDB API.

Reads existing scripts/data/movies_enriched.json if available.
Queries TMDB discover endpoint using multiple strategies.
Enriches new movies with keywords and detail fields.
Iteratively saves progress to avoid data loss.
Filters out low-quality entries using a quality gate.
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
OUTPUT_FILE = DATA_DIR / "movies_enriched.json"

HEADERS = {
    "User-Agent": "CineMate Dataset Expansion Agent",
    "Accept": "application/json"
}

# Configure robust session
session = requests.Session()
retries = Retry(
    total=5,
    backoff_factor=1.5,
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
    try:
        r = session.get(
            f"{BASE_URL}/movie/{movie_id}/keywords",
            params={"api_key": TMDB_API_KEY},
            headers=HEADERS,
            timeout=10,
        )
        r.raise_for_status()
        return [k["name"] for k in r.json().get("keywords", [])]
    except Exception as e:
        print(f"  ⚠ Failed to get keywords for {movie_id}: {e}")
        return []


def get_movie_details(movie_id: int) -> dict:
    """Fetch /movie/{id} for enrichment fields."""
    r = session.get(
        f"{BASE_URL}/movie/{movie_id}",
        params={"api_key": TMDB_API_KEY},
        headers=HEADERS,
        timeout=10,
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


def quality_score(movie: dict) -> int:
    """Evaluate movie quality based on overview, keywords, taglines, and votes."""
    score = 0
    overview = movie.get("overview", "")
    if len(overview) > 100:
        score += 3
    elif len(overview) > 10:
        score += 1
        
    if len(movie.get("keywords", [])) >= 5:
        score += 2
    elif len(movie.get("keywords", [])) >= 2:
        score += 1

    if movie.get("tagline"):
        score += 1

    if movie.get("vote_count", 0) >= 100:
        score += 2
    elif movie.get("vote_count", 0) >= 50:
        score += 1

    return score


def load_existing() -> list[dict]:
    """Load existing enriched movies if available."""
    if OUTPUT_FILE.exists():
        try:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                print(f"Loaded {len(data)} existing movies from {OUTPUT_FILE}")
                return data
        except Exception as e:
            print(f"Error reading {OUTPUT_FILE}: {e}. Starting fresh.")
    return []


def save_progress(movies: list[dict]):
    """Save movies to file immediately."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(movies, f, indent=2, ensure_ascii=False)
    print(f"💾 Progress saved: {len(movies)} movies in {OUTPUT_FILE}")


def discover_and_enrich():
    # 1. Load existing movies
    existing_movies = load_existing()
    movies_dict = {m["id"]: m for m in existing_movies}
    seen_ids = set(movies_dict.keys())

    genre_map = get_genres()

    # 2. Define discovery strategies
    strategies = [
        # Strategy A: Popularity descending (covers mainstream cinema)
        {"sort_by": "popularity.desc", "vote_count.gte": 50, "pages": 250},
        # Strategy B: High rated (covers critically acclaimed / classics)
        {"sort_by": "vote_average.desc", "vote_count.gte": 100, "pages": 150},
        # Strategy C: Foreign language movies (ensures French, Japanese, Korean etc.)
        {"sort_by": "popularity.desc", "vote_count.gte": 30, "with_original_language": "fr", "pages": 30},
        {"sort_by": "popularity.desc", "vote_count.gte": 30, "with_original_language": "ja", "pages": 30},
        {"sort_by": "popularity.desc", "vote_count.gte": 30, "with_original_language": "ko", "pages": 30},
        {"sort_by": "popularity.desc", "vote_count.gte": 30, "with_original_language": "it", "pages": 20},
        {"sort_by": "popularity.desc", "vote_count.gte": 30, "with_original_language": "es", "pages": 20},
        {"sort_by": "popularity.desc", "vote_count.gte": 30, "with_original_language": "de", "pages": 20},
        # Strategy D: Specific genres
        {"sort_by": "popularity.desc", "vote_count.gte": 30, "with_genres": 99, "pages": 35},  # Documentary
        {"sort_by": "popularity.desc", "vote_count.gte": 30, "with_genres": 36, "pages": 35},  # History
    ]

    target_count = 10500
    save_counter = 0

    print(f"Target: Reach {target_count} high-quality movies. Currently have {len(seen_ids)} unique IDs.")

    for s_idx, strat in enumerate(strategies, 1):
        if len(movies_dict) >= target_count:
            print("Target reached!")
            break

        print(f"\n🚀 Running Strategy {s_idx}/{len(strategies)}: {strat}")
        pages = strat.pop("pages")

        for page in range(1, pages + 1):
            if len(movies_dict) >= target_count:
                break

            params = {
                "api_key": TMDB_API_KEY,
                "page": page,
                **strat
            }

            try:
                r = session.get(f"{BASE_URL}/discover/movie", params=params, headers=HEADERS, timeout=10)
                r.raise_for_status()
                results = r.json().get("results", [])
            except Exception as e:
                print(f"Error fetching page {page} for strategy {s_idx}: {e}. Skipping.")
                time.sleep(2)
                continue

            if not results:
                print(f"No results returned on page {page}. Strategy might be exhausted.")
                break

            new_in_page = 0
            for movie_data in results:
                movie_id = movie_data["id"]
                if movie_id in seen_ids:
                    continue

                overview = movie_data.get("overview", "").strip()
                if not overview:
                    continue

                # Quick check before expensive calls
                genre_names = [genre_map.get(gid, "Unknown") for gid in movie_data.get("genre_ids", [])]

                # Create draft movie object to check quality score
                movie = {
                    "id": movie_id,
                    "title": movie_data.get("title", ""),
                    "overview": overview,
                    "genres": genre_names,
                    "release_year": movie_data.get("release_date", "")[:4],
                    "rating": movie_data.get("vote_average", 0),
                    "vote_count": movie_data.get("vote_count", 0),
                    "popularity": movie_data.get("popularity", 0),
                    "poster_path": movie_data.get("poster_path", ""),
                }

                # Fetch extra details (enrichment)
                try:
                    time.sleep(0.2)  # Respect rate limit
                    keywords = get_keywords(movie_id)
                    movie["keywords"] = keywords
                    
                    time.sleep(0.2)  # Respect rate limit
                    details = get_movie_details(movie_id)
                    movie.update(details)
                except Exception as e:
                    print(f"  ⚠ Failed to enrich movie {movie_id} ({movie['title']}): {e}. Skipping.")
                    continue

                # Quality gate: score must be at least 4
                q_score = quality_score(movie)
                if q_score < 4:
                    # Skip low-quality entries to ensure high search relevance precision
                    continue

                # Add to dataset
                movies_dict[movie_id] = movie
                seen_ids.add(movie_id)
                new_in_page += 1
                save_counter += 1

                # Incremental save
                if save_counter >= 50:
                    save_progress(list(movies_dict.values()))
                    save_counter = 0

            print(f"Strategy {s_idx} Page {page}/{pages} | Added {new_in_page} new movies | Total unique: {len(movies_dict)}")
            time.sleep(0.3)

    # Final save
    save_progress(list(movies_dict.values()))
    print(f"\n🎉 Expansion completed! Total high-quality movies in dataset: {len(movies_dict)}")


if __name__ == "__main__":
    print("🎬 Starting TMDB Dataset Expansion to 10k+ movies...\n")
    start_time = time.time()
    discover_and_enrich()
    elapsed = time.time() - start_time
    print(f"⏱ Expansion finished in {elapsed/60:.2f} minutes.")
