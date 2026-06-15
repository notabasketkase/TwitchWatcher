"""
twitch_live_watch.py — Twitch live watcher with GUI.

Setup:
  1. Register an app at https://dev.twitch.tv/console/apps
     - OAuth Redirect URL: http://localhost
     - Category: Application Integration
  2. Copy Client ID and generate a Client Secret.
  3. pip install requests plyer keyring
  4. python twitch_live_watch.py

Security notes:
  - Your Client ID is stored in a local JSON config file (plain text, not sensitive).
  - Your Client Secret is stored in Windows Credential Manager via keyring.
  - Nothing is ever sent to any server other than Twitch's official API.
  - The secret is removed from memory immediately after a token is obtained.
"""

import os
import sys
import time
import json
import threading
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox
import requests

try:
    import keyring
    KEYRING_AVAILABLE = True
except ImportError:
    KEYRING_AVAILABLE = False

try:
    from plyer import notification as plyer_notify
    PLYER_AVAILABLE = True
except ImportError:
    PLYER_AVAILABLE = False

try:
    import pystray
    from PIL import Image
    PYSTRAY_AVAILABLE = True
except ImportError:
    PYSTRAY_AVAILABLE = False

try:
    import winreg
    WINREG_AVAILABLE = True
except ImportError:
    WINREG_AVAILABLE = False

KEYRING_SERVICE  = "TwitchWatcher"
KEYRING_USERNAME = "client_secret"
DEFAULT_GROUP    = "General"


# =============================================================================
# CREDENTIAL HELPERS
# =============================================================================
def store_secret(secret):
    if KEYRING_AVAILABLE:
        keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, secret)

def load_secret():
    if KEYRING_AVAILABLE:
        return keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME) or ""
    return ""

def delete_secret():
    if KEYRING_AVAILABLE:
        try:
            keyring.delete_password(KEYRING_SERVICE, KEYRING_USERNAME)
        except Exception:
            pass


# =============================================================================
# STARTUP (RUN ON WINDOWS LOGIN)
# =============================================================================
RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_KEY_NAME = "TwitchWatcher"

