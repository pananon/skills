---
name: cs2-clip-finder
description: Find and cut publishable clips (funny moments, shouting, hype, clutches, aces, fails) from a long CS2 / Counter-Strike 2 gameplay recording (OBS screen recording, 30-60+ min, with voice chat audio) cheaply. Local ffmpeg + numpy audio analysis, optional local Whisper transcription, optional local LLM (Ollama) ranking and optional CS2 Game State Integration events do the heavy lifting; Claude only reads a few-KB shortlist and then renders vertical/landscape clips with captions. Use when the user gives a path to a gameplay recording and asks for clips, highlights, shorts, reels or "the funny parts".
---

# CS2 clip finder

The goal is good clips at **minimal token cost**. The video never enters the context: local
tools turn 50 minutes of footage into a shortlist of about 25 lines, and Claude decides from that.

```
recording.mkv ─► analyze.py (ffmpeg+numpy: shouts, laughter, screams, loudness, GSI kills)   0 tokens
             ─► transcribe.py (faster-whisper, candidate windows only)                       0 tokens
             ─► rank.py (Ollama local LLM or heuristic) ─► shortlist.md (~3-5 KB)            0 tokens
             ─► Claude reads shortlist.md, writes picks.json                                 ~2-4k tokens
             ─► cut.py (ffmpeg: 9:16 blurred-bg, captions, loudness-normalised)             0 tokens
```

Scripts are in `scripts/` next to this file. Every script runs on Python 3.9+ with `numpy`, and needs
`ffmpeg`/`ffprobe` on PATH.

## Rules that keep it cheap

- **Never** read the video, extract many frames, or read `candidates.json` whole. Read `shortlist.md` only.
- Only if two candidates are truly ambiguous may you look at **one** thumbnail each
  (`ffmpeg -ss <peak> -i video -frames:v 1 -vf scale=480:-1 thumb.jpg`). Never more than 4 in a run.
- Don't print long command output. Pass `> log.txt` if a script is chatty and read only the tail.

## Workflow

1. **Check the setup once** (silently fix what's missing, tell the user only what needs them):
   `ffmpeg -version`, `python -c "import numpy"`. Optional extras:
   `python -c "import faster_whisper"` (transcripts + captions) and
   `curl -s http://127.0.0.1:11434/api/tags` (Ollama, local LLM ranking).
   If those are missing, run anyway: the pipeline degrades gracefully.
2. **Ask nothing you can detect.** Check audio tracks with
   `ffprobe -v error -select_streams a -show_entries stream=index:stream_tags=title -of csv=p=0 "<video>"`.
   If there are 2+ tracks, the mic/voice-only track is usually index 1 (OBS Track 2), so pass `--mic-track 1`.
   If a `events.jsonl` from `gsi_server.py` sits next to the video or in the scripts folder, pass `--gsi`.
3. **Run the pipeline:**
   `python scripts/run.py "<video>" [--mic-track 1] [--gsi events.jsonl] [--lang en|hi]`.
   Output goes to `<video name>_clips/`. A 50-minute file takes about 1 min for analysis, plus a few minutes
   for Whisper on CPU.
4. **Read `<video>_clips/shortlist.md`** and choose clips. Good short-form clips:
   - start 2-4 s **before** the action (setup), end 1-3 s after the reaction dies down. Use `trim_start` / `trim_end`.
   - 10-40 s long; under 60 s always.
   - transcript with a punchline, laughter, disbelief ("no way", "bro", "kya"), a clear game event (ace, clutch, knife kill), or a big shout.
   - skip `none` category with no tags, unless the transcript is funny.
   - default 5-8 picks per game unless the user asked otherwise. Give each a short, catchy title.
5. **Write `picks.json`** in the `_clips` folder (format in `scripts/cut.py` docstring), then run
   `python scripts/cut.py "<video>_clips/candidates.json" "<video>_clips/picks.json" [--encoder h264_nvenc]`.
   Use `--encoder h264_nvenc` (NVIDIA), `h264_amf` (AMD) or `h264_qsv` (Intel) if available. It's much faster.
6. **Report:** a table of rendered clips (file, length, why it's good, suggested caption/title). Offer to
   re-cut any clip with different edges or to render landscape too.

## Tuning

- Too many quiet / boring candidates → the user's lobby is loud all game; use `--mic-track` or raise
  `--top` and rely on the ranking. Too few → `--top 40`.
- Reactions cut off → `analyze.py --post 10`. Missing the setup → `--pre 15`.
- Hindi / Hinglish voice chat → `--lang hi` (or leave auto). Whisper `--whisper medium` is more accurate on GPU.
- Better local LLM ranking: `ollama pull qwen2.5:7b` (default) or any instruct model via `--llm`.

## User-side setup (tell the user once, only if they don't have it yet)

- **OBS multitrack audio (biggest accuracy win):** Settings → Output → (Advanced) → Recording → tick Audio
  Track 1 and 2. Replace "Desktop Audio" with two **Application Audio Capture** sources, one for `cs2.exe` and
  one for `Discord.exe`. In Edit → Advanced Audio Properties set: CS2 → track 1 only; Discord + Mic → tracks
  1 **and** 2. Track 1 is the normal mix used in the clips; track 2 is pure voices (`--mic-track 1`), so
  gunfire no longer confuses the shout and laughter detectors. (If the squad uses in-game voice instead of
  Discord, the voices sit in the game audio; then only your mic goes on track 2.)
  Record as `.mkv` (safe if the game crashes) and keep OBS's default date-time filename.
- **Game events (what Allstar-style tools use):** copy `templates/gamestate_integration_clipper.cfg` into
  `Steam\steamapps\common\Counter-Strike Global Offensive\game\csgo\cfg\` and run
  `python scripts/gsi_server.py --out events.jsonl` before playing. This is Valve's official GSI, with no VAC risk.
  Kills, headshots, 3k/4k, aces, knife kills, deaths and rounds get exact timestamps, aligned with the
  OBS filename's start time (or `--rec-start "YYYY-MM-DD HH:MM:SS"`).
