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

## 🎯 v0.3.0 — Candidates (next up)
Pick a few; these are the strongest from the old "v0.2.0 planned" list plus new ideas.

- 🟡 **Minimize to system tray** — run quietly in the background, no taskbar clutter.
  *(High value: directly serves the "watch streaks while away" purpose.)*
- 🟡 **Dark / light mode toggle** (e.g. `sv_ttk`)
- 🟢 **Screenshots in the setup guide** — add images via `make_guide.py`, rebuild
- 🟡 **Drag to reorder** groups and streamers within groups
- 🟡 **Limit simultaneous auto-opens** — cap how many streams open at once (e.g. max 2),
  with a launch priority order
- 🟡 **Title-change detection mid-stream** — alert on any title change, not just "drops"
- 🟢 **MIT license file** — makes the public repo properly open-source
- 🟢 **Import / export streamer list** — it's already JSON, so this is easy

---

## 💡 Backlog / Someday
- 🟡 **"Streak Keeper" counter** — app tracks how many consecutive days *it* caught each
  streamer live and nudges you to tune in. (Approximate — based on the app opening them,
  not Twitch's official number. See "Can't Do Yet" below.)
- 🟡 **Category browsing** — see who's live in a given game right now (Helix supports this)
- 🟢 **Windows startup entry** — launch on Windows login (separate from "autostart watching")
- 🔴 **Mac / Linux support** — keyring is cross-platform; need to replace `os.startfile`
  and do per-OS packaging

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
