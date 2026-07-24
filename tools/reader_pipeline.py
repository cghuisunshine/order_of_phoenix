from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


BOOK_PDF = Path(
    "The Darwin Economy _ Liberty, Competition, and the Common -- Robert H_ Frank -- "
    "Revised, 2012 -- Princeton University Press -- isbn13 9780691153193 -- "
    "0d008e548694233ab4d9b53ac90068ec -- Anna’s Archive.pdf"
)
OUTPUT_DIR = Path("aligned_reader")
BOOK_TITLE = "The Darwin Economy"
BOOK_SUBTITLE = "Liberty, Competition, and the Common Good"
BOOK_AUTHOR = "Robert H. Frank"
VOICE = "en-GB-RyanNeural"
EDGE_TIMING_SCRIPT = Path(
    "tools/edge_tts_word_boundary.py"
)


@dataclass(frozen=True)
class SectionSpec:
    slug: str
    kind: str
    number: int | None
    title: str
    book_page: str
    pdf_start: int
    pdf_end: int
    opening_marker: str
    opening_text: str


@dataclass(frozen=True)
class Section:
    spec: SectionSpec
    paragraphs: tuple[str, ...]

    @property
    def spoken_heading(self) -> str:
        if self.spec.kind == "chapter":
            return f"Chapter {self.spec.number}. {self.spec.title}."
        return f"{self.spec.title}."

    @property
    def text(self) -> str:
        return "\n\n".join((self.spoken_heading, *self.paragraphs)).strip() + "\n"


SECTION_SPECS = (
    SectionSpec("preface", "preface", None, "Preface", "ix", 11, 18, r"ECONOMICS\s+HAS\s+BEEN", "Behavioral economics has been"),
    SectionSpec("chapter_001", "chapter", 1, "Paralysis", "1", 21, 35, r"OFTEN\s+REMEMBER\s+THE\s+PAST", "People often remember the past"),
    SectionSpec("chapter_002", "chapter", 2, "Darwin’s Wedge", "16", 36, 49, r"WAS\s+BORN\s+IN\s+1945", "I was born in 1945"),
    SectionSpec("chapter_003", "chapter", 3, "No Cash on the Table", "30", 50, 65, r"SMITH’S\s+CONCERNS", "Adam Smith’s concerns"),
    SectionSpec("chapter_004", "chapter", 4, "Starve the Beast—But Which One?", "46", 66, 83, r"MEANS\s+OF\s+THREE\s+SEPARATE", "By means of three separate"),
    SectionSpec("chapter_005", "chapter", 5, "Putting the Positional Consumption Beast on a Diet", "64", 84, 103, r"INSIGHT\s+THAT\s+INDIVIDUAL\s+INCENTIVES", "The insight that individual incentives"),
    SectionSpec("chapter_006", "chapter", 6, "Perpetrators and Victims", "84", 104, 119, r"EVERY\s+COUNTRY", "In almost every country"),
    SectionSpec("chapter_007", "chapter", 7, "Efficiency Rules", "100", 120, 138, r"DEVELOPMENT\s+OF\s+MONEY", "The development of money"),
    SectionSpec("chapter_008", "chapter", 8, "“It’s Your Money…”", "119", 139, 159, r"The\s+Second\s+Treatise", "In The Second Treatise"),
    SectionSpec("chapter_009", "chapter", 9, "Success and Luck", "140", 160, 176, r"OFTEN\s+SPEAK\s+ABOUT", "People often speak about"),
    SectionSpec("chapter_010", "chapter", 10, "The Great Trade-Off?", "157", 177, 191, r"OCIALISMDOESNTWORK\.COM", "Socialismdoesntwork.com"),
    SectionSpec("chapter_011", "chapter", 11, "Taxing Harmful Activities", "172", 192, 213, r"TAX\s+ON\s+ANY\s+ACTIVITY", "A tax on any activity"),
    SectionSpec("chapter_012", "chapter", 12, "The Libertarian’s Objections Reconsidered", "194", 214, 236, r"IFFERENT\s+PEOPLE\s+HAVE\s+DIFFERENT\s+VISIONS", "Different people have different visions"),
    SectionSpec("afterword", "afterword", None, "Afterword to the Paperback Edition", "217", 237, 242, r"N\s+APRIL\s+2011", "In April 2011"),
)


