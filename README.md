# Terraceilia Simulation Game

A living medieval valley played by AI agents, each in its own CLI process.

Twenty-odd villagers, a market town, a castle on the hill, a forest road that is dangerous after dark,
and a winter coming that the last one proved can kill. Each person is played by a coding-agent CLI
(Claude Code, Codex, OpenCode, or Gemini CLI) in its own process, with its own memory and its own
secret. One more agent plays the World: referee, weather, fates, and chronicler. You are the
convener. You watch, you speak as fate, and you can reach into the map and move things with your hand.

The engine owns the world. Stats are rolled by code, dice are rolled by code, every action is
resolved by code, the dead stay dead, and the map is fixed and known to everyone. The World proposes
nothing: it is told what happened and narrates it, and anything it invents is dropped. The agents can
talk, scheme, lie, and act; they cannot change a number by saying so.

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

1. **Dawn.** The engine rolls the weather, spoils the stores, wears the roofs, feeds and warms the
   people from what there is, lets sickness in, and buries nobody. Every unclaimed duty is dumped on
   the nearest able person for the day; a fire, a bad injury, or an attack pulls whoever is nearest.
   A line goes into the chronicle with the season, the weather, and what is low, broken, sick, or
   burning.
2. **Morning: duties.** Everyone able with work is given their duties with place, output, and what
   it costs the valley if skipped. Their `ACTION:` line must begin with `WORK` (all of it), `WORK`
   and one duty's name, or `REFUSE`; anything else counts as skipping. The engine resolves it: output
   rolled from skill and dice, the ledger moved, the skill nudged up. Skipping costs standing and
   that day's work; skip the same work two mornings running and the duty goes unclaimed. REFUSE gives
   it up at once. What nobody did lands its cost and goes to the World and the chronicle by name;
   after two days a neighbour complains by name.
3. **Afternoon: free time.** Only the people something touched, or whose nature is pushing them,
   are asked, and they may act. Everyone else spends the afternoon on their pastime, on the map, and
   people whose pastimes put them in the same place are company and get a turn to talk. Anyone named
   or whispered to at the same place gets a turn to answer. Driving someone out, refusing to share,
   taking work, leaving, and every duty change are settled by the engine before the World sees anything.
4. **The engine resolves the afternoon, the World tells it.** Every free action is read into one of
   fourteen verbs (travel, talk, give, take, steal, hit, drive out, help, tend, court, pray, trade,
   search, wait) with a target, and settled by stats, ties and dice. An action that maps to no verb
   is talk and changes nothing. The World is given only the list of resolved outcomes, with no
   sheets, map, ledger or ties, and tells them one line each, two sentences at most. Its words are
   checked: any line naming a person, place, number or item that is not in the outcome list is
   dropped and logged, and if it gives nothing usable the engine's own lines stand.
5. **Evening: talk.** Everyone goes home, or to the inn if it pulls them, and the people something
   touched talk where they are. No actions. Then the day ends.

Every villager's reply is cut to three sentences before the action line, every World outcome to two,
and every dash a model writes is replaced on the way in. Quiet days are allowed: a person with nothing
touching them replies PASS and is not asked again.

### The people

Each person is rolled with Strength and Speed (2 to 9), hit points (8 to 14), and a purse of gold
(1 to 9). Twelve traits, each scored 1 to 5, shape how they are told to behave: warmth, temper,
honesty, greed, courage, tongue, desire, piety, ambition, loyalty, cunning, and drink. The rolls
are skewed away from nice. Most people are middling, a good share are hard, a few are saints.

Everyone has an opinion about everyone else, as a feeling and a trust score from -5 to 5, seeded
from their natures and then shaped by the ties the World invents and everything that happens after.

### How things go

Fights, thefts, courtship and the rest are settled by the engine. A fight is strength plus a die on
each side; the loser is hurt, and a strong winner on a high roll can kill. A theft is cunning against
cunning; a failed one is seen and costs standing and trust. Courtship is desire and tongue against the
target's chastity and how they feel; a spouse hears of it either way. Every result is written to
state before the World is told a word.

