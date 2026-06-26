import json
import sys
import os
from pathlib import Path
from collections import defaultdict

# Add backend to path to import quality.py
sys.path.append(str(Path(__file__).resolve().parent.parent / "backend"))
from quality import quality_score, LOW_QUALITY_THRESHOLD

def generate_report():
    data_path = Path(__file__).resolve().parent / "data" / "movies_enriched.json"
    if not data_path.exists():
        print(f"Error: Dataset not found at {data_path}")
        sys.exit(1)
        
    with open(data_path, 'r', encoding='utf-8') as f:
        movies = json.load(f)
        
    total_movies = len(movies)
    if total_movies == 0:
        print("Dataset is empty.")
        sys.exit(1)
        
    # Overall statistics
    total_score = 0
    below_threshold_count = 0
    score_distribution = defaultdict(int)
    
    # Grouping
    genre_stats = defaultdict(lambda: {"count": 0, "total_score": 0, "below_threshold": 0})
    lang_stats = defaultdict(lambda: {"count": 0, "total_score": 0, "below_threshold": 0})
    
    for movie in movies:
        score = quality_score(movie)
        
        total_score += score
        score_distribution[score] += 1
        
        is_low = score < LOW_QUALITY_THRESHOLD
        if is_low:
            below_threshold_count += 1
            
        # Genre breakdown
        genres = movie.get("genres")
        if isinstance(genres, str):
            genres = [g.strip() for g in genres.split(",") if g.strip()]
        for genre in (genres or []):
            genre_stats[genre]["count"] += 1
            genre_stats[genre]["total_score"] += score
            if is_low:
                genre_stats[genre]["below_threshold"] += 1
                
        # Language breakdown
        languages = movie.get("spoken_languages")
        if isinstance(languages, str):
            languages = [l.strip() for l in languages.split(",") if l.strip()]
        for lang in (languages or []):
            lang_stats[lang]["count"] += 1
            lang_stats[lang]["total_score"] += score
            if is_low:
                lang_stats[lang]["below_threshold"] += 1
                
    # Finalize report data
    report = {
        "overall": {
            "total_movies": total_movies,
            "average_score": round(total_score / total_movies, 2),
            "percentage_below_threshold": round((below_threshold_count / total_movies) * 100, 2),
            "score_distribution": dict(sorted(score_distribution.items()))
        },
        "genres": {},
        "spoken_languages": {}
    }
    
    for genre, stats in genre_stats.items():
        report["genres"][genre] = {
            "movie_count": stats["count"],
            "average_score": round(stats["total_score"] / stats["count"], 2),
            "percentage_below_threshold": round((stats["below_threshold"] / stats["count"]) * 100, 2)
        }
        
    for lang, stats in lang_stats.items():
        report["spoken_languages"][lang] = {
            "movie_count": stats["count"],
            "average_score": round(stats["total_score"] / stats["count"], 2),
            "percentage_below_threshold": round((stats["below_threshold"] / stats["count"]) * 100, 2)
        }
        
    # Save report
    output_path = Path(__file__).resolve().parent / "data" / "quality_report.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2)
        
    # Print summary table
    print("=========================================================")
    print("                 DATASET QUALITY REPORT                  ")
    print("=========================================================")
    print(f"Total Movies: {report['overall']['total_movies']}")
    print(f"Average Quality Score: {report['overall']['average_score']:.2f}")
    print(f"Below Threshold (<{LOW_QUALITY_THRESHOLD}): {report['overall']['percentage_below_threshold']:.1f}%")
    print("---------------------------------------------------------")
    print("Score Distribution:")
    for score in range(10):
        count = report['overall']['score_distribution'].get(score, 0)
        print(f"  Score {score}: {count} movies")
    print("=========================================================\n")

if __name__ == "__main__":
    generate_report()
