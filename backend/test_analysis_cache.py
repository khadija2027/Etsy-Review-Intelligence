import unittest
from unittest.mock import patch

from backend import analysis_cache


class AnalysisCacheTests(unittest.TestCase):
    def setUp(self):
        analysis_cache._cache.clear()

    @patch("backend.analysis_cache.analyse_reviews")
    def test_identical_reviews_reuse_result_without_sharing_mutations(self, analyse):
        analyse.return_value = {"scores": [0.5]}
        reviews = [{"review_text": "Nice", "rating": 5}]
        first, hit = analysis_cache.analyse_cached(reviews)
        self.assertFalse(hit)
        first["scores"].append(1)
        second, hit = analysis_cache.analyse_cached(reviews)
        self.assertTrue(hit)
        self.assertEqual(second, {"scores": [0.5]})
        analyse.assert_called_once_with(reviews)

    @patch("backend.analysis_cache.analyse_reviews", return_value={})
    def test_changed_reviews_and_version_invalidate_cache(self, analyse):
        analysis_cache.analyse_cached([{"rating": 5}])
        _, hit = analysis_cache.analyse_cached([{"rating": 4}])
        self.assertFalse(hit)
        with patch("backend.analysis_cache.ANALYSIS_VERSION", "new-version"):
            _, hit = analysis_cache.analyse_cached([{"rating": 4}])
            self.assertFalse(hit)
        self.assertEqual(analyse.call_count, 3)

    @patch("backend.analysis_cache.analyse_reviews", return_value={})
    def test_cache_is_bounded(self, analyse):
        for index in range(analysis_cache._MAX_ENTRIES + 1):
            analysis_cache.analyse_cached([{"rating": index}])
        self.assertEqual(len(analysis_cache._cache), analysis_cache._MAX_ENTRIES)
        _, hit = analysis_cache.analyse_cached([{"rating": 0}])
        self.assertFalse(hit)


if __name__ == "__main__":
    unittest.main()
