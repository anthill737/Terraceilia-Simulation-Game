"""Connections: is each agent CLI installed, and is it signed in.

Nothing here invents an authentication flow. Every provider is asked the way its own makers documented:
its own status command where it has one, and the credential file it writes where it does not. Signing in
opens a real terminal window with the provider's own login command already running, which is what these
CLIs are built for. The browser opens from there. This app then asks the CLI every fifteen seconds
whether it is signed in yet, for ten minutes, and turns the row green by itself. Installing runs the
provider's own installer and streams its output. A CLI that is already installed is never touched.
Signing in is the only path. Terraceilia never reads, sets, or asks for an API key or a token.
"""
from __future__ import annotations
import json, os, re, shutil, subprocess, sys, threading, time
from pathlib import Path

IS_WINDOWS = os.name == "nt"
IS_MACOS = sys.platform == "darwin"
HOME = Path.home()
TTL = 60.0                      # a probe is trusted for a minute, and any action clears it at once
PROBE_TIMEOUT = 20.0
LOGIN_POLL = 5.0                # while a sign in is open, ask the CLI this often whether it worked
LOGIN_WAIT = 600.0              # and keep asking for this long


# ---------------------------------------------------------------- finding a CLI that was installed after we started
def _user_bin_dirs() -> list[str]:
    """Where the official installers put things. Recomputed on every call, so a CLI installed while
    Terraceilia is running is found without a restart."""
    c = [HOME / ".local" / "bin", HOME / "bin", HOME / ".codex" / "bin"]
    if IS_WINDOWS:
        ad = Path(os.environ.get("APPDATA", HOME / "AppData" / "Roaming"))
        la = Path(os.environ.get("LOCALAPPDATA", HOME / "AppData" / "Local"))
        c += [ad / "npm", la / "Programs" / "OpenAI" / "Codex" / "bin", la / "GitHub CLI" / "copilot",
              la / "Programs" / "nodejs", Path("C:/Program Files/nodejs"), Path("C:/Program Files/GitHub CLI")]
    else:
        c += [Path("/opt/homebrew/bin"), Path("/usr/local/bin"), HOME / ".npm-global" / "bin",
              HOME / ".bun" / "bin", Path("/usr/local/opt/node/bin")]
    return [str(d) for d in c if d.is_dir()]


def augmented_path() -> str:
    extra = _user_bin_dirs(); cur = os.environ.get("PATH", "")
    return os.pathsep.join(extra + ([cur] if cur else [])) if extra else cur


def which(exe: str) -> str | None:
    return shutil.which(exe, path=augmented_path())


def child_env() -> dict:
    """The environment a CLI is launched with: our PATH plus the installer folders, and no marker that
    would make a CLI believe it is nested inside another agent session and refuse to start."""
    env = {**os.environ, "PATH": augmented_path()}
    for k in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT"): env.pop(k, None)
    return env


def _argv(path: str, *rest: str) -> list[str]:
    """Windows cannot execute a .cmd or .bat shim directly; route those through the command processor."""
    if IS_WINDOWS and path.lower().endswith((".cmd", ".bat")): return ["cmd", "/c", path, *rest]
    return [path, *rest]


def run(argv: list[str], timeout: float = PROBE_TIMEOUT) -> tuple[int, str]:
    """One short command. Returns its exit code, and its output and errors together."""
    try:
        r = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=timeout, env=child_env(),
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if IS_WINDOWS else 0)
        return r.returncode, ((r.stdout or "") + ("\n" + r.stderr if r.stderr else "")).strip()
    except subprocess.TimeoutExpired: return 124, "timed out"
    except (OSError, ValueError) as exc: return 127, f"{type(exc).__name__}: {exc}"


