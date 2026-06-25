"""
twitch_api.py — Twitch Helix calls for live-stream status.

Token retrieval lives in credentials.py (get_app_token); this module just
queries which of the watched usernames are currently live.
"""

import requests

STREAMS_URL = "https://api.twitch.tv/helix/streams"


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
