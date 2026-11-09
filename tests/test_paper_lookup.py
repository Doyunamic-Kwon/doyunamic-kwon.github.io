"""Publication matching and failure cases for the new-review metadata lookup."""

import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import paper_lookup
from paper_metadata import paper_metadata


class PaperLookupTests(unittest.TestCase):
    def setUp(self):
        self.title = "Paper: A Retrieval System"
        self.authors = [{"given": "Ada", "family": "Lee"}, {"given": "Jia", "family": "Chen"}]
        self.item = {"data": {"title": self.title, "date": "2025-02-10", "itemType": "preprint",
                              "DOI": "10.48550/arXiv.2502.00001"}}
        self.csl = {"title": self.title, "author": self.authors}
        self.work = {"DOI": "10.1234/accepted", "title": [self.title], "type": "proceedings-article",
                     "event": {"acronym": "ACL 2025"}, "published": {"date-parts": [[2025]]},
                     "resource": {"primary": {"URL": "https://proceedings.example.org/paper"}},
                     "author": self.authors}

    def lookup(self):
        return paper_lookup.lookup_paper_fields(self.item, self.csl, paper_metadata(self.item, self.csl))

    def test_arxiv_location_confirms_published_record_and_uses_paper_affiliations(self):
        html = f"""<title>{self.title}</title>
        <span class="ltx_creator ltx_role_author">
          <span class="ltx_contact ltx_role_affiliation"><span>Affiliation: </span>Institute of Computing</span>
          <span class="ltx_contact ltx_role_affiliation">Affiliation: and Robotics</span>
        </span>
        <div class="ltx_abstract">Code: <a href="https://github.com/author/paper">Code</a>.</div>
        <p>Related work: https://github.com/unrelated/project</p>"""
        responses = {
            "https://api.openalex.org/works/https://doi.org/10.48550/arXiv.2502.00001": json.dumps({
                "doi": "https://doi.org/10.1234/accepted", "display_name": self.title,
                "locations": [{"landing_page_url": "https://arxiv.org/abs/2502.00001v2"}],
                "authorships": [{"raw_affiliation_strings": ["Index fallback"]}],
            }),
            "https://api.crossref.org/works/10.1234/accepted": json.dumps({"message": self.work}),
            "https://arxiv.org/html/2502.00001": html,
            "https://api.github.com/repos/author/paper": json.dumps({
                "html_url": "https://github.com/author/Paper", "homepage": "https://author.example.org/paper",
            }),
        }
        with patch.object(paper_lookup, "_fetch", side_effect=lambda url: responses.get(url.split("?", 1)[0], "")):
            fields = self.lookup()
        self.assertEqual(fields, {
            "paper_venue": "ACL 2025", "paper_affiliations": ["Institute of Computing and Robotics"],
            "paper_url": "https://doi.org/10.48550/arXiv.2502.00001",
            "paper_page": "https://author.example.org/paper", "paper_github": "https://github.com/author/Paper",
        })

    def test_title_search_rejects_wrong_author_order_and_multiple_publications(self):
        wrong = {**self.work, "DOI": "10.1234/wrong", "author": list(reversed(self.authors))}
        multiple = {**self.work, "DOI": "10.1234/also-matches"}
        cases = (([wrong, self.work], "ACL 2025"), ([self.work, multiple], None))
        for items, expected in cases:
            with self.subTest(expected=expected):
                def fetch(url):
                    if url.startswith("https://api.crossref.org/works?"):
                        return json.dumps({"message": {"items": items}})
                    return ""

                with patch.object(paper_lookup, "_fetch", side_effect=fetch):
                    self.assertEqual(self.lookup().get("paper_venue"), expected)

    def test_no_network_result_preserves_confirmed_zotero_fields(self):
        self.item["data"].update({"conferenceName": "ACL 2025", "extra": "GitHub: https://github.com/author/paper"})
        with patch.object(paper_lookup, "_fetch", return_value=""):
            self.assertEqual(self.lookup(), {
                "paper_venue": "ACL 2025", "paper_url": "https://doi.org/10.48550/arXiv.2502.00001",
                "paper_github": "https://github.com/author/paper",
            })


if __name__ == "__main__":
    unittest.main()
