"""New-review defaults and the boundary between paper dates and blog dates."""

import argparse
from contextlib import ExitStack, redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import blog

KEY = 'ABCD1234'
PAPER_TITLE = 'A Real Paper: Retrieval and Agents'


class NewReviewChecks(unittest.TestCase):
    def setUp(self):
        (ROOT / 'work').mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix='review-defaults-', dir=ROOT / 'work')
        self.vault = Path(self.temporary.name) / 'vault'
        self.note = self.vault / 'Blog/Literature/paper.md'
        self.note.parent.mkdir(parents=True)
        self.note.write_text('Private reading note')
        self.item = {'data': {'itemType': 'conferencePaper', 'title': PAPER_TITLE,
                             'date': '2024-06-01', 'conferenceName': 'ACL',
                             'DOI': 'https://doi.org/10.1234/test_(v2)',
                             'tags': [{'tag': 'RAG'}, {'tag': 'rag'}, {'tag': 'Agent'}]}}
        self.csl = {'type': 'paper-conference', 'title': PAPER_TITLE,
                    'issued': {'date-parts': [[2024, 6, 1]]},
                    'container-title': 'Proceedings of ACL', 'DOI': '10.1234/test_(v2)'}

    def tearDown(self):
        self.temporary.cleanup()

    def create(self, *, title=None, selected=True):
        args = argparse.Namespace(slug='paper-review', title=title, category='RAG',
                                  zotero=KEY if selected else None)
        client = Mock()
        client.get_item.return_value = self.item
        client.get_csl.return_value = self.csl
        with ExitStack() as stack:
            stack.enter_context(patch.object(blog, 'config', return_value={
                'vault': str(self.vault), 'reviews': 'Blog/Reviews'}))
            stack.enter_context(patch.object(blog, 'import_zotero', return_value=self.note))
            stack.enter_context(patch.object(blog, 'ZoteroClient', return_value=client))
            stack.enter_context(patch.object(blog, 'today', return_value='2026-11-06'))
            stack.enter_context(patch('builtins.input', side_effect=AssertionError('Unexpected prompt')))
            stack.enter_context(redirect_stdout(io.StringIO()))
            blog.new_post(args)
        path = self.vault / 'Blog/Reviews/paper-review.md'
        text = path.read_text()
        header = text.split('---', 2)[1]
        meta = {key: json.loads(value) for key, value in
                (line.split(': ', 1) for line in header.strip().splitlines())}
        return meta, text, client

    def test_selected_paper_uses_actual_title_without_another_title_prompt(self):
        meta, text, _ = self.create()
        self.assertEqual(meta['title'], f'[논문리뷰]:{PAPER_TITLE}')
        self.assertNotIn('[논문명]', meta['title'])
        self.assertFalse(meta['blog_publish'])
        self.assertIn('[@zotero-ABCD1234]', text)
        self.assertIn('[[Blog/Literature/paper|Zotero 읽기 메모]]', text)

    def test_paper_date_and_venue_do_not_replace_blog_publication_date(self):
        meta, _, _ = self.create()
        self.assertIn('논문 발표: 2024-06-01', meta['subtitle'])
        self.assertIn('학회·게재처: ACL', meta['subtitle'])
        self.assertEqual(meta['date'], '2026-11-06')
        self.assertEqual(meta['date-modified'], '2026-11-06')

    def test_zotero_tags_merge_with_topic_and_doi_is_a_clickable_link(self):
        meta, text, _ = self.create()
        self.assertEqual(meta['categories'], ['RAG', 'Agent'])
        self.assertIn('https://doi.org/10.1234/test_%28v2%29', text)
        self.assertNotIn('<!-- PAPER_DOI -->', text)

    def test_missing_paper_fields_are_explicitly_unknown(self):
        self.item = {'data': {'itemType': 'preprint', 'title': PAPER_TITLE,
                              'dateAdded': '2026-11-06T00:00:00Z'}}
        self.csl = {'type': 'article', 'title': PAPER_TITLE}
        meta, text, _ = self.create()
        self.assertEqual(meta['subtitle'], '논문 발표: 미확인 · 학회·게재처: 미확인')
        self.assertIn('DOI: 미확인', text)
        self.assertNotIn('https://doi.org/', text)

    def test_custom_review_title_is_preserved(self):
        meta, _, _ = self.create(title='직접 정한 리뷰 제목')
        self.assertEqual(meta['title'], '직접 정한 리뷰 제목')
        self.assertIn('2024-06-01', meta['subtitle'])

    def test_manual_review_has_no_invented_paper_metadata(self):
        meta, text, client = self.create(title='직접 작성한 글', selected=False)
        self.assertEqual(meta['title'], '직접 작성한 글')
        self.assertNotIn('subtitle', meta)
        self.assertNotIn('DOI:', text)
        self.assertNotIn('PAPER_DOI', text)
        client.get_item.assert_not_called()
        client.get_csl.assert_not_called()


if __name__ == '__main__':
    unittest.main()
