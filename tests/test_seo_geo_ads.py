import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import build  # noqa: E402


class SeoGeoAdsTests(unittest.TestCase):
    def test_all_jsonld_blocks_are_valid_and_use_primary_domain(self):
        blocks = 0
        for page in sorted(ROOT.glob("**/*.html")):
            if page.name.startswith("._"):
                continue
            rel = page.relative_to(ROOT).as_posix()
            if rel.startswith(("node_modules/", "templates/")):
                continue
            html_text = page.read_text(encoding="utf-8")
            for raw in re.findall(r'<script type="application/ld\+json">\s*(.*?)\s*</script>', html_text, re.DOTALL):
                parsed = json.loads(raw)
                self.assertIsInstance(parsed, dict, f"{rel} has non-object JSON-LD")
                blocks += 1
        self.assertGreaterEqual(blocks, 150)

    def test_canonicals_match_site_url(self):
        site_url = build.SITE_URL
        self.assertEqual(site_url, "https://garryling.427795.xyz")
        for page in sorted(ROOT.glob("**/*.html")):
            if page.name.startswith("._"):
                continue
            rel = page.relative_to(ROOT).as_posix()
            if rel.startswith(("node_modules/", "templates/")) or rel in ("404.html", "docs/prd/index.html", "shexian/index.html") or (rel.startswith("google") and rel.endswith(".html")):
                continue
            html_text = page.read_text(encoding="utf-8")
            if 'content="noindex"' in html_text:
                continue
            m = re.search(r'<link\s+rel="canonical"\s+href="([^"]+)"', html_text)
            self.assertIsNotNone(m, f"{rel} missing canonical link")
            self.assertTrue(m.group(1).startswith(site_url + "/"), f"{rel} canonical {m.group(1)} does not start with {site_url}/")

    def test_jobs_jsonld_contains_job_postings(self):
        out = build.render_jobs_jsonld(limit=5)
        self.assertIn("JobPosting", out)
        raw = re.search(r'<script type="application/ld\+json">(.*)</script>', out, re.DOTALL).group(1)
        data = json.loads(raw)
        self.assertEqual(data["@type"], "ItemList")
        first = data["itemListElement"][0]["item"]
        self.assertEqual(first["@type"], "JobPosting")
        for key in ("title", "datePosted", "hiringOrganization", "jobLocation", "description"):
            self.assertTrue(first.get(key), f"JobPosting missing {key}")

    def test_ads_disabled_by_default_and_enabled_when_configured(self):
        empty_site = {"analytics": {"provider": "goatcounter", "code": "anaxagore"}, "ads": {"provider": "adsense", "client": "", "slot": ""}}
        self.assertNotIn("googlesyndication", build.render_analytics(empty_site))
        self.assertEqual(build.render_ad_slot(empty_site), "")
        self.assertNotIn("google-adsense-account", build.render_verification(empty_site))

        active_site = {
            "analytics": {"provider": "goatcounter", "code": "anaxagore"},
            "ads": {"provider": "adsense", "client": "ca-pub-1234567890123456", "slot": "9876543210", "auto_ads": True},
        }
        self.assertIn("ca-pub-1234567890123456", build.render_analytics(active_site))
        self.assertIn('data-ad-slot="9876543210"', build.render_ad_slot(active_site))
        self.assertIn('name="google-adsense-account" content="ca-pub-1234567890123456"', build.render_verification(active_site))

        with tempfile.TemporaryDirectory() as tmp:
            orig_root = build.ROOT
            try:
                build.ROOT = Path(tmp)
                build.write_ads_txt(active_site)
                self.assertEqual(
                    (Path(tmp) / "ads.txt").read_text(encoding="utf-8"),
                    "google.com, pub-1234567890123456, DIRECT, f08c47fec0942fa0\n",
                )
                build.write_ads_txt(empty_site)
                self.assertFalse((Path(tmp) / "ads.txt").exists())
            finally:
                build.ROOT = orig_root
