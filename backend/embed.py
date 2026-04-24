import json
import sys
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

# ── Config ────────────────────────────────────────────────────────────────────
# Paths relative to this file
BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent

# Where we look for source data (prefer backend/data, fallback to scripts/data)
POSSIBLE_DATA_DIRS = [
    BACKEND_DIR / "data",
    PROJECT_ROOT / "scripts" / "data"
]

# Where we write the ChromaDB
CHROMA_DIR = str(BACKEND_DIR / "data" / "chroma_db")
COLLECTION = "movies"
MODEL_NAME = "all-MiniLM-L6-v2"
BATCH_SIZE = 64


def build_text(movie: dict) -> str:
    """
    Combine overview + genres + keywords into one string for embedding.
    The richer the text, the better the semantic search later.
    """
    genres = ", ".join(movie.get("genres", []))
    keywords = ", ".join(movie.get("keywords", []))
    overview = movie.get("overview", "")

    parts = []
    if overview:
        parts.append(overview)
    if genres:
        parts.append(f"Genres: {genres}.")
    if keywords:
        parts.append(f"Themes: {keywords}.")

    return " ".join(parts)


def find_dataset() -> Path:
    """Look for enriched dataset first, then standard dataset in possible dirs."""
    for d in POSSIBLE_DATA_DIRS:
        enriched = d / "movies_enriched.json"
        if enriched.exists():
            return enriched
        
        standard = d / "movies_dataset.json"
        if standard.exists():
            return standard
            
    return None


def load_movies(path: Path) -> list[dict]:
    if not path or not path.exists():
        print(f"❌ Error: Dataset not found. Checked: {[str(d) for d in POSSIBLE_DATA_DIRS]}")
        sys.exit(1)

    print(f"📂 Loading dataset from: {path}")
    with open(path, "r", encoding="utf-8") as f:
        movies = json.load(f)
    
    seen_ids = set()
    unique_movies = []
    for m in movies:
        if m["id"] not in seen_ids:
            seen_ids.add(m["id"])
            unique_movies.append(m)

    # Filter out movies with no overview — useless for semantic search
    valid = [m for m in unique_movies if m.get("overview", "").strip()]
    
    skipped_overview = len(unique_movies) - len(valid)
    skipped_dups = len(movies) - len(unique_movies)
    print(f"Loaded {len(valid)} unique movies (skipped {skipped_overview} without overview, {skipped_dups} duplicates)")
    return valid


def embed_and_store(movies: list[dict]):
    print(f"\nLoading embedding model: {MODEL_NAME}")
    model = SentenceTransformer(MODEL_NAME)

    print(f"Connecting to ChromaDB at: {CHROMA_DIR}")
    client = chromadb.PersistentClient(path=CHROMA_DIR)

    # Delete existing collection if re-running, to avoid duplicates
    try:
        client.delete_collection(COLLECTION)
        print("Cleared existing collection.")
    except Exception:
        pass

    collection = client.create_collection(
        name=COLLECTION,
        metadata={"hnsw:space": "cosine"},  # use cosine similarity
    )

    print(f"\nEmbedding {len(movies)} movies in batches of {BATCH_SIZE}...\n")

    for i in tqdm(range(0, len(movies), BATCH_SIZE)):
        batch = movies[i : i + BATCH_SIZE]

        texts = [build_text(m) for m in batch]
        ids = [str(m["id"]) for m in batch]

        # Metadata stored alongside vectors (for display later)
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

    print(f"\n✅ Done! {collection.count()} movies stored in ChromaDB.")


if __name__ == "__main__":
    dataset_path = find_dataset()
    movies = load_movies(dataset_path)
    embed_and_store(movies)
    print("\nNext step: run search.py to query your database!")
