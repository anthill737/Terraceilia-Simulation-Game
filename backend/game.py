"""One game: its saved state, and the engine loop that runs a year of days."""
from __future__ import annotations
import collections, datetime as dt, json, os, random, re, shutil, subprocess, threading, time
from pathlib import Path

from agents import ASK, PROVIDERS, clean_copilot, render_claude_event, ensure_codex_trust
from engine import (GAMES, NAMES, World, roll_character, now_id, map_text, extract_json, strip_json, action_line,  # noqa: F401
                    thought_line, note_log, whisper_targets, visible_text, urges, mentions, validate_map, strip_dashes, cap_speech, cap_outcomes, touched_text, starting_ledger, season_of, DUTIES, SOCIAL, clean_voice, sentences, roll_voice,
                    DRAFT_TIES, REROLLABLE, new_seed, reroll_field, tags_phrase)
from prompts import DEFAULT_WORLD, PLAYER_RULES, WORLD_RULES, map_prompt

import runner
import connect

TAIL = 400
# Nothing here reads or writes any sign in: a refusal pauses the run and asks the convener to sign in
# again; the CLI owns its own credentials.
CODEX_PROVIDER = "Codex"
CODEX_DEFAULT = "gpt-5.6-luna"
PROBE_PROMPT = "Reply with exactly the single word: ready"

def clean_line(text: str | None) -> str | None:
    """One sentence, in plain words, or None: no ACTION or THOUGHT line, no name in front, no quotes, no PASS, no dashes."""
    if not text: return None
    lines = [ln.strip() for ln in strip_dashes(text).split("\n") if ln.strip() and not re.match(r"^\s*(ACTION|THOUGHT)\s*:", ln, re.I)]
    if not lines: return None
    quotes = '"\u201c\u201d\''
    ln = re.sub(r"^[A-Z][\w' -]{0,30}:\s*", "", lines[0].strip()).strip().strip(quotes).strip()
    if not ln or ln.upper().rstrip(".") == "PASS" or ln.startswith("```"): return None
    first = sentences(ln)[0] if sentences(ln) else ln
    return first.strip().strip(quotes).strip()[:240] or None


# ---------------------------------------------------------------- a game (persisted)
class Game:
    def __init__(self, gid: str, d: dict | None = None) -> None:
        d = d or {}
        self.draft = bool(d.get("draft", False))                     # a draft is not a game: it lives under games/drafts and has no game folder
        self.draft_narration = d.get("draft_narration", ""); self.draft_note = d.get("draft_note", "")
        self.id = gid; self.dir = (GAMES / "drafts" / gid) if self.draft else (GAMES / gid)
        self.title = d.get("title", "")
        self.created = d.get("created", dt.datetime.now().isoformat(timespec="minutes"))
        self.world_text = d.get("world_text", DEFAULT_WORLD)
        self.players = d.get("players", 20)
        # an empty model means the first model of that provider that answers the probe; nothing is hardcoded
        self.model_a = d.get("model_a", {"provider": "Claude Code", "model": ""})
        self.model_b = d.get("model_b", {"provider": CODEX_PROVIDER, "model": CODEX_DEFAULT})   # Codex villagers default to luna
        self.world_model = d.get("world_model", {"provider": "Claude Code", "model": ""})
        self.people_seed = int(d.get("people_seed") or 0)    # the roll the people came from; the same seed gives the same people on any map
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
        self.bad_models: list[str] = list(d.get("bad_models", []))      # "provider|model" refused with a model error in this game; never probed again
        self.probe_day: dict[str, int] = dict(d.get("probe_day", {}))   # seat index -> the day it was last probed; one probe per seat per day
        self.world = World(d.get("world"))

    def to_dict(self) -> dict:
        return {"title": self.title, "created": self.created, "world_text": self.world_text, "players": self.players, "draft": self.draft, "draft_narration": self.draft_narration, "draft_note": self.draft_note,
                "model_a": self.model_a, "model_b": self.model_b, "world_model": self.world_model, "max_days": self.max_days,
                "map_source": self.map_source, "map_model": self.map_model, "people_seed": self.people_seed,
                "max_minutes": self.max_minutes, "drama": self.drama, "repo": self.repo, "seats": self.seats, "transcript": self.transcript,
                "turn": self.turn, "status": self.status, "started_at": self.started_at, "cli_sessions": self.cli_sessions,
                "last_seen": self.last_seen, "bad_models": self.bad_models, "probe_day": self.probe_day, "world": self.world.to_dict()}

    def save(self, chronicle: bool = False) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / ("draft.json" if self.draft else "game.json")).write_text(json.dumps(self.to_dict()), encoding="utf-8")
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
                       f"Personality: {', '.join(f'{k} {v}' for k, v in (c.get('traits') or {}).items())}",
                       f"Character: {c['personality']}", f"Secret: {c['secret']}", f"Fear: {c['fear']}", f"Want: {c['want']}", "", "Relationships:", w.relations_text(c["name"]).replace("You ", f"{c['name']} ").replace("you ", f"{c['name']} "), ""]
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
        if not f.exists(): f = GAMES / "drafts" / gid / "draft.json"
        if not f.exists(): return None
        try:
            d = json.loads(f.read_text(encoding="utf-8")); d["draft"] = f.name == "draft.json"
            return cls(gid, d)
        except Exception: return None

    def seat_dir(self, i: int) -> Path:
        d = self.dir / f"seat{i}"; d.mkdir(parents=True, exist_ok=True)
        m = d / "memory.md"
        if not m.exists(): m.write_text(f"# {self.seats[i]['name'] if i < len(self.seats) else i}: memory\n\n(Nothing yet.)\n", encoding="utf-8")
        return d


_GAMES_CACHE: dict[str, tuple[float, dict]] = {}


def list_drafts() -> list[dict]:
    """Every draft, newest first: a draft is a valley being chosen, not a game, and lives apart from the game folders."""
    out = []
    for f in sorted(GAMES.glob("drafts/*/draft.json"), reverse=True):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            out.append({"id": f.parent.name, "title": d.get("title") or "Terraceilia", "created": d.get("created", ""), "status": "draft", "day": 0,
                        "people": len(d.get("world", {}).get("characters", {}))})
        except Exception: continue
    return out


