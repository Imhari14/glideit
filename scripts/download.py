"""Resolve a video source (URL via yt-dlp, or local path) and probe its metadata.

External-free: shells out to yt-dlp and ffprobe only. Downloads are cached in a
per-source work dir so the map run and every zoom run reuse the same file.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

VIDEO_EXTS = (".mp4", ".mkv", ".webm", ".mov", ".m4v", ".avi")


def _has(name: str) -> bool:
    return shutil.which(name) is not None


def is_url(source: str) -> bool:
    return source.startswith("http://") or source.startswith("https://")


def workdir_for(source: str, base: Path) -> Path:
    """Deterministic work dir per source, so map/zoom runs share the download."""
    digest = hashlib.sha1(source.encode("utf-8")).hexdigest()[:12]
    d = base / digest
    d.mkdir(parents=True, exist_ok=True)
    return d


def probe(path: Path) -> dict:
    """Return duration/width/height/fps/has_audio via ffprobe."""
    if not _has("ffprobe"):
        raise SystemExit("ffprobe not found. Install ffmpeg — run: python scripts/setup.py")
    out = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        raise SystemExit(f"ffprobe failed: {out.stderr.strip()}")
    data = json.loads(out.stdout or "{}")
    streams = data.get("streams", [])
    fmt = data.get("format", {})
    v = next((s for s in streams if s.get("codec_type") == "video"), {})
    a = next((s for s in streams if s.get("codec_type") == "audio"), None)
    duration = float(fmt.get("duration") or v.get("duration") or 0)

    fps = 0.0
    rate = v.get("avg_frame_rate") or v.get("r_frame_rate") or "0/0"
    try:
        num, den = rate.split("/")
        fps = float(num) / float(den) if float(den) else 0.0
    except (ValueError, ZeroDivisionError):
        fps = 0.0

    return {
        "duration": duration,
        "width": v.get("width"),
        "height": v.get("height"),
        "fps": round(fps, 3),
        "has_audio": a is not None,
    }


def _cached_video(work: Path) -> Path | None:
    for p in sorted(work.glob("source.*")):
        if p.suffix.lower() in VIDEO_EXTS:
            return p
    return None


def resolve(source: str, work: Path) -> dict:
    """Return {path, title, is_url, duration, width, height, fps, has_audio}.

    URLs are downloaded once into `work` and reused on subsequent calls.
    """
    if is_url(source):
        if not _has("yt-dlp"):
            raise SystemExit("yt-dlp not found. Run: pip install yt-dlp")
        path = _cached_video(work)
        title = source
        info_path = work / "info.json"
        if path is None:
            cmd = [
                "yt-dlp", "-f", "best[ext=mp4]/best", "--no-playlist",
                "-N", "4", "--no-progress",
                "--write-info-json", "-o", str(work / "source.%(ext)s"), source,
            ]
            r = subprocess.run(cmd, capture_output=True, text=True)
            if r.returncode != 0:
                raise SystemExit(f"yt-dlp failed: {r.stderr.strip()[:400]}")
            path = _cached_video(work)
        if path is None:
            raise SystemExit("Download produced no video file.")
        if info_path.exists():
            try:
                title = json.loads(info_path.read_text(encoding="utf-8")).get("title", source)
            except (ValueError, OSError):
                pass
    else:
        path = Path(source)
        if not path.exists():
            raise SystemExit(f"File not found: {source}")
        title = path.name

    return {"path": str(path), "title": title, "is_url": is_url(source), **probe(path)}


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("usage: download.py <url-or-path> [workdir]", file=sys.stderr)
        raise SystemExit(2)
    base = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(".glideit").resolve()
    w = workdir_for(sys.argv[1], base)
    print(json.dumps(resolve(sys.argv[1], w), indent=2))
