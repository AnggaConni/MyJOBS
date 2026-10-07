import unittest

from scraper import canon, city_of, dedupe, make_id, normalize_google


class ScraperTests(unittest.TestCase):
    def test_city_detection(self):
        self.assertEqual(city_of("Kabupaten Ketapang"), "Ketapang")
        self.assertEqual(city_of("Pontianak, Kalimantan Barat"), "Pontianak")
        self.assertEqual(city_of("unknown place"), "Kalimantan Barat")

    def test_canon(self):
        self.assertEqual(canon("Sales & Marketing!"), "sales marketing")

    def test_stable_id(self):
        self.assertEqual(make_id("A", "B"), make_id("A", "B"))

    def test_google_normalization(self):
        job = normalize_google(
            {
                "title": "Sales Executive",
                "company_name": "Example Co",
                "location": "Ketapang, Kalimantan Barat",
                "via": "LinkedIn",
                "share_link": "https://example.com/job/1",
                "description": "Handle sales pipeline.",
                "detected_extensions": {
                    "posted_at": "2 days ago",
                    "schedule_type": "Full-time",
                    "salary": "Rp 5.000.000",
                },
                "extensions": ["Full-time"],
            },
            "lowongan kerja Ketapang",
        )
        self.assertEqual(job["district"], "Ketapang")
        self.assertEqual(job["source"], "Google Jobs")
        self.assertEqual(job["salary"], "Rp 5.000.000")
        self.assertEqual(job["original_url"], "https://example.com/job/1")

    def test_dedupe_by_url(self):
        job = {
            "title": "A",
            "company": "B",
            "district": "Ketapang",
            "original_url": "https://example.com/a",
        }
        self.assertEqual(len(dedupe([job, dict(job)])), 1)


if __name__ == "__main__":
    unittest.main()
