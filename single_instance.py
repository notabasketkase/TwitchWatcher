"""
single_instance.py — Ensure only one TwitchWatcher runs at a time.

Lock: a Windows named mutex. It's reboot-proof, needs no ports or special
permissions, and the OS releases it automatically when the process dies. This
is what actually decides "am I the only instance?".

Show-existing-window: a best-effort loopback socket. When a second launch is
blocked by the mutex, it tries to ping the running instance so it surfaces its
window. If that socket can't be set up — e.g. the port lands in a Windows
reserved range (Hyper-V/WSL grab chunks of the dynamic range on boot) — we just
skip it: the app still single-instances correctly, it only won't pop the window.

IMPORTANT — this FAILS OPEN. If anything about the lock check is uncertain, we
let the app run rather than silently refusing to start. An earlier version used
only a socket as the lock and treated a reserved-port bind error as "already
running", which made the app refuse to launch after a reboot shifted the
reserved ranges over the hardcoded port. Never again: the guard must not be able
to stop the app from starting.
"""

import socket
import threading
import ctypes
from ctypes import wintypes

# Session-namespaced mutex — shared across every launch path in the user's
# session (morning-wake task, run-on-startup, desktop shortcut).
_MUTEX_NAME = "TwitchWatcher_SingleInstance_v1"
_ERROR_ALREADY_EXISTS = 183

# Best-effort loopback port for the "show your window" ping. Kept below the
# default dynamic range (49152+) to dodge the usual Hyper-V/WSL reservations;
# if it's unavailable anyway we degrade gracefully (see module docstring).
_SHOW_HOST = "127.0.0.1"
_SHOW_PORT = 47654
_SHOW_MSG  = b"TW_SHOW"

try:
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.CreateMutexW.restype = wintypes.HANDLE
    _kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    _kernel32.CloseHandle.restype = wintypes.BOOL
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _MUTEX_SUPPORTED = True
except Exception:
    _MUTEX_SUPPORTED = False


class SingleInstance:
    def __init__(self):
        self._mutex = None
        self._sock = None
        self.is_primary = False

    def acquire(self):
        """Return True if we should run (we're the only/primary instance).

        Return False ONLY when we're confident another instance is already
        running — in which case we've asked it to show its window and the caller
        should exit. Any uncertainty fails open (returns True) so the app always
        starts.
        """
        if not _MUTEX_SUPPORTED:
            self.is_primary = True
            return True
        try:
            self._mutex = _kernel32.CreateMutexW(None, False, _MUTEX_NAME)
            err = ctypes.get_last_error()
        except Exception:
            self.is_primary = True
            return True
        if self._mutex and err == _ERROR_ALREADY_EXISTS:
            self._signal_existing()   # best-effort; ok if it does nothing
            # We're bowing out — drop our handle so we don't keep the mutex
            # alive past our own exit (the primary's handle keeps it held).
            self.release()
            return False
        # Fresh mutex (we're primary) OR creation failed → run either way.
        self.is_primary = True
        return True

    def _signal_existing(self):
        """Best-effort: tell the running instance to surface its window."""
        try:
            with socket.create_connection((_SHOW_HOST, _SHOW_PORT), timeout=2) as c:
                c.sendall(_SHOW_MSG)
        except OSError:
            pass  # can't reach it (port reserved/blocked) — just exit quietly

    def start_listener(self, on_show):
        """Best-effort: listen for 'show' pings from future launches.

        If the port can't be bound (reserved or in use), we skip listening. The
        app keeps running normally; it just won't receive show requests. on_show
        runs on a background thread and must marshal to the Tk thread itself
        (the app's _show_window already does).
        """
        if not self.is_primary:
            return
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind((_SHOW_HOST, _SHOW_PORT))
            s.listen(1)
        except OSError:
            try:
                s.close()
            except Exception:
                pass
            return  # no show-listener this run; app still runs fine
        self._sock = s

        def loop():
            while True:
                try:
                    conn, _addr = self._sock.accept()
                except OSError:
                    break  # socket closed during shutdown
                try:
                    if _SHOW_MSG in conn.recv(32):
                        on_show()
                except OSError:
                    pass
                finally:
                    try:
                        conn.close()
                    except OSError:
                        pass

        threading.Thread(target=loop, daemon=True).start()

    def release(self):
        """Drop the socket and mutex. Safe to call repeatedly."""
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        if self._mutex:
            try:
                _kernel32.CloseHandle(self._mutex)
            except Exception:
                pass
            self._mutex = None