# ---------------------------------------------------------------- what each provider is, and how it answers
# status_cmd     the provider's own way of saying whether it is signed in
# status_json_key  read that command's json and believe this key
# status_ok      otherwise the command must exit 0 and its output must match this
# files          the credential the provider writes; used where there is no status command, and as a fallback
PROVIDERS: dict[str, dict] = {
    "Claude Code": {
        "exe": "claude", "docs": "https://docs.claude.com/en/docs/claude-code",
        "login": ["auth", "login"], "logout_hint": "claude auth logout",
        "status_cmd": ["auth", "status"], "status_json_key": "loggedIn",
        "files": [HOME / ".claude" / ".credentials.json"], "keychain": "Claude Code-credentials",
        "install_win": ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", "irm https://claude.ai/install.ps1 | iex"],
        "install_mac": ["bash", "-c", "curl -fsSL https://claude.ai/install.sh | bash"],
    },
    "Codex": {
        "exe": "codex", "docs": "https://developers.openai.com/codex",
        "login": ["login"], "logout_hint": "codex logout",
        "status_cmd": ["login", "status"], "status_ok": r"logged in",
        "files": [HOME / ".codex" / "auth.json"], "subscription_only": True,
        "install_win": ["npm", "install", "-g", "@openai/codex"],
        "install_mac": ["bash", "-c", "curl -fsSL https://chatgpt.com/codex/install.sh | sh"],
    },
    "Gemini CLI": {
        "exe": "gemini", "docs": "https://github.com/google-gemini/gemini-cli",
        "login": [],   # Gemini has no login subcommand; the CLI itself asks on first run
        "login_note": "Gemini CLI has no sign in command of its own. The terminal opens the CLI, which asks how you want to authenticate; choose Login with Google.",
        "files": [HOME / ".gemini" / "oauth_creds.json"],
        "install_win": ["npm", "install", "-g", "@google/gemini-cli"],
        "install_mac": ["npm", "install", "-g", "@google/gemini-cli"],
    },
    "OpenCode": {
        "exe": "opencode", "docs": "https://opencode.ai/docs",
        "login": ["auth", "login"], "logout_hint": "opencode auth logout",
        "status_cmd": ["auth", "list"], "status_ok": r"(anthropic|openai|google|zai|ollama|github|opencode|azure|bedrock)",
        "files": [HOME / ".local" / "share" / "opencode" / "auth.json"],
        "install_win": ["npm", "install", "-g", "opencode-ai"],
        "install_mac": ["bash", "-c", "curl -fsSL https://opencode.ai/install | bash"],
    },
    "GitHub Copilot CLI": {
        "exe": "copilot", "docs": "https://docs.github.com/en/copilot/how-tos/copilot-cli",
        "login": ["login"], "logout_hint": "/logout inside copilot",
        "files": [HOME / ".copilot" / "config.json"],
        "needs_node": 22,
        "install_win": ["npm", "install", "-g", "@github/copilot"],
        "install_mac": ["npm", "install", "-g", "@github/copilot"],
    },
}


def install_argv(name: str) -> list[str] | None:
    p = PROVIDERS.get(name) or {}
    a = p.get("install_win") if IS_WINDOWS else p.get("install_mac")
    return list(a) if a else None


def install_text(name: str) -> str:
    a = install_argv(name)
    if not a: return ""
    return a[-1] if a[0] in ("bash", "sh", "powershell") else " ".join(a)


def login_argv(name: str) -> list[str] | None:
    """The provider's own documented login command, resolved to a real executable."""
    p = PROVIDERS.get(name) or {}
    if p.get("login_argv"):
        exe = which(p["login_argv"][0])
        return _argv(exe, *p["login_argv"][1:]) if exe else None
    if p.get("login") is None: return None
    exe = which(p["exe"])
    return _argv(exe, *p["login"]) if exe else None


def login_text(name: str) -> str:
    """The command as a person would type it, for the row and for the copy button."""
    p = PROVIDERS.get(name) or {}
    if p.get("login_argv"): return " ".join(p["login_argv"])
    if p.get("login") is None: return ""
    return " ".join([p["exe"]] + list(p["login"]))


def _status_argv(name: str) -> list[str] | None:
    p = PROVIDERS.get(name) or {}
    if p.get("status_cmd_argv"):
        exe = which(p["status_cmd_argv"][0])
        return _argv(exe, *p["status_cmd_argv"][1:]) if exe else None
    if not p.get("status_cmd"): return None
    exe = which(p["exe"])
    return _argv(exe, *p["status_cmd"]) if exe else None


# ---------------------------------------------------------------- probing
def _node_major() -> int:
    exe = which("node")
    if not exe: return 0
    rc, out = run(_argv(exe, "--version"), timeout=15)
    m = re.search(r"v?(\d+)\.", out or "")
    return int(m.group(1)) if rc == 0 and m else 0


def _keychain_has(service: str) -> bool:
    if not IS_MACOS: return False
    rc, _ = run(["/usr/bin/security", "find-generic-password", "-s", service], timeout=8)
    return rc == 0


