LOW_QUALITY_THRESHOLD = 4

def quality_score(movie: dict) -> int:
    """
    Calculate the quality score of a movie entry based on completeness.
    Max score is 9.
    
    Rules:
    - overview length > 100 characters: +3
    - keywords count >= 5: +2
    - non-empty tagline: +1
    - vote_average >= 6.0: +1
    - vote_count >= 200: +2
    """
    score = 0
    
    if len(movie.get("overview", "")) > 100:
        score += 3
        
    keywords = movie.get("keywords")
    if isinstance(keywords, list):
        if len(keywords) >= 5:
            score += 2
    elif isinstance(keywords, str):
        if len([k for k in keywords.split(",") if k.strip()]) >= 5:
            score += 2
            
    if movie.get("tagline"):
        score += 1
        
    try:
        # Existing score uses "rating", new definition uses "vote_average", handle both
        rating = float(movie.get("vote_average", movie.get("rating", 0.0)))
        if rating >= 6.0:
            score += 1
    except (ValueError, TypeError):
        pass
        
    try:
        if int(movie.get("vote_count", 0)) >= 200:
            score += 2
    except (ValueError, TypeError):
        pass
        
    return score
