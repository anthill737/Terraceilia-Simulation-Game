"""Launching a provider CLI for one turn, and reading what came back without ever mistaking an error for a line.

A launch has two clocks: a wall clock that kills the process at TURN_TIMEOUT whatever it is printing, and a quiet clock that
kills it when nothing has arrived for NO_OUTPUT_TIMEOUT. What comes back is classified before anyone reads it as speech:
the exit code and the runner's own error lines come first, and only a clean exit with an answer is speech.

Error classes, and what the game does with each:
  auth      401, unauthorized, a revoked or unrefreshable token: the run pauses and asks for a sign in
  model     404, model not found, no access to the model: the seat is moved to the first model that answered the probe
  rate      429 and 5xx, overloaded, rate limited: wait with backoff and ask again
  launcher  credentials missing from the request itself: a bug in how the command was built; the run stops and shows the command
  timeout   killed by one of the two clocks
  other     anything else that was not an answer
"""
from __future__ import annotations
import json, os, re, subprocess, threading, time

TURN_TIMEOUT = 1800.0          # wall clock: the process dies at thirty minutes whatever it is doing
NO_OUTPUT_TIMEOUT = 300.0      # quiet clock: and at five minutes without a line
BACKOFF = (5.0, 15.0, 45.0)    # waits between tries after a rate limit or a server error

AUTH_RX = re.compile(r"\b401\b|unauthori[sz]ed|refresh token was revoked|could not be refreshed|invalid_grant|not logged in|login required|please (?:run )?(?:codex |claude )?(?:auth )?login|authentication (?:failed|required)|invalid (?:api )?key|token (?:has )?expired", re.I)
MODEL_RX = re.compile(r"\b404\b|model[^\n]{0,60}(?:not found|does not exist|unknown|not supported|unavailable|is not available|no access|not (?:permitted|allowed|enabled))|(?:no|not have|don't have|do not have) access to (?:the )?model|unknown model|invalid model|model_not_found|not_found_error|unsupported model", re.I)
RATE_RX = re.compile(r"\b429\b|\b5\d\d\b(?:\s|$|[^\d.])|rate.?limit|too many requests|overloaded|server error|service unavailable|bad gateway|gateway time.?out|temporarily unavailable|capacity|try again later|quota exceeded|resource.?exhausted", re.I)
LAUNCHER_RX = re.compile(r"missing bearer|no (?:api )?key (?:was )?(?:provided|found|set)|api key (?:is )?(?:missing|required|not set)|credentials? (?:are |is )?missing|missing credentials|no credentials|authorization header (?:is )?missing|must (?:provide|set) (?:an? )?(?:api key|token)", re.I)
ERROR_LINE_RX = re.compile(r"^\s*(?:\[?(?:error|fatal|panic)\]?\b|ERR!|✖|❌|error:)", re.I)


class Result:
    """What one launch left behind."""

    def __init__(self, cmd: str) -> None:
        self.cmd = cmd; self.rc: int | None = None; self.stdout: list[str] = []; self.stderr: list[str] = []
        self.speech: str | None = None; self.session_id: str | None = None; self.flagged = False
        self.timed_out = ""; self.kind = ""; self.message = ""; self.started = time.time(); self.ended = 0.0

    @property
    def ok(self) -> bool: return self.kind == ""


def classify(rc: int | None, err_text: str, out_text: str, flagged: bool, timed_out: str, has_answer: bool) -> tuple[str, str]:
    """(kind, message). Empty kind means a good answer. The runner's own message is kept, not paraphrased."""
    if timed_out: return "timeout", timed_out
    err_lines = [ln.strip() for ln in err_text.split("\n") if ln.strip()]
    out_err = [ln.strip() for ln in out_text.split("\n") if ERROR_LINE_RX.search(ln)]
    text = "\n".join(err_lines + out_err)
    failed = (rc not in (0, None)) or flagged or (not has_answer)
    if not failed and not text: return "", ""
    if not failed and text and not (AUTH_RX.search(text) or LAUNCHER_RX.search(text)): return "", ""    # a warning on stderr beside a real answer
    msg = next((ln for ln in err_lines + out_err if re.search(r"error|refused|revoked|denied|not found|unauthori|limit|missing|invalid|timed|unavailable", ln, re.I)), "") or (err_lines[-1] if err_lines else "") or (out_err[-1] if out_err else "") or f"ended without an answer (exit {rc})"
    msg = msg[:300]
    if LAUNCHER_RX.search(text): return "launcher", msg
    if AUTH_RX.search(text): return "auth", msg
    if MODEL_RX.search(text): return "model", msg
    if RATE_RX.search(text): return "rate", msg
    return "other", msg


