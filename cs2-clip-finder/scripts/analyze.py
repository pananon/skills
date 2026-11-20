#!/usr/bin/env python3
"""Stage 1: find candidate moments in a long CS2 recording using audio only.

No AI, no tokens. ffmpeg decodes the audio to 16 kHz mono and numpy scores it:
  * loud   - how far above the rolling 30 s baseline the level is (shouting, hype)
  * voice  - share of energy in the human-voice band (separates voices from gunfire)
  * laugh  - rhythmic 3-7 Hz pulsing of the loudness envelope (ha-ha-ha pattern)
  * burst  - sudden jump in level (a scream right after a kill)
  * game   - optional kill/death/round events logged by gsi_server.py

Usage:
  python analyze.py "C:/Users/me/Videos/2026-11-20 21-04-33.mkv" [--mic-track 1]
        [--gsi events.jsonl] [--rec-start "2026-11-20 21:04:33"] [--top 25]

Writes <video>_clips/candidates.json and prints a summary.
"""
import argparse, datetime as dt, json, os, re, subprocess, sys
import numpy as np

SR = 16000
HOP = 320            # 20 ms frames, 50 per second
FPS = SR // HOP


def ffprobe_duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nw=1:nk=1", path], capture_output=True, text=True)
    try:
        return float(out.stdout.strip())
    except ValueError:
        return None


def audio_tracks(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a",
                          "-show_entries", "stream=index", "-of", "csv=p=0", path],
                         capture_output=True, text=True)
    return len([l for l in out.stdout.split() if l.strip()])


def frame_features(path, track):
    """Stream the audio through ffmpeg and compute per-20 ms features."""
    cmd = ["ffmpeg", "-v", "error", "-i", path, "-map", f"0:a:{track}", "-vn",
           "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    db, voice, flux = [], [], []
    freqs = np.fft.rfftfreq(HOP * 2, 1 / SR)
    vband = (freqs >= 250) & (freqs <= 3500)
    win = np.hanning(HOP * 2).astype(np.float32)
    prev_spec = None
    carry = np.zeros(0, dtype=np.float32)
    chunk_bytes = SR * 2 * 30  # 30 s at a time keeps memory flat for 1 h files
    while True:
        raw = proc.stdout.read(chunk_bytes)
        if not raw:
            break
        x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        x = np.concatenate([carry, x])
        n = (len(x) - HOP) // HOP
        if n <= 0:
            carry = x
            continue
        idx = np.arange(n)[:, None] * HOP + np.arange(HOP * 2)[None, :]
        frames = x[idx] * win
        carry = x[n * HOP:]
        rms = np.sqrt(np.mean(frames ** 2, axis=1) + 1e-10)
        db.append(20 * np.log10(rms + 1e-9))
        spec = np.abs(np.fft.rfft(frames, axis=1)) + 1e-9
        voice.append(spec[:, vband].sum(1) / spec.sum(1))
        if prev_spec is not None:
            spec_prev = np.vstack([prev_spec[None, :], spec[:-1]])
        else:
            spec_prev = np.vstack([spec[:1], spec[:-1]])
        flux.append(np.maximum(spec - spec_prev, 0).sum(1) / spec.sum(1))
        prev_spec = spec[-1]
    proc.wait()
    if not db:
        sys.exit(f"No audio decoded from track {track}. Check --mic-track / the file.")
    return np.concatenate(db), np.concatenate(voice), np.concatenate(flux)


def per_second(a, fn=np.mean):
    n = len(a) // FPS
    return fn(a[: n * FPS].reshape(n, FPS), axis=1)


def rolling_median(a, w):
    pad = w // 2
    ap = np.pad(a, (pad, w - pad - 1), mode="edge")
    return np.median(np.lib.stride_tricks.sliding_window_view(ap, w), axis=1)


def laugh_score(db):
    """Power of 3-7 Hz modulation in the loudness envelope, per second (2 s windows)."""
    env = 10 ** (db / 20)
    n = len(env) // FPS
    out = np.zeros(n)
    w = 2 * FPS
    freqs = np.fft.rfftfreq(w, 1 / FPS)
    band = (freqs >= 3) & (freqs <= 7)
    rest = freqs > 0.5
    hann = np.hanning(w)
    for s in range(n):
        seg = env[s * FPS: s * FPS + w]
        if len(seg) < w:
            break
        seg = (seg - seg.mean()) * hann
        p = np.abs(np.fft.rfft(seg)) ** 2
        out[s] = p[band].sum() / (p[rest].sum() + 1e-12)
    return out


def z(a):
    s = a.std()
    return (a - np.median(a)) / (s if s > 1e-9 else 1.0)


def parse_rec_start(video, explicit):
    if explicit:
        return dt.datetime.fromisoformat(explicit.replace("_", " ")).timestamp()
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})[ _T](\d{2})-(\d{2})-(\d{2})", os.path.basename(video))
    if m:  # OBS default filename: 2026-11-20 21-04-33.mkv
        y, mo, d, h, mi, s = map(int, m.groups())
        return dt.datetime(y, mo, d, h, mi, s).timestamp()
    return None


