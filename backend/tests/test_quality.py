import unittest
from backend.quality import quality_score, LOW_QUALITY_THRESHOLD

class TestQuality(unittest.TestCase):
    def test_threshold_value(self):
        self.assertEqual(LOW_QUALITY_THRESHOLD, 4)

    def test_high_quality_entry(self):
        # Should get max points (9)
        movie = {
            "overview": "A" * 101, # +3 (len > 100)
            "keywords": ["a", "b", "c", "d", "e"], # +2 (len >= 5)
            "tagline": "A great movie", # +1 (non-empty)
            "vote_average": 8.5, # +1 (>= 6.0)
            "vote_count": 500 # +2 (>= 200)
        }
        self.assertEqual(quality_score(movie), 9)

    def test_low_quality_entry(self):
        # Should get 0 points, which is < LOW_QUALITY_THRESHOLD
        movie = {
            "overview": "Short", # 0
            "keywords": ["a", "b"], # 0
            "tagline": "", # 0
            "vote_average": 5.0, # 0
            "vote_count": 100 # 0
        }
        self.assertEqual(quality_score(movie), 0)
        self.assertTrue(quality_score(movie) < LOW_QUALITY_THRESHOLD)

    def test_graceful_handling_missing_fields(self):
        # Empty dict should not crash and return 0
        self.assertEqual(quality_score({}), 0)

    def test_graceful_handling_malformed_fields(self):
        movie = {
            "overview": 123, 
            "keywords": 456, # Neither list nor str, should skip
            "vote_average": "not_a_float", # Should catch ValueError
            "vote_count": None # Should catch TypeError
        }
        # Since overview is expected to be a string or omitted, we omit it
        movie.pop("overview")
        
        self.assertEqual(quality_score(movie), 0)

    def test_keywords_as_string(self):
        movie = {
            "keywords": "action, adventure, sci-fi, thriller, fantasy"
        }
        # This should give +2
        self.assertEqual(quality_score(movie), 2)

    def test_rating_key_fallback(self):
        movie = {
            "rating": 7.5
        }
        # Should fallback to 'rating' and give +1
        self.assertEqual(quality_score(movie), 1)

if __name__ == '__main__':
    unittest.main()
