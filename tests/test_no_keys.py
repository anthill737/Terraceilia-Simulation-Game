"""Sign in is the only path. No tracked file may offer, name, or read an API key or a token field.

The forbidden words are the ones the removed feature was built from: the vendor environment variables
Terraceilia used to set for a child CLI, and the button that set them. A file that reintroduces any of
them fails here, whatever else it does.
Run from the repo root:  python -m pytest tests -q
"""
from __future__ import annotations
import os, subprocess, sys, time, unittest
from pathlib import Path

os.environ["TERRACEILIA_NO_TELEGRAM"] = "1"

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
import connect  # noqa: E402

# Every forbidden word, exactly as it would appear. Matched case sensitively: the lowercase word
# "token" is the browser's own access token and Telegram's bot token, neither of which is a model key.
FORBIDDEN = ("API_KEY", "AUTH_TOKEN", "GITHUB_TOKEN", "Use key")

# This file has to name what it forbids, so it excludes itself and nothing else.
SELF = Path(__file__).name


def tracked_files() -> list[Path]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, text=True, timeout=60)
    if out.returncode != 0: raise unittest.SkipTest("not a git checkout")
    return [ROOT / n for n in out.stdout.split("\0") if n]


class NoKeysAnywhere(unittest.TestCase):
    def test_no_tracked_file_names_a_key_or_a_token_field(self) -> None:
        hits: list[str] = []
        for f in tracked_files():
            if f.name == SELF or not f.is_file(): continue
            try: text = f.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError): continue        # screenshots and other binaries
            for i, line in enumerate(text.splitlines(), 1):
                for word in FORBIDDEN:
                    if word in line: hits.append(f"{f.relative_to(ROOT).as_posix()}:{i}: {word}: {line.strip()[:120]}")
        self.assertEqual(hits, [], "sign in is the only path; these lines bring a key or a token field back:\n" + "\n".join(hits))

    def test_no_provider_carries_a_key_field(self) -> None:
        for name, p in connect.PROVIDERS.items():
            for field in ("key_env", "key_env_alt"):
                self.assertNotIn(field, p, f"{name} still carries {field}")

    def test_there_is_no_route_or_function_that_sets_a_key(self) -> None:
        self.assertFalse(hasattr(connect, "set_key"), "connect.set_key is gone")
        self.assertFalse(hasattr(connect, "_key_in_env"), "connect._key_in_env is gone")
        self.assertNotIn("/connect/key", (ROOT / "backend" / "server.py").read_text(encoding="utf-8"))
        self.assertNotIn("keyin", (ROOT / "frontend" / "app.js").read_text(encoding="utf-8"))

    def test_a_key_in_the_environment_is_never_read(self) -> None:
        """A vendor key sitting in the environment changes nothing. A provider that is not installed stays
        not installed; it is never talked into Connected by a key, and the key never reaches a row."""
        vars_ = ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "COPILOT_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN")
        secret = "x" * 40
        for var in vars_: os.environ[var] = secret
        connect.PROVIDERS["Stub key"] = {"exe": "terraceilia-no-such-cli", "login": ["login"]}
        try:
            row = connect.probe("Stub key")
            self.assertEqual(row["state"], "not_installed")
            for field in ("by_key", "key_env", "key_set"): self.assertNotIn(field, row)
            self.assertNotIn(secret, repr(row))
            with connect._lock: connect._cache["Stub key"] = (time.monotonic(), row)
            shown = connect.state()["Stub key"]
            self.assertEqual(shown["state"], "not_installed")
            for field in ("by_key", "key_env", "key_set"): self.assertNotIn(field, shown)
            self.assertNotIn(secret, repr(shown))
        finally:
            connect.PROVIDERS.pop("Stub key", None)
            with connect._lock: connect._cache.pop("Stub key", None)
            for var in vars_: os.environ.pop(var, None)


if __name__ == "__main__":
    unittest.main()
