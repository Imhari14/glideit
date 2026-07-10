#!/usr/bin/env python3
"""Minimal MCP server exposing glideit to any MCP-speaking coding agent.

Requires the `mcp` package (`pip install mcp`); the host launches this process.
These tools shell out to scripts/glideit.py and return its printed report — the
agent then Reads the storyboard / frame paths mentioned in that text, and can
save findings back with note_video so later calls surface them cheaply.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = str(ROOT / "scripts" / "glideit.py")

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    sys.stderr.write("The 'mcp' package is required: pip install mcp\n")
    raise

mcp = FastMCP("glideit")


def _run(extra: list[str]) -> str:
    result = subprocess.run([sys.executable, SCRIPT, *extra], capture_output=True, text=True)
    output = result.stdout or ""
    if result.returncode != 0:
        output += "\n[stderr]\n" + (result.stderr or "")
    return output.strip() or "(no output)"


@mcp.tool()
def map_video(source: str, detail: str = "balanced"):
    """Map a whole video: transcript + storyboard montages spanning the runtime.

    Returns a report listing the transcript and storyboard image paths. Read
    those, find the relevant window, then call zoom_video.

    Args:
        source: video URL (yt-dlp supported) or local file path.
        detail: 'fast' | 'balanced' | 'deep' (deep also OCRs the map).
    """
    return _run([source, "--detail", detail])


@mcp.tool()
def zoom_video(source: str, start: str, end: str, resolution: int = 1024):
    """Extract dense, high-res frames + OCR for one window of a video.

    Returns a report listing frame paths (with any OCR snippets) to Read.

    Args:
        source: same URL/path used with map_video (download is cached).
        start: window start as SS, MM:SS, or HH:MM:SS (e.g. '3:00').
        end: window end.
        resolution: frame width in px; 1024+ keeps on-screen code legible.
    """
    return _run([source, "--start", start, "--end", end, "--resolution", str(resolution)])


@mcp.tool()
def note_video(source: str, note: str):
    """Save a note to this video's persistent memory (notes.md).

    Write down what you learned so later map_video / zoom_video calls surface it
    ('prior notes: ...') and you can Read cheap text instead of re-reading frames.
    Call once per observation.

    Args:
        source: same URL/path you mapped (identifies which video's notes.md).
        note: one observation to append.
    """
    return _run([source, "--note", note])


if __name__ == "__main__":
    mcp.run()
