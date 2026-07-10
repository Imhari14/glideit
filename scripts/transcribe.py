"""Transcript: native captions first (yt-dlp), local Whisper fallback.

External-free. Captions cover most public videos for free; faster-whisper (if
installed) handles caption-less or local files entirely on-device. No cloud ASR.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

_CUE = re.compile(r"(\d{2}:\d{2}:\d{2}[.,]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[.,]\d{3})")


def _has(name: str) -> bool:
    return shutil.which(name) is not None


def fmt_ts(seconds: float) -> str:
    t = int(round(seconds))
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def _to_seconds(stamp: str) -> float:
    stamp = stamp.replace(",", ".")
    hh, mm, ss = stamp.split(":")
    return int(hh) * 3600 + int(mm) * 60 + float(ss)


def parse_vtt(text: str) -> list[dict]:
    """Parse a WebVTT / SRT-ish caption file into [{start, end, text}]."""
    segs: list[dict] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        m = _CUE.search(lines[i])
        if not m:
            i += 1
            continue
        start, end = _to_seconds(m.group(1)), _to_seconds(m.group(2))
        i += 1
        buf = []
        while i < len(lines) and lines[i].strip() and not _CUE.search(lines[i]):
            buf.append(re.sub(r"<[^>]+>", "", lines[i]).strip())  # strip inline tags
            i += 1
        txt = " ".join(b for b in buf if b)
        if txt:
            segs.append({"start": start, "end": end, "text": txt})

    # collapse the rolling duplicates auto-captions emit
    out: list[dict] = []
    for s in segs:
        if out and s["text"] == out[-1]["text"]:
            out[-1]["end"] = s["end"]
            continue
        out.append(s)
    return out


def from_captions(source: str, work: Path, lang: str = "en") -> list[dict] | None:
    if not source.startswith("http") or not _has("yt-dlp"):
        return None
    cmd = [
        "yt-dlp", "--skip-download", "--write-subs", "--write-auto-subs",
        "--sub-langs", f"{lang}.*,{lang}", "--sub-format", "vtt",
        "-o", str(work / "caption"), source,
    ]
    subprocess.run(cmd, capture_output=True, text=True)
    vtts = sorted(work.glob("caption*.vtt"))
    if not vtts:
        return None
    segs = parse_vtt(vtts[0].read_text(encoding="utf-8", errors="ignore"))
    return segs or None


def _extract_audio(video_path: str, work: Path):
    """Pull a mono 16 kHz WAV once (shared by the local ASR engines)."""
    if not _has("ffmpeg"):
        return None
    audio = work / "audio.wav"
    if not audio.exists():
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(video_path), "-vn", "-ac", "1", "-ar", "16000", str(audio)],
            capture_output=True, text=True,
        )
    return audio if audio.exists() else None


def from_moonshine(video_path: str, work: Path, window: int = 25) -> list[dict] | None:
    """Free, on-device, no-key ASR via Moonshine ONNX — NOT Whisper.

    `pip install useful-moonshine-onnx`. Higher English accuracy than Vosk's small
    model, but built for short clips, so we split the audio into `window`-second
    chunks (fixed windows — a word may clip at a boundary). Models auto-download from
    HuggingFace on first use; set MOONSHINE_MODEL to override (moonshine/tiny|base).
    """
    try:
        import moonshine_onnx as _moon
    except ImportError:
        try:
            import moonshine as _moon
        except ImportError:
            return None
    import os
    audio = _extract_audio(video_path, work)
    if not audio:
        return None
    seg_dir = work / "moonshine_chunks"
    seg_dir.mkdir(exist_ok=True)
    for old in seg_dir.glob("chunk_*.wav"):
        old.unlink()
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(audio), "-f", "segment", "-segment_time", str(window),
         "-ar", "16000", "-ac", "1", str(seg_dir / "chunk_%03d.wav")],
        capture_output=True, text=True,
    )
    chunks = sorted(seg_dir.glob("chunk_*.wav"))
    if not chunks:
        return None
    model_name = os.environ.get("MOONSHINE_MODEL", "moonshine/base")
    segs: list[dict] = []
    for i, ch in enumerate(chunks):
        try:
            out = _moon.transcribe(str(ch), model_name)
        except Exception:
            continue
        text = (out[0] if isinstance(out, (list, tuple)) else str(out)).strip()
        if text:
            segs.append({"start": float(i * window), "end": float((i + 1) * window), "text": text})
    return segs or None


def from_vosk(video_path: str, work: Path) -> list[dict] | None:
    """Free, offline, no-key ASR via Vosk — NOT Whisper. `pip install vosk`.

    Auto-downloads a small English model on first use; set the VOSK_MODEL env var
    to a model directory for a larger or non-English one. Returns word-timed segments.
    """
    try:
        import json as _json
        import os
        import wave
        from vosk import KaldiRecognizer, Model
    except ImportError:
        return None
    audio = _extract_audio(video_path, work)
    if not audio:
        return None
    try:
        model_dir = os.environ.get("VOSK_MODEL")
        model = Model(model_dir) if model_dir else Model(lang="en-us")
    except Exception:
        return None

    wf = wave.open(str(audio), "rb")
    rec = KaldiRecognizer(model, wf.getframerate())
    rec.SetWords(True)
    segs: list[dict] = []

    def _flush(raw: str) -> None:
        r = _json.loads(raw)
        text = (r.get("text") or "").strip()
        if not text:
            return
        words = r.get("result") or []
        start = words[0]["start"] if words else (segs[-1]["end"] if segs else 0.0)
        end = words[-1]["end"] if words else start
        segs.append({"start": start, "end": end, "text": text})

    while True:
        chunk = wf.readframes(4000)
        if not chunk:
            break
        if rec.AcceptWaveform(chunk):
            _flush(rec.Result())
    _flush(rec.FinalResult())
    return segs or None


def from_whisper(video_path: str, work: Path, model_size: str = "base") -> list[dict] | None:
    """Free, offline, no-key ASR via faster-whisper (local Whisper — not the paid API)."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return None
    audio = _extract_audio(video_path, work)
    if not audio:
        return None
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, _ = model.transcribe(str(audio))
    return [{"start": s.start, "end": s.end, "text": s.text.strip()} for s in segments]


