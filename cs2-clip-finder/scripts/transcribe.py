#!/usr/bin/env python3
"""Stage 2 (optional, local, free): transcribe ONLY the candidate windows.

Uses faster-whisper on your own CPU/GPU (pip install faster-whisper; the model
downloads once from Hugging Face, then works offline). A 50 min game with 25
candidates means ~7 min of audio to transcribe instead of 50.

Usage: python transcribe.py <video>_clips/candidates.json [--model small] [--lang en]
Adds "transcript" + "words" to every candidate in candidates.json.
"""
import argparse, json, os, subprocess, sys, tempfile

FUNNY = ["haha", "lol", "lmao", "bro", "what", "no way", "oh my god", "omg", "wtf", "how",
         "yes", "let's go", "lets go", "nice", "insane", "clutch", "ace", "noob", "sorry",
         "kya", "bhai", "arre", "abe", "yaar", "pagal"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("candidates")
    ap.add_argument("--model", default="small", help="tiny|base|small|medium|large-v3 (bigger = better, slower)")
    ap.add_argument("--lang", default=None, help="force language, e.g. en or hi (default: auto)")
    ap.add_argument("--device", default="auto", help="auto|cpu|cuda")
    a = ap.parse_args()
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        sys.exit("faster-whisper not installed: pip install faster-whisper   (skip this stage if you like)")

    data = json.load(open(a.candidates, encoding="utf-8"))
    video, track = data["video"], data["audio_track"]
    compute = "int8" if a.device == "cpu" else "default"
    model = WhisperModel(a.model, device=a.device, compute_type=compute)
    tmp = tempfile.mkdtemp()
    for c in data["candidates"]:
        wav = os.path.join(tmp, f"c{c['id']}.wav")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(c["start"]), "-t",
                        str(c["end"] - c["start"]), "-i", video, "-map", f"0:a:{track}",
                        "-ac", "1", "-ar", "16000", wav], check=True)
        segs, _ = model.transcribe(wav, language=a.lang, word_timestamps=True,
                                   vad_filter=True, condition_on_previous_text=False)
        text, words = [], []
        for s in segs:
            text.append(s.text.strip())
            for w in (s.words or []):
                words.append([round(w.start, 2), round(w.end, 2), w.word.strip()])
        c["transcript"] = " ".join(text)
        c["words"] = words
        low = c["transcript"].lower()
        c["hype_words"] = sorted({k for k in FUNNY if k in low})
        os.remove(wav)
        print(f"  #{c['id']:>2} {c['start']:>7.1f}s  {c['transcript'][:90]}")
    json.dump(data, open(a.candidates, "w", encoding="utf-8"), indent=1)
    print(f"• transcripts saved into {a.candidates}")


if __name__ == "__main__":
    main()
