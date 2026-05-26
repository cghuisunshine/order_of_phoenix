import unittest
from pathlib import Path


READER_HTML = Path(__file__).resolve().parents[1] / "aligned_reader" / "index.html"


class AlignedReaderHtmlTests(unittest.TestCase):
    def test_reader_saves_progress_to_local_storage(self):
        html = READER_HTML.read_text(encoding="utf-8")

        self.assertIn("const progressStorageKey =", html)
        self.assertIn("function saveProgress(", html)
        self.assertIn("localStorage.setItem(progressStorageKey", html)

    def test_reader_restores_saved_progress_on_startup(self):
        html = READER_HTML.read_text(encoding="utf-8")

        self.assertIn("function loadSavedProgress()", html)
        self.assertIn("function loadInitialChapter()", html)
        self.assertIn("loadInitialChapter();", html)

    def test_reader_uses_saved_time_before_audio_metadata_loads(self):
        html = READER_HTML.read_text(encoding="utf-8")

        self.assertIn("function updateTimes(localOverride = null)", html)
        self.assertIn("function resolveLocalTime(localOverride = null)", html)
        self.assertIn("if (pendingStartTime !== null) {", html)
        self.assertIn("pendingStartTime = null;", html)
        self.assertIn("Math.abs(local - pendingStartTime) >= 0.25", html)
        self.assertIn("const local = resolveLocalTime(localOverride);", html)
        self.assertIn("updateTimes(localStart);", html)

    def test_reader_renders_and_highlights_sentence_spans(self):
        html = READER_HTML.read_text(encoding="utf-8")

        self.assertIn("function sentenceItems(paragraph)", html)
        self.assertIn("sentenceNode.className = 'sentence';", html)
        self.assertIn("const unit = findPlaybackUnitAt(chapter, local);", html)
        self.assertIn("audio.currentTime = sentence.localBegin;", html)
        self.assertIn("saveProgress(sentence.id, sentence.localBegin);", html)

    def test_reader_keeps_paragraph_fallback_for_old_manifests(self):
        html = READER_HTML.read_text(encoding="utf-8")

        self.assertIn("return paragraph.sentences && paragraph.sentences.length ? paragraph.sentences : [paragraph];", html)
        self.assertIn("function findParagraphByPlaybackId(chapter, playbackId)", html)


if __name__ == "__main__":
    unittest.main()
