"""
single_instance.py — Ensure only one TwitchWatcher runs at a time.

Uses a loopback TCP socket as the lock. The first instance binds a fixed
127.0.0.1 port and listens; a second launch can't bind that port, so it
connects to the running instance to tell it to surface its window, then
exits. Loopback-only means no firewall prompt, and the OS releases the
port automatically if the app crashes — no stale lock files to clean up.

This fixes duplicate launches from any source (the morning-wake scheduled
task, run-on-Windows-startup, a desktop double-click) all at once.
"""

import socket
import threading

# Fixed loopback port used purely as a single-instance lock + "show" signal.
# Picked from the dynamic/private range and bound to 127.0.0.1 only, so it
# never leaves the machine and won't trigger a Windows Firewall prompt.
_LOCK_HOST = "127.0.0.1"
_LOCK_PORT = 52789
_SHOW_MSG  = b"TW_SHOW"


class SingleInstance:
    def __init__(self):
        self._sock = None
        self.is_primary = False

    def acquire(self):
        """Try to become the single running instance.

        Returns True if we got the lock (we are the primary instance).
        Returns False if another instance already holds it — in that case we
        have already signalled the running instance to show its window, and
        the caller should exit without starting a second app.
        """
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind((_LOCK_HOST, _LOCK_PORT))
        except OSError:
            # Port already bound → another instance is running. Ask it to show.
            s.close()
            self._signal_existing()
            return False
        s.listen(1)
        self._sock = s
        self.is_primary = True
        return True

    def _signal_existing(self):
        """Connect to the running instance and ask it to surface its window."""
        try:
            with socket.create_connection((_LOCK_HOST, _LOCK_PORT), timeout=2) as c:
                c.sendall(_SHOW_MSG)
        except OSError:
            pass  # couldn't reach it; nothing more we can do, just exit

    def start_listener(self, on_show):
        """Spawn a daemon thread that calls on_show() when another launch pings.

        on_show runs on this background thread, so it must marshal back to the
        Tk main thread itself (the app's _show_window already does this).
        """
        if not self.is_primary or self._sock is None:
            return

        def loop():
            while True:
                try:
                    conn, _addr = self._sock.accept()
                except OSError:
                    break  # listening socket closed during shutdown
                try:
                    data = conn.recv(32)
                    if _SHOW_MSG in data:
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
        """Drop the lock (close the listening socket). Safe to call repeatedly."""
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
