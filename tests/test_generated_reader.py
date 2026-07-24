import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
READER = ROOT / "aligned_reader"


class GeneratedReaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((READER / "manifest.json").read_text(encoding="utf-8"))

    def test_manifest_has_complete_book_structure(self):
        sections = self.manifest["sections"]
        self.assertEqual(len(sections), 14)
        self.assertEqual(sections[0]["kind"], "preface")
        self.assertEqual([item["number"] for item in sections[1:13]], list(range(1, 13)))
        self.assertEqual(sections[-1]["kind"], "afterword")
        self.assertEqual(self.manifest["voice"], "en-GB-RyanNeural")

    def test_every_audio_and_timing_asset_exists(self):
        for section in self.manifest["sections"]:
            audio = READER / section["audio"]
            timing = READER / "audio" / f"{section['slug']}.words.json"
            self.assertGreater(audio.stat().st_size, 100_000, audio)
            self.assertGreater(timing.stat().st_size, 100_000, timing)

    def test_word_offsets_are_monotonic_and_match_paragraph_text(self):
        total_words = 0
        for section in self.manifest["sections"]:
            last_start = -1.0
            for paragraph in section["paragraphs"]:
                text = paragraph["text"]
                for word in paragraph["words"]:
                    self.assertGreaterEqual(word["start"], last_start)
                    self.assertGreaterEqual(word["end"], word["start"])
                    self.assertEqual(text[word["startChar"] : word["endChar"]].casefold(), word["text"].casefold())
                    last_start = word["start"]
                    total_words += 1
            self.assertLessEqual(last_start, section["duration"] + 1)
        self.assertGreater(total_words, 79_000)

    def test_section_and_book_durations_are_contiguous(self):
        offset = 0.0
        for section in self.manifest["sections"]:
            self.assertAlmostEqual(section["start"], offset, places=2)
            self.assertAlmostEqual(section["end"], section["start"] + section["duration"], places=2)
            offset = section["end"]
        self.assertAlmostEqual(self.manifest["duration"], offset, places=2)


if __name__ == "__main__":
    unittest.main()
