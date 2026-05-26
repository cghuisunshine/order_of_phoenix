from __future__ import annotations

import argparse
import html
import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


BOOK_PDF = Path("Harry Potter and the Order of the Phoenix - J.K. Rowling.pdf")
AUDIO_DIR = Path("J. K. Rowling - Harry Potter and the Order of the Phoenix")
OUTPUT_DIR = Path("aligned_reader")

CHAPTER_WORDS = [
    "ONE",
    "TWO",
    "THREE",
    "FOUR",
    "FIVE",
    "SIX",
    "SEVEN",
    "EIGHT",
    "NINE",
    "TEN",
    "ELEVEN",
    "TWELVE",
    "THIRTEEN",
    "FOURTEEN",
    "FIFTEEN",
    "SIXTEEN",
    "SEVENTEEN",
    "EIGHTEEN",
    "NINETEEN",
    "TWENTY",
    "TWENTY-ONE",
    "TWENTY-TWO",
    "TWENTY-THREE",
    "TWENTY-FOUR",
    "TWENTY-FIVE",
    "TWENTY-SIX",
    "TWENTY-SEVEN",
    "TWENTY-EIGHT",
    "TWENTY-NINE",
    "THIRTY",
    "THIRTY-ONE",
    "THIRTY-TWO",
    "THIRTY-THREE",
    "THIRTY-FOUR",
    "THIRTY-FIVE",
    "THIRTY-SIX",
    "THIRTY-SEVEN",
    "THIRTY-EIGHT",
]
WORD_TO_NUMBER = {word: index for index, word in enumerate(CHAPTER_WORDS, start=1)}
CHAPTER_TITLES = {
    1: "Dudley Demented",
    2: "A Peck of Owls",
    3: "The Advance Guard",
    4: "Number Twelve, Grimmauld Place",
    5: "The Order of the Phoenix",
    6: "The Noble and Most Ancient House of Black",
    7: "The Ministry of Magic",
    8: "The Hearing",
    9: "The Woes of Mrs. Weasley",
    10: "Luna Lovegood",
    11: "The Sorting Hat's New Song",
    12: "Professor Umbridge",
    13: "Detention with Dolores",
    14: "Percy and Padfoot",
    15: "The Hogwarts High Inquisitor",
    16: "In the Hog's Head",
    17: "Educational Decree Number Twenty-Four",
    18: "Dumbledore's Army",
    19: "The Lion and the Serpent",
    20: "Hagrid's Tale",
    21: "The Eye of the Snake",
    22: "St. Mungo's Hospital for Magical Maladies and Injuries",
    23: "Christmas on the Closed Ward",
    24: "Occlumency",
    25: "The Beetle at Bay",
    26: "Seen and Unforeseen",
    27: "The Centaur and the Sneak",
    28: "Snape's Worst Memory",
    29: "Career Advice",
    30: "Grawp",
    31: "O.W.L.s",
    32: "Out of the Fire",
    33: "Fight and Flight",
    34: "The Department of Mysteries",
    35: "Beyond the Veil",
    36: "The Only One He Ever Feared",
    37: "The Lost Prophecy",
    38: "The Second War Begins",
}


@dataclass(frozen=True)
class Chapter:
    number: int
    title: str
    body: str


SENTENCE_ABBREVIATIONS = {
    "Mr.",
    "Mrs.",
    "Ms.",
    "Dr.",
    "Prof.",
    "St.",
    "Jr.",
    "Sr.",
    "No.",
}
SPEECH_VERBS = {
    "asked",
    "barked",
    "breathed",
    "called",
    "cried",
    "gasped",
    "growled",
    "muttered",
    "replied",
    "said",
    "shouted",
    "snapped",
    "whispered",
    "yelled",
}


