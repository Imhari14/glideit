# glideit

**Long-video vision for coding agents.** Lets Claude Code, Cursor, Codex — any
agent — actually watch a full-length video: it navigates coarse-to-fine so the
detail lands without flooding the agent's context.

External-free by design: `glideit` only runs `ffmpeg` / `yt-dlp` / `tesseract`
locally and prints paths. **No model is called** — the agent that invoked it
Reads the frames and does all the understanding, exactly like claude-video's
`/watch`. The difference is the specialty: **long videos and on-screen code.**

## How it works

1. **Map** — one cheap pass over the whole video produces a timestamped
   **transcript** and **storyboard montages** (grids of labelled thumbnails
   covering the entire runtime). The agent Reads these to understand the shape of
   the video for the token cost of a handful of images.
2. **Zoom** — the agent picks the window that matters and asks for dense,
   high-res frames of just that span, plus **OCR** of any on-screen code.

```
you paste a 1-hour lecture
  → map:  transcript + 4 storyboard grids               (whole video, one glance)
  → agent reads them, spots the relevant 90 seconds
  → zoom: 20 hi-res frames + OCR of that window          (the part that matters)
  → agent answers, grounded in what it actually saw
```

## Install

```bash
python scripts/setup.py          # check ffmpeg / ffprobe / yt-dlp (+ optional tools)
pip install -r requirements.txt  # yt-dlp (and optionally faster-whisper, mcp)
```

System binaries (install once): **ffmpeg** (required), **tesseract** (optional,
for the OCR sidecar). `setup.py` prints the exact command for your OS.

## Use it directly

```bash
# Map the whole video
python scripts/glideit.py "https://youtu.be/<id>"

# Zoom a window in high resolution (download is cached from the map run)
python scripts/glideit.py "https://youtu.be/<id>" --start 12:00 --end 13:30 --resolution 1024

# Local file, exact moments
python scripts/glideit.py "lecture.mp4" --timestamps 3:12,3:40 --resolution 1024
```

Flags: `--detail fast|balanced|deep`, `--start/--end`, `--timestamps`,
`--resolution`, `--budget`, `--grid`, `--no-ocr`, `--json`. See
[`SKILL.md`](SKILL.md) for the full agent workflow.

## Install

**Claude Code** (plugin: skill + `/glideit` command + bundled MCP server):

```bash
/plugin marketplace add Imhari14/glideit
/plugin install glideit@glideit
```

**Cursor, Codex, Copilot, Gemini CLI, and 70+ other agents** (Agent Skill):

```bash
npx skills add Imhari14/glideit -g
```

**From a local clone** (testing):

```bash
claude plugin marketplace add ./glideit
claude plugin install glideit@glideit
claude plugin list          # verify, then /reload-plugins in your session
```

Then, hands-free, either:

```
/glideit https://youtu.be/<id> what does the groupby example do?
```

or just ask ("watch this lecture and summarize the pandas section") — the `scan`
skill auto-invokes. The bundled MCP server also exposes `map_video` / `zoom_video` / `note_video`
to any MCP host (needs `pip install mcp`).

To try it in one session without installing: `claude --plugin-dir ./glideit`.

## Layout (Claude Code plugin)

```
.claude-plugin/
  plugin.json          plugin manifest (references .mcp.json)
  marketplace.json     local marketplace entry (source: "./")
commands/glideit.md    /glideit slash command
skills/glideit/
  SKILL.md             the map -> zoom agent workflow (auto-invocable)
.mcp.json              registers the bundled MCP server
mcp/server.py          MCP wrapper: map_video / zoom_video / note_video
scripts/
  glideit.py           entry point: map + zoom
  download.py          yt-dlp resolve + ffprobe metadata (cached per source)
  transcribe.py        captions-first, local whisper fallback
  frames.py            scene detection · dedup · tile-montage · OCR
  cardsheet.py         cards.json + HyperFrames scaffold (--cards)
  setup.py             preflight tool check
```

Everything runs on-device; nothing leaves the machine except the original video
download. Work is cached under `.glideit/<hash>/`.

## Recreate or remix a video (with HyperFrames)

`glideit "<url>" --cards` turns any reference video into an **editable template**.
It writes a structured `cards.json` (per-card on-screen text, narration, and timing)
plus a `hyperframes_scaffold.html` starter composition. Hand those to
[HyperFrames](https://github.com/heygen-com/hyperframes) (HTML → MP4, built for
agents): flesh out the scaffold, change the content / brand / language / layout, and
`npx hyperframes render`. Then run glideit on the rendered MP4 to review it.

glideit is the **eyes** (watch + review); HyperFrames is the **hands** (render).

## Status

Runnable end-to-end. MIT.
