#!/usr/bin/env python3
"""glideit — let a coding agent watch long videos via coarse-to-fine navigation.

External-free. This script only runs ffmpeg / yt-dlp / tesseract locally and
prints paths. It never calls a model — the agent that invoked it Reads the
storyboards and frames and does all the understanding.

    MAP:   python glideit.py "<url-or-path>"
    ZOOM:  python glideit.py "<url-or-path>" --start 3:00 --end 4:30 --resolution 1024
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import download  # noqa: E402
import transcribe  # noqa: E402
import frames as F  # noqa: E402

SCENE_THRESHOLD = {"fast": 0.4, "balanced": 0.3, "deep": 0.2}
ZOOM_FPS_CAP = 300  # safety ceiling on frame count when --fps is set


def parse_time(value: str | None) -> float | None:
    if value is None:
        return None
    value = str(value).strip()
    if not value:
        return None
    parts = value.split(":")
    try:
        if len(parts) == 1:
            return float(parts[0])
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    except ValueError:
        pass
    raise SystemExit(f"Cannot parse time: {value!r} (use SS, MM:SS, or HH:MM:SS)")


def _ensure_transcript(source: str, video_path: str, work: Path) -> dict:
    txt = work / "transcript.txt"
    if txt.exists():
        return {"source": "cache", "path": str(txt)}
    return transcribe.get_transcript(source, video_path, work)


def _load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None


def _append_note(work: Path, text: str) -> None:
    """Append a note to this video's persistent notes.md (cheap text memory)."""
    work.mkdir(parents=True, exist_ok=True)
    path = work / "notes.md"
    if not path.exists():
        path.write_text("# glideit notes\n\n", encoding="utf-8")
    with path.open("a", encoding="utf-8") as f:
        f.write(f"- {text.strip()}\n")
    print(f"noted -> {path}")


def _zoom_sig(args, resolution: int) -> str:
    base = args.timestamps if args.timestamps else f"{args.start}-{args.end}"
    fps = args.fps if args.fps else "auto"
    return re.sub(r"[^A-Za-z0-9]+", "_", f"{base}_r{resolution}_f{fps}").strip("_")


def run_zoom(args, src, work: Path) -> dict:
    duration = src["duration"]
    resolution = args.resolution or 1024
    sig = _zoom_sig(args, resolution)
    zdir = work / "zoom" / sig
    zmanifest = zdir / "manifest.json"
    if zmanifest.exists() and not args.refresh:
        cached = _load_json(zmanifest)
        if cached and all(Path(f["path"]).exists() for f in cached.get("frames", [])):
            print("(cached zoom — pass --refresh to rebuild)")
            ocr_map = {float(k): v for k, v in cached.get("ocr", {}).items()}
            _report_zoom(cached, ocr_map)
            return cached
    zdir.mkdir(parents=True, exist_ok=True)

    if args.timestamps:
        ts = [parse_time(x) for x in args.timestamps.split(",")]
    else:
        start = parse_time(args.start) or 0.0
        end = parse_time(args.end) or min(duration, start + 60)
        span = max(0.0, end - start)
        if args.fps and args.fps > 0:  # explicit density — dense sampling for fast events
            step = 1.0 / args.fps
            n = int(span / step) + 1
            if n > ZOOM_FPS_CAP:
                print(f"WARNING: --fps {args.fps} over {span:.0f}s = {n} frames; "
                      f"capping at {ZOOM_FPS_CAP} (narrow the window or lower --fps)")
                n = ZOOM_FPS_CAP
            ts = [round(start + i * step, 2) for i in range(max(1, n))]
        else:
            count = max(4, min(40, int(span / 3)))  # default ~1 frame / 3s, capped
            ts = [round(start + span * i / max(1, count - 1), 2) for i in range(count)]

    precise = bool(args.fps and args.fps >= 1)  # sub-second labels for dense sampling
    frames = F.extract_at(src["path"], ts, zdir, resolution=resolution,
                          label=True, precise_label=precise)
    frames, dropped = F.dedup(frames, threshold=2.0)
    ocr_map: dict = {}
    if not args.no_ocr:
        ocr_map, _ = F.ocr(frames, zdir)

    manifest = {
        "mode": "zoom",
        "source": args.source,
        "title": src["title"],
        "window": {"start": args.start, "end": args.end, "timestamps": args.timestamps},
        "resolution": resolution,
        "fps": args.fps,
        "frames": frames,
        "dropped_dupes": dropped,
        "ocr": {str(k): v for k, v in ocr_map.items()},
        "transcript_path": str(work / "transcript.txt") if (work / "transcript.txt").exists() else None,
        "manifest_path": str(zmanifest),
        "workdir": str(work),
    }
    zmanifest.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    _report_zoom(manifest, ocr_map)
    return manifest


