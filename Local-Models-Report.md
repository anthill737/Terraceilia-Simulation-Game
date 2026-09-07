# Local models and OpenRouter: how DevTeam does it, and what fits Terraceilia Sim

Read-only investigation, 2026-09-06. Sources: DevTeam at `C:\Users\antho\Projects\Code\Dev-Team` (main, 1d67f43) and Terraceilia Sim at `C:\Users\antho\Projects\Games\Terraceilia Sim` (branch remove-court). Nothing was changed in either repo. File and line references point at the code as it stands today.

---

## 1. The short answer

DevTeam does not talk to Ollama or OpenRouter itself. It installs and drives one harness, the **OpenCode CLI in server mode**, and generates a locked config that points OpenCode at either **Ollama on 127.0.0.1:11434** (local, $0) or **openrouter.ai/api/v1** (hosted, per-token). Everything the user sees (install button, download progress, hardware fit chips, capability badges, price chips, the key field) is DevTeam's own UI over that one harness.

Terraceilia already shells out to agent CLIs, and OpenCode is already one of its six providers with an `ollama/qwen3` entry in its model list. So there is a **zero-code path today**: pick OpenCode, type `ollama/<model>`, provided the player has Ollama running and OpenCode configured for it. It is undocumented and untested.

The recommendation is not to copy DevTeam's harness. Villagers do not need tools, file access, MCP, or a coding agent. They need one HTTP POST per turn that returns a few sentences and an `ACTION:` line. The right port is:

- **Copy DevTeam's product decisions**: app-owned pinned Ollama install, reuse an existing server, never override the model store, a curated catalog as data with RAM fit tiers, streamed pull with progress, a capability probe that produces a badge, a key that never reaches the browser, honest $0 vs per-token labelling.
- **Skip DevTeam's runtime**: no OpenCode server lifecycle, no tool lockdown, no MCP, no parallel-tool-call rails, no token-fold accounting.
- **Add a second transport** to Terraceilia's `PROVIDERS` table: direct HTTP to Ollama and OpenRouter using `urllib` (the repo's zero-dependency rule), with the memory file inlined since an HTTP model cannot read files.

The one design question that needs a decision before building is villager memory for stateless providers (section 7.3). Everything else is plumbing.

---

## 2. DevTeam architecture in one picture

```
                 model string                      who runs it
  claude-*  ─────────────────────────────►  Claude Code CLI (subscription)
  gpt-* / codex-*  ──────────────────────►  Codex CLI (subscription)
  copilot-*  ────────────────────────────►  Copilot CLI (subscription)
  opencode-<ollama tag>  ────┐
                             ├──►  OpenCode CLI `serve` (pinned 1.18.17, app-owned npm prefix)
  opencode-or-<openrouter id> ┘         │
                                        ├── provider "ollama"     → http://127.0.0.1:11434/v1
                                        └── provider "openrouter" → https://openrouter.ai/api/v1
                                                                     apiKey = {env:OPENROUTER_API_KEY}
```

Key files:

| Concern | File |
|---|---|
| Ollama detect / install / serve / tags | `backend/app/agents/ollama_manager.py` |
| OpenCode `serve` lifecycle and generated config | `backend/app/agents/opencode_server.py` |
| OpenCode HTTP+SSE runner, model-string split | `backend/app/agents/opencode_runner.py` |
| Jobs, pull progress, hardware, probe, badges, boot self-heal | `backend/app/local_models.py` |
| Catalog loaders and validation | `backend/app/local_catalog.py` |
| Local catalog (data) | `backend/app/data/local_models.json` |
| Hosted catalog (data) | `backend/app/data/hosted_models.json` |
| OpenRouter key storage | `backend/app/openrouter_key.py`, `backend/app/secret_crypto.py` |
| OpenCode CLI pin and install | `backend/app/provider_readiness.py` |
| REST routes | `backend/app/api/local_models.py` |
| Unified model picker catalog | `backend/app/api/projects.py` (`/api/projects/models/catalog`) |
| Panel UI | `frontend/src/components/LocalModels.tsx` |
| First-run card and Settings row | `frontend/src/components/ProviderSetup.tsx`, `ScanForProjects.tsx` |
| Per-role dropdowns | `frontend/src/components/ProjectList.tsx` (`ModelAssignmentsSection`) |

### 2.1 Model-id namespace

The prefix is the routing truth, not membership in a list:

| Shape | Routes to | Example |
|---|---|---|
| `opencode-<tag>` | OpenCode → Ollama | `opencode-qwen3:8b` |
| `opencode-or-<org/model>` | OpenCode → OpenRouter | `opencode-or-z-ai/glm-5.2` |

