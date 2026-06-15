# TwitchWatcher — Roadmap

A lightweight Windows desktop app that watches Twitch streamers and notifies you
(and auto-opens the stream) the moment they go live. Built for drops hunters and
people who want to **keep their watch streaks alive without babysitting Twitch** —
catch every go-live while you're asleep or at work.

Effort key: 🟢 quick · 🟡 medium · 🔴 big lift · 🔒 needs Twitch login (OAuth)

---

## ✅ Shipped

### v0.1.0 — 2026-06-11 (first public/beta release)
- Live Windows toast notifications + auto-open browser on go-live
- Drops-only filter per streamer; drops-pending state (watches for drops added mid-stream)
- Drops + watched-game alerts
- Four-tab GUI: Live Status, Streamers, Drops Games, Settings
- Free-text streamer groups; 🟢/⚫ live indicators; timestamped log window
- Config persists (JSON); Client Secret in Windows Credential Manager
- Autostart option; first-run welcome dialog; bundled setup guide PDF; app icon
- Packaged as one-file .exe (PyInstaller); public GitHub repo + README + release

### v0.2.0 — 2026-06-11
- Setup guide: fixed the Dev Console app-name step (Twitch rejects names containing
  "Twitch") and added an FAQ
- App now shows its own icon on the taskbar/window (was the default Tk feather)
- Guide is now generated from an editable source (`make_guide.py`)

---

## 🏁 Path to 1.0

**1.0 = confidence, not perfection.** It means "I'd hand this to a stranger with no caveats and not
wince" — NOT "every roadmap item is done" (the backlog never empties; that's what 1.x / 2.0 are for).
Cut 1.0 when most of these are true:

- [x] Core loop (detect live → notify → auto-open) is reliable
- [ ] Runs **unattended** (system tray) — completes the "leave it running while away" promise
- [x] Per-streamer control (auto-open toggle — done in v0.3.0)
- [ ] A stranger can set it up **solo** (guide does the job; screenshots help close this)
- [x] No known crashes / lost settings in normal use
- [ ] It can **tell users about updates** (update-check)
- [ ] I'd honestly call it "done & solid," not "early / beta"

**Realistic route:** v0.3.0 knocks out tray + toggle + update-check (the core-completeness items) →
let it run in real users' hands for a couple of weeks → if it holds up with no major bugs and the
guide gets someone set up solo, **that's your 1.0.** Dark mode / reorder / multi-select are *polish →
v1.1+*, not 1.0 blockers. You can always ship 1.0.1 the next day — shipped-and-good beats
unshipped-and-perfect.

---

## 🎯 v0.3.0 — Candidates (next up)

**🔨 Committed this cycle (~1.5–2 weeks; alpha-tested on my own machine before sharing):**
1. ✅ **Per-streamer auto-open toggle** — DONE (built + in the exe, 2026-06-14). Per-streamer
   `auto_open` flag (default on), Auto-Open column + checkbox + Toggle button, watcher notifies
   but skips the browser when off.
2. ✅ **Minimize to system tray** — DONE (confirmed in the exe, 2026-06-15). Tray icon + Show/Quit
   menu; the ✕ hides to tray (with a notification); plus a window **File → Quit / Hide to Tray** menu.
3. ✅ **Launch on Windows startup (run on login)** — DONE (in the exe, 2026-06-15). Settings toggle
   adds/removes an HKCU Run-key entry (no admin needed). With tray = the "unattended trifecta" done.
4. **"Create Desktop Shortcut" button** (quick win)
5. **Update check (check-and-notify)** (🟡 moderate — needs an `APP_VERSION` constant first; see the
   detailed bullet + the "forward-looking" caveat below)