def probe(name: str) -> dict:
    """One provider's truth right now: installed, its version, and whether it is signed in."""
    p = PROVIDERS.get(name)
    if not p: return {"state": "error", "detail": "unknown provider"}
    exe_path = which(p["exe"])
    out: dict = {"name": name, "exe": p["exe"], "installed": bool(exe_path), "path": exe_path or "", "version": "",
                 "docs": p.get("docs", ""), "install_text": install_text(name),
                 "login_text": login_text(name), "login_note": p.get("login_note", ""), "logout_hint": p.get("logout_hint", ""),
                 "can_login": p.get("login") is not None or bool(p.get("login_argv")),
                 "can_install": bool(install_argv(name)), "node_missing": False}
    if not out["installed"]:
        out["state"] = "not_installed"
        npm = which("npm")
        out["node_missing"] = not npm
        out["detail"] = f"{p['exe']} is not installed." + ("" if npm else " Node.js is needed to install it.")
        return out
    if p.get("version_argv"):
        vexe = which(p["version_argv"][0]); rc, v = run(_argv(vexe, *p["version_argv"][1:]), timeout=90) if vexe else (1, "")
    else:
        rc, v = run(_argv(exe_path, "--version"), timeout=25)
    if rc == 0 and v:      # the first line that carries a version, not an update notice underneath it
        out["version"] = next((ln.strip() for ln in v.splitlines() if re.search(r"\d+\.\d+", ln)), v.splitlines()[0].strip())[:60]
    if p.get("needs_node"):
        nv = _node_major()
        if nv and nv < p["needs_node"]:
            out["state"] = "not_signed_in"; out["detail"] = f"Node.js {nv} is too old. This CLI needs {p['needs_node']} or newer."
            return out
    sargv = _status_argv(name)
    if sargv:
        rc, o = run(sargv, timeout=PROBE_TIMEOUT)
        if p.get("status_json_key"):
            m = re.search(r"\{.*\}", o or "", re.S)
            if m:
                try:
                    d = json.loads(m.group(0))
                    if d.get(p["status_json_key"]):
                        who = d.get("email") or d.get("account") or ""
                        sub = d.get("subscriptionType") or ""
                        out["state"] = "connected"
                        out["detail"] = "Signed in" + (f" as {who}" if who else "") + (f" on {sub}" if sub else "")
                        return out
                    out["state"] = "not_signed_in"; out["detail"] = "Not signed in."
                    return out
                except (json.JSONDecodeError, TypeError): pass
        elif rc == 0 and o.strip() and re.search(p.get("status_ok", "."), o, re.I):
            out["state"] = "connected"; out["detail"] = o.splitlines()[0][:120]
            return out
        elif rc != 0 and o.strip() and re.search(r"not logged in|no account|logged out|not authenticated", o, re.I):
            out["state"] = "not_signed_in"; out["detail"] = o.splitlines()[0][:120]
            return out
    for f in p.get("files", []):        # the credential the provider writes, for CLIs with no status command
        try:
            if f.is_file() and f.stat().st_size > 2:
                out["state"] = "connected"; out["detail"] = f"Signed in, by {f.name} on disk."
                return out
        except OSError: pass
    if p.get("keychain") and _keychain_has(p["keychain"]):
        out["state"] = "connected"; out["detail"] = "Signed in, by the macOS keychain."
        return out
    out["state"] = "not_signed_in"
    out["detail"] = "Installed, but not signed in."
    return out


# ---------------------------------------------------------------- probes: one real request through the launcher a turn uses
# A row is Connected only when a model of that provider has answered a real request, and it says when.
_probes: dict[str, dict[str, dict]] = {}      # provider -> model -> {"ok", "when", "message"}
_probe_lock = threading.Lock()


def record_probe(provider: str, model: str, ok: bool, message: str = "") -> None:
    with _probe_lock:
        _probes.setdefault(provider, {})[model or ""] = {"ok": bool(ok), "when": time.time(), "message": (message or "")[:200]}


def probes_of(provider: str) -> dict[str, dict]:
    with _probe_lock: return {m: dict(r) for m, r in _probes.get(provider, {}).items()}


def first_accessible(provider: str, exclude: str = "") -> str | None:
    """The first of the provider's models, in its own listed order, that answered a probe. None if none has."""
    from agents import PROVIDERS as AGENT_PROVIDERS
    with _probe_lock: rows = _probes.get(provider, {})
    order = list(AGENT_PROVIDERS.get(provider, {}).get("models", [])) + [m for m in rows if m not in AGENT_PROVIDERS.get(provider, {}).get("models", [])]
    for m in order:
        if m and m != exclude and rows.get(m, {}).get("ok"): return m
    return None


def last_good_probe(provider: str) -> dict | None:
    rows = probes_of(provider); good = [(r["when"], m, r) for m, r in rows.items() if r.get("ok")]
    if not good: return None
    when, m, r = max(good); return {"model": m, "when": when}


# ---------------------------------------------------------------- the cache, kept warm from launch
_cache: dict[str, tuple[float, dict]] = {}
_inflight: set[str] = set()
_lock = threading.Lock()
_jobs: dict[str, dict] = {}          # provider -> what its Install or Sign in is doing


