"""Run the shared Edge TTS timing helper with word boundaries on edge-tts 7.2+."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import edge_tts


HELPER = Path(
    "/Users/chenguagnghui/.codex/skills/edge-tts-highlight-speech/scripts/edge_tts_timings.py"
)


def main() -> int:
    original_communicate = edge_tts.Communicate

    def communicate_with_words(*args, **kwargs):
        kwargs.setdefault("boundary", "WordBoundary")
        return original_communicate(*args, **kwargs)

    edge_tts.Communicate = communicate_with_words
    spec = importlib.util.spec_from_file_location("shared_edge_tts_timings", HELPER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load Edge TTS timing helper: {HELPER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.main(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
