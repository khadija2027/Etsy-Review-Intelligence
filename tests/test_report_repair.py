import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import app as api


class ReportRepairTests(unittest.TestCase):
    def test_saved_reports_restore_missing_scores_and_persist_them(self):
        for comparison in (False, True):
            with self.subTest(comparison=comparison), tempfile.TemporaryDirectory() as directory:
                listing = {
                    "reviews": [{"rating": 5, "review_text": "Nice"}],
                    "sentiment_analysis": {"cluster_metadata": {"analysis_version": api.ANALYSIS_VERSION}},
                }
                payload = {"report_type": "listing_comparison", "listings": [listing]} if comparison else listing
                path = Path(directory) / "report.json"
                path.write_text(json.dumps(payload), encoding="utf-8")

                def annotate(reviews):
                    reviews[0]["sentiment"] = {"score": 0.9, "label": "positive"}
                    return listing["sentiment_analysis"]

                with patch.object(api, "DATA_DIR", Path(directory)), patch.object(
                    api, "analyse_reviews", side_effect=annotate
                ) as analyse, patch.object(api, "compare_listing_satisfaction", return_value={"updated": True}):
                    api.report("report.json")
                    saved = json.loads(path.read_text(encoding="utf-8"))
                    restored = saved["listings"][0] if comparison else saved
                    self.assertEqual(restored["reviews"][0]["sentiment"]["score"], 0.9)
                    if comparison:
                        self.assertEqual(saved["comparison"], {"updated": True})
                    api.report("report.json")
                    analyse.assert_called_once()


if __name__ == "__main__":
    unittest.main()
