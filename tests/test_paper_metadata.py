"""Pure fixtures for publication metadata; no network or Library changes."""

import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from paper_metadata import paper_metadata


class PaperMetadataTests(unittest.TestCase):
    def test_record_metadata_and_title_without_blog_prefix(self):
        item = {"key": "ABCD1234", "data": {
            "title": "<i>한국어</i> 논문", "date": "2024-7-3",
            "conferenceName": "ACL 2024", "proceedingsTitle": "Proceedings of ACL",
            "publicationTitle": "Other source", "DOI": "doi:10.18653/v1/2024.acl-long.1",
            "tags": [{"tag": "LLM"}, {"tag": "RAG"}],
        }}
        result = paper_metadata(item, {"title": "Fallback", "issued": {"date-parts": [[2020]]}})
        self.assertEqual(result, {"title": "한국어 논문", "published": "2024-07-03", "venue": "ACL 2024", "tags": ["LLM", "RAG"], "doi": "10.18653/v1/2024.acl-long.1"})
        self.assertFalse(result["title"].startswith("[논문리뷰]"))

    def test_missing_information_is_empty_and_library_dates_are_ignored(self):
        item = {"data": {"dateAdded": "2026-11-06T03:00:00Z", "dateModified": "2026-11-06T04:00:00Z"}}
        csl = {"accessed": {"date-parts": [[2026, 11, 6]]}}
        self.assertEqual(paper_metadata(item, csl), {"title": "", "published": "", "venue": "", "tags": [], "doi": ""})

    def test_csl_fallback_and_date_precision(self):
        for parts, expected in [([2024], "2024"), ([2024, 6], "2024-06"), ([2024, 6, 3], "2024-06-03")]:
            with self.subTest(parts=parts):
                result = paper_metadata({}, {"title": "Paper", "issued": {"date-parts": [parts]}, "event-title": "ICLR", "container-title": "Proceedings", "DOI": "https://doi.org/10.1234/example"})
                self.assertEqual(result["published"], expected)
                self.assertEqual(result["venue"], "ICLR")
                self.assertEqual(result["doi"], "10.1234/example")

    def test_venue_precedence_and_no_venue_from_preprint_doi(self):
        self.assertEqual(paper_metadata({"data": {"proceedingsTitle": "Proceedings of EMNLP", "publicationTitle": "Fallback"}}, {})["venue"], "Proceedings of EMNLP")
        self.assertEqual(paper_metadata({"data": {"publicationTitle": "Transactions on Machine Learning Research"}}, {})["venue"], "Transactions on Machine Learning Research")
        self.assertEqual(paper_metadata({}, {"container-title": "Journal"})["venue"], "Journal")
        result = paper_metadata({"data": {"itemType": "preprint", "title": "A paper at NeurIPS 2024", "DOI": "10.48550/arXiv.2401.01234"}}, {})
        self.assertEqual(result["venue"], "")
        self.assertEqual(result["published"], "")

    def test_raw_dates_keep_available_precision(self):
        dates = {"2020": "2020", "2020/5": "2020-05", "2020.5.22": "2020-05-22", "May 2020": "2020-05", "May 22, 2020": "2020-05-22", "2024년 3월 2일": "2024-03-02", "2024-07-03T16:20:00Z": "2024-07-03"}
        for value, expected in dates.items():
            with self.subTest(value=value):
                self.assertEqual(paper_metadata({"date": value}, {})["published"], expected)

    def test_invalid_and_status_dates_are_not_publication_dates(self):
        for value in ("2023-02-29", "2024-13", "2024-00-01", "forthcoming", "Accepted in 2024", "/Users/me/2024-05-03", True, [2024]):
            with self.subTest(value=value):
                self.assertEqual(paper_metadata({"date": value}, {})["published"], "")
        self.assertEqual(paper_metadata({"date": "not a date"}, {"issued": {"date-parts": [[2024, 2, 29]]}})["published"], "2024-02-29")
        self.assertEqual(paper_metadata({}, {"issued": {"date-parts": [[2024, 13]]}})["published"], "")

    def test_csl_interval_and_raw_date(self):
        self.assertEqual(paper_metadata({}, {"issued": {"date-parts": [[2024, 1, 2], [2024, 1, 4]]}})["published"], "2024-01-02 – 2024-01-04")
        self.assertEqual(paper_metadata({}, {"issued": {"raw": "2022"}})["published"], "2022")

    def test_doi_prefixes_url_normalization_and_fallback(self):
        for value in ("10.1234/ABC.Def", "doi:10.1234/ABC.Def", "DOI: 10.1234/ABC.Def", "https://doi.org/10.1234/ABC.Def", "http://dx.doi.org/10.1234/ABC.Def?utm_source=x", "<https://doi.org/10.1234/ABC.Def>"):
            with self.subTest(value=value):
                self.assertEqual(paper_metadata({"DOI": value}, {})["doi"], "10.1234/ABC.Def")
        self.assertEqual(paper_metadata({"DOI": "wrong"}, {"DOI": "https://doi.org/10.1234/a%2Fb"})["doi"], "10.1234/a/b")
        for value in ("https://example.org/10.1234/paper", "file:///Users/me/paper", "10.1234/a b", "not-a-doi", "https://secret@doi.org/10.1234/paper"):
            with self.subTest(value=value):
                self.assertEqual(paper_metadata({"DOI": value}, {})["doi"], "")

    def test_tags_are_cleaned_and_deduplicated_in_original_order(self):
        tags = [{"tag": "RAG", "type": 0}, {"tag": "<b>RAG</b>"}, "한국어", {"tag": "한국어"}, {"tag": " ", "type": 1}, None, {"tag": "file:///private/note"}, "C:\\Users\\me\\secret", "/Users/me/private"]
        self.assertEqual(paper_metadata({"tags": tags}, {})["tags"], ["RAG", "한국어"])

    def test_html_controls_and_local_paths_are_removed(self):
        item = {"data": {"title": "<script>alert(1)</script>한글\x00 논문 &amp; café", "conferenceName": "file:///Users/me/secret", "publicationTitle": "<b>학술지</b>\x1b", "tags": ["&lt;script&gt;bad&lt;/script&gt;LLM"]}}
        result = paper_metadata(item, {})
        self.assertEqual(result["title"], "한글 논문 & café")
        self.assertEqual(result["venue"], "학술지")
        self.assertEqual(result["tags"], ["LLM"])
        for value in ("/unknown/private.pdf", "\\\\server\\share\\paper.pdf", "C:\\Users\\me\\paper.pdf"):
            with self.subTest(value=value):
                self.assertEqual(paper_metadata({"title": value}, {})["title"], "")

    def test_inputs_are_not_mutated_and_malformed_optional_shapes_are_safe(self):
        item = {"data": {"title": "Title", "tags": [{"tag": "LLM"}]}}
        csl = {"issued": {"date-parts": [[2024]]}}
        before = copy.deepcopy((item, csl))
        paper_metadata(item, csl)
        self.assertEqual((item, csl), before)
        self.assertEqual(paper_metadata({"data": []}, {"issued": []})["published"], "")
        self.assertEqual(paper_metadata({"tags": "LLM"}, {})["tags"], [])


if __name__ == "__main__":
    unittest.main()
