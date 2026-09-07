# Terraceilia Simulation Game

A living medieval valley played by AI agents, each in its own CLI process.

Twenty-odd villagers, a market town, a castle on the hill, a forest road that is dangerous after dark,
and a winter coming that the last one proved can kill. Each person is played by a coding-agent CLI
(Claude Code, Codex, OpenCode, or Gemini CLI) in its own process, with its own memory and its own
secret. One more agent plays the World: referee, weather, fates, and chronicler. You are the
convener. You watch, you speak as fate, and you can reach into the map and move things with your hand.

The engine owns the world. Stats are rolled by code, dice are rolled by code, every number the World
proposes is validated and clamped, the dead stay dead, and the map is fixed and known to everyone.
The agents can talk, scheme, lie, and act; they cannot change a number by saying so.

## Requirements

- Python 3.11 or newer. No packages to install; the standard library is enough.
- At least one agent CLI installed and signed in:
  - `claude` ([Claude Code](https://www.npmjs.com/package/@anthropic-ai/claude-code))
  - `codex` ([Codex](https://www.npmjs.com/package/@openai/codex)), or `npx` to run the latest Codex without installing it
  - `opencode` ([OpenCode](https://www.npmjs.com/package/opencode-ai))
  - `gemini` ([Gemini CLI](https://www.npmjs.com/package/@google/gemini-cli))
  - `copilot` ([GitHub Copilot CLI](https://www.npmjs.com/package/@github/copilot))

You do not have to set any of that up by hand. Open the gear, then Connections: each tool has a row
showing whether it is installed and signed in, an Install button that runs the official installer, and
a Sign in button that opens a terminal window with the tool's own login command already running. The
row turns green by itself once the tool says it is signed in. A tool you already have is never touched.

Every agent is launched in the provider's read-only mode. They can read the prompt file the engine
writes for them and nothing else; they are told not to touch files and the sandbox enforces it.

## Run

    python backend/main.py            # opens http://127.0.0.1:8766/?token=...

Or `run.bat` on Windows and `./run.sh` elsewhere. Flags:

    --port N          listen on another port (default 8766)
    --local-only      bind to 127.0.0.1 only; no phone link

The first run writes a random access token to `token.txt` and prints three links: desktop, phone on
the same wifi, and phone anywhere if [Tailscale](https://tailscale.com) is installed. Every request
needs the token, so keep the links to yourself.

## Starting a game

Press **New game**, then choose:

- how many people live in the valley (2 to 30),
- how many days the year runs, or a time limit in minutes,
- the **drama** dial from 0 to 10: how much the world throws at the people each day,
- which provider and model plays the World, and which play the people (odd seats and even seats
  can use different models, so two providers can share a valley),
- **the map**: the built-in valley of Terraceilia, or one generated from your description,
- an empty folder for the CLIs to run in.

### A map drawn from your description

Choose "Generate from the description" and a model reads what you wrote and draws the world it
describes: its ground colour and accent, the water it has (river, lake, sea, lava, or none) and that
water's colour, the light it sits under (day, dusk, night, ash, storm), and for every place what it is,
what land it stands on (mountain, peak, cliff, island, crater, crag, forest, marsh, plain, coast) and
how high it stands. A lava valley comes out black and orange with molten pools that light the places
beside them, a town on a peak sits on a drawn ridge, and a castle on an island sits on an island.

The engine trusts none of it. Placeholder and bare category names are refused and the model is asked
again. Unknown kinds, features, water types and skies fall back to safe values. The graph is made
symmetric and connected, places are pushed at least 110 units apart and clamped into the canvas, and
every place gets at least one thing in it. Two bad answers and the built-in valley is used instead,
with a note in the chronicle saying so. It happens once, at Start; World can draw it earlier or again,
and once people exist the map is fixed for that game.

Press **Start the year**. The engine rolls every person's numbers, then asks the World to give each
one a life: a trade, a home, a personality, a secret, a fear, a want, and a web of ties to the
others. Marriages, debts, rivalries, an unrequited love, a servant who hates a master who trusts him.
That takes a minute or two. Then day one begins.

## How a day goes

1. **The people speak.** Every living person who is not banished gets one prompt containing their
   sheet, where they are and who is with them, the valley's unresolved situations, and everything
   they saw and heard since their last turn. Extreme traits push daily urges on them: a drunkard has
   been drinking since noon, a wanton one wants somebody, a schemer has decided somebody is in the
   way. They answer in character, a few sentences, and end with exactly one `ACTION:` line.
2. **Reactions.** Anyone addressed with `@Name`, or whispered to with `WHISPER @Name:`, gets a turn
   to answer. Whispers are heard only by the target and the World, and only if the target is standing
   in the same place.
3. **The World resolves the day.** The engine rolls a die for every action, draws the day's events
   from the drama dial, spreads any fires, and hands it all to the World. The World narrates what
   happened, place by place, and proposes results in a JSON block: wounds, gold, moves, deaths,
   banishments, the prosperity ledger, new situations, changed feelings. The engine validates every
   line and clamps anything impossible.
4. **The chronicle.** What the whole valley learned goes into the chronicle. What each person
   witnessed goes into their own memory file.

Every sixth day the lord's court sits and the World must name the one person the valley trusts
least. They are banished. The year ends when the days run out, the clock runs out, or one person
is left standing. Then the World writes the epilogue.

### The people

Each person is rolled with Strength and Speed (2 to 9), hit points (8 to 14), and a purse of gold
(1 to 9). Twelve traits, each scored 1 to 5, shape how they are told to behave: warmth, temper,
honesty, greed, courage, tongue, desire, piety, ambition, loyalty, cunning, and drink. The rolls
are skewed away from nice. Most people are middling, a good share are hard, a few are saints.

Everyone has an opinion about everyone else, as a feeling and a trust score from -5 to 5, seeded
from their natures and then shaped by the ties the World invents and everything that happens after.

### The World's rules of judgement

The World is told how to judge and may not soften it. A fight wounds. A person with Strength 7 or
more who attacks on a roll of 5 or 6 can kill, and a knife in the dark kills on a 4. Drunk actions
go wrong on a 1 to 3 and are witnessed. A theft that fails is seen. A murder that succeeds still
leaves a body, and bodies are found. Lies succeed on a 4 or better against the simple and fail
against the cunning. Every day, without exception, something happens that no character chose.

### Drama and events

`data/events.json` holds the things the valley can suffer: bandit raids, fires, plague, tax
collectors, witchcraft accusations, a body in the river. At drama 0 nothing happens that the people
did not cause. At 5 there is about one event a day, mostly small. At 10 there are two or three,
including raids, fires, and deaths. Events apply their wounds and losses in code before the World
ever sees them, and many open a **situation** that stays in front of everyone until it is resolved.
Fires burn for days, wreck what is at a place, hurt the people there, and spread to neighbours.

### The ledger

The valley has to store enough grain for the winter, mend three broken roofs, make the forest road
safe, tend its sick, and build something that was not there before. The World moves these numbers
through its JSON block and the chronicle shows them every day.

## The convener's hand

You are not a player, but you are not powerless.

- **Speak as fate.** The composer under the chronicle sends a message to everyone, or to one person
  alone with `@Name`.
- **Move people.** Drag a person on the map to another place.
- **Wreck and restore.** Click a place to see what is there. Destroy a fixture, restore one, or set
  the place on fire and put it out again.
- **Strike someone down.** Smite a person and they are dead.
- **Edit anyone.** In Settings, change a person's model, stats, life, or name while the game runs.
  Bring the dead back or let a banished person walk home. Change how any two people feel about each
  other.
- **Change the game.** Title, world text, days, time limit, drama, and the World's model can all be
  changed mid-game, under World.
- **Resolve a situation.** Situations lists everything the valley has not finished with, what is
  burning, and who or what is standing in each place, with a Resolve button for each one.

Gameplay sits in plain buttons across the header: the primary control, then People, World, Situations
and Fate. Everything else is behind the gear: Connections, the three exports, Display, Stop this year,
and Quit. On a phone the tabs are Map, Chronicle, Valley, People, and More.

## Telegram

Terraceilia can message you when a year ends, through a Telegram bot that belongs to you. Open the
gear, then Connections, and press Connect Telegram: a three step tutorial walks you through making the
bot with BotFather, telling it who you are, and sending yourself a test. The token is kept in
`telegram.json` beside the game, is never sent to the browser, and is git ignored. The tutorial opens
again any time the link has been removed.

Every act is recorded as fate, and the World must narrate it on the next day.

## Layout

    backend/
      main.py      start the server, print the links, open the browser
      server.py    HTTP API, static frontend, the convener's god powers
      game.py      one game: saved state, the day loop, prompts to the World and the people
      engine.py    the world: map, people, traits, urges, events, fires, relations, dice, validation
      agents.py    provider CLIs: launching, streaming, session resume, Codex trust
      prompts.py   the rules the World and the people are told
    frontend/
      index.html   the app shell
      app.js       state polling, setup, chronicle, valley, terminals
      map.js       the overworld map: drag people, destroy or restore things
      style.css
    data/
      map.json     the fixed map: places, descriptions, fixtures, paths, coordinates
      events.json  what the world can throw at the people, by tier
      names.json   the pool of names people are rolled from
    games/         one folder per game (not committed)
      <id>/game.json         everything about the game and the world
      <id>/chronicle.md      the chronicle as markdown
      <id>/seatN/memory.md   what that person has witnessed, theirs alone
      <id>/seatN/prompt_*.md every prompt that person was sent

`games/` and `token.txt` are ignored by git. A finished year can be exported from the UI as
markdown: the chronicle alone, with settings and every person's sheet, or everything including
the map and the terminals.

## API

Every request carries the token as `?token=` or a cookie.

    GET  /state?since=N         everything the UI shows, transcript from entry N
    GET  /events                server-sent events: the map state whenever it changes
    GET  /export?what=chronicle|settings|everything
    GET  /ls?path=              folder listing for the run-folder picker

    POST /config                game settings, editable at any time
    POST /start, /pause, /stop
    POST /say {text}            speak as fate; @Name to speak to one person
    POST /game/new, /game/open {id}, /game/delete {id}
    POST /shutdown

    POST /god/move {name, place}
    POST /god/destroy {place, fixture}   also restores a destroyed fixture
    POST /god/smite {name}
    POST /god/fire {place}, /god/extinguish {place}
    POST /edit/game {...}, /edit/character {name, ...}, /edit/relation {a, b, ...}
    POST /god/resolve {id, note}         close a situation by hand
    POST /map/regenerate                 draw the map again, before the world is made

    POST /connect/refresh {provider}     ask a CLI again whether it is installed and signed in
    POST /connect/install {provider}     run the official installer, output streamed under the row
    POST /connect/login {provider}       open a terminal with the CLI's own login command
    POST /connect/key {provider, key}    an API key for this session only, never written to disk

    POST /telegram/check {token}, /telegram/find {token}, /telegram/test {token, chat_id}
    POST /telegram/save {...}, /telegram/send {text}, /telegram/clear

## Notes

- The World and the people are told never to read, create, modify, or delete files. The CLIs are
  launched read-only anyway. Point them at an empty folder; nothing in it is touched.
- Claude Code seats resume their session between turns, so a person keeps their whole context.
  The other providers start fresh each turn and rely on the memory file the engine writes for them.
- Codex signs in with a subscription and rotates its refresh token. Several seats refreshing at once
  race, and the losers are refused. So each day one Codex call runs on its own first, and the sign in
  file it leaves is kept as a copy. If a seat is refused anyway, the year pauses, the copy is put back,
  the priming call runs again, and the year carries on by itself if that worked. If it did not, the
  year stays paused and says so with a link to Connections. One game never mixes the two Codex
  installs, because they share one sign in.
- Codex refuses folders it has not been told to trust. The engine marks the run folder as trusted
  in `~/.codex/config.toml` and keeps a backup of the file beside it.
- Prompts are code. `backend/prompts.py` is short and worth reading before changing anything.
- A test runs a whole year to its end, and the end of a year is one of the things Telegram is told
  about. Set `TERRACEILIA_NO_TELEGRAM=1` for anything that is not a real game; the test suite sets it
  for itself. Without it, running the tests messages whoever set up the bot.

## License

Copyright (c) 2026 Hillside Ventures LLC. All rights reserved. See [LICENSE](LICENSE).
