import chromadb
from sentence_transformers import SentenceTransformer
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
DATA_DIR = Path(__file__).resolve().parent / "data"
CHROMA_DIR = str(DATA_DIR / "chroma_db")
COLLECTION = "movies"
MODEL_NAME = "all-MiniLM-L6-v2"
TOP_K = 5


def search(query: str, top_k: int = TOP_K):
    model = SentenceTransformer(MODEL_NAME)
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    collection = client.get_collection(COLLECTION)

    query_vector = model.encode([query]).tolist()

    results = collection.query(
        query_embeddings=query_vector,
        n_results=top_k,
        include=["metadatas", "distances"],
    )

    metadatas = results["metadatas"][0]
    distances = results["distances"][0]

    print(f'\n🔍 Query: "{query}"\n')
    print("─" * 60)

    for i, (meta, dist) in enumerate(zip(metadatas, distances), 1):
        similarity = round((1 - dist) * 100, 1)  # cosine distance → % match
        print(
            f"{i}. {meta['title']} ({meta['release_year']})  ⭐ {meta['rating']}  🎯 {similarity}% match"
        )
        print(f"   Genres: {meta['genres']}")
        print(f"   {meta['overview'][:120]}...")
        print()

    return metadatas


if __name__ == "__main__":
    # Try a few mood-based queries
    test_queries = [
        "a lonely film that feels like a rainy Sunday",
        "something hopeful about space and survival",
        "dark psychological thriller with an unreliable narrator",
    ]

    for query in test_queries:
        search(query)
        print("=" * 60 + "\n")
