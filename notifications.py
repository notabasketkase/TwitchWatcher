"""
notifications.py — Desktop toast notifications via plyer (optional dependency).
"""

try:
    from plyer import notification as plyer_notify
    PLYER_AVAILABLE = True
except ImportError:
    PLYER_AVAILABLE = False


def notify(title, message):
    if not PLYER_AVAILABLE:
        return
    try:
        plyer_notify.notify(title=title, message=message, app_name="Twitch Watcher", timeout=8)
    except Exception:
        pass
