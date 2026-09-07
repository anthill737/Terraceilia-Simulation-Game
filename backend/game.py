"""One game: its saved state, and the engine loop that runs a year of days."""
from __future__ import annotations
import collections, datetime as dt, json, os, random, re, shutil, subprocess, threading, time
from pathlib import Path

from agents import ASK, PROVIDERS, clean_copilot, render_claude_event, ensure_codex_trust
from engine import (GAMES, NAMES, World, roll_character, now_id, map_text, extract_json, strip_json, action_line,  # noqa: F401
                    whisper_targets, visible_text, urges, mentions, validate_map, strip_dashes, cap_speech, cap_outcomes, touched_text, starting_ledger, season_of, DUTIES, PASTIMES)
from prompts import DEFAULT_WORLD, PLAYER_RULES, WORLD_RULES, map_prompt

TURN_TIMEOUT = 1800
TAIL = 400

# Codex signs in with a subscription and rotates its refresh token. Several processes refreshing at the same
# moment race, and the losers are refused with 401; a losing write can leave auth.json unusable. So each day
# one Codex call is made on its own first, and the file it leaves behind is kept as the copy to fall back on.
CODEX_PROVIDERS = ("Codex", "Codex (latest)")
# What a dead sign in looks like on the wire: a 401, or Codex saying the refresh token is gone.
CODEX_401 = re.compile(r"\b401\b|unauthorized|missing bearer|refresh token was revoked|could not be refreshed|invalid_grant|not logged in|login required", re.I)
CODEX_AUTH = Path.home() / ".codex" / "auth.json"
CODEX_BACKUP = Path.home() / ".codex" / "auth.json.terraceilia-backup"
CODEX_PRIME = "Reply with exactly the single word: ready"

# ---------------------------------------------------------------- a game (persisted)
class Game:
    def __init__(self, gid: str, d: dict | None = None) -> None:
        self.id = gid; self.dir = GAMES / gid; self.dir.mkdir(parents=True, exist_ok=True)
        d = d or {}
        self.title = d.get("title", "")
        self.created = d.get("created", dt.datetime.now().isoformat(timespec="minutes"))
        self.world_text = d.get("world_text", DEFAULT_WORLD)
        self.players = d.get("players", 20)
        self.model_a = d.get("model_a", {"provider": "Claude Code", "model": "claude-haiku-4-5"})
        self.model_b = d.get("model_b", {"provider": "Codex (latest)", "model": "gpt-5.4-mini"})
        self.world_model = d.get("world_model", {"provider": "Claude Code", "model": "claude-fable-5-1"})
        self.map_source = d.get("map_source") if d.get("map_source") in ("builtin", "generated") else "builtin"
        self.map_model = d.get("map_model") if isinstance(d.get("map_model"), dict) else None     # None: the World's model draws it
        self.max_days = d.get("max_days", 12)
        self.max_minutes = d.get("max_minutes", 0)
        self.drama = int(d.get("drama", 6))
        self.readonly = True
        self.repo = d.get("repo", str(self.dir))
        self.seats: list[dict] = d.get("seats", [])          # index 0 is World; {name, provider, model, color}
        self.transcript: list[dict] = d.get("transcript", [])
        self.turn = d.get("turn", 0); self.status = d.get("status", "idle")
        if self.status in ("running",): self.status = "paused"
        self.started_at = d.get("started_at", 0.0)
        self.cli_sessions = d.get("cli_sessions", {}); self.last_seen = d.get("last_seen", {})
        self.world = World(d.get("world"))

    def to_dict(self) -> dict:
        return {"title": self.title, "created": self.created, "world_text": self.world_text, "players": self.players,
                "model_a": self.model_a, "model_b": self.model_b, "world_model": self.world_model, "max_days": self.max_days,
                "map_source": self.map_source, "map_model": self.map_model,
                "max_minutes": self.max_minutes, "drama": self.drama, "repo": self.repo, "seats": self.seats, "transcript": self.transcript,
                "turn": self.turn, "status": self.status, "started_at": self.started_at, "cli_sessions": self.cli_sessions,
                "last_seen": self.last_seen, "world": self.world.to_dict()}

    def save(self, chronicle: bool = False) -> None:
        (self.dir / "game.json").write_text(json.dumps(self.to_dict()), encoding="utf-8")
        if chronicle: self.write_chronicle()

    def write_chronicle(self) -> None:
        md = [f"# {self.title or 'Terraceilia'}", f"Created: {self.created}", "", self.world_text, ""]
        for e in self.transcript: md += [f"## {e['speaker']} ({e['kind']}, day {e.get('day', 0)}, {e['time']})", "", e["text"], ""]
        (self.dir / "chronicle.md").write_text("\n".join(md), encoding="utf-8")

    # ---- exports
    def export(self, what: str = "chronicle", terms: list[dict] | None = None) -> str:
        """chronicle: the World's days, people's words, fate. settings: plus the game settings and every person's full sheet and ties.
        everything: plus open and resolved situations, fires, the map's ruins, engine adjustments, and each seat's terminal tail."""
        w = self.world; L = self.ledger_line()
        md = [f"# {self.title or 'Terraceilia'}", f"Created {self.created} · day {w.day} of {self.max_days} · {self.status}", "", self.world_text, ""]
        if what in ("settings", "everything"):
            md += ["## Settings", "", f"- People: {self.players}", f"- Days in the year: {self.max_days}", f"- Time limit: {self.max_minutes or 'none'} minutes", f"- Drama: {self.drama} / 10",
                   f"- Map: {('generated from the description: ' + w.map_name + ', ' + str(len(w.map)) + ' places') if w.map_generated else 'the built-in valley of Terraceilia'}",
                   f"- World model: {self.world_model['provider']} {self.world_model['model']}", f"- People models: {self.model_a['provider']} {self.model_a['model']} and {self.model_b['provider']} {self.model_b['model']}", f"- Folder: {self.repo}", ""]
            md += ["## The people", ""]
            for c in sorted(w.characters.values(), key=lambda c: c["seat"]):
                seat = next((x for x in self.seats if x["name"] == c["name"]), {})
                md += [f"### {c['name']}, {c['trade']} ({seat.get('provider', '')} {seat.get('model', '')})",
                       f"{'DEAD: ' + c['cause_of_death'] if not c['alive'] else ('gone: ' + (c['gone_reason'] or 'gone')) if c['gone'] else 'alive'} · at {c['location']} · home {c['home']} · standing {c['standing']}",
                       f"STR {c['str']} SPD {c['spd']} HP {c['hp']}/{c['hp_max']} gold {c['gold']} skills {', '.join(f'{k} {v}' for k, v in c['skills'].items()) or 'none'}",
                       f"Disposition: {', '.join(f'{k} {v}' for k, v in (c.get('traits') or {}).items())}",
                       f"Personality: {c['personality']}", f"Secret: {c['secret']}", f"Fear: {c['fear']}", f"Want: {c['want']}", "", "Ties:", w.relations_text(c["name"]).replace("You ", f"{c['name']} ").replace("you ", f"{c['name']} "), ""]
        if what == "everything":
            md += ["## Situations", ""] + [f"- #{t['id']} (day {t['day']}{', ' + t['place'] if t.get('place') else ''}) {t['text']} · {t['status']}{(' on day ' + str(t.get('resolved_day')) + ': ' + t.get('note', '')) if t['status'] != 'open' else ''}" for t in w.threads] + [""]
            ruins = [f"- {p}: {', '.join(d.get('destroyed', []))}" for p, d in w.map.items() if d.get("destroyed")]; pres = [f"- {p}: {', '.join(d.get('present', []))}" for p, d in w.map.items() if d.get("present")]
            md += ["## The map today", "", "Ruined:"] + (ruins or ["- nothing"]) + ["", "Present:"] + (pres or ["- nothing"]) + ["", f"Fires: {', '.join(w.fires) or 'none'}", ""]
        md += ["## Chronicle", ""]
        for e in self.transcript:
            if what == "chronicle" and e["kind"] == "system": continue
            md += [f"### {e['speaker']} · day {e.get('day', 0)}{' · ' + e['place'] if e.get('place') else ''} · {e['time']} ({e['kind']})", "", e["text"], ""]
        if what == "everything" and terms:
            md += ["## Terminals (last lines of each seat)", ""]
            for seat, t in zip(self.seats, terms):
                md += [f"### {seat['name']} ({seat['provider']} {seat['model']})", "", "```", *[ln for ln in t.get("lines", [])][-120:], "```", ""]
        return "\n".join(md)

    def ledger_line(self) -> str:
        return self.world.ledger_text()

    @classmethod
    def load(cls, gid: str) -> "Game | None":
        f = GAMES / gid / "game.json"
        if not f.exists(): return None
        try: return cls(gid, json.loads(f.read_text(encoding="utf-8")))
        except Exception: return None

    def seat_dir(self, i: int) -> Path:
        d = self.dir / f"seat{i}"; d.mkdir(exist_ok=True)
        m = d / "memory.md"
        if not m.exists(): m.write_text(f"# {self.seats[i]['name'] if i < len(self.seats) else i}: memory\n\n(Nothing yet.)\n", encoding="utf-8")
        return d


