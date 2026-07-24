#!/usr/bin/env bash
set -euo pipefail

uv run --with edge-tts python -m tools.reader_pipeline all "$@"