def run_map(args, src, work: Path) -> dict:
    manifest_path = work / "manifest.json"
    if manifest_path.exists() and not args.refresh:
        cached = _load_json(manifest_path)
        if (cached and cached.get("detail") == args.detail
                and cached.get("budget") == args.budget and cached.get("grid") == args.grid
                and all(Path(b["path"]).exists() for b in cached.get("storyboards", []))):
            print("(cached map — pass --refresh to rebuild)")
            _report_map(cached)
            return cached
    duration = src["duration"]
    resolution = args.resolution or 512
    mdir = work / "map"
    mdir.mkdir(exist_ok=True)
    cols, rows = (int(x) for x in args.grid.lower().split("x"))

    scenes = [] if args.detail == "fast" else F.detect_scenes(
        src["path"], threshold=SCENE_THRESHOLD[args.detail])
    ts = F.pick_storyboard_timestamps(duration, scenes, budget=args.budget)
    thumbs = F.extract_at(src["path"], ts, mdir, resolution=resolution, label=True)
    thumbs, dropped = F.dedup(thumbs, threshold=1.5)
    boards = F.montage(thumbs, mdir, cols=cols, rows=rows)

    ocr_map: dict = {}
    if args.detail == "deep" and not args.no_ocr:
        ocr_map, _ = F.ocr(thumbs, mdir)

    tr = _ensure_transcript(args.source, src["path"], work)
    manifest = {
        "mode": "map",
        "source": args.source,
        "title": src["title"],
        "duration_seconds": round(duration, 1),
        "width": src["width"],
        "height": src["height"],
        "detail": args.detail,
        "budget": args.budget,
        "grid": args.grid,
        "transcript": {"source": tr.get("source"), "path": tr.get("path")},
        "storyboards": boards,
        "scene_changes": len(scenes),
        "thumbs": len(thumbs),
        "dropped_dupes": dropped,
        "ocr": {str(k): v for k, v in ocr_map.items()},
        "workdir": str(work),
    }
    (work / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    _report_map(manifest)
    return manifest


def _report_map(m: dict) -> None:
    print("\n=== glideit MAP ===")
    print(f"title      : {m['title']}")
    print(f"duration   : {F.fmt_ts(m['duration_seconds'])}   ({m['width']}x{m['height']})   detail={m['detail']}")
    tr = m["transcript"]
    print(f"transcript : {tr['path'] or '(none — no captions and no local whisper installed)'}  [{tr['source']}]")
    print(f"storyboard : {len(m['storyboards'])} montage(s), {m['thumbs']} thumbs, "
          f"{m['scene_changes']} scene changes, {m['dropped_dupes']} dupes dropped")
    for b in m["storyboards"]:
        cells = ", ".join(F.fmt_ts(c) for c in b["cells"])
        print(f"  - {b['path']}  [{b['cols']}x{b['rows']}] cells L-R,T-B: {cells}")
    notes = Path(m["workdir"]) / "notes.md"
    if notes.exists():
        print(f"prior notes: {notes}  (Read this first — your saved text memory of this video)")
    print("\nNEXT (agent): Read the transcript, then Read each storyboard image above")
    print("(skip any already in your context — re-running this map reuses the cache, no re-scan).")
    print("Find the window that answers the question, then zoom:")
    print(f'  python scripts/glideit.py "{m["source"]}" --start MM:SS --end MM:SS --resolution 1024')
    print(f'Save what you learn so next time is cheap:  ... "{m["source"]}" --note "..."')
    print(f"workdir    : {m['workdir']}")


def _report_zoom(m: dict, ocr_map: dict) -> None:
    print("\n=== glideit ZOOM ===")
    w = m["window"]
    scope = w["timestamps"] or f"{w['start']} -> {w['end']}"
    print(f"window : {scope}   res={m['resolution']}   fps={m.get('fps') or 'auto (~1/3s)'}")
    print(f"frames : {len(m['frames'])}  ({m['dropped_dupes']} dupes dropped)"
          f"{'' if ocr_map else '   (no OCR — tesseract not installed or --no-ocr)'}")
    fine = bool(m.get("fps") and m["fps"] >= 1)
    for fr in m["frames"]:
        line = f"  t={(F.fmt_ts_fine if fine else F.fmt_ts)(fr['t'])}  {fr['path']}"
        if fr["t"] in ocr_map:
            snippet = ocr_map[fr["t"]].replace("\n", " ")[:64]
            line += f"   ocr: {snippet}..."
        print(line)
    print(f"\nNEXT (agent): Read each frame path above. Full OCR text: {m.get('manifest_path', 'zoom manifest')}")
    notes = Path(m["workdir"]) / "notes.md"
    if notes.exists():
        print(f"prior notes: {notes}")
    print(f"workdir : {m['workdir']}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="glideit", description="Long-video vision for coding agents (external-free).")
    p.add_argument("source", help="video URL (yt-dlp supported) or local file path")
    p.add_argument("--detail", choices=["fast", "balanced", "deep"], default="balanced",
                   help="map density (default: balanced; deep also OCRs the map)")
    p.add_argument("--start", help="zoom window start (SS | MM:SS | HH:MM:SS)")
    p.add_argument("--end", help="zoom window end")
    p.add_argument("--timestamps", help="comma-separated exact moments, e.g. 3:12,3:40")
    p.add_argument("--fps", type=float,
                   help="zoom sampling rate (frames/sec), e.g. 2 = every 0.5s; overrides "
                        "the default ~1 frame/3s to catch fast motion in a short window")
    p.add_argument("--resolution", type=int, default=None,
                   help="frame width in px (default 512 map / 1024 zoom)")
    p.add_argument("--budget", type=int, default=64, help="storyboard thumbnail count (map)")
    p.add_argument("--grid", default="4x4", help="montage grid, e.g. 4x4")
    p.add_argument("--no-ocr", action="store_true", help="skip the OCR sidecar")
    p.add_argument("--refresh", action="store_true", help="ignore cache and rebuild map/zoom")
    p.add_argument("--note", help="append a note to this video's notes.md and exit (persistent memory)")
    p.add_argument("--out", default=".glideit", help="base work directory")
    p.add_argument("--json", action="store_true", help="also print the manifest as JSON")
    return p


def main() -> None:
    for stream in (sys.stdout, sys.stderr):  # tolerate Unicode titles/OCR on cp1252
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args()
    base = Path(args.out).resolve()
    work = download.workdir_for(args.source, base)

    if args.note is not None:  # persistent-memory write; no download needed
        _append_note(work, args.note)
        return

    src = download.resolve(args.source, work)

    is_zoom = any([args.start, args.end, args.timestamps])
    manifest = run_zoom(args, src, work) if is_zoom else run_map(args, src, work)

    if args.json:
        print("\n" + json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
