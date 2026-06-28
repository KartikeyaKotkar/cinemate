from pydantic import BaseModel

class MovieResult(BaseModel):
    id: int
    title: str
    overview: str
    genres: list[str]
    keywords: list[str]
    release_year: str
    rating: float
    similarity_score: float
    poster_url: str | None
    backdrop_url: str | None = None
    match_reason: str | None  # Populated by template now, LLM in Phase 5
    tagline: str | None = None
    runtime: int | None = None
    spoken_languages: list[str] | None = None
    production_companies: list[str] | None = None

class SearchResponse(BaseModel):
    query: str
    results: list[MovieResult]
    total: int
