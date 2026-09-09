"""Faces. Every person carries a face seed, and this reads a portrait out of it and out of who they are today.

Nothing here draws: it settles the features and hands them over as a small dict, and frontend/face.js draws
that dict at whatever size the page needs. The split is on purpose. The features are the part that has to be
the same every time, so they are settled here, in one place, where a test can hold them still; the drawing is
the part that has to be the same shape at 20 pixels and at 160, so it lives in the browser.

What comes from the seed: the shape of the face, the skin, the hair and its colour, the eyes, the nose, the
mouth, the beard. What comes from the person: their age (lines, and grey), their health (pallor), their food
(a thin face), their strength (a scar), their trade (a hat or a hood), and their seat colour (their clothes).
So the same person always has the same face, and the face changes when they do.
"""
from __future__ import annotations
import json, random
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
_PEOPLE = json.loads((DATA / "people.json").read_text(encoding="utf-8"))
TRADE_HATS: dict[str, str] = {t["name"]: t.get("hat", "none") for t in _PEOPLE["trades"]}

SHAPES = ["oval", "round", "square", "long", "heart"]
HAIRS = ["short", "cropped", "long", "braid", "bob", "topknot", "wild", "bald"]
EYES = ["wide", "narrow", "round", "deep", "hooded"]
BEARDS = ["none", "none", "none", "stubble", "full", "goatee", "mutton"]
HATS = ["none", "cap", "hood", "coif", "wimple", "straw", "helm", "veil", "hat"]
SKINS = ["#f2d3bb", "#e8c39e", "#dcae86", "#c68f68", "#a9714d", "#8a5a3c", "#6f462e", "#5a381f"]
HAIR_COLORS = ["#20160f", "#3a2418", "#5a3a20", "#7a512a", "#a06a2c", "#c49a4a", "#8a8073", "#d8cdbc"]
EYE_COLORS = ["#3c2a1a", "#5a3f22", "#4a5a3a", "#3a5060", "#6a6a5a"]
CLOTH = "#7f6a4a"                 # what they wear when they have no seat colour of their own


def _grey(hexcol: str, f: float) -> str:
    """Toward the grey of an old head, by f from 0 to 1."""
    f = max(0.0, min(1.0, f)); r, g, b = (int(hexcol[i:i + 2], 16) for i in (1, 3, 5))
    t = 190
    return "#" + "".join(f"{int(v + (t - v) * f):02x}" for v in (r, g, b))


def hat_for(trade: str) -> str:
    """The hat or hood a trade wears. An unknown trade goes bare headed, which is most of the valley."""
    t = " ".join(str(trade or "").lower().split())
    if not t: return "none"
    if t in TRADE_HATS: return TRADE_HATS[t]
    for name, hat in TRADE_HATS.items():                       # "the miller", "old miller", "miller of Ashford"
        if name in t: return hat
    return "none"


def age_band(age: int) -> int:
    """How many lines a face carries: none young, one at thirty, two at forty five, three past sixty."""
    return 0 if age < 30 else 1 if age < 45 else 2 if age < 60 else 3


def face_of(c: dict, color: str = "") -> dict:
    """The portrait of this person as they are today. Same seed and same state, same dict, always."""
    seed = c.get("face_seed")
    if not isinstance(seed, int): seed = abs(hash(str(c.get("name", "")))) % (10 ** 9)
    rng = random.Random(seed)
    age = int(c.get("age") or 30)
    hp_max = max(1, int(c.get("hp_max") or 1)); hp = max(0, int(c.get("hp") or 0))
    alive = bool(c.get("alive", True))
    food = int((c.get("needs") or {}).get("food", 8))
    shape = SHAPES[rng.randrange(len(SHAPES))]
    skin = SKINS[rng.randrange(len(SKINS))]
    hair = HAIRS[rng.randrange(len(HAIRS))]
    base_hair = HAIR_COLORS[rng.randrange(len(HAIR_COLORS))]
    eyes = EYES[rng.randrange(len(EYES))]
    eyec = EYE_COLORS[rng.randrange(len(EYE_COLORS))]
    nose = rng.randrange(4); mouth = rng.randrange(4); brow = rng.randrange(3); ears = rng.randrange(2)
    beard = BEARDS[rng.randrange(len(BEARDS))]
    if age < 20 and beard == "full": beard = "stubble"
    grey = 0.0 if age < 35 else min(0.85, (age - 35) / 40.0)
    if age >= 55 and hair in ("wild", "topknot") and rng.random() < .5: hair = "cropped"
    frac = hp / hp_max if alive else 0.0
    return {"shape": shape, "skin": skin, "hair": hair, "haircol": _grey(base_hair, grey), "eyes": eyes, "eyecol": eyec,
            "nose": nose, "mouth": mouth, "brow": brow, "ears": ears, "beard": beard, "hat": hat_for(c.get("trade", "")),
            "cloth": color or CLOTH, "lines": age_band(age), "scar": 1 if int(c.get("str") or 0) >= 8 else 0,
            "thin": 1 if food <= 3 else 0, "pale": 0 if frac >= 0.67 else 1 if frac >= 0.34 else 2,
            "dead": not alive, "gone": bool(c.get("gone")), "sick": bool(c.get("sick"))}


def faces_of(characters, colors: dict[str, str] | None = None) -> dict[str, dict]:
    """Every living and dead person's face, keyed by name, for one state reply."""
    colors = colors or {}
    return {c["name"]: face_of(c, colors.get(c["name"], "")) for c in characters}