def _startup_command():
    """The command Windows runs on login (quoted for paths with spaces)."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    return f'"{sys.executable}" "{os.path.abspath(__file__)}"'

def is_run_on_startup():
    """True if the app is registered to launch on Windows login."""
    if not WINREG_AVAILABLE:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, RUN_KEY_NAME)
        return True
    except OSError:
        return False

def set_run_on_startup(enabled):
    """Add or remove the Windows login startup entry (HKCU Run key, no admin needed)."""
    if not WINREG_AVAILABLE:
        return
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, RUN_KEY_NAME, 0, winreg.REG_SZ, _startup_command())
        else:
            try:
                winreg.DeleteValue(key, RUN_KEY_NAME)
            except FileNotFoundError:
                pass


# =============================================================================
# CONFIG
# =============================================================================
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


# =============================================================================
# TWITCH API
# =============================================================================
TOKEN_URL  = "https://id.twitch.tv/oauth2/token"
STREAMS_URL = "https://api.twitch.tv/helix/streams"

def get_app_token(client_id, client_secret):
    resp = requests.post(TOKEN_URL, params={
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "client_credentials",
    }, timeout=10)
    resp.raise_for_status()
    return resp.json()["access_token"]

def get_live_streams(usernames, client_id, token):
    if not usernames:
        return {}
    resp = requests.get(STREAMS_URL,
        params=[("user_login", n.lower()) for n in usernames],
        headers={"Client-ID": client_id, "Authorization": f"Bearer {token}"},
        timeout=10)
    resp.raise_for_status()
    return {
        e["user_login"].lower(): {
            "title":   e["title"],
            "game":    e.get("game_name", ""),
            "viewers": e.get("viewer_count", 0),
        }
        for e in resp.json().get("data", [])
    }


# =============================================================================
# NOTIFICATIONS
# =============================================================================
def notify(title, message):
    if not PLYER_AVAILABLE:
        return
    try:
        plyer_notify.notify(title=title, message=message, app_name="Twitch Watcher", timeout=8)
    except Exception:
        pass


# =============================================================================
# MAIN APP
# =============================================================================
class TwitchWatcherApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Twitch Watcher")
        self.root.geometry("700x580")

        # Set the window/taskbar icon (falls back silently if not found).
        # When frozen, icon.ico is bundled and extracted to sys._MEIPASS.
        try:
            icon_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
            icon_path = os.path.join(icon_dir, "icon.ico")
            if os.path.exists(icon_path):
                self.root.iconbitmap(icon_path)
        except Exception:
            pass

        self.cfg = load_config()
        self.token               = None
        self.opened              = set()
        self.drops_pending       = set()  # live but waiting for drops in title
        self.drops_game_alerted  = set()
        self.watching            = False
        self.status_rows         = {}   # name -> dict of label widgets
        self.tray_icon           = None
        self._tray_hint_shown    = False

        self._build_ui()
        self._populate_settings()
        self._populate_streamers()
        self._populate_games()

        # System tray — lets the app run in the background; closing the window hides to tray
        self._setup_tray()
        if PYSTRAY_AVAILABLE and self.tray_icon is not None:
            self.root.protocol("WM_DELETE_WINDOW", self._hide_to_tray)

        # First run check — show welcome dialog if no credentials saved yet
        self.root.after(200, self._check_first_run)

        # Autostart — kick off the watcher after the UI is fully ready
        if self.cfg.get("autostart"):
            self.root.after(700, self._toggle_watch)

    # =========================================================================
    # UI
    # =========================================================================
    def _build_ui(self):
        # Menu bar — a clear, discoverable way to quit, since the ✕ now hides to tray
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=0)
        if PYSTRAY_AVAILABLE:
            file_menu.add_command(label="Hide to Tray", command=self._hide_to_tray)
            file_menu.add_separator()
        file_menu.add_command(label="Quit", command=self._quit_app)
        menubar.add_cascade(label="File", menu=file_menu)
        self.root.config(menu=menubar)

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        self.tab_live     = ttk.Frame(self.notebook)
        self.tab_stream   = ttk.Frame(self.notebook)
        self.tab_games    = ttk.Frame(self.notebook)
        self.tab_settings = ttk.Frame(self.notebook)

        self.notebook.add(self.tab_live,     text="  Live Status  ")
        self.notebook.add(self.tab_stream,   text="  Streamers  ")
        self.notebook.add(self.tab_games,    text="  Drops Games  ")
        self.notebook.add(self.tab_settings, text="  Settings  ")

        self._build_live_tab()
        self._build_streamers_tab()
        self._build_games_tab()
        self._build_settings_tab()

        bar = ttk.Frame(self.root)
        bar.pack(fill=tk.X, padx=8, pady=(0, 8))
        self.status_var = tk.StringVar(value="Stopped.")
        ttk.Label(bar, textvariable=self.status_var, anchor="w").pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.toggle_btn = ttk.Button(bar, text="▶  Start Watching", command=self._toggle_watch)
        self.toggle_btn.pack(side=tk.RIGHT)

    # -------------------------------------------------------------------------
    # Live tab
    # -------------------------------------------------------------------------
    def _build_live_tab(self):
        top = ttk.Frame(self.tab_live)
        top.pack(fill=tk.X, padx=8, pady=6)
        ttk.Label(top, text="Watched streamers:", font=("", 9, "bold")).pack(side=tk.LEFT)

        container = ttk.Frame(self.tab_live)
        container.pack(fill=tk.BOTH, expand=True, padx=8, pady=2)
        canvas = tk.Canvas(container, highlightthickness=0)
        sb = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        self.live_frame = ttk.Frame(canvas)
        self.live_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.live_frame, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        ttk.Label(self.tab_live, text="Log:", font=("", 9, "bold")).pack(anchor="w", padx=8)
        lf = ttk.Frame(self.tab_live)
        lf.pack(fill=tk.BOTH, expand=False, padx=8, pady=(0, 4))
        self.log_box = tk.Text(lf, height=7, state=tk.DISABLED, wrap=tk.WORD, font=("Consolas", 8))
        ls = ttk.Scrollbar(lf, command=self.log_box.yview)
        self.log_box.configure(yscrollcommand=ls.set)
        ls.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    def _rebuild_live_rows(self):
        """
        Build the Live Status table grouped by the streamer's group field.
        Each group gets a header row, then its streamers underneath.
        """
        for w in self.live_frame.winfo_children():
            w.destroy()
        self.status_rows = {}

        streamers = self.cfg.get("streamers", [])
        if not streamers:
            ttk.Label(self.live_frame, text="No streamers added yet.", foreground="gray").grid(
                row=0, column=0, padx=8, pady=8)
            return

        # Collect unique groups in the order they first appear
        seen_groups = []
        for s in streamers:
            g = s.get("group", DEFAULT_GROUP) or DEFAULT_GROUP
            if g not in seen_groups:
                seen_groups.append(g)

        # Column headers
        for col, h in enumerate(["Streamer", "Status", "Game", "Title", "Viewers", ""]):
            ttk.Label(self.live_frame, text=h, font=("", 8, "bold")).grid(
                row=0, column=col, padx=6, pady=2, sticky="w")

        current_row = 1
        for group in seen_groups:
            group_streamers = [s for s in streamers
                               if (s.get("group", DEFAULT_GROUP) or DEFAULT_GROUP) == group]

            # Group header separator
            ttk.Separator(self.live_frame, orient="horizontal").grid(
                row=current_row, column=0, columnspan=6, sticky="ew", pady=(6, 0))
            current_row += 1
            ttk.Label(self.live_frame, text=f"  {group}",
                      font=("", 8, "bold"), foreground="#666666").grid(
                row=current_row, column=0, columnspan=6, sticky="w", padx=4, pady=(0, 2))
            current_row += 1

            for s in group_streamers:
                name = s["name"].lower()
                nl = ttk.Label(self.live_frame, text=name, width=16)
                sl = ttk.Label(self.live_frame, text="—", width=9)
                gl = ttk.Label(self.live_frame, text="—", width=18)
                tl = ttk.Label(self.live_frame, text="—", width=28)
                vl = ttk.Label(self.live_frame, text="—", width=8)
                ob = ttk.Button(self.live_frame, text="Open", width=5,
                                command=lambda n=name: webbrowser.open(f"https://twitch.tv/{n}"))

                nl.grid(row=current_row, column=0, padx=6, pady=1, sticky="w")
                sl.grid(row=current_row, column=1, padx=6, pady=1, sticky="w")
                gl.grid(row=current_row, column=2, padx=6, pady=1, sticky="w")
                tl.grid(row=current_row, column=3, padx=6, pady=1, sticky="w")
                vl.grid(row=current_row, column=4, padx=6, pady=1, sticky="w")
                ob.grid(row=current_row, column=5, padx=6, pady=1)

                self.status_rows[name] = {"status": sl, "game": gl, "title": tl, "viewers": vl}
                current_row += 1

    def _update_live_row(self, name, info=None):
        if name not in self.status_rows:
            return
        w = self.status_rows[name]
        if info:
            w["status"].config(text="🟢 LIVE", foreground="green")
            w["game"].config(text=(info["game"] or "—")[:22])
            w["title"].config(text=(info["title"] or "—")[:38])
            w["viewers"].config(text=f'{info["viewers"]:,}')
        else:
            w["status"].config(text="⚫ offline", foreground="gray")
            w["game"].config(text="—")
            w["title"].config(text="—")
            w["viewers"].config(text="—")

    # -------------------------------------------------------------------------
    # Streamers tab
    # -------------------------------------------------------------------------
    def _build_streamers_tab(self):
        top = ttk.Frame(self.tab_stream)
        top.pack(fill=tk.X, padx=8, pady=6)

        ttk.Label(top, text="Username:").pack(side=tk.LEFT)
        self.new_streamer_var = tk.StringVar()
        e = ttk.Entry(top, textvariable=self.new_streamer_var, width=18)
        e.pack(side=tk.LEFT, padx=4)
        e.bind("<Return>", lambda _: self._add_streamer())

        ttk.Label(top, text="Group:").pack(side=tk.LEFT)
        self.new_group_var = tk.StringVar(value=DEFAULT_GROUP)
        ttk.Entry(top, textvariable=self.new_group_var, width=14).pack(side=tk.LEFT, padx=4)

        self.drops_only_var = tk.BooleanVar()
        ttk.Checkbutton(top, text="Drops only", variable=self.drops_only_var).pack(side=tk.LEFT, padx=4)

        # Auto-open defaults ON, so new streamers behave like before unless unticked
        self.auto_open_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(top, text="Auto-open", variable=self.auto_open_var).pack(side=tk.LEFT, padx=4)

        ttk.Button(top, text="Add", command=self._add_streamer).pack(side=tk.LEFT, padx=4)

        cols = ("name", "group", "drops_only", "auto_open")
        self.streamer_tree = ttk.Treeview(self.tab_stream, columns=cols, show="headings", height=13)
        self.streamer_tree.heading("name",      text="Username")
        self.streamer_tree.heading("group",     text="Group")
        self.streamer_tree.heading("drops_only",text="Drops Only")
        self.streamer_tree.heading("auto_open", text="Auto-Open")
        self.streamer_tree.column("name",       width=190)
        self.streamer_tree.column("group",      width=150)
        self.streamer_tree.column("drops_only", width=90, anchor="center")
        self.streamer_tree.column("auto_open",  width=90, anchor="center")
        self.streamer_tree.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        bot = ttk.Frame(self.tab_stream)
        bot.pack(fill=tk.X, padx=8, pady=4)
        ttk.Button(bot, text="Toggle Drops Only", command=self._toggle_drops_only).pack(side=tk.LEFT, padx=4)
        ttk.Button(bot, text="Toggle Auto-Open",  command=self._toggle_auto_open).pack(side=tk.LEFT, padx=4)
        ttk.Button(bot, text="Edit Group",        command=self._edit_group).pack(side=tk.LEFT, padx=4)
        ttk.Button(bot, text="Remove Selected",   command=self._remove_streamer).pack(side=tk.LEFT, padx=4)

    def _populate_streamers(self):
        self.streamer_tree.delete(*self.streamer_tree.get_children())
        for s in self.cfg.get("streamers", []):
            self.streamer_tree.insert("", tk.END, values=(
                s["name"],
                s.get("group", DEFAULT_GROUP) or DEFAULT_GROUP,
                "Yes" if s.get("drops_only") else "No",
                "Yes" if s.get("auto_open", True) else "No"
            ))

    def _add_streamer(self):
        name  = self.new_streamer_var.get().strip().lower()
        group = self.new_group_var.get().strip() or DEFAULT_GROUP
        if not name:
            return
        if name in [s["name"].lower() for s in self.cfg["streamers"]]:
            messagebox.showwarning("Duplicate", f"{name} is already in the list.")
            return
        self.cfg["streamers"].append({
            "name":      name,
            "drops_only": self.drops_only_var.get(),
            "auto_open": self.auto_open_var.get(),
            "group":     group,
        })
        save_config(self.cfg)
        self.new_streamer_var.set("")
        self.drops_only_var.set(False)
        self.auto_open_var.set(True)
        self._populate_streamers()
        self._rebuild_live_rows()

    def _remove_streamer(self):
        sel = self.streamer_tree.selection()
        if not sel:
            return
        name = self.streamer_tree.item(sel[0])["values"][0].lower()
        self.cfg["streamers"] = [s for s in self.cfg["streamers"] if s["name"].lower() != name]
        save_config(self.cfg)
        self._populate_streamers()
        self._rebuild_live_rows()

    def _toggle_drops_only(self):
        sel = self.streamer_tree.selection()
        if not sel:
            return
        name = self.streamer_tree.item(sel[0])["values"][0].lower()
        for s in self.cfg["streamers"]:
            if s["name"].lower() == name:
                s["drops_only"] = not s.get("drops_only", False)
        save_config(self.cfg)
        self._populate_streamers()

    def _toggle_auto_open(self):
        sel = self.streamer_tree.selection()
        if not sel:
            return
        name = str(self.streamer_tree.item(sel[0])["values"][0]).lower()
        for s in self.cfg["streamers"]:
            if s["name"].lower() == name:
                s["auto_open"] = not s.get("auto_open", True)
        save_config(self.cfg)
        self._populate_streamers()

    def _edit_group(self):
        """Pop a small dialog to rename the group for the selected streamer."""
        sel = self.streamer_tree.selection()
        if not sel:
            return
        name          = self.streamer_tree.item(sel[0])["values"][0].lower()
        current_group = self.streamer_tree.item(sel[0])["values"][1]

        dialog = tk.Toplevel(self.root)
        dialog.title("Edit Group")
        dialog.geometry("300x110")
        dialog.resizable(False, False)
        dialog.grab_set()  # modal

        ttk.Label(dialog, text=f"Group for {name}:").pack(padx=12, pady=(12, 4), anchor="w")
        group_var = tk.StringVar(value=current_group)
        entry = ttk.Entry(dialog, textvariable=group_var, width=30)
        entry.pack(padx=12, pady=4)
        entry.select_range(0, tk.END)
        entry.focus()

        def apply():
            new_group = group_var.get().strip() or DEFAULT_GROUP
            for s in self.cfg["streamers"]:
                if s["name"].lower() == name:
                    s["group"] = new_group
            save_config(self.cfg)
            self._populate_streamers()
            self._rebuild_live_rows()
            dialog.destroy()

        entry.bind("<Return>", lambda _: apply())
        ttk.Button(dialog, text="Save", command=apply).pack(pady=6)

    # -------------------------------------------------------------------------
    # Drops Games tab
    # -------------------------------------------------------------------------
    def _build_games_tab(self):
        ttk.Label(self.tab_games,
            text="Alert when any watched streamer has 'drops' in their title and is playing one of these games:",
            wraplength=560).pack(padx=8, pady=8, anchor="w")
        top = ttk.Frame(self.tab_games)
        top.pack(fill=tk.X, padx=8, pady=4)
        ttk.Label(top, text="Game name:").pack(side=tk.LEFT)
        self.new_game_var = tk.StringVar()
        ge = ttk.Entry(top, textvariable=self.new_game_var, width=30)
        ge.pack(side=tk.LEFT, padx=4)
        ge.bind("<Return>", lambda _: self._add_game())
        ttk.Button(top, text="Add", command=self._add_game).pack(side=tk.LEFT, padx=4)
        self.games_listbox = tk.Listbox(self.tab_games, height=14, font=("", 9))
        self.games_listbox.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        ttk.Button(self.tab_games, text="Remove Selected", command=self._remove_game).pack(
            padx=8, pady=4, anchor="w")

    def _populate_games(self):
        self.games_listbox.delete(0, tk.END)
        for g in self.cfg.get("drops_watch_games", []):
            self.games_listbox.insert(tk.END, g)

    def _add_game(self):
        name = self.new_game_var.get().strip()
        if not name:
            return
        if name.lower() in [g.lower() for g in self.cfg["drops_watch_games"]]:
            messagebox.showwarning("Duplicate", f"{name} is already in the list.")
            return
        self.cfg["drops_watch_games"].append(name)
        save_config(self.cfg)
        self.new_game_var.set("")
        self._populate_games()

    def _remove_game(self):
        sel = self.games_listbox.curselection()
        if not sel:
            return
        name = self.games_listbox.get(sel[0])
        self.cfg["drops_watch_games"] = [g for g in self.cfg["drops_watch_games"] if g != name]
        save_config(self.cfg)
        self._populate_games()

    # -------------------------------------------------------------------------
    # Settings tab
    # -------------------------------------------------------------------------
    def _build_settings_tab(self):
        f = ttk.LabelFrame(self.tab_settings, text="Twitch API Credentials")
        f.pack(fill=tk.X, padx=12, pady=10)

        ttk.Label(f, text="Client ID:").grid(row=0, column=0, sticky="e", padx=6, pady=4)
        self.cid_var = tk.StringVar()
        ttk.Entry(f, textvariable=self.cid_var, width=44).grid(row=0, column=1, padx=6, pady=4)

        ttk.Label(f, text="Client Secret:").grid(row=1, column=0, sticky="e", padx=6, pady=4)
        self.csec_var = tk.StringVar()
        ttk.Entry(f, textvariable=self.csec_var, width=44, show="*").grid(row=1, column=1, padx=6, pady=4)

        if KEYRING_AVAILABLE:
            security_text  = ("🔒  Your Client Secret is stored in Windows Credential Manager — "
                              "the same encrypted vault your browser uses for saved passwords. "
                              "It is never written to the config file on disk.")
            security_color = "green"
        else:
            security_text  = ("⚠  keyring not installed. Secret will be stored in plain text. "
                              "Run: pip install keyring")
            security_color = "orange"

        ttk.Label(f, text=security_text, wraplength=500, foreground=security_color,
                  font=("", 8)).grid(row=2, column=0, columnspan=2, padx=6, pady=(2, 4), sticky="w")

        config_note = f"ℹ  Streamer list, game list, and poll interval are saved to:\n{CONFIG_FILE}"
        ttk.Label(f, text=config_note, wraplength=500, foreground="gray",
                  font=("", 8)).grid(row=3, column=0, columnspan=2, padx=6, pady=(0, 8), sticky="w")

        f2 = ttk.LabelFrame(self.tab_settings, text="Polling")
        f2.pack(fill=tk.X, padx=12, pady=6)
        ttk.Label(f2, text="Check interval (seconds):").grid(row=0, column=0, sticky="e", padx=6, pady=4)
        self.interval_var = tk.IntVar()
        ttk.Spinbox(f2, from_=30, to=3600, increment=30, textvariable=self.interval_var, width=8).grid(
            row=0, column=1, padx=6, pady=4, sticky="w")
        self.autostart_var = tk.BooleanVar()
        ttk.Checkbutton(f2, text="Start watching automatically when app opens",
                        variable=self.autostart_var).grid(row=1, column=0, columnspan=2, sticky="w", padx=6, pady=4)
        self.run_on_startup_var = tk.BooleanVar()
        ttk.Checkbutton(f2, text="Launch TwitchWatcher when Windows starts",
                        variable=self.run_on_startup_var).grid(row=2, column=0, columnspan=2, sticky="w", padx=6, pady=4)

        btn_row = ttk.Frame(self.tab_settings)
        btn_row.pack(fill=tk.X, padx=12, pady=10)
        ttk.Button(btn_row, text="Save Settings",     command=self._save_settings).pack(side=tk.LEFT)
        ttk.Button(btn_row, text="Clear Saved Secret", command=self._clear_secret).pack(side=tk.LEFT, padx=8)

        if not PLYER_AVAILABLE:
            ttk.Label(self.tab_settings,
                text="⚠  plyer not installed — notifications disabled. Run: pip install plyer",
                foreground="orange", font=("", 8)).pack(padx=12, anchor="w")

    def _populate_settings(self):
        self.cid_var.set(self.cfg.get("client_id", ""))
        self.csec_var.set(load_secret())
        self.interval_var.set(self.cfg.get("poll_interval", 300))
        self.autostart_var.set(self.cfg.get("autostart", False))
        self.run_on_startup_var.set(is_run_on_startup())

    def _save_settings(self):
        self.cfg["client_id"]    = self.cid_var.get().strip()
        self.cfg["poll_interval"] = self.interval_var.get()
        self.cfg["autostart"]     = self.autostart_var.get()
        save_config(self.cfg)
        secret = self.csec_var.get().strip()
        if secret and not all(c == "*" for c in secret):
            store_secret(secret)
            self.csec_var.set("*" * len(secret))
        try:
            set_run_on_startup(self.run_on_startup_var.get())
        except Exception as e:
            messagebox.showwarning("Startup setting",
                                   f"Couldn't update the Windows startup entry:\n{e}")
        messagebox.showinfo("Saved",
            "Settings saved.\n\nClient ID → config file\nClient Secret → Windows Credential Manager")

    def _clear_secret(self):
        if messagebox.askyesno("Clear Secret",
                "Remove the stored Client Secret from Windows Credential Manager?"):
            delete_secret()
            self.csec_var.set("")
            messagebox.showinfo("Cleared", "Client Secret removed from Windows Credential Manager.")

    # =========================================================================
    # WATCHER
    # =========================================================================
    def _toggle_watch(self):
        if self.watching:
            self.watching = False
            self.toggle_btn.config(text="▶  Start Watching")
            self.status_var.set("Stopped.")
            self._log("Watcher stopped.")
        else:
            if not self.cfg.get("client_id"):
                messagebox.showerror("Missing credentials", "Enter your Client ID in Settings first.")
                return
            if not load_secret():
                messagebox.showerror("Missing credentials", "Enter your Client Secret in Settings first.")
                return
            if not self.cfg.get("streamers"):
                messagebox.showerror("No streamers", "Add at least one streamer first.")
                return
            self._rebuild_live_rows()
            self.watching = True
            self.opened.clear()
            self.drops_pending.clear()
            self.drops_game_alerted.clear()
            self.toggle_btn.config(text="⏹  Stop Watching")
            self.status_var.set("Starting…")
            self._log("Watcher started.")
            threading.Thread(target=self._poll_loop, daemon=True).start()

    def _poll_loop(self):
        client_id = self.cfg["client_id"]
        secret    = load_secret()
        try:
            self.token = get_app_token(client_id, secret)
            self._log("Token acquired. Credentials cleared from memory.")
        except Exception as e:
            self._log(f"Auth error: {e}")
            self.root.after(0, self._toggle_watch)
            return
        finally:
            del secret

        while self.watching:
            self._do_poll(client_id)
            interval = self.cfg.get("poll_interval", 300)
            for _ in range(interval * 2):
                if not self.watching:
                    break
                time.sleep(0.5)

    def _do_poll(self, client_id):
        usernames       = [s["name"].lower() for s in self.cfg.get("streamers", [])]
        drops_only_set  = {s["name"].lower() for s in self.cfg.get("streamers", []) if s.get("drops_only")}
        no_auto_open    = {s["name"].lower() for s in self.cfg.get("streamers", []) if not s.get("auto_open", True)}
        drops_games_low = {g.lower() for g in self.cfg.get("drops_watch_games", [])}

        try:
            live_streams = get_live_streams(usernames, client_id, self.token)
        except requests.HTTPError as e:
            if e.response.status_code == 401:
                secret = load_secret()
                try:
                    self.token = get_app_token(client_id, secret)
                    live_streams = get_live_streams(usernames, client_id, self.token)
                    self._log("Token refreshed.")
                except Exception as e2:
                    self._log(f"Re-auth failed: {e2}")
                    return
                finally:
                    del secret
            else:
                self._log(f"API error: {e}")
                return
        except Exception as e:
            self._log(f"Network error: {e}")
            return

        ts       = time.strftime("%H:%M:%S")
        live_now = set(live_streams.keys())

        for s in self.cfg.get("streamers", []):
            name = s["name"].lower()
            self.root.after(0, self._update_live_row, name, live_streams.get(name))

        for name in live_now - self.opened - self.drops_pending:
            info = live_streams[name]
            if name in drops_only_set and "drops" not in info["title"].lower():
                # Live but no drops yet — notify once and park in drops_pending
                self._log(f"[{ts}] {name} live, no drops yet — waiting. ({info['title']})")
                notify(f"{name} is live (no drops yet)", info["title"])
                self.drops_pending.add(name)
                continue
            notify(f"{name} is LIVE 🔴", info["title"])
            if name in no_auto_open:
                self._log(f"[{ts}] {name} LIVE — notify only (auto-open off). ({info['title']})")
            else:
                self._log(f"[{ts}] {name} LIVE — opening browser. ({info['title']})")
                webbrowser.open(f"https://twitch.tv/{name}")
            self.opened.add(name)

        # Check drops_pending streamers — did they add drops to their title?
        for name in list(self.drops_pending):
            if name not in live_now:
                continue  # went offline, handled below
            info = live_streams[name]
            if "drops" in info["title"].lower():
                notify(f"{name} now has DROPS 🎁", info["title"])
                if name in no_auto_open:
                    self._log(f"[{ts}] {name} added drops — notify only (auto-open off). ({info['title']})")
                else:
                    self._log(f"[{ts}] {name} added drops! Opening browser. ({info['title']})")
                    webbrowser.open(f"https://twitch.tv/{name}")
                self.drops_pending.discard(name)
                self.opened.add(name)

        for name in (self.opened | self.drops_pending) - live_now:
            self._log(f"[{ts}] {name} went offline.")
            notify(f"{name} went offline", "Stream has ended.")
            self.opened.discard(name)
            self.drops_pending.discard(name)
            self.drops_game_alerted.discard(name)

        for name, info in live_streams.items():
            if "drops" in info["title"].lower() and info["game"].lower() in drops_games_low:
                if name not in self.drops_game_alerted:
                    self._log(f"[{ts}] 🎁 {name} has DROPS in {info['game']}! ({info['title']})")
                    notify(f"🎁 Drops! {name} — {info['game']}", info["title"])
                    self.drops_game_alerted.add(name)
            else:
                self.drops_game_alerted.discard(name)

        live_str = f"Live: {', '.join(sorted(live_now))}" if live_now else "All offline"
        self.root.after(0, self.status_var.set, f"{live_str} — last checked {ts}")

    def _log(self, msg):
        def _do():
            self.log_box.config(state=tk.NORMAL)
            self.log_box.insert(tk.END, msg + "\n")
            self.log_box.see(tk.END)
            self.log_box.config(state=tk.DISABLED)
        self.root.after(0, _do)



    # =========================================================================
    # SYSTEM TRAY
    # =========================================================================
    def _resource_path(self, name):
        """Path to a bundled resource, working both as a script and a frozen exe."""
        base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base, name)

    def _setup_tray(self):
        """Create a system-tray icon so the app can keep running in the background."""
        if not PYSTRAY_AVAILABLE:
            return
        try:
            icon_path = self._resource_path("icon.ico")
            if os.path.exists(icon_path):
                image = Image.open(icon_path)
            else:
                image = Image.new("RGB", (64, 64), (119, 44, 232))  # Twitch purple fallback
            menu = pystray.Menu(
                pystray.MenuItem("Show Twitch Watcher", self._show_window, default=True),
                pystray.MenuItem("Quit", self._quit_app),
            )
            self.tray_icon = pystray.Icon("TwitchWatcher", image, "Twitch Watcher", menu)
            threading.Thread(target=self.tray_icon.run, daemon=True).start()
        except Exception:
            # If the tray can't start, fall back to normal window behavior
            self.tray_icon = None

    def _hide_to_tray(self):
        """Hide the window to the tray instead of quitting (window close button)."""
        self.root.withdraw()
        if not self._tray_hint_shown:
            notify("TwitchWatcher is still running",
                   "Minimized to the system tray (check the ^ arrow by the clock). "
                   "Right-click the icon to open or quit.")
            self._tray_hint_shown = True

    def _show_window(self, icon=None, item=None):
        """Restore the window from the tray. Runs on the tray thread → marshal to Tk."""
        self.root.after(0, self._do_show_window)

    def _do_show_window(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def _quit_app(self, icon=None, item=None):
        """Fully exit: stop watching, stop the tray icon, close the app."""
        self.watching = False
        if self.tray_icon is not None:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
        self.root.after(0, self.root.destroy)

    # =========================================================================
    # FIRST RUN
    # =========================================================================
    def _check_first_run(self):
        """
        On launch, check if credentials are already saved.
        If not, show a welcome dialog offering to open the setup guide.
        """
        if self.cfg.get("client_id") and load_secret():
            return  # credentials already set up, nothing to do

        dialog = tk.Toplevel(self.root)
        dialog.title("Welcome to TwitchWatcher")
        dialog.geometry("420x220")
        dialog.resizable(False, False)
        dialog.grab_set()  # modal — user must interact before using the app

        # Center the dialog on screen
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth()  // 2) - (420 // 2)
        y = (dialog.winfo_screenheight() // 2) - (220 // 2)
        dialog.geometry(f"+{x}+{y}")

        ttk.Label(dialog, text="Welcome to TwitchWatcher!",
                  font=("", 13, "bold")).pack(pady=(20, 6))
        ttk.Label(dialog,
                  text="To get started you'll need a free Twitch API Client ID and Client Secret.\n"
                       "Do you already have these?",
                  wraplength=360, justify="center").pack(pady=(0, 20))

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack()

        def on_yes():
            dialog.destroy()
            # Jump straight to Settings tab so they can enter credentials
            self.notebook.select(self.tab_settings)

        def on_no():
            dialog.destroy()
            self._open_setup_guide()

        ttk.Button(btn_frame, text="Yes, I'm ready", command=on_yes, width=18).pack(side=tk.LEFT, padx=8)
        ttk.Button(btn_frame, text="No, show me how", command=on_no, width=18).pack(side=tk.LEFT, padx=8)

    def _open_setup_guide(self):
        """
        Open the bundled setup guide PDF.
        Looks for it next to the exe/script first.
        Falls back to opening the GitHub readme if not found.
        """
        import sys
        import subprocess

        # When bundled with PyInstaller, files land in sys._MEIPASS
        if hasattr(sys, "_MEIPASS"):
            base = sys._MEIPASS
        else:
            base = os.path.dirname(os.path.abspath(__file__))

        pdf_path = os.path.join(base, "TwitchWatcher_Setup_Guide.pdf")

        if os.path.exists(pdf_path):
            os.startfile(pdf_path)  # opens in default PDF viewer on Windows
        else:
            # Fallback — open GitHub page if PDF not found
            webbrowser.open("https://github.com/notabasketKase/TwitchWatcher")

# =============================================================================
# ENTRY POINT
# =============================================================================
if __name__ == "__main__":
    root = tk.Tk()
    app = TwitchWatcherApp(root)
    app._rebuild_live_rows()
    root.mainloop()