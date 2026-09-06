"""HTTP API and static frontend. The frontend lives in ../frontend and talks JSON."""
from __future__ import annotations
import json, mimetypes, os, shutil, subprocess, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from agents import PROVIDERS, VERSIONS, refresh_versions, HINTS, test_provider
from engine import GAMES, World, now_id
from game import Game, Run, list_games

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"

# ---------------------------------------------------------------- the app (many games, one selected)
class App:
    def __init__(self) -> None:
        GAMES.mkdir(exist_ok=True)
        self.lock = threading.Lock(); self.runs: dict[str, Run] = {}
        first = self._latest(); self.gid = first.id; self.runs[first.id] = Run(first)
        self.phone_url = ""; self.away_url = ""; self.last_god = ""; self.tests: dict[str, dict] = {}
        refresh_versions()

    def _latest(self) -> Game:
        for m in list_games():
            g = Game.load(m["id"])
            if g: return g
        return Game(now_id())

    @property
    def run(self) -> Run: return self.runs[self.gid]

    def _get(self, gid: str) -> Run | None:
        if gid in self.runs: return self.runs[gid]
        g = Game.load(gid)
        if not g: return None
        self.runs[gid] = Run(g); return self.runs[gid]

    def map_state(self) -> dict:
        """Tiny, fast: everything the map needs, nothing else."""
        r = self.run; g = r.g
        with r.lock:
            w = g.world
            return {"id": g.id, "day": w.day, "status": g.status, "current": r.current, "created": w.created,
                    "map": w.map, "ledger": dict(w.ledger), "pending": list(w.pending), "fires": dict(w.fires), "threads": [t for t in w.threads if t["status"] == "open"],
                    "characters": [{k: c[k] for k in ("name", "location", "alive", "banished", "hp", "hp_max", "gold", "trade", "standing")} for c in w.characters.values()],
                    "seats": [{"name": x["name"], "color": x["color"]} for x in g.seats], "version": r.version}

    def snapshot(self, since: int = -1, terms: bool = False, tail: int = 120) -> dict:
        """Light by default: the transcript only from `since` (turn number), terminals only when asked and only their tails.
        The lock is held just long enough to copy references; JSON is built outside it."""
        r = self.run; g = r.g
        with r.lock:
            w = g.world
            tr = [e for e in g.transcript if e["turn"] > since] if since >= 0 else list(g.transcript)
            chars = [dict(c) for c in w.characters.values()]; ledger = dict(w.ledger); pending = list(w.pending); mp = w.map
            seats = list(g.seats); status = g.status; current = r.current; day = w.day; created = w.created; total = len(g.transcript); last_turn = g.turn
            tstates = [{"state": t["state"], "count": t["count"], "lines": list(t["lines"])[-tail:] if terms else []} for t in r.terms]
            return {"id": g.id, "title": g.title, "world_text": g.world_text, "players": g.players, "model_a": g.model_a, "model_b": g.model_b,
                    "world_model": g.world_model, "max_days": g.max_days, "max_minutes": g.max_minutes, "drama": g.drama, "repo": g.repo, "status": status,
                    "seats": seats, "transcript": tr, "transcript_total": total, "last_turn": last_turn, "current": current, "day": day, "created": created,
                    "characters": chars, "ledger": ledger, "pending": pending, "map": mp, "relations": json.loads(json.dumps(w.relations)),
                    "threads": list(w.threads), "fires": dict(w.fires),
                    "games": list_games(), "live": [k for k, x in self.runs.items() if x.busy()], "places": list(mp.keys()),
                    "terms": tstates,
                    "phone_url": self.phone_url, "away_url": self.away_url, "last_god": self.last_god,
                    "os": ("win" if os.name == "nt" else "mac" if os.uname().sysname == "Darwin" else "linux"),
                    "providers": {k: {"models": v["models"], "installed": shutil.which(v["exe"]) is not None, "exe": v["exe"], "hints": HINTS.get(k, {}), "test": self.tests.get(k),
                                      "version": VERSIONS.get(k, {}).get("installed", ""), "latest": VERSIONS.get(k, {}).get("latest", "")} for k, v in PROVIDERS.items()}}

    def configure(self, d: dict) -> None:
        r = self.run; g = r.g
        with r.lock:
            if r.busy() or g.world.created: return   # a world, once made, is fixed
            for k in ("title", "world_text", "repo"):
                if k in d: setattr(g, k, str(d[k]))
            if "players" in d: g.players = max(2, min(30, int(d["players"] or 20)))
            if "max_days" in d: g.max_days = max(1, int(d["max_days"] or 12))
            if "max_minutes" in d: g.max_minutes = max(0, int(d["max_minutes"] or 0))
            if "drama" in d: g.drama = max(0, min(10, int(d["drama"] or 0)))
            for k in ("model_a", "model_b", "world_model"):
                v = d.get(k)
                if isinstance(v, dict) and v.get("provider") in PROVIDERS and v.get("model"): setattr(g, k, {"provider": v["provider"], "model": v["model"]})
            if not g.title: g.title = "Terraceilia " + g.created[:10]
            g.seats = []; g.save()

    def new_game(self) -> None:
        with self.lock:
            g = Game(now_id()); g.save(); self.runs[g.id] = Run(g); self.gid = g.id

    def open_game(self, gid: str) -> None:
        with self.lock:
            if self._get(gid): self.gid = gid

    def delete_game(self, gid: str) -> None:
        with self.lock:
            r = self.runs.get(gid)
            if r and r.busy(): return
            self.runs.pop(gid, None); shutil.rmtree(GAMES / gid, ignore_errors=True)
            if gid == self.gid:
                g = self._latest(); self.runs.setdefault(g.id, Run(g)); self.gid = g.id

    def edit_game(self, d: dict) -> None:
        """Game settings, editable at any time. Days and minutes apply to the running loop; the World's model on its next turn."""
        r = self.run; g = r.g
        with r.lock:
            if "world_text" in d: g.world_text = str(d["world_text"])
            if "title" in d: g.title = str(d["title"])
            if "max_days" in d: g.max_days = max(1, int(d["max_days"] or 1))
            if "max_minutes" in d: g.max_minutes = max(0, int(d["max_minutes"] or 0))
            if "drama" in d: g.drama = max(0, min(10, int(d["drama"] or 0)))
            wm = d.get("world_model")
            if isinstance(wm, dict) and wm.get("provider") in PROVIDERS and wm.get("model"):
                g.world_model = {"provider": wm["provider"], "model": wm["model"]}
                if g.seats: g.seats[0]["provider"], g.seats[0]["model"] = wm["provider"], wm["model"]; g.cli_sessions.pop("0", None)
            g.save(); r.version += 1

    def edit_character(self, d: dict) -> str:
        """Edit a person while the game runs: seat model, stats, life, name. Returns a note for the chronicle."""
        r = self.run; g = r.g; w = g.world; name = str(d.get("name", "")); c = w.characters.get(name)
        if not c: return "no such person"
        notes = []
        with r.lock:
            seat = next((x for x in g.seats if x["name"] == name), None); i = g.seats.index(seat) if seat else None
            if seat and d.get("provider") in PROVIDERS and d.get("model"):
                if (seat["provider"], seat["model"]) != (d["provider"], d["model"]):
                    seat["provider"], seat["model"] = d["provider"], str(d["model"]); g.cli_sessions.pop(str(i), None); notes.append(f"{name} is now played by {d['provider']} {d['model']}")
            life_changed = False
            for k in ("trade", "personality", "secret", "fear", "want", "home"):
                if k in d and str(d[k]) != c.get(k): c[k] = str(d[k])[:300]; life_changed = True; notes.append(f"{name}'s {k} changed")
            if life_changed and i is not None:
                g.cli_sessions.pop(str(i), None)   # start the model fresh so the new life is not overruled by old context
                c["changed"] = True
            if d.get("standing") in ("respected", "feared", "pitied", "hated", "unknown", "loved") and d["standing"] != c["standing"]: c["standing"] = d["standing"]; notes.append(f"{name} is now {d['standing']}")
            for k in ("str", "spd", "gold", "hp", "hp_max"):
                if k in d:
                    try: v = int(d[k])
                    except (TypeError, ValueError): continue
                    v = max(0, v) if k in ("gold", "hp") else max(1, v)
                    if v != c[k]: c[k] = v; notes.append(f"{name}'s {k} is now {v}")
            tr = d.get("traits")
            if isinstance(tr, dict):
                c.setdefault("traits", {})
                for k, v in tr.items():
                    try: v = max(1, min(5, int(v)))
                    except (TypeError, ValueError): continue
                    if c["traits"].get(k) != v: c["traits"][k] = v; life_changed = True
                if life_changed and i is not None: g.cli_sessions.pop(str(i), None); c["changed"] = True
            c["hp"] = min(c["hp"], c["hp_max"])
            if c["hp"] <= 0 and c["alive"]: c["alive"] = False; c["cause_of_death"] = "struck down by fate"; notes.append(f"{name} died")
            if d.get("alive") is True and not c["alive"]: c["alive"] = True; c["hp"] = max(1, c["hp"]); c["cause_of_death"] = ""; notes.append(f"{name} lives again")
            if "banished" in d and bool(d["banished"]) != c["banished"]:
                c["banished"] = bool(d["banished"])
                if not c["banished"]: c["returned_day"] = w.day; notes.append(f"{name} has returned to the valley from banishment, walking back down the east road; the lord's court has no power over that return")
                else: notes.append(f"{name} has been banished from the valley")
            if d.get("location"):
                from engine import place_key
                dest = place_key(str(d["location"]), w.map)
                if dest and dest != c["location"]: c["location"] = dest; notes.append(f"{name} is at {dest}")
            new = str(d.get("new_name", "")).strip()
            if new and new != name and new not in w.characters and new.lower() != "world":
                c["name"] = new; w.characters = {(new if k == name else k): v for k, v in w.characters.items()}
                if seat: seat["name"] = new
                for a in w.pending:
                    if a["who"] == name: a["who"] = new
                if i is not None:
                    m = g.seat_dir(i) / "memory.md"
                    if m.exists(): m.write_text(m.read_text(encoding="utf-8").replace(f"# {name}:", f"# {new}:", 1) + f"\n(You are now called {new}; you were {name}.)\n", encoding="utf-8")
                notes.append(f"{name} is now called {new}")
            g.save(); r.version += 1
        if notes: w.fate.extend(notes); r._record("Fate", "; ".join(notes), "fate")
        return "; ".join(notes) or "no change"

    def edit_relation(self, d: dict) -> None:
        r = self.run; g = r.g; w = g.world
        with r.lock:
            w.set_rel(str(d.get("a", "")), str(d.get("b", "")), d.get("type"), d.get("feeling"), d.get("trust"), why=str(d.get("why") or "fate reached in and changed how they feel"))
            if d.get("mutual"): w.set_rel(str(d.get("b", "")), str(d.get("a", "")), d.get("type"), d.get("feeling"), d.get("trust"), why=str(d.get("why") or "fate reached in and changed how they feel"))
            g.save(); r.version += 1
        a, b = d.get("a"), d.get("b"); rr = w.rel(a, b) if a in w.characters and b in w.characters else None
        if rr: w.fate.append(f"Between {a} and {b} something has shifted: {a} now {w.feel_word(rr['feeling'])} {b} and {w.trust_word(rr['trust'])} ({rr['type']})."); r._record("Fate", w.fate[-1], "fate")

    def god(self, fn) -> None:  # noqa: ANN001
        """The convener's hand: move people, destroy or restore things, strike someone down. Recorded, then narrated."""
        r = self.run; g = r.g
        with r.lock:
            if not g.world.created: self.last_god = "the world has not been made yet"; return
            self.last_god = fn(g.world); g.save(); r.version += 1
        r._record("Fate", self.last_god, "fate")

    def shutdown(self) -> None:
        for r in list(self.runs.values()): r.stop()   # kills are parallel and non-blocking
        def die() -> None:
            if os.name == "nt":
                try:
                    ppid = subprocess.run(["powershell", "-NoProfile", "-Command", f"(Get-CimInstance Win32_Process -Filter 'ProcessId={os.getpid()}').ParentProcessId"], capture_output=True, text=True, timeout=10).stdout.strip()
                    if ppid.isdigit(): subprocess.Popen(["cmd", "/c", f"timeout /t 1 /nobreak >nul & taskkill /PID {ppid} /T /F"], creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "DETACHED_PROCESS", 0))
                except Exception: pass
            os._exit(0)
        threading.Timer(0.8, die).start()

