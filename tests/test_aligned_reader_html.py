import unittest
from pathlib import Path


READER_HTML = Path(__file__).resolve().parents[1] / "aligned_reader" / "index.html"


class AlignedReaderHtmlTests(unittest.TestCase):
    def test_reader_identifies_the_new_book_and_uk_voice(self):
        html = READER_HTML.read_text(encoding="utf-8")
        self.assertIn("The Darwin Economy", html)
        self.assertIn("Robert H. Frank", html)
        self.assertIn("en-GB-RyanNeural", html)
        self.assertNotIn("Harry Potter", html)

    def test_reader_renders_word_boundaries_and_animation_frame_highlighting(self):
        html = READER_HTML.read_text(encoding="utf-8")
        self.assertIn("function renderTimedText(node,paragraph)", html)
        self.assertIn("span.className='tts-word'", html)
        self.assertIn("requestAnimationFrame(paintLoop)", html)
        self.assertIn("classList.add('is-speaking')", html)

    def test_paragraph_indicator_changes_only_on_paragraph_transition(self):
        html = READER_HTML.read_text(encoding="utf-8")

        self.assertIn("let activeParagraph=null;", html)
        self.assertIn("if(active.paragraph!==activeParagraph)", html)
        self.assertIn("activeParagraph?.classList.remove('is-speaking');", html)
        self.assertIn("activeParagraph=active.paragraph;", html)
        self.assertNotIn("previous?.paragraph.classList.remove('is-speaking')", html)

    def test_reader_supports_progress_search_and_click_to_seek(self):
        html = READER_HTML.read_text(encoding="utf-8")
        self.assertIn("localStorage.setItem(progressStorageKey", html)
        self.assertIn("function loadSavedProgress()", html)
        self.assertIn("function searchText(query)", html)
        self.assertIn("function promptSearch()", html)
        self.assertIn("seekAndPlay(word.start)", html)


if __name__ == "__main__":
    unittest.main()
