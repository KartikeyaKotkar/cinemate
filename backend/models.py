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
    match_reason: str | None  # Populated by template now, LLM in Phase 5

class SearchResponse(BaseModel):
    query: str
    results: list[MovieResult]
    total: int