def list_dir(path: str) -> dict:
    p = Path(path or Path.home()).expanduser()
    if not p.is_dir(): p = Path.home()
    try: subs = sorted([c.name for c in p.iterdir() if c.is_dir() and not c.name.startswith(".")], key=str.lower)
    except PermissionError: subs = []
    drives = [f"{d}:\\" for d in "CDEFGH" if os.name == "nt" and Path(f"{d}:\\").exists()]
    return {"path": str(p), "parent": str(p.parent) if p.parent != p else None, "dirs": subs, "drives": drives}



def make_handler(app: App, token: str):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def _send(self, body: bytes, ctype: str):
            self.send_response(200); self.send_header("Content-Type", ctype); self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
        def _authed(self) -> bool:
            from urllib.parse import parse_qs, urlparse
            q = parse_qs(urlparse(self.path).query).get("token", [""])[0]
            if q == token:
                self.send_response(302); self.send_header("Set-Cookie", f"terra={token}; Path=/; SameSite=Lax"); self.send_header("Location", "/"); self.end_headers(); return False
            if f"terra={token}" in self.headers.get("Cookie", ""): return True
            body = b"Terraceilia: open the link with the token shown in the terminal that started it."
            self.send_response(403); self.send_header("Content-Type", "text/plain"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body); return False
        def do_GET(self):
            if not self._authed(): return
            if self.path == "/events":
                # server-sent events: push the map state whenever the engine's version changes
                self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.send_header("Cache-Control", "no-store"); self.end_headers()
                last = -1
                try:
                    while True:
                        r = app.run; v = r.version
                        if v != last or app.gid != getattr(self, "_gid", None):
                            last = v; self._gid = app.gid
                            self.wfile.write(f"data: {json.dumps(app.map_state())}\n\n".encode()); self.wfile.flush()
                        time.sleep(0.25)
                except (BrokenPipeError, ConnectionResetError, OSError): pass
                return
            if self.path.startswith("/state"):
                from urllib.parse import parse_qs, urlparse
                q = parse_qs(urlparse(self.path).query)
                return self._send(json.dumps(app.snapshot(since=int(q.get("since", ["-1"])[0]), terms=q.get("terms", ["0"])[0] == "1")).encode(), "application/json")
            if self.path.startswith("/ls"):
                from urllib.parse import parse_qs, urlparse
                return self._send(json.dumps(list_dir(parse_qs(urlparse(self.path).query).get("path", [""])[0])).encode(), "application/json")
            if self.path.startswith("/export"):
                from urllib.parse import parse_qs, urlparse
                what = parse_qs(urlparse(self.path).query).get("what", ["chronicle"])[0]
                r = app.run; g = r.g
                with r.lock: terms = [{"lines": list(t["lines"])} for t in r.terms]
                body = g.export(what, terms).encode("utf-8")
                safe = "".join(ch if ch.isalnum() or ch in "-_ " else "_" for ch in (g.title or "terraceilia"))[:50].strip() or "terraceilia"
                self.send_response(200); self.send_header("Content-Type", "text/markdown; charset=utf-8"); self.send_header("Content-Disposition", f'attachment; filename="{safe}-{what}.md"')
                self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body); return
            # static frontend
            rel = self.path.split("?")[0].lstrip("/") or "index.html"
            f = (FRONTEND / rel).resolve()
            if FRONTEND in f.parents and f.is_file():
                ctype = mimetypes.guess_type(str(f))[0] or "application/octet-stream"
                return self._send(f.read_bytes(), ctype + ("; charset=utf-8" if ctype.startswith("text/") or ctype.endswith("javascript") else ""))
            self._send(b"not found", "text/plain")
        def do_POST(self):
            if not self._authed(): return
            n = int(self.headers.get("Content-Length", 0)); data = json.loads(self.rfile.read(n) or b"{}")
            {"/config": lambda: app.configure(data), "/start": lambda: app.run.start(), "/pause": lambda: app.run.pause(), "/stop": lambda: app.run.stop(),
             "/say": lambda: app.run.say(data.get("text", "")), "/game/new": app.new_game, "/game/open": lambda: app.open_game(data.get("id", "")),
             "/game/delete": lambda: app.delete_game(data.get("id", "")), "/shutdown": app.shutdown,
             "/god/move": lambda: app.god(lambda w: w.move(data.get("name", ""), data.get("place", ""))),
             "/god/destroy": lambda: app.god(lambda w: w.destroy(data.get("place", ""), data.get("fixture", ""))),
             "/god/smite": lambda: app.god(lambda w: w.smite(data.get("name", ""))),
             "/god/fire": lambda: app.god(lambda w: w.ignite(data.get("place", ""))),
             "/god/extinguish": lambda: app.god(lambda w: ("fire out at " + data.get("place", "")) if w.extinguish(data.get("place", "")) else "no fire there"),
             "/edit/game": lambda: app.edit_game(data),
             "/provider/test": lambda: app.tests.__setitem__(data.get("provider", ""), test_provider(data.get("provider", ""), data.get("model", ""), app.run.g.repo)),
             "/edit/relation": lambda: app.edit_relation(data),
             "/edit/character": lambda: setattr(app, "last_god", app.edit_character(data))}.get(self.path, lambda: None)()
            full = self.path in ("/game/open", "/game/new", "/game/delete")
            self._send(json.dumps(app.snapshot(since=-1 if full else 10**9)).encode(), "application/json")
    return H


