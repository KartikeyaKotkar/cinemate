from fastapi import FastAPI, HTTPException
from search import search, get_collection

app = FastAPI(title="CineMate API")

@app.get("/search")
def search_movies(q: str, limit: int = 10):
    """Semantic search with hybrid fallback."""
    results = search(query=q, top_k=limit)
    return {"query": q, "results": results, "total": len(results)}

@app.get("/movie/{movie_id}")
def get_movie(movie_id: int):
    """Fetch movie details directly from ChromaDB by ID."""
    collection = get_collection()
    found = collection.get(ids=[str(movie_id)], include=["metadatas"])
    
    if not found["ids"]:
        raise HTTPException(status_code=404, detail="Movie not found")
        
    meta = found["metadatas"][0]
    result = dict(meta)
    result["id"] = int(found["ids"][0])
    return result
