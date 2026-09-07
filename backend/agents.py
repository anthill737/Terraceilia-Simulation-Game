"""Provider CLIs: how each agent process is launched, streamed, and identified."""
from __future__ import annotations
import json, os, re, shutil, subprocess, threading
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
        "models": ["gpt-6-astra", "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna", "gpt-5.4-mini", "gpt-5.3-codex-spark"],
    },
    "Codex": {
        "exe": "codex", "speech": "stdout", "pkg": "@openai/codex",
        "cmd": 'codex exec --skip-git-repo-check --model {model} --dangerously-bypass-approvals-and-sandbox "{ask}"',
        "resume": "",
        "ro_cmd": 'codex exec --skip-git-repo-check --model {model} --sandbox read-only "{ask}"',
        "models": ["gpt-6-astra", "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna", "gpt-5.4-mini", "gpt-5.3-codex-spark"],
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
    "GitHub Copilot CLI": {
        "exe": "copilot", "speech": "copilot", "pkg": "@github/copilot",
        "cmd": 'copilot -p "{ask}" --model {model} --allow-all-tools --no-color',
        "resume": "",
        "ro_cmd": 'copilot -p "{ask}" --model {model} --allow-tool read --no-color',
        "models": ["auto"],
    },
}


# ------------------------------------------------------------ copilot
_COPILOT_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|[\x00-\x08\x0b\x0c\x0e-\x1f]")
_COPILOT_FOOTER = re.compile(r"^(Changes|AI Credits|Tokens|Resume|Session|Total|Model)\b")


def clean_copilot(text: str) -> str:
    """Copilot prints the tools it used above its answer and a table of costs below it. Keep the answer."""
    lines = []
    for raw in _COPILOT_ANSI.sub("", text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        ln = raw.rstrip()
        if _COPILOT_FOOTER.match(ln.strip()): break
        s = ln.strip()
        if s.startswith(("\u25cf", "\u2514", "\u251c", "\u2502")): continue   # its tool use tree
        lines.append(ln)
    return "\n".join(lines).strip()



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
        if cfg.exists(): cfg.with_suffix(".toml.terraceilia-backup").write_text(text, encoding="utf-8")
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
