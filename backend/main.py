"""Start Terraceilia. Run from anywhere: python backend/main.py"""
from __future__ import annotations
import argparse, secrets, shutil, socket, subprocess, sys, webbrowser
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from server import App, make_handler  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--port", type=int, default=8766); ap.add_argument("--local-only", action="store_true")
    a = ap.parse_args(); app = App()
    tf = ROOT / "token.txt"
    token = tf.read_text(encoding="utf-8").strip() if tf.exists() else secrets.token_urlsafe(6)
    if not tf.exists(): tf.write_text(token, encoding="utf-8")
    srv = ThreadingHTTPServer(("127.0.0.1" if a.local_only else "0.0.0.0", a.port), make_handler(app, token))
    url = f"http://127.0.0.1:{a.port}/?token={token}"; lan = ts = ""
    if not a.local_only:
        try:
            sck = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); sck.connect(("8.8.8.8", 80)); lan = sck.getsockname()[0]; sck.close()
        except Exception: lan = ""
        if shutil.which("tailscale"):
            try: ts = subprocess.run(["tailscale", "ip", "-4"], capture_output=True, text=True, timeout=5).stdout.strip().splitlines()[0]
            except Exception: ts = ""
    app.phone_url = f"http://{lan}:{a.port}/?token={token}" if lan else ""; app.away_url = f"http://{ts}:{a.port}/?token={token}" if ts else ""
    print(f"Terraceilia (desktop): {url}")
    if app.phone_url: print(f"Terraceilia (phone, home wifi): {app.phone_url}")
    if app.away_url: print(f"Terraceilia (phone, anywhere via Tailscale): {app.away_url}")
    webbrowser.open(url)
    try: srv.serve_forever()
    except KeyboardInterrupt: app.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
