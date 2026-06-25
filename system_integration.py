"""
system_integration.py — Windows OS integration: run-on-login registry entry
and Desktop shortcut creation.
"""

import os
import sys

try:
    import winreg
    WINREG_AVAILABLE = True
except ImportError:
    WINREG_AVAILABLE = False

RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_KEY_NAME = "TwitchWatcher"


def _entry_script():
    """Absolute path to the launched entry script (twitch_live_watch.py).

    Uses sys.argv[0] rather than __file__ so it stays pointed at the real entry
    point now that this code lives in its own module. Only used in non-frozen
    (script) mode; the frozen .exe uses sys.executable instead.
    """
    return os.path.abspath(sys.argv[0])


def _startup_command():
    """The command Windows runs on login (quoted for paths with spaces)."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    return f'"{sys.executable}" "{_entry_script()}"'


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


def create_desktop_shortcut():
    """Create a TwitchWatcher shortcut on the user's Desktop (Windows, via WScript.Shell)."""
    import subprocess
    if getattr(sys, "frozen", False):
        target    = sys.executable
        arguments = ""
        workdir   = os.path.dirname(sys.executable)
        icon      = sys.executable  # the exe carries the embedded icon
    else:
        script    = _entry_script()
        target    = sys.executable  # python / pythonw
        arguments = f'"{script}"'
        workdir   = os.path.dirname(script)
        ico       = os.path.join(workdir, "icon.ico")
        icon      = ico if os.path.exists(ico) else target

    def q(s):  # quote a value as a PowerShell single-quoted literal
        return "'" + str(s).replace("'", "''") + "'"

    ps = (
        "$ws = New-Object -ComObject WScript.Shell; "
        "$d = [Environment]::GetFolderPath('Desktop'); "
        "$s = $ws.CreateShortcut((Join-Path $d 'TwitchWatcher.lnk')); "
        f"$s.TargetPath = {q(target)}; "
        f"$s.Arguments = {q(arguments)}; "
        f"$s.WorkingDirectory = {q(workdir)}; "
        f"$s.IconLocation = {q(icon)}; "
        "$s.Description = 'TwitchWatcher'; "
        "$s.Save()"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
        check=True, capture_output=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
