import unittest
from datetime import datetime, timezone

from scraper import (
    canon,
    infer_location,
    dedupe,
    filter_expired,
    make_id,
    normalize_google,
    normalize_un_professional,
    parse_datetime,
    parse_undp_job_anchor,
    normalize_un_apify,
    normalize_undp_oracle,
    parse_undp_oracle_job_html,
    normalize_undp_bing_result,
    normalize_toploker,
    parse_toploker_detail,
)


class ScraperTests(unittest.TestCase):
    def test_location_detection(self):
        self.assertEqual(infer_location("Jakarta, Indonesia"), "Jakarta")
        self.assertEqual(infer_location("Pontianak, Kalimantan Barat"), "Pontianak")
        self.assertEqual(infer_location("unknown place"), "Indonesia")

    def test_canon(self):
        self.assertEqual(canon("Sales & Marketing!"), "sales marketing")

    def test_stable_id(self):
        self.assertEqual(make_id("A", "B"), make_id("A", "B"))

    def test_date_parser(self):
        parsed = parse_datetime("2026-10-01T00:00:00Z")
        self.assertEqual(parsed, datetime(2026, 10, 1, tzinfo=timezone.utc))
        self.assertIsNotNone(parse_datetime("2 days ago"))

    def test_expiry_filter(self):
        active, expired, stale = filter_expired([
            {"title": "Expired", "status": "current", "expires_at": "2020-01-01", "posted_at": ""},
            {"title": "Stale", "status": "current", "expires_at": "", "posted_at": "30 days ago"},
            {"title": "Active", "status": "current", "expires_at": "", "posted_at": "2 days ago"},
            {"title": "No Date", "status": "current", "expires_at": "", "posted_at": "Unknown"},
        ])
        self.assertEqual(expired, 1)
        self.assertEqual(stale, 1)
        self.assertEqual([job["title"] for job in active], ["Active", "No Date"])

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
            "lowongan kerja Indonesia",
        )
        self.assertEqual(job["district"], "Ketapang")
        self.assertEqual(job["source"], "Google Jobs")
        self.assertEqual(job["salary"], "Rp 5.000.000")
        self.assertEqual(job["original_url"], "https://example.com/job/1")

    def test_google_asean_market(self):
        job = normalize_google(
            {
                "title": "Programme Officer",
                "company_name": "Example ASEAN Co",
                "location": "Kuala Lumpur",
                "via": "Example",
                "share_link": "https://example.com/job/asean",
                "description": "Programme role.",
                "detected_extensions": {},
            },
            "jobs Malaysia",
            market_country="Malaysia",
        )
        self.assertEqual(job["country"], "Malaysia")
        self.assertEqual(job["region"], "ASEAN")
        self.assertEqual(job["country_code"], "MY")

    def test_un_p_normalization(self):
        job = normalize_un_professional(
            {
                "title": "Programme Management Officer, P4",
                "link": "https://careers.un.org/job-openings",
                "guid": "123",
                "description": "Level: P-4 Job Network: Economic, Social and Development Job Family: Programme Management Category: Professional and Higher Categories Department/Office: Example Office Duty Station: NEW YORK Date Posted: Sep 1, 2026 Deadline: Oct 1, 2026",
            }
        )
        self.assertEqual(job["source"], "UN Careers — P-level")
        self.assertEqual(job["contract_level"], "P-4")
        self.assertEqual(job["country"], "Global")

    def test_undp_oracle_normalization(self):
        job = normalize_undp_oracle({
            "title": "Project Manager",
            "requisitionId": "12345",
            "url": "https://estm.fa.em2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/job/12345",
            "descriptionText": "Project management role, IPSA-10",
            "primaryLocation": "Dili, Timor-Leste",
            "postingDate": "2026-10-01T00:00:00Z",
            "postingEndDate": "2026-10-31T00:00:00Z",
            "jobSchedule": "Full time",
            "detailFetched": True,
        })
        self.assertEqual(job["source"], "UNDP — IPSA")
        self.assertEqual(job["contract_level"], "IPSA-10")
        self.assertEqual(job["location"], "Dili, Timor-Leste")
    def test_un_apify_normalization(self):
        job = normalize_un_apify({
            "title": "Programme Officer",
            "jobId": "285000",
            "url": "https://careers.un.org/jobopening",
            "description": "Professional and Higher Categories, P-4",
            "level": "P-4",
            "dutyStation": "Nairobi",
            "deadline": "2026-11-01",
        })
        self.assertEqual(job["source"], "UN Careers — P-level")
        self.assertEqual(job["contract_level"], "P-4")
        self.assertEqual(job["location"], "Nairobi")

    def test_undp_ipsa_parser(self):
        from bs4 import BeautifulSoup
        anchor = BeautifulSoup(
            '<a href="/cj_view_jobs.cfm/cj_view_job.cfm?cur_job_id=123">Job Title Policy Specialist Post level IPSA-11 Apply by Oct-20-26 Agency UNDP Location Home Based</a>',
            "html.parser",
        ).a
        job = parse_undp_job_anchor(anchor)
        self.assertEqual(job["source"], "UNDP — IPSA")
        self.assertEqual(job["contract_level"], "IPSA-11")
        self.assertEqual(job["location"], "Home Based")

    def test_toploker_normalization(self):
        job = normalize_toploker({
            "title": "Account Officer",
            "company": "Bank Padma",
            "location": "Kota Denpasar",
            "posted_at": "2026-10-07",
            "expires_at": "07 Oktober 2027",
            "description": "Drive branch sales.",
            "requirements": "Minimal S1.",
            "schedule_type": "Full Time",
            "url": "https://toploker.com/lowongan/2026-10-07!account-officer!di!bank-padma-1",
        })
        self.assertEqual(job["source"], "TopLoker")
        self.assertEqual(job["country"], "Indonesia")
        self.assertEqual(job["province"], "Bali")
        self.assertEqual(job["schedule_type"], "Full Time")

    def test_toploker_detail_parser(self):
        html = """
        <html><body>
        <div>Example Company</div>
        <div>Membuka Lowongan</div>
        <h2>Policy Officer</h2>
        <div>Ringkasan</div>
        <div>Status Kerja</div><div>:</div><div>Full Time</div>
        <div>Batas Lamaran</div><div>:</div><div>31 Oktober 2026</div>
        <div>Lokasi Kerja</div><div>:</div><div>Jakarta Selatan</div>
        <div>Deskripsi Pekerjaan</div><div>Develop policy briefs.</div>
        <div>Syarat Pekerjaan</div><div>S1.</div>
        <div>Kirim Lamaran</div><div>Do not include contact details.</div>
        </body></html>
        """
        job = parse_toploker_detail(html, "https://toploker.com/lowongan/2026-10-01!policy-officer!di!example-company-1")
        self.assertEqual(job["title"], "Policy Officer")
        self.assertEqual(job["company"], "Example Company")
        self.assertEqual(job["location"], "Jakarta Selatan")
        self.assertIn("Develop policy briefs", job["description"])

    def test_undp_oracle_list_row(self):
        job = normalize_undp_oracle({
            "Id": "9001",
            "Title": "Programme Specialist",
            "EmployerName": "UNDP",
            "PrimaryLocation": "Jakarta, Indonesia",
            "PostedDate": "2026-10-07T00:00:00Z",
            "ExternalPostedEndDate": "2026-10-31T00:00:00Z",
            "JobGrade": "IPSA-10",
            "ExternalUrlSeo": "https://estm.fa.em2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/job/9001",
        })
        self.assertIsNotNone(job)
        self.assertEqual(job["contract_level"], "IPSA-10")
        self.assertEqual(job["location"], "Jakarta, Indonesia")

    def test_indonesian_date_parser(self):
        parsed = parse_datetime("31 Oktober 2026")
        self.assertEqual(parsed, datetime(2026, 10, 31, tzinfo=timezone.utc))

    def test_undp_bing_normalization(self):
        job = normalize_undp_bing_result({
            "title": "Chief Engineering Specialist [Open to candidates] - UNDP Careers",
            "url": "https://estm.fa.em2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/job/37266",
            "snippet": "Libreville, Gabon Be the First to Apply Job Info Job Identification 37266 Posting Date 10/05/2026, 12:22 PM Apply Before 10/20/2026, 03:59 AM Job Schedule Full time Locations Libreville, Gabon Agency UNDP Grade IPSA-11 Vacancy Type International Personnel Service Agreement",
        })
        self.assertIsNotNone(job)
        self.assertEqual(job["contract_level"], "IPSA-11")
        self.assertEqual(job["location"], "Libreville, Gabon")
        self.assertIn("/job/37266", job["original_url"])

    def test_undp_oracle_html_parser(self):
        html = """
        <html><body>
        <h1>Public and Digital Investment Specialist</h1>
        <div>Job Identification 36742</div>
        <div>Posting Date 09/30/2026, 02:33 PM</div>
        <div>Apply Before 10/08/2026, 03:59 AM</div>
        <div>Job Schedule Full time</div>
        <div>Locations Rome, Italy</div>
        <div>Agency UNDP</div>
        <div>Grade IPSA-10</div>
        <div>Vacancy Type International Personnel Service Agreement</div>
        <div>Practice Area Nature, Climate and Energy</div>
        <div>Bureau Bureau for Policy and Programme Support</div>
        <div>Contract Duration 1 Year</div>
        <div>Education &amp; Work Experience Master's Degree</div>
        <div>Job Description</div>
        <div>Digital and public investment role.</div>
        </body></html>
        """
        job = parse_undp_oracle_job_html(
            html,
            "https://estm.fa.em2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/job/36742"
        )
        self.assertIsNotNone(job)
        self.assertEqual(job["contract_level"], "IPSA-10")
        self.assertEqual(job["location"], "Rome, Italy")
        self.assertEqual(job["source"], "UNDP — IPSA")

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