`_split_model` in `opencode_runner.py:63-77` strips `opencode-`, then checks for `or-`. Tags pass through verbatim so `hf.co/unsloth/...:Q4` pulls survive. Both catalogs enforce their prefix at load and refuse to start otherwise.

---

## 3. Local models: the Ollama path

### 3.1 Install

`ollama_manager.py:56-73`. Pinned `OLLAMA_PINNED_VERSION = "0.32.9"`, release-tagged GitHub assets, never `latest`:

- Windows: `ollama-windows-amd64.zip`, unpacked into `%LOCALAPPDATA%\DevTeam\tools\ollama`
- macOS: `ollama-darwin.tgz`, into `~/.local/share/devteam/tools/ollama`
- Linux: no asset, `install()` raises. Deliberate gap.

The standalone zip was chosen over `OllamaSetup.exe /VERYSILENT` on purpose: no installer, no registry, no admin prompt, no tray app. Download is streamed in 512 KB chunks with progress callbacks (`downloading` → `unpacking` → `verifying`), the archive is deleted, and the last step runs `ollama --version` so nothing half-installed reads as ready.

Binary resolution order (`resolve_ollama_binary`, 105-123): `DEVTEAM_OLLAMA_PATH` env → `ollama` on the augmented PATH → app prefix → macOS defaults (`/usr/local/bin`, Homebrew, `Ollama.app/Contents/Resources`). **A user's own Ollama is found and used before the app's copy.**

### 3.2 Serve

`ensure_serving()` (261-302) probes `GET /api/version` first. **If anything already answers on 11434 it is used and never spawned over or killed.** Otherwise `ollama serve` is spawned as a child with stdout/stderr discarded and polled every 0.5 s for up to 30 s. `OLLAMA_HOST` is not set; `OLLAMA_MODELS` is deliberately not overridden so weights land in `~/.ollama/models` and are shared with any pre-existing install (nothing downloads twice). Teardown kills only a server DevTeam spawned.

Because the spawned server is a child process it dies with each backend restart. `boot_local_stack()` (`local_models.py:39-67`) restarts it at boot as a detached task, and `GET /status` self-heals a stopped server in the background so the settings screen never waits on it.

### 3.3 Hardware detection and fit

`local_models.py:190-238`:

- RAM: `psutil.virtual_memory().total`
- VRAM: `nvidia-smi --query-gpu=memory.total` (5 s timeout, max across GPUs), cached per process because it sat on the settings-open path. macOS reports VRAM = RAM (unified memory). AMD/Intel report `None` honestly.
- **Fit uses RAM only**, never VRAM:

```python
if system_ram_gb >= ram_gb_recommended: return "fits"
if system_ram_gb >= ram_gb_min:         return "tight"
return "wont_run"
```

Rendered as chips "Fits your machine" / "Tight fit" / "Won't run well here". Advisory only, never a block. Disk is the one hard refusal: a pull is refused when free space is under 1.5 × model size.

### 3.4 The local catalog

`backend/app/data/local_models.json`, 14 entries, `verified_against_registry: 2026-08-12`, read fresh on every request (no cache) so data edits need no restart. Required fields per entry: `id`, `ollama_tag`, `label`, `family`, `size_gb`, `ram_gb_min`, `ram_gb_recommended`, `context_window`, `tool_calling`, `license_name`, `license_url`, `registry_url`, `ram_note_source` (`publisher` | `rule_of_thumb`), `capability_note`, `quantization`; optional `vision`, `related_hosted_id`.

Validation at load refuses: wrong prefix, duplicate ids or tags, bad RAM ordering, non-https URLs, `size_gb <= 0`. Curation rules recorded in the file's `$comment`: cloud-only ollama.com tags are banned (they bill an Ollama subscription), `:latest` traps are pinned to explicit sizes (`gpt-oss:120b` vs `:latest` = 20B), `gemma3:12b` was skipped for lacking tools.

Entries as shipped:

