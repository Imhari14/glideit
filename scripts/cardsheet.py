"""Build a structured 'card sheet' (cards.json) + a HyperFrames HTML scaffold from a
mapped video — the handoff for recreating or remixing a video with HyperFrames.

External-free: pure stdlib. Consumes glideit's own frames + OCR + transcript. glideit
never runs HyperFrames; it just emits input the agent hands off to `npx hyperframes`.
"""
from __future__ import annotations

import html
import json
from pathlib import Path


def _fmt(seconds: float) -> str:
    t = int(round(seconds))
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def build_cards(thumbs: list[dict], ocr_map: dict, transcript_segments: list[dict],
                duration: float) -> list[dict]:
    """One card per storyboard thumbnail; each card spans until the next thumbnail.

    thumbs: [{t, path}] in time order · ocr_map: {t(float): text} · transcript_segments:
    [{start, end, text}]. Narration = transcript segments whose midpoint lands in the span.
    """
    cards: list[dict] = []
    for i, fr in enumerate(thumbs):
        t0 = float(fr["t"])
        t1 = float(thumbs[i + 1]["t"]) if i + 1 < len(thumbs) else float(duration or t0)
        if t1 <= t0:
            t1 = t0 + 1.0
        narration = " ".join(
            (seg.get("text") or "").strip()
            for seg in transcript_segments
            if t0 <= (seg.get("start", 0) + seg.get("end", 0)) / 2 < t1
        ).strip()
        cards.append({
            "index": i,
            "t_start": round(t0, 2),
            "t_end": round(t1, 2),
            "duration": round(t1 - t0, 2),
            "timestamp": _fmt(t0),
            "frame": fr["path"],
            "ocr_text": (ocr_map.get(t0) or ocr_map.get(round(t0, 2)) or "").strip(),
            "narration": narration,
        })
    return cards


def write_cards_json(cards: list[dict], meta: dict, out_path: Path) -> Path:
    payload = {
        "source": meta.get("source"),
        "title": meta.get("title"),
        "duration_seconds": meta.get("duration"),
        "count": len(cards),
        "cards": cards,
    }
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out_path


def write_hyperframes_scaffold(cards: list[dict], meta: dict, out_path: Path,
                               width: int = 1920, height: int = 1080, fps: int = 30) -> Path:
    """Emit a starter HyperFrames composition (HTML): one timed clip per card.

    A STARTER, not a final render — flesh out layout/animation with the hyperframes
    skills, and confirm the exact data-* contract + timing units there.
    """
    def esc(x: str) -> str:
        return html.escape(x or "")

    clips = []
    for c in cards:
        first_line = next((ln for ln in (c["ocr_text"] or "").splitlines() if ln.strip()), "")
        clips.append(
            f'  <!-- card {c["index"]} @ {c["timestamp"]}  (ref frame: {c["frame"]})\n'
            f'       narration: {esc(c["narration"])[:240]} -->\n'
            f'  <div class="clip" data-start="{c["t_start"]}" data-duration="{c["duration"]}"'
            f' data-track-index="0">\n'
            f'    <h1>{esc(first_line[:90])}</h1>\n'
            f'    <pre class="card-text">{esc(c["ocr_text"])}</pre>\n'
            f'  </div>'
        )

    doc = f"""<!doctype html>
<!-- glideit -> HyperFrames scaffold.  Source: {esc(str(meta.get("source")))}
     STARTER composition: one clip per detected card, timing from glideit's scene
     detection, text from OCR, narration in comments. Flesh out layout + animation with
     the hyperframes skills (/hyperframes-core, /hyperframes-animation). NOTE: data-start /
     data-duration here are in SECONDS from the source video; confirm HyperFrames' expected
     units and the required data-* attributes with /hyperframes-core before rendering. -->
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ margin: 0; }}
  #root {{ width: {width}px; height: {height}px; position: relative; background: #0f121a;
           font-family: system-ui, -apple-system, sans-serif; color: #eef1f6; }}
  .clip {{ position: absolute; inset: 0; padding: 80px; box-sizing: border-box; }}
  h1 {{ font-size: 64px; margin: 0 0 28px; }}
  .card-text {{ font-size: 30px; line-height: 1.4; white-space: pre-wrap; font-family: inherit; }}
</style>
</head>
<body>
<div id="root" data-composition-id="glideit-recreation" data-width="{width}" data-height="{height}" data-fps="{fps}">
{chr(10).join(clips)}
</div>
</body>
</html>
"""
    out_path.write_text(doc, encoding="utf-8")
    return out_path
