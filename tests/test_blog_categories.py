"""Category configuration fixtures; only temporary Vaults are written."""

from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from blog_categories import (
    CATEGORY_FILE, Category, CategoryError, add_category, ensure_categories,
    read_categories, render_categories, validate_category,
)


CONFIG = 'project:\n  type: website\nwebsite:\n  sidebar:\n    contents:\n      - text: "홈"\n        href: index.qmd\n      # BLOG-CATEGORIES-START\n      old-content\n      # BLOG-CATEGORIES-END\n      - text: "소개"\n        href: about.qmd\n'


class BlogCategoriesTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.vault = Path(self.temporary.name) / "vault"
        self.vault.mkdir()

    def write_document(self, text):
        path = self.vault / CATEGORY_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
        return path

    def test_missing_document_defaults_are_read_without_writing(self):
        self.assertEqual(read_categories(self.vault), [Category("LLM"), Category("RAG"), Category("Agent")])
        self.assertFalse((self.vault / CATEGORY_FILE).exists())

    def test_ensure_creates_once_and_preserves_existing_document(self):
        path = ensure_categories(self.vault)
        self.assertEqual(path, self.vault / CATEGORY_FILE)
        self.assertEqual(read_categories(self.vault), [Category("LLM"), Category("RAG"), Category("Agent")])
        self.assertIn("체크를 해제해도 기존 글은 삭제되지 않습니다", path.read_text())
        self.assertIn("기존 리뷰의 categories", path.read_text())
        original = b"# Private explanation\r\n\r\n- [ ] Custom\r\n"
        path.write_bytes(original)
        self.assertEqual(ensure_categories(self.vault).read_bytes(), original)

    def test_read_preserves_order_check_state_and_ignores_paragraphs(self):
        self.write_document("# 설명\n\n여기에 쓴 개인 설명은 메뉴가 아닙니다.\n\n- [ ] LLM\n- [X] 검색\n- Agent\n")
        self.assertEqual(read_categories(self.vault), [Category("LLM", False), Category("검색"), Category("Agent")])

    def test_code_examples_comments_and_headings_are_not_categories(self):
        self.write_document("# Guide\n```markdown\n- [x] Example\n```\n<!--\n- [x] Hidden\n-->\n~~~\n- Example 2\n~~~\n- [x] Actual\n")
        self.assertEqual(read_categories(self.vault), [Category("Actual")])

    def test_literal_html_comment_inside_code_is_ignored(self):
        self.write_document("```html\n<!--\n- [x] Example\n```\n- [x] Actual\n")
        self.assertEqual(read_categories(self.vault), [Category("Actual")])

    def test_obsidian_private_comment_categories_are_not_published(self):
        with self.assertRaises(CategoryError):
            validate_category('Memory %% comment')
        self.write_document('%%\n- [x] Private\n<!-- ignored\n%%\n- [x] Public\n')
        self.assertEqual(read_categories(self.vault), [Category('Public')])
        self.write_document('%%\n- [x] Private\n')
        with self.assertRaises(CategoryError):
            read_categories(self.vault)

    def test_duplicate_names_use_casefold_and_reject_hidden_duplicates(self):
        for text in ("- [x] LLM\n- [ ] llm\n", "- Straße\n- STRASSE\n"):
            with self.subTest(text=text), self.assertRaises(CategoryError):
                self.write_document(text)
                read_categories(self.vault)

    def test_empty_control_long_and_unsafe_names_raise(self):
        names = ["", "  ", "A" * 81, "LLM\nAgent", "LLM\x00", "LLM\u200b", "file:///Users/me/x", "obsidian://open?vault=private", "zotero://select/library/items/ABCD1234", "C:\\Users\\me\\x", "<img src=x>", "&lt;script&gt;x&lt;/script&gt;", "[Click](https://example.org)", "**LLM**", "`code`", "_emphasis_", "Agent _with_ emphasis", "~~Agent~~", "{{secret}}", "&#10;Agent"]
        for name in names:
            with self.subTest(name=name), self.assertRaises(CategoryError):
                validate_category(name)
        self.assertEqual(validate_category("  한글 & AI/ML (C++)  "), "한글 & AI/ML (C++)")

    def test_empty_bullet_is_an_error(self):
        for text in ("- [x] \n", "- [ ]\n", "- \n", "-\n"):
            with self.subTest(text=text), self.assertRaises(CategoryError):
                self.write_document(text)
                read_categories(self.vault)

    def test_add_appends_checked_name_and_preserves_all_existing_bytes(self):
        original = "# 개인 메모\r\n설명입니다.\r\n\r\n- [ ] LLM\r\n- RAG"
        path = self.write_document(original)
        self.assertEqual(add_category(self.vault, "  검색 & Agent  "), "검색 & Agent")
        self.assertEqual(path.read_bytes(), (original + "\r\n- [x] 검색 & Agent\r\n").encode("utf-8"))
        self.assertEqual(read_categories(self.vault)[-1], Category("검색 & Agent"))

    def test_add_existing_keeps_canonical_name_and_check_state(self):
        path = self.write_document("- [ ] LLM\n- [x] RAG\n")
        before = path.read_bytes()
        self.assertEqual(add_category(self.vault, "llm"), "LLM")
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(read_categories(self.vault)[0], Category("LLM", False))

    def test_add_first_new_name_creates_defaults(self):
        self.assertEqual(add_category(self.vault, "GraphRAG"), "GraphRAG")
        self.assertEqual(read_categories(self.vault), [Category("LLM"), Category("RAG"), Category("Agent"), Category("GraphRAG")])

    def test_invalid_add_does_not_create_a_document(self):
        with self.assertRaises(CategoryError):
            add_category(self.vault, "<script>bad</script>")
        self.assertFalse((self.vault / CATEGORY_FILE).exists())

    def test_symlinked_file_and_directory_outside_vault_are_blocked(self):
        outside = Path(self.temporary.name) / "outside"
        outside.mkdir()
        private = outside / "private.md"
        private.write_text("- [x] Private\n")
        category_parent = self.vault / "Blog"
        category_parent.symlink_to(outside, target_is_directory=True)
        for operation in (ensure_categories, read_categories):
            with self.subTest(operation=operation.__name__), self.assertRaises(CategoryError):
                operation(self.vault)
        with self.assertRaises(CategoryError):
            add_category(self.vault, "New")
        self.assertFalse((outside / "블로그 분류.md").exists())
        category_parent.unlink()
        category_parent.mkdir()
        (self.vault / CATEGORY_FILE).symlink_to(private)
        with self.assertRaises(CategoryError):
            add_category(self.vault, "New")
        self.assertEqual(private.read_text(), "- [x] Private\n")

    def test_internal_symlink_is_permitted(self):
        internal = self.vault / "internal"
        internal.mkdir()
        (self.vault / "Blog").symlink_to(internal, target_is_directory=True)
        ensure_categories(self.vault)
        self.assertTrue((internal / "블로그 분류.md").is_file())

    def test_render_updates_only_marker_region_in_order(self):
        result = render_categories(CONFIG, [Category("숨김", False), Category("검색 & Agent"), Category("LLM")])
        before, after = CONFIG.split("      # BLOG-CATEGORIES-START\n")
        tail = after.split("      # BLOG-CATEGORIES-END", 1)[1]
        self.assertTrue(result.startswith(before + "      # BLOG-CATEGORIES-START\n"))
        self.assertTrue(result.endswith("      # BLOG-CATEGORIES-END" + tail))
        self.assertIn('      - section: "논문 리뷰"\n        contents:\n', result)
        self.assertIn('          - text: "검색 & Agent"\n            href: "reviews.qmd#category=%EA%B2%80%EC%83%89%20%26%20Agent"\n', result)
        self.assertNotIn("숨김", result)
        self.assertLess(result.index('text: "검색 & Agent"'), result.index('text: "LLM"'))
        self.assertNotIn("old-content", result)

    def test_render_with_no_selected_categories_empties_block(self):
        result = render_categories(CONFIG, [Category("LLM", False)])
        self.assertIn("      # BLOG-CATEGORIES-START\n      # BLOG-CATEGORIES-END\n", result)
        self.assertNotIn('section: "논문 리뷰"', result)

    def test_render_preserves_crlf_and_quotes(self):
        result = render_categories(CONFIG.replace("\n", "\r\n"), [Category('AI "Agent"')])
        self.assertIn('          - text: "AI \\"Agent\\""\r\n', result)
        self.assertIn('category=AI%20%22Agent%22', result)
        self.assertNotIn("\n", result.replace("\r\n", ""))

    def test_render_missing_duplicate_or_reversed_markers_are_errors(self):
        for text in ("no markers", CONFIG.replace("# BLOG-CATEGORIES-END", "# MISSING"), CONFIG + "      # BLOG-CATEGORIES-START\n", CONFIG.replace("START", "TEMP").replace("END", "START").replace("TEMP", "END")):
            with self.subTest(text=text), self.assertRaises(CategoryError):
                render_categories(text, [Category("LLM")])

    def test_render_revalidates_programmatic_inputs(self):
        for categories in ([Category("LLM"), Category("llm", False)], [Category("<script>x</script>")], [Category("LLM", "yes")]):
            with self.subTest(categories=categories), self.assertRaises(CategoryError):
                render_categories(CONFIG, categories)


if __name__ == "__main__":
    unittest.main()