| id | Ollama tag | GB | RAM min/rec | ctx | vision |
|---|---|---|---|---|---|
| opencode-qwen3:4b | qwen3:4b | 2.5 | 6 / 8 | 256k | |
| opencode-qwen3:8b | qwen3:8b | 5.2 | 8 / 16 | 40k | |
| opencode-qwen3:14b | qwen3:14b | 9.3 | 12 / 16 | 40k | |
| opencode-devstral:24b | devstral:24b | 14 | 24 / 32 | 128k | |
| opencode-gpt-oss:20b | gpt-oss:20b | 14 | 16 / 24 | 128k | |
| opencode-qwen3.6:27b | qwen3.6:27b | 17 | 24 / 32 | 256k | yes |
| opencode-muse-glimmer:30b | muse-glimmer:30b | 18 | 24 / 32 | 128k | yes |
| opencode-qwen3-coder:30b | qwen3-coder:30b | 19 | 24 / 32 | 256k | |
| opencode-laguna-xs-2.1 | laguna-xs-2.1:latest | 20 | 36 / 48 | 256k | |
| opencode-qwen3-coder-next | qwen3-coder-next:latest | 52 | 64 / 96 | 256k | |
| opencode-gpt-oss:120b | gpt-oss:120b | 65 | 80 / 96 | 128k | |
| opencode-deepseek-v4-flash-gguf | hf.co/unsloth/DeepSeek-V4-Flash-GGUF:UD-Q4_K_XL | 155 | 176 / 256 | 1M | |
| opencode-glm-5.2-gguf | hf.co/unsloth/GLM-5.2-GGUF:UD-IQ2_M | 239 | 256 / 512 | 1M | |
| opencode-kimi-k2.6-gguf | hf.co/unsloth/Kimi-K2.6-GGUF:UD-Q2_K_XL | 340 | 350 / 512 | 256k | |

All 14 carry `tool_calling: true` because DevTeam's seats are tool-driven agents. That filter does not apply to villagers (section 7.1).

### 3.5 Pull with progress

`LocalModelJobs.start_pull` → `POST /api/pull {"model": tag, "stream": true}` on Ollama, NDJSON lines fed into a `PullProgress` state machine (`starting → downloading → verifying → success`, terminal `error` / `cancelled`). Per-layer byte accounting with a monotonic guard so a re-announced layer never makes the bar go backwards. Cancel closes the connection; Ollama resumes from the same bytes next time. On success the capability probe runs automatically. The Ollama binary install feeds the same progress shape with a synthetic digest so the UI has one progress-bar contract.

Jobs live in an in-memory dict, polled by the frontend every 1.5 s only while something is live.

### 3.6 The capability probe and badges

`local_models.py:470-600`. Not a smoke prompt: it runs the real runtime path with one tool named `probe_echo` whose description is the whole test ("call this exactly once with `{"ping": "pong"}` then reply PROBE OK"), 240 s wall clock. Outcomes are written to `%LOCALAPPDATA%\DevTeam\local_models_state.json`:

- `verified`: tool was called and a reply came back
- `failed`: completed without driving the tool; the model stays selectable but picking it in a project opens a consent modal and the backend returns 422 without a per-project acknowledgment
- `unverified`: probe never ran to completion (Ollama down etc.), deliberately not "failed"

No model is ever unlabelled; absence of state reads as `unverified`. Hosted models get the same probe.

### 3.7 Runtime: how a local model actually answers

`opencode_server.py:81-176` generates `opencode.json` per seat:

```python
providers = {"ollama": {"npm": "@ai-sdk/openai-compatible",
                        "name": "Ollama (local)",
                        "options": {"baseURL": "http://127.0.0.1:11434/v1"},
                        "models": {...}}}
```

plus `small_model` pinned to the seat's own model, `share: disabled`, `autoupdate: false`, every builtin tool set `false` (bash, edit, write, read, grep, glob, list, apply_patch, webfetch, websearch, task, skill, todowrite, question, lsp), `permission: {edit/bash/webfetch: deny}`, and one MCP server (`devteam`) carrying a bearer token. `parallelToolCalls: false` is stamped on every model because parallel bursts wedged OpenCode's MCP dispatch 13 times in one audit.

The runner then: `POST /session`, opens `GET /event` SSE **before** prompting, `POST /session/{id}/prompt_async` with `{"model": {"providerID", "modelID"}, "system", "parts"}`, and translates SSE parts into DevTeam's stream events (text delta, thinking delta, tool start, tool result, usage, turn complete). Two hard-won defenses live here: user-role parts are filtered out (a bug once re-emitted the prompt as assistant text and compounded quadratically), and a "fake tool text" bounce loop catches models that print `<tool_call>` instead of calling one.

---

## 4. Hosted models: the OpenRouter path

### 4.1 Key entry and storage

