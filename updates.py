"""
updates.py — Check GitHub Releases for a newer version of TwitchWatcher.
"""

import requests

from config import APP_VERSION, GITHUB_REPO


def _parse_version(s):
    """Turn 'v0.3.0' / '0.3.1' into a comparable tuple like (0, 3, 0)."""
    s = (s or "").lstrip("vV").strip()
    parts = []
    for chunk in s.split("."):
        digits = "".join(c for c in chunk if c.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts) if parts else (0,)


def get_latest_release():
    """Return (tag_name, html_url) for the latest GitHub release. Raises on failure."""
    resp = requests.get(
        f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "TwitchWatcher"},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("tag_name", ""), data.get("html_url", "")


def is_newer_version(latest_tag):
    """True if latest_tag is newer than this app's APP_VERSION."""
    return _parse_version(latest_tag) > _parse_version(APP_VERSION)
