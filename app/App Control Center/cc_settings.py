"""Shared settings for the Control Center (read from settings.json)."""
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
# app root = nearest parent folder that has app/main.py (so the folder can be copied into any app)
BASE = next((p for p in HERE.parents if (p / "app" / "main.py").exists()), HERE.parents[1])
# settings.json allows whole-line // comments
S = json.loads(re.sub(r"(?m)^\s*//.*$", "", (HERE / "settings.json").read_text(encoding="utf-8")))


def command(key: str) -> list[str]:
    sub = {"{python}": sys.executable, "{host}": S["host"], "{port}": str(S["port"])}
    return [sub.get(a, a) for a in S[key]]


if __name__ == "__main__":
    # used by the .bat files:  python cc_settings.py <key>
    key = sys.argv[1]
    if key in ("start_command", "dev_command"):
        print(subprocess.list2cmdline(command(key)))
    else:
        print(S[key])
