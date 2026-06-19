"""
search.py — Hybrid search: semantic vector search + TMDB title fallback,
with weighted re-ranking (Phase 1.5).

Classifies queries into three categories:
  - "title"    → short, no mood words → TMDB /search/movie
  - "mood"     → contains vibe/adjective words → pure ChromaDB vector search
  - "ambiguous" → both, deduplicated, title matches first

Re-ranking formula (applied to semantic results):
  final_score = (cosine_similarity * w_sim)
              + (normalized_rating  * w_rat)
              + (normalized_popularity * w_pop)

Where:
  - normalized_rating is Bayesian average rating divided by 10.
  - normalized_popularity is log-scaled popularity computed across candidate batch.
  - Weights default to 0.7, 0.2, 0.1 but vary by profile.
"""

import os
from pathlib import Path

import chromadb
import numpy as np
import requests
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

# ── Environment ───────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

TMDB_API_KEY = os.getenv("TMDB_API_KEY")
TMDB_BASE = "https://api.tmdb.org/3"

# ── Config ────────────────────────────────────────────────────────────────────
DATA_DIR = Path(__file__).resolve().parent / "data"
CHROMA_DIR = str(DATA_DIR / "chroma_db")
COLLECTION = "movies"
MODEL_NAME = "BAAI/bge-large-en-v1.5"
TOP_K = 5

# Words that signal a mood/vibe query rather than a title lookup
MOOD_WORDS = frozenset(
    {
        # adjectives / emotional descriptors
        "lonely",
        "dark",
        "sad",
        "happy",
        "funny",
        "scary",
        "intense",
        "slow",
        "fast",
        "beautiful",
        "quiet",
        "loud",
        "romantic",
        "melancholy",
        "hopeful",
        "bleak",
        "uplifting",
        "disturbing",
        "nostalgic",
        "dreamy",
        "gritty",
        "atmospheric",
        "tense",
        "relaxing",
        "emotional",
        "heartbreaking",
        "thrilling",
        "suspenseful",
        "whimsical",
        "absurd",
        "surreal",
        "eerie",
        "cozy",
        "warm",
        "cold",
        "brutal",
        "gentle",
        "epic",
        "intimate",
        "cerebral",
        "visceral",
        "psychedelic",
        "haunting",
        "bittersweet",
        "redemptive",
        "existential",
        "philosophical",
        "poetic",
        "raw",
        # intent words
        "feel",
        "feels",
        "feeling",
        "vibe",
        "mood",
        "like",
        "similar",
        "something",
        "anything",
        "recommend",
        "suggest",
    }
)


# ── Query classification ──────────────────────────────────────────────────────


def classify_query(query: str) -> str:
    """
    Classify a search query as 'title', 'mood', or 'ambiguous'.

    Heuristic (per roadmap):
      - < 4 words and no mood words → "title"
      - contains mood/vibe words    → "mood"
      - otherwise                   → "ambiguous"
    """
    words = query.lower().split()
    has_mood = bool(set(words) & MOOD_WORDS)

    if len(words) < 4 and not has_mood:
        return "title"
    if has_mood:
        return "mood"
    return "ambiguous"


# ── TMDB title search ────────────────────────────────────────────────────────


def tmdb_title_search(query: str, limit: int = TOP_K) -> list[dict]:
    """
    Search TMDB by title. Returns results in the same dict shape as
    ChromaDB metadata, with _source='tmdb' and _similarity=None.
    """
    if not TMDB_API_KEY:
        return []

    resp = requests.get(
        f"{TMDB_BASE}/search/movie",
        params={"api_key": TMDB_API_KEY, "query": query},
        timeout=10,
    )
    resp.raise_for_status()

    results = []
    for movie in resp.json().get("results", [])[:limit]:
        overview = movie.get("overview", "").strip()
        if not overview:
            continue
        results.append(
            {
                "title": movie.get("title", ""),
                "overview": overview,
                "genres": "",  # /search/movie only returns genre_ids
                "keywords": "",
                "release_year": movie.get("release_date", "")[:4],
                "rating": float(movie.get("vote_average", 0)),
                "vote_count": int(movie.get("vote_count", 0)),
                "popularity": float(movie.get("popularity", 0)),
                "poster_path": movie.get("poster_path") or "",
                "tagline": "",
                "runtime": 0,
                "spoken_languages": "",
                "production_companies": "",
                "belongs_to_collection": "",
                "_movie_id": str(movie["id"]),
                "_source": "tmdb",
                "_similarity": None,  # no cosine score for title matches
            }
        )

    return results


# ── Re-ranking (Phase 1.5) ───────────────────────────────────────────────────
#
# Raw cosine similarity doesn't account for quality.  A 55% match to an
# 8.5-rated film is probably better than a 60% match to a 4.2-rated film.
# We over-fetch from ChromaDB (RERANK_FACTOR × top_k), score every candidate
# with the weighted formula, sort, and trim to top_k.

RERANK_FACTOR = 10  # fetch 3× as many candidates for re-ranking headroom
MIN_VOTES = 50

