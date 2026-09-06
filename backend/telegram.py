"""Telegram: the game can message you when the year ends, when someone dies, or when you ask for the phone link.

It goes through a bot you own and create in three steps, so no account details are ever shared with anyone.
The token is kept in telegram.json next to the game and is only ever sent to Telegram itself. It never
reaches the browser.
"""
from __future__ import annotations
import json, threading, urllib.error, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TG_FILE = ROOT / "telegram.json"
BLANK = {"token": "", "chat_id": "", "notify_on_finish": True, "notify_on_death": False, "bot": ""}


def config() -> dict:
    if not TG_FILE.exists():
        TG_FILE.write_text(json.dumps(BLANK, indent=1), encoding="utf-8"); return dict(BLANK)
    try:
        d = dict(BLANK); d.update(json.loads(TG_FILE.read_text(encoding="utf-8"))); return d
    except (OSError, json.JSONDecodeError): return dict(BLANK)


def _call(token: str, method: str, payload: dict | None = None) -> dict:
    """One Bot API call. Telegram answers a bad request with a json body that explains why, so return that
    instead of raising, and the wizard can show the reason."""
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/{method}",
                                 data=json.dumps(payload or {}).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r: return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try: return json.loads(e.read().decode())
        except (OSError, json.JSONDecodeError): return {"ok": False, "description": f"HTTP {e.code}"}


def state() -> dict:
    """What the Connections row needs to know. The token itself never leaves this process."""
    c = config(); tok = (c.get("token") or "").strip(); chat = str(c.get("chat_id") or "").strip()
    return {"ready": bool(tok and chat), "chat": chat, "bot": c.get("bot", ""),
            "notify_on_finish": bool(c.get("notify_on_finish", True)), "notify_on_death": bool(c.get("notify_on_death", False))}


def _token(given: str) -> str:
    return (given or "").strip() or (config().get("token") or "").strip()


def check(token: str) -> dict:
    """Step one: is this a real bot token? Ask Telegram for the bot's own name."""
    tok = _token(token)
    if not tok: return {"ok": False, "error": "Paste the token BotFather gave you first."}
    if ":" not in tok or len(tok) < 30:
        return {"ok": False, "error": "That does not look like a bot token. A token is some digits, a colon, then about thirty five letters and digits."}
    try: r = _call(tok, "getMe")
    except (OSError, ValueError) as exc: return {"ok": False, "error": f"Could not reach Telegram: {type(exc).__name__}"}
    if not r.get("ok"):
        return {"ok": False, "error": "Telegram rejected that token" + (f": {r.get('description')}" if r.get("description") else ".") + " Copy it again from BotFather; a missing character is the usual cause."}
    b = r.get("result", {})
    return {"ok": True, "bot": b.get("username", ""), "name": b.get("first_name", "")}


def find(token: str) -> dict:
    """Step two: who has messaged the bot? One call, no polling. If another program is already reading this
    bot Telegram answers with a conflict, and the wizard falls back to asking for the chat id by hand."""
    tok = _token(token)
    if not tok: return {"ok": False, "error": "Do step one first."}
    try: r = _call(tok, "getUpdates", {"timeout": 0, "limit": 100, "allowed_updates": ["message"]})
    except (OSError, ValueError) as exc: return {"ok": False, "error": f"Could not reach Telegram: {type(exc).__name__}"}
    if not r.get("ok"):
        d = r.get("description") or ""
        if "409" in d or "Conflict" in d or "terminated by other" in d or "webhook" in d.lower():
            return {"ok": False, "conflict": True, "error": "Another program is already reading this bot, so Terraceilia cannot look. Use the by hand way below."}
        return {"ok": False, "error": f"Telegram said: {d or 'unknown error'}"}
    chats: dict[str, dict] = {}
    for u in r.get("result", []):
        m = u.get("message") or u.get("edited_message") or {}
        c = m.get("chat") or {}
        if not c.get("id"): continue
        name = c.get("title") or " ".join(x for x in (c.get("first_name"), c.get("last_name")) if x) or c.get("username") or str(c["id"])
        k = str(c["id"])
        if k not in chats or len(name) > len(chats[k]["name"]): chats[k] = {"id": k, "name": name, "kind": c.get("type", "")}
    if not chats:
        return {"ok": False, "empty": True, "error": "Telegram has no messages for this bot yet. Open the chat with your bot, press Start, send it anything, then press Find my chat again."}
    return {"ok": True, "chats": list(chats.values())}


def test(token: str, chat_id: str) -> dict:
    tok = _token(token); chat = (chat_id or "").strip()
    if not tok: return {"ok": False, "error": "Do step one first."}
    if not chat: return {"ok": False, "error": "Terraceilia needs your chat id first; that is step two."}
    try:
        r = _call(tok, "sendMessage", {"chat_id": chat, "disable_web_page_preview": True,
                                       "text": "Terraceilia is connected. You will hear from the valley here."})
    except (OSError, ValueError) as exc: return {"ok": False, "error": f"Could not reach Telegram: {type(exc).__name__}"}
    if r.get("ok"): return {"ok": True}
    d = r.get("description") or "unknown error"
    hint = " Open the chat with your bot in Telegram and press Start first; a bot cannot message you until you do." if ("chat not found" in d.lower() or "blocked" in d.lower()) else ""
    return {"ok": False, "error": f"Telegram said: {d}.{hint}"}


def save(token: str, chat_id: str, notify_finish: bool = True, notify_death: bool = False, bot: str = "") -> dict:
    tok = _token(token); chat = (chat_id or "").strip()
    if not tok or not chat: return {"ok": False, "error": "A checked token and a chat id are both needed before saving."}
    c = config(); c.update({"token": tok, "chat_id": chat, "notify_on_finish": bool(notify_finish), "notify_on_death": bool(notify_death)})
    if bot: c["bot"] = bot
    TG_FILE.write_text(json.dumps(c, indent=1), encoding="utf-8")
    return {"ok": True}


def clear() -> dict:
    """Forget the bot and the chat. The bot itself still exists in Telegram; delete it with BotFather if you want."""
    TG_FILE.write_text(json.dumps(BLANK, indent=1), encoding="utf-8")
    return {"ok": True}


def send(text: str) -> str:
    """Send one message. Returns a line a person can read. The token is never logged."""
    c = config(); token = (c.get("token") or "").strip(); chat = str(c.get("chat_id") or "").strip()
    if not token or not chat: return "Telegram is not connected."
    try:
        r = _call(token, "sendMessage", {"chat_id": chat, "text": text[:3900], "disable_web_page_preview": True})
        return "Sent to Telegram." if r.get("ok") else f"Telegram refused: {r.get('description', 'unknown error')}"
    except (OSError, ValueError) as exc: return f"Telegram error: {type(exc).__name__}"


def notify(text: str, kind: str = "finish") -> None:
    """Fire and forget, from the engine's own thread, only if that kind of message is switched on."""
    c = config()
    if not (c.get("token") and c.get("chat_id")): return
    if kind == "finish" and not c.get("notify_on_finish", True): return
    if kind == "death" and not c.get("notify_on_death", False): return
    threading.Thread(target=send, args=(text,), daemon=True).start()
