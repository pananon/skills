# cs2-clip-finder

Turn a 40-60 minute OBS recording of a CS2 session into ready-to-post clips (funny moments, shouting,
hype, aces, clutches) **without sending the video to an AI**. Everything heavy runs locally and free;
Claude only reads a ~25-line shortlist and decides what to cut.

| Stage | Tool | Cost |
|---|---|---|
| Find moments | `analyze.py`: ffmpeg + numpy on the audio (shouts, laughter rhythm, screams, sustained hype) + optional CS2 game events | free, ~1 min for 50 min |
| What was said | `transcribe.py`: faster-whisper, **only on candidate windows** (~7 of 50 min) | free, local |
| Rank + title | `rank.py`: local LLM via Ollama (falls back to a heuristic) → `shortlist.md` | free, local |
| Pick | Claude reads `shortlist.md` | a few thousand tokens |
| Render | `cut.py`: ffmpeg, 9:16 with blurred background and/or 16:9, word captions, loudness normalised to -14 LUFS | free |

## Install (Windows, once)

```powershell
winget install Gyan.FFmpeg          # or any ffmpeg on PATH
pip install numpy
pip install faster-whisper          # optional: transcripts + captions
# optional local LLM: install Ollama from ollama.com, then
ollama pull qwen2.5:7b
```

Copy this folder into `%USERPROFILE%\.claude\skills\` and Claude Code will pick it up.

## Use

```powershell
# optional, before launching CS2 (needs templates\gamestate_integration_clipper.cfg in the CS2 cfg folder)
python scripts\gsi_server.py --out events.jsonl

# after the game
python scripts\run.py "C:\Users\me\Videos\2026-11-20 21-04-33.mkv" --mic-track 1 --gsi events.jsonl
```

Or just tell Claude Code: *"make clips from C:\Users\me\Videos\2026-11-20 21-04-33.mkv"*. The
skill runs the pipeline, reads the shortlist, writes `picks.json` and renders to `<video>_clips\renders\`.

See [SKILL.md](SKILL.md) for the OBS multitrack setup (the single biggest accuracy boost) and tuning.

## How the detectors work

- **Loudness vs baseline:** each second's peak level minus the rolling 30 s median. A quiet lobby and a loud
  lobby both work, because everything is relative to that recording.
- **Voice band:** share of energy in 250-3500 Hz. Voices are there, while gunfire is broadband and short.
- **Laughter:** ha-ha-ha pulses the loudness envelope at 3-7 Hz; we measure that modulation.
- **Scream / burst:** sudden jumps in level. **Hype:** loudness that stays high for 4+ s.
- **Game events (GSI):** CS2 pushes kills, headshots, multi-kills, aces, knife kills, deaths, round and bomb
  results to a local port. That's how Allstar-style tools know *what* happened, not just that it was loud.
