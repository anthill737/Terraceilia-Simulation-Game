"""Provider CLIs: how each agent process is launched, streamed, and identified."""
from __future__ import annotations
import json, os, shutil, subprocess, threading
from pathlib import Path

ASK = "Read the file {prompt_file} and respond exactly as it instructs. Your final message is your reply."

# Provider definitions. Never shown in the UI.
#   cmd: {ask} and {model} are filled in.
#   speech: how the finished speech is extracted from the run.
#     "claude_stream" parses Claude's stream-json events; "stdout" uses stdout only.
PROVIDERS = {
    "Claude Code": {
        "exe": "claude", "speech": "claude_stream", "pkg": "@anthropic-ai/claude-code",
        "cmd": 'claude -p "{ask}" --model {model} --verbose --output-format stream-json --dangerously-skip-permissions',
        "resume": " --resume {sid}",
        "ro_cmd": 'claude -p "{ask}" --model {model} --verbose --output-format stream-json --allowedTools "Read,Grep,Glob,Bash(git log:*),Bash(git show:*),Bash(git diff:*),Bash(git status:*),Bash(git blame:*),Bash(ls:*),Bash(cat:*),Bash(rg:*),Bash(find:*),Bash(wc:*),Bash(head:*),Bash(tail:*)"',
        "models": ["claude-fable-5-1", "claude-fable-5", "claude-opus-5", "claude-opus-4-8", "claude-sonnet-5", "claude-haiku-4-5", "claude-haiku-4"],
    },
    "Codex (latest)": {
        "exe": "npx", "speech": "stdout", "pkg": "@openai/codex", "isolated": True,
        "cmd": 'npx -y @openai/codex@latest exec --skip-git-repo-check --model {model} --dangerously-bypass-approvals-and-sandbox "{ask}"',
        "ro_cmd": 'npx -y @openai/codex@latest exec --skip-git-repo-check --model {model} --sandbox read-only "{ask}"',
        "resume": "",
        "models": ["gpt-5.4-mini", "gpt-5.5", "gpt-6-astra", "gpt-6-astra-pro", "gpt-5.6", "gpt-5.5-mini", "gpt-5-codex-mini"],
    },
    "Codex": {
        "exe": "codex", "speech": "stdout", "pkg": "@openai/codex",
        "cmd": 'codex exec --skip-git-repo-check --model {model} --dangerously-bypass-approvals-and-sandbox "{ask}"',
        "resume": "",
        "ro_cmd": 'codex exec --skip-git-repo-check --model {model} --sandbox read-only "{ask}"',
        "models": ["gpt-5.4-mini", "gpt-5.5", "gpt-6-astra", "gpt-6-astra-pro", "gpt-5.6", "gpt-5.5-mini", "gpt-5-codex-mini"],
    },
    "OpenCode": {
        "exe": "opencode", "speech": "stdout", "pkg": "opencode-ai",
        "cmd": 'opencode run --model {model} "{ask}"',
        "resume": "",
        "ro_cmd": 'opencode run --model {model} "{ask}"',
        "models": ["zai/glm-5.2", "openai/gpt-6-astra", "openai/gpt-5.6", "anthropic/claude-fable-5-1", "anthropic/claude-opus-5", "google/gemini-3-pro", "ollama/qwen3"],
    },
    "Gemini CLI": {
        "exe": "gemini", "speech": "stdout", "pkg": "@google/gemini-cli",
        "cmd": 'gemini -p "{ask}" -m {model} --yolo',
        "resume": "",
        "ro_cmd": 'gemini -p "{ask}" -m {model}',
        "models": ["gemini-3-pro", "gemini-3-flash", "gemini-3-flash-lite"],
    },
}



# ------------------------------------------------------------ claude stream
def render_claude_event(line: str) -> tuple[str | None, str | None]:
    """Turn one stream-json line into (terminal text, final speech or None)."""
    try:
        ev = json.loads(line)
    except json.JSONDecodeError:
        return line.rstrip("\n"), None
    t = ev.get("type")
    if t == "assistant":
        out = []
        for block in ev.get("message", {}).get("content", []):
            if block.get("type") == "text" and block.get("text"):
                out.append(block["text"])
            elif block.get("type") == "tool_use":
                inp = block.get("input", {})
                brief = inp.get("file_path") or inp.get("command") or inp.get("pattern") or inp.get("path") or ""
                out.append(f"  > {block.get('name')} {str(brief)[:120]}")
        return "\n".join(out) if out else None, None
    if t == "user":
        for block in ev.get("message", {}).get("content", []):
            if block.get("type") == "tool_result":
                c = block.get("content")
                text = c if isinstance(c, str) else " ".join(x.get("text", "") for x in c or [] if isinstance(x, dict))
                text = " ".join(str(text).split())
                return f"    < {text[:160]}", None
        return None, None
    if t == "result":
        return "\n[done]", ev.get("result") or ""
    if t == "system":
        # Claude emits many system events per turn; show only the one that names the model
        if not ev.get("model"): return None, None
        return f"[session {ev.get('model')}]", None
    return None, None