def _probe_into_cache(name: str) -> None:
    try: r = probe(name)
    except Exception as exc:  # noqa: BLE001
        r = {"name": name, "state": "error", "detail": f"{type(exc).__name__}: {exc}", "installed": False, "exe": PROVIDERS.get(name, {}).get("exe", "")}
    with _lock: _cache[name] = (time.monotonic(), r); _inflight.discard(name)


def refresh(name: str | None = None, force: bool = False) -> None:
    """Ask again, in the background. The rows keep showing what they had until the answer lands."""
    for n in ([name] if name else list(PROVIDERS)):
        with _lock:
            hit = _cache.get(n)
            if n in _inflight: continue
            if hit and not force and time.monotonic() - hit[0] < TTL: continue
            _inflight.add(n)
        threading.Thread(target=_probe_into_cache, args=(n,), daemon=True).start()


def invalidate(name: str | None = None) -> None:
    with _lock:
        if name: _cache.pop(name, None)
        else: _cache.clear()
    refresh(name, force=True)


def state() -> dict:
    """What the Connections rows show. A provider not yet tested is Checking, never red."""
    out = {}
    with _lock:
        for n, p in PROVIDERS.items():
            hit = _cache.get(n)
            row = dict(hit[1]) if hit else {"name": n, "state": "checking", "detail": "Checking...", "installed": False,
                                            "exe": p["exe"], "docs": p.get("docs", ""), "version": "",
                                            "install_text": install_text(n), "login_text": login_text(n),
                                            "can_login": True, "can_install": bool(install_argv(n))}
            j = _jobs.get(n)
            if j: row["job"] = {"kind": j["kind"], "lines": j["lines"][-14:], "done": j["done"], "ok": j["ok"],
                                "note": j.get("note", ""), "waited": j.get("waited", 0)}
            # Connected means a model answered a real request; a status command alone is only Signed in, not tested
            good = last_good_probe(n); row["probes"] = probes_of(n); row["shares"] = p.get("shares", "")
            if row["state"] == "connected":
                if good:
                    row["probe_model"] = good["model"]; row["probe_time"] = time.strftime("%H:%M", time.localtime(good["when"]))
                    row["detail"] = f"{good['model']} answered at {row['probe_time']}." + (" " + row["detail"] if row.get("detail") else "")
                else:
                    row["state"] = "signed_in"; row["detail"] = "Signed in, by its own status. No model has answered a test yet; press Test, or Start tests every seat."
            out[n] = row
    return out


def connected(name: str) -> bool:
    with _lock: hit = _cache.get(name)
    return bool(hit and hit[1].get("state") == "connected")


def status_of(name: str) -> str:
    with _lock: hit = _cache.get(name)
    return hit[1].get("state", "checking") if hit else "checking"


# ---------------------------------------------------------------- jobs: what a row is doing right now
_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[=>]|[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _clean(s: str) -> str:
    return _ANSI.sub("", s).replace("\r\n", "\n").replace("\r", "\n")


def job(name: str) -> dict | None:
    with _lock: return _jobs.get(name)


def clear_job(name: str) -> None:
    with _lock: _jobs.pop(name, None)


def begin_test(name: str) -> dict:
    """A test is never silent. From the moment it starts the row carries a job, so the spinner and the
    live line are there whether the convener pressed Test or Start did it for them."""
    return _new_job(name, "test")


def test_line(name: str, text: str) -> None:
    """One more line under the row, as it happens."""
    j = job(name)
    if j and not j["done"]: _say(j, text)


def end_test(name: str, ok: bool) -> None:
    j = job(name)
    if j: j["ok"] = bool(ok); j["done"] = True


def testing(name: str) -> bool:
    j = job(name)
    return bool(j and j["kind"] == "test" and not j["done"])


def _new_job(name: str, kind: str) -> dict:
    j = {"kind": kind, "lines": [], "done": False, "ok": False, "started": time.time(), "note": "", "waited": 0}
    with _lock: _jobs[name] = j
    return j


def _say(j: dict, text: str) -> None:
    for ln in _clean(text).split("\n"):
        ln = ln.rstrip()
        if ln: j["lines"].append(ln[:300]); del j["lines"][:-200]


def _stream(j: dict, argv: list[str], timeout: float) -> int:
    """Run a command with pipes and relay every line under the row. Used by Install."""
    try:
        p = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                             errors="replace", env=child_env(), bufsize=1,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if IS_WINDOWS else 0)
    except (OSError, ValueError) as exc:
        _say(j, f"could not start: {type(exc).__name__}: {exc}"); return 127
    def reap() -> None:
        try:
            for ln in p.stdout: _say(j, ln)
        except (OSError, ValueError): pass
    t = threading.Thread(target=reap, daemon=True); t.start()
    try: rc = p.wait(timeout=timeout)
    except subprocess.TimeoutExpired: p.kill(); _say(j, "[gave up waiting]"); rc = 124
    t.join(timeout=5); return rc