- UI: `LocalModels.tsx:342` `OpenRouterKeyRow`, a password input with placeholder `sk-or-…`, Save key / Remove key.
- API: `POST /api/local-models/openrouter/key {key}` (400 on empty) and `DELETE`. Saving also kicks a background install of the pinned OpenCode CLI.
- Disk: `%LOCALAPPDATA%\DevTeam\openrouter_key`. Windows: DPAPI `CryptProtectData` user-scoped, on-disk format `DPAPI:v1:<base64>`, self-verifying with plaintext fallback. macOS/Linux: plaintext at 0600 (stated posture; Keychain is future work).
- The key **never reaches the browser**. Status exposes only `key_configured: true|false`.
- The key **never reaches a config file**. The generated `opencode.json` carries the literal token `{env:OPENROUTER_API_KEY}` and the real value rides the spawn environment only. A test asserts `"sk-or-" not in str(cfg)`.
- **No validation at save.** Any non-empty string is stored. A bad key surfaces as a `session.error` at runtime, or via the capability probe. No `HTTP-Referer` / `X-Title` headers are sent.

### 4.2 Gating

Key presence, and only key presence, unlocks the hosted tier in the picker (`api/projects.py:388-411`). A prior bug also required the OpenCode CLI to be present, so a saved key unlocked Settings while New Project stayed grey; the fix made the key the sole gate and installs the CLI in the background.

### 4.3 The hosted catalog

`backend/app/data/hosted_models.json`, 6 entries, `verified_against_openrouter: 2026-08-12`. Header comment states the contract: OpenRouter is the **single** gateway, no direct-provider integrations, no arbitrary endpoints, and the tier is curated **open-weight** models only (enforced by curation plus tests, not by code).

| id | OpenRouter id | $/M in | $/M out | $/M cached | ctx | vision |
|---|---|---|---|---|---|---|
| opencode-or-z-ai/glm-5.2 | z-ai/glm-5.2 | 0.77 | 2.64 | 0.14 | 1M | |
| opencode-or-deepseek/deepseek-v4-pro | deepseek/deepseek-v4-pro | 0.435 | 0.87 | | 1M | |
| opencode-or-moonshotai/kimi-k2.6 | moonshotai/kimi-k2.6 | 0.58 | 3.4 | | 262k | yes |
| opencode-or-moonshotai/kimi-k3 | moonshotai/kimi-k3 | 3.0 | 15.0 | 0.3 | 1M | yes |
| opencode-or-meta/muse-glimmer-30b | meta/muse-glimmer-30b | 0.35 | 1.5 | 0.04 | 131k | yes |
| opencode-or-poolside/laguna-s-2.1:free | poolside/laguna-s-2.1:free | 0 | 0 | 0 | 262k | |

Validator rules: `opencode-or-` prefix, `org/model` shape, positive prices unless the id ends in `:free` ("hosted models bill real money; zero prices are a data error"), duplicates refused. GLM-5.2's prices are **measured effective routed rates** (least-squares fit of one run against OpenRouter's per-minute billing, 1.7% error), not the listed ones, because listed and routed rates differed. The free entry carries a data-policy warning (Poolside may train on inputs).

### 4.4 Runtime

Same OpenCode server, different provider block:

```python
providers["openrouter"] = {
    "npm": "@ai-sdk/openai-compatible",
    "name": "OpenRouter (hosted)",
    "options": {"baseURL": "https://openrouter.ai/api/v1",
                "apiKey": "{env:OPENROUTER_API_KEY}"},
    "models": {...}}
```

Hosted seats skip `ensure_serving()` entirely. `small_model` is pinned to the seat model because OpenCode's unset default auto-picked a Gemini Flash model and billed Gemini on an all-GLM run.

### 4.5 Cost accounting

Token usage is read from the SSE `message.updated` / `step-finish` frames. The fold is cumulative within a message id and summed across ids; the earlier latest-wins-globally fold recorded ~1% of real volume (a 160× undercount on one run). Reasoning tokens count as output. Hosted rates come from the catalog; cache reads bill at the cached rate, cache writes as input, unmeasured models fall back to 10% of input for cached. A calibration test replays a real run and asserts the estimate lands within 10% of the $4.42 OpenRouter actually billed.

Local models are priced at exactly $0.00, on purpose.

---

## 5. How a DevTeam user chooses a model

