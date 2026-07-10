# glideit

**Your coding agent can now watch long videos.**

Paste a YouTube link (or any video URL, or a local file) and ask a question. glideit downloads the video, builds a **transcript** and a **storyboard** of the whole thing, then extracts **high-res frames** of just the part that matters. Your agent reads them and answers — grounded in what is actually on screen.

![glideit demo](https://github.com/Imhari14/glideit/releases/download/v0.1.0/demo.gif)

- **No API keys. No cloud.** Everything runs locally: `ffmpeg`, `yt-dlp`, optional `tesseract`. The agent that invoked glideit does all the "seeing" — no model API is ever called.
- **Built for long videos.** A 1-hour lecture becomes 4 storyboard images + a transcript, not 450 frames flooding the agent's context.
- **Reads on-screen code.** High-res zoom frames + an OCR sidecar make IDE/terminal content legible.

## Install

**Claude Code:**

```
/plugin marketplace add Imhari14/glideit
/plugin install glideit@glideit
```

**Cursor, Codex, Copilot, Gemini CLI, and 70+ other agents:**

```bash
npx skills add Imhari14/glideit -g
```

**Requirements:** Python 3.10+, `ffmpeg`, `yt-dlp` (`pip install yt-dlp`). Run `python scripts/setup.py` to check. Optional: `tesseract` (OCR), `vosk` or `useful-moonshine-onnx` (free offline transcripts for videos without captions).

## Use

In your agent, just ask:

```
/glideit https://youtu.be/VIDEO_ID what happens at 12:30?
```

Or run the CLI directly:

```bash
# 1. MAP — whole-video transcript + storyboard grids
python scripts/glideit.py "https://youtu.be/VIDEO_ID"

# 2. ZOOM — dense high-res frames of one window (+ OCR of on-screen text)
python scripts/glideit.py "https://youtu.be/VIDEO_ID" --start 12:00 --end 13:30 --resolution 1024
```

The map prints paths to `transcript.txt` and `storyboard_*.jpg`; the zoom prints per-frame paths. The agent Reads those files and answers. Everything is cached under `.glideit/<hash>/` — re-runs are instant.

### Options

| Flag | What it does |
|---|---|
| `--start / --end / --timestamps` | zoom to a window or exact moments |
| `--fps 2` | denser sampling to catch fast motion (default ~1 frame/3s) |
| `--resolution 1024` | frame width — raise it to read on-screen code |
| `--detail fast\|balanced\|deep` | map density (`deep` also OCRs the map) |
| `--cards` | emit `cards.json` + a [HyperFrames](https://github.com/heygen-com/hyperframes) scaffold to recreate/remix the video |
| `--note "..."` | save a note to the video's persistent `notes.md` |
| `--refresh` | ignore cache and rebuild |

## MCP server

`mcp/server.py` exposes `map_video`, `zoom_video`, and `note_video` to any MCP host (`pip install mcp`):

```json
"glideit": { "command": "python", "args": ["mcp/server.py"] }
```

## Recreate or remix a video

`--cards` turns a reference video into an editable template: a structured `cards.json` (per-scene text, narration, timing) plus a starter [HyperFrames](https://github.com/heygen-com/hyperframes) composition. Change the content, brand, or language and render a new MP4 — then run glideit on the render to review it. The demo video above was made this way.

## How it compares

[claude-video](https://github.com/bradautomates/claude-video)'s `/watch` is great for short clips; glideit is built for the long ones — full lectures, tutorials, conference talks — plus OCR for on-screen code and the recreate/remix bridge.

## License

MIT
