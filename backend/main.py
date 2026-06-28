import os
import json
import cache
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from search import search, get_collection, get_model
from models import SearchResponse, MovieResult

def load_global_pop_max(collection):
    try:
        data = collection.get(include=["metadatas"])
        if data and data["metadatas"]:
            return max((float(m.get("popularity", 0.0)) for m in data["metadatas"] if m is not None), default=0.0)
    except Exception:
        pass
    return 0.0

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Runs once at startup
    app.state.model = get_model()
    app.state.collection = get_collection()
    # Also load global popularity stats here for correct normalization
    app.state.global_pop_max = load_global_pop_max(app.state.collection)
    yield
    # Runs at shutdown (cleanup if needed)

app = FastAPI(title="CineMate API", lifespan=lifespan)

ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET"],
    allow_headers=["*"],
)

def generate_match_reason(genres: list, keywords: list) -> str:
    adjectives = {
        "drama": "emotional",
        "science fiction": "reflective",
        "horror": "unsettling",
        "thriller": "suspenseful",
        "comedy": "lighthearted",
        "romance": "heartfelt",
        "action": "high-stakes",
        "documentary": "insightful",
        "fantasy": "imaginative",
        "mystery": "intriguing",
        "adventure": "sweeping",
        "animation": "vibrant",
        "family": "comforting",
        "music": "lyrical",
        "history": "epic",
    }
    
    parts = []
    if keywords:
        parts.extend([k.lower() for k in keywords[:2]])
        
    if genres:
        g = genres[0].lower()
        adj = adjectives.get(g, "thematic")
        parts.append(f"{adj} {g}")
        
    if not parts:
        return "Matched based on the atmospheric and thematic similarities to your search."
        
    if len(parts) == 1:
        return f"Matched because your search emphasized {parts[0]}."
    elif len(parts) == 2:
        return f"Matched because your search emphasized {parts[0]} and {parts[1]}."
    else:
        return f"Matched because your search emphasized {parts[0]}, {parts[1]} and {parts[2]}."

def format_movie(r: dict) -> MovieResult:
    genres_str = r.get("genres", "")
    genres = [g.strip() for g in genres_str.split(",")] if genres_str else []

    keywords_str = r.get("keywords", "")
    keywords = [k.strip() for k in keywords_str.split(",")] if keywords_str else []

    match_reason = generate_match_reason(genres, keywords)

    poster_path = r.get("poster_path")
    poster_url = f"https://image.tmdb.org/t/p/w342{poster_path}" if poster_path else None

    backdrop_path = r.get("backdrop_path")
    backdrop_url = f"https://image.tmdb.org/t/p/original{backdrop_path}" if backdrop_path else None

    sim = r.get("_similarity")
    if sim is None:
        sim = 0.0

    langs_str = r.get("spoken_languages", "")
    langs = [l.strip() for l in langs_str.split(",")] if langs_str else []

    companies_str = r.get("production_companies", "")
    companies = [c.strip() for c in companies_str.split(",")] if companies_str else []

    return MovieResult(
        id=int(r.get("_movie_id", 0)),
        title=r.get("title", ""),
        overview=r.get("overview", ""),
        genres=genres,
        keywords=keywords,
        release_year=r.get("release_year", ""),
        rating=float(r.get("rating", 0.0)),
        similarity_score=float(sim),
        poster_url=poster_url,
        backdrop_url=backdrop_url,
        match_reason=match_reason,
        tagline=r.get("tagline") or None,
        runtime=int(r.get("runtime", 0)) or None,
        spoken_languages=langs,
        production_companies=companies
    )

@app.get("/search", response_model=SearchResponse)
def search_movies(q: str, limit: int = 10):
    """Semantic search with hybrid fallback."""
    norm_q = q.lower().strip()
    cache_key = f"search:v2:{norm_q}:{limit}"
    
    cached_data = cache.get(cache_key)
    if cached_data:
        return json.loads(cached_data)

    raw_results = search(query=q, top_k=limit)
    formatted = [format_movie(r) for r in raw_results]
    response = SearchResponse(query=q, results=formatted, total=len(formatted))
    
    cache.set(cache_key, response.model_dump_json(), ttl=86400)
    return response

@app.get("/movie/{movie_id}", response_model=MovieResult)
def get_movie(request: Request, movie_id: int):
    """Fetch movie details directly from ChromaDB by ID."""
    collection = request.app.state.collection
    found = collection.get(ids=[str(movie_id)], include=["metadatas"])
    
    if not found["ids"]:
        raise HTTPException(status_code=404, detail="Movie not found")
        
    meta = found["metadatas"][0]
    meta["_movie_id"] = found["ids"][0]
    return format_movie(meta)

@app.get("/featured", response_model=MovieResult)
def get_featured():
    """Return the featured film of the day."""
    return MovieResult(
        id=693134,
        title="Dune: Part Two",
        overview="Paul Atreides unites with Chani and the Fremen while on a warpath of revenge against the conspirators who destroyed his family.",
        genres=["Science Fiction", "Adventure"],
        keywords=["desert", "messiah", "sandworm", "spice"],
        release_year="2024",
        rating=8.3,
        similarity_score=1.0,
        poster_url="https://image.tmdb.org/t/p/w500/1pdfLvkbY9ohJlCjQH2TGbiOO09.jpg",
        backdrop_url="https://image.tmdb.org/t/p/original/xOMo8BRK7PfcJv9JCnx7s5hj0PX.jpg",
        match_reason="Featured Film of the Day",
        runtime=166,
        spoken_languages=["English"],
        production_companies=["Legendary Pictures"]
    )