1. **First run** (`ProviderSetup.tsx`): a grid of four peer cards. Claude Code (recommended), OpenAI Codex, GitHub Copilot, and **Local & hosted models** with a "Free local tier" chip, sub-line "OpenCode + Ollama · no account, no sign-in", and a live summary ("✓ Ollama running · 3 models downloaded · OpenRouter key saved"). Button reads **Set up** when nothing is configured, **Manage** afterwards. Both open the panel.
2. **The panel** (`LocalModels.tsx`): an amber disclaimer that small models perform poorly in agent seats and huge ones need extreme hardware; an Ollama card with Running/Installed/Not installed chips, free disk, RAM and VRAM, and an **Install Ollama** or **Start** button; an OpenCode CLI line with Install/Reinstall; a 2-up grid of local model cards each with fit chip, badge chip, size, context, license link, capability note, and a **Download N GB** button that turns into a progress bar with Cancel, then "Downloaded" plus **Run capability check**; a hosted section with the key row and hosted cards showing a price chip `$X/M in · $Y/M out`.
3. **Settings → Account** (`ScanForProjects.tsx`): the same fourth row under Copilot, same chrome, Manage / Set up.
4. **Create or Edit Project**: per-role dropdowns (Architect, Dispatcher, Coder, optional split Coder (frontend), Reviewer, plus a vision-only Visual critic select) grouped by `<optgroup>`: Anthropic, OpenAI, Copilot, **Local models (Ollama, $0.00)**, **Hosted open models (OpenRouter, per-token)**. Only **pulled** local models appear; un-pulled ones are simply absent and an empty group renders a disabled pointer "No local models installed. Set up in Settings > Local & hosted models." Hosted appears only with a key. Badges ride the option text ("· tool-use verified"). Per-role upgrade policy Auto / Ask first / Never change. The "Recommended" preset never targets local or hosted models.

Front-end pattern worth noting: `uiCache` seeds every one of these surfaces from `localStorage` for an instant first paint and then refreshes in place. Measured cold status fetch is under a second; nothing blocks on Ollama or `nvidia-smi` in a view path.

### 5.1 Gaps found in DevTeam while reading (informational)

- No OpenRouter key validation at save time.
- No Linux Ollama asset.
- `pricing_note` and `price_cached_input_per_mtok` never reach the hosted card UI.
- Hosted spend appears under a "subscription est. / this is not a bill" tooltip in the workroom, which is wrong for real OpenRouter billing.

---

## 6. Where Terraceilia Sim stands today

### 6.1 Shape

Python 3.11 stdlib server (`backend/server.py`) plus vanilla JS (`frontend/app.js`), **zero pip dependencies** as a stated value (README line 17). About 5,200 lines, 22 commits over two days. Every model call goes through one method, `Run._invoke` in `backend/game.py:368-415`:

1. write the prompt to `games/<id>/seatN/prompt_NNN.md`
2. format `PROVIDERS[name]["ro_cmd"]` with `{ask}` = "Read the file … and respond exactly as it instructs" and `{model}`
3. `subprocess.Popen(cmd, shell=True)` in the run folder, stream stdout to the seat's terminal pane
4. for Claude, parse `stream-json` and capture `session_id` for `--resume`; for everyone else take stdout as the speech

The provider table is `backend/agents.py:12-55`: Claude Code, Codex (latest), Codex, **OpenCode**, Gemini CLI, GitHub Copilot CLI. Each entry is `exe`, `cmd`, `ro_cmd`, `resume`, `speech`, `pkg`, `models`. The OpenCode entry already lists:

```python
"models": ["zai/glm-5.2", "openai/gpt-6-astra", "openai/gpt-5.6", "anthropic/claude-fable-5-1",
           "anthropic/claude-opus-5", "google/gemini-3-pro", "ollama/qwen3"]
```

and its sign-in probe regex in `connect.py:116` accepts `ollama` as a configured auth backend. That is the whole extent of local-model support: latent, indirect, and dependent on the player having configured OpenCode's own Ollama provider outside the game.

### 6.2 Connections sheet (`backend/connect.py`)