def launch(cmd: str, cwd: str, speech_mode: str, on_out=None, on_err=None, procs: dict | None = None, key=None,
           wall: float | None = None, quiet: float | None = None, stop_flag: threading.Event | None = None) -> Result:
    """Run one command to the end or to one of the two clocks. Lines are handed to on_out and on_err as they arrive.
    For claude_stream the answer is the result event; otherwise stdout is the answer once the exit is clean."""
    from agents import render_claude_event
    wall = TURN_TIMEOUT if wall is None else wall; quiet = NO_OUTPUT_TIMEOUT if quiet is None else quiet
    r = Result(cmd); last = [time.time()]
    try:
        proc = subprocess.Popen(cmd, cwd=cwd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                encoding="utf-8", errors="replace", start_new_session=(os.name != "nt"))
    except (OSError, ValueError) as exc:
        r.rc = 127; r.kind, r.message = "launcher", f"could not start: {type(exc).__name__}: {exc}"; r.ended = time.time(); return r
    if procs is not None and key is not None: procs[key] = proc

    def pump_err() -> None:
        try:
            for ln in proc.stderr:
                ln = ln.rstrip("\n"); r.stderr.append(ln); del r.stderr[:-60]; last[0] = time.time()
                if on_err: on_err(ln)
        except (OSError, ValueError): pass

    def pump_out() -> None:
        try:
            for ln in proc.stdout:
                r.stdout.append(ln); last[0] = time.time()
                if speech_mode == "claude_stream":
                    try:
                        ev = json.loads(ln)
                        if ev.get("session_id"): r.session_id = ev["session_id"]
                        if ev.get("type") == "result" and (ev.get("is_error") or str(ev.get("subtype", "")).startswith("error")): r.flagged = True
                    except Exception: pass
                    shown, final = render_claude_event(ln)
                    if shown and on_out: on_out(shown)
                    if final is not None: r.speech = final
                elif on_out: on_out(ln.rstrip("\n"))
        except (OSError, ValueError): pass

    te = threading.Thread(target=pump_err, daemon=True); to = threading.Thread(target=pump_out, daemon=True); te.start(); to.start()
    while proc.poll() is None:
        now = time.time()
        if stop_flag is not None and stop_flag.is_set(): r.timed_out = "stopped"; _kill(proc); break
        if now - r.started > wall: r.timed_out = f"killed after {int(wall)} seconds on the wall clock"; _kill(proc); break
        if now - last[0] > quiet: r.timed_out = f"killed after {int(quiet)} seconds without a line of output"; _kill(proc); break
        time.sleep(0.2)
    te.join(timeout=5); to.join(timeout=5)
    r.rc = proc.poll(); r.ended = time.time()
    if speech_mode != "claude_stream": r.speech = "".join(r.stdout).strip() or None
    if r.timed_out == "stopped": r.kind, r.message = "other", "stopped"; r.speech = None; return r
    kind, msg = classify(r.rc, "\n".join(r.stderr), "".join(r.stdout), r.flagged, r.timed_out, bool(r.speech and r.speech.strip()))
    r.kind, r.message = kind, msg
    if kind: r.speech = None
    return r


def _kill(proc: subprocess.Popen) -> None:
    try:
        if os.name == "nt": subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, timeout=15)
        else: os.killpg(os.getpgid(proc.pid), 9)
    except Exception:
        try: proc.kill()
        except Exception: pass
