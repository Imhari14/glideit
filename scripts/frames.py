"""Frame operations: scene detection, extraction, dedup, montage, OCR.

All local. ffmpeg does the pixel work; everything else is stdlib. No model, no
network. These are the mechanics behind the map (storyboard) and zoom (dense
frames + OCR) passes.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path


def _has(name: str) -> bool:
    return shutil.which(name) is not None


def _need_ffmpeg() -> None:
    if not _has("ffmpeg"):
        raise SystemExit("ffmpeg not found. Run: python scripts/setup.py")


def fmt_ts(seconds: float) -> str:
    t = int(round(seconds))
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def fmt_ts_fine(seconds: float) -> str:
    """Like fmt_ts, but appends a one-decimal fraction when the time isn't a whole
    second — so dense (sub-second) --fps frames read distinctly (00:10 vs 00:10.5)."""
    seconds = round(seconds, 1)
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    base = f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
    tenth = int(round((seconds - total) * 10))
    return f"{base}.{tenth}" if tenth else base


# ---------------------------------------------------------------- scene detection
def detect_scenes(path: str, threshold: float = 0.3, limit: int = 5000) -> list[float]:
    """Timestamps where the frame content changes past `threshold` (0..1)."""
    _need_ffmpeg()
    cmd = ["ffmpeg", "-i", str(path), "-filter:v",
           f"select='gt(scene,{threshold})',showinfo", "-f", "null", "-"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    out: list[float] = []
    for m in re.finditer(r"pts_time:([0-9.]+)", r.stderr):
        out.append(float(m.group(1)))
        if len(out) >= limit:
            break
    return out


def pick_storyboard_timestamps(duration: float, scenes: list[float],
                               budget: int = 64) -> list[float]:
    """~budget timestamps spanning the whole video, favouring scene changes."""
    if duration <= 0:
        return [0.0]
    if scenes and len(scenes) >= budget:
        step = len(scenes) / budget
        picked = [scenes[int(i * step)] for i in range(budget)]
    else:
        marks = {round(s, 2) for s in scenes if 0 <= s <= duration}
        for i in range(budget):  # top up with uniform samples
            marks.add(round(duration * i / max(1, budget - 1), 2))
        picked = sorted(marks)
        if len(picked) > budget:
            step = len(picked) / budget
            picked = [picked[int(i * step)] for i in range(budget)]
    return sorted(t for t in picked if 0 <= t <= duration)


# ---------------------------------------------------------------- extraction
def _font_arg() -> str | None:
    """First available system font, escaped for an ffmpeg drawtext filtergraph."""
    for c in (
        r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\segoeui.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
    ):
        if os.path.exists(c):
            return c.replace("\\", "/").replace(":", r"\:")
    return None


def extract_at(path: str, timestamps: list[float], out_dir: Path,
               resolution: int = 512, label: bool = True,
               precise_label: bool = False) -> list[dict]:
    """One JPEG per timestamp. Burns a `MM:SS` label if a font is found.

    Returns [{t, path}] for frames that were written.
    """
    _need_ffmpeg()
    out_dir.mkdir(parents=True, exist_ok=True)
    font = _font_arg() if label else None
    frames: list[dict] = []
    for i, t in enumerate(timestamps):
        p = out_dir / f"f{i:04d}.jpg"
        vf = f"scale={resolution}:-2"
        if font:
            # escape ':' inside the drawtext value or ffmpeg's filtergraph parser splits on it
            label_txt = (fmt_ts_fine(t) if precise_label else fmt_ts(t)).replace(":", r"\:")
            vf += (f",drawtext=fontfile='{font}':text='{label_txt}':x=10:y=10:"
                   f"fontsize=24:fontcolor=white:box=1:boxcolor=black@0.6:boxborderw=6")
        cmd = ["ffmpeg", "-y", "-ss", f"{t:.3f}", "-i", str(path),
               "-frames:v", "1", "-vf", vf, "-q:v", "3", str(p)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0 or not p.exists():
            # drawtext/font can fail on some builds — retry unlabelled
            cmd = ["ffmpeg", "-y", "-ss", f"{t:.3f}", "-i", str(path),
                   "-frames:v", "1", "-vf", f"scale={resolution}:-2", "-q:v", "3", str(p)]
            subprocess.run(cmd, capture_output=True, text=True)
        if p.exists():
            frames.append({"t": round(float(t), 2), "path": str(p)})
    return frames


# ---------------------------------------------------------------- dedup
def dedup(frames: list[dict], threshold: float = 2.0) -> tuple[list[dict], int]:
    """Drop near-identical frames via 16x16 grayscale mean-abs-diff.

    Compares each frame against the last *kept* frame (catches slow fades). Pure
    stdlib after ffmpeg reduces each JPEG to 256 grayscale bytes.
    """
    if len(frames) <= 1:
        return frames, 0
    _need_ffmpeg()
    kept: list[dict] = []
    last: bytes | None = None
    dropped = 0
    for fr in frames:
        raw = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", fr["path"],
             "-vf", "scale=16:16,format=gray", "-frames:v", "1", "-f", "rawvideo", "-"],
            capture_output=True,
        ).stdout
        if len(raw) < 256:
            kept.append(fr)
            last = raw
            continue
        px = raw[:256]
        if last is None or len(last) < 256:
            kept.append(fr)
            last = px
            continue
        diff = sum(abs(px[i] - last[i]) for i in range(256)) / 256.0
        if diff <= threshold:
            dropped += 1
            try:
                os.remove(fr["path"])
            except OSError:
                pass
        else:
            kept.append(fr)
            last = px
    return kept, dropped


# ---------------------------------------------------------------- montage
def montage(frames: list[dict], out_dir: Path, cols: int = 4, rows: int = 4,
            cell_w: int = 480) -> list[dict]:
    """Tile frames into cols x rows storyboard grids.

    Returns [{path, cols, rows, cells: [t,...]}] — cells listed in reading order
    (left→right, top→bottom) so the agent can map any thumbnail to its timestamp.
    """
    if not frames:
        return []
    _need_ffmpeg()
    out_dir.mkdir(parents=True, exist_ok=True)
    per = cols * rows
    boards: list[dict] = []
    for start in range(0, len(frames), per):
        chunk = frames[start:start + per]
        tmp = out_dir / f"_tile_{start}"
        tmp.mkdir(exist_ok=True)
        for j, fr in enumerate(chunk):
            shutil.copy(fr["path"], tmp / f"s{j:03d}.jpg")
        out_path = out_dir / f"storyboard_{len(boards):03d}.jpg"
        cmd = ["ffmpeg", "-y", "-i", str(tmp / "s%03d.jpg"),
               "-vf", f"scale={cell_w}:-1,tile={cols}x{rows}:padding=6:margin=6:color=0x1D222D",
               "-frames:v", "1", "-q:v", "3", str(out_path)]
        subprocess.run(cmd, capture_output=True, text=True)
        shutil.rmtree(tmp, ignore_errors=True)
        if out_path.exists():
            boards.append({"path": str(out_path), "cols": cols, "rows": rows,
                           "cells": [fr["t"] for fr in chunk]})
    return boards


# ---------------------------------------------------------------- OCR
def ocr(frames: list[dict], out_dir: Path, psm: int = 6, min_chars: int = 12
        ) -> tuple[dict, bool]:
    """Read on-screen text from each frame with tesseract. {t: text}, available?"""
    if not _has("tesseract"):
        return {}, False
    out_dir.mkdir(parents=True, exist_ok=True)
    results: dict[float, str] = {}
    for fr in frames:
        r = subprocess.run(["tesseract", fr["path"], "stdout", "--psm", str(psm)],
                           capture_output=True, text=True)
        txt = (r.stdout or "").strip()
        if len(txt) >= min_chars:
            results[fr["t"]] = txt
    if results:
        (out_dir / "ocr.jsonl").write_text(
            "\n".join(json.dumps({"t": k, "text": v}) for k, v in sorted(results.items())),
            encoding="utf-8",
        )
    return results, True


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("usage: frames.py <video-path>  (prints detected scene count)", file=sys.stderr)
        raise SystemExit(2)
    scenes = detect_scenes(sys.argv[1])
    print(f"{len(scenes)} scene changes; first few: {[fmt_ts(s) for s in scenes[:8]]}")
