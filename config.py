"""
config.py — App constants and config-file persistence for TwitchWatcher.

Holds the shared version/repo constants and reads/writes the user's
twitch_watcher_config.json next to the .exe (or script).
"""

import os
import sys
import json

DEFAULT_GROUP = "General"
APP_VERSION   = "1.0.0"
GITHUB_REPO   = "notabasketkase/TwitchWatcher"

# Where to store the user's config. When frozen by PyInstaller, __file__ points
# into a temp extraction folder that gets wiped on exit — so write next to the
# .exe instead, which persists and matches what the setup guide tells users.
if getattr(sys, "frozen", False):
    _APP_DIR = os.path.dirname(sys.executable)
else:
    _APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(_APP_DIR, "twitch_watcher_config.json")
# Runtime state (which streamers we've already opened/notified this run). Kept
# separate from user config so a restart doesn't re-pop streams already open.
STATE_FILE = os.path.join(_APP_DIR, "twitch_watcher_state.json")

DEFAULT_CONFIG = {
    "client_id": os.environ.get("TWITCH_CLIENT_ID", ""),
    "poll_interval": 300,
    "autostart": False,     # if True, start watching automatically on launch
    "streamers": [],        # [{"name": "...", "drops_only": false, "auto_open": true, "group": "General"}]
    "drops_watch_games": [],
    "theme": "dark",        # "dark" | "light" | "system" (dark-first: no bright flash on launch)
    "show_status_dot": True,  # colored live/offline dot in the Live Status rows
    "live_sort": "section",   # section | group | grouped | flat (see ui.LIVE_SORT_MODES)
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


def load_state():
    """Load the watcher's 'already reacted to' sets (opened / drops_pending /
    drops_game_alerted) as a dict of lists. Returns empty lists if there's no
    state file yet or it can't be read."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
                return {
                    "opened":             list(data.get("opened", [])),
                    "drops_pending":      list(data.get("drops_pending", [])),
                    "drops_game_alerted": list(data.get("drops_game_alerted", [])),
                }
        except Exception:
            pass
    return {"opened": [], "drops_pending": [], "drops_game_alerted": []}


def save_state(opened, drops_pending, drops_game_alerted):
    """Persist the watcher's 'already reacted to' sets so a restart doesn't
    re-open / re-notify streamers that were already handled. Best-effort — a
    disk error here must never crash the poll loop."""
    try:
        with open(STATE_FILE, "w") as f:
            json.dump({
                "opened":             sorted(opened),
                "drops_pending":      sorted(drops_pending),
                "drops_game_alerted": sorted(drops_game_alerted),
            }, f, indent=2)
    except Exception:
        pass