def clean_text(text: str) -> str:
    return (
        text.replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\x0c", "\n\n")
        .replace("\u2019", "'")
        .replace("\u2018", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2014", " - ")
        .replace("\u2013", "-")
        .replace("\x91", "")
        .replace("\x92", "")
        .replace("", "")
        .replace("", "")
    )


def normalize_chapter_word(raw: str) -> str:
    return re.sub(r"\s+", "-", raw.strip().replace("—", "-").replace("–", "-")).upper()


def display_chapter_word(number: int) -> str:
    return CHAPTER_WORDS[number - 1].replace("-", " ").title()


def title_case_heading(raw: str) -> str:
    words = " ".join(raw.split()).title().split()
    small_words = {"A", "An", "And", "At", "By", "For", "In", "Of", "On", "The", "To"}
    title = " ".join(
        word.lower() if index > 0 and word in small_words else word for index, word in enumerate(words)
    )
    title = title.replace("'S", "'s")
    title = title.replace("O.W.L.S", "O.W.L.s")
    title = title.replace("St. Mungo'S", "St. Mungo's")
    title = title.replace("Dumbledore'S", "Dumbledore's")
    title = title.replace("Snape'S", "Snape's")
    return title


def extract_chapters(raw_text: str) -> list[Chapter]:
    text = clean_text(raw_text)
    heading_re = re.compile(r"(?im)^[ \t]*CHAPTER[ \t]+([A-Za-z]+(?:[- \t]+[A-Za-z]+)?)[ \t]*$")
    matches = []
    expected_next = 1
    for match in heading_re.finditer(text):
        number = WORD_TO_NUMBER.get(normalize_chapter_word(match.group(1)))
        if not matches and number is not None and number != expected_next:
            expected_next = number
        if number == expected_next:
            matches.append(match)
            expected_next += 1
        if expected_next > 38:
            break

    chapters: list[Chapter] = []
    for index, match in enumerate(matches):
        number = WORD_TO_NUMBER[normalize_chapter_word(match.group(1))]
        next_start = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        section = text[match.end() : next_start]
        title, body = split_title_and_body(section)
        chapters.append(Chapter(number=number, title=title or CHAPTER_TITLES[number], body=body.strip()))

    return chapters


def looks_like_chapter_start(text: str, heading_end: int) -> bool:
    for line in text[heading_end:].splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        letters = [char for char in stripped if char.isalpha()]
        if not letters:
            return False
        uppercase = sum(1 for char in letters if char.isupper())
        return uppercase / len(letters) >= 0.7
    return False


def split_title_and_body(section: str) -> tuple[str, str]:
    lines = section.splitlines()
    index = 0
    while index < len(lines) and not lines[index].strip():
        index += 1

    title_lines: list[str] = []
    while index < len(lines):
        line = lines[index].strip()
        if not title_lines and not looks_like_title_line(line):
            break
        if not line and title_lines:
            index += 1
            break
        if line:
            title_lines.append(line)
        index += 1

    return title_case_heading(" ".join(title_lines)), "\n".join(lines[index:])


def looks_like_title_line(line: str) -> bool:
    letters = [char for char in line if char.isalpha()]
    if not letters:
        return False
    uppercase = sum(1 for char in letters if char.isupper())
    return uppercase / len(letters) >= 0.7


def normalize_paragraphs(body: str, running_headers: Iterable[str] = ()) -> list[str]:
    header_set = {header.strip().upper() for header in running_headers}
    lines = []
    for raw_line in clean_text(body).splitlines():
        line = raw_line.strip()
        if is_page_artifact(line):
            continue
        if line.upper() in header_set:
            continue
        line = re.sub(r"\b([A-Z])\s{2,}([a-z])", r"\1\2", line)
        lines.append((raw_line, line))

    paragraphs: list[str] = []
    current: list[str] = []
    for raw_line, line in lines:
        if not line:
            flush_paragraph(current, paragraphs)
            current = []
            continue
        if current and is_indented_paragraph_start(raw_line):
            flush_paragraph(current, paragraphs)
            current = []
        current.append(line)
    flush_paragraph(current, paragraphs)
    return paragraphs


def is_page_artifact(line: str) -> bool:
    if not line:
        return False
    if re.fullmatch(r"\d{1,4}", line):
        return True
    if re.fullmatch(r"[·.\- ]*\d{1,4}[·.\- ]*", line):
        return True
    if re.fullmatch(r"CHAPTER\s+[A-Za-z]+(?:[- ]+[A-Za-z]+)?", line, flags=re.IGNORECASE):
        return True
    return False


def is_indented_paragraph_start(raw_line: str) -> bool:
    expanded = raw_line.expandtabs(4)
    stripped = expanded.lstrip()
    indent = len(expanded) - len(stripped)
    return 2 <= indent <= 5 and bool(stripped)


def flush_paragraph(lines: list[str], paragraphs: list[str]) -> None:
    if not lines:
        return
    paragraph = lines[0]
    for line in lines[1:]:
        if paragraph.endswith("-") and line[:1].islower():
            paragraph = paragraph[:-1] + line
        else:
            paragraph += " " + line
    paragraph = re.sub(r"\s+", " ", paragraph).strip()
    if paragraph:
        paragraphs.append(paragraph)


def split_sentences(paragraph: str) -> list[str]:
    paragraph = re.sub(r"\s+", " ", paragraph).strip()
    if not paragraph:
        return []

    sentences: list[str] = []
    start = 0
    index = 0
    while index < len(paragraph):
        char = paragraph[index]
        if char not in ".?!":
            index += 1
            continue

        if char == "." and is_non_terminal_period(paragraph, index):
            index += 1
            continue

        end = index + 1
        while end < len(paragraph) and paragraph[end] in "\"')]}":
            end += 1
        next_index = end
        while next_index < len(paragraph) and paragraph[next_index].isspace():
            next_index += 1
        if is_dialogue_attribution(paragraph, end, next_index):
            index += 1
            continue
        if next_index < len(paragraph) and paragraph[next_index].islower():
            index += 1
            continue

        sentence = paragraph[start:end].strip()
        if sentence:
            sentences.append(sentence)
        start = next_index
        index = next_index

    remainder = paragraph[start:].strip()
    if remainder:
        sentences.append(remainder)
    return sentences or [paragraph]


def is_dialogue_attribution(paragraph: str, end: int, next_index: int) -> bool:
    if end == 0 or paragraph[end - 1] not in "\"'":
        return False
    match = re.match(r"([A-Z][A-Za-z']*)\s+([a-z]+)\b", paragraph[next_index:])
    return bool(match and match.group(2) in SPEECH_VERBS)


def is_non_terminal_period(paragraph: str, index: int) -> bool:
    if paragraph[max(0, index - 4) : index + 6].count(".") >= 3:
        return True

    prefix = paragraph[: index + 1]
    match = re.search(r"[\w']+\.$", prefix)
    token = match.group(0) if match else ""
    if token in SENTENCE_ABBREVIATIONS:
        return True
    if re.fullmatch(r"[A-Z]\.", token):
        return True
    if 0 < index < len(paragraph) - 1 and paragraph[index - 1].isdigit() and paragraph[index + 1].isdigit():
        return True
    return False


def chapter_sentence_groups(chapter: Chapter) -> list[list[str]]:
    heading = f"Chapter {display_chapter_word(chapter.number)}. {chapter.title}."
    paragraphs = normalize_paragraphs(chapter.body, running_headers=running_headers_for(chapter))
    return [[heading], *[split_sentences(paragraph) for paragraph in paragraphs]]


def chapter_fragments(chapter: Chapter) -> list[str]:
    return [sentence for group in chapter_sentence_groups(chapter) for sentence in group]


def running_headers_for(chapter: Chapter) -> set[str]:
    headers = {chapter.title.upper()}
    headers.update(title.upper() for title in CHAPTER_TITLES.values())
    headers.add("THE ADVANCED GUARD")
    return headers


def write_chapter_text_files(chapters: Sequence[Chapter], text_dir: Path) -> list[Path]:
    text_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for chapter in chapters:
        fragments = chapter_fragments(chapter)
        path = text_dir / f"chapter_{chapter.number:03d}.txt"
        path.write_text("\n".join(fragments) + "\n", encoding="utf-8")
        written.append(path)
    return written


def extract_pdf_text(pdf_path: Path, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["pdftotext", "-layout", str(pdf_path), str(output_path)], check=True)


def audio_parts(audio_dir: Path) -> list[Path]:
    return sorted(audio_dir.glob("Part *.mp3"))


def ffprobe_duration(audio_path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(audio_path),
        ],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    return float(result.stdout.strip())


def prepare_inputs(pdf_path: Path, audio_dir: Path, output_dir: Path) -> list[Chapter]:
    raw_text_path = output_dir / "book.txt"
    extract_pdf_text(pdf_path, raw_text_path)
    chapters = extract_chapters(raw_text_path.read_text(encoding="utf-8"))
    validate_chapters(chapters)
    parts = audio_parts(audio_dir)
    if len(parts) < 39:
        raise RuntimeError(f"Expected at least 39 audio parts, found {len(parts)}")
    write_chapter_text_files(chapters, output_dir / "text")
    return chapters


def validate_chapters(chapters: Sequence[Chapter]) -> None:
    numbers = [chapter.number for chapter in chapters]
    expected = list(range(1, 39))
    if numbers != expected:
        raise RuntimeError(f"Expected chapters 1-38 in order, found {numbers}")
    small = [chapter.number for chapter in chapters if len(normalize_paragraphs(chapter.body)) < 5]
    if small:
        raise RuntimeError(f"Suspiciously small chapter extraction: {small}")


def run_aeneas(audio_path: Path, text_path: Path, output_path: Path, force: bool = False) -> None:
    if output_path.exists() and not force:
        return
    output_path.parent.mkdir(parents=True, exist_ok=True)
    config = "task_language=eng|is_text_type=plain|os_task_file_format=json"
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "UTF-8"
    subprocess.run(
        [
            "conda",
            "run",
            "-n",
            "aeneas39",
            "python",
            "-m",
            "aeneas.tools.execute_task",
            str(audio_path),
            str(text_path),
            config,
            str(output_path),
        ],
        check=True,
        env=env,
    )


def align_all(audio_dir: Path, output_dir: Path, force: bool = False) -> None:
    align_dir = output_dir / "alignments"
    text_dir = output_dir / "text"
    parts = audio_parts(audio_dir)[:38]
    if len(parts) != 38:
        raise RuntimeError(f"Expected 38 chapter audio parts, found {len(parts)}")
    for index, audio_path in enumerate(parts, start=1):
        text_path = text_dir / f"chapter_{index:03d}.txt"
        output_path = align_dir / f"chapter_{index:03d}.json"
        print(f"aligning chapter {index:03d}: {audio_path.name}", flush=True)
        run_aeneas(audio_path, text_path, output_path, force=force)
        validate_alignment_file(output_path, ffprobe_duration(audio_path))


def validate_alignment_file(path: Path, duration: float) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    last_end = 0.0
    for fragment in data.get("fragments", []):
        begin = float(fragment["begin"])
        end = float(fragment["end"])
        if begin < last_end - 0.001 or end < begin:
            raise RuntimeError(f"Non-monotonic timestamps in {path}")
        last_end = end
    if last_end <= 0:
        raise RuntimeError(f"No usable timestamps in {path}")
    if last_end > duration + 5:
        raise RuntimeError(f"Alignment exceeds audio duration in {path}: {last_end} > {duration}")


def build_reader_manifest(
    chapters: Sequence[Chapter],
    audio_files: Sequence[Path],
    alignment_dir: Path,
    durations: Sequence[float],
    outro_audio: Path | None = None,
    outro_duration: float | None = None,
) -> dict:
    manifest = {"title": "Harry Potter and the Order of the Phoenix", "duration": 0.0, "chapters": []}
    offset = 0.0
    for chapter, audio_path, duration in zip(chapters, audio_files, durations, strict=True):
        alignment_path = alignment_dir / f"chapter_{chapter.number:03d}.json"
        data = json.loads(alignment_path.read_text(encoding="utf-8"))
        fragments = data.get("fragments", [])
        paragraphs = build_manifest_paragraphs(chapter, fragments, offset)
        manifest["chapters"].append(
            {
                "kind": "chapter",
                "number": chapter.number,
                "title": chapter.title,
                "audio": audio_path.as_posix(),
                "start": round(offset, 3),
                "end": round(offset + duration, 3),
                "duration": round(duration, 3),
                "paragraphs": paragraphs,
            }
        )
        offset += duration

    if outro_audio is not None and outro_duration is not None:
        manifest["chapters"].append(
            {
                "kind": "outro",
                "number": None,
                "title": "Outro",
                "audio": outro_audio.as_posix(),
                "start": round(offset, 3),
                "end": round(offset + outro_duration, 3),
                "duration": round(outro_duration, 3),
                "paragraphs": [],
            }
        )
        offset += outro_duration

    manifest["duration"] = round(offset, 3)
    return manifest


def build_manifest_paragraphs(chapter: Chapter, fragments: Sequence[dict], offset: float) -> list[dict]:
    groups = chapter_sentence_groups(chapter)
    sentence_count = sum(len(group) for group in groups)
    if len(fragments) != sentence_count:
        return build_legacy_manifest_paragraphs(chapter, fragments, offset)

    paragraphs = []
    fragment_index = 0
    for paragraph_index, group in enumerate(groups):
        sentences = []
        for sentence_index, sentence_text in enumerate(group):
            fragment = fragments[fragment_index]
            begin = float(fragment["begin"])
            end = float(fragment["end"])
            fragment_text = " ".join(fragment.get("lines", [])).strip() or sentence_text
            sentences.append(
                {
                    "id": f"c{chapter.number:03d}_p{paragraph_index:06d}_s{sentence_index + 1:06d}",
                    "text": fragment_text,
                    "begin": round(offset + begin, 3),
                    "end": round(offset + end, 3),
                    "localBegin": round(begin, 3),
                    "localEnd": round(end, 3),
                }
            )
            fragment_index += 1

        local_begin = sentences[0]["localBegin"]
        local_end = sentences[-1]["localEnd"]
        paragraphs.append(
            {
                "id": f"c{chapter.number:03d}_p{paragraph_index:06d}",
                "text": " ".join(sentence["text"] for sentence in sentences).strip(),
                "begin": round(offset + local_begin, 3),
                "end": round(offset + local_end, 3),
                "localBegin": local_begin,
                "localEnd": local_end,
                "sentences": sentences,
            }
        )
    return paragraphs


def build_legacy_manifest_paragraphs(chapter: Chapter, fragments: Sequence[dict], offset: float) -> list[dict]:
    paragraphs = []
    for fragment in fragments:
        begin = float(fragment["begin"])
        end = float(fragment["end"])
        text = " ".join(fragment.get("lines", [])).strip()
        paragraphs.append(
            {
                "id": f"c{chapter.number:03d}_{fragment.get('id', len(paragraphs))}",
                "text": text,
                "begin": round(offset + begin, 3),
                "end": round(offset + end, 3),
                "localBegin": round(begin, 3),
                "localEnd": round(end, 3),
            }
        )
    return paragraphs


def build_reader(output_dir: Path, audio_dir: Path) -> None:
    raw_text = (output_dir / "book.txt").read_text(encoding="utf-8")
    chapters = extract_chapters(raw_text)
    validate_chapters(chapters)
    parts = audio_parts(audio_dir)
    chapter_audio = [relative_to_output(path, output_dir) for path in parts[:38]]
    durations = [ffprobe_duration(path) for path in parts[:38]]
    outro_audio = relative_to_output(parts[38], output_dir) if len(parts) > 38 else None
    outro_duration = ffprobe_duration(parts[38]) if len(parts) > 38 else None
    manifest = build_reader_manifest(
        chapters=chapters,
        audio_files=chapter_audio,
        alignment_dir=output_dir / "alignments",
        durations=durations,
        outro_audio=outro_audio,
        outro_duration=outro_duration,
    )
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (output_dir / "index.html").write_text(build_reader_html(manifest), encoding="utf-8")


def relative_to_output(path: Path, output_dir: Path) -> Path:
    return Path(os.path.relpath(path.resolve(), output_dir.resolve()))


def build_reader_html(manifest: dict) -> str:
    manifest_json = json.dumps(manifest, ensure_ascii=False)
    title = html.escape(manifest["title"])
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="icon" href="data:,">
  <title>{title}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f5f5f4;
      --surface: #ffffff;
      --line: #d7d3cc;
      --text: #1c1917;
      --muted: #6b6258;
      --active: #fff3c4;
      --active-line: #b45309;
      --button: #1c1917;
      --button-text: #ffffff;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Helvetica Neue", sans-serif;
      font-size: 16px;
      line-height: 1.55;
    }}
    .app {{
      min-height: 100vh;
      display: grid;
      grid-template-columns: 280px minmax(0, 1fr);
    }}
    aside {{
      border-right: 1px solid var(--line);
      background: var(--surface);
      height: 100vh;
      position: sticky;
      top: 0;
      overflow: auto;
      padding: 20px 16px;
    }}
    .book-title {{
      font-size: 15px;
      font-weight: 700;
      margin: 0 0 16px;
      line-height: 1.3;
    }}
    .chapter-list {{
      display: flex;
      flex-direction: column;
      gap: 2px;
    }}
    .chapter-link {{
      width: 100%;
      border: 0;
      border-radius: 6px;
      background: transparent;
      color: var(--text);
      cursor: pointer;
      display: grid;
      grid-template-columns: 32px 1fr;
      gap: 8px;
      padding: 8px;
      text-align: left;
      font: inherit;
      line-height: 1.3;
    }}
    .chapter-link:hover {{ background: #f0eee9; }}
    .chapter-link.active {{
      background: #e7e1d8;
      font-weight: 650;
    }}
    .chapter-number {{ color: var(--muted); font-variant-numeric: tabular-nums; }}
    .chapter-title {{ display: block; }}
    .chapter-pages {{
      display: block;
      color: var(--muted);
      font-size: 12px;
      font-weight: 500;
      margin-top: 3px;
    }}
    main {{
      min-width: 0;
      padding: 28px 32px 112px;
    }}
    .topbar {{
      max-width: 840px;
      margin: 0 auto 24px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
    }}
    h1 {{
      font-size: 22px;
      line-height: 1.25;
      margin: 0;
      font-weight: 750;
    }}
    .time {{
      color: var(--muted);
      font-variant-numeric: tabular-nums;
      white-space: nowrap;
    }}
    .reader {{
      max-width: 840px;
      margin: 0 auto;
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 28px 34px;
    }}
    .chapter-heading {{
      font-size: 20px;
      margin: 0 0 22px;
      padding-bottom: 14px;
      border-bottom: 1px solid var(--line);
    }}
    .paragraph {{
      margin: 0 0 14px;
      padding: 3px 6px;
      border-left: 3px solid transparent;
      border-radius: 4px;
      cursor: pointer;
    }}
    .paragraph:hover {{ background: #f8f6f1; }}
    .paragraph.active {{
      background: var(--active);
      border-left-color: var(--active-line);
    }}
    .sentence {{
      border-radius: 3px;
      cursor: pointer;
    }}
    .sentence:hover {{ background: #f8f6f1; }}
    .sentence.active {{
      background: var(--active);
      box-shadow: 0 0 0 2px var(--active);
    }}
    .outro {{
      color: var(--muted);
      margin: 0;
    }}
    .player {{
      position: fixed;
      left: 280px;
      right: 0;
      bottom: 0;
      border-top: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.96);
      display: grid;
      grid-template-columns: auto auto auto minmax(120px, 1fr) auto;
      gap: 10px;
      align-items: center;
      padding: 12px 20px;
    }}
    button.control {{
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--surface);
      color: var(--text);
      cursor: pointer;
      min-height: 36px;
      padding: 0 12px;
      font: inherit;
      font-weight: 650;
    }}
    button.primary {{
      background: var(--button);
      color: var(--button-text);
      border-color: var(--button);
      min-width: 68px;
    }}
    input[type="range"] {{
      width: 100%;
      accent-color: #b45309;
    }}
    @media (max-width: 760px) {{
      .app {{ display: block; }}
      aside {{
        position: static;
        height: auto;
        max-height: 240px;
        border-right: 0;
        border-bottom: 1px solid var(--line);
      }}
      main {{ padding: 20px 16px 120px; }}
      .reader {{ padding: 22px 18px; }}
      .topbar {{ align-items: flex-start; flex-direction: column; }}
      .player {{
        left: 0;
        grid-template-columns: auto auto auto;
      }}
      .player input[type="range"] {{
        grid-column: 1 / -1;
      }}
    }}
  </style>
</head>
<body>
  <div class="app">
    <aside>
      <p class="book-title">{title}</p>
      <nav class="chapter-list" id="chapterList"></nav>
    </aside>
    <main>
      <div class="topbar">
        <h1 id="chapterTitle"></h1>
        <div class="time" id="timeLabel">0:00 / 0:00</div>
      </div>
      <article class="reader" id="reader"></article>
    </main>
  </div>
  <div class="player">
    <button class="control" id="prevButton" type="button">Prev</button>
    <button class="control primary" id="playButton" type="button">Play</button>
    <button class="control" id="nextButton" type="button">Next</button>
    <input id="seekBar" type="range" min="0" max="1000" value="0" aria-label="Seek">
    <span class="time" id="chapterTime">0:00</span>
  </div>
  <audio id="audio" preload="metadata"></audio>
  <script>
    const manifest = {manifest_json};
    const audio = document.getElementById('audio');
    const chapterList = document.getElementById('chapterList');
    const reader = document.getElementById('reader');
    const chapterTitle = document.getElementById('chapterTitle');
    const playButton = document.getElementById('playButton');
    const prevButton = document.getElementById('prevButton');
    const nextButton = document.getElementById('nextButton');
    const seekBar = document.getElementById('seekBar');
    const timeLabel = document.getElementById('timeLabel');
    const chapterTime = document.getElementById('chapterTime');
    const progressStorageKey = 'aligned-reader-progress-v1';
    const tocEntries = [
      {{ chapter: 1, title: 'Dudley Demented', bookPage: 1, appPage: 37 }},
      {{ chapter: 2, title: 'A Peck of Owls', bookPage: 20, appPage: 94 }},
      {{ chapter: 3, title: 'The Advance Guard', bookPage: 42, appPage: 159 }},
      {{ chapter: 4, title: 'Number Twelve, Grimmauld Place', bookPage: 59, appPage: 210 }},
      {{ chapter: 5, title: 'The Order of the Phoenix', bookPage: 79, appPage: 270 }},
      {{ chapter: 6, title: 'The Noble and Most Ancient House of Black', bookPage: 98, appPage: 325 }},
      {{ chapter: 7, title: 'The Ministry of Magic', bookPage: 121, appPage: 392 }},
      {{ chapter: 8, title: 'The Hearing', bookPage: 137, appPage: 438 }},
      {{ chapter: 9, title: 'The Woes of Mrs. Weasley', bookPage: 152, appPage: 482 }},
      {{ chapter: 10, title: 'Luna Lovegood', bookPage: 179, appPage: 562 }},
      {{ chapter: 11, title: 'The Sorting Hat’s New Song', bookPage: 200, appPage: 623 }},
      {{ chapter: 12, title: 'Professor Umbridge', bookPage: 221, appPage: 685 }},
      {{ chapter: 13, title: 'Detention with Dolores', bookPage: 250, appPage: 772 }},
      {{ chapter: 14, title: 'Percy and Padfoot', bookPage: 279, appPage: 858 }},
      {{ chapter: 15, title: 'The Hogwarts High Inquisitor', bookPage: 306, appPage: 938 }},
      {{ chapter: 16, title: 'In the Hog’s Head', bookPage: 330, appPage: 1008 }},
      {{ chapter: 17, title: 'Educational Decree Number Twenty-Four', bookPage: 350, appPage: 1066 }},
      {{ chapter: 18, title: 'Dumbledore’s Army', bookPage: 374, appPage: 1136 }},
      {{ chapter: 19, title: 'The Lion and the Serpent', bookPage: 397, appPage: 1205 }},
      {{ chapter: 20, title: 'Hagrid’s Tale', bookPage: 420, appPage: 1273 }},
      {{ chapter: 21, title: 'The Eye of the Snake', bookPage: 441, appPage: 1333 }},
      {{ chapter: 22, title: 'St. Mungo’s Hospital for Magical Maladies and Injuries', bookPage: 466, appPage: 1407 }},
      {{ chapter: 23, title: 'Christmas on the Closed Ward', bookPage: 492, appPage: 1485 }},
      {{ chapter: 24, title: 'Occlumency', bookPage: 516, appPage: 1557 }},
      {{ chapter: 25, title: 'The Beetle at Bay', bookPage: 543, appPage: 1637 }},
      {{ chapter: 26, title: 'Seen and Unforeseen', bookPage: 570, appPage: 1718 }},
      {{ chapter: 27, title: 'The Centaur and the Sneak', bookPage: 599, appPage: 1803 }},
      {{ chapter: 28, title: 'Snape’s Worst Memory', bookPage: 624, appPage: 1877 }},
      {{ chapter: 29, title: 'Career Advice', bookPage: 651, appPage: 1956 }},
      {{ chapter: 30, title: 'Grawp', bookPage: 676, appPage: 2030 }},
      {{ chapter: 31, title: 'O.W.L.s', bookPage: 703, appPage: 2111 }},
      {{ chapter: 32, title: 'Out of the Fire', bookPage: 729, appPage: 2187 }},
      {{ chapter: 33, title: 'Fight and Flight', bookPage: 751, appPage: 2251 }},
      {{ chapter: 34, title: 'The Department of Mysteries', bookPage: 764, appPage: 2290 }},
      {{ chapter: 35, title: 'Beyond the Veil', bookPage: 781, appPage: 2341 }},
      {{ chapter: 36, title: 'The Only One He Ever Feared', bookPage: 807, appPage: 2418 }},
      {{ chapter: 37, title: 'The Lost Prophecy', bookPage: 820, appPage: 2456 }},
      {{ chapter: 38, title: 'The Second War Begins', bookPage: 845, appPage: 2531 }},
    ];
    const tocByChapter = new Map(tocEntries.map((entry) => [entry.chapter, entry]));
    let currentIndex = 0;
    let currentParagraphId = null;
    let pendingStartTime = null;

    function formatTime(seconds) {{
      seconds = Math.max(0, Math.floor(seconds || 0));
      const h = Math.floor(seconds / 3600);
      const m = Math.floor((seconds % 3600) / 60);
      const s = seconds % 60;
      return h ? `${{h}}:${{String(m).padStart(2, '0')}}:${{String(s).padStart(2, '0')}}` : `${{m}}:${{String(s).padStart(2, '0')}}`;
    }}

    function renderNav() {{
      chapterList.innerHTML = '';
      manifest.chapters.forEach((chapter, index) => {{
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'chapter-link' + (index === currentIndex ? ' active' : '');
        const number = chapter.kind === 'chapter' ? String(chapter.number).padStart(2, '0') : '--';
        const tocEntry = tocByChapter.get(chapter.number);
        const title = tocEntry?.title || chapter.title;
        const pages = tocEntry ? `<span class="chapter-pages">Book p. ${{tocEntry.bookPage}} · App p. ${{tocEntry.appPage}}</span>` : '';
        button.innerHTML = `<span class="chapter-number">${{number}}</span><span><span class="chapter-title">${{title}}</span>${{pages}}</span>`;
        button.addEventListener('click', () => loadChapter(index, true));
        chapterList.appendChild(button);
      }});
    }}

    function sentenceItems(paragraph) {{
      return paragraph.sentences && paragraph.sentences.length ? paragraph.sentences : [paragraph];
    }}

    function findPlaybackUnitAt(chapter, local) {{
      for (const paragraph of chapter.paragraphs) {{
        const sentence = sentenceItems(paragraph).find((item) => local >= item.localBegin && local < item.localEnd);
        if (sentence) return sentence;
      }}
      return null;
    }}

    function findParagraphByPlaybackId(chapter, playbackId) {{
      return chapter.paragraphs.find((paragraph) => {{
        if (paragraph.id === playbackId) return true;
        return sentenceItems(paragraph).some((sentence) => sentence.id === playbackId);
      }}) || null;
    }}

    function saveProgress(paragraphId = currentParagraphId, localTime = audio.currentTime || 0) {{
      if (!paragraphId) return;
      try {{
        localStorage.setItem(progressStorageKey, JSON.stringify({{
          chapterIndex: currentIndex,
          paragraphId,
          localTime,
        }}));
      }} catch {{
        // localStorage can be unavailable in private or locked-down browser contexts.
      }}
    }}

    function loadSavedProgress() {{
      try {{
        const saved = JSON.parse(localStorage.getItem(progressStorageKey) || 'null');
        if (!saved || !Number.isInteger(saved.chapterIndex)) return null;

        const chapter = manifest.chapters[saved.chapterIndex];
        if (!chapter) return null;

        const paragraph = findParagraphByPlaybackId(chapter, saved.paragraphId);
        if (!paragraph) return null;
        const playbackUnit = sentenceItems(paragraph).find((item) => item.id === saved.paragraphId) || paragraph;

        const savedTime = Number(saved.localTime);
        const localTime = Number.isFinite(savedTime) ? savedTime : playbackUnit.localBegin;
        return {{
          chapterIndex: saved.chapterIndex,
          paragraphId: playbackUnit.id,
          localTime: Math.max(0, Math.min(localTime, chapter.duration || localTime)),
        }};
      }} catch {{
        return null;
      }}
    }}

    function loadChapter(index, autoplay = false, startTime = 0) {{
      currentIndex = Math.max(0, Math.min(index, manifest.chapters.length - 1));
      const chapter = manifest.chapters[currentIndex];
      currentParagraphId = null;
      pendingStartTime = null;
      audio.src = chapter.audio;
      const tocEntry = tocByChapter.get(chapter.number);
      const displayTitle = tocEntry?.title || chapter.title;
      chapterTitle.textContent = chapter.kind === 'chapter' ? `Chapter ${{chapter.number}}. ${{displayTitle}}` : chapter.title;
      reader.innerHTML = '';
      if (chapter.paragraphs.length) {{
        chapter.paragraphs.forEach((paragraph) => {{
          const node = document.createElement('p');
          node.className = 'paragraph';
          node.id = paragraph.id;
          sentenceItems(paragraph).forEach((sentence, sentenceIndex) => {{
            if (sentenceIndex > 0) node.appendChild(document.createTextNode(' '));
            const sentenceNode = document.createElement('span');
            sentenceNode.className = 'sentence';
            sentenceNode.id = sentence.id;
            sentenceNode.textContent = sentence.text;
            sentenceNode.addEventListener('click', (event) => {{
              event.stopPropagation();
              pendingStartTime = null;
              audio.currentTime = sentence.localBegin;
              updateHighlight(sentence.localBegin);
              saveProgress(sentence.id, sentence.localBegin);
              audio.play();
            }});
            node.appendChild(sentenceNode);
          }});
          node.addEventListener('click', () => {{
            const firstSentence = sentenceItems(paragraph)[0];
            pendingStartTime = null;
            audio.currentTime = firstSentence.localBegin;
            updateHighlight(firstSentence.localBegin);
            saveProgress(firstSentence.id, firstSentence.localBegin);
            audio.play();
          }});
          reader.appendChild(node);
        }});
      }} else {{
        const node = document.createElement('p');
        node.className = 'outro';
        node.textContent = 'Audio outro';
        reader.appendChild(node);
      }}
      renderNav();
      const localStart = Math.max(0, Math.min(Number(startTime) || 0, chapter.duration || 0));
      if (localStart > 0) {{
        pendingStartTime = localStart;
        try {{
          audio.currentTime = localStart;
        }} catch {{
          // Some browsers require metadata before seeking a new audio source.
        }}
        updateTimes(localStart);
      }} else {{
        updateTimes();
      }}
      if (autoplay) {{
        audio.play();
      }}
    }}

    function resolveLocalTime(localOverride = null) {{
      if (typeof localOverride === 'number' && Number.isFinite(localOverride)) {{
        return localOverride;
      }}

      if (pendingStartTime !== null) {{
        return pendingStartTime;
      }}

      const local = Number(audio.currentTime);
      return Number.isFinite(local) ? local : 0;
    }}

    function updateTimes(localOverride = null) {{
      const chapter = manifest.chapters[currentIndex];
      const local = resolveLocalTime(localOverride);
      timeLabel.textContent = `${{formatTime(chapter.start + local)}} / ${{formatTime(manifest.duration)}}`;
      chapterTime.textContent = `${{formatTime(local)}} / ${{formatTime(chapter.duration)}}`;
      seekBar.value = chapter.duration ? String(Math.round((local / chapter.duration) * 1000)) : '0';
      updateHighlight(local);
    }}

    function restorePendingStartTime() {{
      if (pendingStartTime === null) {{
        updateTimes();
        return;
      }}

      const startTime = pendingStartTime;
      audio.currentTime = startTime;
      updateTimes(startTime);
    }}

    function updateHighlight(local) {{
      const chapter = manifest.chapters[currentIndex];
      const unit = findPlaybackUnitAt(chapter, local);
      const nextId = unit ? unit.id : null;
      if (nextId === currentParagraphId) return;
      if (currentParagraphId) {{
        document.getElementById(currentParagraphId)?.classList.remove('active');
      }}
      currentParagraphId = nextId;
      if (currentParagraphId) {{
        const node = document.getElementById(currentParagraphId);
        node?.classList.add('active');
        node?.scrollIntoView({{ block: 'center', behavior: 'smooth' }});
        saveProgress(currentParagraphId, local);
      }}
    }}

    function loadInitialChapter() {{
      const savedProgress = loadSavedProgress();
      if (savedProgress) {{
        loadChapter(savedProgress.chapterIndex, false, savedProgress.localTime);
      }} else {{
        loadChapter(0, false);
      }}
    }}

    playButton.addEventListener('click', () => {{
      if (audio.paused) {{
        if (pendingStartTime !== null) {{
          try {{
            audio.currentTime = pendingStartTime;
          }} catch {{
            // Keep the visible saved sentence if the browser cannot seek yet.
          }}
        }}
        audio.play();
      }} else {{
        audio.pause();
      }}
    }});
    prevButton.addEventListener('click', () => loadChapter(currentIndex - 1, !audio.paused));
    nextButton.addEventListener('click', () => loadChapter(currentIndex + 1, !audio.paused));
    seekBar.addEventListener('input', () => {{
      const chapter = manifest.chapters[currentIndex];
      const local = (Number(seekBar.value) / 1000) * chapter.duration;
      const unit = findPlaybackUnitAt(chapter, local);
      pendingStartTime = null;
      audio.currentTime = local;
      updateHighlight(local);
      saveProgress(unit?.id, local);
    }});
    audio.addEventListener('play', () => playButton.textContent = 'Pause');
    audio.addEventListener('pause', () => playButton.textContent = 'Play');
    audio.addEventListener('timeupdate', () => updateTimes());
    audio.addEventListener('loadedmetadata', restorePendingStartTime);
    audio.addEventListener('seeked', () => {{
      if (pendingStartTime !== null) {{
        const local = Number(audio.currentTime);
        if (!Number.isFinite(local) || Math.abs(local - pendingStartTime) >= 0.25) {{
          updateTimes(pendingStartTime);
          return;
        }}
        pendingStartTime = null;
      }}
      updateTimes();
    }});
    audio.addEventListener('ended', () => {{
      if (currentIndex < manifest.chapters.length - 1) {{
        loadChapter(currentIndex + 1, true);
      }}
    }});

    loadInitialChapter();
  </script>
</body>
</html>
"""


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a local synchronized audiobook reader.")
    parser.add_argument("command", choices=["prepare", "align", "build", "all"])
    parser.add_argument("--pdf", type=Path, default=BOOK_PDF)
    parser.add_argument("--audio-dir", type=Path, default=AUDIO_DIR)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--force", action="store_true", help="rerun existing Aeneas alignment files")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.command in {"prepare", "all"}:
        prepare_inputs(args.pdf, args.audio_dir, args.output_dir)
    if args.command in {"align", "all"}:
        align_all(args.audio_dir, args.output_dir, force=args.force)
    if args.command in {"build", "all"}:
        build_reader(args.output_dir, args.audio_dir)
    if args.command in {"build", "all"}:
        print(f"reader ready: {args.output_dir / 'index.html'}")
    else:
        print(f"{args.command} complete: {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