# ---------------------------------------------------------------- codex trust
def ensure_codex_trust(folder: str) -> str | None:
    """Codex's non-interactive mode refuses folders not marked trusted in ~/.codex/config.toml.
    Add the entry if missing. Returns a note if something was changed, else None."""
    try:
        cfg = Path.home() / ".codex" / "config.toml"
        cfg.parent.mkdir(exist_ok=True)
        text = cfg.read_text(encoding="utf-8") if cfg.exists() else ""
        key = str(Path(folder).resolve())
        variants = {key, key.replace("\\", "/"), key.replace("\\", "\\\\")}
        if any(f'[projects."{v}"]' in text or f"[projects.'{v}']" in text for v in variants): return None
        if cfg.exists(): cfg.with_suffix(".toml.agora-backup").write_text(text, encoding="utf-8")
        esc = key.replace("\\", "\\\\")
        with cfg.open("a", encoding="utf-8") as fh:
            fh.write(f'\n[projects."{esc}"]\ntrust_level = "trusted"\n')
        return f"Marked {key} as trusted for Codex in {cfg} (backup saved alongside)."
    except Exception as exc:  # noqa: BLE001
        return f"Could not update Codex trust config: {type(exc).__name__}"


# ---------------------------------------------------------------- versions
VERSIONS: dict[str, dict] = {}     # provider -> {"installed": str, "latest": str}
_ver_lock = threading.Lock()


def _ver_of(cmd: list[str]) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=25, shell=(os.name == "nt"))
        out = (r.stdout or r.stderr or "").strip().splitlines()
        return out[-1].strip() if out else ""
    except Exception: return ""


def refresh_versions() -> None:
    """Installed versions now, latest from npm in the background. Never blocks the UI."""
    def work() -> None:
        for name, prov in PROVIDERS.items():
            if prov.get("isolated"): continue
            inst = _ver_of([prov["exe"], "--version"]) if shutil.which(prov["exe"]) else ""
            with _ver_lock: VERSIONS.setdefault(name, {})["installed"] = inst
        for name, prov in PROVIDERS.items():
            if prov.get("isolated") or not prov.get("pkg") or not shutil.which("npm"): continue
            latest = _ver_of(["npm", "view", prov["pkg"], "version"])
            with _ver_lock: VERSIONS.setdefault(name, {})["latest"] = latest
    threading.Thread(target=work, daemon=True).start()





# ---------------------------------------------------------------- connecting a CLI
HINTS = {
    "Claude Code": {"install_mac": "curl -fsSL https://claude.ai/install.sh | bash", "install_win": "irm https://claude.ai/install.ps1 | iex",
                    "login": "claude   (then follow the sign-in prompt; use /login inside it if needed)", "docs": "https://docs.claude.com/en/docs/claude-code"},
    "Codex (latest)": {"install_mac": "npm install -g @openai/codex   (or nothing: Terraceilia runs the newest release through npx)", "install_win": "npm install -g @openai/codex   (or nothing: runs through npx)",
                       "login": "npx -y @openai/codex@latest login", "docs": "https://developers.openai.com/codex"},
    "Codex": {"install_mac": "npm install -g @openai/codex", "install_win": "npm install -g @openai/codex", "login": "codex login", "docs": "https://developers.openai.com/codex"},
    "OpenCode": {"install_mac": "curl -fsSL https://opencode.ai/install | bash", "install_win": "npm install -g opencode-ai", "login": "opencode auth login", "docs": "https://opencode.ai/docs"},
    "Gemini CLI": {"install_mac": "npm install -g @google/gemini-cli", "install_win": "npm install -g @google/gemini-cli", "login": "gemini   (choose Login with Google on first run)", "docs": "https://github.com/google-gemini/gemini-cli"},
}


def test_provider(name: str, model: str, folder: str) -> dict:
    """Run a one-line prompt through the CLI exactly the way the game does. Returns ok, seconds, and what came back."""
    import tempfile, time as _t
    prov = PROVIDERS.get(name)
    if not prov: return {"ok": False, "detail": "unknown provider"}
    if shutil.which(prov["exe"]) is None: return {"ok": False, "detail": f"'{prov['exe']}' is not on PATH. Install it, then restart Terraceilia so it sees the new PATH."}
    # The prompt file lives inside the folder the CLI runs in, as in a real turn: a sandboxed CLI (Codex) cannot always read outside it.
    run = Path(folder) if Path(folder).is_dir() else Path(tempfile.mkdtemp(prefix="terra-test-")); pf = run / f"terraceilia-connection-test-{os.getpid()}.md"
    pf.write_text("Reply with exactly the single word: ready", encoding="utf-8")
    cmd = prov["ro_cmd"].format(ask=ASK.format(prompt_file=pf), model=model or prov["models"][0])
    t0 = _t.time()
    try:
        r = subprocess.run(cmd, cwd=str(run), shell=True, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=240)
    except subprocess.TimeoutExpired:
        return {"ok": False, "seconds": round(_t.time() - t0, 1), "detail": "no reply within 4 minutes; the CLI is probably waiting for a login prompt. Run its login command in a terminal first."}
    finally:
        try: pf.unlink()
        except OSError: pass
    out = (r.stdout or ""); err = (r.stderr or "").strip()
    final = None
    if prov["speech"] == "claude_stream":
        for ln in out.splitlines():
            try:
                ev = json.loads(ln)
                if ev.get("type") == "result": final = ev.get("result", "")
            except Exception: pass
    else: final = out.strip()
    ok = r.returncode == 0 and bool(final) and "ready" in (final or "").lower()
    detail = (final or "").strip()[:300] or err[-400:] or f"exit {r.returncode}, no output"
    if not ok and err: detail = (detail + "\n" + err[-400:]).strip()
    if not ok and "not supported when using Codex with a ChatGPT account" in (out + err):
        detail += "\nA ChatGPT sign-in accepts only some models (gpt-5.4-mini and gpt-5.5 at the time of writing). Pick one of those for this provider."
    return {"ok": ok, "seconds": round(_t.time() - t0, 1), "detail": detail, "exit": r.returncode}