def list_games() -> list[dict]:
    """Index of games. Parses a game.json only when its mtime changed, so polling stays cheap. Drafts are not games."""
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
        self.testing: dict = {}                 # while Start is testing the seats: done, total, now, names
        self.generating: str = ""               # while a draft is being rolled: all, people, map, reroll <name>, add <name>
        self.talked: set[str] = set()           # groups already talked, one round per group per beat
        self.talks: list[dict] = []             # every talk round run this game: day, phase, beat, place, names
        self.procs: dict[int, subprocess.Popen] = {}; self.speaking: set[int] = set()
        self.thread: threading.Thread | None = None
        self.stop_flag, self.pause_flag = threading.Event(), threading.Event()
        self.rng = random.Random()
        self.version = 0
        self.day_urges: dict[str, list[str]] = {}
        self.map_generating = False
        self.blocked = ""                       # why the run is stuck, in words the convener can act on
        self.auth_lock = threading.Lock()
        self.last_error: dict[int, dict] = {}   # seat -> what the runner said the last time it failed: kind, message, cmd
        self._sync_terms(); self._migrate()

    def _migrate_models(self) -> None:
        """A save whose Codex seats sit on a retired model moves them to the default, once, with one chronicle line."""
        g = self.g; moved: list[tuple[str, str]] = []
        def retired(m: dict) -> bool:
            return m.get("provider") == CODEX_PROVIDER and bool(m.get("model")) and m["model"] not in PROVIDERS[m["provider"]]["models"]
        for x in g.seats:
            if retired(x): moved.append((x["name"], x["model"])); x["model"] = CODEX_DEFAULT; g.cli_sessions.pop(str(g.seats.index(x)), None)
        changed = bool(moved)
        for m in (g.model_a, g.model_b, g.world_model):
            if retired(m): m["model"] = CODEX_DEFAULT; changed = True
        if moved:
            olds = sorted({m for _, m in moved}); names = [n for n, _ in moved]
            self._record("Engine", f"{', '.join(olds)} {'is' if len(olds) == 1 else 'are'} no longer offered; {', '.join(names)} now play{'s' if len(names) == 1 else ''} on {CODEX_DEFAULT}.", "system")
        if changed: g.save()

    def _migrate(self) -> None:
        """A game saved before some part of the colony existed gets that part seeded, once, as a new game would, and the chronicle says so."""
        g = self.g; w = g.world
        self._migrate_models()
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

    # ---- what a failed call means, and what to do about it
    def _auth_refused(self, provider: str) -> None:
        """A seat was refused for want of a sign in. Pause at once and say what the convener has to do. Nothing is restored:
        the CLI owns its credentials, and the convener signs in again and presses Resume."""
        with self.auth_lock:
            with self.lock:
                if self.g.status != "running": return
                self.pause_flag.set(); self.g.status = "paused"; self.blocked = f"{provider} signed out, sign in and press Resume"; self.version += 1; self.g.save()
            self._record("Engine", f"{provider} refused a call for want of a sign in. The run is paused. Open the gear, then Connections, sign in to {provider}, and press Resume.", "system")

    def _stop_with(self, why: str) -> None:
        with self.lock: self.blocked = why; self.version += 1
        self._record("Engine", why, "system"); self.stop_flag.set(); self._kill_tree()

    def resolve_model(self, provider: str, model: str) -> str:
        """The model a call is made with: the seat's own, or for an empty one the first of that provider that answered the probe."""
        return model or connect.first_accessible(provider) or ""

    def ask(self, i: int, prompt: str, label: str, provider: str | None = None, model: str | None = None) -> str | None:
        """One turn's worth of asking a seat, with the error policy: a rate limit or server error waits with backoff; a model
        error moves the seat to the first model that answered the probe; a sign in refusal pauses the run until Resume; a
        launcher bug stops the run with the command; anything else is asked again once, then the seat is benched for the turn."""
        g = self.g; prov_name = provider or g.seats[i]["provider"]; waits = 0; retried = False; switched = False; auth_tries = 0
        while not self.stop_flag.is_set():
            text = self._invoke(i, prompt, label, provider=provider, model=model)
            if text is not None: return text
            err = self.last_error.get(i)
            if not err: return None
            kind, msg = err["kind"], err["message"]
            if kind == "launcher":
                self._stop_with(f"A launcher bug stopped the run: {prov_name} was started without its credentials ({msg}). The command that was built: {err['cmd']}"); return None
            if kind == "auth":
                connect.record_probe(prov_name, err.get("model", ""), False, msg)
                if auth_tries >= 2: break
                auth_tries += 1; self._auth_refused(prov_name)
                while self.pause_flag.is_set() and not self.stop_flag.is_set(): time.sleep(0.5)
                continue
            if kind == "rate":
                if waits >= len(runner.BACKOFF): break
                wait = runner.BACKOFF[waits]; waits += 1
                self._term(i, f"[{prov_name} asked us to wait: {msg}; waiting {int(wait)} seconds]"); time.sleep(wait); continue
            if kind == "model" and not switched and provider is None:
                switched = True; seat = g.seats[i]; self.mark_bad(seat["provider"], err.get("model", "")); better = self.find_model(i, seat["provider"], exclude=seat["model"])
                if better and better != seat["model"]:
                    old = seat["model"]
                    with self.lock: seat["model"] = better; g.cli_sessions.pop(str(i), None); self.version += 1; g.save()
                    self._record("Engine", f"{seat['name']}'s model {old or '(none)'} was refused ({msg}); {seat['name']} now uses {better}, the first {seat['provider']} model that answered a test.", "system")
                    continue
            if not retried:
                retried = True; self._term(i, f"[asking again once: {msg}]"); continue
            break
        if self.stop_flag.is_set(): return None
        err = self.last_error.get(i) or {}
        self._record("Engine", f"{g.seats[i]['name']} is benched for this turn. {prov_name} said: {err.get('message', 'no answer')}", "system")
        return None

    def probe_model(self, provider: str, model: str, i: int = 0) -> tuple[bool, str]:
        """One tiny request through the same launcher and environment a turn uses. Records the result for Connections, and a
        model error marks that model bad for the rest of this game."""
        text = self._invoke(i if i < len(self.g.seats) else 0, PROBE_PROMPT, f"test {provider} {model}", provider=provider, model=model)
        err = self.last_error.get(i if i < len(self.g.seats) else 0) or {}
        ok = text is not None; msg = "" if ok else err.get("message", "no answer")
        connect.record_probe(provider, model, ok, msg)
        if not ok and err.get("kind") == "model": self.mark_bad(provider, model)
        return ok, msg

    def is_bad(self, provider: str, model: str) -> bool:
        return bool(model) and f"{provider}|{model}" in self.g.bad_models

    def mark_bad(self, provider: str, model: str) -> None:
        """A model refused with a model error (404, no access) is never probed again in this game."""
        if model and f"{provider}|{model}" not in self.g.bad_models: self.g.bad_models.append(f"{provider}|{model}")

    def can_probe(self, i: int | str) -> bool:
        """Seat i (or one of the three chosen models on a fresh game, keyed a, b, w) is probed once a day at most."""
        return self.g.probe_day.get(str(i)) != self.g.world.day

    def note_probed(self, i: int | str) -> None:
        self.g.probe_day[str(i)] = self.g.world.day

    def find_model(self, i: int | str, provider: str, exclude: str = "") -> str:
        """The first of the provider's models that answered: from the probes already on record, else by probing the list once for
        seat i, skipping models refused in this game. Empty when none answers or seat i has already been probed today."""
        for m in PROVIDERS.get(provider, {}).get("models", []):
            if m != exclude and not self.is_bad(provider, m) and connect.probes_of(provider).get(m, {}).get("ok"): return m
        if not self.can_probe(i): return ""
        self.note_probed(i); i = i if isinstance(i, int) else 0
        for cand in PROVIDERS.get(provider, {}).get("models", []):
            if self.stop_flag.is_set(): return ""
            if cand == exclude or self.is_bad(provider, cand): continue
            ok, _ = self.probe_model(provider, cand, i)
            if ok: return cand
        return ""

    def preflight(self) -> bool:
        """Before anything is asked of anyone, every seat is probed once (and once at most per seat per day). A sign in refusal
        stops Start and says so. A model refusal does not: the seat moves to the first model of its provider that answered, the
        seat is saved, the chronicle says so, and the run starts. A seat with no model chosen takes the first that answers. On a
        fresh game the three chosen models stand in for the seats not yet built."""
        g = self.g
        if not g.seats: g.seats = [self.world_seat()]; self._sync_terms()
        targets: list[tuple[dict, int | str, str]] = [(x, i, x["name"]) for i, x in enumerate(g.seats)]
        if len(g.seats) <= 1:
            for m, key, who in ((g.model_a, "a", "the first villagers' model"), (g.model_b, "b", "the second villagers' model"), (g.world_model, "w", "the World's model")):
                if not any(m is t[0] for t in targets): targets.append((m, key, who))
        with self.lock:
            self.current = "preflight"; self.testing = {"done": 0, "total": len(targets), "now": "", "names": []}; self.version += 1
        seen: dict[tuple[str, str], tuple[bool, str, str]] = {}      # (provider, model) -> (ok, message, kind) this preflight
        try:
            for ref, i, who in targets:
                with self.lock: self.testing["now"] = who; self.version += 1
                if self.stop_flag.is_set(): return False
                prov, model = ref["provider"], ref.get("model", ""); msg = ""; si = i if isinstance(i, int) else 0
                if model and not self.is_bad(prov, model):
                    if (prov, model) in seen: ok, msg, kind = seen[(prov, model)]
                    elif not self.can_probe(i): ok, msg, kind = True, "", ""      # probed today already; the record stands
                    else:
                        self.note_probed(i); ok, msg = self.probe_model(prov, model, si); kind = "" if ok else (self.last_error.get(si if si < len(g.seats) else 0) or {}).get("kind", "other")
                        seen[(prov, model)] = (ok, msg, kind)
                    if ok: self._tested(who); continue
                    if kind == "auth": self._stop_with(f"{prov} refused the test for want of a sign in ({msg}). Open the gear, then Connections, and sign in. Nothing was started."); return False
                    if kind == "launcher": self._stop_with(f"A launcher bug stopped the run before it began: {msg}. Nothing was started."); return False
                    if kind != "model": self._stop_with(f"{prov} {model} did not answer: {msg}. Nothing was started."); return False
                better = self.find_model(i, prov, exclude=model)
                if not better: self._stop_with(f"No {prov} model answered a test. Nothing was started."); return False
                with self.lock:
                    ref["model"] = better
                    if isinstance(i, int): g.cli_sessions.pop(str(i), None)
                    g.save()
                if model: self._record("Engine", f"{who[0].upper() + who[1:]}'s model {model} was refused at Start ({msg}); {who} now plays on {better}, the first {prov} model that answered.", "system")
                self._tested(who)
            with self.lock: g.save()
            return True
        finally:                       # however Start ends, the line stops claiming a test is still running
            with self.lock: self.current = None; self.testing = {}; self.version += 1

    def _tested(self, who: str) -> None:
        """One more seat has an answer. The Start screen counts them and names them as they finish."""
        with self.lock:
            if not self.testing: return
            self.testing["done"] += 1; self.testing["now"] = ""
            if who not in self.testing["names"]: self.testing["names"].append(who)
            self.version += 1

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
            out = self.ask(0, map_prompt(g.world_text, problem), "map", provider=mm["provider"], model=mm["model"])
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
        if g.draft: return self.generate("map")
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

    def _build_people(self, seed: int | None = None) -> None:
        """Roll the people from the valley's description and nothing else. The map is never read here: names come from
        data/names.json, trades from the general medieval list in data/people.json, and nobody has a home or a place to
        stand until Start settles those against whatever map the year begins on. One seed, one valley of people, on any
        map: everything the engine rolls comes out of this one random stream."""
        g = self.g; w = g.world
        g.people_seed = int(seed if seed is not None else new_seed(random.Random()))
        rng = random.Random(g.people_seed)
        pool = NAMES[:]; rng.shuffle(pool)
        names = pool[: g.players]
        while len(names) < g.players: names.append(f"Newcomer {len(names) + 1}")
        with self.lock:
            g.seats = g.seats[:1] + [{"name": n, "provider": (g.model_a if i % 2 == 0 else g.model_b)["provider"], "model": (g.model_a if i % 2 == 0 else g.model_b)["model"],
                                      "color": PALETTE[i % len(PALETTE)]} for i, n in enumerate(names)]
            w.characters = {}; w.relations = {}; w.activities = {}
            for i, n in enumerate(names): w.characters[n] = roll_character(n, i + 1, rng)
            for c in w.characters.values(): c["voice"] = roll_voice(c, rng)
            w.ledger = starting_ledger(len(names), len(w.map)); w.seed_places()
            w.seed_all_relations(rng); w.seed_duties(rng); w.seed_pastimes(rng); w.seed_wants(rng)
            self._sync_terms(); self.version += 1
        for i in range(len(g.seats)): g.seat_dir(i)
        g.save()

    def _roll_person(self, name: str, seat: int, rng: random.Random) -> dict:
        """One more person, rolled whole, with a face, and fitted into the valley that is already there."""
        w = self.g.world
        c = roll_character(name, seat, rng); c["voice"] = roll_voice(c, rng)
        w.characters[name] = c
        w.seed_all_relations(rng); w.seed_pastimes(rng); w.seed_wants(rng)
        if not c.get("duties"):
            fit = {k: w.duty_fit(c, k) for k in DUTIES}; free = [k for k in DUTIES if not w.holders(k)] or list(DUTIES)
            c["duties"] = [max(free, key=lambda k: fit[k])]
        return c

    # ---- controls
    def start(self) -> None:
        with self.lock:
            g = self.g
            if self.busy() or self.map_generating or self.generating or g.draft: return
            if g.status == "paused" and self.thread and self.thread.is_alive():
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

    def _record(self, speaker: str, text: str, kind: str, cluster: str = "", audience: list | None = None) -> None:
        with self.lock:
            g = self.g; g.turn += 1; w = g.world
            color = next((x.get("color") for x in g.seats if x["name"] == speaker), None)
            place = w.characters.get(speaker, {}).get("location") if kind in ("speech", "social") else None
            heard = None
            if kind in ("speech", "social"):
                # a knot in a crowded room is heard by the knot, not by the room
                heard = sorted((n for n in audience if n != speaker and n in w.characters), key=lambda n: w.characters[n]["seat"]) if audience is not None else w.heard_by(speaker, text)
            e = {"turn": g.turn, "speaker": speaker, "text": text, "kind": kind, "cluster": cluster, "time": dt.datetime.now().strftime("%H:%M:%S"), "day": w.day, "phase": w.phase, "color": color, "place": place, "heard": heard}
            g.transcript.append(e); self.version += 1
            seats = list(enumerate(g.seats)); locs = {n: c.get("location") for n, c in g.world.characters.items()}
        for i, seat in seats:   # file writes outside the lock
            vis = visible_text(e, seat["name"], locs.get(seat["name"]) if seat["name"] != "World" else None)
            if vis is None: continue
            line = ("You" if speaker == seat["name"] else speaker) if kind == "social" else ("You said" if speaker == seat["name"] else f"{speaker} said")
            with (g.seat_dir(i) / "memory.md").open("a", encoding="utf-8") as fh:
                fh.write(f"\n## Day {e['day']}, turn {e['turn']} ({e['time']}), {line}:\n{vis}\n")
        g.save()

    def _set_current(self) -> None:
        names = [self.g.seats[j]["name"] for j in sorted(self.speaking) if j < len(self.g.seats)]
        self.current = ", ".join(names) if names else None; self.version += 1

    def _invoke(self, i: int, prompt: str, label: str, provider: str | None = None, model: str | None = None) -> str | None:
        """Run seat i's CLI on a prompt through the runner. Returns the answer, or None with self.last_error[i] set to what the
        runner said: its kind (auth, model, rate, launcher, timeout, other), its own message, and the exact command that was built.
        provider and model override the seat's own for this one call; no session is resumed or kept then."""
        g = self.g; seat = g.seats[i]; prov_name = provider or seat["provider"]; prov = PROVIDERS[prov_name]
        self.last_error.pop(i, None)
        if self.stop_flag.is_set(): return None
        exe = connect.which(prov["exe"])
        if exe is None:
            self.last_error[i] = {"kind": "launcher", "message": f"'{prov['exe']}' is not installed or not on PATH", "cmd": prov["ro_cmd"], "model": model or seat.get("model", "")}
            self._term(i, f"[runner error] '{prov['exe']}' is not installed or not on PATH"); return None
        use_model = self.resolve_model(prov_name, model or seat.get("model", ""))
        if not use_model:
            self.last_error[i] = {"kind": "model", "message": f"no {prov_name} model is chosen and none has answered a test", "cmd": prov["ro_cmd"], "model": ""}
            self._term(i, f"[runner error] no {prov_name} model is chosen and none has answered a test"); return None
        pfile = g.seat_dir(i) / f"prompt_{g.turn + 1:03d}_{int(time.time() * 1000) % 100000}.md"; pfile.write_text(prompt, encoding="utf-8")
        cmd = prov["ro_cmd"].format(ask=ASK.format(prompt_file=pfile), model=use_model)
        sid = g.cli_sessions.get(str(i)) if provider is None else None
        if sid and prov.get("resume"): cmd += prov["resume"].format(sid=sid)
        with self.lock: self.terms[i]["state"] = "speaking"; self.speaking.add(i); self._set_current()
        self._term(i, "=" * 60 + f"\n{seat['name']}: {label}\n" + "=" * 60)
        r = runner.launch(cmd, g.repo, prov["speech"], on_out=lambda ln: self._term(i, ln), on_err=lambda ln: self._term(i, ln), procs=self.procs, key=i,
                          stop_flag=self.stop_flag, wall=runner.TURN_TIMEOUT, quiet=runner.NO_OUTPUT_TIMEOUT)
        with self.lock:
            self.terms[i]["state"] = "waiting"; self.speaking.discard(i); self._set_current()
            if r.session_id and provider is None and r.ok: g.cli_sessions[str(i)] = r.session_id
        if not r.ok:
            self.last_error[i] = {"kind": r.kind, "message": r.message, "cmd": cmd, "model": use_model, "rc": r.rc}
            self._term(i, f"[runner error, {r.kind}: {r.message} (exit {r.rc})]")
            g.cli_sessions.pop(str(i), None); return None
        speech = r.speech or ""
        if prov["speech"] == "copilot": speech = clean_copilot(speech)
        if not speech.strip():
            self.last_error[i] = {"kind": "other", "message": f"ended without an answer (exit {r.rc})", "cmd": cmd, "model": use_model, "rc": r.rc}
            self._term(i, f"[runner error, other: ended without an answer (exit {r.rc})]"); g.cli_sessions.pop(str(i), None); return None
        connect.record_probe(prov_name, use_model, True, "")
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
                 w.sheet(me), "\n" + (w.duty_brief(me) if w.phase == "morning" else "YOUR JOBS: " + (", ".join(DUTIES[k]["label"] for k in w.characters[me].get("duties", [])) or "none") + ".") + "\n", "\n" + w.surroundings(me), "\nWHAT IS GOING ON IN THE VALLEY (unresolved, everyone has heard):\n" + w.threads_text() + "\n", f"\nYour memory of everything you have witnessed is in {g.seat_dir(i) / 'memory.md'} (yours alone).\n"]
        u = self.day_urges.get(me) or []
        if u: parts.append("YOUR URGES TODAY, which are your nature and not a suggestion; act on at least one of them, in words or in your ACTION, and do not apologize for it:\n" + "\n".join(f"- {x}" for x in u) + "\n")
        er = w.errands(me) if w.phase == "afternoon" else []
        if er:
            parts.append("PEOPLE YOU HAVE A REASON TO FIND, and where each of them is standing right now. Nothing you say reaches anyone you are not standing with, "
                         "so the way to have it out with someone is to go to them: your ACTION can be to travel there, and you talk when you arrive.\n"
                         + "\n".join(f"- {x['name']} is at {x['place']}{' (here, with you)' if x['here'] else ''}: {x['why']}." for x in er) + "\n")
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
            if not self.preflight(): return
            if not w.created:
                if len(g.seats) <= 1:            # a fresh game: the people first, out of the description, then the map they walk into
                    self._build_people()
                    if self.stop_flag.is_set(): return
                    self.prepare_map()
                self._create_world()
            while not self.stop_flag.is_set() and w.created:
                while self.pause_flag.is_set() and not self.stop_flag.is_set(): time.sleep(0.5)
                if self.stop_flag.is_set(): break
                if w.day > g.max_days or (g.max_minutes and time.time() - g.started_at > g.max_minutes * 60) or len(w.living()) <= 1:
                    self._epilogue(); break
                if (w.day_report or {}).get("day") != w.day: self._dawn()
                self._morning_phase()
                if self.stop_flag.is_set(): break
                self._afternoon_phase()
                if self.stop_flag.is_set(): break
                self._world_phase()
                if self.stop_flag.is_set(): break
                self._talk_round("after the afternoon")   # travel has resolved; whoever arrived together talks
                if self.stop_flag.is_set(): break
                self._evening_phase()
                if self.stop_flag.is_set(): break
                with self.lock: w.end_day(); self.version += 1
                g.save(chronicle=True)
        finally:
            with self.lock: self.current = None; g.status = "stopped" if self.stop_flag.is_set() else "done"; g.save(chronicle=True)

    def _create_world(self) -> None:
        """A game started the old way, with no draft: the lives are asked for here and the world is created at once."""
        g = self.g; w = g.world
        homeless = w.assign_homes(self.rng)       # the map is drawn, so everyone is given the nearest place that fits
        out = self._ask_lives(list(w.characters))
        if out is None: return
        if homeless:
            self._record("Engine", "There is no place in this valley to practise every trade. " + "; ".join(homeless)
                         + ". They live among everyone else and take the open jobs like anyone else.", "system")
        for rr in out.get("relations", []) or []:
            if isinstance(rr, dict):
                w.set_rel(str(rr.get("a", "")), str(rr.get("b", "")), rr.get("type"), rr.get("feeling"), rr.get("trust"), why=str(rr.get("why", "") or "an old relationship"))
                if rr.get("mutual", True): w.set_rel(str(rr.get("b", "")), str(rr.get("a", "")), rr.get("type"), rr.get("feeling"), rr.get("trust"), why=str(rr.get("why", "") or "an old relationship"))
        w.created = True; w.day = 1
        self._record("World", (strip_dashes(strip_json(out.get("narration") or "The valley wakes.")) + "\n\n" + w.standings_table()), "world")
    # ---- the draft: the map and the people rolled and shown before anything is a game
    def generate(self, what: str = "all", seed: int | None = None) -> str:
        """Roll the draft in the background. The people come first and owe the map nothing, so the two can be rerolled
        one at a time, any number of times, in either order: "people" rolls a fresh valley of people and leaves the map
        alone, "map" redraws the map and leaves the people alone, "all" does both, people first."""
        g = self.g; w = g.world
        with self.lock:
            if not g.draft: return "this is a game, not a draft"
            if self.busy() or self.generating or self.map_generating: return "busy; try again in a moment"
            if not g.seats: g.seats = [self.world_seat()]; self._sync_terms()
            self.stop_flag.clear(); self.generating = what; g.draft_note = ""; self.version += 1
        def work() -> None:
            try:
                if what in ("all", "people"):
                    self._build_people(seed); self._roll_lives()
                if what in ("all", "map"):
                    if what == "map" and g.map_source == "generated": w.map_generated = False
                    self.prepare_map()
                    with self.lock: w.seed_places(); self.version += 1
            finally:
                with self.lock: self.generating = ""; self.version += 1
                g.save()
        threading.Thread(target=work, daemon=True).start()
        return "rolling the valley; watch the World's terminal"

    def _roll_lives(self) -> bool:
        """Every person is already whole: the engine rolled their trade, their words, their nature and their face. This asks
        the World for the prose on top, out of the valley's description alone, and keeps the opening narration for the day the
        draft becomes a game. If the World gives nothing, the engine's own roll stands and the draft says so."""
        g = self.g; w = g.world; out = self._ask_lives(list(w.characters))
        if out is None:
            g.draft_note = "The World gave no lives, so the people stand as the engine rolled them. Reroll all to try again."
        if out:
            for rr in out.get("relations", []) or []:
                if isinstance(rr, dict):
                    w.set_rel(str(rr.get("a", "")), str(rr.get("b", "")), rr.get("type"), rr.get("feeling"), rr.get("trust"), why=str(rr.get("why", "") or "an old relationship"))
                    if rr.get("mutual", True): w.set_rel(str(rr.get("b", "")), str(rr.get("a", "")), rr.get("type"), rr.get("feeling"), rr.get("trust"), why=str(rr.get("why", "") or "an old relationship"))
            g.draft_narration = strip_dashes(strip_json(out.get("narration") or "The valley wakes."))
        else: g.draft_narration = "The valley wakes."
        with self.lock: self.version += 1
        g.save(); return out is not None

    def _ask_lives(self, names: list[str]) -> dict | None:
        """The creation prompt for these names, answered by the World: {"people": {...}, "relations": [...], "narration": str}
        with every person's fields already written onto their character, or None if nothing usable came back."""
        g = self.g; w = g.world
        if not names: return {"people": {}, "relations": [], "narration": ""}
        stats = "\n".join(f"- {c['name']}: {c.get('trade') or 'villager'}, {c.get('age', 30)} years old, {tags_phrase(c.get('tags') or []).lower()}; STR {c['str']} SPD {c['spd']} HP {c['hp_max']} gold {c['gold']}; wants, in plain terms, {(c.get('goal') or {}).get('text', 'to see spring')}" for c in w.characters.values() if c["name"] in names)
        others = [n for n in w.characters if n not in names]
        prompt = "\n".join([WORLD_RULES, f"\nThe world:\n{g.world_text}\n", "The engine has rolled these people out of that description alone. Their names, their trades, their ages, their words and their numbers are settled and are not yours to change. "
            "Write the rest of each life: their character in one line, their secret, their fear, what they want more than anything, and how they talk. "
            "Say nothing about where anyone lives or where anything is. There is no map yet: the valley they walk into is drawn after this, and homes are given out on the first morning.",
            stats, ("\nThese people already have their lives and are not to be written again, only tied to: " + ", ".join(others) + ".\n") if others else "",
            "\nWrite a short opening narration (the valley waking, the early frost, the rider's news) and then a fenced ```json block, exactly this shape:",
            '```json\n{"people":[{"name":"Name","personality":"one line, in keeping with the words the engine gave them","secret":"one line, only they know it","fear":"one line","want":"one line, what they want more than anything, in their own terms, built around the plain want the engine rolled for them",'
            '"voice":{"length":"clipped or plain or rambling","habit":"one verbal habit, a few words","examples":["three lines they might say","in their own voice","one each"],"never":"what they never talk about"}}],'
            '"relations":[{"a":"Name","b":"OtherName","type":"spouse","feeling":3,"trust":2,"mutual":true,"why":"married twelve years; he drinks, she keeps the ledger"}]}\n```',
            "One entry per name, every name, names exact. Make them different from each other: some rich, some poor, some liked, some feared, some with dangerous secrets that touch other people in this list. "
            "Then give the valley a web of relationships in \"relations\": at least eight, each with a \"why\" (one line of history: how they met, what happened, what is owed), using types spouse, lover, kin, friend, rival, enemy, creditor, debtor, master, servant; feeling and trust run from -5 (hate, would knife them) to 5 (love, trust with their life). "
            "Make some relationships one-sided (mutual false, then a second entry the other way with different numbers): an unrequited love, a servant who hates a master who trusts him, a debtor who smiles at a creditor he loathes."])
        self._term(0, "creating the world..." if not others else f"giving {', '.join(names)} a life...")
        people: dict = {}; out = None; data: dict = {}
        for attempt in range(2):
            if self.stop_flag.is_set(): return None
            out = self.ask(0, prompt if attempt == 0 else prompt + "\n\nYour last reply had no valid JSON block. Reply again with the narration and the fenced json block.", "creation")
            data = extract_json(out or "") or {}
            people = {str(p.get("name")): p for p in data.get("people", []) if isinstance(p, dict)}
            if out and len(people) >= max(1, len(names) // 2): break
        if self.stop_flag.is_set() or not out: return None
        for n in names:
            p = people.get(n, {}); c = w.characters[n]
            sd = lambda v, alt: strip_dashes(str(v or alt))   # noqa: E731
            # the trade stays the engine's, off the general list, and the home waits for Start: the World writes only the prose
            c["personality"] = sd(p.get("personality"), c.get("personality") or "keeps their own counsel")[:200]
            c["secret"] = sd(p.get("secret"), c.get("secret") or "nothing worth telling")[:200]
            c["fear"] = sd(p.get("fear"), c.get("fear") or "the cold")[:200]
            c["want"] = sd(p.get("want"), c.get("want") or "to see spring")[:200]
            c["voice"] = clean_voice(p.get("voice"), c, self.rng)          # fixed for the game; fate can edit it in the editor
        g.cli_sessions.pop("0", None)      # the World begins the year fresh
        return {"people": people, "relations": data.get("relations", []) or [], "narration": out}

    def _fresh_name(self, rng: random.Random) -> str:
        w = self.g.world; used = {n.lower() for n in w.characters}
        pool = [n for n in NAMES if n.lower() not in used]
        return rng.choice(pool) if pool else f"Newcomer {len(w.characters) + 1}"

    def reroll_person(self, name: str) -> str:
        """A new name, trade, words, character, secret, fear, want, face and way of speaking for one drafted person: the
        engine rolls them at once, then the World writes the prose. Their seat and model, their stats, their nature, their
        jobs and their pastime stay. Runs in the background."""
        g = self.g; w = g.world
        with self.lock:
            if not g.draft: return "this is a game, not a draft"
            if name not in w.characters: return "no such person"
            if self.busy() or self.generating: return "busy; try again in a moment"
            new = self._fresh_name(random.Random()); self.generating = f"reroll {name}"; self.version += 1
        def work() -> None:
            try:
                rng = random.Random()
                with self.lock:
                    self._rename(name, new); c = w.characters[new]
                    for k in ("trade", "tags", "personality", "secret", "fear", "want", "face"): reroll_field(c, k, rng)
                    c["voice"] = roll_voice(c, rng)
                if self._ask_lives([new]) is None:
                    g.draft_note = f"The World gave {new} no life, so they stand as the engine rolled them."
            finally:
                with self.lock: self.generating = ""; self.version += 1
                g.save()
        threading.Thread(target=work, daemon=True).start()
        return f"rerolling {name}"

    def _rename(self, old: str, new: str) -> None:
        """One person's name changes everywhere the draft knows it."""
        g = self.g; w = g.world
        w.characters = {(new if k == old else k): v for k, v in w.characters.items()}; w.characters[new]["name"] = new
        for x in g.seats:
            if x["name"] == old: x["name"] = new
        w.relations = {(new if a == old else a): {(new if b == old else b): r for b, r in rs.items()} for a, rs in w.relations.items()}
        for k in list(w.activities):
            if k == old: w.activities[new] = w.activities.pop(old)
        self._sync_terms()

    def add_person(self) -> str:
        """One more drafted person, at the end of the strip: rolled whole by the engine, with a face, at once and with
        nothing to wait for. Edit them from there, or press Reroll to have the World write their prose."""
        g = self.g; w = g.world
        with self.lock:
            if not g.draft: return "this is a game, not a draft"
            if self.busy() or self.generating: return "busy; try again in a moment"
            if len(w.characters) >= 30: return "thirty people is the most a valley holds"
            if not g.seats: g.seats = [self.world_seat()]; self._sync_terms()
            rng = random.Random(); n = self._fresh_name(rng); i = len(g.seats) - 1; m = g.model_a if i % 2 == 0 else g.model_b
            self._roll_person(n, len(w.characters) + 1, rng)
            g.seats.append({"name": n, "provider": m["provider"], "model": m["model"], "color": PALETTE[i % len(PALETTE)]})
            w.ledger = starting_ledger(len(w.characters), len(w.map)); self._sync_terms(); self.version += 1
            g.save()
        return f"{n} the {w.characters[n]['trade']} joins the draft"

    # ---- the small reroll buttons: one field at a time, and nothing else moves
    def reroll_one(self, name: str, field: str) -> str:
        """Roll one field of one person again. Works in the draft and in play; in play it is fate like any other edit."""
        g = self.g; w = g.world; field = str(field or "").strip().lower()
        with self.lock:
            c = w.characters.get(name)
            if not c: return "no such person"
            if field not in REROLLABLE: return "nothing to reroll there"
            rng = random.Random()
            if field == "name":
                new = self._fresh_name(rng)
                if new == name: return "no change"
                self._rename(name, new); self.version += 1; g.save()
                note = f"{name} is now called {new}"
            else:
                note = reroll_field(c, field, rng)
                if not note: return "no change"
                if not g.draft and field in ("trade", "tags", "personality", "traits", "want", "fear", "secret", "voice", "age"):
                    c["changed"] = True                 # in play a changed life starts them fresh; in a draft there is nothing to unlearn
                    i = next((j for j, x in enumerate(g.seats) if x["name"] == c["name"]), None)
                    if i is not None: g.cli_sessions.pop(str(i), None)
                self.version += 1; g.save()
        if not g.draft: w.fate.append(note); self._record("Fate", note, "fate")
        return note

    # ---- the draft's pairs: six plain words, and the opinion each one sets on both sides
    def set_tie(self, a: str, b: str, word: str) -> str:
        """One pair of people, set from the six words the draft offers. The numbers come from the word, both ways."""
        g = self.g; w = g.world; word = str(word or "").strip().lower()
        if word not in DRAFT_TIES: return "no such kind of relationship"
        if a not in w.characters or b not in w.characters or a == b: return "no such pair"
        typ, feel, trust = DRAFT_TIES[word]
        with self.lock:
            why = f"they are {word}" if word != "strangers" else "they are nothing to each other yet"
            w.set_rel(a, b, typ, feel, trust, why=why); w.set_rel(b, a, typ, feel, trust, why=why)
            self.version += 1; g.save()
        note = f"{a} and {b} are {word}"
        if not g.draft: w.fate.append(note); self._record("Fate", note, "fate")
        return note

    def reroll_ties(self) -> str:
        """Reroll every pair in the valley: each one takes one of the six words, weighted so most people are strangers."""
        g = self.g; w = g.world
        with self.lock:
            if self.busy() or self.generating: return "busy; try again in a moment"
            names = list(w.characters); rng = random.Random()
            if len(names) < 2: return "there is nobody to be anything to anyone"
            weighted = ["strangers"] * 8 + ["friends"] * 4 + ["rivals"] * 3 + ["kin"] * 2 + ["lovers"] + ["married"]
            w.relations = {}
            w.seed_all_relations(rng)             # everyone still has a first impression of everyone
            for i, a in enumerate(names):
                for b in names[i + 1:]:
                    word = rng.choice(weighted)
                    if word == "strangers": continue
                    typ, feel, trust = DRAFT_TIES[word]
                    w.set_rel(a, b, typ, feel, trust, why=f"they are {word}"); w.set_rel(b, a, typ, feel, trust, why=f"they are {word}")
            self.version += 1; g.save()
        return "the valley's relationships are rolled again"

    def remove_person(self, name: str) -> str:
        g = self.g; w = g.world
        with self.lock:
            if not g.draft: return "this is a game, not a draft"
            if name not in w.characters: return "no such person"
            if self.busy() or self.generating: return "busy; try again in a moment"
            del w.characters[name]; g.seats = [x for x in g.seats if x["name"] != name]
            w.relations.pop(name, None)
            for rs in w.relations.values(): rs.pop(name, None)
            w.activities.pop(name, None); self._sync_terms(); self.version += 1; g.save()
        return f"{name} removed from the draft"

    def seat_tested(self, x: dict) -> bool:
        """A seat is ready when the model it will run on has answered a test."""
        m = x.get("model") or connect.first_accessible(x["provider"]) or ""
        return bool(m) and bool(connect.probes_of(x["provider"]).get(m, {}).get("ok"))

    def draft_ready(self) -> bool:
        g = self.g
        return bool(g.draft and g.world.characters and not self.generating and g.seats and all(self.seat_tested(x) for x in g.seats))

    def test_seats(self) -> str:
        """Test every distinct model the draft's seats will run on, in the background, one after another."""
        g = self.g
        with self.lock:
            if self.busy() or self.generating or self.testing: return "busy; try again in a moment"
            if not g.seats: g.seats = [self.world_seat()]; self._sync_terms()
            pairs: list[tuple[str, str]] = []
            for x in g.seats:
                p = (x["provider"], x.get("model", ""))
                if p not in pairs: pairs.append(p)
            self.testing = {"done": 0, "total": len(pairs), "now": "", "names": []}; self.version += 1
        def work() -> None:
            try:
                for prov, model in pairs:
                    if self.stop_flag.is_set(): break
                    with self.lock: self.testing["now"] = f"{prov} {model or 'first that answers'}"; self.version += 1
                    if model: self.probe_model(prov, model)
                    else:
                        for cand in PROVIDERS.get(prov, {}).get("models", []):
                            ok, _ = self.probe_model(prov, cand)
                            if ok: break
                    with self.lock:
                        self.testing["done"] += 1; self.testing["now"] = ""
                        if self.seat_tested({"provider": prov, "model": model}): self.testing["names"].append(f"{prov} {model or connect.first_accessible(prov) or ''}".strip())
                        self.version += 1
            finally:
                with self.lock: self.testing = {}; self.version += 1
        threading.Thread(target=work, daemon=True).start()
        return "testing the seats"

    def freeze_draft(self) -> None:
        """The draft becomes the game: its folder moves under games, the world is created as of day one, and the opening
        narration the World wrote at Generate time is the first line of the chronicle."""
        g = self.g; w = g.world
        with self.lock:
            if not g.draft: return
            old = g.dir; g.draft = False; g.dir = GAMES / g.id
            if old.exists():
                if g.dir.exists(): shutil.rmtree(g.dir, ignore_errors=True)
                shutil.move(str(old), str(g.dir))
            for f in (g.dir / "draft.json",):
                try:
                    if f.exists(): f.unlink()
                except OSError: pass
            homeless = w.assign_homes(self.rng)      # the map is settled now, so everyone is given the nearest place that fits
            w.created = True; w.day = 1; g.status = "idle"; self.version += 1
            g.save()
        self._record("World", (g.draft_narration or "The valley wakes.") + "\n\n" + w.standings_table(), "world")
        if homeless:
            self._record("Engine", "There is no place in this valley to practise every trade. " + "; ".join(homeless)
                         + ". They live among everyone else and take the open jobs like anyone else.", "system")
        g.draft_narration = ""; g.save()

    def _dawn(self) -> None:
        """The valley wears a little: weather, spoilage, hunger, cold, sickness, and the dead by morning. Before anyone speaks."""
        g = self.g; w = g.world
        with self.lock:
            w.seed_missing(self.rng)                                                       # anyone or anything still unseeded
            rep = w.dawn(self.rng); roster = w.assign_day(self.rng); self.version += 1
        lines = list(rep["lines"])
        opened = [f"{DUTIES[k]['label']} ({r['dumped_on']} is covering it today)" if r.get("dumped_on") else DUTIES[k]["label"] for k, r in roster["duties"].items() if r["unclaimed"]]
        if opened: lines.append("Open: " + ", ".join(opened) + ".")
        for e in roster.get("emergencies", []):
            if e.get("pulled"): lines.append(f"Emergency, {e['text']}: {', '.join(e['pulled'])} pulled to it.")
        rep["lines"] = lines
        self._record("The valley", "\n".join(lines), "dawn")
        g.save()

    def _able_seats(self) -> list[int]:
        g = self.g; w = g.world
        return [i for i, seat in enumerate(g.seats) if i > 0 and seat["name"] in w.characters and w.able(w.characters[seat["name"]])]

    def _touched(self, i: int) -> bool:
        """Something reached this person since their last turn, or their nature is pushing them today."""
        g = self.g; w = g.world; me = g.seats[i]["name"]; c = w.characters[me]
        if self.day_urges.get(me): return True
        seen = int(g.last_seen.get(str(i), 0)); ties = w.ties_of(me)
        return any(touched_text(e, me, c["location"], ties) for e in g.transcript[seen:])

    def _reactors(self, i: int, text: str, name_to_i: dict[str, int]) -> list[int]:
        """Who gets a turn to answer what seat i just said: the seats standing where the speaker stands whom the
        line names or whispers to. Being named from somewhere else wakes nobody, because nothing said here
        reaches anyone there. Call it holding the lock."""
        g = self.g; w = g.world
        wts = whisper_targets(text) | mentions(text)
        here = w.characters[g.seats[i]["name"]]["location"]
        out = []
        for nm, j in name_to_i.items():
            if j == i: continue
            other = g.seats[j]["name"]
            if w.characters[other]["location"] != here: continue
            if nm in wts or re.search(r"(?<![\w@])" + re.escape(other) + r"\b", text, re.I): out.append(j)
        return out

    def _round(self, seats: list[int], instruction, label: str, on_reply, reactions: bool = True) -> None:
        """One round of prompts to the given seats, in parallel. With reactions on, anyone named or whispered to who is
        standing there gets a turn to answer; being named from somewhere else wakes nobody. The convener speaks as fate,
        so their @mentions do wake people. on_reply(i, text) takes each answer that is not PASS."""
        g = self.g; w = g.world
        reacted: set[int] = set(); queue = list(seats); threads: dict[int, threading.Thread] = {}
        name_to_i = {g.seats[i]["name"].lower(): i for i in self._able_seats()}

        def worker(i: int, react: bool) -> None:
            base = instruction(i) if callable(instruction) else instruction
            instr = ("Someone spoke to you or acted on you, above. Answer them in character, in one to three sentences, or reply exactly PASS. " + base) if react else base
            text = self.ask(i, self._player_prompt(i, instr), f"day {w.day}, {label}")
            g.last_seen[str(i)] = len(g.transcript)
            if not text: on_reply(i, None); return
            if text.strip().upper().rstrip(".") == "PASS": self._term(i, "(passed)"); on_reply(i, None); return
            text = cap_speech(strip_dashes(text))         # one to three sentences, no dashes, the ACTION line kept whole
            on_reply(i, text)
            if not reactions: return
            with self.lock:
                for j in self._reactors(i, text, name_to_i):
                    if j in reacted or j in threads: continue
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
        """What a person said, without their ACTION line or their private THOUGHT line."""
        return "\n".join(ln for ln in text.split("\n") if not re.match(r"^\s*(ACTION|THOUGHT):", ln, re.I)).strip()

    def _say(self, i: int, text: str, cluster: str = "", audience: list | None = None) -> bool:
        """Put what a person said into the chronicle, if there was an ear for it. Talk is face to face: a
        person standing alone is heard by nobody, and so is a person who addresses only people who are not
        there. Those words are dropped and the fact is written in their own log, nowhere else."""
        g = self.g; w = g.world; me = g.seats[i]["name"]
        said = self._speech_part(text); thought = thought_line(text)
        with self.lock:
            c = w.characters.get(me)
            if not c: return False
            here = c["location"]; alone = w.alone(me)
            absent = [] if alone else w.not_here(me, said)
            dropped = alone or bool(absent and not w.addressed_here(me, said))
            if thought: note_log(c, w.day, f"You thought: {thought}")
            if dropped and said:
                note_log(c, w.day, f"You spoke to nobody at {here}." + (f" {', '.join(absent)} {'is' if len(absent) == 1 else 'are'} not here." if absent else ""))
            if thought or (dropped and said): self.version += 1
        if dropped:
            if said: self._term(i, f"(you spoke to nobody at {here}; the words were dropped)")
            return False
        if not said: return False
        self._record(me, said, "speech", cluster=cluster, audience=audience); return True

    def _speech_clause(self, me: str) -> str:
        """What the prompt asks for besides the ACTION line. With people standing there, a word to them. Alone,
        nothing aloud at all: there is no one to hear it, so the prompt does not offer it."""
        w = self.g.world; others = w.others_here(me); here = w.characters[me]["location"]
        if not others:
            return (f"Nobody else is at {here}. There is nobody to talk to, so say nothing aloud: give your ACTION line and nothing more. "
                    "You may add one line beginning THOUGHT: and it goes into your own memory and no further.")
        return f"You are at {here} with {', '.join(others)}. Say what you say to them, in one to three sentences, before your ACTION line."

    def _talk_round(self, beat: str) -> list[dict]:
        """Wherever two or more people stand together, one social beat: the engine rolls whether each does anything at
        all, picks the act from the catalog by dials and feeling, applies its weight, and writes the chronicle sentence.
        An act that carries a line asks the model for exactly one sentence in the person's way of speaking; if nothing
        usable comes back, the act still happened. A crowded room is split into knots of two to four first. One beat per
        knot per beat name, and a seat whose place is empty of others is never woken."""
        g = self.g; w = g.world
        with self.lock:
            groups = w.groups_here(); seat_of = {g.seats[i]["name"]: i for i in self._able_seats()}
            touched = {g.seats[i]["name"] for i in self._able_seats() if self._touched(i)}
        ran: list[dict] = []
        for place in sorted(groups):
            names = [n for n in groups[place] if n in seat_of]
            if len(names) < 2: continue
            with self.lock: clusters = w.talk_clusters(place, names, self.rng)
            for ci, knot in enumerate(clusters):
                key = f"{w.day}|{beat}|{place}|{','.join(knot)}"
                with self.lock:
                    if key in self.talked: continue
                    self.talked.add(key)
                head = w.cluster_header(place, knot, ci if len(clusters) > 1 else None)
                with self.lock: acts = w.social_beat(place, list(knot), self.rng, touched); self.version += 1
                for e in acts:
                    if self.stop_flag.is_set(): break
                    act = SOCIAL.get(e["key"], {})
                    if act.get("line") and e["actor"] in seat_of: e["line"] = self._ask_line(seat_of[e["actor"]], e) or ""
                    self._record_social(e, list(knot), head)
                ran.append({"day": w.day, "phase": w.phase, "beat": beat, "place": place, "names": list(knot), "header": head, "acts": [e["key"] for e in acts]})
                if self.stop_flag.is_set(): break
            if self.stop_flag.is_set(): break
        with self.lock: self.talks.extend(ran); self.version += 1
        self.g.save()
        return ran

    def _line_prompt(self, name: str, e: dict) -> str:
        """The small prompt for one spoken line: who they are, how they talk, how they feel about the target, and the act."""
        w = self.g.world; c = w.characters[name]; act = SOCIAL.get(e["key"], {}); target = e["target"]
        ask = str(act.get("ask", "")).format(a=name, b=target, c="someone who is not here")
        recent = [x for x in w.social_log if {x["actor"], x["target"]} == {name, target} and x is not e][-3:]
        return "\n".join([f"You are {name}, {c.get('trade', 'a villager')}, at {c['location']} with {', '.join(n for n in e.get('witnesses', []) + [target])}. Your character: {c.get('personality', '')}",
                           w.voice_text(name), f"How you feel: {w.feeling_plain(name, target)}.",
                           ("Lately between you: " + "; ".join(x["text"] for x in recent) + ".") if recent else "",
                           f"What just happened: {e['text']}", f"{ask} One sentence. Reply with the sentence alone: no name in front, no quotes, no ACTION line, no stage directions."])

    def _ask_line(self, i: int, e: dict) -> str | None:
        """Exactly one sentence from the seat's model, in the person's way of speaking, or None if nothing usable came back."""
        g = self.g; w = g.world; seat = g.seats[i]; name = seat["name"]
        text = self.ask(i, self._line_prompt(name, e), f"day {w.day}, a line to {e['target']}", provider=seat["provider"], model=seat.get("model", ""))
        return clean_line(text)

    def _record_social(self, e: dict, knot: list[str], head: str) -> None:
        """The chronicle sentence, with the spoken line under it when there is one."""
        text = e["text"] + (f'\n"{e["line"]}"' if e.get("line") else "") + (f"\n{e['fight']}" if e.get("fight") else "")
        self._record(e["actor"], text, "social", cluster=head, audience=knot)

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
            if text: self._say(i, text)
            with self.lock: outcomes[me] = w.resolve_morning(me, text or "", self.rng); self.version += 1

        base = ("It is morning. Your ACTION line must begin with WORK (do all your work today), WORK followed by one job's name (do that one first, then the rest, or take it up if nobody holds it), "
                "REFUSE (give up your jobs; they go open and people notice), or anything else, which counts as skipping your work today and costs the same. "
                "The engine does the work and says what came of it; never describe the outcome yourself. ")
        self._round(working, lambda i: base + self._speech_clause(g.seats[i]["name"]), "morning", on_reply, reactions=False)
        if self.stop_flag.is_set(): return
        with self.lock:
            for i in self._able_seats():
                me = g.seats[i]["name"]
                if me not in outcomes and (w.characters[me].get("duties") or w.characters[me].get("dumped") or w.characters[me].get("emergency")): outcomes[me] = w.resolve_morning(me, "", self.rng)
            for c in w.living():
                if not w.able(c): outcomes[c["name"]] = w.resolve_morning(c["name"], "", self.rng)
            done = {r["duty"] for rs in outcomes.values() for r in rs if r.get("kind") == "work" and r.get("duty")}
            m = w.end_morning(done, self.rng); self.version += 1
        lines = list(w.nothing_lines) + [r["text"] for me in sorted(outcomes, key=lambda n: w.characters[n]["seat"]) for r in outcomes[me] if r.get("text")]
        undone = [u["text"] for u in m["undone"]]
        text = "\n".join(lines) or "Nobody had work to do."
        if undone: text += "\n\nUNDONE: " + " ".join(undone)
        if m["complaints"]: text += "\n\n" + "\n".join(m["complaints"])
        self._record("The valley", text, "morning"); g.save()
        if self.stop_flag.is_set(): return
        self._talk_round("after work")            # the work put people side by side; they talk about it

    def _afternoon_phase(self) -> None:
        """Free actions, from the people something touched or whose nature is pushing them. Quiet days are allowed."""
        g = self.g; w = g.world
        with self.lock: w.phase = "afternoon"; self.version += 1
        seats = [i for i in self._able_seats() if self._touched(i)]
        acted: set[int] = set()

        def on_reply(i: int, text: str | None) -> None:
            if not text: return
            me = g.seats[i]["name"]; self._say(i, text)
            a = action_line(text)
            if a and i not in acted:
                with self.lock:
                    acted.add(i); w.pending.append({"who": me, "text": a, "turn": g.turn})
                    if not w.start_walk(me, a): w.set_activity(me, "acting", a[:48], [{"place": w.characters[me]["location"], "what": a[:48], "dur": 8}])
                    self.version += 1

        base = ("It is afternoon, your free time. If something touched you today or you have a want to act on, act on it now, with one ACTION line. "
                "To say anything to someone who is not standing with you, your ACTION is to travel to them. If nothing presses, reply exactly PASS and you will spend the afternoon on your pastime. ")
        self._round(seats, lambda i: base + self._speech_clause(g.seats[i]["name"]), "afternoon", on_reply, reactions=True)
        if self.stop_flag.is_set(): return
        # everyone else spends the afternoon on their pastime, on the map; who ended up together is a line in the chronicle
        with self.lock:
            done = [w.do_pastime(g.seats[i]["name"], self.rng) for i in self._able_seats() if i not in acted]
            groups = w.pastime_groups(); self.version += 1
        if done:
            lines = [d["text"] for d in done]
            for pl, ns in groups.items(): lines.append(f"At {pl}: {', '.join(ns)} together.")
            self._record("The valley", "\n".join(lines), "afternoon"); g.save()

    def _evening_phase(self) -> None:
        """Dusk. Everyone goes home, or to the inn if it pulls them, and whoever is under the same roof talks. No actions."""
        g = self.g; w = g.world
        with self.lock:
            w.phase = "evening"; moves = w.evening_places(self.rng); self.version += 1
        inn = next((p for p, d in w.map.items() if d.get("kind") == "inn"), None)
        at_inn = [c["name"] for c in w.living() if inn and c["location"] == inn]
        with self.lock: got = w.check_wants(self.rng)
        self._record("The valley", f"Evening. " + (f"At {inn}: {', '.join(at_inn)}. " if at_inn else "") + "Everyone else is at home." + ("".join(" " + x["text"] for x in got)), "evening")
        self._talk_round("evening")               # whoever is under the same roof for the night talks
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
        out = self.ask(0, self._world_prompt(outcomes), f"day {w.day} resolution") if outcomes else ""
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
        out = self.ask(0, prompt, "epilogue")
        self._record("World", strip_dashes(out or "The chronicle ends here.") + "\n\n" + w.standings_table(), "epilogue")
        dead = [c["name"] for c in w.characters.values() if not c["alive"]]
        telegram.notify(f"{g.title or 'Terraceilia'}: the year is over on day {w.day}. "
                        f"{len(w.living())} still living, {len(dead)} dead" + (": " + ", ".join(dead[:8]) if dead else "") + ".", "finish")