6. **Dark / Light (+ System) mode** (do LAST — the flex; if the date's tight, cut THIS first)

Theme: *comfortable to leave running unattended, friendly to live with, easy on the eyes.*
Order protects the must-haves: if the week runs short, the earlier ones are already shipped and
dark mode rolls to v0.3.1. Scope is 6 now (one ✅ done; tray = the big climb; run-on-startup small;
shortcut quick; update-check moderate; dark mode = flex).
**🎯 Target release: ~2026-06-20/21 (next weekend).** To hit it, protect the *date, not the scope*:
ship toggle ✅ + tray + run-on-startup + shortcut on the 20th (+ update-check if tray lands smoothly). **Dark mode is
the flex item** — if it's not solid by then, it rolls to v0.3.1 a week later (totally normal). A dated
release with 3–4 solid features beats an open-ended one stalled on dark mode. Tray is the long pole —
start there.
**Update-check caveat:** it only notifies people who already *have* the version containing it. So
v0.3.0's checker starts the auto-notify chain from v0.3.0 onward; telling current v0.2.0 users about
v0.3.0 itself is still a manual announce.

- ⭐ **Minimize to system tray — PRIORITY for the next v0.3.0 session.** Run quietly in the
  background, no taskbar clutter, with a tray right-click menu (Show / Quit). The most
  on-purpose feature there is: it's exactly how you keep streaks alive while asleep/at work.
  *Build note:* use `pystray` (+ Pillow, already installed) running alongside the Tk loop; make
  the window's "X" minimize to tray instead of quitting (keep a real Quit in the tray menu).
  Bonus: `pystray` is cross-platform, so it carries over to the Mac/Linux goal.
- 🟡 **Dark / Light (+ System) mode** — ⬆ *committed this cycle (#4).* Base light/dark via
  `sv_ttk` is easy; the real work is recoloring the hardcoded bits to be theme-aware. **Color audit:**
  the *grays* are the problem — offline status, the `#666666` group headers, and the gray
  note/placeholder labels all wash out on dark. Make them theme-aware — DON'T hardcode white (it'd be
  invisible on the light theme); switch the neutral color with the theme, or just let those labels
  inherit the theme's default foreground. Accent colors mostly survive both: green "LIVE" is fine (a
  touch brighter pops more on dark), orange warning is fine — just sanity-check contrast. (Note: the
  🔴 in notifications is an emoji, not a color — fine on any background.) Options shape: **Light /
  Dark / System / Auto-by-time**. The "Auto-by-time" logic could adapt the day/night scheduling from the
  user's **SunShift** project (note: SunShift flips the *Windows* theme; here we theme the *app's*
  own window — same logic, different apply step). Apply at startup; avoid sudden bright flips.
  Strong must-have for a gamer audience.
- 🟢 **Screenshots in the setup guide** — add images via `make_guide.py`, rebuild
- 🟡 **Collapsible groups** — click a group header to fold/unfold it on Live Status (state remembered)
- 🟡 **Reorder groups** — arrange groups into the order you want (persisted)
- 🟡 **Reorder streamers** within a group
- 🟡 **Sort Live Status: online above offline** — float live streamers to the top so you see who's
  on at a glance. Requested by Aerwidh. Design Q: sort *within each group* (keep groups, live-first
  inside) vs a flat live-first list (drops grouping). Build note: rows are built once then updated
  in place today, so this needs re-sorting the row *order* when a status changes, not just updating
  labels — a bit more than a one-liner. User's stance: may not make the next update.
