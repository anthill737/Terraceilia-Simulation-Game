"""A stand-in for a provider CLI, used by the tests. It is launched exactly like a real CLI: it gets the
"Read the file ... and respond" instruction as its argument, reads that prompt file, and prints an answer
of the kind a well behaved agent would give. TERRA_STUB_MAP chooses how it answers a map request:
  good (default)  a valid map
  garbage         no json at all, every time
  placeholder     a map with a placeholder place name first, then a valid map once it is asked again"""
from __future__ import annotations
import json, os, re, sys

FIXED_MAP = {
    "name": "Harrowmere",
    "palette": {"ground": "#3b4436", "accent": "#7d8f5a"},
    "water": {"type": "lake", "color": "#2f6f8f"},
    "sky": "storm",
    "places": [
        {"name": "Harrow Keep", "kind": "castle", "feature": "crag", "elevation": 2, "desc": "A squat keep on a crag above the mere, its gate iron banded and its hall always cold.",
         "fixtures": ["the gate", "the great hall", "the armory", "the cistern"], "adj": ["Keep Road", "Saltmarket"], "x": 500, "y": 110},
        {"name": "Saltmarket", "kind": "market", "feature": "plain", "elevation": 0, "desc": "A muddy square where salt, fish, and rumor change hands under striped awnings.",
         "fixtures": ["the salt stalls", "the weigh house", "the pillory", "the well"], "adj": ["Harrow Keep", "The Drowned Rat", "Fenchapel", "Keep Road", "Eelbrook"], "x": 500, "y": 330},
        {"name": "The Drowned Rat", "kind": "inn", "feature": "coast", "elevation": 0, "desc": "A leaning inn on stilts over the water, loud until dawn.",
         "fixtures": ["the taproom", "the hearth", "the back rooms", "the cellar hatch"], "adj": ["Saltmarket", "Reedmoor", "Blackwater Cave"], "x": 740, "y": 300},
        {"name": "Fenchapel", "kind": "chapel", "feature": "marsh", "elevation": 0, "desc": "A grey chapel sinking slowly into the fen, its bell tower already leaning.",
         "fixtures": ["the bell", "the altar", "the bone crypt", "the leaning tower"], "adj": ["Saltmarket", "Eelbrook"], "x": 300, "y": 220},
        {"name": "Eelbrook", "kind": "village", "feature": "marsh", "elevation": 0, "desc": "Eel traps, smokehouses, and huts on the bank of a slow brown brook.",
         "fixtures": ["the eel traps", "the smokehouse", "the plank bridge", "the moorings"], "adj": ["Saltmarket", "Fenchapel", "The Mere", "Gallows Mill"], "x": 260, "y": 470},
        {"name": "Gallows Mill", "kind": "mill", "feature": "coast", "elevation": 0, "desc": "A tide mill beside a gibbet nobody has used in a generation.",
         "fixtures": ["the millwheel", "the sluice", "the grain loft", "the gibbet"], "adj": ["Eelbrook", "Reedmoor"], "x": 480, "y": 560},
        {"name": "Reedmoor", "kind": "fields", "feature": "marsh", "elevation": 0, "desc": "Cut reeds stacked in ricks across sodden pasture; the walking is treacherous.",
         "fixtures": ["the reed ricks", "the drainage ditch", "the shepherd's hut"], "adj": ["The Drowned Rat", "Gallows Mill", "The Mere"], "x": 720, "y": 520},
        {"name": "The Mere", "kind": "water", "feature": "island", "elevation": 0, "desc": "A wide black lake with a single island where something was once buried.",
         "fixtures": ["the jetty", "the island cairn", "the fishing boats"], "adj": ["Eelbrook", "Reedmoor"], "x": 500, "y": 700},
        {"name": "Keep Road", "kind": "road", "feature": "cliff", "elevation": 1, "desc": "The causeway between keep and market, open on both sides to the fen and whatever lives in it.",
         "fixtures": ["the causeway stones", "the toll post", "the drowned milestone"], "adj": ["Harrow Keep", "Saltmarket"], "x": 250, "y": 100},
        {"name": "Blackwater Cave", "kind": "cave", "feature": "cliff", "elevation": 1, "desc": "A wet mouth in the crag where smugglers land and worse things are said to sleep.",
         "fixtures": ["the landing rock", "the rope ladder", "the smugglers' chest"], "adj": ["The Drowned Rat"], "x": 880, "y": 120},
    ],
    "names": ["Aldous", "Bett", "Cuthbert", "Dimity", "Ebbe", "Faye", "Garrick", "Hesper", "Ianthe", "Jory", "Kestrel", "Lowell", "Maudie",
              "Nykke", "Osgar", "Perrin", "Quenby", "Rooke", "Sabra", "Tobin", "Una", "Vane", "Wystan", "Yolande", "Zeph", "Ansel", "Brannoc", "Cerys"],
}


