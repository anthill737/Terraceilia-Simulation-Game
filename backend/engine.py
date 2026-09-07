"""The world: the fixed map, the people, the numbers. Only this module writes them."""
from __future__ import annotations
import datetime as dt, json, math, random, re, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
GAMES = ROOT / "games"

NAMES = json.loads((DATA / "names.json").read_text(encoding="utf-8"))
EVENTS = json.loads((DATA / "events.json").read_text(encoding="utf-8"))
DUTIES: dict[str, dict] = {d["key"]: d for d in json.loads((DATA / "duties.json").read_text(encoding="utf-8"))}
MAX_DUTIES = 3
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
            "gold": rng.randint(1, 9), "skills": {}, "location": rng.choice(places or PLACES), "standing": standing_word(0), "standing_score": 0,
            "alive": True, "gone": False, "gone_reason": "", "trade": "", "home": "", "personality": "", "secret": "", "fear": "", "want": "",
            "cause_of_death": "", "traits": roll_traits(rng), "log": [], "needs": fresh_needs(), "sick": False, "sick_days": 0,
            "duties": [], "dumped": [], "emergency": None}


# ---------------------------------------------------------------- needs, seasons, weather
# Every person has food, warmth and rest on a scale of 0 to 10, and health (hp). Needs fall every day. A need at zero
# takes health, and health at zero is death. Sick people cannot work and get worse until someone tends them.
NEEDS = ("food", "warmth", "rest")
NEED_WORDS = {"food": ["starving", "hungry", "fed"], "warmth": ["freezing", "cold", "warm"], "rest": ["exhausted", "tired", "rested"]}
STORES = ("grain", "meat", "fish", "wood", "meals", "tools", "herbs")     # what the valley keeps; all of it decays and none of it grows without work
PLACE_STATE = ("roof", "warmth", "filth")                                  # what each place is in, 0 to 10; roof and warmth fall, filth rises
SEASONS = [(6, "autumn"), (14, "early winter"), (24, "deep winter"), (10**9, "thaw")]
WEATHER = {"autumn": [("clear", 50), ("rain", 35), ("cold snap", 15)],
           "early winter": [("clear", 30), ("rain", 25), ("snow", 30), ("storm", 15)],
           "deep winter": [("clear", 25), ("snow", 40), ("storm", 20), ("bitter cold", 15)],
           "thaw": [("clear", 45), ("rain", 40), ("storm", 15)]}
COLD = {"cold snap", "snow", "storm", "bitter cold"}
WET = {"rain", "storm"}


def fresh_needs() -> dict:
    return {"food": 8, "warmth": 8, "rest": 8}


def need_word(k: str, v: int) -> str:
    return NEED_WORDS[k][0 if v <= 0 else 1 if v <= 4 else 2]


def season_of(day: int) -> str:
    for top, name in SEASONS:
        if day <= top: return name
    return SEASONS[-1][1]


def roll_weather(day: int, rng: random.Random) -> str:
    table = WEATHER[season_of(day)]; r = rng.random() * sum(w for _, w in table)
    for name, w in table:
        r -= w
        if r < 0: return name
    return table[0][0]


def growing(day: int, weather: str) -> bool:
    """Fields give nothing in winter; nothing planted comes up under snow."""
    return season_of(day) in ("autumn", "thaw") and weather not in ("snow", "bitter cold")