# ---------------------------------------------------------------- a real terminal, which is what these CLIs are built for
LINUX_TERMINALS = ["x-terminal-emulator", "gnome-terminal", "konsole", "xfce4-terminal", "alacritty", "kitty", "xterm"]


def _sh_quote(a: str) -> str:
    return a if re.fullmatch(r"[\w@%+=:,./-]+", a or "") else "'" + (a or "").replace("'", "'\\''") + "'"


def open_terminal(argv: list[str]) -> tuple[bool, str]:
    """Open a terminal window with the login command already running in it. The CLI opens the browser
    itself, prints its own URL or device code, and takes any typing it needs, all where the user can see."""
    line = subprocess.list2cmdline(argv) if IS_WINDOWS else " ".join(_sh_quote(a) for a in argv)
    opened_msg = "A terminal window has opened with the sign in running. Finish there and this row turns green on its own."
    try:
        if IS_WINDOWS:
            subprocess.Popen(["cmd", "/c", "start", "Terraceilia sign in", "cmd", "/k", line], env=child_env())
            return True, opened_msg
        if IS_MACOS:
            script = line.replace("\\", "\\\\").replace('"', '\\"')
            subprocess.Popen(["osascript", "-e", f'tell application "Terminal" to do script "{script}"',
                              "-e", 'tell application "Terminal" to activate'], env=child_env())
            return True, opened_msg
        for term in LINUX_TERMINALS:
            if which(term):
                subprocess.Popen([term, "-e", *argv], env=child_env())
                return True, opened_msg
        return False, f"No terminal program was found. Run this in a terminal yourself: {line}"
    except (OSError, ValueError) as exc:
        return False, f"A terminal window would not open ({type(exc).__name__}). Run this in a terminal yourself: {line}"


# ---------------------------------------------------------------- the three things a row can do
def start_install(name: str) -> str:
    p = PROVIDERS.get(name)
    if not p: return "unknown provider"
    with _lock:
        if name in _jobs and not _jobs[name]["done"]: return "Already running."
    if which(p["exe"]): return "Already installed. Terraceilia never reinstalls a CLI you already have."
    argv = install_argv(name)
    if not argv: return "No installer is known for this one."
    if argv[0] == "npm" and not which("npm"):
        return "Node.js is not installed, and npm comes with it. Install Node.js from https://nodejs.org and press Install again."
    exe = which(argv[0])
    if not exe: return f"{argv[0]} was not found."
    j = _new_job(name, "install")
    def work() -> None:
        _say(j, "$ " + install_text(name))
        rc = _stream(j, _argv(exe, *argv[1:]), timeout=900)
        j["ok"] = rc == 0 and bool(which(p["exe"]))
        _say(j, "installed." if j["ok"] else f"[the installer finished with exit {rc}]")
        j["done"] = True; invalidate(name)
    threading.Thread(target=work, daemon=True).start()
    return "Installing..."


def start_login(name: str) -> str:
    p = PROVIDERS.get(name)
    if not p: return "unknown provider"
    with _lock:
        if name in _jobs and not _jobs[name]["done"]: return "Already running."
    argv = login_argv(name)
    if not argv: return f"{name} is not installed yet, so there is nothing to sign in to."
    j = _new_job(name, "login")
    def work() -> None:
        _say(j, "$ " + login_text(name))
        opened, note = open_terminal(argv)
        j["note"] = (p.get("login_note", "") + " " + note).strip()
        _say(j, note)
        if not opened: j["done"] = True; return
        deadline = time.time() + LOGIN_WAIT      # ten minutes of asking the CLI whether it is signed in yet
        while time.time() < deadline:
            time.sleep(LOGIN_POLL)
            invalidate(name); time.sleep(2.5)    # let the fresh answer land before reading it
            j["waited"] = int(time.time() - j["started"])
            if connected(name): j["ok"] = True; break
        _say(j, "Signed in." if j["ok"] else "[Still not signed in. Press Sign in again once you have finished in the terminal.]")
        j["done"] = True; invalidate(name)
    threading.Thread(target=work, daemon=True).start()
    return "A terminal window is opening..."


def start() -> None:
    """Check everything at launch, so the rows are already coloured the first time Settings is opened."""
    refresh(force=True)