_GAMES_CACHE: dict[str, tuple[float, dict]] = {}


def list_games() -> list[dict]:
    """Index of games. Parses a game.json only when its mtime changed, so polling stays cheap."""
    out = []
    for f in sorted(GAMES.glob("*/game.json"), reverse=True):
        try:
            mt = f.stat().st_mtime; hit = _GAMES_CACHE.get(str(f))
            if hit and hit[0] == mt: out.append(hit[1]); continue
            d = json.loads(f.read_text(encoding="utf-8"))
            meta = {"id": f.parent.name, "title": d.get("title") or "Terraceilia", "created": d.get("created", ""),
                    "status": d.get("status", "idle"), "day": d.get("world", {}).get("day", 0)}
            _GAMES_CACHE[str(f)] = (mt, meta); out.append(meta)
        except Exception: continue
    return out


# Seat colours: the one dot each person carries. Warm and earthen, so nothing on the page is blue.
PALETTE = ["#d0a92c", "#7f9a5c", "#b4553f", "#e2c377", "#a3b26a", "#c77a4a", "#8a5a7a", "#5f8a6a", "#d98b6a", "#9a8a3a",
           "#b08a5a", "#6b7a4a", "#c95a5a", "#a0693a", "#8a7a4a", "#d8b58a", "#4f7a5a", "#b07a2a", "#9f5a4a", "#8fae66", "#c9a227"]


