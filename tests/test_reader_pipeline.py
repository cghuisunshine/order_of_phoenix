import json
import tempfile
import textwrap
import unittest
from pathlib import Path

from tools import reader_pipeline


class ReaderPipelineTests(unittest.TestCase):
    def test_extract_chapters_skips_contents_and_splits_real_chapters(self):
        source = """
        Contents
        ONE
        Dudley Demented . 1
        TWO
        A Peck of Owls . 20

        Harry Potter
        And the Order OF Phoenix

        CHAPTER ONE

        DUDLEY DEMENTED

        First paragraph of chapter one.

        CHAPTER ONE

        Repeated page header should stay inside the first chapter body.

        Second paragraph.

        CHAPTER TWO

        A PECK OF OWLS

        Another chapter starts here.
        """

        chapters = reader_pipeline.extract_chapters(source)

        self.assertEqual([chapter.number for chapter in chapters], [1, 2])
        self.assertEqual(chapters[0].title, "Dudley Demented")
        self.assertEqual(chapters[1].title, "A Peck of Owls")
        self.assertIn("First paragraph", chapters[0].body)
        self.assertNotIn("Contents", chapters[0].body)

    def test_normalize_paragraphs_repairs_wrapped_lines_and_drops_page_artifacts(self):
        body = """
        T      he hottest day of the summer so far was drawing to a close and
               a drowsy silence lay over the large, square houses of Privet
        Drive.
                                     \x91   1   \x91

            On the whole, Harry thought he was to be congratulated on his
        idea of hiding here.
        """

        paragraphs = reader_pipeline.normalize_paragraphs(body)

        self.assertEqual(len(paragraphs), 2)
        self.assertEqual(
            paragraphs[0],
            "The hottest day of the summer so far was drawing to a close and a drowsy silence lay over the large, square houses of Privet Drive.",
        )
        self.assertEqual(
            paragraphs[1],
            "On the whole, Harry thought he was to be congratulated on his idea of hiding here.",
        )

    def test_normalize_paragraphs_uses_indents_and_drops_running_headers(self):
        body = textwrap.dedent("""
        First paragraph continues
        across this wrapped line.
            Second paragraph starts by indentation.
        DUDLEY DEMENTED
        More text in the second paragraph.
        """)

        paragraphs = reader_pipeline.normalize_paragraphs(body, running_headers={"DUDLEY DEMENTED"})

        self.assertEqual(
            paragraphs,
            [
                "First paragraph continues across this wrapped line.",
                "Second paragraph starts by indentation. More text in the second paragraph.",
            ],
        )

    def test_extract_chapter_without_visible_title_keeps_body(self):
        source = """
        CHAPTER THREE

        But Hedwig didn't return next morning. Harry spent the day in his
        bedroom.
        """

        chapters = reader_pipeline.extract_chapters(source)

        self.assertEqual(chapters[0].number, 3)
        self.assertEqual(chapters[0].title, "The Advance Guard")
        self.assertTrue(chapters[0].body.startswith("But Hedwig"))

    def test_build_reader_manifest_offsets_chapter_fragments_and_appends_outro(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            align_dir = root / "alignments"
            align_dir.mkdir()
            (align_dir / "chapter_001.json").write_text(
                json.dumps(
                    {
                        "fragments": [
                            {"id": "f000001", "begin": "0.000", "end": "1.500", "lines": ["First"]},
                            {"id": "f000002", "begin": "1.500", "end": "3.000", "lines": ["Second"]},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (align_dir / "chapter_002.json").write_text(
                json.dumps(
                    {
                        "fragments": [
                            {"id": "f000001", "begin": "0.000", "end": "2.000", "lines": ["Third"]},
                        ]
                    }
                ),
                encoding="utf-8",
            )

            chapters = [
                reader_pipeline.Chapter(1, "One", "First\n\nSecond"),
                reader_pipeline.Chapter(2, "Two", "Third"),
            ]
            audio_files = [Path("Part 001.mp3"), Path("Part 002.mp3")]

            manifest = reader_pipeline.build_reader_manifest(
                chapters=chapters,
                audio_files=audio_files,
                alignment_dir=align_dir,
                durations=[3.0, 2.0],
                outro_audio=Path("Part 039.mp3"),
                outro_duration=100.0,
            )

        self.assertEqual(len(manifest["chapters"]), 3)
        self.assertEqual(manifest["chapters"][1]["start"], 3.0)
        self.assertEqual(manifest["chapters"][1]["paragraphs"][0]["begin"], 3.0)
        self.assertEqual(manifest["chapters"][2]["kind"], "outro")
        self.assertEqual(manifest["duration"], 105.0)


if __name__ == "__main__":
    unittest.main()
