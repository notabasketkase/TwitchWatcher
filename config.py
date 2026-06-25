"""
config.py — App constants and config-file persistence for TwitchWatcher.

Holds the shared version/repo constants and reads/writes the user's
twitch_watcher_config.json next to the .exe (or script).
"""

import os
import sys
import json

DEFAULT_GROUP = "General"
APP_VERSION   = "0.3.1"
GITHUB_REPO   = "notabasketkase/TwitchWatcher"

# Where to store the user's config. When frozen by PyInstaller, __file__ points
# into a temp extraction folder that gets wiped on exit — so write next to the
# .exe instead, which persists and matches what the setup guide tells users.
if getattr(sys, "frozen", False):
    _APP_DIR = os.path.dirname(sys.executable)
else:
    _APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(_APP_DIR, "twitch_watcher_config.json")

DEFAULT_CONFIG = {
    "client_id": os.environ.get("TWITCH_CLIENT_ID", ""),
    "poll_interval": 300,
    "autostart": False,     # if True, start watching automatically on launch
    "streamers": [],        # [{"name": "...", "drops_only": false, "auto_open": true, "group": "General"}]
    "drops_watch_games": [],
}


def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
                for k, v in DEFAULT_CONFIG.items():
                    data.setdefault(k, v)
                data.pop("client_secret", None)
                # Migrate old streamers missing newer fields
                for s in data.get("streamers", []):
                    s.setdefault("group", DEFAULT_GROUP)
                    s.setdefault("auto_open", True)
                return data
        except Exception:
            pass
    return dict(DEFAULT_CONFIG)


def save_config(cfg):
    safe = {k: v for k, v in cfg.items() if k != "client_secret"}
    with open(CONFIG_FILE, "w") as f:
        json.dump(safe, f, indent=2)
