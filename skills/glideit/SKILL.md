---
name: glideit
description: Watch a long video (URL or local path) and answer questions about it. Downloads with yt-dlp, builds a storyboard montage + transcript of the WHOLE video, then zooms into the relevant window with dense high-res frames and OCR of on-screen code. Use for lectures, tutorials, screencasts, conference talks, screen recordings — anything more than a couple of minutes. No external model is called: YOU read the frames.
---

# glideit — watch a long video

Give yourself eyes for a full-length video without drowning your context. Two
phases: **map** the whole video cheaply, then **zoom** into the part that matters.
Never try to Read every frame of a long video — map first, then zoom.

`$CLAUDE_PLUGIN_ROOT` is this plugin's directory. Use it so the script resolves
no matter the working directory. (Running standalone from the repo? Use
`scripts/glideit.py` instead.)

## Workflow

1. **Map the whole video.**
   ```bash
   python "$CLAUDE_PLUGIN_ROOT/scripts/glideit.py" "<url-or-path>"
   ```
   Prints a **transcript** path (`transcript.txt`) and one or more **storyboard
   montages** — grids of timestamp-labelled thumbnails spanning the whole runtime.
   **Read the transcript, then Read each `storyboard_*.jpg`.**

2. **Decide where to look.** From the transcript + storyboards, pick the window
   that answers the user's question (e.g. the code appears around 12:00–13:30).

3. **Zoom in.**
   ```bash
   python "$CLAUDE_PLUGIN_ROOT/scripts/glideit.py" "<url-or-path>" --start 12:00 --end 13:30 --resolution 1024
   ```
   Prints dense, high-res frame paths for that window plus OCR of any on-screen
   code (in `zoom_manifest.json`). **Read each frame.** For code, trust the OCR
   text for exact characters and the frame for layout.

4. **Answer** grounded in the frames and transcript you actually read.

## Flags
- `--detail fast|balanced|deep` — map density (`deep` also OCRs each map frame).
- `--start / --end` — zoom window (`SS`, `MM:SS`, or `HH:MM:SS`).
- `--timestamps 3:12,3:40` — exact moments instead of a window.
- `--fps F` — zoom sampling rate (frames/sec), e.g. `2` = every 0.5s. Overrides the
  default ~1 frame/3s to catch fast motion (demos, UI, gestures, a flashing error)
  in a short window — cheap because the window is already small.
- `--resolution N` — bump to 1024+ for legible on-screen code.
- `--budget N` — storyboard thumbnail count (default 64).
- `--no-ocr` — skip the OCR sidecar.
- `--cards` — emit `cards.json` (per-card text + narration + timing) and a
  `hyperframes_scaffold.html` starter, for recreating/remixing the video.
- `--note "..."` — append a note to this video's persistent `notes.md`, then exit.
- `--refresh` — ignore the cache and rebuild the map/zoom.

## Reuse — don't re-scan, don't re-read

The map and every zoom are cached under `.glideit/<hash>/`. Re-running the same
map or zoom returns instantly (`(cached ...)`) with no re-extraction — pass
`--refresh` only when you truly want to rebuild. To keep tokens low:
- Lean on the **transcript** (cheap text) first; Read frames only for visual
  detail the transcript can't provide.
- **Don't re-Read a storyboard or frame already in your context** this session.
- After you understand the video, **save a digest** with
  `python "$CLAUDE_PLUGIN_ROOT/scripts/glideit.py" "<url-or-path>" --note "..."`
  (one `--note` per point; appends to `<workdir>/notes.md`). Every later map/zoom
  prints `prior notes: …` — **Read that text first** and only re-read an image
  when you need a visual detail the notes don't already capture.

## Recreate or remix a video (with HyperFrames)

To rebuild a video as an editable template, run with `--cards`. It writes:
- `cards.json` — one entry per detected card: `timestamp`, `t_start`/`t_end`,
  on-screen text (OCR), the narration over it, and a reference frame.
- `hyperframes_scaffold.html` — a starter HyperFrames composition (one timed clip
  per card) to flesh out with the hyperframes skills, then `npx hyperframes render`.

Read `cards.json` + the reference frames, apply the user's changes (new content,
brand, language, layout), refine the scaffold, render, then run glideit on the
rendered MP4 to review your own output and iterate.

## Notes
- Everything runs locally (ffmpeg / yt-dlp / tesseract). No model API is called.
- Captions are used when present; install `faster-whisper` for caption-less/local
  videos. OCR needs `tesseract` on PATH (degrades gracefully if absent).
- The download, map, and zooms are all cached under `.glideit/<hash>/`.
- Run `python "$CLAUDE_PLUGIN_ROOT/scripts/setup.py"` once to verify local tools.
