"""Publishing behavior, private content exclusion, and withdrawal checks."""

from pathlib import Path
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import blog
from publishing import ObsidianPublisher, Pandoc, PublishError, strip_private_comments, yaml_header

QUARTO = os.environ.get("QUARTO_BIN") or shutil.which("quarto")


class ReferenceFixture:
    def __init__(self):
        self.requested = []

    def export_references(self, keys):
        self.requested.extend(keys)
        return [{"id": f"zotero-{key}", "type": "article-journal", "title": "Fixture paper"} for key in keys]


@unittest.skipUnless(QUARTO, "Quarto is needed for Markdown integration checks")
class PublishingChecks(unittest.TestCase):
    def setUp(self):
        (ROOT / "work").mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="publishing-check-", dir=ROOT / "work")
        self.folder = Path(self.temporary.name)
        self.repo = self.folder / "repo"
        self.vault = self.folder / "vault"
        self.reviews = self.vault / "Blog/Reviews"
        self.reviews.mkdir(parents=True)
        (self.repo / "posts").mkdir(parents=True)
        (self.vault / "Blog/.blog-vault-id").write_text("a" * 32)
        self.client = ReferenceFixture()
        self.config = {"vault": str(self.vault), "reviews": "Blog/Reviews"}
        self.pandoc = Pandoc(QUARTO)

    def tearDown(self):
        self.temporary.cleanup()

    def pub(self):
        return ObsidianPublisher(self.repo, self.config, self.pandoc, self.client)

    def note(self, name="review", body="본문입니다.", ready=True, **extra):
        meta = {"title": "검증용 리뷰", "date": "2026-11-05", "categories": ["RAG"],
                "blog_publish": ready, "blog_slug": name, **extra}
        path = self.reviews / f"{name}.md"
        path.write_text(yaml_header(meta) + body)
        return path

    def test_only_explicit_boolean_opt_in_is_exported(self):
        self.note("public", ready=True)
        self.note("draft", ready=False, body="DO_NOT_COPY_DRAFT")
        self.note("quoted", ready="true", body="DO_NOT_COPY_QUOTED_FLAG")
        plan = self.pub().sync()
        self.assertEqual(plan["updated"], ["public"])
        self.assertFalse((self.repo / "posts/draft").exists())
        self.assertFalse((self.repo / "posts/quoted").exists())

    def test_private_comments_metadata_and_unrelated_notes_are_excluded(self):
        self.note(body="공개 내용\n\n%% PRIVATE_PERCENT %%\n\n<!-- PRIVATE_HTML -->\n\n공개 끝.",
                  private_note="PRIVATE_FRONTMATTER")
        (self.vault / "unrelated.md").write_text("PRIVATE_UNRELATED")
        self.pub().sync()
        copied = (self.repo / "posts/review/index.md").read_text()
        for secret in ("PRIVATE_PERCENT", "PRIVATE_HTML", "PRIVATE_FRONTMATTER", "PRIVATE_UNRELATED"):
            self.assertNotIn(secret, copied)
        self.assertIn("공개 내용", copied)
        self.assertNotIn("blog_publish", copied)

    def test_comment_markers_in_code_are_preserved(self):
        body = "`%% example %%`\n\n```python\ns = '%% in code %%'\n```\n\n%% private %%"
        cleaned = strip_private_comments(body)
        self.assertIn("%% example %%", cleaned)
        self.assertIn("%% in code %%", cleaned)
        self.assertNotIn("private", cleaned)

    def test_relative_and_wiki_images_copy_only_referenced_files(self):
        assets = self.vault / "Blog/Assets"
        assets.mkdir()
        image = b"image fixture bytes"
        (assets / "figure.png").write_bytes(image)
        (assets / "private-other.png").write_bytes(b"DO_NOT_COPY")
        self.note(body="![그림](../Assets/figure.png)\n\n![[figure.png|다른 설명]]")
        self.pub().sync()
        output = self.repo / "posts/review"
        files = list((output / "assets").iterdir())
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].read_bytes(), image)
        text = (output / "index.md").read_text()
        self.assertNotIn("[[", text)
        self.assertNotIn("private-other", text)

    def test_symlink_image_cannot_escape_vault(self):
        outside = self.folder / "outside.png"
        outside.write_bytes(b"PRIVATE_OUTSIDE")
        (self.reviews / "leak.png").symlink_to(outside)
        self.note(body="![[leak.png]]")
        with self.assertRaises(PublishError):
            self.pub().sync()
        self.assertFalse((self.repo / "posts/review").exists())

    def test_private_note_link_stops_export_without_copying_note(self):
        (self.vault / "private.md").write_text("PRIVATE_NOTE")
        self.note(body="[[private|개인 노트]]")
        with self.assertRaises(PublishError):
            self.pub().sync()
        self.assertFalse((self.repo / "posts/review").exists())

    def test_public_cross_note_heading_becomes_website_anchor(self):
        self.note("one", body="[[two#A Result|다른 글의 결과]]")
        self.note("two", body="## A Result\n\n설명입니다.")
        self.pub().sync()
        text = (self.repo / "posts/one/index.md").read_text()
        self.assertIn("/posts/two/#a-result", text)

    def test_only_cited_zotero_items_are_requested(self):
        self.note(body="논문 [@zotero-ABCD1234]와 다시 인용 [@zotero-ABCD1234].")
        self.pub().sync()
        self.assertEqual(self.client.requested, ["ABCD1234"])
        refs = json.loads((self.repo / "posts/review/references.json").read_text())
        self.assertEqual([r["id"] for r in refs], ["zotero-ABCD1234"])

    def test_withdrawal_preserves_unmanaged_content(self):
        path = self.note()
        self.pub().sync()
        legacy = self.repo / "posts/legacy"
        legacy.mkdir()
        (legacy / "index.qmd").write_text("기존 글")
        path.write_text(path.read_text().replace("blog_publish: true", "blog_publish: false"))
        plan = self.pub().sync()
        self.assertEqual(plan["removed"], ["review"])
        self.assertFalse((self.repo / "posts/review").exists())
        self.assertEqual((legacy / "index.qmd").read_text(), "기존 글")

    def test_export_failure_leaves_previous_export_unchanged(self):
        self.note("one", body="이전 공개 내용")
        self.pub().sync()
        before = (self.repo / "posts/one/index.md").read_bytes()
        self.note("one", body="수정한 내용")
        self.note("two", body="![[missing-image.png]]")
        with self.assertRaises(PublishError):
            self.pub().sync()
        self.assertEqual((self.repo / "posts/one/index.md").read_bytes(), before)

    def test_direct_edits_to_generated_copy_are_preserved(self):
        self.note()
        self.pub().sync()
        copy = self.repo / "posts/review/index.md"
        copy.write_text("직접 수정한 내용")
        with self.assertRaises(PublishError):
            self.pub().sync()
        self.assertEqual(copy.read_text(), "직접 수정한 내용")

    def test_draft_preview_does_not_create_public_copy(self):
        note = self.note(ready=False, body="[핵심 질문]\n\n%% PRIVATE_PREVIEW_NOTE %%")
        pub = self.pub()
        preview = pub.preview_project(pub.review(note, allow_draft=True), [])
        self.assertTrue((preview / "posts/review/index.md").is_file())
        self.assertFalse((self.repo / "posts/review").exists())
        self.assertNotIn("PRIVATE_PREVIEW_NOTE", (preview / "posts/review/index.md").read_text())

    def test_unregistered_source_files_are_not_staged_or_built(self):
        (self.repo / "scripts").mkdir()
        (self.repo / "assets").mkdir()
        (self.repo / "scripts/private-data.txt").write_text("PRIVATE_SCRIPT_DATA")
        (self.repo / "assets/private-data.txt").write_text("PRIVATE_ASSET_DATA")
        (self.repo / "assets/favicon.svg").write_text("public favicon")
        replies = [b"assets/favicon.svg\0scripts/blog.py\0",
                   b"scripts/private-data.txt\0assets/private-data.txt\0scripts/zotero_client.py\0",
                   b"assets/favicon.svg\0scripts/blog.py\0"]
        with patch.object(blog, "ROOT", self.repo), patch.object(blog.subprocess, "check_output", side_effect=replies):
            allowed = blog.publishable_paths(self.pub())
        self.assertNotIn("scripts/private-data.txt", allowed)
        self.assertNotIn("assets/private-data.txt", allowed)
        self.assertIn("scripts/zotero_client.py", allowed)
        target = self.pub().website_project(self.folder / "website-input", allowed)
        self.assertTrue((target / "assets/favicon.svg").exists())
        self.assertFalse((target / "assets/private-data.txt").exists())
        self.assertFalse((target / "scripts").exists())

    def test_first_time_staged_review_survives_publish_retry(self):
        self.note()
        self.pub().sync()
        generated = [p.relative_to(self.repo).as_posix() for p in (self.repo / "posts/review").rglob("*") if p.is_file()]
        indexed = generated + ["scripts/publishing.py", "assets/private-data.txt"]
        replies = [b"scripts/blog.py\0", b"", ("\0".join(indexed) + "\0").encode()]
        with patch.object(blog, "ROOT", self.repo), patch.object(blog.subprocess, "check_output", side_effect=replies):
            allowed = blog.publishable_paths(self.pub())
        self.assertTrue(set(generated).issubset(allowed))
        self.assertIn("scripts/publishing.py", allowed)
        self.assertNotIn("assets/private-data.txt", allowed)
        target = self.pub().website_project(self.folder / "website-retry", allowed)
        self.assertTrue((target / "posts/review/index.md").is_file())

    def tree_config(self):
        config = ('website:\n  sidebar:\n    contents:\n'
                  '      - text: 전체 글\n        href: reviews.qmd\n'
                  '      # BLOG-TREE-START\n      # BLOG-TREE-END\n')
        (self.repo / '_quarto.yml').write_text(config)
        return config

    def test_tree_mirrors_nested_public_folders_and_excludes_private_folders(self):
        original = self.tree_config()
        note = self.note('one', title='Metadata article title')
        target = self.reviews / 'Knowledge Graphs/RAG/Visible Note.md'
        target.parent.mkdir(parents=True)
        note.rename(target)
        draft = self.note('draft', ready=False)
        hidden_folder = self.reviews / 'PRIVATE_UNPUBLISHED_FOLDER'
        hidden_folder.mkdir()
        draft.rename(hidden_folder / draft.name)
        self.pub().sync()
        project = self.pub().website_project(self.folder / 'tree-site', ['_quarto.yml', 'posts/one/index.md'])
        rendered = (project / '_quarto.yml').read_text()
        for name in ('Knowledge Graphs', 'RAG', 'Visible Note'):
            self.assertIn(name, rendered)
        for private in ('PRIVATE_UNPUBLISHED_FOLDER', str(self.vault), 'Blog/Reviews', 'Metadata article title'):
            self.assertNotIn(private, rendered)
        self.assertEqual((self.repo / '_quarto.yml').read_text(), original)

    def test_moving_note_updates_tree_without_changing_post_url(self):
        self.tree_config()
        note = self.note('one')
        self.pub().sync()
        target = self.reviews / 'New Folder/New Name.md'
        target.parent.mkdir()
        note.rename(target)
        self.pub().sync()
        marker = json.loads((self.repo / 'posts/one/_obsidian-import.json').read_text())
        self.assertEqual(marker['navigation'], {'folders': ['New Folder'], 'label': 'New Name'})
        project = self.pub().website_project(self.folder / 'moved-tree', ['_quarto.yml', 'posts/one/index.md'])
        rendered = (project / '_quarto.yml').read_text()
        self.assertIn('New Folder', rendered)
        self.assertIn('New Name', rendered)
        self.assertIn('/posts/one/', rendered)

    def test_withdrawn_review_removes_its_empty_navigation_folder(self):
        self.tree_config()
        note = self.note('one')
        target = self.reviews / 'Folder/one.md'
        target.parent.mkdir()
        note.rename(target)
        self.pub().sync()
        target.write_text(target.read_text().replace('blog_publish: true', 'blog_publish: false'))
        self.pub().sync()
        project = self.pub().website_project(self.folder / 'withdrawn-tree', ['_quarto.yml'])
        self.assertNotIn('Folder', (project / '_quarto.yml').read_text())
        self.assertFalse((self.repo / 'posts/one').exists())

    def test_selected_draft_tree_is_built_after_private_preview_export(self):
        self.tree_config()
        note = self.note('draft', ready=False)
        target = self.reviews / 'Private Preview/Draft Name.md'
        target.parent.mkdir()
        note.rename(target)
        pub = self.pub()
        project = pub.preview_project(pub.review(target, allow_draft=True), ['_quarto.yml'])
        rendered = (project / '_quarto.yml').read_text()
        self.assertIn('Private Preview', rendered)
        self.assertIn('Draft Name', rendered)
        self.assertFalse((self.repo / 'posts/draft').exists())

    def test_hidden_review_folders_are_not_exported(self):
        note = self.note('hidden')
        target = self.reviews / '.private/hidden.md'
        target.parent.mkdir()
        note.rename(target)
        self.pub().sync()
        self.assertFalse((self.repo / 'posts/hidden').exists())

    def test_unconfigured_private_notes_do_not_block_review_selection(self):
        note = self.note('one', ready=False)
        (self.reviews / 'Private scratch note.md').write_text('개인 메모입니다.')
        self.assertEqual([review.path for review in self.pub().candidates(ready_only=False)], [note])


if __name__ == "__main__":
    unittest.main()
