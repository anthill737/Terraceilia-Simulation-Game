"""The world: the fixed map, the people, the numbers. Only this module writes them."""
from __future__ import annotations
import datetime as dt, json, math, random, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
GAMES = ROOT / "games"

NAMES = json.loads((DATA / "names.json").read_text(encoding="utf-8"))
EVENTS = json.loads((DATA / "events.json").read_text(encoding="utf-8"))
_MAPFILE = json.loads((DATA / "map.json").read_text(encoding="utf-8"))
BASE_MAP = _MAPFILE["places"]
BASE_NAME = _MAPFILE.get("name") or "Terraceilia"
BASE_STYLE = {"palette": _MAPFILE.get("palette", {}), "water": _MAPFILE.get("water", {}), "sky": _MAPFILE.get("sky", "day")}
PLACES = list(BASE_MAP.keys())

# ---------------------------------------------------------------- generated maps
KINDS = ["castle", "town", "village", "inn", "chapel", "mill", "forest", "fields", "water", "ruin", "market", "farm", "tower", "cave", "road", "other"]
FEATURES = ["mountain", "peak", "cliff", "island", "crater", "crag", "forest", "marsh", "plain", "coast", "none"]
WATER_TYPES = ["river", "lake", "sea", "lava", "none"]
SKY_MOODS = ["day", "dusk", "night", "ash", "storm"]
DANGEROUS_KINDS = {"road", "forest", "cave", "ruin"}
# Names that mean the model did not name the place. One of these and the whole map is thrown away.
PLACEHOLDER_NAMES = {"placeholder", "place", "location", "unnamed", "tbd", "tba", "unknown", "none", "null", "n/a", "na",
                     "area", "region", "spot", "site", "example", "sample", "test", "todo", "new place", "a place", "the place",
                     "village", "town", "castle", "inn", "chapel", "mill", "forest", "road", "cave", "ruin", "market", "farm", "tower"}
HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
CANVAS_W, CANVAS_H, MIN_GAP = 1000, 780, 110
MIN_PLACES, MAX_PLACES = 8, 14
EDGE_X, EDGE_TOP, EDGE_BOTTOM = 60, 80, 60          # inside the frame, clear of the title and the labels
# Built-in places that events name by their role. On a generated map a place of the same kind stands in for them.
GENERIC_KIND = {"The castle": ("castle",), "Market town": ("town", "market"), "The inn": ("inn",), "The chapel": ("chapel",),
                "The mill": ("mill",), "The forest road": ("forest", "road"), "Open country": ("fields", "farm")}


def _clean(v, n: int) -> str:
    return " ".join(str("" if v is None else v).split())[:n]


def _num(v, default: float) -> float:
    try: return float(v)
    except (TypeError, ValueError): return default


def _hex(v, default: str) -> str:
    v = _clean(v, 7)
    return v if HEX_RE.match(v or "") else default


def _shade(hexcol: str, f: float) -> str:
    """The same color, darker. Used when a generated palette gives only its base ground color."""
    r, g, b = (int(hexcol[i:i + 2], 16) for i in (1, 3, 5))
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(c * f))) for c in (r, g, b))


def is_placeholder(name: str) -> bool:
    """A name the model did not really choose: a stock word, or too short to be a name."""
    n = " ".join((name or "").strip().lower().split())
    if n.startswith("the "): n = n[4:]
    if n in PLACEHOLDER_NAMES: return True
    if re.fullmatch(r"(place|location|area|region|site|spot|village|town|city)\s*\d*", n): return True
    return sum(ch.isalpha() for ch in n) < 3


def validate_style(data: dict) -> dict:
    """The world's own look: the ground it is made of, the water it has, the light it sits under.
    Anything missing or unknown falls back to the built-in valley's greens, its river, and daylight."""
    base = BASE_STYLE.get("palette", {}); p = data.get("palette") if isinstance(data.get("palette"), dict) else {}
    ground = _hex(p.get("ground"), base.get("ground", "#2a4a33"))
    pal = {"ground": ground, "accent": _hex(p.get("accent"), base.get("accent", "#5d7a3a")),
           "mid": _hex(p.get("mid"), _shade(ground, .72)), "deep": _hex(p.get("deep"), _shade(ground, .40))}
    w = data.get("water") if isinstance(data.get("water"), dict) else {}
    wt = _clean(w.get("type"), 10).lower(); wt = wt if wt in WATER_TYPES else "none"
    default_water = "#ff6a1f" if wt == "lava" else BASE_STYLE.get("water", {}).get("color", "#4d9bbd")
    sky = _clean(data.get("sky"), 10).lower()
    return {"palette": pal, "water": {"type": wt, "color": _hex(w.get("color"), default_water)},
            "sky": sky if sky in SKY_MOODS else "day"}


def _clamp_xy(d: dict) -> None:
    d["x"] = min(CANVAS_W - EDGE_X, max(EDGE_X, d["x"])); d["y"] = min(CANVAS_H - EDGE_BOTTOM, max(EDGE_TOP, d["y"]))


def _components(places: dict) -> list[list[str]]:
    seen: set[str] = set(); out = []
    for s in places:
        if s in seen: continue
        comp = []; stack = [s]; seen.add(s)
        while stack:
            n = stack.pop(); comp.append(n)
            for a in places[n]["adj"]:
                if a not in seen: seen.add(a); stack.append(a)
        out.append(comp)
    return out


