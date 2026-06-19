import unittest
import numpy as np
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from search import calculate_movie_score, _rerank

class MockCollection:
    def get(self, include=None):
        # Returns a list of metadatas with rating 7.0 to set global mean C = 7.0
        return {
            "metadatas": [
                {"rating": 7.0, "popularity": 10.0, "vote_count": 100},
                {"rating": 7.0, "popularity": 20.0, "vote_count": 200},
            ]
        }

class TestSearchLogic(unittest.TestCase):
    def test_bayesian_rating_downweighting(self):
        # C = 7.0 (global mean rating)
        global_mean = 7.0
        max_popularity = 1000.0
        weights = {"similarity": 0.7, "rating": 0.2, "popularity": 0.1}

        # Movie A: raw rating = 9.5, but only 5 votes (low confidence)
        movie_a = {
            "rating": 9.5,
            "vote_count": 5,
            "popularity": 10.0,
            "_similarity": 0.8
        }

        # Movie B: raw rating = 8.5, but 500 votes (high confidence)
        movie_b = {
            "rating": 8.5,
            "vote_count": 500,
            "popularity": 10.0,
            "_similarity": 0.8
        }

        score_a = calculate_movie_score(movie_a, max_popularity, global_mean, weights)
        score_b = calculate_movie_score(movie_b, max_popularity, global_mean, weights)

        # Movie B should have a higher rating contribution and final score than Movie A
        # because Movie A's low vote count pulls it strongly down towards global mean C (7.0)
        self.assertTrue(
            score_b["rating_contribution"] > score_a["rating_contribution"],
            f"Expected B's rating contribution ({score_b['rating_contribution']}) to be greater than A's ({score_a['rating_contribution']})"
        )
        self.assertTrue(
            score_b["final_score"] > score_a["final_score"],
            f"Expected B's final score ({score_b['final_score']}) to be greater than A's ({score_a['final_score']})"
        )

    def test_log_popularity_scaling(self):
        global_mean = 7.0
        max_pop = 1000.0
        weights = {"similarity": 0.7, "rating": 0.2, "popularity": 0.1}

        # Movie A: very popular
        movie_a = {"rating": 7.0, "vote_count": 100, "popularity": 1000.0, "_similarity": 0.8}
        # Movie B: moderately popular
        movie_b = {"rating": 7.0, "vote_count": 100, "popularity": 100.0, "_similarity": 0.8}
        # Movie C: unpopular (min popularity = 0)
        movie_c = {"rating": 7.0, "vote_count": 100, "popularity": 0.0, "_similarity": 0.8}

        score_a = calculate_movie_score(movie_a, max_pop, global_mean, weights)
        score_b = calculate_movie_score(movie_b, max_pop, global_mean, weights)
        score_c = calculate_movie_score(movie_c, max_pop, global_mean, weights)

        # Log scale gap:
        log_gap = score_a["popularity_contribution"] - score_b["popularity_contribution"]

        # Min-max scale gap:
        # norm_pop_A = 1.0, norm_pop_B = 100 / 1000 = 0.1
        # gap = (1.0 - 0.1) * weight = 0.9 * 0.1 = 0.09
        min_max_gap = ((1000.0 - 100.0) / 1000.0) * weights["popularity"]

        # Log scale gap should be significantly smaller than min-max gap
        self.assertTrue(
            log_gap < min_max_gap,
            f"Expected log gap ({log_gap}) to be less than min-max gap ({min_max_gap})"
        )

    def test_debug_mode_breakdown(self):
        mock_col = MockCollection()
        
        # Candidate results
        results = [
            {"title": "Movie A", "rating": 8.0, "vote_count": 100, "popularity": 50.0, "_similarity": 0.7},
            {"title": "Movie B", "rating": 7.5, "vote_count": 150, "popularity": 30.0, "_similarity": 0.6},
        ]

        # Case 1: debug=False (default) -> keys should not have _score_breakdown
        results_nodebug = [dict(r) for r in results]
        reranked_nodebug = _rerank(results_nodebug, top_k=2, collection=mock_col, debug=False)
        for r in reranked_nodebug:
            self.assertNotIn("_score_breakdown", r)

        # Case 2: debug=True -> keys should have _score_breakdown
        results_debug = [dict(r) for r in results]
        reranked_debug = _rerank(results_debug, top_k=2, collection=mock_col, debug=True)
        for r in reranked_debug:
            self.assertIn("_score_breakdown", r)
            breakdown = r["_score_breakdown"]
            self.assertIn("final_score", breakdown)
            self.assertIn("similarity_score", breakdown)
            self.assertIn("rating_contribution", breakdown)
            self.assertIn("popularity_contribution", breakdown)

if __name__ == "__main__":
    unittest.main()
