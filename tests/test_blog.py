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
        self.lookup_fields = {}

    def tearDown(self):
        self.temporary.cleanup()

    def create(self, *, title=None, selected=True, category='RAG', folder='', answers=None):
        args = argparse.Namespace(slug='paper-review', title=title, category=category,
                                  zotero=KEY if selected else None, folder=folder)
        client = Mock()
        client.get_item.return_value = self.item
        client.get_csl.return_value = self.csl
        with ExitStack() as stack:
            stack.enter_context(patch.object(blog, 'config', return_value={
                'vault': str(self.vault), 'reviews': 'Blog/Reviews'}))
            stack.enter_context(patch.object(blog, 'import_zotero', return_value=self.note))
            stack.enter_context(patch.object(blog, 'ZoteroClient', return_value=client))
            self.lookup = stack.enter_context(patch.object(blog, 'lookup_paper_fields', return_value=self.lookup_fields))
            stack.enter_context(patch.object(blog, 'today', return_value='2026-11-06'))
            stack.enter_context(patch('builtins.input', side_effect=answers if answers is not None else AssertionError('Unexpected prompt')))
            stack.enter_context(redirect_stdout(io.StringIO()))
            blog.new_post(args)
        path = next((self.vault / 'Blog/Reviews').rglob('paper-review.md'))
        self.created_path = path
        text = path.read_text()
        header = text.split('---', 2)[1]
        meta = {key: json.loads(value) for key, value in
                (line.split(': ', 1) for line in header.strip().splitlines())}
        return meta, text, client

    def test_selected_paper_uses_actual_title_without_another_title_prompt(self):
        meta, text, _ = self.create()
        self.assertTrue(meta['title'].startswith('[논문리뷰]'))
        self.assertEqual(meta['title'].split(']', 1)[1].lstrip(': '), PAPER_TITLE)
        self.assertNotIn('[논문명]', meta['title'])
        self.assertFalse(meta['blog_publish'])
        self.assertEqual(meta['zotero_key'], KEY)
        self.assertIn('[@zotero-ABCD1234]', text)
        self.assertIn('[[Blog/Literature/paper|Zotero 읽기 메모]]', text)

    def test_paper_date_and_venue_do_not_replace_blog_publication_date(self):
        meta, _, _ = self.create()
        self.assertIn('논문 발표: 2024-06-01', meta['subtitle'])
        self.assertIn('학회·게재처: ACL', meta['subtitle'])
        self.assertEqual(meta['date'], '2026-11-06')
        self.assertEqual(meta['date-modified'], '2026-11-06')

    def test_lookup_fields_are_saved_with_the_selected_zotero_item(self):
        self.lookup_fields = {'paper_venue': 'ACL 2024', 'paper_affiliations': ['Example University'],
                              'paper_url': 'https://doi.org/10.1234/test', 'paper_page': 'https://example.org/paper',
                              'paper_github': 'https://github.com/example/paper'}
        meta, _, _ = self.create()
        self.assertEqual({key: meta[key] for key in self.lookup_fields}, self.lookup_fields)
        self.lookup.assert_called_once_with(self.item, self.csl, blog.paper_metadata(self.item, self.csl))

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
        self.lookup.assert_not_called()

    def test_new_review_can_create_a_nested_folder(self):
        meta, _, _ = self.create(category=None, folder=None, answers=['0', 'Knowledge Graphs/RAG'])
        self.assertEqual(meta['categories'][0], 'RAG')
        self.assertEqual(self.created_path.parent, self.vault / 'Blog/Reviews/Knowledge Graphs/RAG')

    def test_existing_folder_choice_reuses_actual_folder_structure(self):
        (self.vault / 'Blog/Reviews/Knowledge Graphs/Memory').mkdir(parents=True)
        meta, _, _ = self.create(category=None, folder=None, answers=['3'])
        self.assertEqual(self.created_path.parent, self.vault / 'Blog/Reviews/Knowledge Graphs/Memory')
        self.assertEqual(meta['categories'][0], 'Memory')

    def test_folder_selection_does_not_depend_on_old_category_document(self):
        previous = '- [ ] RAG\n- [x] [a malformed old menu]\n'
        path = self.vault / 'Blog/블로그 분류.md'
        path.write_text(previous)
        self.create(category=None)
        self.assertEqual(path.read_text(), previous)
        self.assertEqual(self.created_path.parent, self.vault / 'Blog/Reviews')

    def test_duplicate_address_in_another_folder_is_rejected_before_saving(self):
        existing = self.vault / 'Blog/Reviews/Existing Folder/different-filename.md'
        existing.parent.mkdir(parents=True)
        existing.write_text(blog.yaml_header({'title':'Existing review', 'blog_slug':'paper-review', 'blog_publish':False}) + 'Private draft')
        with self.assertRaisesRegex(blog.PublishError, '같은 글 주소'):
            self.create(folder='New Folder')
        self.assertFalse((self.vault / 'Blog/Reviews/New Folder').exists())


if __name__ == '__main__':
    unittest.main()
