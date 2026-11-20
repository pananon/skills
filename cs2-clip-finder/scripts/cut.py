#!/usr/bin/env python3
"""Stage 4: render the chosen clips with ffmpeg.

picks.json:
{
  "format": "vertical",            # vertical (9:16, blurred bg) | landscape | both
  "captions": true,                # burn word captions (needs transcribe.py output)
  "clips": [
    {"id": 3, "title": "bro whiffed the knife", "trim_start": -2, "trim_end": 1},
    {"start": 1520.0, "end": 1545.0, "title": "manual pick"}
  ]
}
trim_start/trim_end shift the candidate's edges in seconds (negative = earlier).

Usage: python cut.py <video>_clips/candidates.json picks.json [--encoder h264_nvenc]
"""
import argparse, json, os, re, subprocess

VERTICAL = ("[0:v]split[a][b];"
            "[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=25:2[bg];"
            "[b]scale=1080:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2")


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40] or "clip"


def srt_time(t):
    t = max(0.0, t)
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def write_srt(words, offset, length, path, per=3):
    """Short punchy captions: `per` words at a time, re-timed to the clip."""
    ws = [(s - offset, e - offset, w) for s, e, w in words if e - offset > 0 and s - offset < length]
    if not ws:
        return False
    with open(path, "w", encoding="utf-8") as f:
        for k in range(0, len(ws), per):
            grp = ws[k:k + per]
            f.write(f"{k // per + 1}\n{srt_time(grp[0][0])} --> {srt_time(min(grp[-1][1], length))}\n"
                    f"{' '.join(w for _, _, w in grp).upper()}\n\n")
    return True


def render(video, track, st, en, out_dir, name, fmt, srt, encoder):
    vf = VERTICAL if fmt == "vertical" else "[0:v]null"
    if srt:
        style = ("Fontname=Arial,Fontsize=20,Bold=1,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
                 "BorderStyle=1,Outline=3,Shadow=0,Alignment=2," + ("MarginV=70" if fmt == "vertical" else "MarginV=40"))
        vf += f",subtitles={os.path.basename(srt)}:force_style='{style}'"
    vf += "[v]"
    enc = ["-c:v", encoder] + (["-preset", "veryfast", "-crf", "20"] if encoder == "libx264" else ["-b:v", "12M"])
    out = f"{name}_{fmt}.mp4"
    cmd = ["ffmpeg", "-v", "error", "-y", "-ss", f"{st:.2f}", "-t", f"{en - st:.2f}", "-i", video,
           "-filter_complex", vf, "-map", "[v]", "-map", f"0:a:{track}",
           *enc, "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
           "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-movflags", "+faststart", out]
    subprocess.run(cmd, check=True, cwd=out_dir)  # cwd keeps the subtitles path simple on Windows
    return os.path.join(out_dir, out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("candidates")
    ap.add_argument("picks")
    ap.add_argument("--encoder", default="libx264", help="libx264 | h264_nvenc (NVIDIA) | h264_amf (AMD) | h264_qsv (Intel)")
    ap.add_argument("--mix-track", type=int, default=0, help="audio track for the output (0 = OBS mixed track)")
    a = ap.parse_args()
    data = json.load(open(a.candidates, encoding="utf-8"))
    picks = json.load(open(a.picks, encoding="utf-8"))
    by_id = {c["id"]: c for c in data["candidates"]}
    out_dir = os.path.join(os.path.dirname(os.path.abspath(a.candidates)), "renders")
    os.makedirs(out_dir, exist_ok=True)
    fmts = ["vertical", "landscape"] if picks.get("format") == "both" else [picks.get("format", "vertical")]
    made = []
    for n, p in enumerate(picks["clips"], 1):
        c = by_id.get(p.get("id"), {})
        st = float(p.get("start", c.get("start", 0))) + float(p.get("trim_start", 0))
        en = float(p.get("end", c.get("end", st + 20))) + float(p.get("trim_end", 0))
        st = max(0.0, st)
        name = f"{n:02d}_{slug(p.get('title') or c.get('rank', {}).get('title') or f'clip-{n}')}"
        srt = None
        if picks.get("captions", True) and c.get("words"):
            srt = os.path.join(out_dir, name + ".srt")
            if not write_srt(c["words"], st - c["start"], en - st, srt):
                srt = None
        for fmt in fmts:
            path = render(data["video"], a.mix_track, st, en, out_dir, name, fmt, srt, a.encoder)
            made.append(path)
            print(f"  ✓ {path}  ({en - st:.0f}s)")
    print(f"• {len(made)} file(s) in {out_dir}")


if __name__ == "__main__":
    main()
