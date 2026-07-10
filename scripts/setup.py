#!/usr/bin/env python3
"""Preflight check for glideit. Verifies required + optional local tools.

Required: ffmpeg, ffprobe, yt-dlp.
Optional: tesseract (OCR sidecar), faster-whisper (local ASR fallback).
"""
from __future__ import annotations

import platform
import shutil
import sys

HINTS = {
    "Windows": {
        "ffmpeg": "winget install Gyan.FFmpeg",
        "yt-dlp": "pip install yt-dlp",
        "tesseract": "winget install UB-Mannheim.TesseractOCR",
    },
    "Darwin": {
        "ffmpeg": "brew install ffmpeg",
        "yt-dlp": "brew install yt-dlp   (or pip install yt-dlp)",
        "tesseract": "brew install tesseract",
    },
    "Linux": {
        "ffmpeg": "sudo apt install ffmpeg",
        "yt-dlp": "pip install yt-dlp",
        "tesseract": "sudo apt install tesseract-ocr",
    },
}


def check(name: str, hints: dict, required: bool) -> bool:
    ok = shutil.which(name) is not None
    if ok:
        status = "OK"
    else:
        status = "MISSING" if required else "optional"
    hint = "" if ok else "  ->  " + hints.get(name, "see project README")
    print(f"[{status:>8}] {name:<11}{hint}")
    return ok or not required


def main() -> None:
    for stream in (sys.stdout, sys.stderr):  # tolerate Unicode on cp1252 consoles
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    osname = platform.system()
    hints = HINTS.get(osname, HINTS["Linux"])
    print(f"glideit preflight - {osname}\n")

    ready = True
    ready &= check("ffmpeg", hints, required=True)
    ready &= check("ffprobe", {"ffprobe": "bundled with ffmpeg"}, required=True)
    ready &= check("yt-dlp", hints, required=True)
    check("tesseract", hints, required=False)

    for imp, pipname, note in (
        ("moonshine_onnx", "useful-moonshine-onnx", "best English ASR, no key, not Whisper"),
        ("vosk", "vosk", "lightest offline ASR, no key, not Whisper"),
        ("faster_whisper", "faster-whisper", "local Whisper fallback, also free/no key"),
    ):
        try:
            __import__(imp)
            print(f"[      OK] {imp:<15} ({note})")
        except ImportError:
            print(f"[optional] {imp:<15} ->  pip install {pipname}  ({note})")

    print()
    print("READY — run:  python scripts/glideit.py \"<url-or-path>\""
          if ready else "MISSING REQUIRED TOOLS — install the items above and re-run.")
    sys.exit(0 if ready else 1)


if __name__ == "__main__":
    main()