# WEIGHT_PROFILES: default balances all; popular boosts crowd-pleasers; obscure drops popularity; acclaimed highlights high-rated films.
WEIGHT_PROFILES = {
    "default": {"similarity": 0.7, "rating": 0.2, "popularity": 0.1},
    "popular": {"similarity": 0.6, "rating": 0.1, "popularity": 0.3},
    "obscure": {"similarity": 0.8, "rating": 0.2, "popularity": 0.0},
    "acclaimed": {"similarity": 0.5, "rating": 0.4, "popularity": 0.1},
}


def calculate_movie_score(
    result: dict,
    max_popularity: float,
    global_mean_rating: float,
    weights: dict,
) -> dict:
    """
    Calculate scoring components for a single movie candidate.
    """
    w_similarity = weights.get("similarity", 0.7)
    w_rating = weights.get("rating", 0.2)
    w_popularity = weights.get("popularity", 0.1)

    sim = result.get("_similarity") or 0.0
    rating = float(result.get("rating", 0))
    votes = max(0.0, float(result.get("vote_count", 0)))
    raw_pop = float(result.get("popularity", 0))

    # Bayesian average rating normalization
    bayesian_avg = (votes * rating + MIN_VOTES * global_mean_rating) / (
        votes + MIN_VOTES
    )
    norm_rating = bayesian_avg / 10.0

    # Log-scaled popularity normalization
    denom = np.log1p(max_popularity)
    norm_pop = np.log1p(raw_pop) / denom if denom > 0 else 0.0

    sim_contrib = sim * w_similarity
    rating_contrib = norm_rating * w_rating
    pop_contrib = norm_pop * w_popularity

    final_score = round(sim_contrib + rating_contrib + pop_contrib, 4)

    return {
        "final_score": final_score,
        "similarity_score": sim,
        "rating_contribution": rating_contrib,
        "popularity_contribution": pop_contrib,
    }


def _rerank(
    results: list[dict],
    top_k: int,
    collection: chromadb.Collection | None = None,
    profile: str = "default",
    debug: bool = False,
) -> list[dict]:
    """
    Apply weighted re-ranking and return the best *top_k* results.
    """
    if not results:
        return results

    if collection is None:
        collection = get_collection()
    C = _get_global_mean_rating(collection)

    # Look up weights profile, fall back to "default" if profile not found or malformed
    weights = WEIGHT_PROFILES.get(profile)
    if (
        not isinstance(weights, dict)
        or not all(k in weights for k in ("similarity", "rating", "popularity"))
        or abs(sum(weights.values()) - 1.0) > 1e-5
    ):
        weights = WEIGHT_PROFILES["default"]

    # Get max popularity across the candidate batch
    max_popularity = max((float(r.get("popularity", 0)) for r in results), default=0.0)

    # ── Score each candidate ─────────────────────────────────────────────
    for r in results:
        scores = calculate_movie_score(r, max_popularity, C, weights)
        r["_final_score"] = scores["final_score"]
        if debug:
            r["_score_breakdown"] = scores

    # ── Sort by final score descending, then trim ────────────────────────
    results.sort(key=lambda r: r["_final_score"], reverse=True)
    return results[:top_k]


# ── Semantic (vector) search ─────────────────────────────────────────────────


def semantic_search(
    query: str,
    top_k: int = TOP_K,
    model: SentenceTransformer | None = None,
    collection: chromadb.Collection | None = None,
    profile: str = "default",
    debug: bool = False,
) -> list[dict]:
    """
    Vector search via ChromaDB with weighted re-ranking.

    Over-fetches RERANK_FACTOR × top_k candidates from the vector index,
    applies the quality-weighted scoring formula, and returns the best top_k.
    Accepts pre-loaded model/collection to avoid re-loading on every call.
    """
    if model is None:
        model = SentenceTransformer(MODEL_NAME)
    if collection is None:
        client = chromadb.PersistentClient(path=CHROMA_DIR)
        collection = client.get_collection(COLLECTION)

    fetch_k = top_k * RERANK_FACTOR

    QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "
    query_vector = model.encode([QUERY_INSTRUCTION + query]).tolist()

    results = collection.query(
        query_embeddings=query_vector,
        n_results=fetch_k,
        include=["metadatas", "distances"],
    )

    metadatas = results["metadatas"][0]
    distances = results["distances"][0]
    ids = results["ids"][0]

    enriched = []
    for meta, dist, mid in zip(metadatas, distances, ids):
        entry = dict(meta)
        entry["_movie_id"] = mid
        entry["_source"] = "semantic"
        entry["_similarity"] = round(1 - dist, 4)  # cosine distance → similarity
        enriched.append(entry)

    return _rerank(enriched, top_k, collection, profile=profile, debug=debug)


# ── Hybrid search (the main entry point) ─────────────────────────────────────