def starting_ledger(players: int, places: int) -> dict:
    """Enough for a few days if nobody works, and not a day more. Grain is in sacks (a sack makes ten meals), meat and fish
    in cuts (one meal each), meals ready to eat, wood in bundles (one warms a place for a day), tools and herbs by the piece."""
    return {"grain": max(4, int(players * 1.2)), "meat": max(2, players // 3), "fish": max(2, players // 4), "wood": max(6, places * 3),
            "meals": max(4, players), "tools": max(3, players // 2), "herbs": max(2, players // 4), "road_safe": False, "built": []}


# ---------------------------------------------------------------- standing
# One number, -9 to 9, and the word the valley uses for it. Nobody decides it; it moves from what a person does and how
# the people around them answer it. The words the World used to hand out ("feared", "pitied") are gone.
STANDING_BANDS = [(-6, "hated"), (-3, "shunned"), (2, "nobody"), (5, "known"), (8, "respected"), (99, "loved")]
STANDING_WORDS = [w for _, w in STANDING_BANDS]


def standing_word(score: int) -> str:
    for top, word in STANDING_BANDS:
        if score < top or top == 99: return word
    return STANDING_WORDS[-1]


STANDING_MID = {"hated": -8, "shunned": -5, "nobody": 0, "known": 3, "respected": 6, "loved": 9, "unknown": 0, "feared": 3, "pitied": -3}    # the last three: old saves only
OLD_GONE_KEY = "bani" + "shed"      # the key saves used before people were "gone"; spelled in two halves so the word itself is out of the game


def standing_score_for(word: str) -> int:
    """The middle of a band, for when fate sets the word by hand."""
    return STANDING_MID.get(word, 0)


def bump_standing(c: dict, delta: int) -> str:
    """Move a person's standing and return the word for it now."""
    c["standing_score"] = max(-9, min(9, int(c.get("standing_score", 0)) + int(delta)))
    c["standing"] = standing_word(c["standing_score"]); return c["standing"]


def note_log(c: dict, day: int, text: str) -> None:
    """A line in a person's own log: what happened to them, in the engine's words."""
    c.setdefault("log", []).append({"day": day, "text": str(text)[:240]}); del c["log"][:-60]


TRAITS = ["warmth", "temper", "honesty", "greed", "courage", "tongue", "desire", "piety", "ambition", "loyalty", "cunning", "drink"]
TRAIT_TEXT = {
    "warmth":  ["You are cruel and enjoy it.", "You are hard and unkind; other people's troubles bore you.", "You are neither kind nor cruel; you look after your own.", "You are decent to people who deserve it.", "You are kind to a fault."],
    "temper":  ["Nothing moves you; you answer insults with a shrug.", "You keep your temper unless pushed.", "You have an ordinary temper.", "You flare fast and say things you regret.", "You are violent when crossed and quick to threaten."],
    "honesty": ["You lie as easily as you breathe, even when the truth would serve.", "You lie when it suits you and feel nothing.", "You bend the truth when it pays.", "You are mostly honest, with exceptions you can name.", "You cannot lie without it showing."],
    "greed":   ["You give without counting.", "You share when asked.", "You want your fair share and no less.", "You want more than your share and say so.", "You would sell your mother's grave for coin and everyone knows it."],
    "courage": ["You run from anything that might hurt.", "You avoid fights and dangerous roads.", "You take ordinary risks.", "You are brave, sometimes stupidly.", "You are reckless; danger is a dare to you."],
    "tongue":  ["You barely talk. A few blunt words, often a curse, and you are done.", "You are blunt and short; you say the thing and stop.", "You talk like anyone else, plainly.", "You are articulate and say things clearly, in plain words that are simply better chosen.", "You talk a lot: you explain, you repeat yourself, you fill the silences."],
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
        self.ledger = d.get("ledger") or starting_ledger(20, 10)
        self.pending: list[dict] = d.get("pending", [])
        self.created = d.get("created", False)
        self.weather: str = d.get("weather", "clear")
        self.upkeep: dict[str, dict] = d.get("upkeep", {})         # per place: roof, warmth, filth; beside the map, which is fixed
        self.duties: dict[str, dict] = d.get("duties", {})         # per duty: unclaimed since, done day, days undone
        self.roster: dict = d.get("roster", {})                    # today's assignment: who does what where, and the emergencies
        self.morning: dict = d.get("morning", {})                  # what the morning left undone, and who complained
        self.reached: list[dict] = d.get("reached", [])            # wants reached and not yet announced by the World
        self.activities: dict[str, dict] = d.get("activities", {})   # name -> what they are doing now, for the map to play
        self.phase: str = d.get("phase", "morning")                # morning, afternoon, evening
        self.bodies: dict[str, str] = d.get("bodies", {})          # the unburied dead: name -> where they lie
        self.day_report: dict = d.get("day_report", {})            # what dawn found: season, weather, changes, the low and the broken and the sick
        for c in self.characters.values():           # games saved under the old rules
            if "gone" not in c: c["gone"] = bool(c.pop(OLD_GONE_KEY, False)); c["gone_reason"] = "driven out, in a game saved under the old rules" if c["gone"] else ""
            if "standing_score" not in c: c["standing_score"] = standing_score_for(c.get("standing", "nobody"))
            c["standing"] = standing_word(c["standing_score"])
            c.setdefault("log", []); c.setdefault("needs", fresh_needs()); c.setdefault("sick", False); c.setdefault("sick_days", 0)
            c.setdefault("duties", []); c.setdefault("dumped", []); c.setdefault("emergency", None)
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
        if "grain_weeks" in self.ledger:             # the old prosperity ledger: carry what it meant across
            old = self.ledger; self.ledger = starting_ledger(max(1, len(self.characters)) or 20, len(self.map))
            self.ledger["grain"] = max(0, int(old.get("grain_weeks", 10)) * 2); self.ledger["road_safe"] = bool(old.get("road_safe")); self.ledger["built"] = list(old.get("built", []))
        for k in STORES: self.ledger.setdefault(k, 0)
        self.ledger.setdefault("road_safe", False); self.ledger.setdefault("built", []); self.seed_places()

    def to_dict(self) -> dict:
        return {"characters": self.characters, "day": self.day, "ledger": self.ledger, "pending": self.pending,
                "created": self.created, "map": self.map, "fate": self.fate, "relations": self.relations,
                "threads": self.threads, "fires": self.fires, "next_thread": self.next_thread,
                "map_name": self.map_name, "map_generated": self.map_generated, "names": self.names, "style": self.style,
                "weather": self.weather, "upkeep": self.upkeep, "bodies": self.bodies, "day_report": self.day_report,
                "duties": self.duties, "roster": self.roster, "morning": self.morning, "phase": self.phase, "reached": self.reached, "activities": self.activities}

    # ---- which map this game plays on
    def install_map(self, v: dict) -> None:
        self.map = v["places"]; self.map_name = v.get("name") or "The valley"; self.map_generated = True
        self.names = list(v.get("names") or []); self.style = v.get("style") or json.loads(json.dumps(BASE_STYLE)); self.seed_places()

    def install_builtin(self) -> None:
        self.map = json.loads(json.dumps(BASE_MAP)); self.map_name = BASE_NAME; self.map_generated = False
        self.names = []; self.style = json.loads(json.dumps(BASE_STYLE)); self.seed_places()

    OUTDOORS = ("forest", "fields", "water", "road", "cave", "ruin")

    def seed_places(self) -> None:
        """Every place starts with a roof that mostly holds, a little warmth, and little filth. Outdoor kinds have no roof to lose.
        Kept beside the map, not in it: the map is fixed, and this is what wears."""
        for n, d in self.map.items():
            u = self.upkeep.setdefault(n, {})
            u.setdefault("roof", 0 if d.get("kind") in self.OUTDOORS else 7); u.setdefault("warmth", 5); u.setdefault("filth", 1)
        for n in list(self.upkeep):
            if n not in self.map: del self.upkeep[n]

    def place_state(self, place: str) -> dict:
        u = self.upkeep.get(place) or {}
        return {k: int(u.get(k, 0)) for k in PLACE_STATE}

    def roofed(self, place: str) -> bool:
        return (self.map.get(place) or {}).get("kind") not in self.OUTDOORS

    def sheltered(self, place: str) -> bool:
        return self.place_state(place)["roof"] >= 4

    # ---- dawn: the valley wears a little more each day, and the people with it
    def dawn(self, rng: random.Random) -> dict:
        """Run once at the start of every day, before anyone speaks. Rolls the weather, decays the stores and the places,
        feeds and warms the people from what there is, moves their needs, lets sickness in, and buries nobody.
        Returns the day report and keeps it on the world for the prompts and the UI."""
        L = self.ledger; day = self.day; season = season_of(day); self.weather = roll_weather(day, rng); cold = self.weather in COLD; wet = self.weather in WET
        before = {k: L[k] for k in STORES}; pbefore = {p: self.place_state(p) for p in self.map}
        lines: list[str] = []; sick_new: list[str] = []; dead: list[str] = []
        # stores spoil whether or not anyone touches them
        L["grain"] = max(0, L["grain"] - (1 if rng.random() < .5 else 0)); L["meat"] = max(0, L["meat"] - (1 if not cold else 0)); L["fish"] = max(0, L["fish"] - (2 if not cold else 1))
        L["meals"] = max(0, L["meals"] - max(0, (L["meals"] + 9) // 10 - 1)); L["herbs"] = max(0, L["herbs"] - (1 if day % 2 == 0 else 0))
        if L["tools"] > 0 and rng.random() < .15: L["tools"] -= 1
        # places: roofs rot in the wet, warmth needs wood every day, filth builds where people live and where the dead lie
        self.seed_places()
        for p in self.map:
            u = self.upkeep[p]; here = self.at(p)
            if u["roof"] > 0 and (wet or rng.random() < .2): u["roof"] = max(0, u["roof"] - (2 if self.weather == "storm" else 1))
            if here:
                need = 2 if cold else 1
                if L["wood"] >= need: L["wood"] -= need; u["warmth"] = min(10, u["warmth"] + (1 if cold else 2))
                else: u["warmth"] = max(0, u["warmth"] - (3 if cold else 2))
                if u["roof"] < 4 and (wet or cold): u["warmth"] = max(0, u["warmth"] - 2)
                u["filth"] = min(10, u["filth"] + 1 + len(here) // 4)
            else:
                u["warmth"] = max(0, u["warmth"] - (2 if cold else 1))
                if u["filth"] > 0 and not any(pl == p for pl in self.bodies.values()): u["filth"] -= 1
            u["filth"] = min(10, u["filth"] + sum(1 for pl in self.bodies.values() if pl == p))
        # the people: they eat what there is, warm themselves at what fire there is, and rest as well as the roof lets them
        for c in sorted(self.living(), key=lambda c: c["seat"]):
            n = c.setdefault("needs", fresh_needs()); place = self.place_state(c["location"])
            if L["meals"] > 0: L["meals"] -= 1; n["food"] = min(10, n["food"] + 4)
            elif L["grain"] > 0 and rng.random() < .5: L["grain"] -= 1; n["food"] = min(7, n["food"] + 2)
            elif L["fish"] > 0: L["fish"] -= 1; n["food"] = min(8, n["food"] + 3)
            elif L["meat"] > 0: L["meat"] -= 1; n["food"] = min(9, n["food"] + 3)
            n["food"] = max(0, n["food"] - 3)
            warmth = place["warmth"]
            n["warmth"] = max(0, min(10, n["warmth"] + (2 if warmth >= 6 else 0 if warmth >= 3 else -2) - (2 if cold else 1)))
            n["rest"] = max(0, min(10, n["rest"] + (3 if place["roof"] >= 4 and warmth >= 3 else 1) - 2))
            hurt = [k for k in NEEDS if n[k] <= 0]
            if hurt:
                c["hp"] = max(0, c["hp"] - len(hurt)); note_log(c, day, f"You are {', '.join(need_word(k, 0) for k in hurt)}. It is taking your health.")
            # sickness: filth, the unburied, cold and hunger all let it in; the sick get worse until they are tended
            risk = 0.0
            if place["filth"] >= 6: risk += .15
            risk += .08 * sum(1 for pl in self.bodies.values() if pl == c["location"])
            if n["warmth"] <= 0: risk += .25
            if n["food"] <= 0: risk += .10
            if season != "autumn": risk += .03
            if not c.get("sick") and rng.random() < risk:
                c["sick"] = True; c["sick_days"] = 0; sick_new.append(c["name"]); note_log(c, day, "You woke sick. You cannot work until someone tends you.")
            elif c.get("sick"):
                c["sick_days"] = c.get("sick_days", 0) + 1
                if c.get("tended_day") == day - 1 and rng.random() < .6:
                    c["sick"] = False; note_log(c, day, "The tending worked. You are on your feet again.")
                elif n["food"] >= 5 and n["warmth"] >= 5 and rng.random() < .12:
                    c["sick"] = False; note_log(c, day, "You slept it off, warm and fed.")
                else: c["hp"] = max(0, c["hp"] - 1)
            if c["hp"] <= 0 and c["alive"]:
                cause = "starved" if n["food"] <= 0 else "froze" if n["warmth"] <= 0 else "died of sickness" if c.get("sick") else "died worn out"
                self.kill(c, cause); dead.append(f"{c['name']} {cause} at {c['location']}")
                note_log(c, day, f"You {cause}.")
        # the report
        change = {k: L[k] - before[k] for k in STORES}
        low = [k for k in STORES if L[k] <= (2 if k in ("tools", "herbs") else 4)]
        broken = [p for p in self.map if self.roofed(p) and self.upkeep[p]["roof"] < 4]
        coldp = [p for p in self.map if self.at(p) and self.upkeep[p]["warmth"] <= 2]
        foul = [p for p in self.map if self.upkeep[p]["filth"] >= 6]
        sick = [c["name"] for c in self.living() if c.get("sick")]
        hungry = [c["name"] for c in self.living() if c["needs"]["food"] <= 2]; freezing = [c["name"] for c in self.living() if c["needs"]["warmth"] <= 2]
        lines.append(f"Day {day}, {season}, {self.weather}.")
        if low: lines.append("Low: " + ", ".join(f"{k} {L[k]}" for k in low) + ".")
        if broken: lines.append("Roofs failing: " + ", ".join(broken) + ".")
        if coldp: lines.append("Cold hearths: " + ", ".join(coldp) + ".")
        if foul: lines.append("Foul with filth: " + ", ".join(foul) + ".")
        if self.bodies: lines.append("Unburied: " + ", ".join(f"{n} at {p}" for n, p in self.bodies.items()) + ".")
        if self.fires: lines.append("Burning: " + ", ".join(self.fires) + ".")
        if sick: lines.append("Sick and cannot work: " + ", ".join(sick) + ".")
        if hungry: lines.append("Hungry: " + ", ".join(hungry) + ".")
        if freezing: lines.append("Freezing: " + ", ".join(freezing) + ".")
        if sick_new: lines.append("Fell sick in the night: " + ", ".join(sick_new) + ".")
        if dead: lines.append("Dead by morning: " + "; ".join(dead) + ".")
        self.day_report = {"day": day, "season": season, "weather": self.weather, "growing": growing(day, self.weather), "ledger": dict(L), "change": change,
                           "places": {p: {k: self.place_state(p)[k] - pbefore[p][k] for k in PLACE_STATE} for p in self.map},
                           "low": low, "broken": broken, "cold": coldp, "foul": foul, "sick": sick, "hungry": hungry, "freezing": freezing, "sick_new": sick_new, "dead": dead,
                           "lines": lines}
        return self.day_report

    def kill(self, c: dict, cause: str) -> None:
        """The one way a person dies. The body lies where they were until someone buries it."""
        if not c["alive"]: return
        c["alive"] = False; c["hp"] = 0; c["cause_of_death"] = (cause or "unknown")[:120]; c["sick"] = False
        self.bodies[c["name"]] = c["location"]

    def bury(self, name: str) -> bool:
        if name in self.bodies: del self.bodies[name]; return True
        return False

    def ledger_text(self) -> str:
        L = self.ledger; ch = (self.day_report or {}).get("change", {})
        parts = [f"{k} {L[k]}" + (f" ({ch[k]:+d})" if ch.get(k) else "") for k in STORES]
        return ", ".join(parts) + f"; road {'safe' if L.get('road_safe') else 'unsafe'} after dark; built: {', '.join(L.get('built', [])) or 'nothing'}"

    def places_text(self) -> str:
        return "\n".join(f"- {p}: {'roof ' + str(self.place_state(p)['roof']) + '/10, ' if self.roofed(p) else 'no roof, '}warmth {self.place_state(p)['warmth']}/10, filth {self.place_state(p)['filth']}/10" for p in self.map)

    def needs_text(self, name: str) -> str:
        c = self.characters[name]; n = c.get("needs") or fresh_needs()
        words = ", ".join(f"{need_word(k, n[k])} ({k} {n[k]}/10)" for k in NEEDS)
        return f"HOW YOU ARE: {words}; health {c['hp']} of {c['hp_max']}" + ("; SICK, you cannot work until someone tends you" if c.get("sick") else "") + "."

    def dawn_text(self) -> str:
        return "\n".join((self.day_report or {}).get("lines") or [f"Day {self.day}, {season_of(self.day)}, {self.weather}."])

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
            if c["hp"] <= 0 and c["alive"]: self.kill(c, f"burned at {p}")

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

    def ties_of(self, name: str) -> list[str]:
        """The people this person is really tied to: a named tie, or a strong feeling or trust either way."""
        out = []
        for b, r in self.relations.get(name, {}).items():
            if b in self.characters and (r["type"] != "none" or abs(r["feeling"]) >= 3 or abs(r["trust"]) >= 3): out.append(b)
        for a, rs in self.relations.items():
            r = rs.get(name)
            if a in self.characters and a != name and a not in out and r and (r["type"] != "none" or abs(r["feeling"]) >= 3 or abs(r["trust"]) >= 3): out.append(a)
        return out

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
        self.kill(c, "struck down by fate"); self.fate.append(f"{name} died suddenly, of no cause anyone can name."); return f"{name} is dead"

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
            if "standing" in fx: bump_standing(who, int(fx["standing"]))
            if "sick" in fx:
                pool = [c for c in self.living() if not c.get("sick")]; rng.shuffle(pool)
                for c in pool[:max(0, int(fx["sick"]))]: c["sick"] = True; c["sick_days"] = 0; note_log(c, self.day, "You fell sick.")
            if "grain" in fx: self.ledger["grain"] = max(0, self.ledger["grain"] + int(fx["grain"]))
            if "roofs" in fx:
                roofed = [p for p in self.map if self.roofed(p) and self.place_state(p)["roof"] > 0]
                if roofed: rp = place if place in roofed else rng.choice(roofed); self.upkeep[rp]["roof"] = max(0, self.upkeep[rp]["roof"] - 4 * int(fx["roofs"]))
            if fx.get("road_unsafe"): self.ledger["road_safe"] = False
            if fx.get("destroy") and fixture in fixtures: self.map[place].setdefault("destroyed", []).append(fixture)
            if who["hp"] <= 0 and who["alive"]: self.kill(who, "died of it")
            if e.get("thread"):
                t = self.open_thread(text, place if ("{place}" in e["t"] or e.get("place") or e.get("spawn")) else None, [who["name"]] + ([who2["name"]] if "{who2}" in e["t"] else []), e.get("spawn"))
                text = f"{text} [situation #{t['id']}]"
            out.append(text); log.append(f"event: {text[:60]}")
        return out

    def living(self) -> list[dict]:
        return [c for c in self.characters.values() if c["alive"] and not c["gone"]]

    def gone_list(self) -> list[str]:
        return [f"{c['name']} ({c['gone_reason'] or 'gone'})" for c in self.characters.values() if c["gone"] and c["alive"]]

    def public_table(self) -> str:
        rows = [f"{c['name']}: {c['location']}, {c['standing']}" for c in sorted(self.living(), key=lambda c: c["seat"])]
        dead = [f"{c['name']} ({c['cause_of_death']})" for c in self.characters.values() if not c["alive"]]
        return "WHO IS WHERE\n" + "\n".join(rows) + f"\nDEAD: {', '.join(dead) or 'none'}\nGONE: {', '.join(self.gone_list()) or 'none'}"

    def standings_table(self) -> str:
        rows = [f"| {c['name']} | {c['location']} | {c['hp']}/{c['hp_max']}{' sick' if c.get('sick') else ''} | {c['gold']} | {', '.join(f'{k} {v}' for k, v in c['skills'].items()) or 'none'} | {c['standing']} |"
                for c in sorted(self.living(), key=lambda c: c["seat"])]
        dead = [f"{c['name']} ({c['cause_of_death']})" for c in self.characters.values() if not c["alive"]]
        led = f"PROSPERITY, day {self.day}, {season_of(self.day)}, {self.weather}: {self.ledger_text()}."
        return (led + "\n\nSTANDINGS\n| Name | Location | Health | Gold | Skills | Standing |\n|---|---|---|---|---|---|\n"
                + "\n".join(rows) + f"\n\nDEAD: {', '.join(dead) or 'none'}\nGONE: {', '.join(self.gone_list()) or 'none'}")

    # ---- what one person does to another, decided here and only here
    # Nothing in the valley is decided by a body. A person drives someone out, refuses them, takes their work, or leaves,
    # and the engine settles it: the target resists, the people standing there take a side, and the dice fall.
    SOCIAL_KINDS = ("drive_out", "refuse", "take_duty", "leave")

    def social_intent(self, actor: str, text: str) -> tuple[str, str | None] | None:
        """(kind, target) when an ACTION line is one of the four social acts, else None. The target is a living person named in it."""
        t = " ".join((text or "").lower().split())
        if not t: return None
        names = [c["name"] for c in self.living() if c["name"] != actor]
        target = next((n for n in sorted(names, key=len, reverse=True) if re.search(r"(?<![\w@])@?" + re.escape(n.lower()) + r"(?:'s)?\b", t)), None)
        if re.search(r"\b(leave|leaving|quit|abandon|walk out of|walk away from|go from|get out of)\b.{0,30}\b(valley|village|this place|for good|forever|and (?:not|never) come back)\b", t) \
                or re.search(r"\b(leave|leaving)\b.{0,12}\bfor good\b", t) or re.search(r"\bpack\b.{0,20}\b(leave|go)\b", t):
            if not target or re.search(r"\bi(?:'m| am|'ll| will)? (?:leav|quit|go|walk|pack|am done|take the road)", t): return ("leave", None)
        if not target: return None
        if re.search(r"\b(drive|driving|run|running|chase|chasing|throw|throwing|force|forcing|push|pushing|cast|casting|turn|turning|kick|kicking|see|march)\b.{0,40}\b(out|off|away|from the valley|out of the valley)\b", t) \
                or re.search(r"\b(exile|expel|evict)\w*\b", t) or re.search(r"\b(out of (?:the|this|our) valley|out of here for good|leave the valley or else)\b", t):
            return ("drive_out", target)
        if re.search(r"\b(refuse|refusing|deny|denying|won't|will not|shan't|not going to|stop)\b.{0,30}\b(share|sharing|feed|feeding|give|giving|sell|selling|lend|lending|help|helping|serve|serving|bread|grain|food|fire|water|shelter|roof|a place)\b", t) \
                or re.search(r"\b(cut|cutting)\b.{0,20}\b(off|out)\b", t) or re.search(r"\bno (?:more )?(?:bread|grain|food|help|share|fire)\b.{0,20}\bfor\b", t):
            return ("refuse", target)
        if re.search(r"\b(take|taking|seize|seizing|claim|claiming|do|doing)\b.{0,30}\b(duty|duties|job|work|post|place at|role|trade|charge of)\b", t) and re.search(r"\b(from|over|off|his|her|their|" + re.escape(target.lower()) + r"'s)\b", t):
            return ("take_duty", target)
        return None

    def sides(self, actor: str, target: str, place: str) -> tuple[list[str], list[str]]:
        """Who standing at `place` stands with the actor, and who with the target, by how they feel about each."""
        with_a: list[str] = []; with_t: list[str] = []
        for c in self.at(place):
            if c["name"] in (actor, target): continue
            fa = self.rel(c["name"], actor)["feeling"]; ft = self.rel(c["name"], target)["feeling"]
            if fa - ft >= 2: with_a.append(c["name"])
            elif ft - fa >= 2: with_t.append(c["name"])
        return with_a, with_t

    def resolve_social(self, actor: str, kind: str, target: str | None, rng: random.Random, resisting: bool = False) -> dict:
        """Settle one social act now and write it into the world. Returns {kind, actor, target, ok, text, with_actor, with_target, rolls}.
        Standing, ties, and dice decide it; no group does. `resisting` is true when the target's own action today pushed back."""
        a = self.characters[actor]; here = a["location"]
        if kind == "leave":
            a["gone"] = True; a["gone_reason"] = f"left the valley on day {self.day}"; a["location"] = here
            note_log(a, self.day, "You left the valley for good, by your own choice.")
            txt = f"{actor} left the valley for good."
            for c in self.living(): self.set_rel(c["name"], actor, feeling=-1, delta=True, why=f"{actor} walked out on the valley")
            return {"kind": kind, "actor": actor, "target": None, "ok": True, "text": txt, "with_actor": [], "with_target": [], "rolls": []}
        t = self.characters.get(target or "")
        if not t or not t["alive"] or t["gone"]:
            return {"kind": kind, "actor": actor, "target": target, "ok": False, "text": f"{actor} tried to act against {target}, who is not here to be acted on.", "with_actor": [], "with_target": [], "rolls": []}
        with_a, with_t = self.sides(actor, target, here) if t["location"] == here else ([], [])
        ra, rt = rng.randint(1, 6), rng.randint(1, 6)
        tr = t.get("traits", {}); grit = (int(tr.get("courage", 3)) + int(tr.get("temper", 3)) - 6) // 2
        score_a = ra + int(a.get("standing_score", 0)) // 2 + len(with_a)
        score_t = rt + int(t.get("standing_score", 0)) // 2 + len(with_t) + grit + (2 if resisting else 0)
        if kind == "refuse": score_t -= 2                   # a refusal is a person's own to make; it takes a crowd to stop one
        if kind == "drive_out" and t["location"] != here: score_a -= 3     # you cannot drive out someone who is not in front of you
        ok = score_a > score_t
        who_a = f", with {', '.join(with_a)} behind them" if with_a else ""; who_t = f", with {', '.join(with_t)} standing by {target}" if with_t else ""
        if kind == "drive_out":
            if ok:
                t["gone"] = True; t["gone_reason"] = f"driven out by {actor} on day {self.day}"
                note_log(t, self.day, f"{actor} drove you out of the valley{who_a}. You are gone.")
                note_log(a, self.day, f"You drove {target} out of the valley{who_a}.")
                bump_standing(a, 1 if with_a else -1); txt = f"{actor} drove {target} out of the valley{who_a}{who_t}. {target} is gone."
                for n in with_t: self.set_rel(n, actor, feeling=-2, trust=-1, delta=True, why=f"drove {target} out over their objection")
            else:
                bump_standing(a, -2); a["hp"] = max(1, a["hp"] - (1 if grit > 0 else 0))
                note_log(a, self.day, f"You tried to drive {target} out and failed{who_t}. People saw."); note_log(t, self.day, f"{actor} tried to drive you out and failed{who_t}.")
                txt = f"{actor} tried to drive {target} out{who_a} and failed{who_t}. {actor} lost face."
                self.set_rel(target, actor, feeling=-3, trust=-2, delta=True, why="tried to drive them out of the valley")
            self.set_rel(actor, target, feeling=-2, delta=True, why="tried to be rid of them")
        elif kind == "refuse":
            if ok:
                bump_standing(t, -1); note_log(t, self.day, f"{actor} refused to share with you{who_a}."); note_log(a, self.day, f"You refused {target}{who_a}.")
                txt = f"{actor} refused to share with {target}{who_a}{who_t}. {target} went without."
                t["hp"] = max(1, t["hp"] - 1)
            else:
                bump_standing(a, -1); note_log(a, self.day, f"You refused {target} and the people there made you share anyway{who_t}."); note_log(t, self.day, f"{actor} refused you, and the people there shamed them into it{who_t}.")
                txt = f"{actor} refused {target}{who_a}, and the people there shamed them into sharing{who_t}."
            self.set_rel(target, actor, feeling=-2, trust=-1, delta=True, why="refused to share")
        elif kind == "take_duty":
            taken = self.transfer_duty(target, actor) if ok else None
            if ok:
                bump_standing(t, -1); bump_standing(a, 1)
                what = taken or "their work"
                note_log(t, self.day, f"{actor} took {what} from you{who_a}."); note_log(a, self.day, f"You took {what} from {target}{who_a}.")
                txt = f"{actor} took {what} from {target}{who_a}{who_t}."
            else:
                bump_standing(a, -1); note_log(a, self.day, f"You tried to take {target}'s work and were refused{who_t}."); note_log(t, self.day, f"{actor} tried to take your work and was refused{who_t}.")
                txt = f"{actor} tried to take {target}'s work{who_a} and was refused{who_t}."
            self.set_rel(target, actor, feeling=-2, trust=-1, delta=True, why="tried to take their work")
        else:
            return {"kind": kind, "actor": actor, "target": target, "ok": False, "text": "", "with_actor": [], "with_target": [], "rolls": []}
        return {"kind": kind, "actor": actor, "target": target, "ok": ok, "text": txt, "with_actor": with_a, "with_target": with_t, "rolls": [ra, rt]}

    # ---- duties: the valley's work, split into named pieces that people hold
    # A person holds one to three. They change through play: refused (standing drops, the duty goes unclaimed), handed to
    # someone, taken up when unclaimed, or taken from someone by the contest above. Fate can set them by hand.
    def duty_state(self, key: str) -> dict:
        return self.duties.setdefault(key, {"unclaimed_day": None, "done_day": 0, "undone_days": 0, "dumped_on": None, "last_output": ""})

    def holders(self, key: str) -> list[str]:
        return [c["name"] for c in self.living() if key in c.get("duties", [])]

    def able(self, c: dict) -> bool:
        return c["alive"] and not c["gone"] and not c.get("sick") and c["hp"] > 0

    def duty_key(self, text: str) -> str | None:
        """Which duty a line of text names, by its key, its label, or an alias. The longest match wins."""
        t = " ".join((text or "").lower().split()); best = None
        for k, d in DUTIES.items():
            for a in [k, d["label"]] + d.get("aliases", []):
                if re.search(r"\b" + re.escape(a.lower()) + r"\b", t) and (best is None or len(a) > best[1]): best = (k, len(a))
        return best[0] if best else None

    def duty_place(self, key: str, holder: str | None = None) -> str:
        """Where a duty is done on this map: a place of the right kind, or the place that needs it most, or the holder's home."""
        d = DUTIES[key]; w = d.get("where", {}); dyn = w.get("dynamic")
        if dyn == "worst_roof":
            cands = [p for p in self.map if self.roofed(p)]
            if cands: return min(cands, key=lambda p: self.place_state(p)["roof"])
        elif dyn == "foulest":
            return max(self.map, key=lambda p: self.place_state(p)["filth"])
        elif dyn == "body":
            if self.bodies: return next(iter(self.bodies.values()))
        elif dyn == "sick":
            sick = [c for c in self.living() if c.get("sick")]
            if sick: return sick[0]["location"]
        elif dyn == "coldest":
            lived = [p for p in self.map if self.at(p)] or list(self.map)
            return min(lived, key=lambda p: self.place_state(p)["warmth"])
        words = [a.lower() for a in d.get("aliases", []) if len(a) > 3]
        for p, pd in self.map.items():          # a place whose things are named for the work: the fishing boats, the hunter's blind
            if any(re.search(r"\b" + re.escape(a) + r"\b", f.lower()) for f in pd.get("fixtures", []) for a in words) and pd.get("kind") in w.get("kinds", []) + w.get("fallback", []) + ["village", "town"]:
                return p
        for kind in w.get("kinds", []):
            for p, pd in self.map.items():
                if pd.get("kind") == kind: return p
        for feat in w.get("features", []):
            for p, pd in self.map.items():
                if pd.get("feature") == feat: return p
        for kind in w.get("fallback", []):
            for p, pd in self.map.items():
                if pd.get("kind") == kind: return p
        c = self.characters.get(holder or "")
        home = (c or {}).get("home") or (c or {}).get("location")
        return home if home in self.map else next(iter(self.map))

    def distance(self, a: str, b: str) -> int:
        """Paths between two places, or a large number when there is no way."""
        if a == b: return 0
        if a not in self.map or b not in self.map: return 99
        seen = {a}; frontier = [a]; n = 0
        while frontier:
            n += 1; nxt = []
            for p in frontier:
                for q in self.map[p]["adj"]:
                    if q == b: return n
                    if q not in seen: seen.add(q); nxt.append(q)
            frontier = nxt
        return 99

    def duty_fit(self, c: dict, key: str) -> float:
        """How well a person fits a duty: their trade, their nature, and any skill they already have."""
        d = DUTIES[key]; seed = d.get("seed", {}); trade = (c.get("trade") or "").lower(); score = 0.0
        if any(t in trade for t in seed.get("trades", [])): score += 5
        tr = c.get("traits", {})
        for k, v in seed.get("traits", {}).items():
            if k == "str": score += 1.5 if int(c.get("str", 0)) >= v else 0
            elif v >= 4 and int(tr.get(k, 3)) >= v: score += 1
            elif v <= 2 and int(tr.get(k, 3)) <= v: score += 1
        score += int(c.get("skills", {}).get(d["skill"], 0)) * 0.7
        return score

    def seed_duties(self, rng: random.Random) -> None:
        """Every duty gets its best fitting holder; then everyone left without work gets the duty they fit best; then the ambitious
        and the well suited pick up a second or third. Not a table of priorities: a list on each person that play then moves."""
        ppl = self.living()
        if not ppl: return
        for c in ppl: c["duties"] = []
        fit = {(c["name"], k): self.duty_fit(c, k) + rng.random() * 1.5 for c in ppl for k in DUTIES}
        for k in DUTIES:
            free = [c for c in ppl if len(c["duties"]) < MAX_DUTIES]
            if not free: break
            best = max(free, key=lambda c: fit[(c["name"], k)] - 1.2 * len(c["duties"]))
            best["duties"].append(k)
        for c in ppl:
            if not c["duties"]: c["duties"].append(max(DUTIES, key=lambda k: fit[(c["name"], k)]))
        for c in ppl:
            want = 1 + (1 if int(c.get("traits", {}).get("ambition", 3)) >= 4 else 0) + (1 if rng.random() < .35 else 0)
            for k in sorted(DUTIES, key=lambda k: -fit[(c["name"], k)]):
                if len(c["duties"]) >= min(MAX_DUTIES, want): break
                if k not in c["duties"] and fit[(c["name"], k)] >= 3: c["duties"].append(k)
        for k in DUTIES: self.duty_state(k)

    def refuse_duty(self, name: str, key: str) -> str:
        c = self.characters.get(name)
        if not c or key not in DUTIES: return "no such person or duty"
        if key not in c.get("duties", []): return f"{name} does not hold {DUTIES[key]['label']}"
        c["duties"].remove(key); bump_standing(c, -1); st = self.duty_state(key)
        if not self.holders(key): st["unclaimed_day"] = self.day
        note_log(c, self.day, f"You refused {DUTIES[key]['label']}. People noticed.")
        return f"{name} refused {DUTIES[key]['label']}" + ("; it is unclaimed" if not self.holders(key) else "")

    def hand_duty(self, name: str, to: str, key: str) -> str:
        c = self.characters.get(name); t = self.characters.get(to)
        if not c or not t or key not in DUTIES: return "no such person or duty"
        if key not in c.get("duties", []): return f"{name} does not hold {DUTIES[key]['label']}"
        if not self.able(t): return f"{to} cannot take it on"
        if len(t.setdefault("duties", [])) >= MAX_DUTIES: return f"{to} already holds {MAX_DUTIES} duties"
        c["duties"].remove(key)
        if key not in t["duties"]: t["duties"].append(key)
        note_log(c, self.day, f"You handed {DUTIES[key]['label']} to {to}."); note_log(t, self.day, f"{name} handed you {DUTIES[key]['label']}.")
        return f"{name} handed {DUTIES[key]['label']} to {to}"

    def claim_duty(self, name: str, key: str) -> str:
        c = self.characters.get(name)
        if not c or key not in DUTIES: return "no such person or duty"
        if key in c.get("duties", []): return f"{name} already holds {DUTIES[key]['label']}"
        if self.holders(key): return f"{DUTIES[key]['label']} is held by {', '.join(self.holders(key))}; it must be taken from them or handed over"
        if len(c.setdefault("duties", [])) >= MAX_DUTIES: return f"{name} already holds {MAX_DUTIES} duties"
        c["duties"].append(key); self.duty_state(key)["unclaimed_day"] = None; bump_standing(c, 1)
        note_log(c, self.day, f"You took up {DUTIES[key]['label']}, which nobody held.")
        return f"{name} took up {DUTIES[key]['label']}"

    def set_duties(self, name: str, keys: list[str]) -> str:
        """Fate's hand: set a person's duties outright."""
        c = self.characters.get(name)
        if not c: return "no such person"
        new = []
        for k in keys:
            k = str(k).strip().lower()
            if k in DUTIES and k not in new: new.append(k)
        new = new[:MAX_DUTIES]
        if new == c.get("duties", []): return "no change"
        c["duties"] = new
        for k in DUTIES:
            st = self.duty_state(k)
            if not self.holders(k) and st["unclaimed_day"] is None: st["unclaimed_day"] = self.day
            elif self.holders(k): st["unclaimed_day"] = None
        return f"{name}'s duties are now {', '.join(DUTIES[k]['label'] for k in new) or 'none'}"

    def transfer_duty(self, frm: str, to: str) -> str | None:
        """The contest's prize: one duty moves from the loser to the winner. Returns its label, or None if there was nothing to take."""
        c = self.characters.get(frm); t = self.characters.get(to)
        if not c or not t or not c.get("duties"): return None
        key = c["duties"][0]; c["duties"].remove(key)
        t.setdefault("duties", [])
        if key not in t["duties"] and len(t["duties"]) < MAX_DUTIES: t["duties"].append(key)
        elif not self.holders(key): self.duty_state(key)["unclaimed_day"] = self.day
        return DUTIES[key]["label"]

    def duty_intent(self, actor: str, text: str) -> tuple[str, str, str | None] | None:
        """(kind, duty, other) when an ACTION line refuses, hands over, or takes up a duty, else None."""
        t = " ".join((text or "").lower().split()); key = self.duty_key(t)
        if not key: return None
        names = [c["name"] for c in self.living() if c["name"] != actor]
        other = next((n for n in sorted(names, key=len, reverse=True) if re.search(r"(?<![\w@])@?" + re.escape(n.lower()) + r"\b", t)), None)
        if re.search(r"\b(refuse|refusing|won't do|will not do|not doing|quit|quitting|give up|giving up|drop|dropping|walk away from|done with|no longer)\b", t) and not other:
            return ("refuse_duty", key, None)
        if other and re.search(r"\b(hand|handing|give|giving|pass|passing|leave|leaving)\b.{0,40}\b(to|over to)\b", t) and re.search(r"\b(hand|handing|give|giving|pass|passing|leave|leaving)\b", t):
            return ("hand_duty", key, other)
        if not other and re.search(r"\b(take up|take on|take over|take|claim|pick up|i'll do|i will do|i'll take|start doing|see to)\b", t):
            return ("claim_duty", key, None)
        return None

    def resolve_duty_actions(self, actions: list[dict], log: list[str]) -> list[dict]:
        """Pull the duty acts out of today's actions and settle them. Returns their outcomes; the acts leave the list."""
        out = []
        for a in list(actions):
            it = self.duty_intent(a["who"], a["text"])
            if not it: continue
            kind, key, other = it
            r = self.refuse_duty(a["who"], key) if kind == "refuse_duty" else self.hand_duty(a["who"], other, key) if kind == "hand_duty" else self.claim_duty(a["who"], key)
            ok = not (r.startswith("no such") or "does not hold" in r or "already" in r or "cannot" in r or "is held by" in r)
            out.append({"kind": kind, "actor": a["who"], "target": other, "ok": ok, "text": r + "."}); log.append(f"{kind}: {r[:80]}")
            if ok: actions.remove(a)
        return out

    def assign_day(self, rng: random.Random) -> dict:
        """Before anyone speaks: every unclaimed duty is dumped on the nearest able person with room for it, for today only, and
        emergencies (fire, someone badly hurt, an attack) pull whoever is nearest regardless of duty. Returns today's roster."""
        for c in self.characters.values(): c["dumped"] = []; c["emergency"] = None
        roster: dict[str, dict] = {}
        for k in DUTIES:
            st = self.duty_state(k); hs = [h for h in self.holders(k) if self.able(self.characters[h])]
            place = self.duty_place(k, hs[0] if hs else None)
            if not hs:
                if self.holders(k): st["unclaimed_day"] = None       # held, but everyone holding it is sick today
                elif st["unclaimed_day"] is None: st["unclaimed_day"] = self.day
                cands = [c for c in self.living() if self.able(c) and len(c.get("duties", [])) + len(c["dumped"]) < MAX_DUTIES]
                if cands:
                    pick = min(cands, key=lambda c: (self.distance(c["location"], place), len(c.get("duties", [])) + len(c["dumped"]), rng.random()))
                    pick["dumped"].append(k); hs = [pick["name"]]
                    note_log(pick, self.day, f"{DUTIES[k]['label'].capitalize()} was dumped on you today: nobody holds it and you were nearest.")
            roster[k] = {"holders": hs, "place": place, "unclaimed": not self.holders(k), "dumped_on": hs[0] if hs and k in self.characters[hs[0]].get("dumped", []) else None,
                         "undone_days": st.get("undone_days", 0)}
        # emergencies
        emergencies: list[dict] = []
        for p in list(self.fires): emergencies.append({"kind": "fire", "place": p, "text": f"fire at {p}"})
        for c in self.living():
            if c["hp"] <= 3 and not c.get("sick"): emergencies.append({"kind": "injury", "place": c["location"], "who": c["name"], "text": f"{c['name']} badly hurt at {c['location']}"})
        for t in self.open_threads():
            if t.get("day") == self.day - 1 and re.search(r"\b(raid|bandit|attack|wolf|wolves|deserter, armed)\b", t["text"], re.I) and t.get("place"):
                emergencies.append({"kind": "attack", "place": t["place"], "text": t["text"][:80]})
        for e in emergencies:
            pool = [c for c in self.living() if self.able(c) and not c.get("emergency") and c["name"] != e.get("who")]
            pool.sort(key=lambda c: (self.distance(c["location"], e["place"]), rng.random()))
            for c in pool[:2]:
                c["emergency"] = e; note_log(c, self.day, f"Emergency: {e['text']}. You are nearest; it pulls you off whatever else you meant to do.")
                self.set_activity(c["name"], "emergency", e["text"][:40], [{"place": e["place"], "what": e["text"][:40], "dur": 0}], immediate=True)
                if e["place"] in self.map: c["location"] = e["place"]        # pulled at once, not when they get round to it
            e["pulled"] = [c["name"] for c in pool[:2]]
        self.roster = {"day": self.day, "duties": roster, "emergencies": emergencies}
        return self.roster

    def duty_brief(self, name: str) -> str:
        """What a person is told about their work today: each duty with its place, its output, and what it costs if skipped."""
        c = self.characters[name]; lines = []
        if c.get("emergency"):
            e = c["emergency"]; lines.append(f"EMERGENCY, before anything else: {e['text']}. Go to {e['place']} and deal with it.")
        for k in list(c.get("duties", [])) + list(c.get("dumped", [])):
            d = DUTIES[k]; place = self.duty_place(k, name); dumped = k in c.get("dumped", [])
            prod = ", ".join(f"{v} {s}" for s, v in d.get("produces", {}).items()) or ", ".join(f"{k2} {v:+d}" for k2, v in d.get("effect", {}).items() if k2 in ("roof", "warmth", "filth")) or "keeps things from getting worse"
            cost = ", ".join(f"{v} {s}" for s, v in d.get("consumes", {}).items())
            lines.append(f"- {d['label'].upper()}{' (dumped on you today, nobody holds it)' if dumped else ''}: {d['verb']} at {place}. Makes {prod}" + (f"; uses {cost}" if cost else "") + f". If skipped: {d['breaks']}.")
        if not lines: return "YOUR WORK TODAY: nothing is yours to do. Take up something unclaimed, or do as you like."
        return "YOUR WORK TODAY:\n" + "\n".join(lines)

    def do_duty(self, name: str, key: str, rng: random.Random) -> dict:
        """Work, resolved here: output rolled from skill and dice, the ledger moved, the skill nudged up. Returns what happened."""
        c = self.characters[name]; d = DUTIES[key]; L = self.ledger; place = self.duty_place(key, name); st = self.duty_state(key)
        fx0 = d.get("effect", {}); st["done_day"] = self.day; st["undone_days"] = 0
        if "tend" in fx0 and not any(x.get("sick") for x in self.living()):
            return {"who": name, "duty": key, "place": place, "roll": 0, "skill": 0, "made": {}, "used": {}, "text": f"{name} went {d['verb']} at {place} and found nobody sick."}
        if "bury" in fx0 and not self.bodies:
            return {"who": name, "duty": key, "place": place, "roll": 0, "skill": 0, "made": {}, "used": {}, "text": f"{name} went {d['verb']} at {place} and found nobody to bury."}
        if "teach" in fx0 and not [x for x in self.living() if x["name"] != name and x["location"] == place]:
            return {"who": name, "duty": key, "place": place, "roll": 0, "skill": 0, "made": {}, "used": {}, "text": f"{name} went {d['verb']} at {place} and found nobody to teach."}
        skill = int(c.get("skills", {}).get(d["skill"], 0)); roll = rng.randint(1, 6); total = roll + skill
        factor = 0.0 if total <= 2 else 0.5 if total <= 5 else 1.0 if total <= 8 else 1.5
        out: dict = {"who": name, "duty": key, "place": place, "roll": roll, "skill": skill, "made": {}, "used": {}, "text": ""}
        if d.get("needs_tools") and L["tools"] <= 0: factor = min(factor, 0.5); out["no_tools"] = True
        if d.get("growing_only") and not growing(self.day, self.weather): factor = 0.0; out["season"] = True
        if c.get("needs", {}).get("rest", 5) <= 0: factor = min(factor, 0.5)
        # what it uses: all of it, or one of the "any" set, only if it is there
        use = dict(d.get("consumes", {})); any_of = d.get("consumes_any")
        if any_of:
            have = [s for s in any_of if L[s] >= use.get(s, 1)]
            for s in any_of: use.pop(s, None)
            if have: use[have[0]] = d["consumes"][have[0]]
            elif factor > 0: factor = 0.0; out["nothing_to_cook"] = True
        for s, v in use.items():
            if L[s] < v and factor > 0: factor = 0.0; out["short"] = s
        if factor > 0:
            for s, v in use.items(): L[s] -= v; out["used"][s] = v
            for s, v in d.get("produces", {}).items():
                n = int(round(v * factor))
                if n: L[s] += n; out["made"][s] = n
            fx = d.get("effect", {})
            if "roof" in fx: self.upkeep[place]["roof"] = min(10, self.upkeep[place]["roof"] + int(round(fx["roof"] * factor))); out["made"]["roof"] = place
            if "warmth" in fx: self.upkeep[place]["warmth"] = min(10, self.upkeep[place]["warmth"] + int(round(fx["warmth"] * factor))); out["made"]["warmth"] = place
            if "filth" in fx: self.upkeep[place]["filth"] = max(0, self.upkeep[place]["filth"] + int(round(fx["filth"] * factor))); out["made"]["filth"] = place
            if "kept" in fx: L["kept_day"] = self.day; out["made"]["kept"] = True
            if "road_safe" in fx: L["road_safe"] = True; out["made"]["road_safe"] = True
            if "bury" in fx and self.bodies:
                who = next((n for n, p in self.bodies.items() if p == place), next(iter(self.bodies))); self.bury(who); out["made"]["buried"] = who
            if "tend" in fx:
                sick = [x for x in self.living() if x.get("sick") and x["location"] == place] or [x for x in self.living() if x.get("sick")]
                for x in sick[:1 + int(factor)]: x["tended_day"] = self.day; note_log(x, self.day, f"{name} tended you."); out["made"].setdefault("tended", []).append(x["name"])
            if "teach" in fx:
                pupils = [x for x in self.living() if x["name"] != name and x["location"] == place]
                if pupils:
                    pupil = rng.choice(pupils); ks = pupil.get("duties") or [key]; sk = DUTIES[ks[0]]["skill"]
                    pupil["skills"][sk] = min(9, pupil["skills"].get(sk, 0) + 1); out["made"]["taught"] = f"{pupil['name']} in {sk}"; note_log(pupil, self.day, f"{name} taught you {sk}.")
        if d.get("needs_tools") and roll == 1 and L["tools"] > 0: L["tools"] -= 1; out["broke_tool"] = True
        if d.get("risk") == "hurt" and roll == 1: c["hp"] = max(0, c["hp"] - 2); out["hurt"] = True
        c["needs"]["rest"] = max(0, c["needs"].get("rest", 5) - 2); c["activity"] = d["verb"]
        if factor > 0 and rng.random() < .3 + .1 * (factor > 1): c["skills"][d["skill"]] = min(9, c["skills"].get(d["skill"], 0) + 1); out["learned"] = True
        said = {"roof": "the roof mended at {v}", "warmth": "the hearth warmed at {v}", "filth": "the filth cleared at {v}", "kept": "the stores kept from the rats",
                "road_safe": "the road watched and safe tonight", "buried": "{v} buried", "tended": "{v} tended", "taught": "{v}"}
        bits = []
        for k2, v in out["made"].items():
            if k2 in said: bits.append(said[k2].format(v=", ".join(v) if isinstance(v, list) else v))
            else: bits.append(f"{v} {k2}")
        made = ", ".join(bits)
        if factor == 0:
            why = "there was nothing to work with" if out.get("short") or out.get("nothing_to_cook") else "nothing grows this season" if out.get("season") else "it went badly"
            out["text"] = f"{name} tried {d['verb']} at {place} and got nothing: {why}."
        elif not made and "tend" in d.get("effect", {}): out["text"] = f"{name} went {d['verb']} at {place} and found nobody sick."
        elif not made and "bury" in d.get("effect", {}): out["text"] = f"{name} went {d['verb']} at {place} and found nobody to bury."
        elif not made and "teach" in d.get("effect", {}): out["text"] = f"{name} went {d['verb']} at {place} and found nobody to teach."
        else:
            out["text"] = f"{name} spent the morning {d['verb']} at {place}: {made or 'it held'}" + (", and broke a tool" if out.get("broke_tool") else "") + (", and got hurt" if out.get("hurt") else "") + "."
        note_log(c, self.day, out["text"].replace(name, "You", 1))
        return out

    def mark_undone(self, key: str) -> dict:
        """A duty nobody did today: its cost lands, and the count of days it has gone undone rises."""
        d = DUTIES[key]; st = self.duty_state(key); st["undone_days"] = st.get("undone_days", 0) + 1; L = self.ledger
        for s, v in d.get("undone", {}).items():
            if s == "road_safe": L["road_safe"] = False
            elif s in STORES: L[s] = max(0, L[s] + v)
        return {"duty": key, "days": st["undone_days"], "text": f"{d['label'].capitalize()} went undone: {d['breaks']}."}

    # ---- wants: what a person is after, measured, so the engine can say how close they are
    # A want is gold to hold, a skill to reach or to be best at, a tie to win, or an evening spent somewhere. Reached, it is
    # announced, standing rises, and a new one is rolled. Nobody chooses these; they come from the person's nature and life.
    def roll_want(self, name: str, rng: random.Random) -> dict:
        c = self.characters[name]; tr = c.get("traits", {}); others = [x["name"] for x in self.living() if x["name"] != name]
        kinds = ["gold"] * (2 + (2 if int(tr.get("greed", 3)) >= 4 else 0)) + ["skill"] * (2 + (2 if int(tr.get("ambition", 3)) >= 4 else 0)) \
            + ["tie"] * (2 + (2 if int(tr.get("desire", 3)) >= 4 or int(tr.get("warmth", 3)) >= 4 else 0)) + ["place"] * 2
        kind = rng.choice(kinds) if others else rng.choice(["gold", "skill", "place"])
        if kind == "gold":
            n = int(c.get("gold", 0)) + rng.randint(5, 12)
            return {"kind": "gold", "target": n, "text": f"to have {n} gold put by"}
        if kind == "skill":
            keys = list(c.get("duties") or list(DUTIES)); k = rng.choice(keys); sk = DUTIES[k]["skill"]; lvl = int(c.get("skills", {}).get(sk, 0))
            if rng.random() < .5: return {"kind": "best", "target": sk, "text": f"to be the best at {sk} in the valley, {DUTIES[k].get('title', 'the one everyone goes to')}"}
            t = min(9, lvl + rng.randint(2, 3)); return {"kind": "skill", "target": sk, "level": t, "text": f"to reach {sk} {t}"}
        if kind == "tie":
            who = rng.choice(others); r = rng.random()
            if r < .4: return {"kind": "feeling", "target": who, "level": 3, "text": f"to be liked by {who}, truly"}
            if r < .7: return {"kind": "trust", "target": who, "level": 3, "text": f"to have {who}'s trust"}
            return {"kind": "lover", "target": who, "text": f"to be {who}'s lover, or more"}
        place = rng.choice([p for p in self.map if p != c["location"]] or list(self.map))
        return {"kind": "place", "target": place, "text": f"to spend an evening at {place}"}

    def want_progress(self, name: str) -> tuple[int, str]:
        """(percent, a plain line about how close they are)."""
        c = self.characters[name]; g = c.get("goal") or {}; k = g.get("kind")
        if not g: return 0, "nothing measured yet"
        if k == "gold": have = int(c.get("gold", 0)); n = max(1, int(g["target"])); return min(100, 100 * have // n), f"{have} of {n} gold"
        if k == "skill": have = int(c.get("skills", {}).get(g["target"], 0)); n = max(1, int(g["level"])); return min(100, 100 * have // n), f"{g['target']} {have} of {n}"
        if k == "best":
            have = int(c.get("skills", {}).get(g["target"], 0)); top = max([int(x.get("skills", {}).get(g["target"], 0)) for x in self.living() if x["name"] != name] or [0])
            pct = 100 if have > top and have >= 2 else min(95, 100 * have // max(2, top + 1)); return pct, f"{g['target']} {have}; the best other is {top}"
        if k in ("feeling", "trust"):
            t = self.characters.get(g["target"])
            if not t or not t["alive"]: return 0, f"{g['target']} is gone"
            have = int(self.rel(g["target"], name)[k]); n = int(g["level"]); return max(0, min(100, 100 * (have + 5) // (n + 5))), f"{g['target']} {'feels' if k == 'feeling' else 'trusts'} {have:+d} toward you, {n:+d} wanted"
        if k == "lover":
            t = self.characters.get(g["target"])
            if not t or not t["alive"]: return 0, f"{g['target']} is gone"
            r = self.rel(g["target"], name); ok = r["type"] in ("lover", "spouse"); return 100 if ok else max(0, min(90, 100 * (r["feeling"] + 5) // 10)), ("they are yours" if ok else f"{g['target']} feels {r['feeling']:+d} toward you")
        if k == "place":
            d = self.distance(c["location"], g["target"]); return max(0, 100 - 25 * d) if d < 4 else 5, f"{d} path(s) from {g['target']}"
        return 0, "nothing measured yet"

    def want_reached(self, name: str) -> bool:
        c = self.characters[name]; g = c.get("goal") or {}; k = g.get("kind")
        if k == "place": return c["location"] == g["target"] and self.phase == "evening"
        return bool(g) and self.want_progress(name)[0] >= 100

    def want_text(self, name: str) -> str:
        c = self.characters[name]; pct, how = self.want_progress(name)
        return f"What you want more than anything: {c.get('want') or 'to see spring'}. In plain terms: {(c.get('goal') or {}).get('text', 'nothing measured')}. How close you are: {pct}% ({how})."

    def seed_wants(self, rng: random.Random) -> None:
        for c in self.living():
            if not c.get("goal"): c["goal"] = self.roll_want(c["name"], rng); c.setdefault("wants_reached", [])

    def check_wants(self, rng: random.Random) -> list[dict]:
        """Anyone whose want is reached: it is written down, standing rises, and a new want is rolled. Returns what to announce."""
        out = []
        for c in self.living():
            if not c.get("goal") or not self.want_reached(c["name"]): continue
            old = c["goal"]; bump_standing(c, 2); c.setdefault("wants_reached", []).append({"day": self.day, "text": old["text"]})
            c["goal"] = self.roll_want(c["name"], rng); c["want"] = c["goal"]["text"]
            note_log(c, self.day, f"You got what you wanted: {old['text']}. Now you want {c['goal']['text']}.")
            out.append({"who": c["name"], "text": f"{c['name']} got what they wanted: {old['text']}. Now they want {c['goal']['text']}."})
        if out: self.reached += out
        return out

    # ---- recognition: whoever is best at a duty's skill is called by it
    def titles(self) -> dict[str, list[str]]:
        """name -> the titles the valley gives them: the one person with the highest skill (at least 2, no tie) for each duty."""
        out: dict[str, list[str]] = {}
        for k, d in DUTIES.items():
            sk = d["skill"]; title = d.get("title")
            if not title: continue
            scores = sorted(((int(c.get("skills", {}).get(sk, 0)), c["name"]) for c in self.living()), reverse=True)
            if scores and scores[0][0] >= 2 and (len(scores) < 2 or scores[1][0] < scores[0][0]): out.setdefault(scores[0][1], []).append(title)
        return out

    def titled(self, name: str) -> str:
        t = self.titles().get(name, [])
        return f"{name} ({', '.join(t)})" if t else name

    # ---- the morning: WORK, REFUSE, or anything else, which is a skip
    def morning_intent(self, name: str, text: str) -> tuple[str, str | None]:
        """("work", duty or None) for WORK and WORK <duty>; ("refuse", duty or None) for REFUSE and REFUSE <duty>; ("skip", None) for anything else."""
        t = " ".join((text or "").strip().split())
        m = re.match(r"^(work|refuse)\b[:,]?\s*(.*)$", t, re.I)
        if not m: return ("skip", None)
        kind = m.group(1).lower(); rest = m.group(2)
        key = self.duty_key(rest) if rest else None
        return (kind, key)

    def fight_fire(self, place: str, people: list[str], rng: random.Random) -> dict:
        """The people pulled to a fire try to put it out. Speed helps; a bad roll burns."""
        total = 0; hurt = []
        for n in people:
            c = self.characters[n]; r = rng.randint(1, 6); total += r + int(c["spd"]) // 3
            if r == 1: c["hp"] = max(0, c["hp"] - 1); hurt.append(n)
        ok = total >= 7 and self.extinguish(place)
        txt = (f"{', '.join(people)} put out the fire at {place}." if ok else f"{', '.join(people)} fought the fire at {place} and could not put it out.") + (f" {', '.join(hurt)} got burned." if hurt else "")
        for n in people: note_log(self.characters[n], self.day, txt.replace(n, "You", 1) if txt.startswith(n) else txt)
        return {"kind": "fire", "place": place, "ok": ok, "text": txt}

    def handle_emergency(self, name: str, rng: random.Random) -> dict | None:
        """Whatever pulled this person this morning comes first. Fire is fought by everyone pulled to it at once."""
        c = self.characters[name]; e = c.get("emergency")
        if not e: return None
        c["emergency"] = None
        if e["kind"] == "fire":
            if e["place"] not in self.fires: return {"kind": "fire", "place": e["place"], "ok": True, "text": f"{name} went to the fire at {e['place']} and found it already out."}
            crew = [name] + [n for n in e.get("pulled", []) if n != name and self.characters.get(n, {}).get("emergency") is e and self.able(self.characters[n])]
            for n in crew: self.characters[n]["emergency"] = None
            for n in crew:
                if self.characters[n]["location"] != e["place"]: self.characters[n]["location"] = e["place"]
            return self.fight_fire(e["place"], crew, rng)
        if e["kind"] == "injury":
            t = self.characters.get(e.get("who") or "")
            if t and t["alive"]:
                c["location"] = e["place"]; t["tended_day"] = self.day; t["hp"] = min(t["hp_max"], t["hp"] + 1)
                if self.ledger["herbs"] > 0: self.ledger["herbs"] -= 1; t["hp"] = min(t["hp_max"], t["hp"] + 1)
                note_log(t, self.day, f"{name} came and saw to your wounds."); return {"kind": "injury", "place": e["place"], "ok": True, "text": f"{name} went to {e['place']} and saw to {t['name']}'s wounds."}
            return None
        if e["kind"] == "attack":
            c["location"] = e["place"]; r = rng.randint(1, 6) + int(c["str"]) // 3; ok = r >= 5
            if not ok: c["hp"] = max(0, c["hp"] - 2)
            return {"kind": "attack", "place": e["place"], "ok": ok, "text": f"{name} went to {e['place']} against {e['text']} and " + ("drove it off." if ok else "was beaten back and hurt.")}
        return None

    # ---- what each person is doing right now, for the map to walk them through
    # An activity is a state, a label, and the stops it takes them through, each with a place and how long the work there
    # shows for. The frontend plays it from `started`: walks the path to each stop, fills a bar for its seconds, and walks on.
    def set_activity(self, name: str, state: str, what: str, stops: list[dict] | None = None, immediate: bool = False) -> dict:
        c = self.characters[name]
        a = {"state": state, "what": what[:60], "from": c["location"], "stops": stops or [], "started": time.time(), "immediate": immediate, "day": self.day, "phase": self.phase}
        self.activities[name] = a; c["activity"] = what[:60]; return a

    def work_label(self, r: dict) -> str:
        """The words under the name while the work shows: "mending the roof at The mill", "tending Alder"."""
        d = DUTIES[r["duty"]]; made = r.get("made", {})
        if "tended" in made: return f"tending {', '.join(made['tended'])}"
        if "buried" in made: return f"burying {made['buried']}"
        if "taught" in made: return f"teaching {made['taught'].split(' in ')[0]}"
        if "roof" in made: return f"mending the roof at {r['place']}"
        if "warmth" in made: return f"feeding the hearth at {r['place']}"
        if "filth" in made: return f"clearing the filth at {r['place']}"
        return d["verb"]

    def resolve_morning(self, name: str, action: str | None, rng: random.Random) -> list[dict]:
        out = self._resolve_morning(name, action, rng); c = self.characters[name]
        stops = [{"place": r["place"], "what": self.work_label(r), "dur": 6} for r in out if r.get("kind") == "work" and r.get("place")]
        for r in out:
            if r.get("kind") in ("fire", "injury", "attack") and r.get("place"): stops.insert(0, {"place": r["place"], "what": r["kind"] if r["kind"] != "fire" else "fighting the fire", "dur": 5})
        if stops:
            self.set_activity(name, "working", stops[0]["what"], stops)
            if c["alive"] and not c["gone"]: c["location"] = stops[-1]["place"]
        elif out and out[0].get("kind") == "sick": self.set_activity(name, "resting", "resting", [{"place": c.get("home") if c.get("home") in self.map else c["location"], "what": "resting", "dur": 0}])
        elif any(r.get("kind") in ("skip", "refuse") for r in out): self.set_activity(name, "idle", "idle")
        return out

    def _resolve_morning(self, name: str, action: str | None, rng: random.Random) -> list[dict]:
        """One person's morning, settled: the emergency first if one pulled them, then WORK on their duties (or the one named),
        or REFUSE (the duties go unclaimed and standing drops), or a skip, which costs the same as a refusal for the day."""
        c = self.characters[name]; out: list[dict] = []
        if not self.able(c):
            out.append({"kind": "sick", "who": name, "text": f"{name} is sick and did no work."}); return out
        kind, key = self.morning_intent(name, action or "")
        em = self.handle_emergency(name, rng)
        if em: out.append(dict(em, who=name)); c["needs"]["rest"] = max(0, c["needs"].get("rest", 5) - 1)
        mine = list(c.get("duties", [])) + [k for k in c.get("dumped", []) if k not in c.get("duties", [])]
        if not mine:
            if kind == "work": out.append({"kind": "idle", "who": name, "text": f"{name} had no work to do."})
            return out
        if kind == "work":
            todo = [key] if key and key in mine else mine
            for k in todo:
                r = self.do_duty(name, k, rng); r["kind"] = "work"; out.append(r)
            skipped = [k for k in mine if k not in todo]
        else:
            skipped = [key] if (kind == "refuse" and key and key in mine) else mine
        if skipped:
            for k in skipped:
                if k in c.get("duties", []): c["duties"].remove(k)
                if k in c.get("dumped", []): c["dumped"].remove(k)
                st = self.duty_state(k)
                if not self.holders(k): st["unclaimed_day"] = self.day
            bump_standing(c, -1)
            verb = "refused" if kind == "refuse" else "skipped"
            labels = ", ".join(DUTIES[k]["label"] for k in skipped)
            note_log(c, self.day, f"You {verb} {labels}. It is no longer yours, and people noticed.")
            out.append({"kind": kind if kind == "refuse" else "skip", "who": name, "duties": skipped, "text": f"{name} {verb} {labels}; {'it is' if len(skipped) == 1 else 'they are'} nobody's now."})
        return out

    def end_morning(self, done: set[str], rng: random.Random) -> dict:
        """After every morning: the duties nobody did land their cost, and after two days a neighbour complains by name."""
        undone: list[dict] = []; complaints: list[str] = []
        for k in DUTIES:
            if k in done: continue
            u = self.mark_undone(k); undone.append(u)
            if u["days"] >= 2:
                place = self.duty_place(k); hs = self.holders(k)
                pool = [c for c in self.living() if c["name"] not in hs and c["location"] == place] or [c for c in self.living() if c["name"] not in hs]
                if pool:
                    who = rng.choice(pool); blame = ", ".join(hs) if hs else "nobody"
                    line = f"{who['name']} complains that {DUTIES[k]['label']} has gone undone {u['days']} days running, and that {blame} {'holds' if hs else 'has taken'} it."
                    complaints.append(line); note_log(who, self.day, line.replace(who["name"], "You", 1).replace("complains", "complained", 1))
                    for h in hs: note_log(self.characters[h], self.day, f"{who['name']} complained, by name, that you have left {DUTIES[k]['label']} undone {u['days']} days running."); self.set_rel(who["name"], h, feeling=-1, delta=True, why=f"left {DUTIES[k]['label']} undone")
        self.morning = {"day": self.day, "undone": undone, "complaints": complaints}
        return self.morning

    def undone_text(self) -> str:
        m = self.morning if (self.morning or {}).get("day") == self.day else {}
        if not m or not m.get("undone"): return "- every duty was done today"
        return "\n".join(f"- {u['text']}" + (f" ({u['days']} days running)" if u["days"] > 1 else "") for u in m["undone"]) + ("\n" + "\n".join(f"- {c}" for c in m.get("complaints", [])) if m.get("complaints") else "")

    def evening_places(self, rng: random.Random) -> dict[str, str]:
        """At dusk everyone goes home, unless the inn pulls them: drinkers and talkers go there, and anyone whose home is gone."""
        inn = next((p for p, d in self.map.items() if d.get("kind") == "inn"), None); moves = {}
        for c in self.living():
            tr = c.get("traits", {}); home = c.get("home") if c.get("home") in self.map else c["location"]
            pull = (int(tr.get("drink", 3)) >= 4) or (int(tr.get("tongue", 3)) >= 4 and rng.random() < .5) or (int(tr.get("desire", 3)) >= 4 and rng.random() < .4)
            dest = inn if (inn and pull and not c.get("sick")) else home
            if dest and dest != c["location"]: c["location"] = dest; moves[c["name"]] = dest
            self.set_activity(c["name"], "evening", "at the inn" if dest == inn and inn != home else "at home", [{"place": dest or c["location"], "what": "at the inn" if dest == inn and inn != home else "at home", "dur": 0}])
        return moves

    def duties_text(self) -> str:
        """The roster for the World: who holds what, what is unclaimed, and what has gone undone and for how long."""
        out = []
        for k, d in DUTIES.items():
            hs = self.holders(k); st = self.duty_state(k); r = (self.roster or {}).get("duties", {}).get(k, {})
            who = ", ".join(hs) if hs else ("dumped on " + r["dumped_on"] + " today" if r.get("dumped_on") else "UNCLAIMED, nobody did it")
            out.append(f"- {d['label']}: {who}" + (f"; undone {st['undone_days']} day(s) running" if st.get("undone_days") else ""))
        return "\n".join(out)

    def resists(self, target: str, actor: str, text: str) -> bool:
        """The target's own action today pushed back: it names the actor and says stay, fight, refuse, or the like."""
        t = (text or "").lower()
        if not re.search(r"(?<![\w@])@?" + re.escape(actor.lower()) + r"\b", t): return False
        return bool(re.search(r"\b(stay|staying|stand|standing|resist|refuse|fight|won't go|will not go|not leaving|not going|hold|keep my|defend|my ground|dare)\b", t))

    def resolve_social_actions(self, actions: list[dict], rng: random.Random, log: list[str]) -> list[dict]:
        """Pull the social acts out of today's actions, settle them, and return their outcomes. The rest are left for the World to narrate."""
        out = []
        for a in list(actions):
            intent = self.social_intent(a["who"], a["text"])
            if not intent: continue
            kind, target = intent
            if a["who"] not in self.characters or not self.characters[a["who"]]["alive"] or self.characters[a["who"]]["gone"]: continue
            resisting = bool(target) and any(x["who"] == target and self.resists(target, a["who"], x["text"]) for x in actions)
            r = self.resolve_social(a["who"], kind, target, rng, resisting)
            if r["text"]: out.append(r); log.append(f"{kind}: {r['text'][:80]}"); actions.remove(a)
        return out

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
                f"{self.needs_text(name)}\n"
                f"Your secret, known only to you: {c['secret']}\nYour fear: {c['fear']}\n{self.want_text(name)}\n"
                + (f"People call you {', '.join(self.titles().get(name, []))}.\n" if self.titles().get(name) else "")
                + f"YOUR PEOPLE, and how you truly feel about them (act on this):\n{self.relations_text(name)}")

    def apply(self, res: dict, log: list[str]) -> None:
        """Validate and apply a World result block. Anything impossible is clamped and logged.
        Nobody is sent away by this block: driving out and leaving are actions the engine settles itself."""
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
            if "standing" in r:
                try: bump_standing(c, max(-2, min(2, int(r["standing"]))))
                except (TypeError, ValueError): log.append(f"standing for {c['name']} must be a number, -2 to 2")
        for d in res.get("dead", []) or []:
            c = self.characters.get(str(d.get("who", "")))
            if c and c["alive"]: self.kill(c, str(d.get("cause", "unknown"))[:120])
        for c in self.characters.values():
            if c["alive"] and c["hp"] <= 0: self.kill(c, c["cause_of_death"] or "wounds")
        if res.get("sent_away") or res.get("gone"): log.append("the block named people to send away and was ignored: nobody is sent away but by another person's own act")
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
        for k in STORES:
            if k in L:
                try: g[k] = max(0, g[k] + max(-3, min(3, int(L[k]))))
                except (TypeError, ValueError): log.append(f"bad number in ledger for {k}")
        if "road_safe" in L: g["road_safe"] = bool(L["road_safe"])
        for b in L.get("built", []) or []:
            if str(b).strip() and str(b).strip() not in g["built"]: g["built"].append(str(b).strip()[:60])

    def end_day(self) -> None:
        """Evening is over. Whatever was dumped or pulled today is cleared, and tomorrow begins at dawn."""
        for c in self.characters.values():
            c["dumped"] = []; c["emergency"] = None; c["activity"] = ""
            if c["alive"] and not c["gone"]:
                home = c.get("home") if c.get("home") in self.map else c["location"]
                self.set_activity(c["name"], "resting", "resting", [{"place": home, "what": "resting", "dur": 0}]); c["location"] = home
        self.day += 1; self.phase = "morning"



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


DASH_RE = re.compile("[ \\t]*[\u2014\u2013\u2015]+[ \\t]*")      # em dash, en dash, horizontal bar, by code point so none is written here
SENTENCE_RE = re.compile(r"(?<=[.!?][\"')\]])\s+(?=\S)|(?<=[.!?])\s+(?=\S)")


def strip_dashes(text: str) -> str:
    """No em or en dash survives a model's reply. Between words it becomes a comma; before a capital or at the end
    of a line it becomes a full stop; at the start of a line it is dropped. Runs on every line the models send."""
    out = []
    for ln in (text or "").split("\n"):
        pos = 0; s = ""
        for m in DASH_RE.finditer(ln):
            before = ln[:m.start()]; after = ln[m.end():]
            s += ln[pos:m.start()]
            if not before.strip(): pass                                   # a dash opening the line: just drop it
            elif not after.strip(): s = s.rstrip(" ,;:") + "."           # a dash ending the line
            elif after[:1].isupper() and not re.match(r"I\b", after): s = s.rstrip(" ,;:") + ". "
            elif before.rstrip()[-1:] in ".!?,;:": s = s.rstrip() + " "  # already punctuated
            else: s = s.rstrip() + ", "
            pos = m.end()
        s += ln[pos:]
        out.append(s)
    return "\n".join(out)


def sentences(text: str) -> list[str]:
    return [x for x in SENTENCE_RE.split(text.strip()) if x.strip()] if text and text.strip() else []


def cap_speech(text: str, limit: int = 3) -> str:
    """A person's reply is at most `limit` sentences before the ACTION line. WHISPER lines keep their own line;
    everything after the cap is dropped, and the ACTION line is kept whole."""
    lines = (text or "").split("\n"); body: list[str] = []; action: list[str] = []
    for ln in lines:
        if re.match(r"^\s*ACTION:", ln, re.I) or action: action.append(ln)
        else: body.append(ln)
    left = limit; kept: list[str] = []
    for ln in body:
        if left <= 0: break
        if not ln.strip(): kept.append(ln); continue
        m = WHISPER_RE.match(ln); head = ""
        if m: head = ln[:ln.lower().index(":") + 1] + " "; ln = m.group(2)
        ss = sentences(ln)
        if len(ss) > left: ss = ss[:left]
        left -= len(ss); kept.append(head + " ".join(ss))
    while kept and not kept[-1].strip(): kept.pop()
    return "\n".join(kept + action).strip()


def cap_outcomes(text: str, limit: int = 2) -> str:
    """The World's narration is at most `limit` sentences per outcome, one outcome per line or paragraph."""
    out = []
    for ln in (text or "").split("\n"):
        if not ln.strip(): out.append(ln); continue
        m = re.match(r"^(\s*(?:[-*]\s*)?(?:[A-Z][\w' -]{0,40}:\s*|EVENT:\s*|SETTLED:\s*)?)(.*)$", ln)
        head, rest = (m.group(1), m.group(2)) if m else ("", ln)
        ss = sentences(rest)
        out.append(head + " ".join(ss[:limit]) if len(ss) > limit else ln)
    return "\n".join(out)


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


def _name_rx(name: str) -> re.Pattern:
    return re.compile(r"(?<![\w@])@?" + re.escape(name) + r"(?:'s)?\b", re.I)


def touched_text(entry: dict, me: str, my_place: str, ties: list[str]) -> str | None:
    """What of a chronicle entry reached this person: only the lines that happened where they are, name them, or were done by
    someone they have a tie with. Speech and the convener's words go through the usual sight rules. Engine notes never reach a person."""
    kind = entry.get("kind")
    if kind == "system": return None
    if kind in ("speech", "convener"):
        return visible_text(entry, me, my_place)
    text = entry.get("text", "")
    cut = re.search(r"\n(?:PROSPERITY|STANDINGS|WHO IS WHERE)\b", text)
    if cut: text = text[:cut.start()]
    rxs = [_name_rx(me), _name_rx(my_place)] + [_name_rx(t) for t in ties]
    keep = []
    for ln in text.split("\n"):
        if not ln.strip(): continue
        for s in sentences(ln) if len(sentences(ln)) > 1 else [ln]:
            if any(rx.search(s) for rx in rxs): keep.append(s.strip())
    return "\n".join(keep) or None

