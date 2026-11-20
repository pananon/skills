#!/usr/bin/env python3
"""One command: analyse → (transcribe) → rank → shortlist.md. All local, zero tokens.

Usage:
  python run.py "C:/Users/me/Videos/2026-11-20 21-04-33.mkv"
        [--mic-track 1] [--gsi events.jsonl] [--whisper small] [--llm qwen2.5:7b]
        [--no-transcribe] [--no-llm] [--top 25]

Stages that need something not installed (faster-whisper, Ollama) are skipped with a note.
"""
import argparse, importlib.util, os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))


def step(name, args):
    t = time.time()
    print(f"\n== {name} ==")
    r = subprocess.run([sys.executable, os.path.join(HERE, name)] + args)
    if r.returncode:
        sys.exit(f"{name} failed")
    print(f"   ({time.time() - t:.0f}s)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--mic-track", type=int)
    ap.add_argument("--gsi")
    ap.add_argument("--rec-start")
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--whisper", default="small")
    ap.add_argument("--lang")
    ap.add_argument("--llm", default="qwen2.5:7b")
    ap.add_argument("--no-transcribe", action="store_true")
    ap.add_argument("--no-llm", action="store_true")
    a = ap.parse_args()

    out = os.path.splitext(os.path.abspath(a.video))[0] + "_clips"
    cand = os.path.join(out, "candidates.json")
    args = [a.video, "--top", str(a.top)]
    if a.mic_track is not None: args += ["--mic-track", str(a.mic_track)]
    if a.gsi: args += ["--gsi", a.gsi]
    if a.rec_start: args += ["--rec-start", a.rec_start]
    step("analyze.py", args)

    if a.no_transcribe:
        pass
    elif importlib.util.find_spec("faster_whisper"):
        step("transcribe.py", [cand, "--model", a.whisper] + (["--lang", a.lang] if a.lang else []))
    else:
        print("\n(skip transcription: `pip install faster-whisper` to add transcripts + captions)")

    step("rank.py", [cand, "--model", a.llm] + (["--no-llm"] if a.no_llm else []))
    print(f"\nDone. Read {os.path.join(out, 'shortlist.md')}, write picks.json, then:\n"
          f'  python "{os.path.join(HERE, "cut.py")}" "{cand}" picks.json')


if __name__ == "__main__":
    main()
