#!/usr/bin/env python3
"""Optional: log CS2 game events (kills, headshots, multi-kills, aces, deaths, rounds)
with timestamps while you play, using CS2's built-in Game State Integration.

1. Copy templates/gamestate_integration_clipper.cfg into
   ...\\Steam\\steamapps\\common\\Counter-Strike Global Offensive\\game\\csgo\\cfg\\
2. Run this before you launch CS2:  python gsi_server.py --out events.jsonl
3. Start OBS recording, play, stop. Then:  python run.py <video> --gsi events.jsonl

Pure standard library; listens only on 127.0.0.1. Valve-sanctioned (no VAC risk):
the game pushes data to this port, nothing reads game memory.
"""
import argparse, json, time
from http.server import BaseHTTPRequestHandler, HTTPServer

TOKEN = "cs2clipper"
state = {"round_kills": 0, "round_hs": 0, "health": 100, "round_phase": None, "map_phase": None,
         "multi_logged": 0}


def emit(f, kind, detail=""):
    rec = {"t": time.time(), "kind": kind, "detail": detail}
    f.write(json.dumps(rec) + "\n")
    f.flush()
    print(time.strftime("%H:%M:%S"), kind, detail)


def handle(payload, f):
    if payload.get("auth", {}).get("token") != TOKEN:
        return
    me = payload.get("provider", {}).get("steamid")
    player = payload.get("player", {})
    rnd = payload.get("round", {})
    mp = payload.get("map", {})
    mine = player.get("steamid") == me  # ignore data while spectating teammates
    if mine:
        ps = player.get("state", {})
        rk, hs = ps.get("round_kills", 0), ps.get("round_killhs", 0)
        if rk > state["round_kills"]:
            weapon = next((w.get("name", "") for w in player.get("weapons", {}).values()
                           if w.get("state") == "active"), "")
            for _ in range(rk - state["round_kills"]):
                emit(f, "knife_kill" if "knife" in weapon else "kill", weapon.replace("weapon_", ""))
            if hs > state["round_hs"]:
                emit(f, "headshot")
            if rk >= 5 and state["multi_logged"] < 5:
                emit(f, "ace", "5k"); state["multi_logged"] = 5
            elif rk >= 3 and state["multi_logged"] < rk:
                emit(f, "multikill", f"{rk}k"); state["multi_logged"] = rk
        hp = ps.get("health", state["health"])
        if hp == 0 and state["health"] > 0 and rnd.get("phase") == "live":
            emit(f, "death")
        state.update(round_kills=rk, round_hs=hs, health=hp)
    phase = rnd.get("phase")
    if phase != state["round_phase"]:
        if phase == "over":
            win = rnd.get("win_team")
            team = player.get("team")
            if win and team:
                emit(f, "round_win" if win == team else "round_loss", f"{win}")
        if phase == "freezetime":
            state.update(round_kills=0, round_hs=0, multi_logged=0, health=100)
        state["round_phase"] = phase
    bomb = rnd.get("bomb")
    if bomb and bomb != state.get("bomb"):
        if bomb in ("planted", "defused"):
            emit(f, "bomb_" + bomb)
        state["bomb"] = bomb
    if mp.get("phase") == "gameover" and state["map_phase"] != "gameover":
        emit(f, "match_end", mp.get("name", ""))
    state["map_phase"] = mp.get("phase")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=3000)
    ap.add_argument("--out", default="events.jsonl")
    a = ap.parse_args()
    f = open(a.out, "a", encoding="utf-8")

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            try:
                handle(json.loads(body), f)
            except Exception as e:
                print("parse error:", e)
            self.send_response(200); self.end_headers()

        def log_message(self, *_):
            pass

    print(f"GSI logger on 127.0.0.1:{a.port} → {a.out}  (Ctrl+C to stop)")
    HTTPServer(("127.0.0.1", a.port), H).serve_forever()


if __name__ == "__main__":
    main()
