"""
embed_movies.py — Embed movie text and store vectors in ChromaDB.

Reads:  scripts/data/movies_dataset.json
Writes: scripts/data/chroma_db/
"""

import json
import sys
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

# ── Config ────────────────────────────────────────────────────────────────────
DATA_DIR = Path(__file__).resolve().parent / "data"
DATASET_FILE = DATA_DIR / "movies_dataset.json"
CHROMA_DIR = str(DATA_DIR / "chroma_db")
COLLECTION = "movies"
MODEL_NAME = "all-MiniLM-L6-v2"
BATCH_SIZE = 64
# ─────────────────────────────────────────────────────────────────────────────


def build_text(movie: dict) -> str:
    """Combine overview + genres + keywords into a single embedding string."""
    parts = []

    overview = movie.get("overview", "")
    if overview:
        parts.append(overview)

    genres = ", ".join(movie.get("genres", []))
    if genres:
        parts.append(f"Genres: {genres}.")

    keywords = ", ".join(movie.get("keywords", []))
    if keywords:
        parts.append(f"Themes: {keywords}.")

    return " ".join(parts)


def load_movies(path: Path) -> list[dict]:
    if not path.exists():
        sys.exit(f"Dataset not found: {path}\nRun fetch_movies.py first.")

    with open(path, "r", encoding="utf-8") as f:
        movies = json.load(f)

    # Deduplicate by ID (TMDB pagination can sometimes return the same movie twice)
    seen_ids = set()
    unique_movies = []
    for m in movies:
        if m["id"] not in seen_ids:
            seen_ids.add(m["id"])
            unique_movies.append(m)

    valid = [m for m in unique_movies if m.get("overview", "").strip()]
    
    skipped_overview = len(unique_movies) - len(valid)
    skipped_dups = len(movies) - len(unique_movies)
    print(f"Loaded {len(valid)} unique movies (skipped {skipped_overview} without overview, {skipped_dups} duplicates)")
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
                "popularity": float(m.get("popularity", 0)),
                "poster_path": m.get("poster_path", ""),
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


if __name__ == "__main__":
    movies = load_movies(DATASET_FILE)
    embed_and_store(movies)
    print("\nNext: run search.py to query your database.")