def load_gsi(path, rec_start, duration):
    """Returns list of (second_in_video, kind, detail)."""
    events = []
    if not path or not os.path.exists(path):
        return events
    if rec_start is None:
        print("! GSI log given but recording start time unknown; pass --rec-start", file=sys.stderr)
        return events
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = e["t"] - rec_start
            if 0 <= t <= (duration or 1e9):
                events.append((t, e["kind"], e.get("detail", "")))
    return events


GSI_WEIGHT = {"kill": 1.5, "headshot": 0.5, "multikill": 3.0, "ace": 6.0, "clutch_win": 4.0,
              "death": 0.8, "round_win": 0.7, "round_loss": 0.4, "bomb_planted": 0.4,
              "bomb_defused": 1.5, "knife_kill": 3.0, "match_end": 1.0}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("--mic-track", type=int, default=None,
                    help="audio track index holding ONLY voices (OBS multitrack). Default: 0 (mixed)")
    ap.add_argument("--gsi", help="events.jsonl written by gsi_server.py")
    ap.add_argument("--rec-start", help='recording start, e.g. "2026-11-20 21:04:33" (else parsed from OBS filename)')
    ap.add_argument("--top", type=int, default=25, help="max candidates to keep")
    ap.add_argument("--pre", type=float, default=10, help="seconds before the peak")
    ap.add_argument("--post", type=float, default=6, help="seconds after the peak")
    ap.add_argument("--min-gap", type=float, default=20, help="min seconds between peaks")
    ap.add_argument("--out", help="output folder (default <video>_clips)")
    a = ap.parse_args()

    video = os.path.abspath(a.video)
    if not os.path.exists(video):
        sys.exit(f"not found: {video}")
    out = a.out or os.path.splitext(video)[0] + "_clips"
    os.makedirs(out, exist_ok=True)
    duration = ffprobe_duration(video)
    ntracks = audio_tracks(video)
    track = a.mic_track if a.mic_track is not None else 0
    if track >= ntracks:
        sys.exit(f"file has {ntracks} audio track(s); --mic-track {track} does not exist")
    print(f"• {os.path.basename(video)}  {duration/60 if duration else 0:.1f} min, "
          f"{ntracks} audio track(s), analysing track {track}")

    db, voice, flux = frame_features(video, track)
    s_db = per_second(db, np.max)           # peak level each second
    s_voice = per_second(voice)
    s_flux = per_second(flux)
    n = len(s_db)
    base = rolling_median(s_db, 31)
    loud = np.clip(s_db - base, 0, None)
    burst = np.clip(np.diff(s_db, prepend=s_db[0]), 0, None)
    burst[:3] = 0; loud[:3] = 0          # ignore encoder start-up / OBS start click
    laugh = laugh_score(db)[:n]
    laugh = np.pad(laugh, (0, n - len(laugh)))

    # sustained loudness: 4 s moving average of 'loud'
    sustain = np.convolve(loud, np.ones(4) / 4, mode="same")
    voiced = (s_voice > np.percentile(s_voice, 60)).astype(float)
    mixed_only = a.mic_track is None
    voice_w = 1.0 if not mixed_only else 0.6   # on mixed audio, demand voice-band energy
    score = (1.0 * z(loud) + 0.8 * z(sustain) + 0.6 * z(burst) + 0.9 * z(laugh) * voiced
             + voice_w * z(s_voice) * (loud > 3) - 0.3 * z(s_flux) * (1 - voiced))

    rec_start = parse_rec_start(video, a.rec_start)
    gsi = load_gsi(a.gsi, rec_start, duration)
    gsi_bonus = np.zeros(n)
    for t, kind, _ in gsi:
        i = int(t)
        if 0 <= i < n:
            gsi_bonus[max(0, i - 2): i + 4] += GSI_WEIGHT.get(kind, 0.5)
    score = score + gsi_bonus
    score = np.convolve(score, np.ones(3) / 3, mode="same")

    # peak picking with a minimum gap
    order = np.argsort(-score)
    peaks = []
    for i in order:
        if score[i] <= 0.8 or len(peaks) >= a.top * 2:
            break
        if all(abs(i - p) >= a.min_gap for p in peaks):
            peaks.append(int(i))

    thr = {"loud": np.percentile(loud, 98), "laugh": np.percentile(laugh * voiced, 98),
           "sustain": np.percentile(sustain, 97), "burst": np.percentile(burst, 99)}
    cands = []
    for p in peaks:
        st = max(0.0, p - a.pre)
        en = min(float(n), p + a.post)
        # stretch end while the reaction keeps going (sustained loud talk)
        while en < n - 1 and en - p < 20 and sustain[int(en)] > 4:
            en += 1
        win = slice(int(st), int(en))
        tags = []  # relative to THIS recording, so a quiet or loud lobby both work
        if loud[win].max() > max(9, thr["loud"]): tags.append("shout")
        if (laugh[win] * voiced[win]).max() > thr["laugh"]: tags.append("laughter")
        if sustain[win].max() > max(5, thr["sustain"]): tags.append("hype")
        if burst[win].max() > max(12, thr["burst"]): tags.append("scream")
        ev = [f"{k}@{t - st:.0f}s" + (f"({d})" if d else "") for t, k, d in gsi if st <= t <= en]
        cands.append({
            "start": round(st, 1), "end": round(en, 1), "peak": p,
            "score": round(float(score[p]), 2),
            "loud_db": round(float(loud[win].max()), 1),
            "laugh": round(float(laugh[win].max()), 2),
            "tags": tags, "game_events": ev,
        })
    # merge overlapping windows
    cands.sort(key=lambda c: c["start"])
    merged = []
    for c in cands:
        if merged and c["start"] <= merged[-1]["end"] + 2:
            m = merged[-1]
            m["end"] = max(m["end"], c["end"])
            m["score"] = max(m["score"], c["score"])
            m["tags"] = sorted(set(m["tags"]) | set(c["tags"]))
            m["game_events"] += c["game_events"]
        else:
            merged.append(c)
    merged.sort(key=lambda c: -c["score"])
    merged = merged[: a.top]
    merged.sort(key=lambda c: c["start"])
    for k, c in enumerate(merged, 1):
        c["id"] = k

    data = {"video": video, "duration": duration, "audio_track": track,
            "rec_start": rec_start, "gsi_events": len(gsi), "candidates": merged}
    path = os.path.join(out, "candidates.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
    np.save(os.path.join(out, "score_per_second.npy"), score.astype(np.float32))
    print(f"• {len(merged)} candidates → {path}")


if __name__ == "__main__":
    main()
