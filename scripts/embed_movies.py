"""
embed_movies.py — Embed movie text and store vectors in ChromaDB.

Reads:  scripts/data/movies_enriched.json
Writes: scripts/data/chroma_db/
Also:   copies movies_enriched.json → backend/data/ for the API layer.
"""

import json
import shutil
import sys
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

# ── Config ────────────────────────────────────────────────────────────────────
DATA_DIR = Path(__file__).resolve().parent / "data"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DATA_DIR = PROJECT_ROOT / "backend" / "data"
DATASET_FILE = DATA_DIR / "movies_enriched.json"
CHROMA_DIR = str(DATA_DIR / "chroma_db")
COLLECTION = "movies"
MODEL_NAME = "BAAI/bge-large-en-v1.5"
BATCH_SIZE = 64
# ─────────────────────────────────────────────────────────────────────────────


def build_text(movie: dict) -> str:
    """
    Build a rich text representation for embedding.

    Combines: overview, tagline, genres, keywords, runtime,
    spoken_languages, production_companies, belongs_to_collection,
    directors.
    The richer the signal, the better cosine similarity works.
    """
    parts = []

    overview = movie.get("overview", "")
    if overview:
        parts.append(overview)

    tagline = movie.get("tagline", "")
    if tagline:
        parts.append(f"Tagline: {tagline}")

    directors = movie.get("directors", [])
    if isinstance(directors, str):
        directors = [d.strip() for d in directors.split(",") if d.strip()]
    if directors:
        parts.append(f"Directed by: {', '.join(directors)}.")

    genres = ", ".join(movie.get("genres", []))
    if genres:
        parts.append(f"Genres: {genres}.")

    keywords = ", ".join(movie.get("keywords", []))
    if keywords:
        parts.append(f"Themes: {keywords}.")

    runtime = movie.get("runtime")
    if runtime:
        parts.append(f"Runtime: {runtime} minutes.")

    languages = movie.get("spoken_languages", [])
    if languages:
        parts.append(f"Languages: {', '.join(languages)}.")

    companies = movie.get("production_companies", [])
    if companies:
        parts.append(f"Studios: {', '.join(companies)}.")

    collection = movie.get("belongs_to_collection")
    if collection:
        parts.append(f"Part of: {collection}.")

    return " ".join(parts)


def load_movies(path: Path) -> list[dict]:
    if not path.exists():
        sys.exit(
            f"Dataset not found: {path}\n"
            f"Run fetch_movies.py then enrich_dataset.py first."
        )

    with open(path, "r", encoding="utf-8") as f:
        movies = json.load(f)

    # Deduplicate by ID (TMDB pagination can sometimes return the same movie twice)
    seen_ids = set()
    unique_movies = []
    for m in movies:
        if m["id"] not in seen_ids:
            seen_ids.add(m["id"])
            unique_movies.append(m)

    def quality_score(movie) -> int:
        score = 0
        if len(movie.get("overview", "")) > 100: score += 3
        if len(movie.get("keywords", [])) >= 5:  score += 2
        if movie.get("tagline"):                 score += 1
        if movie.get("vote_count", 0) >= 100:   score += 2
        return score

    valid = [m for m in unique_movies if m.get("overview", "").strip() and quality_score(m) >= 4]
    
    skipped = len(unique_movies) - len(valid)
    skipped_dups = len(movies) - len(unique_movies)
    print(f"Loaded {len(valid)} unique movies (skipped {skipped} low-quality/no-overview, {skipped_dups} duplicates)")
    return valid


def embed_and_store(movies: list[dict]):
    print(f"\nLoading model: {MODEL_NAME}")
    model = SentenceTransformer(MODEL_NAME)

    print(f"ChromaDB path: {CHROMA_DIR}")
    client = chromadb.PersistentClient(path=CHROMA_DIR)

    # Clear existing to avoid duplicates on re-run
    try:
        client.delete_collection(COLLECTION)
        print("Cleared existing collection.")
    except Exception:
        pass

    collection = client.create_collection(
        name=COLLECTION,
        metadata={"hnsw:space": "cosine"},
    )

    print(f"\nEmbedding {len(movies)} movies (batch size {BATCH_SIZE})...\n")

    for i in tqdm(range(0, len(movies), BATCH_SIZE)):
        batch = movies[i : i + BATCH_SIZE]
        texts = [build_text(m) for m in batch]
        ids = [str(m["id"]) for m in batch]

        metadatas = [
            {
                "title": m.get("title", ""),
                "overview": m.get("overview", ""),
                "genres": ", ".join(m.get("genres", [])),
                "keywords": ", ".join(m.get("keywords", [])),
                "release_year": str(m.get("release_year", "")),
                "rating": float(m.get("rating", 0)),
                "vote_count": int(m.get("vote_count", 0)),
                "popularity": float(m.get("popularity", 0)),
                "poster_path": m.get("poster_path", ""),
                "tagline": m.get("tagline", ""),
                "runtime": int(m.get("runtime") or 0),
                "spoken_languages": ", ".join(m.get("spoken_languages", [])),
                "production_companies": ", ".join(m.get("production_companies", [])),
                "belongs_to_collection": m.get("belongs_to_collection") or "",
                "directors": ", ".join(m.get("directors", [])),
            }
            for m in batch
        ]

        embeddings = model.encode(texts, show_progress_bar=False).tolist()

        collection.add(
            ids=ids,
            embeddings=embeddings,
            metadatas=metadatas,
            documents=texts,
        )

    print(f"\n✅ {collection.count()} movies stored in ChromaDB at {CHROMA_DIR}")


def sync_to_backend():
    """Copy enriched dataset to backend/data/ so the API can serve it."""
    BACKEND_DATA_DIR.mkdir(parents=True, exist_ok=True)
    dest = BACKEND_DATA_DIR / "movies_enriched.json"
    shutil.copy2(DATASET_FILE, dest)
    print(f"📋 Synced enriched dataset → {dest}")


if __name__ == "__main__":
    movies = load_movies(DATASET_FILE)
    embed_and_store(movies)
    sync_to_backend()
    print("\nNext: run backend/embed.py to build the backend ChromaDB, then search.py to query.")
