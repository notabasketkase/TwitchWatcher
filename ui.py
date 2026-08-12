"""
ui.py — The TwitchWatcherApp window: tabs, settings, system tray, and the
watch/poll loop. Kept as one class for now; can be split per-tab later.
"""

import os
import sys
import re
import time
import threading
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox
import requests

try:
    import pystray
    from PIL import Image
    PYSTRAY_AVAILABLE = True
except ImportError:
    PYSTRAY_AVAILABLE = False

from config import (load_config, save_config, load_state, save_state,
                    DEFAULT_GROUP, APP_VERSION, GITHUB_REPO, CONFIG_FILE)
from credentials import store_secret, load_secret, delete_secret, get_app_token, KEYRING_AVAILABLE
from twitch_api import get_live_streams
from updates import get_latest_release, is_newer_version
from system_integration import is_run_on_startup, set_run_on_startup, create_desktop_shortcut
from notifications import notify, PLYER_AVAILABLE


# Per-streamer behavior as one friendly "Mode" instead of two interacting
# booleans (auto_open × drops_only). The flags stay the stored representation
# (so the watch loop and existing configs are unchanged); Mode is just the UI.
_MODE_TO_FLAGS = {                       # mode -> (auto_open, drops_only)
    "Open when live":  (True,  False),
    "Open on Drops":   (True,  True),
    "Notify only":     (False, False),
    "Notify on Drops": (False, True),
}
STREAMER_MODES = list(_MODE_TO_FLAGS)
MODE_HELP = {
    "Open when live":  "Opens the stream in your browser whenever they go live.",
    "Open on Drops":   "Opens the stream only when they're live with “drops” in the title.",
    "Notify only":     "Sends a notification when they go live — never opens the stream.",
    "Notify on Drops": "Notifies you only when they're live with drops — never opens the stream.",
}


# How the Live Status table is ordered (friendly name -> stored key).
LIVE_SORT_MODES = {
    "Live now section":     "section",  # live pinned in a section on top, offline grouped below
    "Live first in groups": "group",    # groups kept, live rises within each group
    "Grouped":              "grouped",  # original: fixed config order, grouped, no live-sorting
    "Flat (live on top)":   "flat",     # one list, no group headers, live above offline
}
_LIVE_SORT_LABEL = {v: k for k, v in LIVE_SORT_MODES.items()}


def mode_of(s):
    """The friendly Mode name for a streamer dict (from its auto_open/drops_only)."""
    flags = (s.get("auto_open", True), s.get("drops_only", False))
    for mode, mf in _MODE_TO_FLAGS.items():
        if mf == flags:
            return mode
    return "Open when live"


def set_mode(s, mode):
    """Write the auto_open/drops_only flags for a chosen Mode name."""
    s["auto_open"], s["drops_only"] = _MODE_TO_FLAGS.get(mode, (True, False))


class TwitchWatcherApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"Twitch Watcher v{APP_VERSION}")
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
        # First successful poll after a (re)start reconciles persisted state
        # silently — no stale "went offline" alerts for streams that dropped
        # while the app was closed. True by default so it's a no-op until a
        # watch session actually starts and sets it False.
        self._reconciled_after_start = True
        self.watching            = False
        # Set to wake the watch loop early — for an immediate poll after a
        # streamer is added/removed, and for an instant Stop.
        self._poll_now           = threading.Event()
        self.status_rows         = {}   # name -> dict of label widgets
        self._live_info          = {}   # name -> live info dict (or None) from the last poll
        self._rendered_live_set  = None # names currently shown in the "Live now" section
        self.tray_icon           = None
        self._tray_hint_shown    = False
        self._last_log_date      = ""
        self._muted_labels       = []   # persistent muted labels (re-colored on theme switch)
        self._live_muted_labels  = []   # muted labels rebuilt with the live table

        # Apply the saved theme (dark/light/system) BEFORE building any widgets,
        # so the window opens already themed with no bright flash.
        self._apply_saved_theme()
        self._pal = self._palette()
        self._build_ui()
        self._apply_titlebar_theme(nudge=True)
        self._populate_preferences()
        self._populate_streamers()
        self._populate_games()

        # System tray — lets the app run in the background; closing the window hides to tray
        self._setup_tray()
        if PYSTRAY_AVAILABLE and self.tray_icon is not None:
            self.root.protocol("WM_DELETE_WINDOW", self._hide_to_tray)

        # First run check — show welcome dialog if no credentials saved yet
        self.root.after(200, self._check_first_run)

        # Quietly check for a newer release in the background (silent if offline/up-to-date)
        self.root.after(1500, self._check_updates_on_launch)

        # Autostart — kick off the watcher after the UI is fully ready
        if self.cfg.get("autostart"):
            self.root.after(700, self._toggle_watch)

    # =========================================================================
    # UI
    # =========================================================================
    def _build_ui(self):
        # Menu bar. Split logic: Settings menu = "the plumbing" (setup/troubleshooting);
        # the Preferences tab = "how it behaves day to day".
        menubar = tk.Menu(self.root)

        file_menu = tk.Menu(menubar, tearoff=0)
        if PYSTRAY_AVAILABLE:
            file_menu.add_command(label="Hide to Tray", command=self._hide_to_tray)
            file_menu.add_separator()
        file_menu.add_command(label="Quit", command=self._quit_app)
        menubar.add_cascade(label="File", menu=file_menu)

        settings_menu = tk.Menu(menubar, tearoff=0)
        settings_menu.add_command(label="Twitch Credentials…", command=self._open_credentials_dialog)
        settings_menu.add_separator()
        settings_menu.add_command(label="Clear Saved Secret", command=self._clear_secret)
        settings_menu.add_command(label="Create Desktop Shortcut", command=self._create_shortcut)
        menubar.add_cascade(label="Settings", menu=settings_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="Open Setup Guide", command=self._open_setup_guide)
        help_menu.add_command(label="Check for Updates", command=self._check_updates_clicked)
        help_menu.add_separator()
        help_menu.add_command(label="About TwitchWatcher", command=self._show_about)
        menubar.add_cascade(label="Help", menu=help_menu)

        self.root.config(menu=menubar)

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        self.tab_live   = ttk.Frame(self.notebook)
        self.tab_stream = ttk.Frame(self.notebook)
        self.tab_games  = ttk.Frame(self.notebook)
        self.tab_prefs  = ttk.Frame(self.notebook)

        self.notebook.add(self.tab_live,   text="  Live Status  ")
        self.notebook.add(self.tab_stream, text="  Streamers  ")
        self.notebook.add(self.tab_games,  text="  Drops Games  ")
        self.notebook.add(self.tab_prefs,  text="  Preferences  ")

        self._build_live_tab()
        self._build_streamers_tab()
        self._build_games_tab()
        self._build_preferences_tab()

        bar = ttk.Frame(self.root)
        bar.pack(fill=tk.X, padx=8, pady=(0, 8))
        self.status_var = tk.StringVar(value="Stopped.")
        ttk.Label(bar, textvariable=self.status_var, anchor="w").pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.toggle_btn = ttk.Button(bar, text="▶  Start Watching", command=self._toggle_watch)
        self.toggle_btn.pack(side=tk.RIGHT)

        self._apply_tk_theme()

    def _windows_theme(self):
        """Return 'dark' or 'light' from the Windows apps-theme setting."""
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
                val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return "light" if val == 1 else "dark"
        except Exception:
            return "dark"  # safe default if we can't read it

    def _resolve_theme(self, choice):
        """Map a saved choice (dark/light/system) to an actual 'dark'/'light'."""
        if choice == "system":
            return self._windows_theme()
        return choice if choice in ("dark", "light") else "dark"

    def _apply_saved_theme(self):
        """Set the sv_ttk theme from the saved choice (startup path — no widget
        recolor yet; _apply_tk_theme runs later once widgets exist)."""
        resolved = self._resolve_theme(self.cfg.get("theme", "dark"))
        try:
            import sv_ttk
            sv_ttk.set_theme(resolved)
        except Exception:
            pass

    def _apply_titlebar_theme(self, nudge=False):
        """Match the Windows title bar to the app theme so it isn't a jarring
        light strip over the dark UI. Uses DWM immersive dark mode (Win10 2004+
        / Win11); silently does nothing on older/other systems. nudge=True forces
        a quick redraw so a *live* theme switch re-tints the bar immediately."""
        if sys.platform != "win32":
            return
        try:
            import ctypes
            resolved = self._resolve_theme(self.cfg.get("theme", "dark"))
            value = ctypes.c_int(1 if resolved == "dark" else 0)
            self.root.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            # DWMWA_USE_IMMERSIVE_DARK_MODE = 20 (newer), 19 on early 2004 builds.
            for attr in (20, 19):
                if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                        hwnd, attr, ctypes.byref(value), ctypes.sizeof(value)) == 0:
                    break
            if nudge:
                # Force the frame to repaint so the new bar color shows at once.
                self.root.withdraw()
                self.root.deiconify()
        except Exception:
            pass

    def _on_theme_change(self):
        """Appearance radio buttons → persist + apply the new theme live."""
        self._set_theme(self.theme_var.get())

    def _on_show_dot_change(self):
        """Toggle the per-row live/offline dot; persist + redraw the table."""
        self.cfg["show_status_dot"] = self.show_dot_var.get()
        save_config(self.cfg)
        self._rebuild_live_rows()

    def _on_sort_change(self):
        """Change how Live Status is ordered; persist + redraw the table."""
        self.cfg["live_sort"] = LIVE_SORT_MODES.get(self.sort_var.get(), "section")
        save_config(self.cfg)
        self._rebuild_live_rows()

    def _set_theme(self, choice):
        """Persist the theme choice and apply it immediately across the app."""
        self.cfg["theme"] = choice
        save_config(self.cfg)
        resolved = self._resolve_theme(choice)
        try:
            import sv_ttk
            if sv_ttk.get_theme() != resolved:
                sv_ttk.set_theme(resolved)
        except Exception:
            pass
        # Recompute the palette and recolor the parts sv_ttk doesn't touch:
        # the raw tk widgets and every muted label (persistent + live-table).
        self._apply_tk_theme()
        for lbl in self._muted_labels + self._live_muted_labels:
            try:
                lbl.configure(foreground=self._pal["muted"])
            except Exception:
                pass
        self._apply_titlebar_theme(nudge=True)

    def _palette(self):
        """Theme-aware colors for the raw tk widgets and the previously
        hardcoded label colors. Keyed off the active sv_ttk theme, so this also
        serves the light/dark toggle coming in a later phase."""
        theme = "dark"
        try:
            import sv_ttk
            theme = sv_ttk.get_theme()
        except Exception:
            pass
        if theme == "light":
            return {"bg": "#fafafa", "field": "#ffffff", "fg": "#1a1a1a",
                    "muted": "#6b6b6b", "sel": "#cfe2ff",
                    "live": "#1a7f37", "drops": "#9a6700", "error": "#cf222e"}
        return {"bg": "#1c1c1c", "field": "#2b2b2b", "fg": "#fafafa",
                "muted": "#9aa0a6", "sel": "#3a3a3a",
                "live": "#3fb950", "drops": "#e3b341", "error": "#f85149"}

    def _apply_tk_theme(self):
        """Color the raw tk widgets (Text / Listbox / Canvas) that sv_ttk can't
        style, so the theme is consistent everywhere."""
        p = self._pal = self._palette()
        try:
            self.live_canvas.configure(bg=p["bg"])
        except Exception:
            pass
        try:
            self.log_box.configure(bg=p["field"], fg=p["fg"], insertbackground=p["fg"],
                                   selectbackground=p["sel"], selectforeground=p["fg"],
                                   highlightthickness=0, borderwidth=0)
            # Log color-coding (Phase 5) — reconfigured here so it re-themes on
            # a light/dark switch, and existing lines recolor retroactively.
            self.log_box.tag_configure("time",    foreground=p["muted"])
            self.log_box.tag_configure("divider", foreground=p["muted"])
            self.log_box.tag_configure("live",    foreground=p["live"])
            self.log_box.tag_configure("offline", foreground=p["muted"])
            self.log_box.tag_configure("drops",   foreground=p["drops"])
            self.log_box.tag_configure("error",   foreground=p["error"])
            self.log_box.tag_configure("default", foreground=p["fg"])
        except Exception:
            pass
        try:
            self.games_listbox.configure(bg=p["field"], fg=p["fg"],
                                         selectbackground=p["sel"], selectforeground=p["fg"],
                                         highlightthickness=0, borderwidth=0)
        except Exception:
            pass

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
        self.live_canvas = canvas
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
        Build the Live Status table: a pinned "🔴 Live now" section on top (all
        currently-live streamers, most viewers first), then everyone else grouped
        by their group field. Re-runs when the live set changes, so live streamers
        always float to the top.
        """
        for w in self.live_frame.winfo_children():
            w.destroy()
        self.status_rows = {}
        self._live_muted_labels = []  # rebuilt fresh each time this runs

        streamers = self.cfg.get("streamers", [])
        if not streamers:
            nl = ttk.Label(self.live_frame, text="No streamers added yet.", foreground=self._pal["muted"])
            nl.grid(row=0, column=0, padx=8, pady=8)
            self._live_muted_labels.append(nl)
            self._rendered_live_set = frozenset()
            return

        # Optional status dot (Dante's idea). With the Live-now section it's
        # redundant, so it's a per-user toggle. Row order:
        #   [Open] · (dot) · Streamer · Game · Title · Viewers
        show_dot = self.cfg.get("show_status_dot", True)
        headers = (["", "", "Streamer", "Game", "Title", "Viewers"] if show_dot
                   else ["", "Streamer", "Game", "Title", "Viewers"])
        span = len(headers)
        for col, h in enumerate(headers):
            ttk.Label(self.live_frame, text=h, font=("", 8, "bold")).grid(
                row=0, column=col, padx=6, pady=2, sticky="w")

        self._row_cursor = 1

        def section_header(text, color):
            ttk.Separator(self.live_frame, orient="horizontal").grid(
                row=self._row_cursor, column=0, columnspan=span, sticky="ew", pady=(6, 0))
            self._row_cursor += 1
            lbl = ttk.Label(self.live_frame, text=text, font=("", 8, "bold"), foreground=color)
            lbl.grid(row=self._row_cursor, column=0, columnspan=span, sticky="w", padx=4, pady=(0, 2))
            self._row_cursor += 1
            return lbl

        def place_row(s):
            name = s["name"].lower()
            nl = ttk.Label(self.live_frame, text=name, width=16)
            gl = ttk.Label(self.live_frame, text="—", width=18)
            tl = ttk.Label(self.live_frame, text="—", width=28)
            vl = ttk.Label(self.live_frame, text="—", width=8)
            ob = ttk.Button(self.live_frame, text="Open", width=5,
                            command=lambda n=name: webbrowser.open(f"https://twitch.tv/{n}"))
            r, c = self._row_cursor, 0
            ob.grid(row=r, column=c, padx=6, pady=1); c += 1
            row = {"name": nl, "game": gl, "title": tl, "viewers": vl}
            if show_dot:
                sl = ttk.Label(self.live_frame, text="●", width=3, font=("", 12),
                               foreground=self._pal["muted"])
                sl.grid(row=r, column=c, padx=(6, 2), pady=1); c += 1
                row["status"] = sl
                self._attach_tooltip(
                    sl, lambda n=name: "Live" if self.status_rows.get(n, {}).get("live") else "Offline")
            nl.grid(row=r, column=c, padx=6, pady=1, sticky="w"); c += 1
            gl.grid(row=r, column=c, padx=6, pady=1, sticky="w"); c += 1
            tl.grid(row=r, column=c, padx=6, pady=1, sticky="w"); c += 1
            vl.grid(row=r, column=c, padx=6, pady=1, sticky="w"); c += 1
            self.status_rows[name] = row
            self._update_live_row(name, self._live_info.get(name))  # paint current state
            self._row_cursor += 1

        def group_of(s):
            return s.get("group", DEFAULT_GROUP) or DEFAULT_GROUP

        def ordered_groups(items):
            seen = []
            for s in items:
                g = group_of(s)
                if g not in seen:
                    seen.append(g)
            return seen

        def is_live(s):
            return bool(self._live_info.get(s["name"].lower()))

        def by_viewers(s):
            return -((self._live_info.get(s["name"].lower()) or {}).get("viewers", 0))

        def grouped_block(members):
            for group in ordered_groups(members):
                gm = [s for s in members if group_of(s) == group]
                if not gm:
                    continue
                self._live_muted_labels.append(section_header(f"  {group}", self._pal["muted"]))
                for s in gm:
                    place_row(s)

        mode = self.cfg.get("live_sort", "section")
        if mode == "flat":
            # One list, no group headers: live (most viewers first) then offline.
            for s in sorted([x for x in streamers if is_live(x)], key=by_viewers) + \
                     [x for x in streamers if not is_live(x)]:
                place_row(s)
        elif mode == "grouped":
            # Original: groups in config order, no live-sorting.
            grouped_block(streamers)
        elif mode == "group":
            # Groups kept, but live rises to the top within each group.
            for group in ordered_groups(streamers):
                gm = [s for s in streamers if group_of(s) == group]
                gm = sorted([s for s in gm if is_live(s)], key=by_viewers) + \
                     [s for s in gm if not is_live(s)]
                self._live_muted_labels.append(section_header(f"  {group}", self._pal["muted"]))
                for s in gm:
                    place_row(s)
        else:  # "section" — pinned "Live now" on top, everyone else grouped below
            live = sorted([s for s in streamers if is_live(s)], key=by_viewers)
            if live:
                section_header("🔴  Live now", self._pal["live"])
                for s in live:
                    place_row(s)
            grouped_block([s for s in streamers if not is_live(s)])

        self._rendered_live_set = frozenset(s["name"].lower() for s in streamers if is_live(s))

    def _update_live_row(self, name, info=None):
        if name not in self.status_rows:
            return
        w = self.status_rows[name]
        if info:
            w["live"] = True
            w["name"].config(foreground=self._pal["live"])
            if "status" in w:
                w["status"].config(text="●", foreground=self._pal["live"])
            w["game"].config(text=(info["game"] or "—")[:22])
            w["title"].config(text=(info["title"] or "—")[:38])
            w["viewers"].config(text=f'{info["viewers"]:,}')
        else:
            w["live"] = False
            w["name"].config(foreground=self._pal["muted"])
            if "status" in w:
                w["status"].config(text="●", foreground=self._pal["muted"])
            w["game"].config(text="—")
            w["title"].config(text="—")
            w["viewers"].config(text="—")

    def _refresh_live_display(self):
        """Called after each poll (on the UI thread). For live-aware sort modes,
        reflow the table when the live set changes; otherwise (and for the fixed
        "grouped" mode) just refresh each row's details in place."""
        live_now = frozenset(n for n, info in self._live_info.items() if info)
        reflows = self.cfg.get("live_sort", "section") != "grouped"
        if reflows and live_now != self._rendered_live_set:
            self._rebuild_live_rows()
        else:
            for name, info in self._live_info.items():
                if name in self.status_rows:
                    self._update_live_row(name, info)

    def _attach_tooltip(self, widget, text_getter):
        """Lightweight hover tooltip. text_getter() returns the current text
        (so the status dot can report Live/Offline as it changes)."""
        state = {"win": None}

        def show(_e=None):
            if state["win"] is not None:
                return
            text = text_getter()
            if not text:
                return
            x = widget.winfo_rootx() + 24
            y = widget.winfo_rooty() + widget.winfo_height() + 2
            win = tk.Toplevel(widget)
            win.wm_overrideredirect(True)
            win.wm_geometry(f"+{x}+{y}")
            tk.Label(win, text=text, background=self._pal["field"], foreground=self._pal["fg"],
                     relief="solid", borderwidth=1, font=("", 8), padx=6, pady=2).pack()
            state["win"] = win

        def hide(_e=None):
            if state["win"] is not None:
                state["win"].destroy()
                state["win"] = None

        widget.bind("<Enter>", show)
        widget.bind("<Leave>", hide)
        widget.bind("<Destroy>", lambda _e: hide())

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

        ttk.Label(top, text="Mode:").pack(side=tk.LEFT)
        self.new_mode_var = tk.StringVar(value="Open when live")
        ttk.Combobox(top, textvariable=self.new_mode_var, values=STREAMER_MODES,
                     state="readonly", width=15).pack(side=tk.LEFT, padx=4)

        ttk.Button(top, text="Add", command=self._add_streamer).pack(side=tk.LEFT, padx=4)

        cols = ("name", "group", "mode")
        self.streamer_tree = ttk.Treeview(self.tab_stream, columns=cols, show="headings", height=13)
        self.streamer_tree.heading("name",  text="Username")
        self.streamer_tree.heading("group", text="Group")
        self.streamer_tree.heading("mode",  text="Mode")
        self.streamer_tree.column("name",  width=180)
        self.streamer_tree.column("group", width=140)
        self.streamer_tree.column("mode",  width=150, anchor="center")
        # Click a column header to sort the list by that column
        for _c in cols:
            self.streamer_tree.heading(_c, command=lambda c=_c: self._sort_streamer_column(c, False))
        # Double-click a row to edit it
        self.streamer_tree.bind("<Double-1>", lambda _e: self._edit_streamer())
        self.streamer_tree.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        bot = ttk.Frame(self.tab_stream)
        bot.pack(fill=tk.X, padx=8, pady=4)
        ttk.Button(bot, text="Edit Streamer",   command=self._edit_streamer).pack(side=tk.LEFT, padx=4)
        ttk.Button(bot, text="Remove Selected", command=self._remove_streamer).pack(side=tk.LEFT, padx=4)

    def _populate_streamers(self):
        self.streamer_tree.delete(*self.streamer_tree.get_children())
        for s in self.cfg.get("streamers", []):
            self.streamer_tree.insert("", tk.END, values=(
                s["name"],
                s.get("group", DEFAULT_GROUP) or DEFAULT_GROUP,
                mode_of(s),
            ))

    def _sort_streamer_column(self, col, descending):
        """Click a Streamers column header to sort the view by that column (toggles asc/desc)."""
        rows = [(self.streamer_tree.set(item, col), item)
                for item in self.streamer_tree.get_children("")]
        rows.sort(key=lambda r: str(r[0]).lower(), reverse=descending)
        for index, (_val, item) in enumerate(rows):
            self.streamer_tree.move(item, "", index)
        # flip direction for the next click on this header
        self.streamer_tree.heading(col, command=lambda: self._sort_streamer_column(col, not descending))

    def _add_streamer(self):
        name  = self.new_streamer_var.get().strip().lower()
        group = self.new_group_var.get().strip() or DEFAULT_GROUP
        if not name:
            return
        if name in [s["name"].lower() for s in self.cfg["streamers"]]:
            messagebox.showwarning("Duplicate", f"{name} is already in the list.")
            return
        entry = {"name": name, "group": group}
        set_mode(entry, self.new_mode_var.get())
        self.cfg["streamers"].append(entry)
        save_config(self.cfg)
        self.new_streamer_var.set("")
        self.new_mode_var.set("Open when live")
        self._populate_streamers()
        self._rebuild_live_rows()
        self._poll_soon()  # fill in the new streamer's status right away

    def _remove_streamer(self):
        sel = self.streamer_tree.selection()
        if not sel:
            return
        name = self.streamer_tree.item(sel[0])["values"][0].lower()
        self.cfg["streamers"] = [s for s in self.cfg["streamers"] if s["name"].lower() != name]
        save_config(self.cfg)
        self._populate_streamers()
        self._rebuild_live_rows()
        self._poll_soon()

    def _edit_streamer(self):
        """Edit the selected streamer's Group and Mode together in one dialog."""
        sel = self.streamer_tree.selection()
        if not sel:
            return
        name = str(self.streamer_tree.item(sel[0])["values"][0]).lower()
        s = next((x for x in self.cfg["streamers"] if x["name"].lower() == name), None)
        if s is None:
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Edit Streamer")
        dialog.resizable(False, False)
        dialog.grab_set()

        frm = ttk.Frame(dialog, padding=14)
        frm.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frm, text=name, font=("", 10, "bold")).grid(
            row=0, column=0, columnspan=2, pady=(0, 8), sticky="w")

        ttk.Label(frm, text="Group:").grid(row=1, column=0, sticky="e", padx=6, pady=6)
        group_var = tk.StringVar(value=s.get("group", DEFAULT_GROUP) or DEFAULT_GROUP)
        ge = ttk.Entry(frm, textvariable=group_var, width=24)
        ge.grid(row=1, column=1, padx=6, pady=6, sticky="w")

        ttk.Label(frm, text="Mode:").grid(row=2, column=0, sticky="e", padx=6, pady=6)
        mode_var = tk.StringVar(value=mode_of(s))
        cb = ttk.Combobox(frm, textvariable=mode_var, values=STREAMER_MODES, state="readonly", width=22)
        cb.grid(row=2, column=1, padx=6, pady=6, sticky="w")

        # Plain-language description of the selected mode, updates as you change it.
        hint = ttk.Label(frm, text=MODE_HELP.get(mode_var.get(), ""), wraplength=300,
                         foreground=self._pal["muted"], font=("", 8))
        hint.grid(row=3, column=0, columnspan=2, padx=6, pady=(2, 8), sticky="w")
        cb.bind("<<ComboboxSelected>>", lambda _e: hint.config(text=MODE_HELP.get(mode_var.get(), "")))

        def apply():
            s["group"] = group_var.get().strip() or DEFAULT_GROUP
            set_mode(s, mode_var.get())
            save_config(self.cfg)
            self._populate_streamers()
            self._rebuild_live_rows()
            dialog.destroy()

        btns = ttk.Frame(frm)
        btns.grid(row=4, column=0, columnspan=2, pady=(4, 0))
        ttk.Button(btns, text="Save", command=apply, width=10).pack(side=tk.LEFT, padx=6)
        ttk.Button(btns, text="Cancel", command=dialog.destroy, width=10).pack(side=tk.LEFT, padx=6)
        ge.focus()
        self._center_on_root(dialog)

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
    def _build_preferences_tab(self):
        # Day-to-day behavior. (The "plumbing" — credentials, clear secret,
        # shortcut — lives in the Settings menu instead.)
        f2 = ttk.LabelFrame(self.tab_prefs, text="Polling")
        f2.pack(fill=tk.X, padx=12, pady=(12, 6))
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

        f3 = ttk.LabelFrame(self.tab_prefs, text="Appearance")
        f3.pack(fill=tk.X, padx=12, pady=6)
        ttk.Label(f3, text="Theme:").grid(row=0, column=0, sticky="e", padx=6, pady=6)
        self.theme_var = tk.StringVar(value=self.cfg.get("theme", "dark"))
        for i, (label, val) in enumerate([("Dark", "dark"), ("Light", "light"), ("System", "system")]):
            ttk.Radiobutton(f3, text=label, value=val, variable=self.theme_var,
                            command=self._on_theme_change).grid(row=0, column=1 + i, padx=6, pady=6, sticky="w")

        self.show_dot_var = tk.BooleanVar(value=self.cfg.get("show_status_dot", True))
        ttk.Checkbutton(f3, text="Show a live/offline dot on each Live Status row",
                        variable=self.show_dot_var, command=self._on_show_dot_change).grid(
            row=1, column=0, columnspan=4, sticky="w", padx=6, pady=(0, 6))

        ttk.Label(f3, text="Live Status sort:").grid(row=2, column=0, sticky="w", padx=6, pady=(0, 8))
        self.sort_var = tk.StringVar(
            value=_LIVE_SORT_LABEL.get(self.cfg.get("live_sort", "section"), "Live now section"))
        sort_cb = ttk.Combobox(f3, textvariable=self.sort_var, values=list(LIVE_SORT_MODES),
                               state="readonly", width=20)
        sort_cb.grid(row=2, column=1, columnspan=3, sticky="w", padx=6, pady=(0, 8))
        sort_cb.bind("<<ComboboxSelected>>", lambda _e: self._on_sort_change())

        btn_row = ttk.Frame(self.tab_prefs)
        btn_row.pack(fill=tk.X, padx=12, pady=10)
        ttk.Button(btn_row, text="Save Preferences", command=self._save_preferences).pack(side=tk.LEFT)

        note = ttk.Label(self.tab_prefs,
                         text=("ℹ  Twitch credentials live under Settings → Twitch Credentials.\n"
                               f"Your streamer list and preferences are saved to:\n{CONFIG_FILE}"),
                         wraplength=520, foreground=self._pal["muted"], font=("", 8))
        note.pack(padx=12, pady=(0, 6), anchor="w")
        self._muted_labels.append(note)

        if not PLYER_AVAILABLE:
            ttk.Label(self.tab_prefs,
                text="⚠  plyer not installed — notifications disabled. Run: pip install plyer",
                foreground="orange", font=("", 8)).pack(padx=12, anchor="w")

    def _populate_preferences(self):
        self.interval_var.set(self.cfg.get("poll_interval", 300))
        self.autostart_var.set(self.cfg.get("autostart", False))
        self.run_on_startup_var.set(is_run_on_startup())
        self.theme_var.set(self.cfg.get("theme", "dark"))
        self.show_dot_var.set(self.cfg.get("show_status_dot", True))
        self.sort_var.set(_LIVE_SORT_LABEL.get(self.cfg.get("live_sort", "section"), "Live now section"))

    def _save_preferences(self):
        self.cfg["poll_interval"] = self.interval_var.get()
        self.cfg["autostart"]     = self.autostart_var.get()
        save_config(self.cfg)
        try:
            set_run_on_startup(self.run_on_startup_var.get())
        except Exception as e:
            messagebox.showwarning("Startup setting",
                                   f"Couldn't update the Windows startup entry:\n{e}")
        messagebox.showinfo("Saved", "Preferences saved.")

    def _open_credentials_dialog(self):
        """Modal dialog to enter/update the Twitch Client ID + Secret. Keeping
        credentials off the main window is nicer during screen-sharing and
        de-clutters the UI."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Twitch Credentials")
        dialog.resizable(False, False)
        dialog.grab_set()

        frm = ttk.Frame(dialog, padding=14)
        frm.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frm, text="Client ID:").grid(row=0, column=0, sticky="e", padx=6, pady=6)
        cid_var = tk.StringVar(value=self.cfg.get("client_id", ""))
        cid_entry = ttk.Entry(frm, textvariable=cid_var, width=46)
        cid_entry.grid(row=0, column=1, padx=6, pady=6)

        ttk.Label(frm, text="Client Secret:").grid(row=1, column=0, sticky="e", padx=6, pady=6)
        csec_var = tk.StringVar(value=load_secret())
        ttk.Entry(frm, textvariable=csec_var, width=46, show="*").grid(row=1, column=1, padx=6, pady=6)

        if KEYRING_AVAILABLE:
            sec_text  = ("🔒  Your Client Secret is stored in Windows Credential Manager — the same "
                         "encrypted vault your browser uses for saved passwords. It is never written "
                         "to the config file on disk.")
            sec_color = "green"
        else:
            sec_text  = ("⚠  keyring not installed. Secret will be stored in plain text. "
                         "Run: pip install keyring")
            sec_color = "orange"
        ttk.Label(frm, text=sec_text, wraplength=440, foreground=sec_color,
                  font=("", 8)).grid(row=2, column=0, columnspan=2, padx=6, pady=(2, 10), sticky="w")

        def save_and_close():
            self.cfg["client_id"] = cid_var.get().strip()
            save_config(self.cfg)
            secret = csec_var.get().strip()
            if secret and not all(c == "*" for c in secret):
                store_secret(secret)
            dialog.destroy()
            messagebox.showinfo("Saved",
                "Credentials saved.\n\nClient ID → config file\nClient Secret → Windows Credential Manager")

        btns = ttk.Frame(frm)
        btns.grid(row=3, column=0, columnspan=2, pady=(4, 0))
        ttk.Button(btns, text="Save", command=save_and_close, width=12).pack(side=tk.LEFT, padx=6)
        ttk.Button(btns, text="Cancel", command=dialog.destroy, width=12).pack(side=tk.LEFT, padx=6)

        cid_entry.focus()
        self._center_on_root(dialog)

    def _show_about(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("About TwitchWatcher")
        dialog.resizable(False, False)
        dialog.grab_set()

        frm = ttk.Frame(dialog, padding=18)
        frm.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frm, text="TwitchWatcher", font=("", 14, "bold")).pack()
        ttk.Label(frm, text=f"Version {APP_VERSION}").pack(pady=(2, 10))
        ttk.Label(frm, text="Auto-launch your favorite streams and keep an eye on drops.",
                  wraplength=320, justify="center").pack(pady=(0, 12))

        btns = ttk.Frame(frm)
        btns.pack()
        ttk.Button(btns, text="GitHub", width=12,
                   command=lambda: webbrowser.open(f"https://github.com/{GITHUB_REPO}")).pack(side=tk.LEFT, padx=6)
        # Ko-fi: add a support button here when you have a page, e.g.
        #   ttk.Button(btns, text="Ko-fi ☕", command=lambda: webbrowser.open("https://ko-fi.com/<you>"))
        ttk.Button(btns, text="Close", width=12, command=dialog.destroy).pack(side=tk.LEFT, padx=6)
        self._center_on_root(dialog)

    def _center_on_root(self, dialog):
        """Center a Toplevel over the main window."""
        dialog.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width()  // 2) - (dialog.winfo_width()  // 2)
        y = self.root.winfo_rooty() + (self.root.winfo_height() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{max(x, 0)}+{max(y, 0)}")

    def _clear_secret(self):
        if messagebox.askyesno("Clear Secret",
                "Remove the stored Client Secret from Windows Credential Manager?"):
            delete_secret()
            messagebox.showinfo("Cleared", "Client Secret removed from Windows Credential Manager.")

    def _create_shortcut(self):
        try:
            create_desktop_shortcut()
            messagebox.showinfo("Shortcut created",
                                "A TwitchWatcher shortcut was added to your Desktop.")
        except Exception as e:
            messagebox.showwarning("Couldn't create shortcut",
                                   f"Something went wrong:\n{e}")

    def _check_updates_on_launch(self):
        """Background check; only bothers the user if a newer release exists."""
        def work():
            try:
                tag, url = get_latest_release()
                if tag and is_newer_version(tag):
                    self.root.after(0, self._prompt_update, tag, url)
            except Exception:
                pass  # stay silent on launch (offline, rate-limited, etc.)
        threading.Thread(target=work, daemon=True).start()

    def _check_updates_clicked(self):
        """Manual 'Check for Updates' button — reports every outcome."""
        try:
            tag, url = get_latest_release()
        except Exception as e:
            messagebox.showwarning("Update check failed",
                                   f"Couldn't reach GitHub to check for updates.\n{e}")
            return
        if tag and is_newer_version(tag):
            self._prompt_update(tag, url)
        else:
            messagebox.showinfo("Up to date",
                                f"You're running the latest version (v{APP_VERSION}).")

    def _prompt_update(self, tag, url):
        if messagebox.askyesno("Update available",
                f"A new version ({tag}) of TwitchWatcher is available.\n"
                f"You're on v{APP_VERSION}.\n\nOpen the download page?"):
            webbrowser.open(url or f"https://github.com/{GITHUB_REPO}/releases/latest")

    # =========================================================================
    # WATCHER
    # =========================================================================
    def _toggle_watch(self):
        if self.watching:
            self.watching = False
            self._poll_now.set()  # wake the loop so it stops right away
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
            # Restore the "already opened / already notified" memory from disk so
            # a restart doesn't re-pop streams that were already open before it.
            # (While running, a streamer going offline still clears them from this
            # set, so a genuine offline→online still reopens as before.)
            state = load_state()
            self.opened             = set(state["opened"])
            self.drops_pending      = set(state["drops_pending"])
            self.drops_game_alerted = set(state["drops_game_alerted"])
            self._reconciled_after_start = False
            self.toggle_btn.config(text="⏹  Stop Watching")
            self.status_var.set("Starting…")
            self._log("Watcher started.")
            threading.Thread(target=self._poll_loop, daemon=True).start()

    def _poll_soon(self):
        """Ask the watch loop to poll right now instead of waiting out the
        interval (used after a streamer is added/removed while watching)."""
        if self.watching:
            self._poll_now.set()

    def _poll_loop(self):
        client_id = self.cfg["client_id"]
        self.token = None

        while self.watching:
            # (Re)acquire a token whenever we don't have one. A failure here —
            # e.g. the network isn't up yet after a wake, or the connection
            # dropped — no longer stops the watcher: we keep retrying until it
            # succeeds, so the watcher recovers on its own when the internet
            # comes back instead of silently switching itself off.
            if self.token is None:
                secret = load_secret()
                try:
                    self.token = get_app_token(client_id, secret)
                    self._log("Token acquired. Credentials cleared from memory.")
                except Exception as e:
                    self._log(f"Auth error (will keep retrying): {e}")
                    self.root.after(0, self.status_var.set, "Waiting for connection…")
                finally:
                    del secret

            if self.token is not None:
                self._do_poll(client_id)

            # Poll at the normal interval once connected; while we still can't
            # get a token, retry quickly (every 15s) so recovery is prompt.
            interval = self.cfg.get("poll_interval", 300) if self.token is not None else 15
            # Wait out the interval, but wake immediately if asked to poll now
            # (streamer added/removed) or to stop.
            self._poll_now.wait(timeout=interval)
            self._poll_now.clear()

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
            self.root.after(0, self.status_var.set, "Network error — retrying…")
            return

        ts       = time.strftime("%H:%M:%S")
        live_now = set(live_streams.keys())

        # Record each streamer's current live info (fresh dict prunes removed
        # ones), then reflow the display so live streamers float to the top.
        self._live_info = {s["name"].lower(): live_streams.get(s["name"].lower())
                           for s in self.cfg.get("streamers", [])}
        self.root.after(0, self._refresh_live_display)

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
            # On the first poll after a (re)start we're just reconciling restored
            # state — a streamer that dropped while we were closed shouldn't fire
            # a stale "went offline" alert. Clear them quietly instead.
            if self._reconciled_after_start:
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

        # This poll completed a full pass, so any future offline transitions are
        # real (not restored-state reconciliation) and should alert normally.
        self._reconciled_after_start = True
        # Persist what we've reacted to so a restart resumes where we left off.
        save_state(self.opened, self.drops_pending, self.drops_game_alerted)

    def _log_kind(self, msg):
        """Pick a color tag for a log line from its content (priority: error →
        drops → offline → live → default)."""
        m = msg.lower()
        if "error" in m or "failed" in m:
            return "error"
        if "drops" in m or "🎁" in msg:
            return "drops"
        if "offline" in m:
            return "offline"
        if "live" in m or "opening browser" in m or "watcher started" in m:
            return "live"
        return "default"

    def _log(self, msg):
        def _do():
            self.log_box.config(state=tk.NORMAL)
            # Drop a date divider when the day rolls over, so multi-day (set-and-forget) logs
            # stay readable. Spelled-out month avoids US/EU numeric-date ambiguity.
            today = time.strftime("%b %d, %Y")
            if today != self._last_log_date:
                self._last_log_date = today
                self.log_box.insert(tk.END, f"——— {today} ———\n", "divider")
            # Split a leading "[HH:MM:SS] " timestamp so it can be muted, and
            # color the rest by kind.
            tag = self._log_kind(msg)
            m = re.match(r"^(\[\d{2}:\d{2}:\d{2}\] )(.*)$", msg, re.S)
            if m:
                self.log_box.insert(tk.END, m.group(1), "time")
                self.log_box.insert(tk.END, m.group(2) + "\n", tag)
            else:
                self.log_box.insert(tk.END, msg + "\n", tag)
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
            # Open the credentials dialog so they can enter their keys
            self._open_credentials_dialog()

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
