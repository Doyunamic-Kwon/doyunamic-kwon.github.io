"""Read-only fixtures for the Zotero bridge; no real library is accessed."""

import io
import json
from pathlib import Path
import sys
import unittest
from unittest import mock
from urllib.error import HTTPError, URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from zotero_client import ZoteroClient, ZoteroError, citation_key


KEY = "ABCD1234"
PDF = "PDFX1234"
ANNOTATION = "ANNX1234"
CSL = {"id": "changing-id", "type": "paper-conference", "title": "한국어 논문 · café", "author": [{"family": "김", "given": "도윤"}], "issued": {"date-parts": [[2026, 11, 5]]}, "URL": "https://example.org/paper"}


class Response(io.BytesIO):
    def __init__(self, data):
        super().__init__(json.dumps(data, ensure_ascii=False).encode("utf-8"))


def client_with_response(data):
    client = ZoteroClient()
    client._opener = mock.Mock()
    client._opener.open.return_value = Response(data)
    return client


class ZoteroClientTests(unittest.TestCase):
    def test_citation_keys_are_stable_and_strict(self):
        self.assertEqual(citation_key(KEY), "zotero-ABCD1234")
        for invalid in ("abcd1234", "ABCD12345", "../items", "ABCD123!", None, 12345678):
            with self.subTest(invalid=invalid), self.assertRaises(ZoteroError):
                citation_key(invalid)

    def test_connection_is_restricted_to_local_zotero(self):
        ZoteroClient("http://localhost:23119/")
        for url in ("https://example.org:23119", "http://127.0.0.1:80", "http://localhost:23119@evil.example", "http://localhost:23119/api/", "file:///private/data", "http://user:secret@localhost:23119", "http://localhost:23119/?secret=x"):
            with self.subTest(url=url), self.assertRaises(ZoteroError):
                ZoteroClient(url)

    def test_list_only_returns_reference_summaries_and_uses_get(self):
        client = client_with_response([
            {"key": KEY, "data": {"itemType": "journalArticle", "title": "한글 제목", "abstractNote": "private"}},
            {"key": PDF, "data": {"itemType": "attachment", "title": "PDF"}},
        ])
        self.assertEqual(client.list_items(5), [{"key": KEY, "title": "한글 제목", "itemType": "journalArticle"}])
        request = client._opener.open.call_args.args[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertIn("/api/users/0/items/top?limit=5", request.full_url)
        self.assertEqual(request.get_header("Zotero-api-version"), "3")
        self.assertNotIn("Authorization", dict(request.header_items()))

    def test_csl_strips_private_fields_and_local_paths(self):
        value = {**CSL, "abstract": "PRIVATE ABSTRACT", "note": "private", "file": "/Users/me/paper.pdf", "tags": ["private"], "URL": "file:///Users/me/paper.pdf", "publisher-place": "/Users/me/private", "author": [{"family": "김", "given": "도윤", "note": "private", "URL": "file:///private/name"}]}
        result = client_with_response([value]).get_csl(KEY)
        self.assertEqual(result["id"], citation_key(KEY))
        self.assertEqual(result["title"], "한국어 논문 · café")
        self.assertEqual(result["author"], [{"family": "김", "given": "도윤"}])
        for field in ("abstract", "note", "file", "tags", "URL", "publisher-place"):
            self.assertNotIn(field, result)
        self.assertNotIn("private", json.dumps(result, ensure_ascii=False))

    def test_csl_accepts_single_object_and_preserves_public_url_and_dates(self):
        result = client_with_response(CSL).get_csl(KEY)
        self.assertEqual(result["URL"], CSL["URL"])
        self.assertEqual(result["issued"], CSL["issued"])

    def test_csl_drops_unsafe_urls(self):
        for url in ("javascript:alert(1)", "file:///Users/me/paper", "https://me:secret@example.org/x", "https://example.org/\nprivate"):
            with self.subTest(url=url):
                self.assertNotIn("URL", client_with_response({**CSL, "URL": url}).get_csl(KEY))
        self.assertEqual(client_with_response({**CSL, "URL": "http://example.org/paper"}).get_csl(KEY)["URL"], "http://example.org/paper")

    def test_exports_only_selected_keys_and_deduplicates(self):
        client = ZoteroClient()
        with mock.patch.object(client, "get_csl", side_effect=lambda key: {"id": citation_key(key)}) as export:
            self.assertEqual(client.export_references([KEY, PDF, KEY]), [{"id": citation_key(KEY)}, {"id": citation_key(PDF)}])
            self.assertEqual(export.call_args_list, [mock.call(KEY), mock.call(PDF)])

    def test_all_selected_keys_are_validated_before_access(self):
        client = ZoteroClient()
        with mock.patch.object(client, "get_csl") as export, self.assertRaises(ZoteroError):
            client.export_references([KEY, "bad"])
        export.assert_not_called()

    def test_api_errors_hide_private_response_data(self):
        for status in (403, 404, 500):
            client = ZoteroClient()
            client._opener = mock.Mock()
            client._opener.open.side_effect = HTTPError("http://localhost/private-title", status, "PRIVATE NOTE", {}, io.BytesIO(b"PRIVATE LIBRARY"))
            with self.subTest(status=status), self.assertRaises(ZoteroError) as caught:
                client.get_item(KEY)
            message = str(caught.exception)
            self.assertNotIn("PRIVATE", message)
            self.assertNotIn("private-title", message)
            if status == 403:
                self.assertIn("설정", message)
                self.assertIn("통신", message)

    def test_network_and_json_errors_hide_response_contents(self):
        client = ZoteroClient()
        client._opener = mock.Mock()
        client._opener.open.side_effect = URLError("PRIVATE PATH")
        with self.assertRaises(ZoteroError) as caught:
            client.get_item(KEY)
        self.assertNotIn("PRIVATE", str(caught.exception))
        client._opener.open.side_effect = None
        client._opener.open.return_value = io.BytesIO(b"PRIVATE INVALID JSON")
        with self.assertRaises(ZoteroError) as caught:
            client.get_item(KEY)
        self.assertNotIn("PRIVATE", str(caught.exception))

    def test_private_note_converts_html_and_annotation_links(self):
        client = ZoteroClient()
        note = {"key": "NOTE1234", "data": {"itemType": "note", "note": '<p>한글 <strong>핵심</strong><br><em>생각</em> &amp; café</p><script>private_js()</script><p><a href="https://example.org">문헌</a> <a href="javascript:alert(1)">링크</a><img src="https://example.org/tracker"></p>'}}
        pdf = {"key": PDF, "data": {"itemType": "attachment", "contentType": "application/pdf"}}
        annotation = {"key": ANNOTATION, "data": {"itemType": "annotation", "annotationText": "밑줄 친 문장", "annotationComment": "내 해석", "annotationPageLabel": "iii", "annotationPosition": '{"pageIndex": 2}'}}
        with mock.patch.object(client, "get_item", return_value={"key": KEY, "data": {"itemType": "journalArticle", "title": CSL["title"]}}), mock.patch.object(client, "get_csl", return_value={**CSL, "id": citation_key(KEY)}), mock.patch.object(client, "get_children", side_effect=lambda key: [note, pdf] if key == KEY else [annotation]):
            text = client.literature_markdown(KEY)
        self.assertIn('zotero_key: "ABCD1234"', text)
        self.assertIn('citation_key: "zotero-ABCD1234"', text)
        self.assertIn("한글 **핵심**\n*생각* & café", text)
        self.assertIn("[문헌](https://example.org)", text)
        self.assertIn("zotero://open-pdf/library/items/PDFX1234?page=3&annotation=ANNX1234", text)
        self.assertIn("페이지 iii", text)
        self.assertIn("> 밑줄 친 문장", text)
        self.assertIn("메모: 내 해석", text)
        for hidden in ("private_js", "javascript:", "<script>", "<img", "tracker"):
            self.assertNotIn(hidden, text)

    def test_missing_physical_page_is_not_invented(self):
        self.assertIsNone(ZoteroClient._annotation_page({"annotationPageLabel": "iv"}))
        self.assertEqual(ZoteroClient._annotation_page({"annotationPageLabel": "8"}), 8)
        self.assertEqual(ZoteroClient._annotation_page({"annotationPageLabel": "8", "annotationPosition": {"pageIndex": 0}}), 1)

    def test_invalid_response_shapes_are_reported(self):
        for value in ([], [{}, {}], {"title": "private without type"}):
            with self.subTest(value=value), self.assertRaises(ZoteroError):
                client_with_response(value).get_csl(KEY)
        with self.assertRaises(ZoteroError):
            client_with_response({"not": "a list"}).get_children(KEY)


if __name__ == "__main__":
    unittest.main()
