"""Folder-tree fixtures; all filesystem checks use temporary directories."""

import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from obsidian_tree import FolderError, TreeEntry, list_review_folders, render_tree, resolve_review_folder


CONFIG = 'project:\n  type: website\nwebsite:\n  sidebar:\n    contents:\n      - text: "홈"\n        href: index.qmd\n      # BLOG-TREE-START\n      old-content\n      # BLOG-TREE-END\n      - text: "소개"\n        href: about.qmd\n'


class ObsidianTreeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "Reviews"
        self.root.mkdir()

    def test_tree_merges_common_parents_and_preserves_relative_folders(self):
        entries = [TreeEntry(("RAG", "Basics"), "Two", "/posts/two/"), TreeEntry(("RAG", "Basics"), "One", "/posts/one/"), TreeEntry(("RAG",), "Overview", "/posts/overview/"), TreeEntry((), "Root note", "/posts/root/")]
        result = render_tree(CONFIG, entries)
        self.assertEqual(result.count('section: "RAG"'), 1)
        self.assertEqual(result.count('section: "Basics"'), 1)
        self.assertIn('      - section: "RAG"\n        contents:\n          - section: "Basics"\n            contents:\n              - text: "One"\n                href: "/posts/one/"', result)
        self.assertIn('          - text: "Overview"\n            href: "/posts/overview/"', result)
        self.assertIn('      - text: "Root note"\n        href: "/posts/root/"', result)
        self.assertNotIn("논문 리뷰", result)

    def test_folders_precede_documents_and_names_are_sorted(self):
        entries = [TreeEntry((), "AA", "/posts/aa/"), TreeEntry(("Zebra",), "Z", "/posts/z/"), TreeEntry(("agent",), "B", "/posts/b/"), TreeEntry(("agent",), "a", "/posts/a/")]
        result = render_tree(CONFIG, entries)
        self.assertLess(result.index('section: "agent"'), result.index('section: "Zebra"'))
        self.assertLess(result.index('section: "Zebra"'), result.index('text: "AA"'))
        self.assertLess(result.index('text: "a"'), result.index('text: "B"'))

    def test_same_basename_in_different_folders_is_retained(self):
        entries = [TreeEntry(("A",), "Review", "/posts/a-review/"), TreeEntry(("B",), "Review", "/posts/b-review/")]
        result = render_tree(CONFIG, entries)
        self.assertEqual(result.count('text: "Review"'), 2)
        self.assertIn('href: "/posts/a-review/"', result)
        self.assertIn('href: "/posts/b-review/"', result)

    def test_actual_symbols_are_escaped_instead_of_rejected(self):
        entry = TreeEntry(('RAG [심화] & <Agent>',), '논문: _A_ **B** @paper $x$ `code`', '/posts/literal/')
        result = render_tree(CONFIG, [entry])
        section = next(line.split('section: ', 1)[1] for line in result.splitlines() if 'section:' in line)
        text = next(line.split('text: ', 1)[1] for line in result.splitlines() if '논문' in line)
        self.assertEqual(json.loads(section), r'RAG \[심화\] &amp; &lt;Agent&gt;')
        self.assertEqual(json.loads(text), r'논문\: \_A\_ \*\*B\*\* \@paper \$x\$ \`code\`')
        self.assertNotIn('<Agent>', result)

    def test_only_the_marker_region_changes_and_crlf_is_preserved(self):
        source = CONFIG.replace('\n', '\r\n')
        result = render_tree(source, [TreeEntry((), 'A', '/posts/a/')])
        before, after = source.split('      # BLOG-TREE-START\r\n')
        tail = after.split('      # BLOG-TREE-END', 1)[1]
        self.assertTrue(result.startswith(before + '      # BLOG-TREE-START\r\n'))
        self.assertTrue(result.endswith('      # BLOG-TREE-END' + tail))
        self.assertNotIn('\n', result.replace('\r\n', ''))
        self.assertNotIn('old-content', result)

    def test_empty_entries_leave_no_generated_section(self):
        result = render_tree(CONFIG, [])
        self.assertIn('      # BLOG-TREE-START\n      # BLOG-TREE-END', result)

    def test_invalid_names_and_urls_raise(self):
        invalid = [TreeEntry(('A/B',), 'X', '/posts/x/'), TreeEntry(('..',), 'X', '/posts/x/'), TreeEntry(('A\nB',), 'X', '/posts/x/'), TreeEntry((), 'X\x00Y', '/posts/x/'), TreeEntry((), '..', '/posts/x/'), TreeEntry((), 'X', 'https://example.org/posts/x/'), TreeEntry((), 'X', '/posts/UPPER/'), TreeEntry((), 'X', '/posts/x/?private=1'), TreeEntry((), 'X', '/posts/../'), TreeEntry((), 'X', '/posts/x_1/')]
        for entry in invalid:
            with self.subTest(entry=entry), self.assertRaises(FolderError):
                render_tree(CONFIG, [entry])

    def test_invalid_markers_raise(self):
        for source in ('missing', CONFIG.replace('BLOG-TREE-END', 'OTHER'), CONFIG + '      # BLOG-TREE-START\n', CONFIG.replace('START', 'TEMP').replace('END', 'START').replace('TEMP', 'END')):
            with self.subTest(source=source), self.assertRaises(FolderError):
                render_tree(source, [])

    def test_folder_listing_uses_posix_paths_without_hidden_or_symlink_dirs(self):
        for name in ('RAG/Basics', 'RAG/Advanced', 'Agent', '.private/Secrets', 'Visible/.hidden', 'Visible/Public'):
            (self.root / name).mkdir(parents=True)
        (self.root / 'RAG' / 'ignored.md').write_text('not read')
        outside = Path(self.temporary.name) / 'outside'
        outside.mkdir()
        (self.root / 'External').symlink_to(outside, target_is_directory=True)
        (self.root / 'Alias').symlink_to(self.root / 'RAG', target_is_directory=True)
        self.assertEqual(list_review_folders(self.root), ['.', 'Agent', 'RAG', 'RAG/Advanced', 'RAG/Basics', 'Visible', 'Visible/Public'])

    def test_resolve_root_and_missing_nested_path_does_not_create_directories(self):
        self.assertEqual(resolve_review_folder(self.root, ''), self.root)
        self.assertEqual(resolve_review_folder(self.root, '.'), self.root)
        target = resolve_review_folder(self.root, 'New [주제]/세부 폴더')
        self.assertEqual(target, self.root / 'New [주제]' / '세부 폴더')
        self.assertFalse(target.exists())

    def test_missing_root_is_a_root_choice_without_creating_it(self):
        root = self.root / 'Missing'
        self.assertEqual(list_review_folders(root), ['.'])
        self.assertFalse(root.exists())

    def test_resolve_rejects_absolute_parent_hidden_and_control_paths(self):
        for relative in ('/private/tmp', 'C:\\Users\\me', '\\\\server\\share', '../Outside', 'RAG/../Other', '.private', 'RAG/.hidden', 'A\nB', 'A\x00B'):
            with self.subTest(relative=relative), self.assertRaises(FolderError):
                resolve_review_folder(self.root, relative)

    def test_resolve_blocks_symlinks_outside_root_and_to_hidden_targets(self):
        outside = Path(self.temporary.name) / 'outside'
        outside.mkdir()
        (self.root / 'External').symlink_to(outside, target_is_directory=True)
        (self.root / '.hidden').mkdir()
        (self.root / 'HiddenAlias').symlink_to(self.root / '.hidden', target_is_directory=True)
        for relative in ('External', 'External/New', 'HiddenAlias'):
            with self.subTest(relative=relative), self.assertRaises(FolderError):
                resolve_review_folder(self.root, relative)

    def test_resolve_rejects_a_file_in_the_target_path(self):
        (self.root / 'paper.md').write_text('not read')
        with self.assertRaises(FolderError):
            resolve_review_folder(self.root, 'paper.md/new')


if __name__ == '__main__':
    unittest.main()