- 🟢 **Per-streamer auto-open toggle** — choose who auto-opens vs. who is notify-only (some
  streamers you want launched, others just a heads-up). Requested by wyntrblue. Easy: add a
  per-streamer flag (default ON, so today's behavior is unchanged) + a column/toggle in the
  Streamers tab, checked before `webbrowser.open`. Pairs naturally with the Drops-Only toggle.
- 🟢 **Show stream uptime** — display how long each live streamer has been live ("live for 3h 12m")
  on Live Status. Easy: the Helix Get Streams response already includes `started_at` (the app
  fetches it today but ignores it) — just parse it and show elapsed time, refreshed each poll. No
  new API calls or login. The happy opposite of the watch-streak number: Twitch hands this out freely.
- 🟢 **Dates on log timestamps** — the log shows time only (`20:17:58`); add the date so multi-day
  runs are readable. Matters specifically once the app lives in the tray running for days. Trivial:
  widen the `strftime` format. Nicer option: a "— Jun 13, 2026 —" divider line when the day rolls
  over, rather than repeating the date on every line.
  **i18n decision:** use an UNAMBIGUOUS date format — spelled-out month ("Jun 13") or ISO
  ("2026-06-13") — NOT numeric `MM/DD` or `DD/MM`, which US vs EU testers read differently (is
  06/07 June 7 or July 6?). Sidesteps locale handling entirely. Time stays 24-hour (already
  locale-safe); AM/PM could be an optional setting later if US testers want it.
- 🟡 **"Last live / did they stream today?" indicator** — answer "did they go live while I was away?"
  at a glance (real friction: logged in Saturday unsure if a friend had streamed). Two complementary
  approaches:
  - *App-side (🟢):* record when the app last saw each streamer live → show "last live: today 14:12 /
    yesterday / Jun 11". Easy, no API/login — but only knows what it saw *while running*, so it leans
    on the tray feature (keep running = keep observing). Doesn't cover gaps when the app was off.
  - *Query Twitch VODs (🟡):* Helix "Get Videos" (type=archive) to ask "did this user stream recently?"
    — works even if the app was off, and **app-token only (no login!)**. Needs username→user_id
    resolution, and only works for streamers who save VODs (some disable them).
- 🟡 **Limit simultaneous auto-opens** — cap how many streams open at once (e.g. max 2),
  with a launch priority order
- 🟡 **Title-change detection mid-stream** — alert on any title change, not just "drops"
- 🟡 **"Create Desktop Shortcut" button** (Settings) — one click makes a desktop shortcut to
  the app so non-technical users don't lose the exe in their Downloads folder. Windows: doable
  from within the app via a small PowerShell/COM call (no heavy deps). Mac/Linux: handle during
  the cross-platform work (dock alias / `.desktop` file).
- 🟢 **MIT license file** — makes the public repo properly open-source
- 🟢 **Import / export streamer list** — it's already JSON, so this is easy
- 🟡 **Update check (check-and-notify)** — on launch (and via a Settings "Check for updates" button),
  query the GitHub Releases API (the same `releases/latest` call we already use) and compare the
  latest tag to the app's own version; if newer, show "v0.3.0 available" + a button to open the
  release page. No login (public API). High value: it's how friends learn a new version exists
  instead of you pinging everyone. **Prerequisite:** add an `APP_VERSION` constant (also surface it
  in the title bar / an About line).
  *Avoid for now:* full silent self-update (download + replace the running exe) — 🔴 rabbit hole on
  Windows (a running onefile exe can't overwrite itself; needs a helper-relaunch dance). Keep the
  download manual.
- 🟡 **Multi-select / checkbox delete** — remove several streamers or drops-games at once
  instead of one-at-a-time. Light version: enable multi-highlight (Ctrl/Shift-click) on the
  existing lists. Fuller version: a checkbox next to each row + a Delete button (more
  discoverable, but needs custom widgets since Tkinter has no built-in checkbox list)

---

## 💡 Backlog / Someday
- 🔴🔒 **Import your followed channels from Twitch** — log in with your Twitch account, pull your
  follow list (Helix "Get Followed Channels" + the `user:read:follows` scope), and tick which ones
  to watch / auto-open instead of typing usernames. Wanted by wyntrblue — genuinely cool, likely a
  marquee v0.4.0/v1.0 feature. **Big lift:** the app currently only uses an *app* token; this adds a
  real **user login (OAuth)** + user-token storage/refresh. Stays true to "no website" — can use the
  `http://localhost` redirect already configured (tiny local handler) or the device-code flow.
- 🟡 **"Streak Keeper" counter** — app tracks how many consecutive days *it* caught each
  streamer live and nudges you to tune in. (Approximate — based on the app opening them,
  not Twitch's official number. See "Can't Do Yet" below.)
- 🟡 **Category browsing** — see who's live in a given game right now (Helix supports this)
- 🟡 **UI refresh — consider moving Settings into a menu** (e.g. File → Settings / a Preferences
  dialog) now that there's a menu bar. *Polish, not a feature* — reorganizes existing UI. Tradeoff:
  more conventional + frees tab space, BUT a visible Settings *tab* is arguably more discoverable for
  non-technical users (a core value). Best done as a deliberate UI pass bundled with the dark-mode /
  theming work (v0.4.0-ish), not mid-cycle. Idea sparked by adding the File menu.
- 🟢🔨 **Launch on Windows startup (run on login)** — register/unregister the app to start when
  Windows boots, via a Settings toggle (adds/removes a registry Run key or a Startup-folder
  shortcut). Requested by Aerwidh; **actively being worked on.** Distinct from the existing in-app
  "autostart watching" (that starts the *watcher* when the app opens; this launches the *app itself*
  on login). Completes the **unattended trifecta**: tray (background) + run-on-startup (survives
  reboots) + autostart-watching (auto-begins) = "leave a machine running to keep my streak." Pairs
  with the tray work — ⬆ **now committed to v0.3.0** (#3, build it with tray).
- 🔴 **Mac / Linux support** — the stack is ~90% portable (Python, Tkinter, requests, keyring
  are all cross-platform). What needs doing:
  - Replace Windows-only `os.startfile()` (PDF open) with `open` (Mac) / `xdg-open` (Linux)
  - Make the window icon cross-platform — `iconphoto()` + PNG instead of `.ico`/`iconbitmap()`
  - Genericize Windows-specific UI text ("Credential Manager" → Keychain / Secret Service)
  - Per-OS builds: PyInstaller can't cross-compile — build on each OS, ideally via GitHub
    Actions (free mac/linux/windows runners)
  - Test on each platform (notifications via plyer can vary)

---

## ⛔ Can't Do Yet (blocked by Twitch — would add if it becomes possible)
- 🔒 **Display Twitch's official watch-streak number** — *Wanted*, and would build it if the
  data existed. But Twitch currently exposes **no API** for a viewer's watch streak; it's an
  internal Channel Points feature surfaced only as a chat message (confirmed 2026-06-11).
  **Revisit if Twitch ever adds an endpoint** — at that point this becomes a real feature.
  Until then, the "Streak Keeper" backlog item is the closest approximation.

---

## 🧹 Housekeeping
- [ ] Test the exe on a truly clean machine (no Python installed) to confirm it's fully standalone
      — **planned: try it on the new laptop** (also the first true "fresh friend" first-run test,
      since there'll be no `TWITCH_CLIENT_ID` env var or stored secret)
