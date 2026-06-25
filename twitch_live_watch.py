"""
twitch_live_watch.py — Entry point for the Twitch live watcher GUI.

The app is split across small modules in this folder:
  - config.py              app constants + config-file persistence
  - credentials.py         Client Secret storage (keyring) + app-token retrieval
  - twitch_api.py          Twitch Helix live-stream queries
  - updates.py             GitHub Releases update check
  - system_integration.py  run-on-login + Desktop shortcut (Windows)
  - notifications.py        desktop toast notifications (plyer)
  - ui.py                  the TwitchWatcherApp window, tabs, and watch loop

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

import tkinter as tk

from ui import TwitchWatcherApp


def main():
    root = tk.Tk()
    app = TwitchWatcherApp(root)
    app._rebuild_live_rows()
    root.mainloop()


if __name__ == "__main__":
    main()
