import tempfile
import unittest
from pathlib import Path

from tools import reader_pipeline


class ReaderPipelineTests(unittest.TestCase):
    def test_section_map_covers_preface_twelve_chapters_and_afterword(self):
        specs = reader_pipeline.SECTION_SPECS
        self.assertEqual(len(specs), 14)
        self.assertEqual(specs[0].kind, "preface")
        self.assertEqual([item.number for item in specs if item.kind == "chapter"], list(range(1, 13)))
        self.assertEqual(specs[-1].kind, "afterword")
        self.assertEqual(specs[-1].pdf_end, 242)

    def test_clean_section_pages_repairs_drop_cap_and_removes_running_header(self):
        spec = reader_pipeline.SECTION_SPECS[1]
        pages = [
            "ONE\nParalysis\n\npo OFTEN REMEMBER THE PAST with fondness.\n   A new paragraph.\n\n1",
            "2 CHAPTER ONE\n\nContinuation of the paragraph.\n\n2",
        ]
        body = reader_pipeline.clean_section_pages(pages, spec)
        self.assertTrue(body.startswith("People often remember the past with fondness."))
        self.assertNotIn("CHAPTER ONE", body)
        self.assertNotIn("\n1", body)

    def test_normalize_paragraphs_joins_wrapped_and_page_continuation_lines(self):
        source = """People often remember the past with exaggerated fondness. Some-
    times, however, life was better in the old days.
   A genuinely new paragraph starts here.
It continues on the next line.
"""
        self.assertEqual(
            reader_pipeline.normalize_paragraphs(source),
            [
                "People often remember the past with exaggerated fondness. Sometimes, however, life was better in the old days.",
                "A genuinely new paragraph starts here. It continues on the next line.",
            ],
        )

    def test_section_text_uses_one_canonical_string_for_display_and_tts(self):
        spec = reader_pipeline.SECTION_SPECS[1]
        section = reader_pipeline.Section(spec, ("First paragraph.", "Second paragraph."))
        self.assertEqual(
            section.text,
            "Chapter 1. Paralysis.\n\nFirst paragraph.\n\nSecond paragraph.\n",
        )
        ranges = reader_pipeline.paragraph_ranges(section.text)
        self.assertEqual([item[2] for item in ranges], ["Chapter 1. Paralysis.", "First paragraph.", "Second paragraph."])

    def test_write_text_assets_emits_all_section_files_and_book(self):
        sections = [reader_pipeline.Section(spec, ("Body text.",)) for spec in reader_pipeline.SECTION_SPECS]
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            reader_pipeline.write_text_assets(sections, output)
            self.assertEqual(len(list((output / "text").glob("*.txt"))), 14)
            self.assertIn("Afterword to the Paperback Edition.", (output / "book.txt").read_text())


if __name__ == "__main__":
    unittest.main()