### Drama and events

`data/events.json` holds the things the valley can suffer: bandit raids, fires, plague, tax
collectors, witchcraft accusations, a body in the river. At drama 0 nothing happens that the people
did not cause. At 5 there is about one event a day, mostly small. At 10 there are two or three,
including raids, fires, and deaths. Events apply their wounds and losses in code before the World
ever sees them, and many open a **situation** that stays in front of everyone until it is resolved.
Fires burn for days, wreck what is at a place, hurt the people there, and spread to neighbours.

### Needs and the ledger

Every person has food, warmth and rest on a scale of 0 to 10, and health. They fall every day. A
need at zero takes health each morning, and health at zero is death. A starving or freezing person
spends the morning seeing to it before any duty: they eat what the stores hold or go home and burn
wood, and the duty waits without being lost. Sick people cannot work and get worse until someone
tends them.

The valley keeps grain (in sacks), meat, fish, wood, meals, tools and herbs, and every place has a
roof, a warmth and a filth score. All of it decays daily and nothing comes back without work. Unburied
bodies and filth breed sickness. The season turns with the days (autumn, early winter, deep winter,
thaw) and the weather is rolled from it each morning: cold burns wood and warmth, rain rots roofs,
and nothing grows in winter. The engine runs all of this at dawn, before anyone speaks, and writes a
line into the chronicle with the season, the weather, and what is low, broken, sick, or burning.

### Duties

The valley's work is split into fifteen named duties in `data/duties.json`: mill, fields, hunt, fish,
wood, roofs, stores, healing, kitchen, watch, burial, cleaning, trade, teaching, fire. Each says what
it produces, what it consumes, where it happens on this map, the skill it uses, and what breaks when
it goes undone. Every person holds one to three, seeded from their trade and disposition when the
world is made. Duties change through play, never by a table: a person can refuse one as their action
(standing drops and it goes unclaimed), hand one to someone by name, or take up one nobody holds.
Fate can set them outright in the Duties tab under People. Every morning an unclaimed duty is dumped
on the nearest able person with room for it, who is told so, and a fire, a bad injury, or an attack
pulls whoever is nearest regardless of duty. Work is resolved by the engine: output rolled from skill
and dice, the ledger moved, the skill nudged up.

### Pastimes and spirit

Everyone has a pastime, rolled from `data/pastimes.json` by their disposition: carving, fishing for
fun, singing at the inn, dice, drinking, wandering the ridge, gossip, tending a garden, sparring,
telling stories, praying, collecting things. Fate can change it under People. A free afternoon goes
to it by default, on the map, with a label. Some have side effects: fishing for fun brings a little
fish, carving makes a small thing the person keeps, sparring can nudge strength, drinking costs rest
and warmth. Spirit is a need beside food, warmth and rest: it falls a little every day, more when the
body suffers, and rises on the pastime, on time with someone liked, and on a good meal. Low spirit
halves work output and makes refusing likelier; high spirit raises output.

### Wants and recognition

