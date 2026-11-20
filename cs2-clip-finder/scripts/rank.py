#!/usr/bin/env python3
"""Stage 3: rank candidates and write the token-cheap shortlist.

If Ollama is running locally (https://ollama.com, e.g. `ollama pull qwen2.5:7b`),
a local LLM reads each candidate's numbers + transcript and returns
{category, title, score}. Without Ollama a heuristic score is used.

Then shortlist.md is written: one line per candidate. That file (a few KB) is
the ONLY thing Claude needs to read to pick clips.

Usage: python rank.py <video>_clips/candidates.json [--model qwen2.5:7b] [--no-llm]
"""
import argparse, json, os, urllib.request

OLLAMA = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")

PROMPT = """You rate moments from a Counter-Strike 2 gameplay recording with friends on voice chat.
Signals: loud_db = dB above the room's normal level, laugh = laughter-rhythm score (>0.3 is strong),
tags from audio analysis, game_events from the game itself, transcript = what players said.
Decide if this is publishable short-form content (TikTok/Shorts/Reels).
Categories: funny, hype, clutch, ace, multikill, fail, rage, wholesome, none.
Reply with JSON only: {{"category": "...", "score": 0-10, "title": "short catchy title, max 8 words", "why": "max 12 words"}}

Moment:
{moment}"""


def ollama_ok(model):
    try:
        with urllib.request.urlopen(f"{OLLAMA}/api/tags", timeout=2) as r:
            tags = json.load(r)
        names = [m["name"] for m in tags.get("models", [])]
        return any(n == model or n.split(":")[0] == model.split(":")[0] for n in names), names
    except Exception:
        return False, []


def ask(model, moment):
    body = json.dumps({"model": model, "prompt": PROMPT.format(moment=moment), "stream": False,
                       "format": "json", "options": {"temperature": 0.2}}).encode()
    req = urllib.request.Request(f"{OLLAMA}/api/generate", body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(json.load(r)["response"])


def heuristic(c, top):
    s = 10 * max(0.0, c["score"]) / top          # best moment of the game = 10
    tags = set(c["tags"])
    ev = " ".join(c.get("game_events", []))
    s += 0.5 * len(tags)
    if "ace" in ev: cat = "ace"
    elif "clutch_win" in ev: cat = "clutch"
    elif "multikill" in ev: cat = "multikill"
    elif "laughter" in tags: cat = "funny"
    elif "scream" in tags or "shout" in tags: cat = "hype"
    else: cat = "none"
    if c.get("hype_words"): s += 1
    s = min(10.0, s)
    return {"category": cat, "score": round(s, 1), "title": "", "why": "heuristic"}


def fmt(t):
    t = int(t)
    return f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}" if t >= 3600 else f"{t // 60}:{t % 60:02d}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("candidates")
    ap.add_argument("--model", default="qwen2.5:7b")
    ap.add_argument("--no-llm", action="store_true")
    a = ap.parse_args()
    data = json.load(open(a.candidates, encoding="utf-8"))
    use_llm = False
    if not a.no_llm:
        use_llm, names = ollama_ok(a.model)
        if not use_llm:
            print(f"• Ollama/{a.model} not available ({'installed: ' + ', '.join(names) if names else 'not running'}); heuristic ranking")
    top = max([c["score"] for c in data["candidates"]] + [1e-6])
    for c in data["candidates"]:
        r = None
        if use_llm:
            moment = {k: c.get(k) for k in ("loud_db", "laugh", "tags", "game_events", "transcript")}
            moment["length_s"] = round(c["end"] - c["start"])
            try:
                r = ask(a.model, json.dumps(moment, ensure_ascii=False))
                r["score"] = float(r.get("score", 0))
            except Exception as e:
                print(f"  #{c['id']} LLM error: {e}; heuristic used")
        c["rank"] = r or heuristic(c, top)
        print(f"  #{c['id']:>2} {c['rank']['category']:<9} {c['rank']['score']:>4}  {c['rank'].get('title', '')}")
    json.dump(data, open(a.candidates, "w", encoding="utf-8"), indent=1)

    rows = sorted(data["candidates"], key=lambda c: -c["rank"]["score"])
    lines = [f"# Shortlist: {os.path.basename(data['video'])}",
             f"duration {fmt(data['duration'] or 0)} | ranked by {'local LLM ' + a.model if use_llm else 'heuristic'} | "
             f"gsi events {data['gsi_events']}",
             "", "id | time | len | score | category | tags/events | title | transcript"]
    for c in rows:
        tr = (c.get("transcript") or "").replace("\n", " ").replace("|", "/")
        if len(tr) > 160:
            tr = tr[:157] + "..."
        kinds = [e.split("@")[0] for e in c.get("game_events", [])]
        evs = [f"{kinds.count(k)}x{k}" if kinds.count(k) > 1 else k for k in dict.fromkeys(kinds)]
        info = ",".join(c["tags"] + evs)
        lines.append(f"{c['id']} | {fmt(c['start'])}-{fmt(c['end'])} | {c['end'] - c['start']:.0f}s | "
                     f"{c['rank']['score']} | {c['rank']['category']} | {info} | "
                     f"{c['rank'].get('title', '')} | {tr}")
    path = os.path.join(os.path.dirname(os.path.abspath(a.candidates)), "shortlist.md")
    open(path, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print(f"• shortlist → {path}  ({len(open(path, encoding='utf-8').read())} chars)")


if __name__ == "__main__":
    main()