One row per provider: installed?, version, signed in? (via the CLI's own status command, or its credential file), **Install** (runs the vendor's official installer, output streamed under the row), **Sign in** (opens a real terminal window with the vendor's login command and polls for ten minutes), and an **API key** password input for providers with a `key_env` (`ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `COPILOT_GITHUB_TOKEN`). Keys are placed in the process environment for this session only, **never written to disk, never sent to the browser** (docstring line 9). `telegram.json` beside the game is the one precedent for a small gitignored secrets file.

### 6.3 Model choice UI

New game: four `<select provider><select model><input custom>` triplets (World, odd seats, even seats, map model). "Custom..." accepts any string. World sheet changes the World's model mid-game; People → Bio changes one villager's provider and model mid-game (starting them fresh). Mixed seating is already first-class: **the World can run on one provider while villagers run on two others**.

### 6.4 Call pattern and tolerance

Per in-game day: one call per living villager, **all launched in parallel threads** (`_player_phase`, `game.py:521+`), plus reaction calls for anyone `@mentioned`, plus one or two World calls. Roughly 25 to 60 calls a day at 20 villagers, several hundred per default 12-day year. `TURN_TIMEOUT = 1800` (30 minutes) per call. Prompts run about 9 to 14 KB (3 to 4k tokens); the memory file is **referenced by path, not inlined** (`game.py:424`), so prompts stay bounded even at day 30 when `memory.md` reaches 250 KB.

Outputs: villagers return free prose plus one `ACTION:` line, parsed by regex. The World returns narration plus a fenced JSON block (`results`, `events`, `ledger`, `dead`, `relations`, `threads`, `fires_out`) that `World.apply` validates and clamps. The map surveyor returns strict JSON validated by `validate_map`. `engine.py:118` says it plainly: "Never trust the AI." Weak models already degrade gracefully by design.

Tests already inject a fake provider (`tests/stub_agent.py`, registered by inserting one dict into `agents.PROVIDERS`) and run a whole three-day game against it.

---

## 7. Fit assessment

### 7.1 What is different about a game

| | DevTeam seat | Terraceilia villager | Terraceilia World |
|---|---|---|---|
| Needs tool calling | yes, constantly | **no** | no |
| Needs file access | yes (worktree) | only to read its own memory | no |
| Output contract | agentic multi-turn | 1 to 3 sentences + `ACTION:` | prose + JSON block |
| Calls per unit of work | hundreds per task | 1 per day | 1 to 2 per day |
| Concurrency | a few seats | **up to 30 at once** | 1 |
| Latency tolerance | minutes | 30 minutes | 30 minutes |
| Quality bar | must produce working code | must stay in character, be readable | must emit valid JSON and obey rules |

Consequences:

- **Tool-use is not the gate for villagers.** DevTeam's whole catalog filter (`tool_calling: true`), its probe, its fake-tool bounce loop, and its parallel-tool-call rails exist because agents drive tools. Villagers need none of that. A 4B or 8B model that DevTeam's disclaimer calls poor in agent seats may be perfectly adequate as a drunk blacksmith. The game's probe should test what the game needs: **does it return prose ending in exactly one `ACTION:` line, in character, under the length limit?**
- **The World is the hard seat.** It must obey rules, count, and emit strict JSON. That seat is where a hosted or frontier model earns its keep. Because seating is already mixed, the natural default is **World on a cloud or hosted model, villagers local**.
- **Structured output is a direct-HTTP advantage.** Ollama's `/api/chat` accepts `format: "json"` or a JSON schema, and OpenRouter passes `response_format` through for models that support it. CLIs cannot offer this; today the World's JSON is retried on parse failure (`for attempt in range(2)`). Direct HTTP could enforce the schema for the World turn and ask for plain text for villagers.

### 7.2 Concurrency is the real hardware constraint

DevTeam runs a handful of seats and never had to think about this. Terraceilia fires **every living villager at once**. Ollama serves one loaded model with a bounded number of parallel request slots (`OLLAMA_NUM_PARALLEL`, auto-chosen between 1 and 4 by free memory in recent versions) and queues the rest (`OLLAMA_MAX_QUEUE`, default 512). So 20 parallel villager calls do not fail, they serialize:

- day-phase wall time ≈ (villagers ÷ parallel slots) × per-call latency
- per-call for a ~4k-token prompt and ~150-token reply on an 8B Q4 model on a mid-range consumer GPU is on the order of 5 to 15 s; so 20 villagers land around 1 to 5 minutes, well inside the 30-minute timeout and comparable to the "a minute or two" the README already promises for world creation
- on CPU-only machines multiply by 5 to 10; still inside the timeout but a worse experience
- two different local models (odd and even seats) means Ollama swaps models between requests unless both fit in memory at once (`OLLAMA_MAX_LOADED_MODELS`); recommend one local model for all villagers by default

Three concrete mitigations the game controls: cap concurrent local calls with a semaphore sized from `OLLAMA_NUM_PARALLEL` (or just 4); keep prompts short (they already are); keep the model loaded across the day with `keep_alive`. None of these exist in DevTeam because it never needed them.

These figures are estimates from general experience with Ollama, not measurements on Anthony's hardware. A ten-minute test with `qwen3:8b` and 20 stub villagers would replace them with real numbers.

### 7.3 The memory problem (the one design decision)

Claude Code seats keep their whole context via `--resume`. Every other provider starts fresh each turn and is told where its `memory.md` lives so it can **read the file itself** (`game.py:424`). An HTTP model cannot read files. So a local or hosted villager would have **no memory beyond "what you saw since your last turn"** unless the engine inlines it.

Options, roughly in order of cost:

1. **Inline the tail** of `memory.md` (last N KB or last K days) into the prompt. Simple, bounded, and matches what small-context models can hold. Recommended default.
2. **Rolling summary**: every few days ask the villager's own model to compress older memory into a paragraph and keep that plus the recent tail. Costs one extra call per villager per few days.
3. **Full inline** for large-context models only (the 256k-context entries in DevTeam's catalog would take a 250 KB memory file, but slowly and with KV-cache pressure across 20 seats).

Whatever is chosen, the prompt file under `seatN/` should still be written since it is a documented feature and useful for debugging; it just stops being what the model reads.

### 7.4 What to port from DevTeam, and what to leave

**Port (product decisions, mostly language-agnostic):**

- App-owned pinned Ollama install from release-tagged assets into a per-user prefix; verify by running `--version`; no installer, no admin.
- Reuse any server already on 11434; never kill one you did not start; never override `OLLAMA_MODELS`.
- Catalog as a data file, validated at load, read fresh (no restart for edits). Fields the game needs: id, tag, label, size, RAM min/rec, context, license, note. Drop `tool_calling`. Consider adding a `role_hint` (villager / world / either) and a quantization label.
- RAM-based fit tiers as advisory chips; disk check as the one hard refusal.
- Streamed pull with layer-accurate progress and cancel; auto-probe on success.
- A badge per model from a real probe, with `unverified` as the standing default and `failed` as a warning rather than a block.
- OpenRouter as the single hosted gateway, curated open models, prices shown per million tokens, the user's dashboard named as billing ground truth, `:free` entries allowed only with a data-policy note.
- Key handling: password field, never to the browser, never into a config file, DPAPI on Windows / 0600 elsewhere **if** the game decides keys may persist (today it says they may not).
- Boot self-heal for the spawned server; status endpoints that never block on Ollama or `nvidia-smi`.
- Honest copy: "$0.00, runs on your machine" vs "billed per token to your OpenRouter account".

**Leave behind (DevTeam runtime, agent-specific):**

- OpenCode `serve` lifecycle, generated `opencode.json`, tool lockdown, MCP bearer tokens, `parallelToolCalls`, `small_model` pinning.
- SSE-to-stream-event translation and its user-part filter and fake-tool bounce.
- The three-tier token fold and measured routed rates. For a game, listed rates times a simple in/out token count from the response `usage` field is enough.
- The 422 acknowledgment gate. A confirm dialog in the game UI is plenty.
- Per-role upgrade policy and the model-routing spine.

### 7.5 Two ways to build it

**Option A: lean on OpenCode, which is already a provider.** Generate an OpenCode config with `ollama` and `openrouter` provider blocks (exactly DevTeam's `generate_opencode_config` minus the lockdown), pass it via `OPENCODE_CONFIG` when launching `opencode run --model ollama/<tag>`. Add Ollama install/pull UI. No new transport in `_invoke`. Cost: still spawns a coding-agent process per villager per turn (heavy at 30 seats), inherits OpenCode's startup time and version churn (DevTeam pins 1.18.17 for this reason), the memory-by-path trick keeps working since OpenCode can read files, and the World cannot use structured output. Fastest to a demo, weakest as a product.

**Option B: add an HTTP transport (recommended).** Give `PROVIDERS` entries a `transport` field (`cli` today, `http` new). `_invoke` branches: `cli` keeps every line it has now; `http` builds messages (system = rules, user = prompt text with the memory tail inlined), POSTs to Ollama `/api/chat` or OpenRouter `/api/v1/chat/completions` with `stream: true` via `urllib`, feeds text chunks into the existing `_term(i, …)` sink so the seat terminal shows tokens arriving, and returns the final text. `connect.py` gets two new probe shapes: Ollama = `GET /api/tags` (installed + which models are pulled), OpenRouter = key present. Both rows keep the existing Install / key-input chrome. Zero new dependencies. The stub-agent test pattern extends naturally with a tiny stdlib HTTP stub.

Rough size for B, based on the current code: a new `backend/local_models.py` of a few hundred lines (Ollama install, serve, tags, pull job, hardware, probe), about 60 lines in `_invoke` for the HTTP branch, two probe branches in `connect.py`, a `data/models.json` catalog, one new Connections panel section in `app.js`, and tests against an HTTP stub. The memory decision (7.3) and the concurrency cap (7.2) are the only parts that need thought rather than transcription.

### 7.6 Cost picture, so the pitch is honest

Per in-game day at 20 villagers: roughly 50 calls × ~4k input tokens + ~200 output tokens ≈ 200k in, 10k out.

| Seat plan | Per day | 12-day year |
|---|---|---|
| All local (Ollama) | $0 | $0 |
| Villagers local, World on GLM-5.2 hosted (2 calls) | ~$0.01 | ~$0.15 |
| All hosted on GLM-5.2 ($0.77 / $2.64 per M) | ~$0.18 | ~$2.20 |
| All hosted on DeepSeek V4 Pro ($0.435 / $0.87) | ~$0.10 | ~$1.15 |
| All hosted on Laguna S 2.1 :free | $0, but Poolside may train on the transcripts | $0 |

Rates are DevTeam's catalog snapshots from 2026-08-12; OpenRouter routes and reprices, so the player's dashboard is ground truth. Today's subscription-CLI path has no visible cost at all, which is part of why nobody has measured it.

### 7.7 Model shortlist for the game (starting point, not verified in-game)

From DevTeam's verified entries, re-judged for roleplay rather than coding:

- **Villagers, local, modest machine (8 to 16 GB RAM)**: `qwen3:4b` or `qwen3:8b`. Small, fast, fits alongside a browser. Character consistency will be the weak point; the engine's clamps cover the rest.
- **Villagers, local, 24 to 32 GB RAM or a 16 GB GPU**: `gpt-oss:20b` or `qwen3.6:27b`. Noticeably better prose and rule-following.
- **World, local, only on big machines**: `gpt-oss:120b` and above. Otherwise put the World on a hosted or subscription model.
- **World, hosted**: `z-ai/glm-5.2` (measured cheap, 1M context, proven on multi-hour DevTeam runs) or `deepseek/deepseek-v4-pro` (cheapest). Kimi K3 is priced 4 to 6× higher and DevTeam found it slow.
- **Onboarding without a card**: `poolside/laguna-s-2.1:free`, with the data-policy line shown.

None of these have been run against Terraceilia's prompts. The capability probe proposed in 7.1 is how the catalog earns its badges.

---

## 8. Open questions for Anthony

1. **Key persistence.** Today Terraceilia refuses to write API keys to disk. DevTeam persists the OpenRouter key DPAPI-wrapped. Should the game keep session-only keys (re-paste every launch) or adopt the `telegram.json` precedent with DPAPI on Windows?
2. **Memory strategy for stateless providers** (7.3): tail, rolling summary, or full inline gated by context window?
3. **Default seating.** Should a fresh install default to World on the best connected cloud provider and villagers on the best pulled local model, or stay provider-neutral as now?
4. **Option A vs B.** OpenCode-with-generated-config gets a demo fastest; direct HTTP is the better product and the only path to schema-enforced World JSON. Both can coexist (OpenCode stays a provider either way).
5. **Bundling.** DevTeam downloads Ollama on demand rather than shipping it. Same here, or ship nothing and only detect a user-installed Ollama at first?
6. **Linux.** DevTeam has no Linux Ollama asset. Terraceilia runs on Linux; the official `install.sh` or the tarball would need adding.

---

## Appendix A: DevTeam endpoints, for reference when designing the game's API

```
GET    /api/local-models/status                 whole panel state; self-heals a stopped server in background
POST   /api/local-models/ollama/install         job snapshot
POST   /api/local-models/ollama/start           {state, version}; 409 on failure
POST   /api/local-models/opencode/install       forced CLI ensure
POST   /api/local-models/pull                   {model_id} → job; 404 unknown, 409 disk/serve failure
GET    /api/local-models/jobs/{id}              job snapshot
POST   /api/local-models/jobs/{id}/cancel
POST   /api/local-models/probe                  {model_id} → job
POST   /api/local-models/acknowledge            {model_id, project_id}
POST   /api/local-models/openrouter/key         {key} → {configured: true}
DELETE /api/local-models/openrouter/key
GET    /api/projects/models/catalog             merged picker list with stage_timings_ms
```

Status shape: `ollama {state, version, pinned_version, free_disk_gb}`, `hardware {ram_gb, vram_gb|null}`, `catalog[] {…, pulled, fit, badge, badge_detail, active_job}`, `hosted {key_configured, catalog[]}`, `opencode {installed, path, version, pinned_version, ensure_state, ensure_error}`.

Job shape: `{id, kind: pull|ollama_install|probe, model_id, state: starting|downloading|verifying|success|error|cancelled, error, bytes_total, bytes_completed, percent, phase?}`.

## Appendix B: Terraceilia's equivalents today

```
POST /connect/refresh {provider}     re-probe one CLI
POST /connect/install {provider}     run vendor installer, stream output under the row
POST /connect/login {provider}       open a terminal with the vendor login command
POST /connect/key {provider, key}    env var for this session only
POST /connect/dismiss {provider}
```

Provider table: `backend/agents.py:12-55`. Probe table: `backend/connect.py:80-129`. Single call site: `backend/game.py:368` `Run._invoke`. Model pickers: `frontend/index.html:42-45` and `frontend/app.js:22-23, 121-123`. Stub provider for tests: `tests/stub_agent.py`, wired at `tests/test_generated_map.py:38-39`.