def _enrich_tmdb_from_chroma(
    tmdb_results: list[dict],
    collection: chromadb.Collection,
) -> list[dict]:
    """
    Cross-reference TMDB title hits against ChromaDB.
    If a movie exists in our database, swap in the richer metadata.
    """
    if not tmdb_results:
        return tmdb_results

    ids_to_check = [r["_movie_id"] for r in tmdb_results]

    try:
        found = collection.get(ids=ids_to_check, include=["metadatas"])
    except Exception:
        return tmdb_results

    chroma_map = {}
    for fid, fmeta in zip(found["ids"], found["metadatas"]):
        chroma_map[fid] = fmeta

    enriched = []
    for r in tmdb_results:
        mid = r["_movie_id"]
        if mid in chroma_map:
            entry = dict(chroma_map[mid])
            entry["_movie_id"] = mid
            entry["_source"] = "tmdb+db"
            entry["_similarity"] = None
        else:
            entry = r
        enriched.append(entry)

    return enriched


_MODEL_CACHE = None
_COLLECTION_CACHE = None
_GLOBAL_MEAN_RATING_CACHE = None


def get_model():
    global _MODEL_CACHE
    if _MODEL_CACHE is None:
        _MODEL_CACHE = SentenceTransformer(MODEL_NAME)
    return _MODEL_CACHE


def get_collection():
    global _COLLECTION_CACHE
    if _COLLECTION_CACHE is None:
        client = chromadb.PersistentClient(path=CHROMA_DIR)
        _COLLECTION_CACHE = client.get_collection(COLLECTION)
    return _COLLECTION_CACHE


def _get_global_mean_rating(collection: chromadb.Collection) -> float:
    global _GLOBAL_MEAN_RATING_CACHE
    if _GLOBAL_MEAN_RATING_CACHE is None:
        data = collection.get(include=["metadatas"])
        ratings = [
            float(meta.get("rating", 0.0))
            for meta in data["metadatas"]
            if meta is not None
        ]
        if ratings:
            _GLOBAL_MEAN_RATING_CACHE = sum(ratings) / len(ratings)
        else:
            _GLOBAL_MEAN_RATING_CACHE = 0.0
    return _GLOBAL_MEAN_RATING_CACHE


def search(
    query: str,
    top_k: int = TOP_K,
    profile: str = "default",
    debug: bool = False,
) -> list[dict]:
    """
    Hybrid search entry point.

    Routes:
      title     → TMDB title search (enriched from DB if possible)
      mood      → pure vector search
      ambiguous → both, deduplicated, title matches first
    """
    query_type = classify_query(query)

    # Pre-load model & collection once, caching them globally
    model = get_model()
    collection = get_collection()

    if query_type == "title":
        results = tmdb_title_search(query, limit=top_k)
        results = _enrich_tmdb_from_chroma(results, collection)
        # Fallback to semantic if TMDB returns nothing
        if not results:
            results = semantic_search(
                query,
                top_k,
                model=model,
                collection=collection,
                profile=profile,
                debug=debug,
            )

    elif query_type == "mood":
        results = semantic_search(
            query,
            top_k,
            model=model,
            collection=collection,
            profile=profile,
            debug=debug,
        )

    else:  # ambiguous — do both, deduplicate, title matches first
        title_results = tmdb_title_search(query, limit=top_k)
        title_results = _enrich_tmdb_from_chroma(title_results, collection)
        sem_results = semantic_search(
            query,
            top_k,
            model=model,
            collection=collection,
            profile=profile,
            debug=debug,
        )

        seen_ids = set()
        results = []
        for r in title_results + sem_results:
            if r["_movie_id"] not in seen_ids:
                seen_ids.add(r["_movie_id"])
                results.append(r)
        results = results[:top_k]

    # ── Print results ─────────────────────────────────────────────────────
    print(f'\n🔍 Query: "{query}"  [{query_type}]\n')
    print("─" * 60)

    for i, meta in enumerate(results, 1):
        source = meta.get("_source", "?")
        sim = meta.get("_similarity")
        final = meta.get("_final_score")

        # Show both raw similarity and final re-ranked score when available
        if final is not None and sim is not None:
            score_str = f"🎯 sim={round(sim * 100, 1)}%  ⚖ final={final}"
        elif sim is not None:
            score_str = f"🎯 {round(sim * 100, 1)}%"
        else:
            score_str = "📌 title"

        print(
            f"{i}. {meta['title']} ({meta.get('release_year', '?')})  "
            f"⭐ {meta.get('rating', 0)}  {score_str}  [{source}]"
        )
        print(f"   Genres: {meta.get('genres', '')}")
        print(f"   {meta.get('overview', '')[:120]}...")
        print()

    return results


if __name__ == "__main__":
    test_queries = [
        # Title searches (< 4 words, no mood words)
        "Inception",
        "The Dark Knight",
        "Parasite",
        # Mood searches (contains vibe/adjective words)
        "a lonely film that feels like a rainy Sunday",
        "something hopeful about space and survival",
        "dark psychological thriller with an unreliable narrator",
        # Ambiguous (neither clearly title nor mood)
        "films about time travel",
        "revenge thriller in winter",
    ]

    for q in test_queries:
        search(q)
        print("=" * 60 + "\n")