Every person's want is measured. The engine rolls it from their nature and life: gold to put by, a
skill to reach or to be best at, a tie to win (to be liked, to be trusted, to be someone's lover),
or an evening spent somewhere. The World writes the want line in their own terms around it, and every
prompt tells the person how close they are. When a want is reached the valley hears of it, standing
rises, and a new want is rolled. Skill comes from work and from being taught, and whoever is best at
a duty's skill, alone at the top, is called by it in every prompt and on the People sheet: the miller,
the healer, the woodcutter. Everyone starts as nobody and earns from there.

## The convener's hand

You are not a player, but you are not powerless.

- **Speak as fate.** The composer under the chronicle sends a message to everyone, or to one person
  alone with `@Name`.
- **Move people.** Drag a person on the map to another place.
- **Watch them work.** The map walks each person along the paths to wherever their work or their
  action takes them, with a line under the name saying what they are doing and a thin bar that fills
  as the work resolves. Skippers show idle, the sick rest at home, emergencies move people at once.
  It is driven by the engine's own record of what each person is doing, so a page opened halfway
  through shows the right stage, on a phone as much as on a desktop.
- **Wreck and restore.** Click a place to see what is there. Destroy a fixture, restore one, or set
  the place on fire and put it out again.
- **Strike someone down.** Smite a person and they are dead.
- **Edit anyone.** In Settings, change a person's model, stats, life, or name while the game runs.
  Bring the dead back or let someone who left walk home. Change how any two people feel about each
  other.
- **Change the game.** Title, world text, days, time limit, drama, and the World's model can all be
  changed mid-game, under World.
- **Resolve a situation.** The World sheet's situations timeline lists everything open, with its age
  and days left and a Resolve control, then everything ended and what ended it. The same sheet holds
  the valley as the player described it with what each place is, the season calendar as plain
  rows, and today's weather with tomorrow's chances.

Gameplay sits in plain buttons across the header: the primary control, then Colony, People, World
and Fate. Colony shows today's duties with who holds each and the unfilled ones in red, the
ledger with today's change per line, every place's roof, warmth and filth, the season and the weather,
and this morning's work. People carries a Duties tab and the want line under every name, and each card
in the strip says what that person is doing now. The chronicle is grouped by morning, afternoon and
evening. Everything else is behind the gear: Connections, the three exports, Display, Stop this year,
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
- Every CLI is launched by `backend/runner.py`, which reads the exit code and the runner's own error lines
  before anything is taken as a line of dialogue. A refusal for want of a sign in pauses the year and asks you
  to sign in and press Resume. A model that is not found or not accessible moves the seat to the first model
  of that provider that answered the probe, with a line in the chronicle. A rate limit or a server error waits
  with backoff and asks again. Credentials missing from the request itself is a launcher bug: the run stops and
  shows the exact command it built. Anything else is asked again once, then the seat is benched for the turn
  with the runner's message. Two clocks kill a hung process: thirty minutes on the wall whatever it prints,
  and five minutes without a line.
- Nothing in Terraceilia reads or writes any CLI's credential file. Codex's sign in belongs to Codex; the two
  Codex installs share it, so one game uses only one of them, and Connections says so.
- Start runs a preflight: every seat's chosen model answers one tiny request through the same launcher and
  environment a turn uses, or the run stops and the reason is shown. A seat with no model chosen takes the
  first model of its provider that answers; nothing is hardcoded. Connections shows Connected only after a
  model has answered a real request, with the time, and the version of the binary that will actually run.
- Codex refuses folders it has not been told to trust. The engine marks the run folder as trusted
  in `~/.codex/config.toml` and keeps a backup of the file beside it.
- A game saved before some part of the colony existed is brought up to date when it is opened: duties,
  pastimes, wants, needs, spirit, the ledger and the state of the places are seeded once, exactly as
  for a new game, and a line in the chronicle says so.
- Situations never repeat while they are open, at most six are open at once, each expires after its
  own number of days with a chronicle line, and the duties that can settle one do (the trader fixes
  the bell, the healer ends the sickness, the sexton buries the body). `data/events.json` carries
  `days` and `fixed_by` for each.
- The whole page is drawn from seven colours defined once at the top of `frontend/style.css`; the
  map's own painting keeps its colours. Seat colours are warm and earthen.
- Prompts are code. `backend/prompts.py` is short and worth reading before changing anything.
- A test runs a whole year to its end, and the end of a year is one of the things Telegram is told
  about. Set `TERRACEILIA_NO_TELEGRAM=1` for anything that is not a real game; the test suite sets it
  for itself. Without it, running the tests messages whoever set up the bot.

## License

Copyright (c) 2026 Hillside Ventures LLC. All rights reserved. See [LICENSE](LICENSE).