def spread_places(places: dict, gap: int = MIN_GAP) -> None:
    """Clamp every place into the canvas, then nudge pairs apart until no two are closer than `gap`."""
    for d in places.values(): _clamp_xy(d)
    keys = list(places); want = gap + 2      # two units of slack so rounding cannot undo it
    for _ in range(400):
        moved = False
        for i in range(len(keys)):
            for j in range(i + 1, len(keys)):
                a, b = places[keys[i]], places[keys[j]]
                dx, dy = b["x"] - a["x"], b["y"] - a["y"]; d = math.hypot(dx, dy)
                if d >= want: continue
                if d < 1e-6: dx, dy, d = 1.0, 0.6, math.hypot(1.0, 0.6)
                push = (want - d) / 2 + 0.5; ux, uy = dx / d, dy / d
                a["x"] -= ux * push; a["y"] -= uy * push; b["x"] += ux * push; b["y"] += uy * push
                _clamp_xy(a); _clamp_xy(b); moved = True
        if not moved: break
    for d in places.values(): d["x"] = int(round(d["x"])); d["y"] = int(round(d["y"]))


def validate_map(data) -> dict:
    """Never trust the AI. Returns {"ok": True, "name", "places", "names", "style"} with every rule enforced, or
    {"ok": False, "why": "..."} naming what was wrong so the retry can be specific. Enforced here: no placeholder or
    generic place names; unique names; kind and feature from their lists, else other and none; elevation 0 to 3;
    8 to 14 places (extras with the fewest paths dropped); adjacency symmetric and pruned to real places; separate
    components joined at their nearest pair; coordinates inside the canvas and at least 110 apart; at least one
    fixture each; 8 to 60 distinct people names, else none (the engine then uses data/names.json)."""
    if not isinstance(data, dict) or not isinstance(data.get("places"), list):
        return {"ok": False, "why": "there was no json block with a places list in it"}
    bad = [_clean(p.get("name"), 40) for p in data["places"] if isinstance(p, dict) and is_placeholder(_clean(p.get("name"), 40))]
    if bad:
        return {"ok": False, "why": f"these are not names a person would say, they are placeholders or bare category words: {', '.join(repr(b) for b in bad[:6])}. Every place needs a real name of its own"}
    places: dict[str, dict] = {}
    for i, p in enumerate(data["places"]):
        if not isinstance(p, dict): continue
        n = _clean(p.get("name"), 40)
        if not n or n.lower() in {k.lower() for k in places}: continue
        kind = _clean(p.get("kind"), 20).lower(); feat = _clean(p.get("feature"), 20).lower()
        try: elev = max(0, min(3, int(p.get("elevation", 0))))
        except (TypeError, ValueError): elev = 0
        fx: list[str] = []
        for f in (p.get("fixtures") if isinstance(p.get("fixtures"), list) else []):
            f = _clean(f, 60)
            if f and f.lower() not in {x.lower() for x in fx}: fx.append(f)
        adj = [_clean(a, 40) for a in (p.get("adj") if isinstance(p.get("adj"), list) else [])]
        gx, gy = 150 + (i % 4) * 230, 130 + (i // 4) * 180      # a seat on a grid for a place that came without usable coordinates
        places[n] = {"desc": _clean(p.get("desc"), 400) or "A place the surveyor did not describe.", "fixtures": fx[:8] or ["the ground"],
                     "adj": [a for a in adj if a], "x": _num(p.get("x"), gx), "y": _num(p.get("y"), gy),
                     "kind": kind if kind in KINDS else "other", "feature": feat if feat in FEATURES else "none", "elevation": elev}
    if len(places) < MIN_PLACES:
        return {"ok": False, "why": f"only {len(places)} usable places came back and the map needs at least {MIN_PLACES}"}
    lower = {k.lower(): k for k in places}
    for n, d in places.items():                       # only real places, never itself, no repeats
        kept: list[str] = []
        for a in d["adj"]:
            k = lower.get(a.lower())
            if k and k != n and k not in kept: kept.append(k)
        d["adj"] = kept
    for n, d in places.items():                       # both sides
        for a in d["adj"]:
            if n not in places[a]["adj"]: places[a]["adj"].append(n)
    order = list(places)
    while len(places) > MAX_PLACES:                   # drop the least connected, the later listed first among equals
        victim = min(places, key=lambda k: (len(places[k]["adj"]), -order.index(k)))
        del places[victim]
        for d in places.values():
            if victim in d["adj"]: d["adj"].remove(victim)
    for d in places.values(): _clamp_xy(d)
    comps = _components(places)
    while len(comps) > 1:                             # join the nearest pair between the first component and any other
        best = None
        for a in comps[0]:
            for comp in comps[1:]:
                for b in comp:
                    dd = math.hypot(places[a]["x"] - places[b]["x"], places[a]["y"] - places[b]["y"])
                    if best is None or dd < best[0]: best = (dd, a, b)
        _, a, b = best; places[a]["adj"].append(b); places[b]["adj"].append(a)
        comps = _components(places)
    spread_places(places)
    names: list[str] = []
    for x in (data.get("names") if isinstance(data.get("names"), list) else []):
        x = _clean(x, 30)
        if x and x.lower() != "world" and x.lower() not in {y.lower() for y in names}: names.append(x)
    names = names[:60]
    if len(names) < 8: names = []
    nm = _clean(data.get("name"), 40)
    if is_placeholder(nm): nm = ""
    return {"ok": True, "name": nm or "The valley", "places": places, "names": names, "style": validate_style(data)}


def _phrase(s: str) -> re.Pattern:
    return re.compile(r"(?<![\w'])" + re.escape(s.lower()) + r"(?![\w'])")


_BUILTIN_PLACE_RE = {k: _phrase(k) for k in BASE_MAP}
_BUILTIN_FIXTURE_RE = {f: _phrase(f) for d in BASE_MAP.values() for f in d["fixtures"]}


def map_text(m: dict | None = None) -> str:
    m = m or BASE_MAP; out = []
    for n, d in m.items():
        fx = [f for f in d["fixtures"] if f not in d.get("destroyed", [])]; gone = d.get("destroyed", [])
        out.append(f"- {n}: {d['desc']} You can use: {', '.join(fx) or 'nothing usable'}." + (f" Destroyed and gone: {', '.join(gone)}." if gone else "") + f" Paths lead to: {', '.join(d['adj'])}.")
    return "\n".join(out)


def place_key(name: str, m: dict | None = None) -> str | None:
    m = m or BASE_MAP; n = (name or "").strip().lower()
    for k in m:
        if k.lower() == n or n.endswith(k.lower()) or k.lower().endswith(n): return k
    return None


def now_id() -> str:
    base = dt.datetime.now().strftime("%Y%m%d-%H%M%S"); sid = base; n = 2
    while (GAMES / sid).exists(): sid = f"{base}-{n}"; n += 1
    return sid


def roll_character(name: str, seat: int, rng: random.Random, places: list[str] | None = None) -> dict:
    hp = rng.randint(8, 14)
    return {"name": name, "seat": seat, "str": rng.randint(2, 9), "spd": rng.randint(2, 9), "hp": hp, "hp_max": hp,
            "gold": rng.randint(1, 9), "skills": {}, "location": rng.choice(places or PLACES), "standing": "unknown",
            "alive": True, "banished": False, "trade": "", "home": "", "personality": "", "secret": "", "fear": "", "want": "",
            "cause_of_death": "", "traits": roll_traits(rng)}


TRAITS = ["warmth", "temper", "honesty", "greed", "courage", "tongue", "desire", "piety", "ambition", "loyalty", "cunning", "drink"]
TRAIT_TEXT = {
    "warmth":  ["You are cruel and enjoy it.", "You are hard and unkind; other people's troubles bore you.", "You are neither kind nor cruel; you look after your own.", "You are decent to people who deserve it.", "You are kind to a fault."],
    "temper":  ["Nothing moves you; you answer insults with a shrug.", "You keep your temper unless pushed.", "You have an ordinary temper.", "You flare fast and say things you regret.", "You are violent when crossed and quick to threaten."],
    "honesty": ["You lie as easily as you breathe, even when the truth would serve.", "You lie when it suits you and feel nothing.", "You bend the truth when it pays.", "You are mostly honest, with exceptions you can name.", "You cannot lie without it showing."],
    "greed":   ["You give without counting.", "You share when asked.", "You want your fair share and no less.", "You want more than your share and say so.", "You would sell your mother's grave for coin and everyone knows it."],
    "courage": ["You run from anything that might hurt.", "You avoid fights and dangerous roads.", "You take ordinary risks.", "You are brave, sometimes stupidly.", "You are reckless; danger is a dare to you."],
    "tongue":  ["You speak in grunts and curses, a few words at a time. No poetry, no speeches, no describing your feelings.", "You speak plainly and bluntly, short sentences, no flourishes.", "You talk like an ordinary villager, nothing fancy.", "You are well spoken and enjoy a turn of phrase.", "You are eloquent and know it; you talk too much."],
    "desire":  ["You have no interest in anyone's bed and find the subject tiresome.", "You keep your desires to yourself and act on them rarely.", "You notice who is handsome and sometimes act on it.", "You flirt with anyone worth flirting with and take a lover when you can.", "You are wanton; you pursue whoever catches your eye, married or not, and the valley talks about it."],
    "piety":   ["You think the chapel is a roof over a fraud and say so.", "You go to chapel for appearances.", "You believe, quietly, without much thought.", "You are devout and judge others by it.", "You see God's hand in everything and preach whether asked or not."],
    "ambition":["You want nothing but to be left alone.", "You want a quiet life and a full belly.", "You would like to do a little better than your father did.", "You mean to rise, and you watch for the chance.", "You want to run this valley one day and everything you do serves that."],
    "loyalty": ["You would sell out anyone for a better offer.", "Your loyalty lasts as long as it pays.", "You keep faith with your own and no one else.", "You stand by your friends even when it costs.", "You would die for the people you have chosen, and kill for them."],
    "cunning": ["You are simple; schemes go over your head and you say what you think.", "You are straightforward and suspicious of clever people.", "You can see a trick coming most of the time.", "You are sly; you plan two moves ahead and let others think they chose.", "You are a schemer; every friendship is a piece on a board."],
    "drink":   ["You never touch drink and despise those who do.", "A cup at feast days, no more.", "You drink like anyone else.", "You drink too much and know it.", "You are a drunkard; the inn owns your evenings and your coin."],
}


def roll_traits(rng: random.Random) -> dict:
    """Skewed away from nice: most people are middling, a good share are hard, a few are saints."""
    out = {}
    for t in TRAITS:
        r = rng.random()
        out[t] = 1 if r < .18 else 2 if r < .42 else 3 if r < .68 else 4 if r < .88 else 5
    return out


def urges(c: dict, world: "World", rng: random.Random) -> list[str]:
    """Daily compulsions from extreme traits, aimed at real people nearby. The person is told to act on at least one."""
    t = c.get("traits", {}); g = lambda k: int(t.get(k, 3))
    here = [x for x in world.at(c["location"]) if x["name"] != c["name"]]
    near = [x for x in world.living() if x["name"] != c["name"]]
    pick = lambda pool: rng.choice(pool)["name"] if pool else (rng.choice(near)["name"] if near else "someone")
    out = []; r = rng.random
    hot, drunk, cruel, sly = g("temper") >= 4, g("drink") >= 4, g("warmth") <= 2, g("cunning") >= 4
    if drunk and r() < .7: out.append(f"You have been drinking since noon and will be drunk by dusk. Drunk, you say what you think and do what you want.")
    if hot and drunk and r() < .6: out.append(f"{pick(here)} said something about you, or you have decided they did. You want to hit them.")
    elif hot and r() < .35: out.append(f"You are in a foul temper and {pick(here)} is the nearest target for it.")
    if cruel and sly and hot and r() < .35: out.append(f"{pick(here or near)} is in your way and always will be. You have been thinking about how to be rid of them for good, and today the thought does not frighten you.")
    elif cruel and sly and r() < .4: out.append(f"{pick(here or near)} has something you want, or knows something you need buried. Work them: flatter, threaten, or trap them into owing you.")
    elif cruel and r() < .3: out.append(f"You feel like hurting {pick(here)} today, with words or worse, because you can.")
    if g("desire") >= 4 and r() < .6: out.append(f"You want {pick(here or near)}. Married or not, willing or not yet, you go after them today, and you are not subtle about it.")
    if g("greed") >= 4 and r() < .45: out.append(f"{pick(here)} has coin or goods within your reach. Take, cheat, or extort; you are owed, in your own mind.")
    if g("honesty") <= 2 and r() < .5: out.append(f"Tell a lie today that gets you something: about {pick(near)}, about the grain, about yourself.")
    if g("piety") >= 4 and r() < .4: out.append(f"{pick(near)} is a sinner and you know it. Say so, to their face or to the chapel.")
    if g("piety") <= 2 and g("tongue") >= 4 and r() < .3: out.append("Mock the chapel and its people out loud today. Faith is for fools and you enjoy saying it.")
    if g("courage") <= 2 and r() < .4: out.append("Something today will frighten you. Run, hide, or sell someone out to stay safe.")
    if g("courage") >= 4 and r() < .3: out.append("Do the dangerous thing today, the one sensible people avoid, because it is there.")
    if g("ambition") >= 4 and r() < .4: out.append(f"{pick(near)} stands between you and what you mean to become. Undercut them today.")
    if g("loyalty") <= 2 and r() < .3: out.append(f"Someone would pay for what you know about {pick(near)}. Consider selling it.")
    if g("loyalty") >= 4 and here and r() < .3: out.append(f"{pick(here)} needs you today whether they know it or not. Stand with them even if it costs.")
    rng.shuffle(out); return out[:3]


def trait_text(traits: dict) -> str:
    return " ".join(TRAIT_TEXT[t][max(1, min(5, int(traits.get(t, 3)))) - 1] for t in TRAITS)


class World:
    """All game state. Only the engine writes it. Includes this game's copy of the map."""

    def __init__(self, d: dict | None = None) -> None:
        d = d or {}
        self.characters: dict[str, dict] = d.get("characters", {})
        self.day = d.get("day", 0)
        self.ledger = d.get("ledger", {"grain_weeks": 10, "grain_needed": 16, "roofs_broken": 3, "road_safe": False, "sick": 0, "built": []})
        self.pending: list[dict] = d.get("pending", [])
        self.court_every = d.get("court_every", 6)
        self.created = d.get("created", False)
        self.map: dict = d.get("map") or json.loads(json.dumps(BASE_MAP))
        self.map_name: str = d.get("map_name") or BASE_NAME
        self.style: dict = d.get("style") or json.loads(json.dumps(BASE_STYLE))
        self.map_generated = bool(d.get("map_generated", False))    # drawn from the description rather than data/map.json
        self.names: list[str] = list(d.get("names") or [])           # people names that came with a generated map
        self.fate: list[str] = d.get("fate", [])      # acts of the convener not yet narrated
        self.relations: dict[str, dict[str, dict]] = d.get("relations", {})   # relations[a][b] = {type, feeling, trust}
        self.threads: list[dict] = d.get("threads", [])     # open situations: {id, text, day, place, who, status, spawn}
        self.fires: dict[str, int] = d.get("fires", {})    # place -> days burning
        self.next_thread = d.get("next_thread", 1)

    def to_dict(self) -> dict:
        return {"characters": self.characters, "day": self.day, "ledger": self.ledger, "pending": self.pending,
                "court_every": self.court_every, "created": self.created, "map": self.map, "fate": self.fate, "relations": self.relations,
                "threads": self.threads, "fires": self.fires, "next_thread": self.next_thread,
                "map_name": self.map_name, "map_generated": self.map_generated, "names": self.names, "style": self.style}

    # ---- which map this game plays on
    def install_map(self, v: dict) -> None:
        self.map = v["places"]; self.map_name = v.get("name") or "The valley"; self.map_generated = True
        self.names = list(v.get("names") or []); self.style = v.get("style") or json.loads(json.dumps(BASE_STYLE))

    def install_builtin(self) -> None:
        self.map = json.loads(json.dumps(BASE_MAP)); self.map_name = BASE_NAME; self.map_generated = False
        self.names = []; self.style = json.loads(json.dumps(BASE_STYLE))

    def resolve_place(self, name: str) -> str | None:
        """A built-in place name on this map: the same name, or for the generic built-in places a place of the same kind."""
        if not name: return None
        for k in self.map:
            if k.lower() == name.lower(): return k
        for kind in GENERIC_KIND.get(name, ()):
            for k, d in self.map.items():
                if d.get("kind") == kind: return k
        return None

    def has_fixture(self, fixture: str, place: str | None = None) -> bool:
        where = [self.map[place]] if place in self.map else list(self.map.values())
        return any(f.lower() == fixture.lower() for d in where for f in d["fixtures"])

    def event_fits(self, e: dict) -> bool:
        """An event that names a built-in place or thing fires only when this map has it; {place} and {fixture} events fit any map."""
        fx = e.get("effect", {}) or {}
        named = str(fx.get("place") or e.get("place") or "")
        if named and not self.resolve_place(named): return False
        if fx.get("fixture") and not self.has_fixture(str(fx["fixture"]), self.resolve_place(named)): return False
        text = re.sub(r"\{\w+\}", " ", e["t"]).lower()
        if any(rx.search(text) and not self.resolve_place(k) for k, rx in _BUILTIN_PLACE_RE.items()): return False
        if any(rx.search(text) and not self.has_fixture(f) for f, rx in _BUILTIN_FIXTURE_RE.items()): return False
        return True

    # ---- situations that persist until resolved
    def open_thread(self, text: str, place: str | None, who: list[str], spawn: str | None = None) -> dict:
        t = {"id": self.next_thread, "text": text, "day": self.day, "place": place, "who": who, "status": "open", "spawn": spawn}
        self.next_thread += 1; self.threads.append(t)
        if spawn and place in self.map: self.map[place].setdefault("present", []).append(spawn)
        return t

    def resolve_thread(self, tid: int, note: str = "") -> bool:
        for t in self.threads:
            if t["id"] == int(tid) and t["status"] == "open":
                t["status"] = "resolved"; t["resolved_day"] = self.day; t["note"] = note[:200]
                if t.get("spawn") and t.get("place") in self.map:
                    pr = self.map[t["place"]].get("present", [])
                    if t["spawn"] in pr: pr.remove(t["spawn"])
                return True
        return False

    def open_threads(self) -> list[dict]: return [t for t in self.threads if t["status"] == "open"]

    def threads_text(self) -> str:
        ts = self.open_threads()
        if not ts: return "- nothing unresolved"
        return "\n".join(f"- [#{t['id']}, since day {t['day']}{', at ' + t['place'] if t.get('place') else ''}{', involving ' + ', '.join(t['who']) if t.get('who') else ''}] {t['text']}" for t in ts)

    # ---- fire, which spreads and lingers
    def ignite(self, place: str, by: str = "fate") -> str:
        p = place_key(place, self.map)
        if not p: return "no such place"
        if p in self.fires: return f"{p} is already burning"
        self.fires[p] = 0
        self._burn(p)
        self.fate.append(f"Fire has broken out at {p}; it is burning now and will keep burning and spreading until it is put out or burns itself out. People there were hurt.")
        self.open_thread(f"Fire at {p}. It burns until the people put it out.", p, [c["name"] for c in self.at(p)], "smoke and flames")
        return f"{p} is burning"

    def _burn(self, p: str) -> None:
        m = self.map[p]; fx = [f for f in m["fixtures"] if f not in m.get("destroyed", [])]
        if fx: m.setdefault("destroyed", []).append(fx[0])
        for c in self.at(p): c["hp"] = max(0, c["hp"] - 2)
        for c in self.at(p):
            if c["hp"] <= 0 and c["alive"]: c["alive"] = False; c["cause_of_death"] = f"burned at {p}"

    def spread_fires(self, rng: random.Random, log: list[str]) -> None:
        for p in list(self.fires):
            self.fires[p] += 1
            if self.fires[p] >= 3:
                self.extinguish(p); log.append(f"the fire at {p} burned itself out"); continue
            self._burn(p); log.append(f"the fire at {p} burns on")
            if rng.random() < .35:
                q = rng.choice(self.map[p]["adj"])
                if q not in self.fires: self.fires[q] = 0; self._burn(q); log.append(f"the fire spread from {p} to {q}"); self.open_thread(f"Fire spread to {q} from {p}.", q, [c["name"] for c in self.at(q)], "smoke and flames")

    def extinguish(self, place: str) -> bool:
        p = place_key(place, self.map)
        if not p or p not in self.fires: return False
        del self.fires[p]
        for t in self.threads:
            if t["status"] == "open" and t.get("place") == p and t.get("spawn") == "smoke and flames": self.resolve_thread(t["id"], "the fire is out")
        return True

    # ---- relationships
    REL_TYPES = ("none", "spouse", "lover", "kin", "friend", "rival", "enemy", "creditor", "debtor", "master", "servant")

    def rel(self, a: str, b: str) -> dict:
        return self.relations.setdefault(a, {}).setdefault(b, {"type": "none", "feeling": 0, "trust": 0, "why": []})

    def set_rel(self, a: str, b: str, typ: str | None = None, feeling: int | None = None, trust: int | None = None, delta: bool = False, why: str = "") -> None:
        if a not in self.characters or b not in self.characters or a == b: return
        r = self.rel(a, b); before = (r["type"], r["feeling"], r["trust"])
        if typ in self.REL_TYPES: r["type"] = typ
        for k, v in (("feeling", feeling), ("trust", trust)):
            if v is None: continue
            try: v = int(v)
            except (TypeError, ValueError): continue
            r[k] = max(-5, min(5, (r[k] + v) if delta else v))
        if (r["type"], r["feeling"], r["trust"]) != before or why:
            r.setdefault("why", []).append({"day": self.day, "note": (why or "something shifted between them")[:240],
                                            "feeling": r["feeling"], "trust": r["trust"], "type": r["type"]})
            del r["why"][:-12]

    @staticmethod
    def feel_word(v: int) -> str:
        return ["hates", "despises", "dislikes", "is cold toward", "is cool toward", "is indifferent to", "is warm toward", "likes", "is fond of", "cares deeply for", "loves"][max(-5, min(5, int(v))) + 5]

    @staticmethod
    def trust_word(v: int) -> str:
        return ["would knife in the dark", "distrusts utterly", "distrusts", "is wary of", "is unsure of", "neither trusts nor distrusts", "trusts a little", "trusts", "trusts well", "trusts with secrets", "trusts with their life"][max(-5, min(5, int(v))) + 5]

    def seed_all_relations(self, rng: random.Random) -> None:
        """Everyone has an opinion about everyone. Shaped by the holder's nature, with a roll, before the World's named ties are laid on top."""
        names = list(self.characters)
        for a in names:
            ta = self.characters[a].get("traits", {}); warmth = int(ta.get("warmth", 3)); cun = int(ta.get("cunning", 3)); loy = int(ta.get("loyalty", 3))
            for b in names:
                if a == b: continue
                tb = self.characters[b].get("traits", {})
                feel = rng.randint(-2, 2) + (warmth - 3) + (1 if int(tb.get("warmth", 3)) >= 4 else -1 if int(tb.get("warmth", 3)) <= 2 else 0)
                trust = rng.randint(-2, 2) + (loy - 3) - (1 if int(tb.get("cunning", 3)) >= 4 and cun >= 4 else 0) + (1 if int(tb.get("honesty", 3)) >= 4 else -1 if int(tb.get("honesty", 3)) <= 2 else 0)
                r = self.rel(a, b)
                if r["type"] == "none" and not r["feeling"] and not r["trust"]:
                    r["feeling"] = max(-5, min(5, feel)); r["trust"] = max(-5, min(5, trust))
                    wb = int(tb.get("warmth", 3)); hb = int(tb.get("honesty", 3)); cb = int(tb.get("cunning", 3))
                    bits = []
                    bits.append("first impression, before anything happened between you")
                    if warmth <= 2: bits.append("you think little of most people")
                    elif warmth >= 4: bits.append("you tend to like people until they give you cause not to")
                    if wb >= 4: bits.append(f"{b} has a kind reputation")
                    elif wb <= 2: bits.append(f"{b} is known to be hard")
                    if hb <= 2: bits.append(f"{b} has a liar's name in the valley")
                    elif hb >= 4: bits.append(f"{b} is thought honest")
                    if cb >= 4 and cun >= 4: bits.append("two schemers recognize each other")
                    if loy >= 4: bits.append("you give trust easily")
                    elif loy <= 2: bits.append("you trust no one much")
                    r["why"] = [{"day": 0, "note": "; ".join(bits), "feeling": r["feeling"], "trust": r["trust"], "type": "none"}]

    def relations_of(self, name: str) -> list[tuple[str, dict]]:
        out = [(b, r) for b, r in self.relations.get(name, {}).items() if b in self.characters and (r["type"] != "none" or r["feeling"] or r["trust"])]
        return sorted(out, key=lambda x: (-abs(x[1]["feeling"]) - abs(x[1]["trust"]), x[0]))

    FEEL2 = ["hate", "despise", "dislike", "are cold toward", "are cool toward", "are indifferent to", "are warm toward", "like", "are fond of", "care deeply for", "love"]
    TRUST2 = ["would knife in the dark", "distrust utterly", "distrust", "are wary of", "are unsure of", "neither trust nor distrust", "trust a little", "trust", "trust well", "trust with your secrets", "trust with your life"]

    def relations_text(self, name: str) -> str:
        rs = self.relations_of(name)
        if not rs: return "You have no ties worth the name yet; that will change."
        return "\n".join(f"- {b}{(' (your ' + r['type'] + ')') if r['type'] != 'none' else ''}: you {self.FEEL2[r['feeling'] + 5]} them ({r['feeling']:+d}) and {self.TRUST2[r['trust'] + 5]} them ({r['trust']:+d})." + (f" Why: {r['why'][-1]['note']}" if r.get('why') else "") for b, r in rs)

    # ---- the convener's hand
    def move(self, name: str, place: str) -> str:
        c = self.characters.get(name); dest = place_key(place, self.map)
        if not c or not dest: return "no such person or place"
        c["location"] = dest; self.fate.append(f"{name} was found at {dest} with no memory of walking there."); return f"{name} moved to {dest}"

    def destroy(self, place: str, fixture: str) -> str:
        p = place_key(place, self.map)
        if not p: return "no such place"
        d = self.map[p]; f = next((x for x in d["fixtures"] if x.lower() == fixture.lower()), None)
        if not f: return "no such thing there"
        d.setdefault("destroyed", [])
        if f in d["destroyed"]: d["destroyed"].remove(f); self.fate.append(f"At {p}, {f} stands again as if it had never been lost."); return f"{f} restored"
        d["destroyed"].append(f); self.fate.append(f"At {p}, {f} is destroyed: ruined, gone, no longer there to be used."); return f"{f} destroyed"

    def smite(self, name: str) -> str:
        c = self.characters.get(name)
        if not c or not c["alive"]: return "no such living person"
        c["alive"] = False; c["hp"] = 0; c["cause_of_death"] = "struck down by fate"; self.fate.append(f"{name} died suddenly, of no cause anyone can name."); return f"{name} is dead"

    def draw_events(self, drama: int, rng: random.Random, log: list[str]) -> list[str]:
        """Roll the day's events against the drama dial (0 none .. 10 chaos), apply their hard effects, return the lines to narrate."""
        drama = max(0, min(10, int(drama)))
        if drama == 0 or not self.living(): return []
        n = 0
        for k in range(3):   # up to three events; each successive one is less likely
            if rng.random() < (drama / 10) * (0.9, 0.5, 0.25)[k]: n += 1
        out = []
        for _ in range(n):
            pool = [e for e in EVENTS if e.get("tier", 1) <= (1 if drama <= 3 else 2 if drama <= 7 else 3) and self.event_fits(e)]
            if not pool: break
            e = rng.choice(pool); ppl = self.living(); rng.shuffle(ppl)
            who = ppl[0]; who2 = ppl[1] if len(ppl) > 1 else ppl[0]
            fx = e.get("effect", {}) or {}
            place = self.resolve_place(str(fx.get("place") or e.get("place") or "")) or rng.choice(list(self.map.keys()))
            fixtures = [f for f in self.map[place]["fixtures"] if f not in self.map[place].get("destroyed", [])]
            fixture = fx.get("fixture") or (rng.choice(fixtures) if fixtures else "the ground")
            text = e["t"].format(who=who["name"], who2=who2["name"], place=place, fixture=fixture)
            # hard effects, applied now
            if "hp" in fx: who["hp"] = max(0, min(who["hp_max"], who["hp"] + int(fx["hp"])))
            if "gold" in fx: who["gold"] = max(0, who["gold"] + int(fx["gold"]))
            if fx.get("standing"): who["standing"] = fx["standing"]
            if "sick" in fx: self.ledger["sick"] = max(0, self.ledger["sick"] + int(fx["sick"]))
            if "grain" in fx: self.ledger["grain_weeks"] = max(0, self.ledger["grain_weeks"] + int(fx["grain"]))
            if "roofs" in fx: self.ledger["roofs_broken"] = max(0, self.ledger["roofs_broken"] + int(fx["roofs"]))
            if fx.get("road_unsafe"): self.ledger["road_safe"] = False
            if fx.get("destroy") and fixture in fixtures: self.map[place].setdefault("destroyed", []).append(fixture)
            if who["hp"] <= 0 and who["alive"]: who["alive"] = False; who["cause_of_death"] = "died of it"
            if e.get("thread"):
                t = self.open_thread(text, place if ("{place}" in e["t"] or e.get("place") or e.get("spawn")) else None, [who["name"]] + ([who2["name"]] if "{who2}" in e["t"] else []), e.get("spawn"))
                text = f"{text} [situation #{t['id']}]"
            out.append(text); log.append(f"event: {text[:60]}")
        return out

    def living(self) -> list[dict]:
        return [c for c in self.characters.values() if c["alive"] and not c["banished"]]

    def public_table(self) -> str:
        rows = [f"{c['name']}: {c['location']}, {c['standing']}" for c in sorted(self.living(), key=lambda c: c["seat"])]
        dead = [f"{c['name']} ({c['cause_of_death']})" for c in self.characters.values() if not c["alive"]]
        ban = [c["name"] for c in self.characters.values() if c["banished"] and c["alive"]]
        return "WHO IS WHERE\n" + "\n".join(rows) + f"\nDEAD: {', '.join(dead) or 'none'}\nBANISHED: {', '.join(ban) or 'none'}"

    def standings_table(self) -> str:
        rows = [f"| {c['name']} | {c['location']} | {c['hp']}/{c['hp_max']} | {c['gold']} | {', '.join(f'{k} {v}' for k, v in c['skills'].items()) or 'none'} | {c['standing']} |"
                for c in sorted(self.living(), key=lambda c: c["seat"])]
        dead = [f"{c['name']} ({c['cause_of_death']})" for c in self.characters.values() if not c["alive"]]
        ban = [c["name"] for c in self.characters.values() if c["banished"] and c["alive"]]
        L = self.ledger
        led = (f"PROSPERITY, day {self.day}: grain for {L['grain_weeks']} of {L['grain_needed']} weeks needed; "
               f"{L['roofs_broken']} roofs still broken; road {'safe' if L['road_safe'] else 'unsafe'} after dark; "
               f"{L['sick']} sick; built this year: {', '.join(L['built']) or 'nothing yet'}.")
        return (led + "\n\nSTANDINGS\n| Name | Location | Health | Gold | Skills | Standing |\n|---|---|---|---|---|---|\n"
                + "\n".join(rows) + f"\n\nDEAD: {', '.join(dead) or 'none'}\nBANISHED: {', '.join(ban) or 'none'}")

    def at(self, place: str) -> list[dict]:
        return [c for c in self.living() if c["location"] == place]

    def surroundings(self, name: str) -> str:
        c = self.characters[name]; here = c["location"]; m = self.map.get(here, {"desc": "", "fixtures": [], "adj": []}); fx = [f for f in m['fixtures'] if f not in m.get('destroyed', [])]
        people = [x["name"] for x in self.at(here) if x["name"] != name]
        near = []
        for a in m["adj"]:
            who = [x["name"] for x in self.at(a)]
            near.append(f"{a} ({', '.join(who) if who else 'nobody you can see'})")
        return (f"WHERE YOU ARE: {here}. {m['desc']}\nThings here you can use: {', '.join(m['fixtures'])}.\n"
                f"People here with you: {', '.join(people) if people else 'nobody'}.\nOne path away: {'; '.join(near)}.")

    def sheet(self, name: str) -> str:
        c = self.characters[name]
        head = ("WHO YOU ARE NOW. This is the truth about you today; if it differs from how you have spoken before, you have changed, and you play the new you without comment.\n" if c.get("changed") else "")
        return (head + f"You are {c['name']}, {c['trade']}, living at {c['home']}. Your character: {c['personality']}\nYour disposition, which you play without softening: {trait_text(c.get('traits', {}))}\n"
                f"Strength {c['str']}, Speed {c['spd']}, Health {c['hp']} of {c['hp_max']}, Gold {c['gold']}, "
                f"Skills {', '.join(f'{k} {v}' for k, v in c['skills'].items()) or 'none'}. You are at {c['location']}.\n"
                f"Your secret, known only to you: {c['secret']}\nYour fear: {c['fear']}\nWhat you want more than anything: {c['want']}\n"
                f"YOUR PEOPLE, and how you truly feel about them (act on this):\n{self.relations_text(name)}")

    def apply(self, res: dict, log: list[str], court: bool = False) -> None:
        """Validate and apply a World result block. Anything impossible is clamped and logged.
        Banishment is accepted only on a court day, one name only; the convener's returns are never undone."""
        for r in res.get("results", []) or []:
            c = self.characters.get(str(r.get("who", "")))
            if not c or not c["alive"]: log.append(f"ignored result for unknown or dead '{r.get('who')}'"); continue
            try:
                if "hp" in r: c["hp"] = max(0, min(c["hp_max"], c["hp"] + int(r["hp"])))
                if "gold" in r: c["gold"] = max(0, c["gold"] + int(r["gold"]))
            except (TypeError, ValueError): log.append(f"bad number in result for {c['name']}")
            if r.get("location"):
                dest = place_key(str(r["location"]), self.map)
                if not dest: log.append(f"{c['name']}: '{r['location']}' is not a place on the map, stayed at {c['location']}")
                elif dest != c["location"] and dest not in self.map[c["location"]]["adj"]: log.append(f"{c['name']}: {dest} is not one path from {c['location']}, stayed put")
                else: c["location"] = dest
            if r.get("skill"): k = str(r["skill"]).strip().lower()[:30]; c["skills"][k] = min(9, c["skills"].get(k, 0) + 1)
            if r.get("standing") in ("respected", "feared", "pitied", "hated", "unknown", "loved"): c["standing"] = r["standing"]
        for d in res.get("dead", []) or []:
            c = self.characters.get(str(d.get("who", "")))
            if c and c["alive"]: c["alive"] = False; c["hp"] = 0; c["cause_of_death"] = str(d.get("cause", "unknown"))[:120]
        for c in self.characters.values():
            if c["alive"] and c["hp"] <= 0: c["alive"] = False; c["cause_of_death"] = c["cause_of_death"] or "wounds"
        bl = [str(b) for b in (res.get("banished", []) or []) if str(b) in self.characters]
        if bl and not court: log.append(f"banishment of {', '.join(bl)} ignored: the court does not sit today")
        elif bl:
            if len(bl) > 1: log.append(f"only one may be banished per court; taking {bl[0]}")
            c = self.characters[bl[0]]
            if c.get("returned_day", -1) == self.day: log.append(f"{bl[0]} was returned by fate today and cannot be banished the same day")
            elif not c["banished"]: c["banished"] = True; c["returned_day"] = -1
        for th in res.get("threads", []) or []:
            if isinstance(th, dict) and th.get("status") == "resolved":
                try: self.resolve_thread(int(th.get("id", 0)), str(th.get("note", "")))
                except (TypeError, ValueError): pass
        for fp in res.get("fires_out", []) or []:
            if self.extinguish(str(fp)): log.append(f"fire put out at {fp}")
        for rr in res.get("relations", []) or []:
            if not isinstance(rr, dict): continue
            a, b = str(rr.get("a", "")), str(rr.get("b", "")); why = str(rr.get("why", "") or "")
            self.set_rel(a, b, rr.get("type"), rr.get("feeling"), rr.get("trust"), delta=True, why=why)
            if rr.get("mutual"): self.set_rel(b, a, rr.get("type"), rr.get("feeling"), rr.get("trust"), delta=True, why=why)
        L = res.get("ledger", {}) or {}; g = self.ledger
        try:
            if "grain_weeks" in L: g["grain_weeks"] = max(0, g["grain_weeks"] + int(L["grain_weeks"]))
            if "roofs_broken" in L: g["roofs_broken"] = max(0, g["roofs_broken"] + int(L["roofs_broken"]))
            if "sick" in L: g["sick"] = max(0, g["sick"] + int(L["sick"]))
        except (TypeError, ValueError): log.append("bad number in ledger")
        if "road_safe" in L: g["road_safe"] = bool(L["road_safe"])
        for b in L.get("built", []) or []:
            if str(b).strip() and str(b).strip() not in g["built"]: g["built"].append(str(b).strip()[:60])
        self.day += 1



def extract_json(text: str) -> dict | None:
    """Last fenced ```json block, or the last top-level {...} object in the text."""
    m = list(re.finditer(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S))
    cands = [x.group(1) for x in m]
    if not cands:
        i = text.rfind("{"); j = text.rfind("}")
        if i != -1 and j > i:
            # walk back to find a balanced object
            depth = 0
            for k in range(j, -1, -1):
                if text[k] == "}": depth += 1
                elif text[k] == "{":
                    depth -= 1
                    if depth == 0: cands = [text[k:j + 1]]; break
    for c in reversed(cands):
        try: return json.loads(c)
        except Exception: continue
    return None


def strip_json(text: str) -> str:
    return re.sub(r"```(?:json)?\s*\{.*?\}\s*```", "", text, flags=re.S).strip()


def action_line(text: str) -> str | None:
    m = list(re.finditer(r"^\s*ACTION:\s*(.+?)\s*$", text, re.M | re.I))
    return m[-1].group(1).strip() if m else None


WHISPER_RE = re.compile(r"^\s*WHISPER\s+@([A-Za-z][\w -]*?)\s*:\s*(.*)$", re.I)


def whisper_targets(text: str) -> set[str]:
    return {m.group(1).strip().lower() for ln in text.split("\n") if (m := WHISPER_RE.match(ln))}


MENTION_RE = re.compile(r"@([A-Za-z][\w-]*)")


def mentions(text: str) -> set[str]:
    return {m.lower() for m in MENTION_RE.findall(text or "")}


def visible_text(entry: dict, viewer: str, viewer_place: str | None = None) -> str | None:
    """What `viewer` may see of a message. The World's chronicle and engine notes reach everyone.
    The convener's words reach everyone unless they @mention someone, then only those people (and the World).
    A person's words reach the people standing where they spoke (and themselves, and the World).
    WHISPER lines reach only their target, at the same place."""
    v = viewer.lower(); sp = entry.get("speaker", "").lower()
    if entry.get("kind") == "convener":
        ms = mentions(entry.get("text", ""))
        if ms and v != "world" and v not in ms: return None
    if entry.get("kind") == "speech" and v not in ("world", sp) and viewer_place is not None and entry.get("place") and entry["place"] != viewer_place:
        return None
    keep = []
    for ln in entry.get("text", "").split("\n"):
        m = WHISPER_RE.match(ln)
        if m and v not in (m.group(1).strip().lower(), "world", sp): continue
        if m and v == m.group(1).strip().lower() and viewer_place is not None and entry.get("place") and entry["place"] != viewer_place: continue
        keep.append(ln)
    out = "\n".join(keep).strip()
    return out or None


def can_see(entry: dict, viewer: str) -> bool:
    return visible_text(entry, viewer) is not None