# ---------------------------------------------------------------- the run (one game's engine)
class Run:
    def __init__(self, g: Game) -> None:
        self.g = g; self.lock = threading.RLock()
        self.terms: list[dict] = []; self.current: str | None = None
        self.procs: dict[int, subprocess.Popen] = {}; self.speaking: set[int] = set()
        self.thread: threading.Thread | None = None
        self.stop_flag, self.pause_flag = threading.Event(), threading.Event()
        self.rng = random.Random()
        self.version = 0
        self.day_urges: dict[str, list[str]] = {}
        self.map_generating = False
        self.blocked = ""                       # why the run is stuck, in words the convener can act on
        self.codex_lock = threading.Lock(); self._in_codex_recovery = False
        self.reprime = False; self.refused: set[int] = set()     # seats whose last call was refused with 401, to be asked again after the recovery
        self._sync_terms(); self._migrate()

    def _migrate(self) -> None:
        """A game saved before some part of the colony existed gets that part seeded, once, as a new game would, and the chronicle says so."""
        g = self.g; w = g.world
        if not w.created: return
        seeded = w.seed_missing(self.rng); carried = list(w.migrated); w.migrated = []
        if not seeded and not carried: return
        bits = []
        if seeded: bits.append("seeded as for a new game: " + ", ".join(seeded))
        if carried: bits.append("carried over from the old save: " + ", ".join(carried))
        self._record("Engine", "This game was saved before the colony rules changed; " + "; ".join(bits) + ".", "system")
        g.save()

    def _sync_terms(self) -> None:
        """One terminal per seat. Existing terminals keep their lines; extra ones go when the seats are rebuilt."""
        n = len(self.g.seats); del self.terms[n:]
        while len(self.terms) < n: self.terms.append({"lines": collections.deque(maxlen=TAIL), "state": "waiting", "count": 0})

    def busy(self) -> bool: return self.g.status == "running"

    # ---- Codex, whose sign in rotates under everyone
    def codex_provider(self) -> str | None:
        """The one Codex install this game uses, or None if it uses none."""
        names = [s["provider"] for s in self.g.seats if s["provider"] in CODEX_PROVIDERS]
        return collections.Counter(names).most_common(1)[0][0] if names else None

    def one_codex(self) -> None:
        """Both Codex installs share one sign in, so a game never mixes them; every Codex seat gets the same one."""
        keep = self.codex_provider()
        if not keep: return
        moved = [s["name"] for s in self.g.seats if s["provider"] in CODEX_PROVIDERS and s["provider"] != keep]
        if not moved: return
        for s in self.g.seats:
            if s["provider"] in CODEX_PROVIDERS and s["provider"] != keep:
                s["provider"] = keep; self.g.cli_sessions.pop(str(self.g.seats.index(s)), None)
        self.g.save()
        self._record("Engine", f"{', '.join(moved)} moved to {keep}. The two Codex installs share one sign in, so one game uses only one of them.", "system")

    def _backup_codex(self) -> None:
        try:
            if CODEX_AUTH.is_file(): shutil.copy2(CODEX_AUTH, CODEX_BACKUP)
        except OSError: pass

    def _restore_codex(self) -> bool:
        try:
            if CODEX_BACKUP.is_file(): shutil.copy2(CODEX_BACKUP, CODEX_AUTH); return True
        except OSError: pass
        return False

    def prime_codex(self, label: str) -> bool:
        """One short call through Codex, alone, before the seats run in parallel. It refreshes the token once
        instead of every seat refreshing at once, and the file it leaves is then kept as the copy to restore."""
        prov = self.codex_provider()
        if not prov: return True
        model = next((s["model"] for s in self.g.seats if s["provider"] == prov), "")
        out = self._invoke(0, CODEX_PRIME, f"Codex {label}", provider=prov, model=model)
        ok = bool(out) and not CODEX_401.search(out)
        if ok: self._backup_codex()
        return ok

    def _codex_refused(self) -> None:
        """A seat was refused with 401. Pause at once, put the saved sign in back, prime again, and carry on if
        that worked. If it did not, stay paused and say plainly what the convener has to do."""
        with self.codex_lock:
            if self._in_codex_recovery: return
            self._in_codex_recovery = True
        try:
            self.pause_flag.set()
            with self.lock:
                self.g.status = "paused"; self.blocked = "Codex was refused. Putting the saved sign in back."; self.version += 1; self.g.save()
            self._record("Engine", "A Codex seat was refused with 401, which is what a rotated sign in looks like. The run is paused while the saved sign in is restored and primed again.", "system")
            self._restore_codex()
            if self.prime_codex("priming again after a refusal"):
                with self.lock:
                    self.blocked = ""; self.g.status = "running"; self.version += 1; self.g.save()
                self.pause_flag.clear()
                self._record("Engine", "Codex answered again. The year carries on.", "system")
            else:
                with self.lock:
                    self.blocked = "Codex signed out, sign in and press Resume"; self.version += 1; self.g.save()
                self._record("Engine", "Codex is still signed out. Open the gear, then Connections, sign in to Codex, and press Resume.", "system")
        finally:
            with self.codex_lock: self._in_codex_recovery = False

    # ---- setup: the map, then the people
    def world_seat(self) -> dict:
        g = self.g; return {"name": "World", "provider": g.world_model["provider"], "model": g.world_model["model"], "color": "#d0a92c"}

    def map_model_used(self) -> dict:
        """The model that draws a generated map: the one chosen for it, else the World's."""
        g = self.g; m = g.map_model
        return m if isinstance(m, dict) and m.get("provider") in PROVIDERS and m.get("model") else g.world_model

    def prepare_map(self) -> None:
        """Before the people are rolled: keep the built-in valley, keep a map already generated, or generate one now
        (two tries through the CLI; then the built-in valley, with an Engine note in the chronicle)."""
        g = self.g; w = g.world
        if not g.seats: g.seats = [self.world_seat()]; self._sync_terms()
        if g.map_source != "generated":
            if w.map_generated: w.install_builtin(); g.save()
            return
        if w.map_generated or self._generate_map() or self.stop_flag.is_set(): return
        with self.lock: w.install_builtin(); self.version += 1
        g.save()
        self._record("Engine", "The map could not be generated from the description after two tries. The built-in valley of Terraceilia is used instead.", "system")

    def _generate_map(self) -> bool:
        """Ask the map model for the map through the same CLI path as everything else; one retry on an unusable reply."""
        g = self.g; w = g.world; mm = self.map_model_used()
        self._term(0, f"drawing the map from the description with {mm['provider']} {mm['model']}...")
        ok = False; problem = ""
        for attempt in range(2):
            if self.stop_flag.is_set(): break
            out = self._invoke(0, map_prompt(g.world_text, problem), "map", provider=mm["provider"], model=mm["model"])
            v = validate_map(extract_json(out or ""))
            if v.get("ok"):
                with self.lock: w.install_map(v); self.version += 1
                self._term(0, f"map: {v['name']}, {len(v['places'])} places, {len(v['names']) or 'no'} names, {v['style']['water']['type']} water, {v['style']['sky']} sky"); ok = True; break
            problem = v.get("why", "it could not be read")
            self._term(0, f"[unusable map: {problem}]")
        g.cli_sessions.pop("0", None)      # the World begins its own session fresh
        g.save(); return ok

    def regenerate_map(self) -> str:
        """Draw a new map now, before Start. Once people exist the map is fixed for the game."""
        g = self.g; w = g.world
        with self.lock:
            if w.created or w.characters or len(g.seats) > 1: return "the map is fixed once people exist"
            if self.busy() or self.map_generating: return "busy; try again in a moment"
            if g.map_source != "generated": return "this game uses the built-in valley"
            if not g.seats: g.seats = [self.world_seat()]; self._sync_terms()
            self.stop_flag.clear(); self.map_generating = True; self.version += 1
        def work() -> None:
            try:
                if not self._generate_map() and not self.stop_flag.is_set():
                    self._record("Engine", "The map could not be generated from the description after two tries; the map is unchanged.", "system")
            finally:
                with self.lock: self.map_generating = False; self.version += 1
                g.save()
        threading.Thread(target=work, daemon=True).start()
        return "drawing a new map from the description; watch the World's terminal"

    def _build_people(self) -> None:
        """Roll the people onto this map: names from the generated map when it brought enough, else data/names.json."""
        g = self.g; w = g.world; rng = random.Random()
        pool = list(w.names) if w.names else NAMES[:]; rng.shuffle(pool)
        if len(pool) < g.players:
            extra = [n for n in NAMES if n.lower() not in {p.lower() for p in pool}]; rng.shuffle(extra); pool += extra
        names = pool[: g.players]; srng = random.Random(); places = list(w.map)
        with self.lock:
            g.seats = g.seats[:1] + [{"name": n, "provider": (g.model_a if i % 2 == 0 else g.model_b)["provider"], "model": (g.model_a if i % 2 == 0 else g.model_b)["model"],
                                      "color": PALETTE[i % len(PALETTE)]} for i, n in enumerate(names)]
            w.characters = {}
            for i, n in enumerate(names): w.characters[n] = roll_character(n, i + 1, srng, places)
            w.ledger = starting_ledger(len(names), len(w.map)); w.seed_places()
            self._sync_terms(); self.version += 1
        for i in range(len(g.seats)): g.seat_dir(i)
        self.one_codex(); g.save()

    # ---- controls
    def start(self) -> None:
        with self.lock:
            g = self.g
            if self.busy() or self.map_generating: return
            if g.status == "paused" and self.thread and self.thread.is_alive():
                if self.blocked: self.reprime = True          # the convener signed in again: prime before anyone speaks, and keep the new sign in as the copy
                self.blocked = ""; self.pause_flag.clear(); g.status = "running"; self.version += 1; g.save(); return
            if not g.seats: g.seats = [self.world_seat()]; self._sync_terms()     # the map and the people are made in the run, see _run
            if g.status in ("done", "stopped") and g.world.day > g.max_days: g.max_days = g.world.day + 5   # Continue: six more days
            self.stop_flag.clear(); self.pause_flag.clear(); self.blocked = ""
            if not g.started_at: g.started_at = time.time()
            g.status = "running"; g.save()
            for i in range(len(g.seats)): g.seat_dir(i)
            provs = {x["provider"] for x in g.seats} | {g.model_a["provider"], g.model_b["provider"], self.map_model_used()["provider"]}
            if any(PROVIDERS.get(p, {}).get("exe") in ("codex", "npx") for p in provs):
                note = ensure_codex_trust(g.repo)
                if note: self._record("Engine", note, "system")
        self.thread = threading.Thread(target=self._run, daemon=True); self.thread.start()

    def pause(self) -> None:
        with self.lock:
            if self.g.status == "running": self.pause_flag.set(); self.g.status = "paused"; self.g.save()

    def _kill_tree(self) -> None:
        """Kill every CLI this run started, all at once, without blocking the caller."""
        def kill(p: subprocess.Popen) -> None:
            try:
                if os.name == "nt": subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True, timeout=15)
                else: os.killpg(os.getpgid(p.pid), 9)
            except Exception:
                try: p.kill()
                except Exception: pass
        for p in list(self.procs.values()):
            if p and p.poll() is None: threading.Thread(target=kill, args=(p,), daemon=True).start()

    def stop(self) -> None:
        self.stop_flag.set(); self.pause_flag.clear(); self._kill_tree()

    def say(self, text: str) -> None:
        text = (text or "").strip()
        if text: self._record("The convener", text, "convener")

    # ---- internals
    def _term(self, i: int, text: str) -> None:
        with self.lock:
            if i >= len(self.terms): return
            for ln in text.split("\n"): self.terms[i]["lines"].append(ln); self.terms[i]["count"] += 1

    def _record(self, speaker: str, text: str, kind: str) -> None:
        with self.lock:
            g = self.g; g.turn += 1
            color = next((x.get("color") for x in g.seats if x["name"] == speaker), None)
            place = g.world.characters.get(speaker, {}).get("location") if kind == "speech" else None
            e = {"turn": g.turn, "speaker": speaker, "text": text, "kind": kind, "time": dt.datetime.now().strftime("%H:%M:%S"), "day": g.world.day, "phase": g.world.phase, "color": color, "place": place}
            g.transcript.append(e); self.version += 1
            seats = list(enumerate(g.seats)); locs = {n: c.get("location") for n, c in g.world.characters.items()}
        for i, seat in seats:   # file writes outside the lock
            vis = visible_text(e, seat["name"], locs.get(seat["name"]) if seat["name"] != "World" else None)
            if vis is None: continue
            line = "You said" if speaker == seat["name"] else f"{speaker} said"
            with (g.seat_dir(i) / "memory.md").open("a", encoding="utf-8") as fh:
                fh.write(f"\n## Day {e['day']}, turn {e['turn']} ({e['time']}), {line}:\n{vis}\n")
        g.save()

    def _set_current(self) -> None:
        names = [self.g.seats[j]["name"] for j in sorted(self.speaking) if j < len(self.g.seats)]
        self.current = ", ".join(names) if names else None; self.version += 1

    def _invoke(self, i: int, prompt: str, label: str, provider: str | None = None, model: str | None = None) -> str | None:
        """Run seat i's CLI on a prompt; return its final answer or None on failure (details in the terminal pane).
        provider and model override the seat's own for this one call (the map model drawing through the World's seat); no session is resumed or kept then."""
        g = self.g; seat = g.seats[i]; prov = PROVIDERS[provider or seat["provider"]]
        if self.stop_flag.is_set(): return None
        if shutil.which(prov["exe"]) is None:
            self._term(i, f"'{prov['exe']}' is not installed or not on PATH"); return None
        pfile = g.seat_dir(i) / f"prompt_{g.turn + 1:03d}_{int(time.time() * 1000) % 100000}.md"; pfile.write_text(prompt, encoding="utf-8")
        cmd = prov["ro_cmd"].format(ask=ASK.format(prompt_file=pfile), model=model or seat["model"])
        sid = g.cli_sessions.get(str(i)) if provider is None else None
        if sid and prov.get("resume"): cmd += prov["resume"].format(sid=sid)
        with self.lock: self.terms[i]["state"] = "speaking"; self.speaking.add(i); self._set_current()
        self._term(i, "=" * 60 + f"\n{seat['name']}: {label}\n" + "=" * 60)
        out: list[str] = []; speech: str | None = None; new_sid = None; err_tail: list[str] = []; rc = None
        try:
            proc = subprocess.Popen(cmd, cwd=g.repo, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                    encoding="utf-8", errors="replace", start_new_session=(os.name != "nt"))
            self.procs[i] = proc
            def pump(p):  # noqa: ANN001
                for ln in p.stderr: err_tail.append(ln.rstrip("\n")); del err_tail[:-8]; self._term(i, ln.rstrip("\n"))
            threading.Thread(target=pump, args=(proc,), daemon=True).start()
            for ln in proc.stdout:
                out.append(ln)
                if prov["speech"] == "claude_stream":
                    try:
                        ev = json.loads(ln)
                        if ev.get("session_id"): new_sid = ev["session_id"]
                    except Exception: pass
                    shown, final = render_claude_event(ln)
                    if shown: self._term(i, shown)
                    if final is not None: speech = final
                else: self._term(i, ln.rstrip("\n"))
            rc = proc.wait(timeout=TURN_TIMEOUT)
        except subprocess.TimeoutExpired:
            self.procs[i].kill(); self._term(i, f"[timed out after {TURN_TIMEOUT}s]")
        except Exception as exc:  # noqa: BLE001
            self._term(i, f"[engine error: {type(exc).__name__}: {exc}]")
        with self.lock:
            self.terms[i]["state"] = "waiting"; self.speaking.discard(i); self._set_current()
            if new_sid and provider is None: g.cli_sessions[str(i)] = new_sid
        if speech is None and prov["speech"] != "claude_stream": speech = "".join(out).strip()
        if speech and prov["speech"] == "copilot": speech = clean_copilot(speech)
        if (provider or seat["provider"]) in CODEX_PROVIDERS and CODEX_401.search("".join(out) + "\n".join(err_tail)):
            self.refused.add(i); speech = None
            if not self._in_codex_recovery and provider is None: threading.Thread(target=self._codex_refused, daemon=True).start()
        if not speech:
            self._term(i, f"[ended without an answer: exit {rc}]" + ("\n" + "\n".join(err_tail) if err_tail else ""))
            g.cli_sessions.pop(str(i), None); return None
        self._term(i, "\ndone.\n"); return speech

    # ---- prompts
    def _player_prompt(self, i: int, instruction: str) -> str:
        g = self.g; me = g.seats[i]["name"]; w = g.world
        my_place = w.characters[me]["location"]; ties = w.ties_of(me)
        seen = int(g.last_seen.get(str(i), 0))
        # not the day's story: only what touched this person (happened where they are, named them, or was done by someone they are tied to)
        new = [(e, touched_text(e, me, my_place, ties)) for e in g.transcript[seen:]]; new = [(e, v) for e, v in new if v]
        parts = [PLAYER_RULES, f"\nThe world:\n{g.world_text}\n", "THE MAP, known to everyone (the only places and things that exist):\n" + map_text(w.map) + "\n",
                 f"Day {w.day}, {season_of(w.day)}, {w.weather}. Everyone who lives in the valley: " + ", ".join(w.titled(c["name"]) for c in w.living() if c["name"] != me) + ".\n",
                 w.sheet(me), "\n" + (w.duty_brief(me) if w.phase == "morning" else "YOUR DUTIES: " + (", ".join(DUTIES[k]["label"] for k in w.characters[me].get("duties", [])) or "none") + ".") + "\n", "\n" + w.surroundings(me), "\nWHAT IS GOING ON IN THE VALLEY (unresolved, everyone has heard):\n" + w.threads_text() + "\n", f"\nYour memory of everything you have witnessed is in {g.seat_dir(i) / 'memory.md'} (yours alone).\n"]
        u = self.day_urges.get(me) or []
        if u: parts.append("YOUR URGES TODAY, which are your nature and not a suggestion; act on at least one of them, in words or in your ACTION, and do not apologize for it:\n" + "\n".join(f"- {x}" for x in u) + "\n")
        if new:
            parts.append("WHAT TOUCHED YOU since your last turn. Only this reached you: words spoken where you stand, things done to you or named you, and what the people you are tied to did. Do not repeat any of it back. React to it, or ignore it, as you would:\n")
            for e, v in new: parts.append(f"--- {e['speaker']} (day {e.get('day', 0)}) ---\n{v}\n")
        parts.append(f"Now: {instruction}")
        return "\n".join(parts)

    def _world_prompt(self, outcomes: list[dict]) -> str:
        """Only the engine's resolved outcomes reach the World. No sheets, no map, no ledger, no ties, no talk."""
        g = self.g; w = g.world
        lines = "\n".join(f"- {o['text']}" for o in outcomes) or "- Nothing happened this afternoon that is worth a line."
        return "\n".join([WORLD_RULES, f"\nDay {w.day}, {season_of(w.day)}, {w.weather}. The afternoon's outcomes, settled by the engine, in order:\n{lines}",
                           "\nTell them, one line each, in that order, the person's name first and a colon, at most two sentences each, and nothing else."])

    # ---- the day loop
    def _run(self) -> None:
        g = self.g; w = g.world
        try:
            if not w.created:
                if len(g.seats) <= 1:            # a fresh game: the map first, then the people, then their lives
                    self.prepare_map()
                    if self.stop_flag.is_set(): return
                    self._build_people()
                self._create_world()
            while not self.stop_flag.is_set() and w.created:
                while self.pause_flag.is_set() and not self.stop_flag.is_set(): time.sleep(0.5)
                if self.stop_flag.is_set(): break
                if w.day > g.max_days or (g.max_minutes and time.time() - g.started_at > g.max_minutes * 60) or len(w.living()) <= 1:
                    self._epilogue(); break
                if (w.day_report or {}).get("day") != w.day: self._dawn()
                if self._prime_day() or self.stop_flag.is_set(): break
                self._morning_phase()
                if self.stop_flag.is_set(): break
                self._afternoon_phase()
                if self.stop_flag.is_set(): break
                self._world_phase()
                if self.stop_flag.is_set(): break
                self._evening_phase()
                if self.stop_flag.is_set(): break
                with self.lock: w.end_day(); self.version += 1
                g.save(chronicle=True)
        finally:
            with self.lock: self.current = None; g.status = "stopped" if self.stop_flag.is_set() and w.day < g.max_days else "done"; g.save(chronicle=True)

    def _create_world(self) -> None:
        g = self.g; w = g.world
        names = [c["name"] for c in w.characters.values()]
        w.seed_wants(self.rng)
        stats = "\n".join(f"- {c['name']}: STR {c['str']} SPD {c['spd']} HP {c['hp_max']} gold {c['gold']}, currently at {c['location']}; wants, in plain terms, {c['goal']['text']}" for c in w.characters.values())
        prompt = "\n".join([WORLD_RULES, f"\nThe world:\n{g.world_text}\n", "THE MAP (fixed):\n" + map_text(w.map) + "\n", "The engine has rolled these people. Give each a life. Homes must be places on the map.",
            stats, "\nWrite a short opening narration (the valley waking, the early frost, the rider's news) and then a fenced ```json block, exactly this shape:",
            '```json\n{"people":[{"name":"Name","trade":"miller","home":"The mill","personality":"one line","secret":"one line, only they know it","fear":"one line","want":"one line, what they want more than anything, in their own terms, built around the plain want the engine rolled for them"}],'
            '"relations":[{"a":"Name","b":"OtherName","type":"spouse","feeling":3,"trust":2,"mutual":true,"why":"married twelve years; he drinks, she keeps the ledger"}]}\n```',
            "One entry per name, every name, names exact. Make them different from each other: some rich, some poor, some liked, some feared, some with dangerous secrets that touch other people in this list. "
            "Then give the valley a web of ties in \"relations\": at least eight, each with a \"why\" (one line of history: how they met, what happened, what is owed), using types spouse, lover, kin, friend, rival, enemy, creditor, debtor, master, servant; feeling and trust run from -5 (hate, would knife them) to 5 (love, trust with their life). "
            "Make some ties one-sided (mutual false, then a second entry the other way with different numbers): an unrequited love, a servant who hates a master who trusts him, a debtor who smiles at a creditor he loathes."])
        self._term(0, "creating the world...")
        people: dict = {}; out = None
        for attempt in range(2):
            if self.stop_flag.is_set(): return
            out = self._invoke(0, prompt if attempt == 0 else prompt + "\n\nYour last reply had no valid JSON block. Reply again with the narration and the fenced json block.", "creation")
            data = extract_json(out or "") or {}
            people = {str(p.get("name")): p for p in data.get("people", []) if isinstance(p, dict)}
            if out and len(people) >= max(1, len(names) // 2): break
        if self.stop_flag.is_set() or not out: return
        for n in names:
            p = people.get(n, {})
            c = w.characters[n]
            sd = lambda v, alt: strip_dashes(str(v or alt))   # noqa: E731
            c["trade"] = sd(p.get("trade"), "villager")[:40]; c["home"] = str(p.get("home") or c["location"])[:40]
            c["personality"] = sd(p.get("personality"), "keeps their own counsel")[:200]
            c["secret"] = sd(p.get("secret"), "nothing worth telling")[:200]; c["fear"] = sd(p.get("fear"), "the cold")[:200]
            c["want"] = sd(p.get("want"), "to see spring")[:200]
            if p.get("home") in w.map: c["location"] = p["home"]
        w.seed_all_relations(self.rng); w.seed_duties(self.rng); w.seed_pastimes(self.rng)
        for rr in data.get("relations", []) or []:
            if isinstance(rr, dict):
                w.set_rel(str(rr.get("a", "")), str(rr.get("b", "")), rr.get("type"), rr.get("feeling"), rr.get("trust"), why=str(rr.get("why", "") or "an old tie"))
                if rr.get("mutual", True): w.set_rel(str(rr.get("b", "")), str(rr.get("a", "")), rr.get("type"), rr.get("feeling"), rr.get("trust"), why=str(rr.get("why", "") or "an old tie"))
        w.created = True; w.day = 1
        self._record("World", (strip_dashes(strip_json(out or "The valley wakes.")) + "\n\n" + w.standings_table()), "world")

    def _dawn(self) -> None:
        """The valley wears a little: weather, spoilage, hunger, cold, sickness, and the dead by morning. Before anyone speaks."""
        g = self.g; w = g.world
        with self.lock:
            w.seed_missing(self.rng)                                                       # anyone or anything still unseeded
            rep = w.dawn(self.rng); roster = w.assign_day(self.rng); self.version += 1
        lines = list(rep["lines"])
        dumped = [f"{DUTIES[k]['label']} (dumped on {r['dumped_on']})" if r.get("dumped_on") else DUTIES[k]["label"] for k, r in roster["duties"].items() if r["unclaimed"]]
        if dumped: lines.append("Nobody holds: " + ", ".join(dumped) + ".")
        for e in roster.get("emergencies", []):
            if e.get("pulled"): lines.append(f"Emergency, {e['text']}: {', '.join(e['pulled'])} pulled to it.")
        rep["lines"] = lines
        self._record("The valley", "\n".join(lines), "dawn")
        g.save()

    def _prime_day(self) -> bool:
        """Codex is primed once a day, alone, before the seats run in parallel. A refusal pauses the run; after the pause,
        whether the recovery lifted it or the convener signed in and pressed Resume, it primes again before going on. True if the run must stop."""
        g = self.g; w = g.world
        while self.codex_provider() and not self.stop_flag.is_set():
            self.reprime = False
            if self.prime_codex(f"priming for day {w.day}"): break
            self._codex_refused()
            while self.pause_flag.is_set() and not self.stop_flag.is_set(): time.sleep(0.5)
        return self.stop_flag.is_set()

    def _wait_out_recovery(self) -> None:
        """A seat was refused: the recovery thread is starting or running. Wait for it, and for any pause it leaves behind."""
        for _ in range(40):
            if self._in_codex_recovery or self.pause_flag.is_set() or self.stop_flag.is_set(): break
            time.sleep(0.25)
        while (self._in_codex_recovery or self.pause_flag.is_set()) and not self.stop_flag.is_set(): time.sleep(0.5)
        if self.reprime and not self.stop_flag.is_set() and self.codex_provider():
            self.reprime = False; self.prime_codex(f"priming again after the convener signed in")

    def _able_seats(self) -> list[int]:
        g = self.g; w = g.world
        return [i for i, seat in enumerate(g.seats) if i > 0 and seat["name"] in w.characters and w.able(w.characters[seat["name"]])]

    def _touched(self, i: int) -> bool:
        """Something reached this person since their last turn, or their nature is pushing them today."""
        g = self.g; w = g.world; me = g.seats[i]["name"]; c = w.characters[me]
        if self.day_urges.get(me): return True
        seen = int(g.last_seen.get(str(i), 0)); ties = w.ties_of(me)
        return any(touched_text(e, me, c["location"], ties) for e in g.transcript[seen:])

    def _round(self, seats: list[int], instruction, label: str, on_reply, reactions: bool = True) -> None:
        """One round of prompts to the given seats, in parallel. With reactions on, anyone named or whispered to at the same place
        gets a turn to answer, and the convener's @mentions wake people. on_reply(i, text) takes each answer that is not PASS."""
        g = self.g; w = g.world
        reacted: set[int] = set(); queue = list(seats); threads: dict[int, threading.Thread] = {}
        name_to_i = {g.seats[i]["name"].lower(): i for i in self._able_seats()}

        def worker(i: int, react: bool) -> None:
            base = instruction(i) if callable(instruction) else instruction
            instr = ("Someone spoke to you or acted on you, above. Answer them in character, in one to three sentences, or reply exactly PASS. " + base) if react else base
            text = self._invoke(i, self._player_prompt(i, instr), f"day {w.day}, {label}")
            if text is None and i in self.refused and not self.stop_flag.is_set():
                self.refused.discard(i); self._wait_out_recovery()
                if not self.stop_flag.is_set(): self._term(i, "(asked again after the sign in came back)"); text = self._invoke(i, self._player_prompt(i, instr), f"day {w.day}, {label}, again")
            g.last_seen[str(i)] = len(g.transcript)
            if not text:
                self._record("Engine", f"{g.seats[i]['name']} gave no answer this turn (see its terminal).", "system"); return
            if text.strip().upper().rstrip(".") == "PASS": self._term(i, "(passed)"); on_reply(i, None); return
            text = cap_speech(strip_dashes(text))         # one to three sentences, no dashes, the ACTION line kept whole
            for t in whisper_targets(text):
                tc = next((c for c in w.living() if c["name"].lower() == t), None)
                if tc and tc["location"] != w.characters[g.seats[i]["name"]]["location"]:
                    self._term(i, f"(your whisper to {tc['name']} went nowhere: they are at {tc['location']}, you are at {w.characters[g.seats[i]['name']]['location']})")
            on_reply(i, text)
            if not reactions: return
            wts = whisper_targets(text)
            with self.lock:
                here = w.characters[g.seats[i]["name"]]["location"]
                for nm, j in name_to_i.items():
                    if w.characters[g.seats[j]["name"]]["location"] != here: continue
                    if j != i and j not in reacted and j not in threads and (re.search(r"(?<![\w@])" + re.escape(g.seats[j]["name"]) + r"\b", text, re.I) or nm in wts):
                        reacted.add(j); queue.append(j)

        seen_len = len(g.transcript)
        while not self.stop_flag.is_set():
            while self.pause_flag.is_set() and not self.stop_flag.is_set(): time.sleep(0.5)
            if len(g.transcript) != seen_len:            # the convener spoke: anyone @mentioned is woken to answer now
                for e in g.transcript[seen_len:]:
                    if e["kind"] == "convener":
                        with self.lock:
                            for nm, j in name_to_i.items():
                                if nm in mentions(e["text"]) and j not in threads and j not in queue: reacted.add(j); queue.append(j)
                seen_len = len(g.transcript)
            for j in [j for j, t in threads.items() if not t.is_alive()]: threads.pop(j)
            with self.lock:
                launch = [j for j in queue if j not in threads]; queue = [j for j in queue if j in threads]
            for j in launch:
                t = threading.Thread(target=worker, args=(j, j in reacted), daemon=True); threads[j] = t; t.start()
            if not threads and not queue: break
            time.sleep(0.5)

    def _speech_part(self, text: str) -> str:
        """What a person said, without their ACTION line."""
        return "\n".join(ln for ln in text.split("\n") if not re.match(r"^\s*ACTION:", ln, re.I)).strip()

    def _morning_phase(self) -> None:
        """Duties. Everyone able with work is asked for WORK, REFUSE, or a free action, which is a skip. The engine settles all of it,
        writes one line per person, lands the cost of what nobody did, and lets a neighbour complain after two days."""
        g = self.g; w = g.world
        with self.lock: w.phase = "morning"; self.version += 1
        self.day_urges = {g.seats[i]["name"]: urges(w.characters[g.seats[i]["name"]], w, self.rng) for i in self._able_seats()}
        outcomes: dict[str, list[dict]] = {}
        working = [i for i in self._able_seats() if w.characters[g.seats[i]["name"]].get("duties") or w.characters[g.seats[i]["name"]].get("dumped") or w.characters[g.seats[i]["name"]].get("emergency")]

        def on_reply(i: int, text: str | None) -> None:
            me = g.seats[i]["name"]
            if text:
                said = self._speech_part(text)
                if said: self._record(me, said, "speech")
            act = action_line(text or "") or ""
            with self.lock: outcomes[me] = w.resolve_morning(me, act, self.rng); self.version += 1

        instr = ("It is morning. Your ACTION line must begin with WORK (do all your work today), WORK followed by one duty's name (do that one and skip the rest), "
                 "REFUSE (give up your duties; they go unclaimed and people notice), or anything else, which counts as skipping your work today and costs the same. "
                 "The engine does the work and says what came of it; never describe the outcome yourself. Speak only if something touched you; otherwise give the ACTION line alone.")
        self._round(working, instr, "morning", on_reply, reactions=False)
        if self.stop_flag.is_set(): return
        with self.lock:
            for i in self._able_seats():
                me = g.seats[i]["name"]
                if me not in outcomes and (w.characters[me].get("duties") or w.characters[me].get("dumped") or w.characters[me].get("emergency")): outcomes[me] = w.resolve_morning(me, "", self.rng)
            for c in w.living():
                if not w.able(c): outcomes[c["name"]] = w.resolve_morning(c["name"], "", self.rng)
            done = {r["duty"] for rs in outcomes.values() for r in rs if r.get("kind") == "work" and r.get("duty")}
            m = w.end_morning(done, self.rng); self.version += 1
        lines = [r["text"] for me in sorted(outcomes, key=lambda n: w.characters[n]["seat"]) for r in outcomes[me] if r.get("text")]
        undone = [u["text"] for u in m["undone"]]
        text = "\n".join(lines) or "Nobody had work to do."
        if undone: text += "\n\nUNDONE: " + " ".join(undone)
        if m["complaints"]: text += "\n\n" + "\n".join(m["complaints"])
        self._record("The valley", text, "morning"); g.save()

    def _afternoon_phase(self) -> None:
        """Free actions, from the people something touched or whose nature is pushing them. Quiet days are allowed."""
        g = self.g; w = g.world
        with self.lock: w.phase = "afternoon"; self.version += 1
        seats = [i for i in self._able_seats() if self._touched(i)]
        acted: set[int] = set()

        def on_reply(i: int, text: str | None) -> None:
            if not text: return
            me = g.seats[i]["name"]; self._record(me, text, "speech")
            a = action_line(text)
            if a and i not in acted:
                with self.lock:
                    acted.add(i); w.pending.append({"who": me, "text": a, "turn": g.turn})
                    w.set_activity(me, "acting", a[:48], [{"place": w.characters[me]["location"], "what": a[:48], "dur": 8}]); self.version += 1

        instr = ("It is afternoon, your free time. If something touched you today or you have a want to act on, act on it now: speak if you must, then one ACTION line. "
                 "If nothing presses, reply exactly PASS and you will spend the afternoon on your pastime.")
        self._round(seats, instr, "afternoon", on_reply, reactions=True)
        if self.stop_flag.is_set(): return
        # everyone else spends the afternoon on their pastime, on the map; the same place makes company, and company talks
        with self.lock:
            done = [w.do_pastime(g.seats[i]["name"], self.rng) for i in self._able_seats() if i not in acted]
            groups = w.pastime_groups(); self.version += 1
        if done:
            lines = [d["text"] for d in done]
            for pl, ns in groups.items(): lines.append(f"At {pl}: {', '.join(ns)} together.")
            self._record("The valley", "\n".join(lines), "afternoon"); g.save()
        if groups:
            name_seat = {g.seats[i]["name"]: i for i in self._able_seats()}
            talkers = [name_seat[n] for ns in groups.values() for n in ns if n in name_seat]
            def instr_for(i: int) -> str:
                me = g.seats[i]["name"]; pl = w.characters[me]["location"]; others = [n for n in groups.get(pl, []) if n != me]
                return (f"You are {PASTIMES[w.characters[me]['pastime']]['verb']} at {pl} with {', '.join(others)}. Say something to them if you have anything to say, in one to three sentences, or reply exactly PASS. No ACTION line.")
            def on_talk(i: int, text: str | None) -> None:
                if not text: return
                said = self._speech_part(text)
                if said: self._record(g.seats[i]["name"], said, "speech")
            self._round(talkers, instr_for, "afternoon company", on_talk, reactions=True)

    def _evening_phase(self) -> None:
        """Dusk. Everyone goes home, or to the inn if it pulls them, and the people something touched talk where they are. No actions."""
        g = self.g; w = g.world
        with self.lock:
            w.phase = "evening"; moves = w.evening_places(self.rng); self.version += 1
        inn = next((p for p, d in w.map.items() if d.get("kind") == "inn"), None)
        at_inn = [c["name"] for c in w.living() if inn and c["location"] == inn]
        with self.lock: got = w.check_wants(self.rng)
        self._record("The valley", f"Evening. " + (f"At {inn}: {', '.join(at_inn)}. " if at_inn else "") + "Everyone else is at home." + ("".join(" " + x["text"] for x in got)), "evening")
        seats = [i for i in self._able_seats() if self._touched(i)]

        def on_reply(i: int, text: str | None) -> None:
            if not text: return
            me = g.seats[i]["name"]; said = self._speech_part(text)
            if action_line(text): self._term(i, "(no actions in the evening; only what you said was kept)")
            if said: self._record(me, said, "speech")

        instr = "It is evening. You are where you are for the night, with whoever is there. Say something to them if you have something to say, in one to three sentences, or reply exactly PASS. No ACTION line tonight."
        self._round(seats, instr, "evening", on_reply, reactions=True)
        g.save()

    def _world_phase(self) -> None:
        """The afternoon, settled by the engine, then told by the World. The World invents nothing: its lines are checked."""
        g = self.g; w = g.world
        told_fate = list(w.fate); told_reached = list(w.reached); elog: list[str] = []
        w.spread_fires(self.rng, elog); events = w.draw_events(g.drama, self.rng, elog)
        actions = list(w.pending); w.pending = []
        outcomes: list[dict] = [{"kind": "fate", "who": "", "text": f} for f in told_fate] + [{"kind": "event", "who": "", "text": e} for e in events]
        outcomes += w.resolve_afternoon(actions, self.rng, elog)
        got = w.check_wants(self.rng)
        outcomes += [{"kind": "want", "who": x["who"], "text": x["text"]} for x in told_reached + got]
        w.fate = [f for f in w.fate if f not in told_fate]; w.reached = [x for x in w.reached if x not in told_reached and x not in got]
        with self.lock: self.version += 1
        g.save()
        engine_text = "\n".join(o["text"] for o in outcomes)
        out = self._invoke(0, self._world_prompt(outcomes), f"day {w.day} resolution") if outcomes else ""
        if self.stop_flag.is_set(): return
        kept, dropped = w.check_narration(strip_dashes(strip_json(out or "")), outcomes)
        text = cap_outcomes(kept) if kept.strip() else engine_text
        if not text.strip(): text = "Nothing happened this afternoon that is worth a line."
        if dropped: elog.append("the World's narration was checked: " + "; ".join(dropped))
        if not out and outcomes: elog.append("the World gave no narration; the engine's own lines stand")
        self._record("World", text + "\n\n" + w.standings_table(), "world")
        if elog: self._record("Engine", "Adjustments: " + "; ".join(elog), "system")
        g.save()

    def _epilogue(self) -> None:
        import telegram
        g = self.g; w = g.world
        prompt = "\n".join([WORLD_RULES, f"\nThe world:\n{g.world_text}\n", "The year is over. Here is the final state:\n" + w.standings_table(),
                            "\nWrite the chronicle's closing: what became of the valley and of each person, living, dead, and gone, in the order they mattered. No json block."])
        out = self._invoke(0, prompt, "epilogue")
        self._record("World", strip_dashes(out or "The chronicle ends here.") + "\n\n" + w.standings_table(), "epilogue")
        dead = [c["name"] for c in w.characters.values() if not c["alive"]]
        telegram.notify(f"{g.title or 'Terraceilia'}: the year is over on day {w.day}. "
                        f"{len(w.living())} still living, {len(dead)} dead" + (": " + ", ".join(dead[:8]) if dead else "") + ".", "finish")