def clean_text(text: str) -> str:
    replacements = {
        "\r\n": "\n",
        "\r": "\n",
        "\u00ad": "",
        "|": "I",
        "ﬁ": "fi",
        "ﬂ": "fl",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def extract_pdf_pages(pdf_path: Path, start: int, end: int) -> list[str]:
    result = subprocess.run(
        ["pdftotext", "-f", str(start), "-l", str(end), "-layout", str(pdf_path), "-"],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    pages = clean_text(result.stdout).split("\f")
    return pages[: end - start + 1]


def first_nonempty_index(lines: list[str]) -> int | None:
    return next((index for index, line in enumerate(lines) if line.strip()), None)


def clean_section_pages(pages: Sequence[str], spec: SectionSpec) -> str:
    output: list[str] = []
    marker_re = re.compile(spec.opening_marker, flags=re.IGNORECASE)
    for page_index, page in enumerate(pages):
        lines = page.splitlines()
        if page_index == 0:
            marker_line = next((i for i, line in enumerate(lines) if marker_re.search(line)), None)
            if marker_line is None:
                raise RuntimeError(f"Opening marker not found for {spec.title!r}")
            match = marker_re.search(lines[marker_line])
            assert match is not None
            lines = [spec.opening_text + lines[marker_line][match.end() :], *lines[marker_line + 1 :]]
        else:
            header_index = first_nonempty_index(lines)
            if header_index is not None:
                lines.pop(header_index)
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
        if lines and is_page_artifact(lines[-1].strip()):
            lines.pop()
        while lines and not lines[-1].strip():
            lines.pop()
        output.extend(lines)
    return "\n".join(output)


def is_page_artifact(line: str) -> bool:
    if not line:
        return False
    if re.fullmatch(r"[ivxlcdm\d{}()\[\]|'`.,;:~\- ]{1,12}", line, flags=re.IGNORECASE):
        return True
    return bool(re.fullmatch(r"CHAPTER\s+[A-Z]+", line, flags=re.IGNORECASE))


def is_indented_paragraph_start(raw_line: str) -> bool:
    expanded = raw_line.expandtabs(4)
    indent = len(expanded) - len(expanded.lstrip())
    return 2 <= indent <= 6 and bool(expanded.strip())


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
    paragraph = paragraph.replace("ona Diet", "on a Diet")
    paragraph = re.sub(r"\bofthe\b", "of the", paragraph, flags=re.IGNORECASE)
    paragraph = paragraph.replace("Repreentatives", "Representatives")
    paragraph = re.sub(r"\bPll\b", "I'll", paragraph)
    contractions = {
        "arent": "aren't", "cant": "can't", "couldnt": "couldn't", "didnt": "didn't",
        "doesnt": "doesn't", "dont": "don't", "hadnt": "hadn't", "hasnt": "hasn't",
        "havent": "haven't", "hed": "he'd", "isnt": "isn't", "shouldnt": "shouldn't",
        "theyd": "they'd", "wasnt": "wasn't", "werent": "weren't", "wouldnt": "wouldn't",
        "youd": "you'd", "youre": "you're", "youve": "you've",
    }
    for source, replacement in contractions.items():
        paragraph = re.sub(rf"\b{source}\b", replacement, paragraph, flags=re.IGNORECASE)
    paragraph = re.sub(r"\bSO,\b", "SO2", paragraph)
    if paragraph:
        paragraphs.append(paragraph)


def normalize_paragraphs(body: str) -> list[str]:
    body = re.sub(r"typi-\s+(?:ain\s+S\s+)?cally", "typically", body, flags=re.IGNORECASE)
    lines: list[tuple[str, str]] = []
    for raw_line in clean_text(body).splitlines():
        line = raw_line.strip()
        if is_page_artifact(line):
            continue
        lines.append((raw_line, line))

    paragraphs: list[str] = []
    current: list[str] = []
    for raw_line, line in lines:
        if not line:
            flush_paragraph(current, paragraphs)
            current = []
            continue
        previous_ends_sentence = bool(current and re.search(r"[.!?][\"'”’)]?$", current[-1]))
        if current and is_indented_paragraph_start(raw_line) and previous_ends_sentence:
            flush_paragraph(current, paragraphs)
            current = []
        current.append(line)
    flush_paragraph(current, paragraphs)
    compound_fixes = {
        "highspeed": "high-speed", "invisiblehand": "invisible-hand",
        "onebedroom": "one-bedroom", "twobedroom": "two-bedroom",
        "smokefree": "smoke-free", "workplace": "workplace",
    }
    return [
        _fix_compounds(re.sub(r"\bSO,+", "SO2", paragraph).replace("8,o00", "8,000"), compound_fixes)
        for paragraph in paragraphs
    ]


def _fix_compounds(text: str, fixes: dict[str, str]) -> str:
    for source, replacement in fixes.items():
        text = re.sub(rf"\b{source}\b", replacement, text, flags=re.IGNORECASE)
    return text


def extract_sections(pdf_path: Path) -> list[Section]:
    sections: list[Section] = []
    for spec in SECTION_SPECS:
        pages = extract_pdf_pages(pdf_path, spec.pdf_start, spec.pdf_end)
        body = clean_section_pages(pages, spec)
        paragraphs = tuple(normalize_paragraphs(body))
        if len(paragraphs) < 5:
            raise RuntimeError(f"Suspiciously small extraction for {spec.title!r}: {len(paragraphs)} paragraphs")
        sections.append(Section(spec, paragraphs))
    return sections


def write_text_assets(sections: Sequence[Section], output_dir: Path) -> None:
    text_dir = output_dir / "text"
    if text_dir.exists():
        shutil.rmtree(text_dir)
    text_dir.mkdir(parents=True)
    book_parts = []
    for section in sections:
        text = section.text
        (text_dir / f"{section.spec.slug}.txt").write_text(text, encoding="utf-8")
        book_parts.append(text.rstrip())
    (output_dir / "book.txt").write_text("\n\n\n".join(book_parts) + "\n", encoding="utf-8")


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


def generate_narration(sections: Sequence[Section], output_dir: Path, force: bool = False) -> None:
    if not EDGE_TIMING_SCRIPT.exists():
        raise RuntimeError(f"Edge TTS timing script not found: {EDGE_TIMING_SCRIPT}")
    audio_dir = output_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    for index, section in enumerate(sections, start=1):
        audio_path = audio_dir / f"{section.spec.slug}.mp3"
        timing_path = audio_dir / f"{section.spec.slug}.words.json"
        if audio_path.exists() and timing_path.exists() and not force:
            timing = json.loads(timing_path.read_text(encoding="utf-8"))
            if timing.get("text") == section.text and timing.get("words"):
                print(f"[{index:02d}/{len(sections):02d}] keeping {section.spec.title}", flush=True)
                continue
        print(f"[{index:02d}/{len(sections):02d}] narrating {section.spec.title}", flush=True)
        subprocess.run(
            [
                sys.executable,
                str(EDGE_TIMING_SCRIPT),
                "--text-file",
                str(output_dir / "text" / f"{section.spec.slug}.txt"),
                "--out-dir",
                str(audio_dir),
                "--basename",
                section.spec.slug,
                "--voice",
                VOICE,
            ],
            check=True,
        )


def paragraph_ranges(text: str) -> list[tuple[int, int, str]]:
    ranges = []
    cursor = 0
    for paragraph in text.rstrip("\n").split("\n\n"):
        start = text.find(paragraph, cursor)
        end = start + len(paragraph)
        ranges.append((start, end, paragraph))
        cursor = end
    return ranges


def section_manifest(section: Section, output_dir: Path, section_index: int, offset: float) -> dict:
    audio_path = output_dir / "audio" / f"{section.spec.slug}.mp3"
    timing_path = output_dir / "audio" / f"{section.spec.slug}.words.json"
    timing = json.loads(timing_path.read_text(encoding="utf-8"))
    if timing.get("text") != section.text:
        raise RuntimeError(f"Timing text does not match visible text for {section.spec.title!r}")
    duration = ffprobe_duration(audio_path)
    words = timing.get("words", [])
    paragraphs = []
    for paragraph_index, (start_char, end_char, paragraph_text) in enumerate(paragraph_ranges(section.text)):
        paragraph_words = []
        for word_index, word in enumerate(words):
            if start_char <= word["start_char"] < end_char:
                paragraph_words.append(
                    {
                        "id": f"s{section_index:03d}_p{paragraph_index:04d}_w{word_index:06d}",
                        "text": word["text"],
                        "start": word["start"],
                        "end": word["end"],
                        "startChar": word["start_char"] - start_char,
                        "endChar": min(word["end_char"], end_char) - start_char,
                    }
                )
        paragraphs.append(
            {
                "id": f"s{section_index:03d}_p{paragraph_index:04d}",
                "kind": "heading" if paragraph_index == 0 else "body",
                "text": paragraph_text,
                "words": paragraph_words,
            }
        )
    return {
        "slug": section.spec.slug,
        "kind": section.spec.kind,
        "number": section.spec.number,
        "title": section.spec.title,
        "bookPage": section.spec.book_page,
        "pdfPage": section.spec.pdf_start,
        "audio": f"audio/{section.spec.slug}.mp3",
        "voice": VOICE,
        "start": round(offset, 3),
        "end": round(offset + duration, 3),
        "duration": round(duration, 3),
        "paragraphs": paragraphs,
    }


def build_manifest(sections: Sequence[Section], output_dir: Path) -> dict:
    manifest = {
        "title": BOOK_TITLE,
        "subtitle": BOOK_SUBTITLE,
        "author": BOOK_AUTHOR,
        "voice": VOICE,
        "duration": 0.0,
        "sections": [],
    }
    offset = 0.0
    for index, section in enumerate(sections, start=1):
        item = section_manifest(section, output_dir, index, offset)
        manifest["sections"].append(item)
        offset = item["end"]
    manifest["duration"] = round(offset, 3)
    return manifest


def build_reader_html(manifest: dict) -> str:
    manifest_json = json.dumps(manifest, ensure_ascii=False, separators=(",", ":"))
    title = html.escape(manifest["title"])
    subtitle = html.escape(manifest["subtitle"])
    author = html.escape(manifest["author"])
    return f'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="theme-color" content="#f5f2ea">
  <link rel="icon" href="data:,">
  <title>{title}</title>
  <style>
    :root {{ color-scheme: light; --bg:#f5f2ea; --surface:#fffdfa; --line:#d8d0c4; --text:#28231f; --muted:#6e655b; --hover:#f0ebe2; --active:#f6dfa0; --button:#302a25; --button-text:#fff; }}
    * {{ box-sizing: border-box; }}
    body {{ margin:0; background:var(--bg); color:var(--text); font-family:Charter,"Bitstream Charter","Iowan Old Style",Georgia,serif; font-size:17px; line-height:1.62; }}
    button,input {{ font:inherit; }}
    .app {{ min-height:100vh; display:grid; grid-template-columns:252px minmax(0,1fr); }}
    aside {{ position:sticky; top:0; height:100vh; overflow:auto; padding:20px 14px; border-right:1px solid var(--line); background:var(--surface); }}
    .book-title {{ margin:0; font-family:ui-sans-serif,system-ui,sans-serif; font-size:15px; font-weight:750; line-height:1.3; }}
    .book-subtitle,.book-author {{ margin:4px 0 0; color:var(--muted); font-family:ui-sans-serif,system-ui,sans-serif; font-size:12px; line-height:1.35; }}
    .book-author {{ margin-bottom:18px; }}
    .section-list {{ display:flex; flex-direction:column; gap:2px; }}
    .section-link {{ width:100%; display:grid; grid-template-columns:30px 1fr; gap:8px; padding:8px; border:0; border-radius:6px; background:transparent; color:var(--text); text-align:left; cursor:pointer; font-family:ui-sans-serif,system-ui,sans-serif; font-size:13px; line-height:1.3; }}
    .section-link:hover {{ background:var(--hover); }}
    .section-link.active {{ background:#e9e2d7; font-weight:700; }}
    .section-number,.section-page {{ color:var(--muted); font-variant-numeric:tabular-nums; }}
    .section-page {{ display:block; margin-top:2px; font-size:11px; font-weight:500; }}
    main {{ min-width:0; padding:26px 30px 112px; }}
    .topbar {{ max-width:800px; margin:0 auto 20px; display:flex; align-items:flex-start; justify-content:space-between; gap:16px; font-family:ui-sans-serif,system-ui,sans-serif; }}
    h1 {{ margin:0; font-size:21px; line-height:1.3; }}
    .time {{ color:var(--muted); font-family:ui-sans-serif,system-ui,sans-serif; font-size:13px; font-variant-numeric:tabular-nums; white-space:nowrap; }}
    .reader {{ max-width:800px; margin:0 auto; padding:28px 36px; border:1px solid var(--line); border-radius:8px; background:var(--surface); }}
    .paragraph {{ margin:0 0 16px; padding:2px 5px; border-left:2px solid transparent; border-radius:3px; }}
    .paragraph.heading {{ margin-bottom:22px; padding-bottom:14px; border-bottom:1px solid var(--line); font-family:ui-sans-serif,system-ui,sans-serif; font-size:18px; font-weight:750; }}
    .paragraph.is-speaking {{ border-left-color:#a35d12; }}
    .tts-word {{ border-radius:2px; cursor:pointer; transition:background-color 120ms ease,color 120ms ease; }}
    .tts-word:hover {{ background:var(--hover); }}
    .tts-word.is-speaking {{ background:var(--active); color:#1f1a16; }}
    .player {{ position:fixed; left:252px; right:0; bottom:0; z-index:5; display:grid; grid-template-columns:auto auto auto auto minmax(130px,1fr) auto; gap:9px; align-items:center; padding:11px 18px; border-top:1px solid var(--line); background:rgba(255,253,250,.97); font-family:ui-sans-serif,system-ui,sans-serif; }}
    .control {{ min-height:36px; padding:0 11px; border:1px solid var(--line); border-radius:6px; background:var(--surface); color:var(--text); cursor:pointer; font-size:14px; font-weight:650; }}
    .control:hover {{ background:var(--hover); }}
    .control.primary {{ min-width:66px; border-color:var(--button); background:var(--button); color:var(--button-text); }}
    input[type="range"] {{ width:100%; accent-color:#a35d12; }}
    @media (max-width:760px) {{
      .app {{ display:block; }}
      aside {{ position:static; height:auto; max-height:220px; border-right:0; border-bottom:1px solid var(--line); }}
      main {{ padding:18px 14px 138px; }}
      .reader {{ padding:22px 18px; }}
      .topbar {{ flex-direction:column; gap:5px; }}
      .player {{ left:0; grid-template-columns:repeat(4,auto); padding:9px 12px; }}
      .player input[type="range"] {{ grid-column:1/-1; grid-row:2; }}
      .player .time {{ grid-column:1/-1; text-align:right; }}
    }}
  </style>
</head>
<body>
  <div class="app">
    <aside>
      <p class="book-title">{title}</p>
      <p class="book-subtitle">{subtitle}</p>
      <p class="book-author">{author}</p>
      <nav class="section-list" id="sectionList" aria-label="Book sections"></nav>
    </aside>
    <main>
      <div class="topbar"><h1 id="sectionTitle"></h1><div class="time" id="totalTime">0:00 / 0:00</div></div>
      <article class="reader" id="reader"></article>
    </main>
  </div>
  <div class="player">
    <button class="control" id="prevButton" type="button">Prev</button>
    <button class="control primary" id="playButton" type="button">Play</button>
    <button class="control" id="nextButton" type="button">Next</button>
    <button class="control" id="searchButton" type="button">Search</button>
    <input id="seekBar" type="range" min="0" max="1000" value="0" aria-label="Seek within section">
    <span class="time" id="sectionTime">0:00 / 0:00</span>
  </div>
  <audio id="audio" preload="metadata"></audio>
  <script>
    const manifest={manifest_json};
    const audio=document.getElementById('audio');
    const sectionList=document.getElementById('sectionList');
    const reader=document.getElementById('reader');
    const sectionTitle=document.getElementById('sectionTitle');
    const playButton=document.getElementById('playButton');
    const seekBar=document.getElementById('seekBar');
    const totalTime=document.getElementById('totalTime');
    const sectionTime=document.getElementById('sectionTime');
    const progressStorageKey='darwin-economy-reader-progress-v1';
    let currentIndex=0;
    let currentWords=[];
    let activeWordIndex=-1;
    let activeParagraph=null;
    let pendingStartTime=null;
    let animationFrame=null;

    function formatTime(value) {{
      const seconds=Math.max(0,Math.floor(value||0));
      const h=Math.floor(seconds/3600),m=Math.floor((seconds%3600)/60),s=seconds%60;
      return h?`${{h}}:${{String(m).padStart(2,'0')}}:${{String(s).padStart(2,'0')}}`:`${{m}}:${{String(s).padStart(2,'0')}}`;
    }}

    function displayTitle(section) {{
      return section.kind==='chapter'?`Chapter ${{section.number}}. ${{section.title}}`:section.title;
    }}

    function renderNav() {{
      sectionList.textContent='';
      manifest.sections.forEach((section,index)=>{{
        const button=document.createElement('button');
        button.type='button';
        button.className='section-link'+(index===currentIndex?' active':'');
        const number=section.kind==='chapter'?String(section.number).padStart(2,'0'):section.kind==='preface'?'PF':'AF';
        const numberNode=document.createElement('span');
        numberNode.className='section-number'; numberNode.textContent=number;
        const label=document.createElement('span'); label.textContent=section.title;
        const page=document.createElement('span'); page.className='section-page'; page.textContent=`Book p. ${{section.bookPage}} · PDF p. ${{section.pdfPage}}`;
        label.appendChild(page); button.append(numberNode,label);
        button.addEventListener('click',()=>loadSection(index,false));
        sectionList.appendChild(button);
      }});
    }}

    function renderTimedText(node,paragraph) {{
      let cursor=0;
      paragraph.words.forEach((word)=>{{
        if(word.startChar>cursor) node.append(document.createTextNode(paragraph.text.slice(cursor,word.startChar)));
        const span=document.createElement('span');
        span.className='tts-word'; span.id=word.id; span.textContent=paragraph.text.slice(word.startChar,word.endChar);
        const entry={{...word,element:span,paragraph:node}};
        const wordIndex=currentWords.length; currentWords.push(entry);
        span.addEventListener('click',(event)=>{{event.stopPropagation();seekAndPlay(word.start);}});
        node.appendChild(span); cursor=word.endChar;
      }});
      if(cursor<paragraph.text.length) node.append(document.createTextNode(paragraph.text.slice(cursor)));
    }}

    function renderSection(section) {{
      reader.textContent=''; currentWords=[]; activeWordIndex=-1; activeParagraph=null;
      section.paragraphs.forEach((paragraph)=>{{
        const node=document.createElement(paragraph.kind==='heading'?'h2':'p');
        node.className='paragraph '+paragraph.kind; node.id=paragraph.id;
        renderTimedText(node,paragraph);
        node.addEventListener('click',()=>{{const first=paragraph.words[0];if(first)seekAndPlay(first.start);}});
        reader.appendChild(node);
      }});
    }}

    function wordIndexAt(time) {{
      let low=0,high=currentWords.length-1,result=-1;
      while(low<=high) {{const mid=(low+high)>>1;if(currentWords[mid].start<=time){{result=mid;low=mid+1;}}else high=mid-1;}}
      return result>=0&&time<currentWords[result].end?result:-1;
    }}

    function paint(time=resolveLocalTime()) {{
      const next=wordIndexAt(time);
      if(next!==activeWordIndex) {{
        const previous=currentWords[activeWordIndex];
        previous?.element.classList.remove('is-speaking');
        activeWordIndex=next;
        const active=currentWords[activeWordIndex];
        if(active) {{
          active.element.classList.add('is-speaking');
          if(active.paragraph!==activeParagraph) {{
            activeParagraph?.classList.remove('is-speaking');
            activeParagraph=active.paragraph;
            activeParagraph.classList.add('is-speaking');
          }}
          active.element.scrollIntoView({{block:'center',behavior:'smooth'}});
          saveProgress(active.id,time);
        }}
      }}
    }}

    function paintLoop() {{
      paint(); updateTimes();
      if(!audio.paused&&!audio.ended) animationFrame=requestAnimationFrame(paintLoop);
    }}

    function resolveLocalTime() {{
      if(pendingStartTime!==null) return pendingStartTime;
      const value=Number(audio.currentTime); return Number.isFinite(value)?value:0;
    }}

    function updateTimes() {{
      const section=manifest.sections[currentIndex],local=resolveLocalTime();
      totalTime.textContent=`${{formatTime(section.start+local)}} / ${{formatTime(manifest.duration)}}`;
      sectionTime.textContent=`${{formatTime(local)}} / ${{formatTime(section.duration)}}`;
      seekBar.value=section.duration?String(Math.round(local/section.duration*1000)):'0'; paint(local);
    }}

    function saveProgress(wordId=currentWords[activeWordIndex]?.id,localTime=resolveLocalTime()) {{
      if(!wordId)return;
      try{{localStorage.setItem(progressStorageKey,JSON.stringify({{sectionIndex:currentIndex,wordId,localTime}}));}}catch{{}}
    }}

    function loadSavedProgress() {{
      try{{
        const saved=JSON.parse(localStorage.getItem(progressStorageKey)||'null');
        if(!saved||!Number.isInteger(saved.sectionIndex)||!manifest.sections[saved.sectionIndex])return null;
        return {{sectionIndex:saved.sectionIndex,localTime:Number(saved.localTime)||0}};
      }}catch{{return null;}}
    }}

    function loadSection(index,autoplay=false,startTime=0) {{
      currentIndex=Math.max(0,Math.min(index,manifest.sections.length-1));
      const section=manifest.sections[currentIndex]; pendingStartTime=null;
      sectionTitle.textContent=displayTitle(section); renderSection(section); renderNav();
      audio.src=section.audio;
      const local=Math.max(0,Math.min(Number(startTime)||0,section.duration));
      if(local>0){{pendingStartTime=local;try{{audio.currentTime=local;}}catch{{}}}}
      updateTimes();
      if(autoplay)audio.play();
    }}

    function seekAndPlay(time) {{pendingStartTime=null;audio.currentTime=time;paint(time);saveProgress(currentWords[wordIndexAt(time)]?.id,time);audio.play();}}

    function searchText(query) {{
      const needle=query.trim().toLocaleLowerCase(); if(!needle)return null;
      for(let pass=0;pass<2;pass++){{
        const start=pass===0?currentIndex:0,end=pass===0?manifest.sections.length:currentIndex;
        for(let sectionIndex=start;sectionIndex<end;sectionIndex++){{
          for(const paragraph of manifest.sections[sectionIndex].paragraphs){{
            const charIndex=paragraph.text.toLocaleLowerCase().indexOf(needle);
            if(charIndex>=0){{const word=paragraph.words.find(item=>item.endChar>charIndex)||paragraph.words[0];return {{sectionIndex,paragraphId:paragraph.id,time:word?.start||0}};}}
          }}
        }}
      }}
      return null;
    }}

    function promptSearch() {{
      const query=window.prompt('Search text'); if(query===null)return;
      const match=searchText(query); if(!match){{window.alert('No match found.');return;}}
      loadSection(match.sectionIndex,false,match.time);
      document.getElementById(match.paragraphId)?.scrollIntoView({{block:'center'}});
    }}

    document.getElementById('prevButton').addEventListener('click',()=>loadSection(currentIndex-1,!audio.paused));
    document.getElementById('nextButton').addEventListener('click',()=>loadSection(currentIndex+1,!audio.paused));
    document.getElementById('searchButton').addEventListener('click',promptSearch);
    playButton.addEventListener('click',()=>audio.paused?audio.play():audio.pause());
    seekBar.addEventListener('input',()=>{{const section=manifest.sections[currentIndex];seekAndPlay(Number(seekBar.value)/1000*section.duration);}});
    audio.addEventListener('play',()=>{{playButton.textContent='Pause';cancelAnimationFrame(animationFrame);paintLoop();}});
    audio.addEventListener('pause',()=>{{playButton.textContent='Play';cancelAnimationFrame(animationFrame);updateTimes();}});
    audio.addEventListener('loadedmetadata',()=>{{if(pendingStartTime!==null){{audio.currentTime=pendingStartTime;pendingStartTime=null;}}updateTimes();}});
    audio.addEventListener('ended',()=>{{if(currentIndex<manifest.sections.length-1)loadSection(currentIndex+1,true);}});

    const saved=loadSavedProgress();
    loadSection(saved?.sectionIndex||0,false,saved?.localTime||0);
  </script>
</body>
</html>'''


def prepare(pdf_path: Path, output_dir: Path) -> list[Section]:
    output_dir.mkdir(parents=True, exist_ok=True)
    old_alignments = output_dir / "alignments"
    if old_alignments.exists():
        shutil.rmtree(old_alignments)
    sections = extract_sections(pdf_path)
    write_text_assets(sections, output_dir)
    return sections


def load_prepared_sections(output_dir: Path) -> list[Section]:
    sections = []
    for spec in SECTION_SPECS:
        text = (output_dir / "text" / f"{spec.slug}.txt").read_text(encoding="utf-8").rstrip("\n")
        parts = text.split("\n\n")
        sections.append(Section(spec, tuple(parts[1:])))
    return sections


def build(sections: Sequence[Section], output_dir: Path) -> None:
    manifest = build_manifest(sections, output_dir)
    (output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "index.html").write_text(build_reader_html(manifest), encoding="utf-8")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the synchronized Darwin Economy reader.")
    parser.add_argument("command", choices=("prepare", "narrate", "build", "all"))
    parser.add_argument("--pdf", type=Path, default=BOOK_PDF)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--force", action="store_true", help="regenerate existing narration")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.command in {"prepare", "all"}:
        sections = prepare(args.pdf, args.output_dir)
    else:
        sections = load_prepared_sections(args.output_dir)
    if args.command in {"narrate", "all"}:
        generate_narration(sections, args.output_dir, force=args.force)
    if args.command in {"build", "all"}:
        build(sections, args.output_dir)
        print(f"reader ready: {args.output_dir / 'index.html'}")
    else:
        print(f"{args.command} complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