def placeholder_map() -> dict:
    """The failure this is here to catch: a real looking map with one place the model never named."""
    m = json.loads(json.dumps(FIXED_MAP))
    m["places"][4]["name"] = "placeholder"
    for p in m["places"]:
        p["adj"] = ["placeholder" if a == "Eelbrook" else a for a in p["adj"]]
    return m


def fenced(obj: dict) -> str:
    return "```json\n" + json.dumps(obj) + "\n```"


def answer(text: str) -> str:
    if '"places":[{"name"' in text:                       # a map request
        mode = os.environ.get("TERRA_STUB_MAP", "good")
        if mode == "garbage":
            return "The fen is wide and I am tired. There is no map today, and no json either."
        if mode == "placeholder" and "could not be used" not in text:
            return "Here is the map of the fen.\n" + fenced(placeholder_map())
        return "Here is the map of the fen.\n" + fenced(FIXED_MAP)
    if '"people":[{"name"' in text:                       # world creation: give every rolled name a life
        names = re.findall(r"^- (.+?): STR \d+", text, re.M)
        places = re.findall(r"^- (.+?): .*? Paths lead to: ", text, re.M) or ["Saltmarket"]
        people = [{"name": n, "trade": "eel catcher", "home": places[i % len(places)], "personality": "keeps to the water",
                   "secret": "owes the miller", "fear": "the mere at night", "want": "a dry roof"} for i, n in enumerate(names)]
        rels = [{"a": names[0], "b": names[1], "type": "rival", "feeling": -2, "trust": -1, "mutual": True, "why": "the same eel run"}] if len(names) > 1 else []
        return "The fen wakes under a low sky.\n" + fenced({"people": people, "relations": rels})
    if "actions to resolve" in text:                      # a day's resolution: the first person walks one path
        adj = {m.group(1): [a.strip() for a in m.group(2).split(",")] for m in re.finditer(r"^- (.+?): .*? Paths lead to: (.+?)\.$", text, re.M)}
        ppl = re.findall(r"^- (.+?) \(.*?, at (.+?)\): STR", text, re.M)
        results = []
        if ppl and adj.get(ppl[0][1]): results.append({"who": ppl[0][0], "location": adj[ppl[0][1]][0], "note": "walked"})
        return "The day passes in mud and argument.\n" + fenced({"results": results, "events": [], "ledger": {"grain": 0}})
    if "The year is over" in text:
        return "The chronicle ends here, in the fen."
    if "It is morning" in text: return "ACTION: WORK"
    if "It is evening" in text: return "Cold night." if "Say something" in text else "PASS"
    return "I keep my own counsel and watch the water.\nACTION: I mend my nets and listen."


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    m = re.search(r"Read the file (.+?) and respond", " ".join(sys.argv[1:]))
    if not m: print("stub: no prompt file named"); return 1
    print(answer(open(m.group(1), encoding="utf-8").read()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
