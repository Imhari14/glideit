---
name: glideit
description: Watch a long video (URL or path) — map it, then zoom into what matters.
---

The user wants you to watch a video: **$ARGUMENTS**

Treat the first token of `$ARGUMENTS` as the video URL or file path. Any remaining
text is what the user wants to know — keep it in mind when choosing where to zoom,
but do NOT pass it to the script.

Follow this loop (the script only runs ffmpeg/yt-dlp locally and prints paths —
you are the one who watches):

1. **Map** the whole video:
   ```bash
   python "$CLAUDE_PLUGIN_ROOT/scripts/glideit.py" "<video-url-or-path>"
   ```
2. **Read** the printed `transcript.txt` and every `storyboard_*.jpg`.
3. **Zoom** into the window that answers the user, at high resolution:
   ```bash
   python "$CLAUDE_PLUGIN_ROOT/scripts/glideit.py" "<video-url-or-path>" --start MM:SS --end MM:SS --resolution 1024
   ```
4. **Read** the zoom frames (and `zoom_manifest.json` for OCR of on-screen code),
   then answer the user's question grounded in what you actually saw.

If the user only wants a quick overview, the map alone may be enough. If they name
a moment ("around 12:30"), zoom straight to it with `--start/--end` or
`--timestamps`.
