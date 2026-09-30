import os
import json
import re
import base64
import logging
import requests
import cache
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from search import search, get_collection, get_model
from models import SearchResponse, MovieResult

logger = logging.getLogger("cinemate")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")

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

    directors_raw = r.get("directors", "")
    if isinstance(directors_raw, list):
        directors = [str(d).strip() for d in directors_raw if str(d).strip()]
    else:
        directors = [d.strip() for d in directors_raw.split(",")] if directors_raw else []

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
        production_companies=companies,
        directors=directors or None
    )

@app.get("/search", response_model=SearchResponse)
def search_movies(q: str, limit: int = 10):
    """Semantic search with hybrid fallback."""
    norm_q = q.lower().strip()
    cache_key = f"search:v3:{norm_q}:{limit}"
    
    cached_data = cache.get(cache_key)
    if cached_data:
        return json.loads(cached_data)

    raw_results = search(query=q, top_k=limit)
    formatted = [format_movie(r) for r in raw_results]
    response = SearchResponse(query=q, results=formatted, total=len(formatted))
    
    cache.set(cache_key, response.model_dump_json(), ttl=86400)
    return response

# ─── Spotify Synesthetic Discovery ──────────────────────────────────────────────

SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")

def get_spotify_token() -> str | None:
    """Obtain a Client Credentials access token from Spotify."""
    if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
        logger.error("Spotify credentials not configured (SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET)")
        return None

    auth_b64 = base64.b64encode(f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()).decode()
    try:
        res = requests.post(
            "https://accounts.spotify.com/api/token",
            headers={
                "Authorization": f"Basic {auth_b64}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={"grant_type": "client_credentials"},
            timeout=10,
        )
        res.raise_for_status()
        token = res.json().get("access_token")
        if token:
            logger.info("Spotify auth successful")
        else:
            logger.error("Spotify auth response missing access_token: %s", res.text)
        return token
    except requests.RequestException as e:
        logger.error("Spotify auth request failed: %s", e)
        return None


def _extract_playlist_id(url: str) -> str:
    """Pull the playlist ID from various Spotify URL formats."""
    # Matches open.spotify.com/playlist/<id>, spotify:playlist:<id>, etc.
    m = re.search(r"playlist[/:]([A-Za-z0-9]{22})", url)
    if not m:
        raise HTTPException(
            status_code=400,
            detail=f"Could not extract a playlist ID from the provided URL: {url}",
        )
    return m.group(1)


def infer_mood_from_tracks(tracks: list[dict]) -> str:
    """
    Build a rich natural-language mood query from track names and artist names.

    Strategy:
      1. Collect every track name and artist name.
      2. Scan them against curated mood-signal keywords.
      3. Combine the top matched mood descriptors into a cinematic query sentence.

    This avoids the deprecated Audio Features endpoint entirely.
    """
    if not tracks:
        return "A cinematic and atmospheric movie experience."

    # Flatten all textual signals into one lowercased corpus
    corpus_parts: list[str] = []
    for t in tracks:
        track_obj = t.get("track")
        if not track_obj:
            continue
        name = (track_obj.get("name") or "").lower()
        artists = ", ".join(a.get("name", "") for a in track_obj.get("artists", []))
        corpus_parts.append(f"{name} {artists.lower()}")
    corpus = " ".join(corpus_parts)

    if not corpus.strip():
        return "A cinematic and atmospheric movie experience."

    # Mood signals: keyword fragments → (mood descriptor, weight)
    mood_signals: dict[str, tuple[str, float]] = {
        # Sad / melancholic
        "sad": ("melancholic and emotionally heavy", 2.0),
        "cry": ("melancholic and tearful", 1.5),
        "tears": ("melancholic and tearful", 1.5),
        "lonely": ("lonely and introspective", 1.5),
        "heartbreak": ("heartbreaking and romantic", 2.0),
        "broken": ("emotionally raw and painful", 1.5),
        "miss you": ("nostalgic and longing", 1.5),
        "goodbye": ("bittersweet and farewell", 1.5),
        "rain": ("melancholic and atmospheric", 1.0),
        "alone": ("lonely and introspective", 1.5),
        # Happy / upbeat
        "happy": ("joyful and uplifting", 2.0),
        "sunshine": ("warm and feel-good", 1.5),
        "dance": ("energetic and euphoric", 1.5),
        "party": ("wild and celebratory", 1.5),
        "fun": ("lighthearted and fun", 1.0),
        "celebrate": ("celebratory and triumphant", 1.5),
        "good vibes": ("feel-good and easygoing", 1.5),
        "joy": ("joyful and heartwarming", 1.5),
        # Chill / relaxed
        "chill": ("relaxed and contemplative", 1.5),
        "relax": ("calm and meditative", 1.5),
        "sleep": ("dreamy and tranquil", 1.0),
        "dream": ("dreamy and surreal", 1.5),
        "peace": ("peaceful and serene", 1.5),
        "quiet": ("quiet and intimate", 1.0),
        "soft": ("gentle and tender", 1.0),
        "lo-fi": ("lo-fi and cozy", 1.5),
        "lofi": ("lo-fi and cozy", 1.5),
        # Dark / intense
        "dark": ("dark and brooding", 2.0),
        "night": ("nocturnal and mysterious", 1.5),
        "death": ("dark and existential", 1.5),
        "blood": ("violent and gritty", 1.5),
        "rage": ("furious and intense", 2.0),
        "anger": ("intense and volatile", 1.5),
        "pain": ("painful and raw", 1.5),
        "scream": ("intense and chaotic", 1.5),
        "demon": ("dark and supernatural", 1.5),
        "hell": ("dark and infernal", 1.0),
        "fear": ("tense and fearful", 1.5),
        "monster": ("monstrous and terrifying", 1.5),
        # Love / romantic
        "love": ("romantic and passionate", 2.0),
        "kiss": ("romantic and intimate", 1.5),
        "heart": ("heartfelt and emotional", 1.0),
        "baby": ("tender and romantic", 0.5),
        "forever": ("epic and timeless", 1.0),
        # Epic / powerful
        "war": ("epic and war-torn", 2.0),
        "fight": ("action-packed and combative", 1.5),
        "fire": ("fiery and intense", 1.5),
        "power": ("powerful and commanding", 1.5),
        "king": ("regal and epic", 1.0),
        "glory": ("triumphant and glorious", 1.5),
        "hero": ("heroic and adventurous", 1.5),
        "rise": ("triumphant and uplifting", 1.0),
        "thunder": ("thunderous and powerful", 1.5),
        # Nostalgic / retro
        "remember": ("nostalgic and reflective", 1.5),
        "memory": ("nostalgic and wistful", 1.5),
        "old": ("vintage and nostalgic", 1.0),
        "yesterday": ("nostalgic and bittersweet", 1.5),
        "summer": ("warm and sun-drenched", 1.5),
        "young": ("youthful and coming-of-age", 1.0),
        # Mystery / suspense
        "secret": ("mysterious and secretive", 1.5),
        "shadow": ("shadowy and noir", 1.5),
        "ghost": ("ghostly and haunting", 1.5),
        "lost": ("lost and searching", 1.0),
        "stranger": ("mysterious and tense", 1.5),
        "midnight": ("nocturnal and noir", 1.5),
    }

    # Score each mood descriptor
    mood_scores: dict[str, float] = {}
    for keyword, (descriptor, weight) in mood_signals.items():
        count = corpus.count(keyword)
        if count > 0:
            mood_scores[descriptor] = mood_scores.get(descriptor, 0.0) + count * weight

    if not mood_scores:
        # Fallback: just use the first few track names as-is for a more literal query
        sample_names = []
        for t in tracks[:5]:
            track_obj = t.get("track")
            if track_obj and track_obj.get("name"):
                sample_names.append(track_obj["name"])
        if sample_names:
            return f"A movie with the mood of songs like {', '.join(sample_names)}."
        return "A cinematic and atmospheric movie experience."

    # Pick top 3 descriptors by score
    ranked = sorted(mood_scores.items(), key=lambda x: x[1], reverse=True)
    top_moods = [desc for desc, _ in ranked[:3]]

    return f"A {', '.join(top_moods)} movie."


@app.get("/search/spotify", response_model=SearchResponse)
def search_by_spotify_playlist(url: str, limit: int = 10):
    """Synesthetic Discovery: Map a Spotify playlist's vibe to movie recommendations."""
    logger.info("Spotify sync request: %s", url)

    playlist_id = _extract_playlist_id(url)
    logger.info("Extracted playlist ID: %s", playlist_id)

    # ── Auth ──
    token = get_spotify_token()
    if not token:
        raise HTTPException(status_code=502, detail="Spotify authentication failed. Check server logs for details.")

    # ── Fetch playlist tracks ──
    headers = {"Authorization": f"Bearer {token}"}
    try:
        res = requests.get(
            f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks",
            headers=headers,
            params={"limit": 50, "fields": "items(track(name,artists(name)))"},
            timeout=10,
        )
    except requests.RequestException as e:
        logger.error("Spotify playlist request failed: %s", e)
        raise HTTPException(status_code=502, detail=f"Could not reach Spotify API: {e}")

    if res.status_code != 200:
        error_body = res.json() if res.headers.get("content-type", "").startswith("application/json") else {}
        spotify_msg = error_body.get("error", {}).get("message", res.text[:200])
        logger.error("Spotify API error %d: %s", res.status_code, spotify_msg)
        raise HTTPException(status_code=res.status_code, detail=f"Spotify API error: {spotify_msg}")

    items = res.json().get("items", [])
    logger.info("Fetched %d tracks from playlist %s", len(items), playlist_id)

    if not items:
        raise HTTPException(status_code=404, detail="Playlist is empty or could not be read.")

    # ── Infer mood from metadata ──
    mood_query = infer_mood_from_tracks(items)
    logger.info("Generated mood query: '%s'", mood_query)

    # ── Run semantic search ──
    raw_results = search(query=mood_query, top_k=limit)
    formatted = [format_movie(r) for r in raw_results]
    logger.info("Returning %d movie results for playlist %s", len(formatted), playlist_id)
    return SearchResponse(query=mood_query, results=formatted, total=len(formatted))

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

# ─── Director Hub ─────────────────────────────────────────────────────────────

def _parse_directors_field(meta: dict) -> list[str]:
    raw = meta.get("directors", "")
    if isinstance(raw, list):
        return [str(d).strip() for d in raw if str(d).strip()]
    if isinstance(raw, str):
        return [d.strip() for d in raw.split(",") if d.strip()]
    return []


def _get_movie_index(request: Request) -> list[tuple[str, dict]]:
    """All (chroma_id, metadata) pairs, cached after first load."""
    cached = getattr(request.app.state, "movie_index", None)
    if cached is not None:
        return cached
    collection = request.app.state.collection
    data = collection.get(include=["metadatas"])
    index = list(zip(data["ids"], data["metadatas"]))
    request.app.state.movie_index = index
    return index


@app.get("/directors")
def list_directors(request: Request):
    """All directors with movie counts, sorted most prolific first."""
    counts: dict[str, int] = {}
    for _, meta in _get_movie_index(request):
        for d in _parse_directors_field(meta or {}):
            counts[d] = counts.get(d, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    return {
        "directors": [{"name": name, "movie_count": n} for name, n in ranked],
        "total": len(ranked),
    }


@app.get("/directors/{director_name}/graph")
def director_graph(request: Request, director_name: str):
    """Force-graph payload: director hub + poster satellites."""
    nodes = [
        {"id": director_name, "label": director_name,
         "type": "director", "val": 30}
    ]
    links = []
    for mid, meta in _get_movie_index(request):
        meta = meta or {}
        if director_name not in _parse_directors_field(meta):
            continue
        poster_path = meta.get("poster_path") or ""
        nodes.append({
            "id": mid,
            "label": meta.get("title", ""),
            "poster_url": (
                f"https://image.tmdb.org/t/p/w342{poster_path}"
                if poster_path else None
            ),
            "type": "movie",
            "val": 15,
        })
        links.append({"source": director_name, "target": mid})

    if not links:
        raise HTTPException(status_code=404, detail="Director not found")
    return {"nodes": nodes, "links": links}

@app.get("/featured", response_model=MovieResult)
def get_featured():
    """Return the featured film of the day from TMDB."""
    TMDB_API_KEY = os.getenv("TMDB_API_KEY")
    if not TMDB_API_KEY:
        raise HTTPException(status_code=500, detail="TMDB API key not configured")
        
    try:
        headers = {"User-Agent": "Mozilla/5.0", "Connection": "close"}
        res = requests.get(
            "https://api.themoviedb.org/3/trending/movie/day",
            params={"api_key": TMDB_API_KEY},
            headers=headers,
            timeout=10
        )
        res.raise_for_status()
        data = res.json()
        results = data.get("results", [])
        if not results:
            raise HTTPException(status_code=404, detail="No trending movies found")
            
        movie = results[0]
        movie_id = movie.get("id")
        
        detail_res = requests.get(
            f"https://api.themoviedb.org/3/movie/{movie_id}",
            params={"api_key": TMDB_API_KEY, "append_to_response": "keywords"},
            headers=headers,
            timeout=10
        )
        detail_res.raise_for_status()
        detail_data = detail_res.json()
        
        genres = [g["name"] for g in detail_data.get("genres", [])]
        keywords_data = detail_data.get("keywords", {}).get("keywords", [])
        keywords = [k["name"] for k in keywords_data]
        
        release_year = ""
        release_date = detail_data.get("release_date")
        if release_date:
            release_year = release_date.split("-")[0]
            
        poster_path = detail_data.get("poster_path")
        backdrop_path = detail_data.get("backdrop_path")

        directors = []
        try:
            credits_res = requests.get(
                f"https://api.themoviedb.org/3/movie/{movie_id}/credits",
                params={"api_key": TMDB_API_KEY},
                headers=headers,
                timeout=10
            )
            credits_res.raise_for_status()
            directors = [
                c.get("name", "")
                for c in credits_res.json().get("crew", [])
                if c.get("job") == "Director" and c.get("name")
            ]
        except requests.RequestException:
            directors = []

        return MovieResult(
            id=detail_data.get("id", 0),
            title=detail_data.get("title") or detail_data.get("original_title") or "",
            overview=detail_data.get("overview") or "",
            genres=genres,
            keywords=keywords,
            release_year=release_year,
            rating=detail_data.get("vote_average", 0.0),
            similarity_score=1.0,
            poster_url=f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None,
            backdrop_url=f"https://image.tmdb.org/t/p/original{backdrop_path}" if backdrop_path else None,
            match_reason="Trending globally on TMDB today.",
            runtime=detail_data.get("runtime"),
            spoken_languages=[lang["english_name"] for lang in detail_data.get("spoken_languages", [])],
            production_companies=[comp["name"] for comp in detail_data.get("production_companies", [])],
            directors=directors or None
        )
    except requests.RequestException as e:
        logger.error(f"Failed to fetch featured movie from TMDB: {e}")
        
    # Fallback if API fails
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
        production_companies=["Legendary Pictures"],
        directors=["Denis Villeneuve"]
    )

@app.get("/health")
def health():
    """Liveness — is the process alive?"""
    return {"status": "ok"}

@app.get("/ready")
def ready(request: Request):
    """Readiness — is model + collection loaded?"""
    model = getattr(request.app.state, "model", None)
    collection = getattr(request.app.state, "collection", None)
    if model is None or collection is None:
        raise HTTPException(status_code=503, detail="Not ready")
    return {"status": "ready"}