def get_transcript(source: str, video_path: str, work: Path, lang: str = "en") -> dict:
    """Write transcript.txt (+ .jsonl) and return {source, segments, path}."""
    segs = from_captions(source, work, lang)
    origin = "captions"
    if not segs:
        segs = from_moonshine(video_path, work)  # free, on-device, no key, not Whisper
        origin = "moonshine"
    if not segs:
        segs = from_vosk(video_path, work)  # free, offline, no key, not Whisper
        origin = "vosk"
    if not segs:
        segs = from_whisper(video_path, work)  # free local Whisper fallback
        origin = "whisper"
    if not segs:
        return {"source": "none", "segments": [], "path": None}

    txt_path = work / "transcript.txt"
    with txt_path.open("w", encoding="utf-8") as f:
        for s in segs:
            f.write(f"[{fmt_ts(s['start'])}] {s['text']}\n")
    (work / "transcript.jsonl").write_text(
        "\n".join(json.dumps(s) for s in segs), encoding="utf-8"
    )
    return {"source": origin, "segments": segs, "path": str(txt_path)}


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("usage: transcribe.py <source-url-or-tag> <video-path> [workdir]", file=sys.stderr)
        raise SystemExit(2)
    base = Path(sys.argv[3]) if len(sys.argv) > 3 else Path(".glideit").resolve()
    base.mkdir(parents=True, exist_ok=True)
    res = get_transcript(sys.argv[1], sys.argv[2], base)
    print(f"source={res['source']} segments={len(res['segments'])} path={res['path']}")
